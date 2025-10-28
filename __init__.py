#!/usr/bin/env python3
"""Audiobookshelf Sync Plugin for calibre"""

import os
from functools import partial

from calibre.constants import DEBUG as _DEBUG
from calibre.constants import numeric_version
from calibre.customize import InterfaceActionBase
from calibre.devices.usbms.driver import debug_print as root_debug_print
from calibre.utils.config import JSONConfig

__license__ = 'GNU GPLv3'
__copyright__ = '2025, jbhul'

DEBUG = _DEBUG
DRY_RUN = False  # Used during debugging to skip the actual updating of metadata

if numeric_version >= (5, 5, 0):
    module_debug_print = partial(
        root_debug_print,
        ' audiobookshelf:__init__:',
        sep=''
    )
else:
    module_debug_print = partial(root_debug_print, ' audiobookshelf:__init__:')


class AudiobookshelfSync(InterfaceActionBase):
    name = 'Audiobookshelf Sync'
    description = 'Get metadata from a connected Audiobookshelf instance'
    author = 'jbhul'
    version = (1, 5, 2)
    minimum_calibre_version = (5, 0, 1)  # Because Python 3
    config = JSONConfig(os.path.join('plugins', 'Audiobookshelf Sync.json'))
    actual_plugin = 'calibre_plugins.audiobookshelf.action:AudiobookshelfAction'

    def is_customizable(self):
        return True

    def config_widget(self):
        if self.actual_plugin_:
            from calibre_plugins.audiobookshelf.config import ConfigWidget
            return ConfigWidget(self.actual_plugin_)
        return None

    def save_settings(self, config_widget):
        config_widget.save_settings()
