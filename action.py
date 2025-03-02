#!/usr/bin/env python3
"""Audiobookshelf Sync plugin for calibre"""

import json
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

from PyQt5.Qt import (
    QDialog,
    QIcon,
    QPushButton,
    QLabel,
    QFont,
    QHBoxLayout,
    QVBoxLayout,
    QTableWidget,
    QTableWidgetItem,
    QScrollArea,
    QUrl,
    QTimer,
    QTime,
    QColor,
    QApplication,
    Qt,
)
from PyQt5.QtGui import QPixmap

from calibre.gui2.actions import InterfaceAction
from calibre.gui2.dialogs.message_box import MessageBox
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

    def genesis(self):
        base = self.interface_action_base_plugin
        self.version = f'{base.name} (v{".".join(map(str, base.version))})'
        # Set up toolbar button icon and left-click action
        icon = get_icons('images/abs_icon.png')
        self.qaction.setIcon(icon)
        self.qaction.triggered.connect(self.sync_from_audiobookshelf)
        # Right-click menu (already includes left-click action)
        menu = self.qaction.menu()
        self.create_menu_action(
            menu,
            'Link Audiobookshelf Book',
            'Link Audiobookshelf Book',
            icon='insert-link.png',
            triggered=self.link_audiobookshelf_book,
            description=''
        )
        self.create_menu_action(
            menu,
            'Quick Link Books',
            'Quick Link Books',
            icon='wizard.png',
            triggered=self.quick_link_books,
            description=''
        )
        menu.addSeparator()
        self.create_menu_action(
            menu,
            'Configure',
            'Configure',
            icon='config.png',
            triggered=self.show_config,
            description=''
        )
        menu.addSeparator()
        self.create_menu_action(
            menu,
            'Readme',
            'Readme',
            icon='dialog_question.png',
            triggered=self.show_readme,
            description=''
        )
        self.create_menu_action(
            menu,
            'About',
            'About',
            icon='dialog_information.png',
            triggered=self.show_about,
            description=''
        )
        # Start scheduled sync if enabled
        if CONFIG.get('checkbox_enable_scheduled_sync', False):
            self.scheduled_sync()

    def show_config(self):
        self.interface_action_base_plugin.do_user_config(self.gui)

    def show_readme(self):
        open_url(QUrl('https://github.com/jbhul/Audiobookshelf-calibre-plugin#readme'))

    def show_about(self):
        text = get_resources('about.txt').decode('utf-8')
        if DEBUG:
            text += '\n\nRunning in debug mode'
        icon = get_icons('images/abs_icon.png')
        about_dialog = MessageBox(
            MessageBox.INFO,
            f'About {self.version}',
            text,
            det_msg='',
            q_icon=icon,
            show_copy_button=False,
            parent=None,
        )
        return about_dialog.exec_()

    def scheduled_sync(self):
        def scheduledTask():
            QTimer.singleShot(24 * 3600 * 1000, scheduledTask)
            self.sync_from_audiobookshelf(silent = True if not DEBUG else False)
        def main():
            currentTime = QTime.currentTime()
            targetTime = QTime(CONFIG.get('scheduleSyncHour', 4), CONFIG.get('scheduleSyncMinute', 0))
            timeDiff = currentTime.msecsTo(targetTime)
            if timeDiff < 0:
                timeDiff += 86400000
            QTimer.singleShot(timeDiff, scheduledTask)
        main()

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
            old_value = metadata.get(key)
            if new_value != old_value:
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

    def api_request(self, url, api_key):
        headers = {
            'Authorization': f'Bearer {api_key}',
            'Accept': 'application/json',
        }
        req = Request(url, headers=headers)
        try:
            with urlopen(req, timeout=20) as response:
                resp_data = response.read()
                return json.loads(resp_data.decode('utf-8'))
        except (HTTPError, URLError):
            return None

    def sync_from_audiobookshelf(self, silent=False):
        api_key = CONFIG.get('abs_key', '')
        library_id = CONFIG.get('abs_library_id', '')
        if not api_key or not library_id:
            show_error(self.gui, "Configuration Error", "API Key or Library ID not set in configuration.")
            return

        server_url = CONFIG.get('abs_url', 'http://localhost:13378')
        items_url = f"{server_url}/api/libraries/{library_id}/items"
        me_url = f"{server_url}/api/me"

        items_data = self.api_request(items_url, api_key)
        me_data = self.api_request(me_url, api_key)

        if items_data is None or me_data is None:
            show_error(self.gui, "API Error", "Failed to retrieve data from Audiobookshelf API.")
            return

        # If items_data is a dict with "results", use that list
        if isinstance(items_data, dict) and "results" in items_data:
            items_list = items_data["results"]
        elif isinstance(items_data, list):
            items_list = items_data
        else:
            items_list = []

        # Build dictionary mapping item id to item data (from lib_items)
        items_dict = {}
        for item in items_list:
            item_id = item.get('id')
            if item_id:
                items_dict[item_id] = item

        # Build dictionary mapping libraryItemId to media progress data (from mediaProgress)
        media_progress_dict = {}
        media_progress_list = me_data.get('mediaProgress', [])
        for prog in media_progress_list:
            lib_item_id = prog.get('libraryItemId')
            if lib_item_id:
                media_progress_dict[lib_item_id] = prog

        db = self.gui.current_db.new_api
        all_book_ids = db.search('')
        num_success = 0
        num_fail = 0
        num_skip = 0
        results = []

        for book_id in all_book_ids:
            metadata = db.get_metadata(book_id)
            book_uuid = metadata.get('uuid')
            identifiers = metadata.get('identifiers', {})
            abs_id = identifiers.get('audiobookshelf_id')
            if not abs_id:
                continue  # Skip books that are not linked
            item_data = items_dict.get(abs_id)
            if not item_data:
                results.append({'title': metadata.get('title', f'Book {book_id}'), 'error': 'Audiobookshelf item not found'})
                num_skip += 1
                continue
            progress_data = media_progress_dict.get(abs_id, {})

            result = {'title': metadata.get('title', f'Book {book_id}')}
            keys_values_to_update = {}
            
            # For each custom column, use api_source and data_location for lookup
            for config_name, col_meta in COLUMNS.items():
                column_name = CONFIG.get(config_name, '')
                if not column_name:  # Skip if column not configured
                    continue
                    
                data_location = col_meta.get('data_location', [])
                api_source = col_meta.get('api_source', '')
                value = None
                
                if api_source == "mediaProgress":
                    value = self.get_nested_value(progress_data, data_location)
                    if col_meta['column_heading'] == "Audiobook Started" and value is None:
                        value = True
                elif api_source == "lib_items":
                    value = self.get_nested_value(item_data, data_location)
                elif api_source == "me":
                    value = self.get_nested_value(me_data, data_location)
                    
                if value is not None:
                    if 'transform' in col_meta and callable(col_meta['transform']):
                        value = col_meta['transform'](value)
                    if value is not None:
                        old_value = metadata.get(column_name)
                        if old_value != value:
                            keys_values_to_update[column_name] = value
                            # Only add to result if there's an actual change
                            result[col_meta['column_heading']] = f"{old_value if old_value is not None else '-'} >> {value}"

            if keys_values_to_update:
                status, detail = self.update_metadata(book_uuid, keys_values_to_update)
                if status:
                    num_success += 1
                else:
                    num_fail += 1
                    result['error'] = detail.get('error', 'Unknown error')
            else:
                num_skip += 1
            results.append(result)

        if not silent:
            message = (f"Total books processed: {len(results)}\n"
                       f"Updated: {num_success}\nSkipped: {num_skip}\nFailed: {num_fail}\n")
            SyncCompletionDialog(self.gui, "Sync Completed", message, results, type="info").exec_()

    def quick_link_books(self):
        api_key = CONFIG.get('abs_key', '')
        library_id = CONFIG.get('abs_library_id', '')
        if not api_key or not library_id:
            show_error(self.gui, "Configuration Error", "API Key or Library ID not set in configuration.")
            return
        server_url = CONFIG.get('abs_url', 'http://localhost:13378')
        items_url = f"{server_url}/api/libraries/{library_id}/items"
        items_data = self.api_request(items_url, api_key)
        if items_data is None:
            show_error(self.gui, "API Error", "Failed to retrieve Audiobookshelf items.")
            return
        if isinstance(items_data, dict) and "results" in items_data:
            abs_items = items_data["results"]
        elif isinstance(items_data, list):
            abs_items = items_data
        else:
            abs_items = []
        isbn_index = {}
        asin_index = {}
        for item in abs_items:
            media = item.get('media', {})
            metadata_item = media.get('metadata', {})
            isbn = metadata_item.get('isbn')
            asin = metadata_item.get('asin')
            if isbn:
                isbn_index.setdefault(isbn, []).append(item)
            if asin:
                asin_index.setdefault(asin, []).append(item)
        db = self.gui.current_db.new_api
        all_book_ids = db.search('')
        num_linked = 0
        num_failed = 0
        results = []
        for book_id in all_book_ids:
            metadata = db.get_metadata(book_id)
            identifiers = metadata.get('identifiers', {})
            if 'audiobookshelf_id' in identifiers:
                continue  # already linked
            book_isbn = identifiers.get('isbn')
            book_asin = identifiers.get('asin')
            matched_item = None
            if book_isbn and book_isbn in isbn_index and len(isbn_index[book_isbn]) == 1:
                matched_item = isbn_index[book_isbn][0]
            elif book_asin and book_asin in asin_index and len(asin_index[book_asin]) == 1:
                matched_item = asin_index[book_asin][0]
            if matched_item:
                abs_id = matched_item.get('id')
                abs_title = matched_item.get('media', {}).get('metadata', {}).get('title', 'Unknown Title')
                identifiers['audiobookshelf_id'] = abs_id
                metadata.set('identifiers', identifiers)
                db.set_metadata(book_id, metadata, set_title=False, set_authors=False)
                num_linked += 1
                results.append({
                    'title': metadata.get('title', f'Book {book_id}'),
                    'linked': f'Linked to "{abs_title}"'
                })
            else:
                num_failed += 1
                results.append({
                    'title': metadata.get('title', f'Book {book_id}'),
                    'error': 'No unique match found'
                })
        message = (f"Quick Link Books completed.\nBooks linked: {num_linked}\nBooks failed: {num_failed}")
        SyncCompletionDialog(self.gui, "Quick Link Results", message, results, type="info").exec_()

    def link_audiobookshelf_book(self):
        api_key = CONFIG.get('abs_key', '')
        library_id = CONFIG.get('abs_library_id', '')
        if not api_key or not library_id:
            show_error(self.gui, "Configuration Error", "API Key or Library ID not set in configuration.")
            return

        server_url = CONFIG.get('abs_url', 'http://localhost:13378')
        items_url = f"{server_url}/api/libraries/{library_id}/items"
        me_url = f"{server_url}/api/me"  # Add /me endpoint URL

        # Get both items and me data
        items_data = self.api_request(items_url, api_key)
        me_data = self.api_request(me_url, api_key)  # Get user data including reading progress

        if items_data is None:
            show_error(self.gui, "API Error", "Failed to retrieve Audiobookshelf items.")
            return

        if me_data is None:
            show_error(self.gui, "API Error", "Failed to retrieve Audiobookshelf user data.")
            return

        if isinstance(items_data, dict) and "results" in items_data:
            items_list = items_data["results"]
        elif isinstance(items_data, list):
            items_list = items_data
        else:
            items_list = []

        filtered_items = [item for item in items_list if isinstance(item, dict)]
        sorted_items = sorted(filtered_items, key=lambda x: x.get('media', {}).get('metadata', {}).get('title', '').lower())

        selected_ids = self.gui.library_view.get_selected_ids()
        if not selected_ids:
            show_info(self.gui, "No Selection", "No books selected.")
            return
        summary = {'linked': 0, 'skipped': 0, 'failed': 0, 'details': []}
        for book_id in selected_ids:
            metadata = self.gui.current_db.new_api.get_metadata(book_id)
            book_title = metadata.get('title', f'Book {book_id}')
            book_uuid = metadata.get('uuid')
            
            dlg = LinkDialog(self.gui, sorted_items, calibre_metadata=metadata, me_data=me_data)
            if dlg.exec_():
                selected_item = dlg.get_selected_item()
                if selected_item:
                    abs_id = selected_item.get('id')
                    abs_title = selected_item.get('media', {}).get('metadata', {}).get('title', 'Unknown Title')
                    identifiers = metadata.get('identifiers', {})
                    identifiers['audiobookshelf_id'] = abs_id
                    metadata.set('identifiers', identifiers)
                    self.gui.current_db.new_api.set_metadata(book_id, metadata, set_title=False, set_authors=False)
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


class SyncCompletionDialog(QDialog):
    def __init__(self, parent=None, title="", msg="", results=None, type=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(800)
        self.setMinimumHeight(800)
        layout = QVBoxLayout(self)
        # Main Message Area
        mainMessageLayout = QHBoxLayout()
        type_icon = {
            'info': 'dialog_information',
            'error': 'dialog_error',
            'warn': 'dialog_warning',
        }.get(type)
        if type_icon is not None:
            icon = QIcon.ic(f'{type_icon}.png')
            mainMessageLayout.setSpacing(10)
            self.setWindowIcon(icon)
            icon_widget = QLabel(self)
            icon_widget.setPixmap(icon.pixmap(64, 64))
            mainMessageLayout.addWidget(icon_widget)
        message_label = QLabel(msg)
        message_label.setWordWrap(True)
        mainMessageLayout.addWidget(message_label)
        layout.addLayout(mainMessageLayout)
        # Scrollable area for the table
        self.table_area = QScrollArea(self)
        self.table_area.setWidgetResizable(True)
        if results:
            table = self.create_results_table(results)
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
        bottomButtonLayout.addWidget(ok_button)
        layout.addLayout(bottomButtonLayout)
    
    def create_results_table(self, results):
        # Get all possible headers from results
        all_headers = set()
        for result in results:
            all_headers.update(result.keys())
        
        # Organize headers: title first, custom columns in middle, error last
        headers = ['title']
        custom_columns = sorted(h for h in all_headers 
                               if h not in ('title', 'error', 'linked', 'skipped'))
        if custom_columns:
            headers.extend(custom_columns)
        if 'linked' in all_headers:
            headers.append('linked')
        if 'skipped' in all_headers:
            headers.append('skipped')
        headers.append('error')

        table = QTableWidget()
        table.setRowCount(len(results))
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(headers)

        # Set minimum width for each column
        for i in range(len(headers)):
            table.setColumnWidth(i, 150)

        for row, result in enumerate(results):
            for col, key in enumerate(headers):
                value = result.get(key, "")
                item = QTableWidgetItem(str(value))
                table.setItem(row, col, item)
                item.setToolTip(str(value))
        
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
            bottom_label_text = f"{calibre_title} by {calibre_authors}"
        else:
            bottom_label_text = ''
        bottom_label = QLabel(bottom_label_text)
        bold = QFont()
        bold.setBold(True)
        bottom_label.setFont(bold)
        bottom_label.setWordWrap(True)
        layout.addWidget(bottom_label)
        # Only two columns: Title and Author
        self.table = QTableWidget(len(items), 3)
        self.table.setHorizontalHeaderLabels(["Title", "Author", "Reading/Read"])
        
        # Get calibre book details for comparison
        calibre_title = self.calibre_metadata.get('title', '').lower() if self.calibre_metadata else ''
        calibre_authors = self.calibre_metadata.get('authors', []) if self.calibre_metadata else []
        if isinstance(calibre_authors, str):
            calibre_authors = [calibre_authors]
        calibre_authors = [author.lower() for author in calibre_authors]

        # Sort items - matched items first, then alphabetically by title
        def sort_key(item):
            metadata = item.get('media', {}).get('metadata', {})
            abs_title = metadata.get('title', '').lower()
            abs_author = metadata.get('authorName', '').lower()
            
            # Calculate match score: 2 for title+author match, 1 for either match, 0 for no match
            score = 0
            if abs_title == calibre_title:
                score += 1
            if abs_author in calibre_authors:
                score += 1
                
            # Return tuple: (negative score for reverse sort, title for alphabetical)
            return (-score, abs_title)
            
        sorted_items = sorted(items, key=sort_key)
        self.items = sorted_items  # Update items list with sorted version
        
        # Create a light blue color for highlighting
        highlight_color = QColor(173, 216, 230)  # Light blue RGB values
        
        # Create checkmark icon for reading/read status
        checkmark_icon = QIcon.ic('ok.png')
        
        # Get list of library item IDs from me_data
        reading_ids = set()
        if me_data and 'mediaProgress' in me_data:
            reading_ids = {prog.get('libraryItemId') for prog in me_data['mediaProgress'] if prog.get('libraryItemId')}

        for i, item in enumerate(sorted_items):
            metadata = item.get('media', {}).get('metadata', {})
            abs_title = metadata.get('title', '')
            abs_author = metadata.get('authorName', '')

            # Create title item
            title_item = QTableWidgetItem(abs_title)
            title_item.setFlags(title_item.flags() & ~Qt.ItemIsEditable)
            if abs_title.lower() == calibre_title:
                title_item.setBackground(highlight_color)
                title_item.setForeground(QColor(0, 0, 0))  # Force black text
            self.table.setItem(i, 0, title_item)

            # Create author item  
            author_item = QTableWidgetItem(abs_author)
            author_item.setFlags(author_item.flags() & ~Qt.ItemIsEditable)
            if abs_author.lower() in calibre_authors:
                author_item.setBackground(highlight_color)
                author_item.setForeground(QColor(0, 0, 0))  # Force black text
            self.table.setItem(i, 1, author_item)

            # Create reading status item
            status_item = QTableWidgetItem()
            status_item.setFlags(status_item.flags() & ~Qt.ItemIsEditable)
            if item.get('id') in reading_ids:
                status_item.setIcon(checkmark_icon)
            self.table.setItem(i, 2, status_item)

        self.table.selectRow(0)
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
