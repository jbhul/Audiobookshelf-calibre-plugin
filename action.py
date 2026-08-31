#!/usr/bin/env python3
"""Audiobookshelf Sync plugin for calibre"""

import json
import time
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
import urllib.parse

from PyQt5.Qt import (
    QDialog,
    QProgressBar,
    QIcon,
    QPushButton,
    QLabel,
    QHBoxLayout,
    QVBoxLayout,
    QTableWidget,
    QTableWidgetItem,
    QScrollArea,
    QTimer,
    QTime,
    QColor,
    QApplication,
    QThread,
    pyqtSignal,
    Qt,
)
from PyQt5.QtGui import QPixmap

from calibre.gui2.actions import InterfaceAction
from calibre.gui2.dialogs.message_box import MessageBox
from calibre.db.listeners import EventType
from calibre.ebooks.metadata.book.base import Metadata
from calibre.utils.config import JSONConfig
from calibre.gui2 import (
    error_dialog,
    warning_dialog,
    info_dialog,
    open_url,
)

from calibre_plugins.audiobookshelf.config import CONFIG, CUSTOM_COLUMN_DEFAULTS as COLUMNS
from calibre_plugins.audiobookshelf import DEBUG

__license__ = 'GNU GPLv3'
__copyright__ = '2025, jbhul'

# Helper functions to show error and info messages using MessageBox
def show_error(gui, title, message):
    MessageBox(MessageBox.ERROR, title, message, parent=gui).exec_()

def show_info(gui, title, message):
    MessageBox(MessageBox.INFO, title, message, parent=gui).exec_()

class AudiobookshelfAction(InterfaceAction):
    name = "Audiobookshelf"
    action_spec = (name, 'diff.png', 'Get metadata from Audiobookshelf', None)
    action_add_menu = True
    action_menu_clone_qaction = 'Sync from Audiobookshelf'
    dont_add_to = frozenset([
        'context-menu', 'context-menu-device', 'toolbar-child',
        'menubar', 'menubar-device', 'context-menu-cover-browser', 
        'context-menu-split'
    ])
    dont_remove_from = InterfaceAction.all_locations - dont_add_to
    action_type = 'current'
    Syncing = False

    def genesis(self):
        base = self.interface_action_base_plugin
        self.version = f'{base.name} (v{".".join(map(str, base.version))})'
        # Set up toolbar button icon and left-click action
        self.qaction.setIcon(get_icons('images/abs_icon.png'))
        self.qaction.triggered.connect(self.sync_from_audiobookshelf)
        # Right-click menu (already includes left-click action)
        menu = self.qaction.menu()
        self.create_menu_action(
            menu,
            'Sync Audible Ratings',
            'Sync Audible Ratings',
            icon='rating.png',
            triggered=self.sync_audible_rating,
            description='Update Audible Ratings Data from Audible API'
        )
        self.create_menu_action(
            menu,
            'Get Audiobookshelf Covers',
            'Get Audiobookshelf Covers',
            icon='beautify.png',
            triggered=self.get_abs_covers,
            description='Compare and update covers from Audiobookshelf for selected books'
        )
        menu.addSeparator()
        self.create_menu_action(
            menu,
            'Link Audiobookshelf Book',
            'Link Audiobookshelf Book',
            icon='insert-link.png',
            triggered=self.link_audiobookshelf_book,
            description='Match calibre Book to Audiobookshelf Book'
        )
        self.create_menu_action(
            menu,
            'Quick Link Books',
            'Quick Link Books',
            icon='wizard.png',
            triggered=self.quick_link_books,
            description='Search Audible for Book and check for matches in Audiobookshelf by ASIN'
        )
        if DEBUG or CONFIG.get('checkbox_unlink_button', False):
            self.create_menu_action(
                menu,
                'Remove ABS Link',
                'Remove ABS Link',
                icon='list_remove.png',
                triggered=self.unlink_audiobookshelf_book,
                description='Removes ABS ID and all ABS synced metadata from selected calibre book(s)'
            )
        menu.addSeparator()
        self.create_menu_action(
            menu,
            'Audiobooks Not In Calibre',
            'Audiobooks Not In Calibre',
            icon='format-list-ordered.png',
            triggered=self.show_not_in_calibre,
            description='List of Audiobooks Not In Calibre'
        )
        menu.addSeparator()
        self.create_menu_action(
            menu,
            'Configure',
            'Configure',
            icon='config.png',
            triggered=self.show_config,
            description='Add Columns, User Credentials, and Configure The Plugin'
        )
        menu.addSeparator()
        self.create_menu_action(
            menu,
            'Readme',
            'Readme',
            icon='dialog_question.png',
            triggered=self.show_readme,
            description='Open Github Readme in Browser'
        )
        self.create_menu_action(
            menu,
            'About',
            'About',
            icon='dialog_information.png',
            triggered=self.show_about,
            description='Get General Information About The Plugin'
        )
        
        # Start scheduled sync if enabled
        if CONFIG.get('checkbox_enable_scheduled_sync', False):
            self.scheduled_sync()
        
        # Start writeback watcher if enabled
        if CONFIG.get('checkbox_enable_writeback', False):
            watched_columns = {}
            for config_name, col_meta in COLUMNS.items():
                if '*' in col_meta['config_label'] and CONFIG.get(config_name):
                    watched_columns[CONFIG.get(config_name)] = col_meta['data_location'][-1]
            self.watcher(watched_columns)

    def show_config(self):
        self.interface_action_base_plugin.do_user_config(self.gui)

    def show_readme(self):
        open_url('https://github.com/jbhul/Audiobookshelf-calibre-plugin#readme')

    def show_about(self):
        text = get_resources('about.txt').decode('utf-8')
        if DEBUG:
            text += '\n\nRunning in debug mode'
        about_dialog = MessageBox(
            MessageBox.INFO,
            f'About {self.version}',
            text,
            det_msg='',
            q_icon=get_icons('images/abs_icon.png'),
            show_copy_button=False,
            parent=None,
        )
        return about_dialog.exec_()

    def show_not_in_calibre(self):
        abs_items = self.get_abs_library_items(apply_library_filter=True)
        if abs_items is None:
            show_error(self.gui, "API Error", "Failed to retrieve Audiobookshelf library data, "
            "does user have library permissions or is Audiobookshelf empty?")
            return
        if not abs_items:
            show_info(
                self.gui,
                "No Libraries Available",
                "The selected Audiobookshelf library filters exclude all available audiobook libraries. "
                "Clear or adjust the filters in Audiobookshelf Account Settings."
            )
            return

        # Get all linked ABS IDs from Calibre
        db = self.gui.current_db.new_api
        all_book_ids = db.search('identifiers:"=audiobookshelf_id:"')
        linked_abs_ids = {db.get_metadata(book_id).get('identifiers', {}).get('audiobookshelf_id') for book_id in all_book_ids}

        # Filter and sort unlinked items
        unlinked_items = []
        for item in abs_items:
            if item.get('id') not in linked_abs_ids:
                metadata = item.get('media', {}).get('metadata', {})
                unlinked_items.append({
                        'Add?': True,
                        'hidden_id': item.get('id'),
                        'title': metadata.get('title', ''),
                        'author': metadata.get('authorName', ''),
                        'library': item.get('libraryName', ''),
                        'hidden_isbn': (metadata.get('isbn') or ''),
                    })
        # Check if there are unlinked items   
        if not unlinked_items:
            # Show a dialog indicating there are no unlinked audiobooks
            message = "There are no Unlinked Audiobooks in your Library."
            dialog = SyncCompletionDialog(self.gui, "Unlinked Audiobookshelf Books", message, [], resultsColWidth=0, type="info")
            dialog.show()
        else:
            # Sort by title
            unlinked_items.sort(key=lambda x: x['title'].lower())

            # Show results
            message = (f"Found {len(unlinked_items)} unlinked books in Audiobookshelf library.\n\n"
                       "Check the box(es) to add minimal records to calibre (title, authors, ABS ID, and ISBN if available). "
                       "Double Click the title to open book in Audiobookshelf.")
            dialog = SyncCompletionDialog(self.gui, "Unlinked Audiobookshelf Books", message, unlinked_items, resultsColWidth=0, type="info")
            table = dialog.table_area.findChild(QTableWidget)
            def on_cell_double_clicked(row, col):
                if col == 2:
                    open_url(f"{CONFIG['abs_url']}/audiobookshelf/item/{unlinked_items[int(table.item(row, 0).text())].get('hidden_id')}")
            table.cellDoubleClicked.connect(on_cell_double_clicked)

            if dialog.exec_() and hasattr(dialog, 'checked_rows') and dialog.checked_rows:
                # Build payload for calibre: list of (Metadata, format_map)
                payload = []
                for row_idx in dialog.checked_rows:
                    rec = unlinked_items[row_idx]
                    title = rec.get('title') or 'Unknown Title'
                    authors = rec.get('author')
                    authors_list = [a.strip() for a in authors.split(',') if a.strip()] if isinstance(authors, str) else ['Unknown']

                    mi = Metadata(title, authors_list)
                    ids = {'audiobookshelf_id': rec.get('hidden_id')}
                    if rec.get('hidden_isbn'):
                        ids['isbn'] = rec['hidden_isbn']
                    mi.set_identifiers(ids)

                    # empty book record; actual formats/other fields sync later
                    payload.append((mi, {}))

                added_ids, _skipped = db.add_books(payload)
                # Refresh the GUI so the new books appear immediately
                model = self.gui.library_view.model()
                model.refresh()
                if added_ids:
                    self.gui.library_view.select_rows(added_ids) # Select newly added books
                results = []
                for i, row_idx in enumerate(dialog.checked_rows):
                    rec = unlinked_items[row_idx]
                    results.append({
                        'title': rec.get('title', ''),
                        'author': rec.get('author', ''),
                        'audiobookshelf_id': rec.get('hidden_id', ''),
                        'isbn': rec.get('hidden_isbn', '') or '-',
                        'added book id': added_ids[i] if i < len(added_ids) else '-'
                    })
                msg = (f"Added {len(added_ids)} book{'s' if len(added_ids)!=1 else ''} to calibre.\n"
                    "Only title, authors, Audiobookshelf ID, and ISBN (when available) were stored; "
                    "run your normal Audiobookshelf sync to fetch the rest.")
                SyncCompletionDialog(self.gui, "Add Completed", msg, results, resultsColWidth=0, type="good").show()
            else: # Either no selection or dialog canceled; do nothing
                pass

    def scheduled_sync(self):
        def scheduledTask():
            QTimer.singleShot(24 * 3600 * 1000, scheduledTask)
            self.sync_from_audiobookshelf( silent = (not DEBUG) and (not CONFIG.get('checkbox_scheduled_sync_show_log', False)) )
        def main():
            currentTime = QTime.currentTime()
            targetTime = QTime(CONFIG.get('scheduleSyncHour', 4), CONFIG.get('scheduleSyncMinute', 0))
            timeDiff = currentTime.msecsTo(targetTime)
            if timeDiff < 0:
                timeDiff += 86400000 # add 24 hours in milliseconds = 24 * 3600 * 1000
            QTimer.singleShot(timeDiff, scheduledTask)
        main()

    def watcher(self, watched_columns):
        """Watch specified columns for changes and sync back to Audiobookshelf"""
        if not hasattr(self.gui, 'current_db'):
            print("Database not yet initialized, delaying watcher setup")
            QTimer.singleShot(1000, lambda: self.watcher(watched_columns))
            return

        def event_listener(db, event_type, event_data):
            if not self.Syncing and event_type == EventType.metadata_changed:
                print(event_data)
                field, book_ids = event_data
                if field.endswith('_index'):
                    field = field[:-6]
                # Only process if the changed field is one we're watching
                if field in watched_columns:
                    for book_id in book_ids:
                        metadata = db.get_metadata(book_id, index_is_id=True)
                        abs_id = metadata.get('identifiers', '').get('audiobookshelf_id', '')
                        if not abs_id:
                            continue
                        new_value = metadata.get(field)
                        if watched_columns[field] == 'collections':
                            collections_dict, collections_map = self.get_abs_collections(server_url, api_key)
                            server_collections = collections_dict.get(abs_id, [])
                            for collection in server_collections:
                                if collection not in new_value: # Item in Server but not local, therefore remove from server
                                    collection_id = collections_map.get(collection, None)
                                    if collection_id:
                                        if collection[0:3] == "PL ": # Playlist
                                            self.api_request(f"{server_url}/api/playlists/{collection_id}/batch/remove", api_key, ('POST', {"items": [abs_id]}))
                                        else: # Collection
                                            self.api_request(f"{server_url}/api/collections/{collection_id}/batch/remove", api_key, ('POST', {"books": [abs_id]}))
                            for collection in new_value:
                                if collection not in server_collections: # Item not in server but in local, therefore add to server
                                    collection_id = collections_map.get(collection, None)
                                    if collection_id:
                                        if collection[0:3] == 'PL ': # Playlist
                                            self.api_request(f"{server_url}/api/playlists/{collection_id}/batch/add", api_key, ('POST', {"items": [{"libraryItemId": abs_id}]}))
                                        else: # Collection
                                            self.api_request(f"{server_url}/api/collections/{collection_id}/batch/add", api_key, ('POST', {"books": [abs_id]}))
                        else:
                            if watched_columns[field].startswith('series'):
                                body = {"metadata": {'series': [{
                                    "name": new_value,
                                    "sequence": str(int(metadata.get(f'{field}_index', 1)))
                                    }]
                                }}
                            elif watched_columns[field] == 'authorName':
                                body = {"metadata": {'authors': [{"name": author} for author in new_value]}}
                            elif watched_columns[field] == 'narratorName':
                                body = {"metadata": {'narrators': new_value}}
                            elif watched_columns[field] == 'tags':
                                body = {"tags": new_value}
                            else:
                                body = {"metadata": {watched_columns[field]: new_value}}
                            self.api_request(f"{server_url}/api/items/{abs_id}/media", api_key, ('PATCH', body))

        server_url = CONFIG.get('abs_url', 'http://localhost:13378')
        api_key = CONFIG.get('abs_key', '')
        self.gui.add_db_listener(event_listener)

    def update_metadata(self, book_uuid, keys_values_to_update):
        db = self.gui.current_db.new_api
        try:
            book_id = db.lookup_by_uuid(book_uuid)
        except Exception:
            return False, {'error': f"Book not found: {book_uuid}"}
        if not book_id:
            return False, {'error': f"Book not found: {book_uuid}"}
        metadata = db.get_metadata(book_id)
        updates = []
        for key, new_value in keys_values_to_update.items():
            if isinstance(new_value, tuple):
                metadata.set(key, new_value[0], extra=new_value[1])
            else:
                metadata.set(key, new_value)
            updates.append(key)
        if updates:
            db.set_metadata(book_id, metadata, set_title=False, set_authors=False)
        return True, {'updated': updates, 'book_id': book_id}

    def get_nested_value(self, data, path):
        for key in path:
            if data is None:
                return None
            if isinstance(data, dict):
                data = data.get(key)
            else:
                return None
        return data

    def api_request(self, url, api_key, body=None):
        headers = {
            'Authorization': f'Bearer {api_key}',
            'Accept': 'application/json',
            'Content-Type': 'application/json',
            'User-Agent': f'CalibreAudiobookshelfSync/{self.version}',
        }
        req = Request(url, headers=headers)
        if body is not None:
            req.method = body[0]
            req.data = json.dumps(body[1]).encode("utf-8")
        try:
            with urlopen(req, timeout=10) as response:
                resp_data = response.read()
                return json.loads(resp_data.decode('utf-8'))
        except (HTTPError, URLError):
            print("API request failed")
            return None

    def sync_from_audiobookshelf(self, silent=False):
        self.Syncing = True
        server_url = CONFIG.get('abs_url', 'http://localhost:13378')
        api_key = CONFIG.get('abs_key', '')
        columns_to_sync = {k: {**v, 'column_name': CONFIG.get(k)} for k, v in COLUMNS.items() if CONFIG.get(k)}
        api_sources = list({col_meta['api_source'] for col_meta in columns_to_sync.values()})

        db = self.gui.current_db.new_api
        all_book_ids = list(db.search('identifiers:"=audiobookshelf_id:"'))
        if not all_book_ids:
            show_info(self.gui, "No Linked Books", "Calibre library has no linked books, try using Quick Link or manually linking books.")
            return

        abs_items = self.get_abs_library_items()
        if abs_items is None:
            show_error(self.gui, "API Error", "Failed to retrieve Audiobookshelf library data, "
            "does user have library permissions or is Audiobookshelf empty?")
            return
        # Build dictionary mapping item id to item data (from lib_items)
        items_dict = {}
        for item in abs_items:
            item_id = item.get('id')
            if item_id:
                items_dict[item_id] = item

        if 'itemDetail' in api_sources:
            chapters_dict = {}
            supplementary_books_dict = {}
            linked_abs_ids = list({db.get_metadata(book_id).get('identifiers', {}).get('audiobookshelf_id') for book_id in all_book_ids})
            book_details = self.api_request(f"{server_url}/api/items/batch/get", api_key, ('POST', {"libraryItemIds": [linked_abs_ids]}))['libraryItems']
            for book in book_details:
                book_chapters = book['media']['chapters']
                book_chapters.sort(key=lambda item: item['id'])
                chapters_dict[book['id']] = '\n'.join([f"{item['id'] + 1}: {item['title']} ({int((item['end']-item['start'])/60)} mins)" for item in book_chapters])
                supp_files = [
                    (lf.get('metadata') or {}).get('filename')
                    for lf in book.get('libraryFiles', [])
                    if lf.get('isSupplementary') is True and (lf.get('metadata') or {}).get('filename')
                ]
                if supp_files:
                    supplementary_books_dict[book['id']] = f"{len(supp_files)}: {', '.join(supp_files)}"

        # Get me data
        if 'mediaProgress' in api_sources:
            me_url = f"{server_url}/api/me"
            me_data = self.api_request(me_url, api_key)
            if me_data is None:
                show_error(self.gui, "API Error", "Failed to retrieve Audiobookshelf user data.")
                return
            # Build dictionary mapping libraryItemId to media progress data (from mediaProgress)
            media_progress_dict = {}
            for prog in me_data.get('mediaProgress', []):
                media_progress_dict[prog.get('libraryItemId')] = {**prog, 'bookmarks': []}
            for bookmark in me_data.get('bookmarks'):
                media_progress_dict.setdefault(bookmark.get('libraryItemId'), {'bookmarks': []})['bookmarks'].append({
                    "title": bookmark["title"],
                    "time": bookmark["time"],
                })

        # Get collection/playlist data
        if 'collections' in api_sources:
            collections_dict = self.get_abs_collections(server_url, api_key)[0]

        # Get session data
        if 'sessions' in api_sources:
            sessions_response = self.api_request(f"{server_url}/api/me/listening-sessions?itemsPerPage=999999", api_key).get('sessions')
            if sessions_response is None:
                show_error(self.gui, "API Error", "Failed to retrieve Audiobookshelf sessions.")
                return
            else:
                sessions_dict = {}
                for session in sessions_response:
                    sessions_dict.setdefault(session["libraryItemId"], []).append({
                        "date": session["date"],
                        "timeListening": session["timeListening"],
                        'progression': (progression := session['currentTime'] - session['startTime']),
                        "sessionDuration": (sessionDuration := ((session["updatedAt"] - session["startedAt"]) / 1000)),
                        "cleanSession": 0.8 <= (sessionSpeed := progression / sessionDuration) <= 4,
                        "isComplete": (session["startTime"] == 0 and int(session['currentTime']) == int(session['duration'])),
                        "durationRemaining": durationRemaining if (durationRemaining := int(session['duration'] - session['currentTime'])) > 300 else 0,
                        "sessionSpeed": sessionSpeed,
                    })
                for item_id, sessions in sessions_dict.items():
                    if len(sessions) > 1 and any(s.get('isComplete') for s in sessions):
                        sessions = [s for s in sessions if not s.get("isComplete", False)]
                    sessions_dict[item_id] = {
                        'sessions': sessions,
                        'session_count': len(sessions),
                        'distinct_date_count': len({s["date"] for s in sessions}),
                        'total_time_listening': sum(s["timeListening"] for s in sessions),
                        'total_session_duration': sum(s["sessionDuration"] for s in sessions),
                        'total_progression': sum(s["progression"] for s in sessions),
                        'filtered_session_count': len(filtered_sessions := [s for s in sessions if s["cleanSession"]]),
                        'filtered_date_count': len({s["date"] for s in filtered_sessions}),
                        'filtered_time_listening': (filtered_time_listening := sum(s["timeListening"] for s in filtered_sessions)),
                        'filtered_session_duration': (filtered_session_duration := sum(s["sessionDuration"] for s in filtered_sessions)),
                        'filtered_progression': (filtered_progression := sum(s["progression"] for s in filtered_sessions)),
                        'filtered_avg_session_duration': filtered_session_duration/len(filtered_sessions) if filtered_sessions else None,
                        'filtered_avg_speed': filtered_progression / filtered_session_duration if filtered_session_duration else None,
                        'filtered_max_speed': max((s["sessionSpeed"] for s in filtered_sessions), default=None),
                    }

        class ABSSyncWorker(QThread):
            progress_update = pyqtSignal(int)
            finished_signal = pyqtSignal(dict)

            def __init__(self, action, db, book_ids):
                super().__init__()
                self.action = action
                self.db = db
                self.book_ids = book_ids

            def run(self):
                num_success = 0
                num_fail = 0
                num_skip = 0
                results = []
                for idx, book_id in enumerate(all_book_ids):
                    metadata = db.get_metadata(book_id)
                    book_uuid = metadata.get('uuid')
                    identifiers = metadata.get('identifiers', {})
                    abs_id = identifiers.get('audiobookshelf_id')
                    item_data = items_dict.get(abs_id)
                    if not item_data:
                        results.append({'title': metadata.get('title', f'Book {book_id}'), 'error': 'Audiobookshelf item not found'})
                        num_skip += 1
                        continue

                    result = {'title': metadata.get('title', f'Book {book_id}')}
                    keys_values_to_update = {}

                    # Check if book is finished and should not be synced again
                    if CONFIG.get('checkbox_no_sync_if_finished', False):
                        status_key = CONFIG['column_audiobook_status_text']
                        book_finished = metadata.get(CONFIG['column_audiobook_finished'], False) or metadata.get(status_key, "") == CONFIG['audiobook_status_texts_finished']
                        if book_finished:
                            num_skip += 1
                            continue

                    # Update identifiers if Audible ASIN sync is enabled
                    if CONFIG.get('checkbox_enable_Audible_ASIN_sync', False):
                        current_Audible_ASIN = identifiers.get('audible')
                        Audible_ASIN = item_data.get('media').get('metadata').get('asin')
                        if Audible_ASIN != current_Audible_ASIN:
                            identifiers['audible'] = Audible_ASIN
                            keys_values_to_update['identifiers'] = identifiers
                            result['Audible ASIN'] = f"{current_Audible_ASIN if current_Audible_ASIN is not None else '-'} >> {Audible_ASIN}"

                    # For each custom column, use api_source and data_location for lookup
                    for col_meta in columns_to_sync.values():
                        column_name = col_meta.get('column_name')
                        data_location = col_meta.get('data_location', [])
                        api_source = col_meta.get('api_source')
                        value = None

                        if api_source == "mediaProgress":
                            value = self.action.get_nested_value(media_progress_dict.get(abs_id), data_location)
                            if col_meta['column_heading'] == "Audiobook Started" and value is None:
                                if self.action.get_nested_value(media_progress_dict.get(abs_id), COLUMNS['column_audiobook_progress_float']['data_location']) > 0:
                                    value = True
                            if col_meta['column_heading'] == "Audiobook Status":
                                if self.action.get_nested_value(media_progress_dict.get(abs_id), COLUMNS['column_audiobook_finished']['data_location']):
                                    value = CONFIG.get('audiobook_status_texts_finished', 'Finished')
                                elif (percent := self.action.get_nested_value(media_progress_dict.get(abs_id), COLUMNS['column_audiobook_progress_float']['data_location'])) is not None and percent > 0:
                                    value = CONFIG.get('audiobook_status_texts_started', 'Started')
                        elif api_source == "lib_items":
                            value = self.action.get_nested_value(item_data, data_location)
                        elif api_source == "sessions":
                            value = self.action.get_nested_value(sessions_dict.get(abs_id, {}), data_location)
                        elif api_source == "collections":
                            value = collections_dict.get(abs_id, [])
                        elif api_source == "itemDetail":
                            if col_meta['column_heading'] == "Audiobook Chapters":
                                value = chapters_dict.get(abs_id, None)
                            elif col_meta['column_heading'] == "Audiobook Supplementary Files":
                                value = supplementary_books_dict.get(abs_id, None)
                        else:
                            continue

                        if value is not None:
                            if 'transform' in col_meta and callable(col_meta['transform']):
                                value = col_meta['transform'](value)
                            if value is not None:
                                old_value = metadata.get(column_name)
                                if type(old_value) != type(value):
                                    # Convert value to the same type as old_value
                                    if isinstance(old_value, str) and isinstance(value, list):
                                        value = ', '.join(value)
                                    elif col_meta['datatype'] == 'series':
                                        if old_value == value[0] and metadata.get(f'{column_name}_index') == value[1]:
                                            value = old_value
                                    elif isinstance(old_value, bool):
                                        value = bool(value)
                                    elif isinstance(old_value, int):
                                        value = int(value)
                                    elif isinstance(old_value, float):
                                        value = float(value)
                                    else: # Default to string
                                        value = str(value)
                                if isinstance(value, str):
                                    value = value.strip()
                                if old_value != value:
                                    keys_values_to_update[column_name] = value
                                    # Only add to result if there's an actual change
                                    result[col_meta['column_heading']] = f"{old_value if old_value is not None else '-'} >> {value}"

                    if keys_values_to_update:
                        # Check if changes are more recent before updating
                        if CONFIG.get('checkbox_sync_only_if_more_recent', False):
                            lastread = CONFIG['column_audiobook_lastread']
                            current_lastread = metadata.get(lastread)
                            new_lastread = keys_values_to_update.get(lastread)
                            if current_lastread is not None and new_lastread is not None:
                                if current_lastread.timestamp() >= new_lastread.timestamp():
                                    results.append({'title': metadata.get('title', f'Book {book_id}'), 'skipped': 'Data in calibre is more recent'})
                                    num_skip += 1
                                    continue
                            # Fallback if no 'column_audiobook_lastread' is set
                            elif new_lastread is None:
                                progress_key = CONFIG['column_audiobook_progress_float'] or CONFIG['column_audiobook_progress_int']
                                current_progress = metadata.get(progress_key)
                                new_progress = keys_values_to_update.get(progress_key)
                                if current_progress is not None and new_progress is not None:
                                    if current_progress > new_progress:
                                        results.append({'title': metadata.get('title', f'Book {book_id}'), 'skipped': 'Progress is lower than in calibre'})
                                        num_skip += 1
                                        continue
                                elif current_progress is not None and new_progress is None:
                                    results.append({'title': metadata.get('title', f'Book {book_id}'), 'skipped': 'No Progress found'})
                                    num_skip += 1
                                    continue

                        status, detail = self.action.update_metadata(book_uuid, keys_values_to_update)
                        if status:
                            num_success += 1
                        else:
                            num_fail += 1
                            result['error'] = detail.get('error', 'Unknown error')
                    else:
                        num_skip += 1
                    results.append(result)
                    self.progress_update.emit(idx + 1)
                self.finished_signal.emit({'results': results, 'num_success': num_success, 'num_fail': num_fail, 'num_skip': num_skip})

        startTime = time.perf_counter()
        self.absSyncWorker = ABSSyncWorker(self, db, all_book_ids)
        progress_dialog = None
        if not silent and len(all_book_ids)>25:
            progress_dialog = ProgressDialog(self.gui, "Updating Metadata...", len(all_book_ids))
            progress_dialog.show()
            self.absSyncWorker.progress_update.connect(progress_dialog.setValue)
        def on_finished(res):
            self.Syncing = False
            if not silent:
                if progress_dialog:
                    progress_dialog.close()
                message = (f"Total books processed: {len(res['results'])}\nUpdated: {res['num_success']}\nSkipped: {res['num_skip']}\nFailed: {res['num_fail']}\n\nTime taken: {time.perf_counter() - startTime:.6f} seconds.")
                res['results'].sort(key=lambda row: (not row.get('error', False), -len(row), row['title'].lower())) # Sort by if error, # of changes, then title
                SyncCompletionDialog(self.gui, "Sync Completed", message, res['results'], type="info").show()
        self.absSyncWorker.finished_signal.connect(on_finished)
        self.absSyncWorker.start()

    def audible_search(self, params):
        # https://audible.readthedocs.io/en/latest/misc/external_api.html#get--1.0-catalog-products
        headers = {
            'Accept': 'application/json',
            'User-Agent': f'CalibreAudiobookshelfSync/{self.version}',
        }
        req = Request(f"https://api.audible{CONFIG['audibleRegion']}/1.0/catalog/products?{urllib.parse.urlencode(params)}", headers=headers)
        with urlopen(req, timeout=10) as response:
            resp_data = response.read()
            return json.loads(resp_data.decode('utf-8'))

    def sync_audible_rating(self):
        if not CONFIG.get('checkbox_enable_Audible_ASIN_sync', False):
            show_error(self.gui, "Configuration Error", "Audible ASIN sync is not enabled but is required for this feature, please enable it in the configuration.")
            return

        audible_cols = {col_lookup_name: COLUMNS[config_key]['data_location'] for config_key, col_lookup_name in CONFIG.items() if config_key.startswith('column_audible_') and col_lookup_name}
        if not audible_cols:
            show_error(self.gui, "Configuration Error", "No Audible columns configured for syncing, please configure them in the plugin settings.")
            return

        db = self.gui.current_db.new_api
        bookList = list(db.search('identifiers:"=audible:"'))
        if not bookList:
            show_info(self.gui, "No Linked Books/ASINs", "Calibre library has no linked books and/or ASINs, try using Quick Link or manually linking books and verify Audiobookshelf has ASINs filled in.")
            return
        bookList = [
            {
                'book_id': book_id,
                'metadata': metadata,
                'ASIN': str(metadata.get('identifiers', {}).get('audible')),
                'current_values': {key: metadata.get(key, '') for key in audible_cols.keys()}
            }
            for book_id in bookList
            if (metadata := db.get_metadata(book_id))
        ]

        # Query Audible API for ratings in chunks of 50 ASINs (API restriction). Save response data as dict keyed by ASIN
        audible_ratings = {}
        for i in range(0, len(bookList), 50):                
            audible_ratings.update({item['asin']: item for item in self.audible_search({
                'asins': ','.join([book['ASIN'] for book in bookList[i:i + 50]]),
                'response_groups': 'rating'
            })['products']})

        class AudibleSyncWorker(QThread):
            progress_update = pyqtSignal(int)
            finished_signal = pyqtSignal(list)

            def __init__(self, action, db, bookList, audible_ratings, audible_cols):
                super().__init__()
                self.action = action
                self.db = db
                self.bookList = bookList
                self.audible_ratings = audible_ratings
                self.audible_cols = audible_cols

            def run(self):
                log = []
                for i, book in enumerate(bookList):
                    self.progress_update.emit(i)
                    if 'rating' not in audible_ratings.get(book['ASIN'], {}):
                        log.append({'title': book['metadata'].get('title'), 'ASIN': book['ASIN'], 'error': 'No rating found'})
                        continue
                    log.append({'title': book['metadata'].get('title'), 'ASIN': book['ASIN']})
                    for col_lookup_name, data_location in audible_cols.items():
                        new_value = self.action.get_nested_value(audible_ratings[book['ASIN']], data_location)
                        if isinstance(new_value, float): # Audible rating is a float, but we want to store it as an int*2 (for half rating) in calibre
                            new_value = int(new_value*2)
                        if new_value != book['current_values'][col_lookup_name]:
                            book['metadata'].set(col_lookup_name, new_value)
                            db.set_metadata(book['book_id'], book['metadata'], set_title=False, set_authors=False)
                            log[i][col_lookup_name] = f"{book['current_values'][col_lookup_name] if book['current_values'][col_lookup_name] is not None else '-'} >> {new_value}"
                self.finished_signal.emit(log)

        startTime = time.perf_counter()
        self.audibleSyncWorker = AudibleSyncWorker(self, db, bookList, audible_ratings, audible_cols)
        progress_dialog = None
        if len(audible_ratings)>25:
            progress_dialog = ProgressDialog(self.gui, "Updating Audible Data...", len(audible_ratings))
            progress_dialog.show()
            self.audibleSyncWorker.progress_update.connect(progress_dialog.setValue)
        def on_finished(log):
            if progress_dialog:
                progress_dialog.close()
            log.sort(key=lambda row: (not row.get('error', False), -len(row), row['title'].lower())) # Sort by if error, # of changes, then title
            SyncCompletionDialog(self.gui, 
                                    "Audible Ratings Updated",
                                    (f"Total books processed: {len(bookList)}\n"
                                    f"Updated: {sum(1 for d in log if any(key.startswith('#') for key in d.keys()))}\n"
                                    f"Skipped: {len([d for d in log if len(d) == 2])}\n"
                                    f"Failed: {sum(1 for d in log if 'error' in d)}"
                                    f"\n\nTime taken: {time.perf_counter() - startTime:.6f} seconds"),
                                    log, resultsColWidth=0, type="good").show()
        self.audibleSyncWorker.finished_signal.connect(on_finished)
        self.audibleSyncWorker.start()

    def get_abs_covers(self):
        db = self.gui.current_db.new_api
        server_url = CONFIG.get('abs_url', 'http://localhost:13378')
        api_key = CONFIG.get('abs_key', '')
        if not api_key:
            show_error(self.gui, "Configuration Error", "API Key not set in configuration.")
            return

        selected_ids = self.gui.library_view.get_selected_ids()
        if not selected_ids:
            show_info(self.gui, "No Selection", "No books selected.")
            return

        def fetch_cover_bytes(abs_id: str) -> bytes:
            # raw cover endpoint returns image (not JSON), so use urlopen directly, not api_request
            from urllib.request import Request, urlopen
            from urllib.error import URLError, HTTPError
            req = Request(f"{server_url}/api/items/{abs_id}/cover",
                        headers={'Authorization': f'Bearer {api_key}', 'User-Agent': f'CalibreAudiobookshelfSync/{self.version}'})
            try:
                with urlopen(req, timeout=10) as r:
                    return r.read()
            except (HTTPError, URLError):
                return b""

        def sha1(data: bytes) -> str:
            import hashlib
            return hashlib.sha1(data).hexdigest() if data else ""

        rows = []
        updatable = []  # parallel to rows, holds (book_id, server_bytes)
        for book_id in selected_ids:
            mi = db.get_metadata(book_id)
            ids = mi.get('identifiers', {}) or {}
            abs_id = ids.get('audiobookshelf_id') or ids.get('audiobookshelf') or ids.get('audiobookshelfId')
            if not abs_id:
                continue  # skip items without ABS id

            # current calibre cover (bytes)
            current_bytes = b""
            try:
                # db.cover returns a path in older APIs; if so, read it
                path_or_data = db.cover(book_id)
                if isinstance(path_or_data, (bytes, bytearray)):
                    current_bytes = bytes(path_or_data)
                elif path_or_data:
                    try:
                        with open(path_or_data, 'rb') as fh:
                            current_bytes = fh.read()
                    except Exception:
                        current_bytes = b""
            except Exception:
                current_bytes = b""

            server_bytes = fetch_cover_bytes(abs_id)
            if not server_bytes:
                continue

            # skip if identical
            if sha1(current_bytes) == sha1(server_bytes):
                continue

            # build pixmaps
            current_pm = QPixmap()
            server_pm = QPixmap()
            current_pm.loadFromData(current_bytes) if current_bytes else None
            server_pm.loadFromData(server_bytes)

            rows.append({
                'Add?': True,
                'title': mi.get('title', ''),
                'Current Cover': current_pm if not current_pm.isNull() else QPixmap(),
                'Server Cover': server_pm
            })
            updatable.append((book_id, server_bytes))

        if not rows:
            show_info(self.gui, "Covers", "Nothing to update (no ABS IDs, no server covers, or covers already match).")
            return

        msg = ("Check the items whose covers you want to update.\n"
            "Only books with an Audiobookshelf ID are shown; identical covers are hidden.")
        dlg = SyncCompletionDialog(self.gui, "Get Audiobookshelf Covers", msg, rows, resultsColWidth=0, type="info")
        table = dlg.table_area.findChild(QTableWidget)
        table.setSortingEnabled(False)
        headers = [table.horizontalHeaderItem(c).text() for c in range(table.columnCount())]
        try:
            title_col = headers.index('title')
            cur_col = headers.index('Current Cover')
            srv_col = headers.index('Server Cover')
            table.hideColumn(title_col)
            table.setColumnWidth(cur_col, 320)
            table.setColumnWidth(srv_col, 320)
        except ValueError:
            pass
        table.resizeRowsToContents()

        if dlg.exec_() and hasattr(dlg, 'checked_rows') and dlg.checked_rows:
            updated_ids = []
            for row_idx in dlg.checked_rows:
                book_id, server_bytes = updatable[row_idx]
                # db.set_cover accepts bytes in newer APIs; fall back to temp-file if needed
                try:
                    db.set_cover({book_id: server_bytes})
                except Exception:
                    import tempfile, os
                    fd, tmp = tempfile.mkstemp(suffix='.jpg'); os.close(fd)
                    try:
                        with open(tmp, 'wb') as f: f.write(server_bytes)
                        with open(tmp, 'rb') as f: db.set_cover({book_id: f})
                    finally:
                        try: os.remove(tmp)
                        except Exception: pass
                updated_ids.append(book_id)

            # minimal refresh so covers pop immediately
            if updated_ids:
                self.gui.library_view.model().refresh()
                self.gui.library_view.select_rows(updated_ids) # highlight what changed

            SyncCompletionDialog(
                self.gui,
                "Cover Update Complete",
                f"Updated covers for {len(updated_ids)} book(s).",
                [{'title': db.get_metadata(bid).get('title', ''), 'updated': 'OK'} for bid in updated_ids],
                resultsColWidth=0,
                type='good'
            ).show()

    def quick_link_books(self):
        import difflib

        db = self.gui.current_db.new_api
        all_book_ids = list(db.search('not identifiers:"=audiobookshelf_id:"'))
        if not all_book_ids:
            show_info(self.gui, "All Books Linked", "All the books in the calibre library have already been linked, this function won't do anything.")
            return

        if CONFIG.get('checkbox_cache_QuickLink_history', False):
            QLCache = JSONConfig('plugins/Audiobookshelf QL Cache.json')
            cacheList = QLCache.get('cache', [])
            all_book_ids = [book_id for book_id in all_book_ids if book_id not in cacheList]
            if not all_book_ids:
                cacheList = [
                    {
                        'hidden_book_id': book_id,
                        'title': metadata.title,
                        'authors': ', '.join(metadata.authors),
                    }
                    for book_id in cacheList
                    if (metadata := db.get_metadata(book_id))
                ]
                cacheList.sort(key=lambda row: row['title'].lower())  # Sort by title
                dialog = SyncCompletionDialog(self.gui, 
                                     "All Books Linked or Tried",
                                     ("All the books in the calibre library that have not been linked have already failed to QuickLink.\n\n"
                                      "See below for a list of books that have failed to link.\n"
                                      "Press the Backspace or Delete key while row(s) are selected to try them again during the next QuickLink."),
                                     cacheList, resultsColWidth=0, type="warn")
                table = dialog.table_area.findChild(QTableWidget)
                def custom_key_press(event):
                    if event.key() == Qt.Key_Delete or event.key() == Qt.Key_Backspace:
                        rows_to_remove = sorted({index.row() for index in table.selectedIndexes()}, reverse=True) # row index in descending order so the list doesn't shift meaningfully
                        cache_to_remove = sorted({int(table.item(row, 0).text()) for row in rows_to_remove}, reverse=True) # same for cache items
                        for row in rows_to_remove:
                            table.removeRow(row)
                        for item in cache_to_remove:
                            cacheList.pop(item)
                        QLCache['cache'] = [item['hidden_book_id'] for item in cacheList]
                table.keyPressEvent = custom_key_press
                dialog.show()
                return

        abs_items = self.get_abs_library_items(apply_library_filter=True)
        if abs_items is None:
            show_error(self.gui, "API Error", "Failed to retrieve Audiobookshelf library data, does user have library permissions or is Audiobookshelf empty?")
            return
        if not abs_items:
            show_info(
                self.gui,
                "No Libraries Available for Linking",
                "The selected Audiobookshelf library filters exclude all available audiobook libraries. "
                "Clear or adjust the filters in Audiobookshelf Account Settings."
            )
            return

        # key of ASIN and value of list of dict with keys abs_id and abs_title
        abs_asin_index = {}
        for item in abs_items:
            abs_asin = item.get('media', {}).get('metadata', {}).get('asin')
            abs_title = item.get('media', {}).get('metadata', {}).get('title', 'Unknown Title')
            if abs_asin:
                abs_asin_index.setdefault(abs_asin, []).append({'abs_id': item.get('id'), 'abs_title': abs_title})
        abs_asin_set = set(abs_asin_index.keys())

        class QuickLinkWorker(QThread):
            progress_update = pyqtSignal(int)
            finished_signal = pyqtSignal(dict)

            def __init__(self, action, db, book_ids):
                super().__init__()
                self.action = action
                self.db = db
                self.book_ids = book_ids

            def run(self):
                num_matched = 0
                num_failed = 0
                results = []
                for idx, book_id in enumerate(self.book_ids):
                    metadata = self.db.get_metadata(book_id)
                    title = metadata.get('title', 'None')
                    authors = metadata.get('authors', [])
                    if title and authors and authors[0] != 'Unknown':
                        try:
                            response = self.action.audible_search({
                                'title': title,
                                'author': authors[0],
                                'num_results': 25,
                                'response_groups': 'product_desc'
                            })
                            asin_overlap = {item['asin'] for item in response['products'] if difflib.SequenceMatcher(None, title, item['title']).ratio()>.5}.intersection(abs_asin_set)
                            if asin_overlap:
                                if len(asin_overlap) == 1:
                                    matched_asin = next(iter(asin_overlap))
                                    abs_id_list = abs_asin_index.get(matched_asin)
                                    if len(abs_id_list) == 1:
                                        num_matched += 1
                                        results.append({
                                            'title': metadata.get('title', f'Book {book_id}'),
                                            'matched title': f"{abs_id_list[0]['abs_title']}",
                                            'Link?': True,
                                            'hidden_book_id': book_id,
                                            'hidden_abs_id': abs_id_list[0]['abs_id'],
                                            'hidden_matched_asin': matched_asin,
                                            'hidden_metadata': metadata,
                                            **({'Audible Search Results': '\n'.join(item['title'] for item in response['products'])} if DEBUG else {})
                                        })
                                    else:
                                        num_failed += 1
                                        results.append({
                                            'title': metadata.get('title', f'Book {book_id}'),
                                            'error': f"{len(abs_id_list)} ABS books with same ASIN, manual match required"
                                        })
                                else:
                                    num_failed += 1
                                    results.append({
                                        'title': metadata.get('title', f'Book {book_id}'),
                                        'error': f"{len(asin_overlap)} possible matches found, manual match required"
                                    })
                            else:
                                num_failed += 1
                                results.append({
                                    'title': metadata.get('title', f'Book {book_id}'),
                                    'error': f"Audible search found {response['total_results']} books; {len(response['products'])} checked; none matched",
                                    'hidden_id_for_cache': book_id
                                })
                        except Exception:
                            num_failed += 1
                            results.append({
                                'title': metadata.get('title', f'Book {book_id}'),
                                'error': "Exception during Audible search"
                            })
                    else:
                        num_failed += 1
                        results.append({
                            'title': metadata.get('title', f'Book {book_id}'),
                            'error': "Calibre is missing title and/or author, which are required for QuickLink"
                        })
                    self.progress_update.emit(idx + 1)
                self.finished_signal.emit({'results': results, 'num_matched': num_matched, 'num_failed': num_failed})

        startTime = time.perf_counter()
        self.quickLinkWorker = QuickLinkWorker(self, db, all_book_ids)
        progress_dialog = None
        if len(all_book_ids)>5:
            progress_dialog = ProgressDialog(self.gui, "Quick linking books...", len(all_book_ids))
            progress_dialog.show()
            self.quickLinkWorker.progress_update.connect(progress_dialog.setValue)
        def on_finished(res):
            if progress_dialog:
                progress_dialog.close()
            if CONFIG.get('checkbox_cache_QuickLink_history', False):
                cacheList.extend([book['hidden_id_for_cache'] for book in res['results'] if 'hidden_id_for_cache' in book])
                QLCache['cache'] = cacheList
            if res['num_matched'] == 0:
                message = 'QuickLink Completed Without Matches.'
            else:
                message = f"Confirm Matches via Checkbox and Click ''Link Selected'' to Link Selected Matches.\nYou can double click the matched title to open up the book in Audiobookshelf."
            message += f"\nBooks matched: {res['num_matched']}\nBooks failed: {res['num_failed']}\n\nTime taken: {time.perf_counter() - startTime:.6f} seconds."
            res['results'].sort(key=lambda row: (not row.get('Link?', False), row['title'].lower())) # Sort by if linkable, then title
            dialog = SyncCompletionDialog(self.gui, "Quick Link Results", message, res['results'], resultsColWidth=0, type="info")
            table = dialog.table_area.findChild(QTableWidget)
            def on_cell_double_clicked(row, col):
                if col == 3 and (id := res['results'][int(table.item(row, 0).text())].get('hidden_abs_id')):
                    open_url(f"{CONFIG['abs_url']}/audiobookshelf/item/{id}")
                elif col == 2 and (asin := res['results'][int(table.item(row, 0).text())].get('hidden_matched_asin')): # Debug Only Open in Audible
                    open_url(f"https://www.audible{CONFIG['audibleRegion']}/pd/{asin}")
            table.cellDoubleClicked.connect(on_cell_double_clicked)
            if dialog.exec_() and hasattr(dialog, 'checked_rows') and dialog.checked_rows:
                for idx in dialog.checked_rows:
                    identifiers = res['results'][idx]['hidden_metadata'].get('identifiers', {})
                    identifiers['audiobookshelf_id'] = res['results'][idx]['hidden_abs_id']
                    res['results'][idx]['hidden_metadata'].set('identifiers', identifiers)
                    db.set_metadata(res['results'][idx]['hidden_book_id'], res['results'][idx]['hidden_metadata'], set_title=False, set_authors=False)
            else: # Either no selection or dialog canceled; do nothing
                pass

        self.quickLinkWorker.finished_signal.connect(on_finished)
        self.quickLinkWorker.start()

    def link_audiobookshelf_book(self):
        abs_items = self.get_abs_library_items(apply_library_filter=True)
        if abs_items is None:
            show_error(self.gui, "API Error", "Failed to retrieve Audiobookshelf library data, "
            "does user have library permissions or is Audiobookshelf empty?")
            return
        if not abs_items:
            show_info(
                self.gui,
                "No Libraries Available for Linking",
                "The selected Audiobookshelf library filters exclude all available audiobook libraries. "
                "Clear or adjust the filters in Audiobookshelf Account Settings."
            )
            return

        # Get me data
        server_url = CONFIG.get('abs_url', 'http://localhost:13378')
        api_key = CONFIG.get('abs_key', '')
        me_url = f"{server_url}/api/me"
        me_data = self.api_request(me_url, api_key)

        if me_data is None:
            show_error(self.gui, "API Error", "Failed to retrieve Audiobookshelf user data.")
            return

        filtered_items = [item for item in abs_items if isinstance(item, dict)]
        sorted_items = sorted(filtered_items, key=lambda x: x.get('media', {}).get('metadata', {}).get('title', '').lower())

        selected_ids = self.gui.library_view.get_selected_ids()
        if not selected_ids:
            show_info(self.gui, "No Selection", "No books selected.")
            return
        summary = {'linked': 0, 'skipped': 0, 'failed': 0, 'details': []}
        db = self.gui.current_db.new_api
        for book_id in selected_ids:
            metadata = db.get_metadata(book_id)
            book_title = metadata.get('title', f'Book {book_id}')
            book_uuid = metadata.get('uuid')
            
            dlg = LinkDialog(self.gui, sorted_items, calibre_metadata=metadata, me_data=me_data)
            if dlg.exec_():
                selected_item = dlg.get_selected_item()
                if selected_item:
                    abs_id = selected_item.get('id')
                    abs_title = selected_item.get('media', {}).get('metadata', {}).get('title', 'Unknown Title')
                    identifiers = metadata.get('identifiers', {})
                    if identifiers.get('audiobookshelf_id') is not None: # Already linked, so clear synced data
                        for config_key, col_lookup_name in CONFIG.items():
                            if config_key.startswith('column_') and col_lookup_name:
                                metadata.set(col_lookup_name, None)
                        db.set_metadata(book_id, metadata, force_changes=True, set_title=False, set_authors=False)
                    identifiers['audiobookshelf_id'] = abs_id
                    if CONFIG.get('checkbox_enable_Audible_ASIN_sync', False):
                        Audible_ASIN = selected_item.get('media').get('metadata').get('asin')
                        identifiers['audible'] = Audible_ASIN
                    metadata.set('identifiers', identifiers)
                    db.set_metadata(book_id, metadata, set_title=False, set_authors=False)
                    summary['linked'] += 1
                    summary['details'].append({
                        'title': book_title,
                        'mapped_title': abs_title,
                        'linked': 'Linked successfully'
                    })
                else:
                    summary['skipped'] += 1
                    summary['details'].append({
                        'title': book_title,
                        'mapped_title': '',
                        'skipped': 'Skipped by user'
                    })
            else:
                summary['skipped'] += 1
                summary['details'].append({
                    'title': book_title,
                    'mapped_title': '',
                    'skipped': 'Dialog cancelled'
                })
        message = (f"Link Audiobookshelf Book completed.\nBooks linked: {summary['linked']}\nBooks skipped: {summary['skipped']}")
        SyncCompletionDialog(self.gui, "Link Results", message, summary['details'], type="info").exec_()

    def unlink_audiobookshelf_book(self):
        selected_ids = self.gui.library_view.get_selected_ids()
        if not selected_ids:
            show_info(self.gui, "No Selection", "No books selected.")
            return
        log = []
        db = self.gui.current_db.new_api
        for book_id in selected_ids:
            metadata = db.get_metadata(book_id)
            identifiers = metadata.get('identifiers', {})
            log.append({'title': metadata.get('title', ''), 'abs_id': identifiers.get('audiobookshelf_id', '')})
            identifiers.pop('audiobookshelf_id', None)
            metadata.set('identifiers', identifiers)
            for config_key, col_lookup_name in CONFIG.items():
                if config_key.startswith('column_') and col_lookup_name:
                    metadata.set(col_lookup_name, None)
            db.set_metadata(book_id, metadata, force_changes=True, set_title=False, set_authors=False)
        SyncCompletionDialog(self.gui, "Unlinked From Audiobookshelf", 
                             f"{len(selected_ids)} {'book has' if len(selected_ids) == 1 else 'books have'} been unlinked from Audiobookshelf.", 
                             log, resultsColWidth=0, type="info").exec_()

    def get_abs_library_items(self, apply_library_filter=False):
        """Get items from Audiobookshelf libraries, optionally applying configured filters."""
        server_url = CONFIG.get('abs_url', 'http://localhost:13378')
        api_key = CONFIG.get('abs_key', '')
        configured_filtered_ids = CONFIG.get('abs_filtered_libraries', [])
        if not isinstance(configured_filtered_ids, (list, tuple, set)):
            configured_filtered_ids = []
        filtered_library_ids = {
            str(library_id)
            for library_id in configured_filtered_ids
        } if apply_library_filter else set()
        
        if not api_key:
            show_error(self.gui, "Configuration Error", "API Key not set in configuration.")
            return None

        # Get list of libraries
        libraries_url = f"{server_url}/api/libraries?minified=1"
        libraries_response = self.api_request(libraries_url, api_key)
        
        if libraries_response is None:
            show_error(self.gui, "API Error", "Failed to retrieve Audiobookshelf libraries.")
            return None

        # Extract libraries list from response
        libraries_data = libraries_response.get('libraries', [])
        
        # Build complete items list from all libraries
        all_items = []
        for library in libraries_data:
            library_id = library.get('id')
            library_name = library.get('name')
            if not library_id:
                continue
            if str(library_id) in filtered_library_ids:
                continue
            if library.get('mediaType') != 'book':
                continue  # Skip non-book libraries (like podcasts)
                
            items_url = f"{server_url}/api/libraries/{library_id}/items"
            items_data = self.api_request(items_url, api_key)
            
            if items_data is None:
                continue
                
            # Extract items from response and add library name
            items_list = [{**item, 'libraryName': library_name} for item in items_data["results"]]
                
            all_items.extend(items_list)
        
        if all_items:
            return all_items
        # An empty result is valid when the configured filter excludes every
        # audiobook library. Preserve the existing None-as-error behavior for
        # unfiltered callers.
        return [] if filtered_library_ids else None

    def get_abs_collections(self, server_url, api_key):
        collections_dict = {}
        collections_map = {}
        collections_data = self.api_request(f"{server_url}/api/collections", api_key)
        if collections_data is None:
            show_error(self.gui, "API Error", "Failed to retrieve Audiobookshelf collections.")
            return
        for collection in collections_data.get("collections", []):
            collection_name = collection.get("name")
            collections_map[collection_name] = collection.get("id")
            for book in collection.get("books", []):
                collections_dict.setdefault(book.get("id"), []).append(collection_name)
        
        playlists_data = self.api_request(f"{server_url}/api/playlists", api_key)
        if playlists_data is None:
            show_error(self.gui, "API Error", "Failed to retrieve Audiobookshelf playlists.")
            return
        for playlist in playlists_data.get("playlists", []):
            playlist_label = "PL " + playlist.get("name", "")
            collections_map[playlist_label] = playlist.get("id")
            for item in playlist.get("items", []):
                collections_dict.setdefault(item.get("libraryItemId"), []).append(playlist_label)

        return collections_dict, collections_map

class ProgressDialog(QDialog):
    def __init__(self, parent, title: str, count: int):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowCloseButtonHint)
        self.setWindowModality(Qt.WindowModal)
        layout = QVBoxLayout(self)
        self.progressBar = QProgressBar(self)
        self.progressBar.setMinimum(0)
        self.progressBar.setMaximum(count)
        self.progressBar.setFormat("%v of %m")
        layout.addWidget(self.progressBar)
    
    def setValue(self, value: int):
        self.progressBar.setValue(value)

class SyncCompletionDialog(QDialog):
    def __init__(self, parent=None, title="", msg="", results=None, resultsRowHeight=None, resultsColWidth=150, type=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(800)
        self.setMinimumHeight(800)
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # Main Message Area
        mainMessageLayout = QHBoxLayout()
        type_icon = {
            'info': 'dialog_information',
            'error': 'dialog_error',
            'warn': 'dialog_warning',
            'good': 'ok',
        }.get(type)
        if type_icon is not None:
            icon = QIcon.ic(f'{type_icon}.png')
            self.setWindowIcon(icon)
            icon_widget = QLabel(self)
            icon_widget.setPixmap(icon.pixmap(64, 64))
            mainMessageLayout.addWidget(icon_widget)
        message_label = QLabel(msg)
        mainMessageLayout.addWidget(message_label)
        mainMessageLayout.addStretch() # Left align the message/text
        layout.addLayout(mainMessageLayout)

        # Table in scrollable area if results are provided
        if results:
            self.table_area = QScrollArea(self)
            self.table_area.setWidgetResizable(True)
            table = self.create_results_table(results, resultsRowHeight, resultsColWidth)
            self.table_area.setWidget(table)
            layout.addWidget(self.table_area)

        # Bottom Buttons
        bottomButtonLayout = QHBoxLayout()
        if results:
            copy_button = QPushButton("COPY", self)
            copy_button.setFixedWidth(200)
            copy_button.setIcon(QIcon.ic('edit-copy.png'))
            copy_button.clicked.connect(lambda: (
                QApplication.clipboard().setText(str(results)), 
                copy_button.setText('Copied')
            ))
            bottomButtonLayout.addWidget(copy_button)
        bottomButtonLayout.addStretch() # Right align the rest of this layout
        ok_button = QPushButton("OK", self)
        ok_button.setFixedWidth(200)
        ok_button.setIcon(QIcon.ic('ok.png'))
        ok_button.clicked.connect(self.accept)
        ok_button.setDefault(True)
        if results:
            second_header = table.horizontalHeaderItem(1).text()
            if second_header in ('Link?', 'Add?'):
                if second_header == 'Link?':
                    ok_button.setText('Link Selected')
                    ok_button.setIcon(QIcon.ic('insert-link.png'))
                elif second_header == 'Add?':
                    ok_button.setText('Add Selected')
                    ok_button.setIcon(QIcon.ic('add_book.png'))
                def collect_checked_and_accept():
                    self.checked_rows = []
                    for row in range(table.rowCount()):
                        item = table.item(row, 1)  # checkbox column is 1
                        if item and item.checkState() == Qt.Checked:
                            orig_idx_item = table.item(row, 0)
                            if orig_idx_item:
                                self.checked_rows.append(int(orig_idx_item.text()))
                    self.accept()
                ok_button.clicked.connect(collect_checked_and_accept)
        bottomButtonLayout.addWidget(ok_button)
        layout.addLayout(bottomButtonLayout)
    
    def create_results_table(self, results, resultsRowHeight, resultsColWidth):
        # Get all possible headers from results (ignoring hidden_ prefix) and save as set
        all_headers = {key for result in results for key in result.keys() if not key.startswith('hidden_')}

        # Organize headers: idx very left hidden, checkbox left for QL, title first, messages in middle, custom columns last
        headers = ['idx', 'title']
        custom_columns = sorted(h for h in all_headers 
                               if h not in ('title', 'matched title', 'skipped', 'error', 'Link?', 'Add?'))
        
        if 'Link?' in all_headers:
            headers.insert(1, 'Link?')
        if 'Add?' in all_headers:
            headers.insert(1, 'Add?')
        if 'matched title' in all_headers:
            headers.append('matched title')
        if 'skipped' in all_headers:
            headers.append('skipped')
        if 'error' in all_headers:
            headers.append('error')
        if custom_columns:
            headers.extend(custom_columns)

        table = QTableWidget()
        table.setRowCount(len(results))
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setColumnHidden(0, True) # Hide idx column
        table.setSortingEnabled(True)

        # Populate Table
        for row, result in enumerate(results):
            for col, header in enumerate(headers):
                if header == "idx":
                    item = QTableWidgetItem(str(row))
                    item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                    table.setItem(row, col, item)
                elif header in ("Link?", "Add?"):
                    item = QTableWidgetItem("")
                    item.setFlags((item.flags() & ~Qt.ItemIsEditable) | Qt.ItemIsUserCheckable)
                    item.setTextAlignment(Qt.AlignCenter)
                    if header == "Link?" and result.get(header, False):
                        item.setCheckState(Qt.Checked)
                        item.setToolTip('Checked Box = Link, Unchecked Box = Skip')
                    elif header == "Add?":
                        item.setCheckState(Qt.Unchecked)
                        item.setToolTip('Check to add this Audiobookshelf item to calibre')
                    table.setItem(row, col, item)
                else: # All other headers
                    value = result.get(header, "")
                    if isinstance(value, QPixmap):
                        lbl = QLabel()
                        lbl.setAlignment(Qt.AlignCenter)
                        lbl.setPixmap(value.scaledToWidth(300, Qt.SmoothTransformation))
                        table.setCellWidget(row, col, lbl)
                    else:
                        item = QTableWidgetItem(str(value))
                        item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                        item.setToolTip(str(value))
                        table.setItem(row, col, item)

        # Set minimum width for each column
        if resultsColWidth == 0:
            table.resizeColumnsToContents()
            # Enforce a maximum width of 300 for each column
            for col in range(len(headers)):
                if table.columnWidth(col) > 300: 
                    table.setColumnWidth(col, 300)
        else:
            for col in range(len(headers)):
                table.setColumnWidth(col, resultsColWidth)

        if resultsRowHeight:
            if resultsRowHeight == 0:
                table.resizeRowsToContents()
                # Enforce a maximum height of 50 for each row, default = 30
                for row in range(len(results)):
                    if table.rowHeight(row) > 50: 
                        table.setRowHeight(row, 50)
            else:
                for row in range(len(results)):
                    table.setRowHeight(row, resultsRowHeight)

        max_lines = 1
        for col, header in enumerate(headers):
            words, line, lines, col_len_limit = header.split(), "", [], max(table.columnWidth(col) // 7, 10)
            for word in words:
                line = f"{line} {word}".strip()
                if len(line) > col_len_limit:
                    lines.append(line.rsplit(' ', 1)[0])
                    line = word if ' ' in line else ''
            lines.append(line)
            max_lines = max(len(lines), max_lines)
            wrapped = '\n'.join(lines)
            table.setHorizontalHeaderItem(col, QTableWidgetItem(wrapped))
        table.horizontalHeader().setFixedHeight(20 * max_lines) # Default = 20

        return table

class LinkDialog(QDialog):
    def __init__(self, parent, items, calibre_metadata=None, me_data=None):
        super().__init__(parent)
        self.setWindowTitle("Link Audiobookshelf Book")
        self.setMinimumWidth(800)
        self.setMinimumHeight(600)
        self.selected_item = None
        self.items = items
        self.calibre_metadata = calibre_metadata

        layout = QVBoxLayout(self)
        top_label = QLabel("Select the Audiobookshelf book to link:")
        layout.addWidget(top_label)
        if self.calibre_metadata is not None:
            # Assume calibre metadata provides 'title' and 'authors'
            calibre_title = self.calibre_metadata.get('title', 'Unknown Title')
            # For authors, attempt to join if it's a list, else use the string.
            calibre_authors = self.calibre_metadata.get('authors')
            if isinstance(calibre_authors, list):
                calibre_authors = ", ".join(calibre_authors)
            else:
                calibre_authors = calibre_authors or "Unknown Author"
            book_label_text = f'<b>{calibre_title}</b> by <i><b>{calibre_authors}</b></i>'
        else:
            book_label_text = ''
        book_label = QLabel(book_label_text)
        book_label.setWordWrap(True)
        layout.addWidget(book_label)
        if (linked_book_id := calibre_metadata.get('identifiers', {}).get('audiobookshelf_id')) is not None:
            linked_book_title = next(
                (item.get('media', {}).get('metadata', {}).get('title', '')
                for item in items if item.get('id') == linked_book_id),
                "Unknown Title"
            )
            already_linked_label = QLabel(f'<span style="color:red">This book is already linked to Audiobookshelf item <b>{linked_book_title}</b>.</span>')
            layout.addWidget(already_linked_label)

        self.table = QTableWidget(len(items), 3)
        self.table.setHorizontalHeaderLabels(["Title", "Author", "Reading/Read"])

        # Get calibre book details for comparison
        calibre_title = self.calibre_metadata.get('title', '').lower() if self.calibre_metadata else ''
        calibre_title_left_colon = calibre_title.split(':', 1)[0].strip() if ':' in calibre_title else ''
        calibre_authors = self.calibre_metadata.get('authors', []) if self.calibre_metadata else []
        if isinstance(calibre_authors, str):
            calibre_authors = [calibre_authors]
        calibre_authors = [author.lower() for author in calibre_authors]

        def authors_match(abs_author):
            abs_author_list = [author.strip() for author in abs_author.split(',') if author.strip()]
            return any(author in calibre_authors for author in abs_author_list)

        # Sort items - matched items first, then alphabetically by title
        def sort_key(item):
            metadata = item.get('media', {}).get('metadata', {})
            abs_title = metadata.get('title', '').lower()
            abs_author = metadata.get('authorName', '').lower()

            # Calculate match score: +3 exact title, +2 loose title, +1 author match
            score = 0
            if abs_title == calibre_title:
                score += 3
            elif calibre_title_left_colon and abs_title == calibre_title_left_colon:
                score += 2
            if authors_match(abs_author):
                score += 1
            if linked_book_id is not None and abs_title == linked_book_title.lower():
                score += 5  # Boost score for already linked book

            # Return tuple: (negative score for reverse sort, title for alphabetical)
            return (-score, abs_title)

        sorted_items = sorted(items, key=sort_key)
        self.items = sorted_items  # Update items list with sorted version

        # Create a light blue color for highlighting
        highlight_color = QColor(173, 216, 230)  # Light blue RGB values

        # Get list of library item IDs from me_data
        reading_ids = set()
        if me_data and 'mediaProgress' in me_data:
            reading_ids = {prog.get('libraryItemId') for prog in me_data['mediaProgress'] if prog.get('libraryItemId')}

        for row, item in enumerate(sorted_items):
            metadata = item.get('media', {}).get('metadata', {})
            abs_title = metadata.get('title', '')
            abs_author = metadata.get('authorName', '')

            # Create title item
            title_item = QTableWidgetItem(abs_title)
            title_item.setFlags(title_item.flags() & ~Qt.ItemIsEditable)
            abs_title_lower = abs_title.lower()
            if abs_title_lower == calibre_title or (calibre_title_left_colon and abs_title_lower == calibre_title_left_colon):
                title_item.setBackground(highlight_color)
                title_item.setForeground(QColor(0, 0, 0))  # Force black text
            self.table.setItem(row, 0, title_item)

            # Create author item  
            author_item = QTableWidgetItem(abs_author)
            author_item.setFlags(author_item.flags() & ~Qt.ItemIsEditable)
            if authors_match(abs_author.lower()):
                author_item.setBackground(highlight_color)
                author_item.setForeground(QColor(0, 0, 0))  # Force black text
            self.table.setItem(row, 1, author_item)

            # Create reading status item
            status_item = QTableWidgetItem()
            status_item.setFlags(status_item.flags() & ~Qt.ItemIsEditable)
            if item.get('id') in reading_ids:
                status_item.setIcon(QIcon.ic('ok.png'))
            self.table.setItem(row, 2, status_item)

        self.table.resizeColumnsToContents()
        self.table.setColumnWidth(0, 300)
        self.table.setColumnWidth(1, 300)
        self.table.setColumnWidth(2, 100)
        # Allow double-clicking a row to link
        self.table.cellDoubleClicked.connect(self.link)
        layout.addWidget(self.table)

        bottomButtonLayout = QHBoxLayout()
        skip_btn = QPushButton("Skip", self)
        skip_btn.setFixedWidth(200)
        skip_btn.setIcon(QIcon.ic('edit-redo.png'))
        skip_btn.clicked.connect(self.skip)
        bottomButtonLayout.addWidget(skip_btn)
        bottomButtonLayout.addStretch() # Right align the rest of this layout
        link_btn = QPushButton("Link", self)
        link_btn.setFixedWidth(200)
        link_btn.setIcon(QIcon.ic('insert-link.png'))
        link_btn.clicked.connect(self.link)
        link_btn.setDefault(True)
        bottomButtonLayout.addWidget(link_btn)
        layout.addLayout(bottomButtonLayout)

    def keyPressEvent(self, event):
        # Type a letter to jump to the row with a title starting with that letter.
        key = event.text().lower()
        if key:
            for i in range(self.table.rowCount()):
                item = self.table.item(i, 0)
                if item and item.text().lower().startswith(key):
                    self.table.selectRow(i)
                    break
        super().keyPressEvent(event)

    def link(self, *args):
        row = self.table.currentRow()
        self.selected_item = self.items[row] if 0 <= row < len(self.items) else None
        self.accept()

    def skip(self):
        self.selected_item = None
        self.accept()

    def get_selected_item(self):
        return self.selected_item
