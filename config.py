#!/usr/bin/env python3
"""Config for Audiobookshelf Sync plugin for calibre"""

import os
import json
from functools import partial
from datetime import datetime, timedelta

from PyQt5.Qt import (
    QComboBox,
    QCheckBox,
    QGroupBox,
    QPushButton,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QHBoxLayout,
    QVBoxLayout,
    QFormLayout,
    QWidget,
    QSpinBox,
    QFrame,
    QDialog,
    QSizePolicy,
    Qt,
)
from PyQt5.QtGui import QPixmap
from calibre.constants import numeric_version
from calibre.devices.usbms.driver import debug_print as root_debug_print
from calibre.utils.iso8601 import local_tz
from calibre.utils.config import JSONConfig
from calibre.gui2 import show_restart_warning, info_dialog, error_dialog
from calibre.customize.ui import initialized_plugins
from calibre.customize import PluginInstallationType

__license__ = 'GNU GPLv3'
__copyright__ = '2025, jbhul'

'''
Each entry in the below dict has the following keys:
Each entry is keyed by the name of the config item used to store the selected column's lookup name
  first_in_group (optional): If present and true, a separator will be added before this item in the Config UI.
                             If this is a string a QLabel with bolded string value will be added below the separator.
  column_heading: Default custom column heading
  datatype: Default custom column datatype
  is_multiple (optional): tuple (bool, bool), only for text columns. First bool is make default new column multiple values (tags). Second bool is only is_multiple columns in dropdown.
  additional_params (optional): additional parameters for the custom column display parameter as specified in the calibre API as a dictionary.
    https://github.com/kovidgoyal/calibre/blob/bc29562c0c8534b349c9d330ac9aec72eef2be99/src/calibre/gui2/preferences/create_custom_column.py#L901
  description: Default custom column description
  default_lookup_name: Name of the config item to store the selected column
  config_label: Label for the item in the Config UI
  config_tool_tip: Tooltip for the item in the Config UI
  api_source: Source of the data; "lib_items" for the GET /api/libraries/{ID}/items endpoint,
              "mediaProgress" for the GET /api/me endpoint,
              "collections" for the combined GET /api/collections /api/playlists endpoints,
              "audible" for the GET api.audible.com/1.0/catalog/products endpoint,
              "sessions" for the GET /api/me/listening-sessions endpoint.
  data_location: Reference (as a list of keys) to the value in the API response.
  transform (optional): lambda expression to be applied in formatting the value.
'''
CUSTOM_COLUMN_DEFAULTS = {
    'column_audiobook_title': {
        'column_heading': _("Audiobook Title"),
        'datatype': 'text',
        'description': _("Title of the audiobook"),
        'default_lookup_name': '#abs_title',
        'config_label': _('Title*:'),
        'config_tool_tip': _('A "Text" column to store the title from the audiobook metadata.'),
        'api_source': "lib_items",
        'data_location': ['media', 'metadata', 'title'],
    },
    'column_audiobook_subtitle': {
        'column_heading': _("Audiobook Subtitle"),
        'datatype': 'text',
        'description': _("Subtitle of the audiobook"),
        'default_lookup_name': '#abs_subtitle',
        'config_label': _('Subtitle*:'),
        'config_tool_tip': _('A "Text" column to store the subtitle from the audiobook metadata.'),
        'api_source': "lib_items",
        'data_location': ['media', 'metadata', 'subtitle'],
    },
    'column_audiobook_description': {
        'column_heading': _("Audiobook Description"),
        'datatype': 'comments',
        'description': _("Description of the audiobook"),
        'default_lookup_name': '#abs_description',
        'config_label': _('Description*:'),
        'config_tool_tip': _('A "Long text" column to store the description from the audiobook metadata.'),
        'api_source': "lib_items",
        'data_location': ['media', 'metadata', 'description'],
    },
    'column_audiobook_narrator': {
        'column_heading': _("Audiobook Narrator"),
        'datatype': 'text',
        'is_multiple': (True, False),
        'additional_params': {'is_names': True},
        'description': _("Narrator name(s)"),
        'default_lookup_name': '#abs_narrator',
        'config_label': _('Narrator*:'),
        'config_tool_tip': _('A "Text" column to store the narrator name(s) from the audiobook metadata.'),
        'api_source': "lib_items",
        'data_location': ['media', 'metadata', 'narratorName'],
        'transform': (lambda value: None if not value else [narrator.strip() for narrator in value.split(',')]),
    },
    'column_audiobook_author': {
        'column_heading': _("Audiobook Author"),
        'datatype': 'text',
        'is_multiple': (True, False),
        'additional_params': {'is_names': True},
        'description': _("Author name(s)"),
        'default_lookup_name': '#abs_author',
        'config_label': _('Author*:'),
        'config_tool_tip': _('A "Text" column to store the author name(s) from the audiobook metadata.'),
        'api_source': "lib_items",
        'data_location': ['media', 'metadata', 'authorName'],
        'transform': (lambda value: None if not value else [author.strip() for author in value.split(',')]),
    },
    'column_audiobook_chapters': {
        'column_heading': _("Audiobook Chapters"),
        'datatype': 'comments',
        'description': _("List of Chapters with Timestamps."),
        'default_lookup_name': '#abs_chapters',
        'config_label': _('Chapters:'),
        'config_tool_tip': _('A "Long text" column to store the chapters and timestamps from the audiobook metadata.'),
        'api_source': "itemDetail",
    },
    'column_audiobook_series': {
        'column_heading': _("Audiobook Series"),
        'datatype': 'series',
        'description': _("Series of the audiobook"),
        'default_lookup_name': '#abs_series',
        'config_label': _('Series*:'),
        'config_tool_tip': _('A "series" column to store the series from the audiobook metadata.'),
        'api_source': "lib_items",
        'data_location': ['media', 'metadata', 'seriesName'],
        'transform': (lambda value: None if not value else (value.split(" #")[0].strip(), float(value.split(" #")[1].split(",")[0]) if len(value.split(" #")) > 1 else float(1))),
    },
    'column_audiobook_language': {
        'column_heading': _("Audiobook Language"),
        'datatype': 'text',
        'description': _("Language of the audiobook"),
        'default_lookup_name': '#abs_language',
        'config_label': _('Language*:'),
        'config_tool_tip': _('A "Text" column to store the language from the audiobook metadata.'),
        'api_source': "lib_items",
        'data_location': ['media', 'metadata', 'language'],
    },
    'column_audiobook_genres': {
        'column_heading': _("Audiobook Genres"),
        'datatype': 'text',
        'is_multiple': (True, True),
        'description': _("Genres tagged for the audiobook."),
        'default_lookup_name': '#abs_genres',
        'config_label': _('Genres*:'),
        'config_tool_tip': _('A "Text" column to store the genres from the audiobook metadata.'),
        'api_source': "lib_items",
        'data_location': ['media', 'metadata', 'genres'],
        'transform': (lambda genres: [genre.replace(',', ';') for genre in genres]),
    },
    'column_audiobook_tags': {
        'column_heading': _("Audiobook Tags"),
        'datatype': 'text',
        'is_multiple': (True, True),
        'description': _("Tags associated with the audiobook."),
        'default_lookup_name': '#abs_tags',
        'config_label': _('Tags*:'),
        'config_tool_tip': _('A "Text" column to store the tags from the audiobook metadata.'),
        'api_source': "lib_items",
        'data_location': ['media', 'tags'],
        'transform': (lambda tags: [tag.replace(',', ';') for tag in tags]),
    },
    'column_audiobook_publisher': {
        'column_heading': _("Audiobook Publisher"),
        'datatype': 'text',
        'description': _("Publisher of the audiobook"),
        'default_lookup_name': '#abs_publisher',
        'config_label': _('Publisher*:'),
        'config_tool_tip': _('A "Text" column to store the publisher from the audiobook metadata.'),
        'api_source': "lib_items",
        'data_location': ['media', 'metadata', 'publisher'],
    },
    'column_audiobook_publish_year': {
        'column_heading': _("Audiobook Publish Year"),
        'datatype': 'int',
        'description': _("Year the audiobook was published"),
        'default_lookup_name': '#abs_publish_year',
        'config_label': _('Publish Year*:'),
        'config_tool_tip': _('A "Integer" column to store the year the audiobook was published.'),
        'api_source': "lib_items",
        'data_location': ['media', 'metadata', 'publishedYear'],
        'transform': (lambda value: int(value)),
    },
    'column_audiobook_abridged': {
        'column_heading': _("Audiobook Abridged"),
        'datatype': 'bool',
        'description': _("Indicates if the audiobook is abridged"),
        'default_lookup_name': '#abs_abridged',
        'config_label': _('Abridged?*:'),
        'config_tool_tip': _('A "Yes/No" column to indicate if the audiobook is abridged.'),
        'api_source': "lib_items",
        'data_location': ['media', 'metadata', 'abridged'],
        'transform': (lambda value: bool(value)),
    },
    'column_audiobook_explicit': {
        'column_heading': _("Audiobook Explicit"),
        'datatype': 'bool',
        'description': _("Indicates if the audiobook is explicit"),
        'default_lookup_name': '#abs_explicit',
        'config_label': _('Explicit?*:'),
        'config_tool_tip': _('A "Yes/No" column to indicate if the audiobook is explicit.'),
        'api_source': "lib_items",
        'data_location': ['media', 'metadata', 'explicit'],
        'transform': (lambda value: bool(value)),
    },
    'column_audiobook_size': {
        'first_in_group': True,
        'column_heading': _("Audiobook Size"),
        'datatype': 'int',
        'additional_params': {'number_format': "{:,d} MB"},
        'description': _("Size of the audiobook in MB"),
        'default_lookup_name': '#abs_size',
        'config_label': _('Size:'),
        'config_tool_tip': _('An "Integer" column to store the audiobook size in MB (formatted with commas as thousands separators).'),
        'api_source': "lib_items",
        'data_location': ['size'],
        'transform': lambda value: int(float(value) / (1024*1024)),
    },
    'column_audiobook_duration': {
        'column_heading': _("Audiobook Duration"),
        'datatype': 'text',
        'description': _("Duration of the audiobook formatted (Hrs:Min)"),
        'default_lookup_name': '#abs_duration',
        'config_label': _('Duration:'),
        'config_tool_tip': _('A "Text" column to store the duration of the audiobook in Hrs:Min format.'),
        'api_source': "lib_items",
        'data_location': ['media', 'duration'],
        'transform': (lambda value: f"{int(float(value)//3600)}:{int((float(value) % 3600)//60):02d}"),
    },
    'column_audiobook_numfiles': {
        'column_heading': _("Audiobook File Count"),
        'datatype': 'int',
        'description': _("Number of files that comprise the audiobook"),
        'default_lookup_name': '#abs_numfiles',
        'config_label': _('File Count:'),
        'config_tool_tip': _('An "Integer" column to store the number of files in the audiobook.'),
        'api_source': "lib_items",
        'data_location': ['numFiles'],
    },
    'column_audiobook_supfiles': {
        'column_heading': _("Audiobook Supplementary Files"),
        'datatype': 'text',
        'description': _("Number and list of supplementary files that accompany the audiobook"),
        'default_lookup_name': '#abs_supfiles',
        'config_label': _('Supplementary Files:'),
        'config_tool_tip': _('An "Text" column to store the number and list of supplementary files that accompany the audiobook.'),
        'api_source': "itemDetail",
    },
    'column_audiobook_numchapters': {
        'column_heading': _("Audiobook Chapter Count"),
        'datatype': 'int',
        'description': _("Number of chapters in the audiobook"),
        'default_lookup_name': '#abs_numchapters',
        'config_label': _('Chapter Count:'),
        'config_tool_tip': _('An "Integer" column to store the number of chapters in the audiobook.'),
        'api_source': "lib_items",
        'data_location': ['media', 'numChapters'],
    },
    'column_audiobookshelf_library': {
        'first_in_group': 'Audiobookshelf',
        'column_heading': _("Audiobookshelf Library"),
        'datatype': 'text',
        'description': _("Audiobookshelf Library the audiobook is located in"),
        'default_lookup_name': '#abs_library',
        'config_label': _('Library:'),
        'config_tool_tip': _('A "Text" column to store the Audiobookshelf Library the audiobook is located in.'),
        'api_source': "lib_items",
        'data_location': ['libraryName'],
    },
    'column_audiobookshelf_addedDate': {
        'column_heading': _("Audiobookshelf Date Added"),
        'datatype': 'datetime',
        'description': _("The date the audiobook was added to Audiobookshelf"),
        'default_lookup_name': '#abs_addeddate',
        'config_label': _('Date Added:'),
        'config_tool_tip': _('A "Date" column to store the date the audiobook was added to Audiobookshelf.'),
        'api_source': "lib_items",
        'data_location': ['addedAt'],
        'transform': lambda value: datetime.fromtimestamp(int(value/1000)).replace(tzinfo=local_tz),
    },
    'column_audiobookshelf_full_path': {
        'column_heading': _("Audiobookshelf Full Path"),
        'datatype': 'text',
        'description': _("Full path to the audiobook"),
        'default_lookup_name': '#abs_fullpath',
        'config_label': _('Full Path:'),
        'config_tool_tip': _('A "Text" column to store the full path to the audiobook.'),
        'api_source': "lib_items",
        'data_location': ['path'],
    },
    'column_audiobookshelf_rel_path': {
        'column_heading': _("Audiobookshelf Relative Path"),
        'datatype': 'text',
        'description': _("Relative Path of the audiobook"),
        'default_lookup_name': '#abs_relpath',
        'config_label': _('Relative Path:'),
        'config_tool_tip': _('A "Text" column to store the relative (from library) path to the audiobook.'),
        'api_source': "lib_items",
        'data_location': ['relPath'],
    },
    'column_audiobook_lastread': {
        'first_in_group': True,
        'column_heading': _("Audiobook Last Read Date"),
        'datatype': 'datetime',
        'description': _("The last date the audiobook was read"),
        'default_lookup_name': '#abs_lastread',
        'config_label': _('Last Read Date:'),
        'config_tool_tip': _('A "Date" column to store the last date the audiobook was read.'),
        'api_source': "mediaProgress",
        'data_location': ['lastUpdate'],
        'transform': lambda value: datetime.fromtimestamp(int(value/1000)).replace(tzinfo=local_tz),
    },
    'column_audiobook_progress_float': {
        'column_heading': _("Audiobook Precise Progress"),
        'datatype': 'float',
        'additional_params': {'number_format': "{:.2f}%"},
        'description': _("Progress percentage with decimal precision"),
        'default_lookup_name': '#abs_progfloat',
        'config_label': _('Precise Progress (#.##%):'),
        'config_tool_tip': _('A "Float" column to store the precise reading progress with decimal places.'),
        'api_source': "mediaProgress",
        'data_location': ['progress'],
        'transform': (lambda value: round(float(value) * 100, 2)),
    },
    'column_audiobook_progress_int': {
        'column_heading': _("Audiobook Progress"),
        'datatype': 'int',
        'additional_params': {'number_format': "{}%"},
        'description': _("Progress percentage as a whole number"),
        'default_lookup_name': '#abs_progint',
        'config_label': _('Progress (#%):'),
        'config_tool_tip': _('An "Integer" column to store the reading progress (0-100).'),
        'api_source': "mediaProgress",
        'data_location': ['progress'],
        'transform': (lambda value: round(float(value) * 100)),
    },
    'column_audiobook_progress_time': {
        'column_heading': _("Audiobook Progress Time"),
        'datatype': 'text',
        'description': _("Current audiobook progress time formatted as Hrs:Min"),
        'default_lookup_name': '#abs_progresstime',
        'config_label': _('Progress Time:'),
        'config_tool_tip': _('A "Text" column to store the progress time formatted as Hrs:Min.'),
        'api_source': "mediaProgress",
        'data_location': ['currentTime'],
        'transform': (lambda value: f"{int(float(value)//3600)}:{int((float(value)%3600)//60):02d}"),
    },
    'column_audiobook_progress_time_remaining': {
        'column_heading': _("Audiobook Time Remaining"),
        'datatype': 'text',
        'description': _("Time remaining in audiobook as Hrs:Min"),
        'default_lookup_name': '#abs_progresstimeremaining',
        'config_label': _('Time Remaining:'),
        'config_tool_tip': _('A "Text" column to store the time remaining in audiobook formatted as Hrs:Min.'),
        'api_source': "mediaProgress",
        'data_location': [],
        'transform': (lambda value: (
            f"{int(progress_time_remaining // 3600)}:{int((progress_time_remaining % 3600) // 60):02d}"
            if value.get('duration') and (progress_time_remaining := value["duration"] - value['currentTime']) is not None
            else '-'
        )),
    },
    'column_audiobook_listen_time': {
        'column_heading': _("Audiobook Listen Time"),
        'datatype': 'text',
        'description': _("Current audiobook listen time formatted as Hrs:Min"),
        'default_lookup_name': '#abs_listentime',
        'config_label': _('Listen Time:'),
        'config_tool_tip': _('A "Text" column to store the listen time factoring skips formatted as Hrs:Min.'),
        'api_source': "sessions",
        'data_location': ['total_time_listening'],
        'transform': (lambda value: f"{int(float(value)//3600)}:{int((float(value)%3600)//60):02d}"),
    },
    'column_audiobook_session_time': {
        'column_heading': _("Audiobook Session Time"),
        'datatype': 'text',
        'description': _("Current audiobook session time formatted as Hrs:Min"),
        'default_lookup_name': '#abs_sessiontime',
        'config_label': _('Session Time:'),
        'config_tool_tip': _('A "Text" column to store the session time factoring speed formatted as Hrs:Min.'),
        'api_source': "sessions",
        'data_location': [],
        'transform': (lambda value: (
            f"{int(est_session_time // 3600)}:{int((est_session_time % 3600) // 60):02d}"
            if (speed := value.get('filtered_avg_speed')) and (est_session_time := value.get('total_progression') / speed)
            else None
        )),
    },
    'column_audiobook_session_time_remaining': {
        'column_heading': _("Audiobook Time to Finish"),
        'datatype': 'text',
        'description': _("Time to finish audiobook factoring speed as Hrs:Min"),
        'default_lookup_name': '#abs_sessiontimeremaining',
        'config_label': _('Time to Finish:'),
        'config_tool_tip': _('A "Text" column to store the time to finish audiobook factoring speed formatted as Hrs:Min.'),
        'api_source': "sessions",
        'data_location': [],
        'transform': (lambda value: (
            f"{int(est_session_time_remaining // 3600)}:{int((est_session_time_remaining % 3600) // 60):02d}"
            if (speed := value.get('filtered_avg_speed')) and (est_session_time_remaining := (min((s["durationRemaining"] for s in value['sessions']))) / speed) is not None
            else '-'
        )),
    },
    'column_audiobook_started': {
        'first_in_group': True,
        'column_heading': _("Audiobook Started?"),
        'datatype': 'bool',
        'description': _("Indicates if the audiobook has been started"),
        'default_lookup_name': '#abs_started',
        'config_label': _('Audiobook Started?:'),
        'config_tool_tip': _('A "Yes/No" column to indicate if the audiobook has been started.'),
        'api_source': "mediaProgress",
        'data_location': [],  # No direct key; will be computed if mediaProgress is missing
        'transform': (lambda value: bool(value)),
    },
    'column_audiobook_begindate': {
        'column_heading': _("Audiobook Begin Date"),
        'datatype': 'datetime',
        'description': _("The date when the audiobook reading began"),
        'default_lookup_name': '#abs_begindate',
        'config_label': _('Begin Date:'),
        'config_tool_tip': _('A "Date" column to store when the audiobook reading began.'),
        'api_source': "mediaProgress",
        'data_location': ['startedAt'],
        'transform': lambda value: datetime.fromtimestamp(int(value/1000)).replace(tzinfo=local_tz),
    },
    'column_audiobook_status_text': {
        'column_heading': _("Audiobook Status"),
        'datatype': 'text',
        'description': _("Status of the audiobook (started/finished)"),
        'default_lookup_name': '#abs_status_text',
        'config_label': _('Audiobook Status:'),
        'config_tool_tip': _('A text column to indicate the status of the audiobook (started/finished).'),
        'api_source': "mediaProgress",
        'data_location': [],  # No direct key; will be computed if mediaProgress is missing
    },
    'column_audiobook_finished': {
        'first_in_group': True,
        'column_heading': _("Audiobook Finished?"),
        'datatype': 'bool',
        'description': _("Indicates if the audiobook has been finished"),
        'default_lookup_name': '#abs_finished',
        'config_label': _('Audiobook Finished?:'),
        'config_tool_tip': _('A "Yes/No" column to indicate if the audiobook has been finished.'),
        'api_source': "mediaProgress",
        'data_location': ['isFinished'],
        'transform': (lambda value: bool(value)),
    },    
    'column_audiobook_finishdate': {
        'column_heading': _("Audiobook Finish Date"),
        'datatype': 'datetime',
        'description': _("The date when the audiobook was finished"),
        'default_lookup_name': '#abs_finishdate',
        'config_label': _('Finish Date:'),
        'config_tool_tip': _('A "Date" column to store when the audiobook was finished.'),
        'api_source': "mediaProgress",
        'data_location': ['finishedAt'],
        'transform': lambda value: datetime.fromtimestamp(int(value/1000)).replace(tzinfo=local_tz),
    },
    'column_audiobook_avg_playback_speed': {
        'column_heading': _("Audiobook Average Playback Speed"),
        'datatype': 'float',
        'additional_params': {'number_format': "{:.2f}x"},
        'description': _("Average Audiobook Playback Speed"),
        'default_lookup_name': '#abs_avgspeed',
        'config_label': _('Average Playback Speed:'),
        'config_tool_tip': _('An "Float" column to store the Average Playback Speed of the Audiobook.'),
        'api_source': "sessions",
        'data_location': ['filtered_avg_speed'],
    },
        'column_audiobook_max_playback_speed': {
        'column_heading': _("Audiobook Max Playback Speed"),
        'datatype': 'float',
        'additional_params': {'number_format': "{:.2f}x"},
        'description': _("Highest Audiobook Playback Speed"),
        'default_lookup_name': '#abs_maxspeed',
        'config_label': _('Max Playback Speed:'),
        'config_tool_tip': _('An "Float" column to store the Highest Session Playback Speed of the Audiobook.'),
        'api_source': "sessions",
        'data_location': ['filtered_max_speed'],
    },
    'column_audiobook_session_count': {
        'column_heading': _("Audiobook # of Reading Sessions"),
        'datatype': 'int',
        'description': _("The # of sessions you listened to the audiobook"),
        'default_lookup_name': '#abs_sessioncount',
        'config_label': _('# of Reading Sessions:'),
        'config_tool_tip': _('An "Integer" column to store when the number of times you did a playback session of the Audiobook.'),
        'api_source': "sessions",
        'data_location': ['session_count'],
    },
    'column_audiobook_avg_session_length': {
        'column_heading': _("Audiobook Avg Session Length"),
        'datatype': 'text',
        'description': _("The average time spent actually listening to the audiobook factoring speed as Hrs:Min"),
        'default_lookup_name': '#abs_avgsessionlength',
        'config_label': _('Average Session Length:'),
        'config_tool_tip': _('An "Text" column to store when the average time spent actually listening to the audiobook factoring speed as Hrs:Min.'),
        'api_source': "sessions",
        'data_location': ['filtered_avg_session_duration'],
        'transform': (lambda value: f"{int(float(value)//3600)}:{int((float(value)%3600)//60):02d}"),
    },
    'column_audiobook_reading_day_count': {
        'column_heading': _("Audiobook # of Days Read"),
        'datatype': 'int',
        'description': _("The # of days you listened to the audiobook"),
        'default_lookup_name': '#abs_readingdaycount',
        'config_label': _('# of Days Read:'),
        'config_tool_tip': _('An "Integer" column to store when the number of days you did a playback session of the Audiobook.'),
        'api_source': "sessions",
        'data_location': ['distinct_date_count'],
    },
    'column_audiobook_daystofinish': {
        'column_heading': _("Audiobook Days to Finish"),
        'datatype': 'text',
        'description': _("The time between book start and finish formatted as Days:Hrs:Min"),
        'default_lookup_name': '#abs_daystofinish',
        'config_label': _('Days to Finish:'),
        'config_tool_tip': _('A "text" column to store the time between book start and finish formatted as Days:Hrs:Min.'),
        'api_source': "mediaProgress",
        'data_location': [],
        'transform': (lambda value: (   lambda delta: f"{delta.days:,d}:{delta.seconds//3600:02d}:{(delta.seconds//60)%60:02d}"
                                    )(  datetime.fromtimestamp(int(value['finishedAt']/1000)).replace(tzinfo=local_tz) -
                                        datetime.fromtimestamp(int(value['startedAt']/1000)).replace(tzinfo=local_tz)
                                    ) if bool(value.get('isFinished')) else None),
    },
    'column_audiobook_bookmarks': {
        'first_in_group': True,
        'column_heading': _("Audiobook Bookmarks"),
        'datatype': 'comments',
        'description': _("Bookmarks in the format 'title at time' (time as hh:mm:ss)"),
        'default_lookup_name': '#abs_bookmarks',
        'config_label': _('Bookmarks:'),
        'config_tool_tip': _('A "Long text" column to store the audiobook bookmarks with timestamps'),
        'api_source': "mediaProgress",
        'data_location': ['bookmarks'],
        'transform': (lambda bookmarks: "\n".join(
            f"{b.get('title', 'No Title')} at {str(timedelta(seconds=b.get('time', 0)))}" for b in bookmarks) 
            if bookmarks else 'No Bookmarks'),
    },
    'column_audiobook_collections': {
        'column_heading': _("Audiobook Collections"),
        'datatype': 'text',
        'is_multiple': (True, True),
        'description': _("Collections and Playlists associated with the audiobook"),
        'default_lookup_name': '#abs_collections',
        'config_label': _('Collections*:'),
        'config_tool_tip': _('A "Text" column to store the names of collections and playlists the audiobook is associated with as tags.'),
        'api_source': "collections",
        'data_location': ['collections'],
    },
    'column_audible_avgrating': {
        'first_in_group': 'Audible',
        'column_heading': _("Audible Average Rating"),
        'datatype': 'rating',
        'additional_params': {'allow_half_stars': True},
        'description': _("Average overall rating on Audible"),
        'default_lookup_name': '#abs_avgrating',
        'config_label': _('Average Rating:'),
        'config_tool_tip': _('A "rating" column to store the average overall rating from Audible with half stars.'),
        'api_source': "audible",
        'data_location': ['rating', 'overall_distribution', 'display_stars'],
    },
    'column_audible_avgperformancerating': {
        'column_heading': _("Audible Average Performance Rating"),
        'datatype': 'rating',
        'additional_params': {'allow_half_stars': True},
        'description': _("Average Performance rating on Audible"),
        'default_lookup_name': '#abs_avgperfrating',
        'config_label': _('Average Performance Rating:'),
        'config_tool_tip': _('A "rating" column to store the average performance rating from Audible with half stars.'),
        'api_source': "audible",
        'data_location': ['rating', 'performance_distribution', 'display_stars'],
    },
    'column_audible_avgstoryrating': {
        'column_heading': _("Audible Average Story Rating"),
        'datatype': 'rating',
        'additional_params': {'allow_half_stars': True},
        'description': _("Average Story rating on Audible"),
        'default_lookup_name': '#abs_avgstoryrating',
        'config_label': _('Average Story Rating:'),
        'config_tool_tip': _('A "rating" column to store the average story rating from Audible with half stars.'),
        'api_source': "audible",
        'data_location': ['rating', 'story_distribution', 'display_stars'],
    },
    'column_audible_numratings': {
        'column_heading': _("Audible Rating Count"),
        'datatype': 'int',
        'additional_params': {'number_format': "{:,d}"},
        'description': _("Number of ratings on Audible"),
        'default_lookup_name': '#abs_numratings',
        'config_label': _('Rating Count:'),
        'config_tool_tip': _('An "Integer" column to store the number of (star) ratings on Audible.'),
        'api_source': "audible",
        'data_location': ['rating', 'overall_distribution', 'num_ratings'],
    },
    'column_audible_numreviews': {
        'column_heading': _("Audible Review Count"),
        'datatype': 'int',
        'additional_params': {'number_format': "{:,d}"},
        'description': _("Number of reviews on Audible"),
        'default_lookup_name': '#abs_numreviews',
        'config_label': _('Review Count:'),
        'config_tool_tip': _('An "Integer" column to store the number of (text) reviews on Audible.'),
        'api_source': "audible",
        'data_location': ['rating', 'num_reviews'],
    },
}

CHECKBOXES = { # Each entry in the below dict is keyed with config_name
    'checkbox_enable_scheduled_sync': {
        'config_label': 'Enable Daily Sync',
        'config_tool_tip': 'Enable daily sync of metadata using Audiobookshelf\'s API.',
    },
    'checkbox_scheduled_sync_show_log': {
        'config_label': 'Show Daily Sync Log',
        'config_tool_tip': 'Default false. Show the log popup after the automatic daily sync.',
    },
    'checkbox_enable_Audible_ASIN_sync': {
        'config_label': 'Enable Audible ASIN Sync',
        'config_tool_tip': 'Enable sync of the Audible identifier and Audible link.',
    },
    'checkbox_cache_QuickLink_history': {
        'config_label': 'Cache QuickLink History',
        'config_tool_tip': "Stores the id of calibre books that failed to QuickLink and doesn't try to QuickLink them again.",
        'default': True,
    },
    'checkbox_enable_writeback': {
        'config_label': 'Enable Writeback',
        'config_tool_tip': 'If columns marked with a * are changed in calibre, update ABS.',
    },
    'checkbox_sync_only_if_more_recent': {
        'config_label': 'Only Sync if Audiobookshelf Has New Data',
        'config_tool_tip': "Only updates metadata if the data from Audiobookshelf is more recent than the data stored in calibre.",
    },
    'checkbox_no_sync_if_finished': {
        'config_label': 'Skip Sync if Audiobook is Already Finished',
        'config_tool_tip': "Does not sync the audiobook again if the status in calibre already indicates that it is already finished.",
    },
    'checkbox_unlink_button': {
        'config_label': 'Show Unlink Button',
        'config_tool_tip': 'Adds "Remove ABS Link" button to toolbar that allows for easy un-linking of books.',
    },
}

CONFIG = JSONConfig(os.path.join('plugins', 'Audiobookshelf Sync.json'))
# Set specific defaults
CONFIG.defaults['abs_url'] = 'http://localhost:13378'
CONFIG.defaults['abs_key'] = ''
CONFIG.defaults['scheduleSyncHour'] = 4
CONFIG.defaults['scheduleSyncMinute'] = 0
CONFIG.defaults['audibleRegion'] = '.com'
CONFIG.defaults['audiobook_status_texts_started'] = 'Started'
CONFIG.defaults['audiobook_status_texts_finished'] = 'Finished'
# Set defaults for all custom columns
for config_name in CUSTOM_COLUMN_DEFAULTS:
    CONFIG.defaults[config_name] = ''
# Set defaults for checkboxes
for config_name in CHECKBOXES:
    CONFIG.defaults[config_name] = CHECKBOXES[config_name].get('default', False)

def create_separator():
    separator = QFrame()
    separator.setFrameShape(QFrame.HLine)
    separator.setFrameShadow(QFrame.Sunken)
    return separator

if numeric_version >= (5, 5, 0):
    module_debug_print = partial(root_debug_print, ' audiobookshelf:config:', sep='')
else:
    module_debug_print = partial(root_debug_print, ' audiobookshelf:config:')

class ConfigWidget(QWidget):
    def __init__(self, plugin_action):
        QWidget.__init__(self)
        debug_print = partial(module_debug_print, 'ConfigWidget:__init__:')
        debug_print('start')
        self.action = plugin_action
        self.must_restart = False

        # Set up main layout
        layout = QVBoxLayout()
        self.setLayout(layout)

        # Add icon and title
        title_layout = TitleLayout(
            self,
            'images/abs_icon.png',
            f'Configure {self.action.version}',
        )
        layout.addLayout(title_layout)

        # Sync Section
        layout.addWidget(create_separator())
        ps_header_label = QLabel(
            "This plugin allows calibre to pull metadata from the built-in Audiobookshelf API.\n"
            "You must link the audiobook using either Quick Link (intelligently by Audiobookshelf "
            "ASIN and calibre title/author) or by selecting the correct book using the link feature.\n"
            "This functionality can optionally be scheduled as a daily sync from within calibre. "
            "Enter scheduled time in military time (default is 4 AM local time).\n"
            "This plugin can also maintain bidirectional sync."
        )
        ps_header_label.setWordWrap(True)
        layout.addWidget(ps_header_label)

        # ABS Account
        audiobookshelf_account_button = QPushButton('Add Audiobookshelf Account', self)
        audiobookshelf_account_button.clicked.connect(self.show_abs_account_popup)
        layout.addWidget(audiobookshelf_account_button)

        # Scheduled Sync
        scheduled_sync_layout = QHBoxLayout()
        scheduled_sync_layout.setAlignment(Qt.AlignLeft)
        scheduled_sync_layout.addLayout(self.add_checkbox('checkbox_enable_scheduled_sync'))
        scheduled_sync_layout.addLayout(self.add_checkbox('checkbox_scheduled_sync_show_log'))
        scheduled_sync_layout.addWidget(QLabel('Scheduled Time:'))
        self.schedule_hour_input = QSpinBox()
        self.schedule_hour_input.setRange(0, 23)
        self.schedule_hour_input.setValue(CONFIG['scheduleSyncHour'])
        self.schedule_hour_input.setSuffix('h')
        self.schedule_hour_input.wheelEvent = lambda event: event.ignore()
        scheduled_sync_layout.addWidget(self.schedule_hour_input)
        scheduled_sync_layout.addWidget(QLabel(':'))
        self.schedule_minute_input = QSpinBox()
        self.schedule_minute_input.setRange(0, 59)
        self.schedule_minute_input.setValue(CONFIG['scheduleSyncMinute'])
        self.schedule_minute_input.setSuffix('m')
        self.schedule_minute_input.wheelEvent = lambda event: event.ignore()
        scheduled_sync_layout.addWidget(self.schedule_minute_input)
        layout.addLayout(scheduled_sync_layout)

        # Add custom column dropdowns
        layout.addWidget(create_separator())
        self._get_create_new_custom_column_instance = None
        self.sync_custom_columns = {}
        bottom_options_layout = QHBoxLayout()
        layout.addLayout(bottom_options_layout)
        columns_group_box = QGroupBox(_('Synchronisable Custom Columns:'), self)
        bottom_options_layout.addWidget(columns_group_box)
        columns_group_box_layout = QHBoxLayout()
        columns_group_box.setLayout(columns_group_box_layout)
        columns_group_box_layout2 = QFormLayout()
        columns_group_box_layout2.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        columns_group_box_layout.addLayout(columns_group_box_layout2, 1)
        columns_group_box_layout.addStretch()
        # Populate custom column dropdowns
        for config_name, metadata in CUSTOM_COLUMN_DEFAULTS.items():
            self.sync_custom_columns[config_name] = {
                'current_columns': self.get_custom_columns(metadata['datatype'], metadata.get('is_multiple', (False, False))[1])
            }
            self._column_combo = self.create_custom_column_controls(
                columns_group_box_layout2, 
                config_name
            )
            metadata['comboBox'] = self._column_combo
            self._column_combo.populate_combo(
                self.sync_custom_columns[config_name]['current_columns'],
                CONFIG[config_name]
            )

        # Additional Sync Options
        layout.addWidget(create_separator())
        additional_options_label = QLabel('Additional Sync Behavior Settings. Hover for more information.')
        layout.addWidget(additional_options_label)
        additional_options_r1 = QHBoxLayout()
        additional_options_r1.addLayout(self.add_checkbox('checkbox_no_sync_if_finished'))
        additional_options_r1.addLayout(self.add_checkbox('checkbox_sync_only_if_more_recent'))
        layout.addLayout(additional_options_r1)
        additional_options_r2 = QHBoxLayout()
        additional_options_r2.addLayout(self.add_checkbox('checkbox_unlink_button'))
        layout.addLayout(additional_options_r2)

        # Add option to change status texts
        layout.addWidget(create_separator())
        layout.addWidget(QLabel('Audiobook Status: Set the status names for "Started" & "Finished" (Case sensitive)'))
        status_texts_layout = QHBoxLayout()
        status_texts_layout.setAlignment(Qt.AlignLeft)
        self.status_texts_started = QLineEdit(self)
        self.status_texts_started.setText(CONFIG['audiobook_status_texts_started'])
        self.status_texts_started.setToolTip('Text to set to when audiobook is started')
        status_texts_layout.addWidget(self.status_texts_started)
        self.status_texts_finished = QLineEdit(self)
        self.status_texts_finished.setText(CONFIG['audiobook_status_texts_finished'])
        self.status_texts_finished.setToolTip('Text to set to when audiobook is finished')
        status_texts_layout.addWidget(self.status_texts_finished)
        layout.addLayout(status_texts_layout)

        # Audible ASIN Identifier
        layout.addWidget(create_separator())
        identifer_label = QLabel('Audible & QuickLink Settings. Optionally add composite columns to internal Identifiers.')
        layout.addWidget(identifer_label)
        audible_config_layout_r1 = QHBoxLayout()
        audible_config_layout_r1.addLayout(self.add_checkbox('checkbox_enable_Audible_ASIN_sync'))
        audible_config_layout_r1.addStretch()
        audible_config_layout_r1.addWidget(QLabel('Audible Region: '))
        self.audible_region_comboBox = QComboBox()
        self.audible_region_comboBox.addItems([".com", ".ca", ".co.uk", ".com.au", ".fr", ".de", ".co.jp", ".it", ".in", ".es", ".com.br"])
        self.audible_region_comboBox.setCurrentText(CONFIG['audibleRegion'])
        self.audible_region_comboBox.setMinimumWidth(75)
        self.audible_region_comboBox.wheelEvent = lambda event: event.ignore()
        audible_config_layout_r1.addWidget(self.audible_region_comboBox)
        audible_config_layout_r1.addStretch()
        abs_id_button = QPushButton('Audiobookshelf ID', self)
        abs_id_button.setMinimumWidth(150)
        abs_id_button.clicked.connect(lambda: self.add_composite_column('#abs_id', 'Audiobookshelf ID', 'audiobookshelf_id'))
        audible_config_layout_r1.addWidget(abs_id_button)
        layout.addLayout(audible_config_layout_r1)
        audible_config_layout_r2 = QHBoxLayout()
        audible_config_layout_r2.addLayout(self.add_checkbox('checkbox_cache_QuickLink_history'))
        audible_config_layout_r2.addStretch()
        clear_QLcache_button = QPushButton('Clear QuickLink Cache', self)
        clear_QLcache_button.setMinimumWidth(150)
        clear_QLcache_button.clicked.connect(
            lambda: (JSONConfig('plugins/Audiobookshelf QL Cache.json').__setitem__('cache', []),
                        info_dialog(self.action.gui, 'Cache Successfully Cleared', 'Cache Successfully Cleared', show=True, show_copy_button=False))
            )
        audible_config_layout_r2.addWidget(clear_QLcache_button)
        audible_config_layout_r2.addStretch()
        asin_button = QPushButton('Audible ASIN', self)
        asin_button.setMinimumWidth(150)
        asin_button.clicked.connect(lambda: self.add_composite_column('#abs_asin', 'Audible ASIN', 'audible'))
        audible_config_layout_r2.addWidget(asin_button)
        layout.addLayout(audible_config_layout_r2)

        # Writeback
        layout.addWidget(create_separator())
        writeback_header_label = QLabel(
            "This plugin allows calibre to push metadata back to Audiobookshelf when changed inside of calibre.\n"
            "Any of the columns above with a * are able to be easily sync'd back to Audiobookshelf.\n"
            "This feature is offered with the disclaimer that this will edit your Audiobooshelf database. "
            "Make sure you have backups enabled in case this borks anything up, which it shouldn't but you never know.\n"
            "For Collections/Playlists this plugin will not create new ones, only update existing."
        )
        writeback_header_label.setWordWrap(True)
        layout.addWidget(writeback_header_label)
        layout.addLayout(self.add_checkbox('checkbox_enable_writeback'))

    def show_abs_account_popup(self):
        self.abs_account_popup = ABSAccountPopup(self)
        self.abs_account_popup.show()

    def add_composite_column(self, lookup_name, column_heading, identifier):
        # Get the create column instance
        create_new_custom_column_instance = self.get_create_new_custom_column_instance
        if not create_new_custom_column_instance:
            return False
        
        result = create_new_custom_column_instance.create_column(
                lookup_name, 
                column_heading, 
                'composite', 
                False, 
                display={'composite_template': f'{{identifiers:select({identifier})}}'},
                generate_unused_lookup_name=True,
                freeze_lookup_name=False
            )
            
        if result and result[0] == CreateNewCustomColumn.Result.COLUMN_ADDED:
            self.must_restart = True

    def save_settings(self):
        debug_print = partial(module_debug_print, ' ConfigWidget:save_settings:')
        debug_print('old CONFIG = ', CONFIG)

        needRestart = (self.must_restart or
            CONFIG['checkbox_enable_scheduled_sync'] != (CHECKBOXES['checkbox_enable_scheduled_sync']['checkbox'].checkState() == Qt.Checked) or
            CONFIG['checkbox_enable_writeback'] != (CHECKBOXES['checkbox_enable_writeback']['checkbox'].checkState() == Qt.Checked) or
            CONFIG['checkbox_unlink_button'] != (CHECKBOXES['checkbox_unlink_button']['checkbox'].checkState() == Qt.Checked) or
            CONFIG['scheduleSyncHour'] != self.schedule_hour_input.value() or
            CONFIG['scheduleSyncMinute'] != self.schedule_minute_input.value()
        )

        CONFIG['scheduleSyncHour'] = self.schedule_hour_input.value()
        CONFIG['scheduleSyncMinute'] = self.schedule_minute_input.value()
        CONFIG['audibleRegion'] = self.audible_region_comboBox.currentText()

        CONFIG['audiobook_status_texts_started'] = self.status_texts_started.text()
        CONFIG['audiobook_status_texts_finished'] = self.status_texts_finished.text()

        for config_name, metadata in CUSTOM_COLUMN_DEFAULTS.items():
            CONFIG[config_name] = metadata['comboBox'].get_selected_column()

        for config_name in CHECKBOXES:
            CONFIG[config_name] = CHECKBOXES[config_name]['checkbox'].checkState() == Qt.Checked

        try:
            from calibre.ebooks.metadata.sources.prefs import msprefs
            id_link_rules = msprefs['id_link_rules']
            id_link_rules['audible'] = [['Audible', f"https://www.audible{CONFIG['audibleRegion']}/pd/{{id}}"]]
            msprefs['id_link_rules'] = id_link_rules
        except ImportError:
            print('Could not add identifer link rule for Audible')  

        debug_print('new CONFIG = ', CONFIG)
        if needRestart and show_restart_warning('Changes have been made that require a restart to take effect.\nRestart now?'):
            self.action.gui.quit(restart=True)

    def add_checkbox(self, checkboxKey):
        layout = QHBoxLayout()
        checkboxMeta = CHECKBOXES[checkboxKey]
        checkbox = QCheckBox()
        checkbox.setCheckState(Qt.Checked if CONFIG[checkboxKey] else Qt.Unchecked)
        label = QLabel(checkboxMeta['config_label'])
        label.setToolTip(checkboxMeta['config_tool_tip'])
        label.setBuddy(checkbox)
        label.mousePressEvent = lambda event, checkbox=checkbox: checkbox.toggle()
        layout.addWidget(checkbox)
        layout.addWidget(label)
        layout.addStretch()
        CHECKBOXES[checkboxKey]['checkbox'] = checkbox
        return layout

    def create_custom_column_controls(self, columns_group_box_layout, custom_col_name, min_width=300):
        form_layout = columns_group_box_layout
        if fig := CUSTOM_COLUMN_DEFAULTS[custom_col_name].get('first_in_group', False):
            form_layout.addRow(create_separator())
            if isinstance(fig, str):
                form_layout.addRow(QLabel(f'<b>{fig}</b>', self))
        current_Location_label = QLabel(CUSTOM_COLUMN_DEFAULTS[custom_col_name]['config_label'], self)
        current_Location_label.setToolTip(CUSTOM_COLUMN_DEFAULTS[custom_col_name]['config_tool_tip'])
        create_column_callback = partial(self.create_custom_column, custom_col_name) if SUPPORTS_CREATE_CUSTOM_COLUMN else None
        avail_columns = self.sync_custom_columns[custom_col_name]['current_columns']
        custom_column_combo = CustomColumnComboBox(self, avail_columns, create_column_callback=create_column_callback)
        custom_column_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        custom_column_combo.setMinimumWidth(min_width)
        current_Location_label.setBuddy(custom_column_combo)
        form_layout.addRow(current_Location_label, custom_column_combo)

        self.sync_custom_columns[custom_col_name]['combo_box'] = custom_column_combo
        return custom_column_combo

    def create_custom_column(self, lookup_name=None):
        if not lookup_name or lookup_name not in CUSTOM_COLUMN_DEFAULTS:
            return False
            
        column_meta = CUSTOM_COLUMN_DEFAULTS[lookup_name]
        display_params = {
            'description': column_meta['description'],
            **column_meta.get('additional_params', {})
        }
        datatype = column_meta['datatype']
        column_heading = column_meta['column_heading']
        is_multiple = column_meta.get('is_multiple', (False, False))
        
        # Get the create column instance
        create_new_custom_column_instance = self.get_create_new_custom_column_instance
        if not create_new_custom_column_instance:
            return False

        # Use default_lookup_name as base for new column
        new_lookup_name = column_meta['default_lookup_name']
        
        try:
            result = create_new_custom_column_instance.create_column(
                new_lookup_name, 
                column_heading, 
                datatype, 
                is_multiple[0], 
                display=display_params,
                generate_unused_lookup_name=True,
                freeze_lookup_name=False
            )
            
            if result and result[0] == CreateNewCustomColumn.Result.COLUMN_ADDED:
                self.sync_custom_columns[lookup_name]['current_columns'][result[1]] = {
                    'name': column_heading
                }
                self.sync_custom_columns[lookup_name]['combo_box'].populate_combo(
                    self.sync_custom_columns[lookup_name]['current_columns'],
                    result[1]
                )
                self.must_restart = True
                return True
        except Exception:
            pass
            
        return False

    @property
    def get_create_new_custom_column_instance(self):
        if self._get_create_new_custom_column_instance is None and SUPPORTS_CREATE_CUSTOM_COLUMN:
            self._get_create_new_custom_column_instance = CreateNewCustomColumn(self.action.gui)
        return self._get_create_new_custom_column_instance

    def get_custom_columns(self, datatype, only_is_multiple=False):
        if SUPPORTS_CREATE_CUSTOM_COLUMN:
            custom_columns = self.get_create_new_custom_column_instance.current_columns()
        else:
            custom_columns = self.action.gui.library_view.model().custom_columns
        available_columns = {}
        for key, column in custom_columns.items():
            typ = column['datatype']
            if typ == datatype:
                available_columns[key] = column
        if datatype == 'rating':  # Add rating column if requested
            ratings_column_name = self.action.gui.library_view.model().orig_headers['rating']
            available_columns['rating'] = {'name': ratings_column_name}
        if only_is_multiple: # If user requests only is_multiple columns check and filter
            available_columns = {
                key: column for key, column in available_columns.items()
                if column.get('is_multiple', False) != {}
            }
        return available_columns

try:
    from calibre.gui2.preferences.create_custom_column import CreateNewCustomColumn
    SUPPORTS_CREATE_CUSTOM_COLUMN = True
except ImportError:
    SUPPORTS_CREATE_CUSTOM_COLUMN = False

class ABSAccountPopup(QDialog):
    def __init__(self, parent):
        QDialog.__init__(self, parent)
        self.setWindowTitle('Add Audiobookshelf Account')
        self.resize(400, 100) # 400 width, small height to constrain

        layout = QVBoxLayout()
        self.setLayout(layout)

        self.note_label = QLabel(
            "Enter your Audiobookshelf server URL, if it's the same device as calibre you can leave the default filled in.<br>"
            'Enter your <a href="https://www.audiobookshelf.org/guides/api-keys/">Audiobookshelf API Key</a> and click Save Account.',
            self
        )
        self.note_label.setWordWrap(True)
        self.note_label.setOpenExternalLinks(True)
        layout.addWidget(self.note_label)
        layout.addWidget(create_separator())

        self.url_label = QLabel('Audiobookshelf Server URL:', self)
        self.url_label.setBuddy(self.url_label)
        self.url_input = QLineEdit(self)
        self.url_input.setText(CONFIG['abs_url'])
        layout.addWidget(self.url_label)
        layout.addWidget(self.url_input)
        layout.addWidget(create_separator())

        self.key_label = QLabel('API Key:', self)
        self.url_label.setBuddy(self.key_label)
        self.key_input = QPlainTextEdit(self)
        self.key_input.setFixedHeight(100)
        self.key_input.setPlainText(CONFIG['abs_key'])
        layout.addWidget(self.key_label)
        layout.addWidget(self.key_input)

        self.validate_credentials_button = QPushButton('Validate Account', self)
        self.validate_credentials_button.clicked.connect(self.validate_audiobookshelf_credentials)
        layout.addWidget(self.validate_credentials_button)
        self.isValidated = False

        self.login_button = QPushButton('Validate + Save Account', self)
        self.login_button.clicked.connect(self.save_audiobookshelf_account_settings)
        layout.addWidget(self.login_button)

    def validate_audiobookshelf_credentials(self):
        from urllib.request import Request, urlopen
        from urllib.error import URLError, HTTPError

        self.currURL = self.url_input.text()
        self.currKey = self.key_input.toPlainText()

        def api_request(url, api_key, post=False):
            req = Request(url, headers={
                'Authorization': f'Bearer {api_key}',
                'Accept': 'application/json',
                'Content-Type': 'application/json',
                'User-Agent': f'CalibreAudiobookshelfSync/',
            })
            if post:
                req.method = 'POST'
            try:
                with urlopen(req, timeout=4) as response:
                    code = response.getcode()
                    resp_data = response.read()
                    json_data = json.loads(resp_data.decode('utf-8'))
                    return code, json_data
            except HTTPError as e:
                code = e.getcode()
                try:
                    error_resp = e.read()
                    error_json = json.loads(error_resp.decode('utf-8'))
                except Exception:
                    error_json = None
                return (code, error_json)
            except URLError as e:
                return None, None

        resp_code, res= api_request(f'{self.currURL}/ping', self.currKey)
        if resp_code != 200 or res['success'] != True:
            error_dialog(
                self.parent().action.gui,
                'Server Not Accessible',
                'Server URL not accessible, please check that the URL includes http(s):// and port and is reachable in your browser.',
                show=True,
                show_copy_button=False
            )
            return False

        resp_code, res= api_request(f'{self.currURL}/api/authorize', self.currKey, True)
        if resp_code != 200:
            error_dialog(
                self.parent().action.gui,
                'API Key Not Valid',
                'Server is Reachable, but the provided API Key was rejected. Check again and ensure there are no spaces and the word "Bearer" is not included.',
                show=True,
                show_copy_button=False
            )
            return False
        else:
            info_dialog(
                self.parent().action.gui,
                'API Key Valid',
                'URL and API Key are valid!\nSee below for details.',
                det_msg=json.dumps({
                    'username': res['user']['username'],
                    'isActive': res['user']['isActive'],
                    'type': res['user']['type'],
                    'canWriteback': res['user']['permissions'].get('update', False),
                    'permissions': res['user']['permissions'],
                    'libraries (if accessAllLibraries is not True)': res['user']['librariesAccessible'],
                }, indent=4),
                show=True,
                show_copy_button=True
            )
            self.isValidated = True
            return True

    def save_audiobookshelf_account_settings(self):
        if not (self.isValidated and self.currURL == self.url_input.text() and self.currKey == self.key_input.toPlainText()):
            if not self.validate_audiobookshelf_credentials():
                return

        CONFIG['abs_url'] = self.currURL
        CONFIG['abs_key'] = self.currKey

        try:
            from calibre.ebooks.metadata.sources.prefs import msprefs
            id_link_rules = msprefs['id_link_rules']
            id_link_rules['audiobookshelf_id'] = [['Audiobookshelf', f'{self.currURL}/audiobookshelf/item/{{id}}']]
            msprefs['id_link_rules'] = id_link_rules
        except ImportError:
            print('Could not add identifer link rule for Audiobookshelf')        

        self.accept()

class TitleLayout(QHBoxLayout):
    def __init__(self, parent, icon, title):
        QHBoxLayout.__init__(self)
        icon_label = QLabel(parent)
        pixmap = QPixmap()
        pixmap.loadFromData(get_resources(icon))
        icon_label.setPixmap(pixmap)
        icon_label.setMaximumSize(64, 64)
        icon_label.setScaledContents(True)
        self.addWidget(icon_label)
        title_label = QLabel(f'<h2>{title}</h2>', parent)
        title_label.setContentsMargins(10, 0, 10, 0)
        self.addWidget(title_label)
        self.addStretch()
        readme_label = QLabel('<a href="#">Readme</a>', parent)
        readme_label.setTextInteractionFlags(Qt.LinksAccessibleByMouse | Qt.LinksAccessibleByKeyboard)
        readme_label.linkActivated.connect(parent.action.show_readme)
        self.addWidget(readme_label)
        about_label = QLabel('<a href="#">About</a>', parent)
        about_label.setTextInteractionFlags(Qt.LinksAccessibleByMouse | Qt.LinksAccessibleByKeyboard)
        about_label.linkActivated.connect(parent.action.show_about)
        self.addWidget(about_label)

class CustomColumnComboBox(QComboBox):
    def __init__(self, parent, custom_columns={}, selected_column='', create_column_callback=None):
        super(CustomColumnComboBox, self).__init__(parent)
        self.create_column_callback = create_column_callback
        if create_column_callback is not None:
            self.currentTextChanged.connect(self.current_text_changed)
        self.populate_combo(custom_columns, selected_column)

    def populate_combo(self, custom_columns, selected_column, show_lookup_name=True):
        self.blockSignals(True)
        self.clear()
        self.column_names = []

        if self.create_column_callback is not None:
            self.column_names.append('Create new column')
            self.addItem('Create new column')

        self.column_names.append('do not sync')
        self.addItem('do not sync')
        selected_idx = 1

        for key in sorted(custom_columns.keys()):
            self.column_names.append(key)
            display_name = '%s (%s)'%(key, custom_columns[key]['name']) if show_lookup_name else custom_columns[key]['name']
            self.addItem(display_name)
            if key == selected_column:
                selected_idx = len(self.column_names) - 1

        self.setCurrentIndex(selected_idx)
        self.current_index = selected_idx
        self.blockSignals(False)

    def get_selected_column(self):
        selected_column = self.column_names[self.currentIndex()]
        if selected_column == 'Create new column' or selected_column == 'do not sync':
            selected_column = ''
        return selected_column

    def current_text_changed(self, new_text):
        if new_text == 'Create new column':
            result = self.create_column_callback()
            if not result:
                self.setCurrentIndex(self.current_index)
        else:
            self.current_index = self.currentIndex()
    
    def wheelEvent(self, event): # Prevents the mouse wheel from changing the selected item
        event.ignore()
