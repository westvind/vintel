###########################################################################
#  Vintel - Visual Intel Chat Analyzer                                    #
#  Copyright (C) 2014-15 Sebastian Meyer (sparrow.242.de+eve@gmail.com )  #
#                                                                         #
#  This program is free software: you can redistribute it and/or modify   #
#  it under the terms of the GNU General Public License as published by   #
#  the Free Software Foundation, either version 3 of the License, or      #
#  (at your option) any later version.                                    #
#                                                                         #
#  This program is distributed in the hope that it will be useful,        #
#  but WITHOUT ANY WARRANTY; without even the implied warranty of         #
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the          #
#  GNU General Public License for more details.                           #
#                                                                         #
#                                                                         #
#  You should have received a copy of the GNU General Public License      #
#  along with this program.  If not, see <http://www.gnu.org/licenses/>.  #
###########################################################################

import os, re, time
from PyQt5.QtCore import QThread, QFileSystemWatcher, pyqtSignal

"""
There is a problem with the QFIleWatcher on Windows and the log
files from EVE.
The first implementation (now FileWatcher_orig) works fine on Linux, but
on Windows it seems ther is something buffered. Only a file-operation on
the watched directory another event there, which tirggers the OS to
reread the files informations, trigger the QFileWatcher.
So here is a workaround implementation.
We use here also a QFileWatcher, only to the directory. It will notify it
if a new file was created. We watch only the newest (last 24h), not all!
"""


class FileWatcher(QThread):
    fchange = pyqtSignal(str, str)

    def __init__(self, path, max_age):
        QThread.__init__(self)
        self.path = path
        self.max_age = max_age
        self.files = {}
        self.file_reg = re.compile('(.+)_\d{8}_\d{6}' + re.escape(os.path.extsep) + 'txt$', re.IGNORECASE)
        self.qtfw = QFileSystemWatcher()
        self.qtfw.directoryChanged.connect(self.directory_changed)
        self.qtfw.addPath(path)
        self.update_watched_files(path)

    def directory_changed(self, path):
        self.update_watched_files(path)

    def run(self):
        while True:
            for path, modified in self.files.items():
                new_modified = 0
                try:
                    new_modified = os.path.getsize(path)
                except Exception as e:
                    print('filewatcher-thread error:', path, str(e))
                if new_modified > modified:
                    chatname = None
                    test = self.file_reg.search(os.path.basename(path))
                    if test:
                        chatname = test.group(1)
                    self.fchange.emit(path, chatname)
                    self.files[path] = new_modified
            time.sleep(1)

    def update_watched_files(self, changed_path):
        # reeading all files from the directory
        now = time.time()
        path = self.path
        files_in_dir = set()

        for f in os.listdir(path):
            if not os.path.isdir(f):
                full_path = ''
                try:
                    add = True
                    full_path = os.path.join(path, f)
                    if self.max_age and now - os.path.getmtime(full_path) > self.max_age:
                        add = False
                    if add:
                        files_in_dir.add(full_path)
                except Exception as e:
                    print("file to filewatcher failed:", full_path, str(e))

        # are there old file, that not longer exists?
        files_to_remove = set()
        for known_file in self.files:
            if known_file not in files_in_dir:
                files_to_remove.add(known_file)

        for file_to_remove in files_to_remove:
            del self.files[file_to_remove]

        # are there new files we must watch now?
        for new_file in files_in_dir:
            if new_file not in self.files:
                self.files[new_file] = os.path.getsize(new_file)
