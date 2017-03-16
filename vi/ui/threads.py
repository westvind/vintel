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

from PyQt5.QtCore import QThread, pyqtSignal
# from PyQt5.QtCore import SIGNAL

from queue import Queue
import time
import logging

from vi import evegate
from vi import koschecker
from vi.cache.cache import Cache

from vi.resources import resource_path


class AvatarFindThread(QThread):
    avatar_update = pyqtSignal(object, bytes)

    def __init__(self):
        QThread.__init__(self)
        self.q = Queue()

    def add_chatentry(self, chatentry, clear_cache=False):
        if clear_cache:
            cache = Cache()
            cache.remove_avatar(chatentry.message.user)
        self.q.put(chatentry)

    def run(self):
        cache = Cache()
        last_call = 0
        wait = 300  # time between 2 requests in ms
        while True:
            try:
                chatentry = self.q.get()
                charname = chatentry.message.user
                avatar = None

                logging.debug('loading avatar for {0}'.format(charname))

                if charname == "VINTEL":
                    logging.debug('fetching VINTEL avatar')
                    with open(resource_path("vi/ui/res/logo_small.png"), "rb") as f:
                        avatar = f.read()

                if not avatar:
                    logging.debug('getting avatar from cache')
                    avatar = cache.get_avatar(charname)

                if not avatar:
                    diff_last_call = time.time() - last_call
                    if diff_last_call < wait:
                        time.sleep((wait - diff_last_call) / 1000.0)

                    logging.debug('getting avatar from evegate')

                    avatar = evegate.get_avatar_for_player(charname)
                    last_call = time.time()

                    if avatar:
                        logging.debug('saving avatar from evegate to cache')
                        cache.put_avatar(charname, avatar)

                if avatar:
                    if isinstance(avatar, str):
                        self.avatar_update.emit(chatentry, eval(avatar))
                    elif isinstance(avatar, bytes):
                        self.avatar_update.emit(chatentry, avatar)
                    else:
                        logging.warning('unknown avatar object type {0}'.format(type(avatar)))

            except Exception as e:
                print("An error in the avatar-find-thread:", str(e))


class PlayerFindThread(QThread):
    def __init__(self):
        QThread.__init__(self)
        self.q = Queue()
        
    def add_chatentry(self, chatentry):
        self.q.put(chatentry)
        
    def run(self):
        # cache = Cache()
        while True:
            chatentry = self.q.get()
            # text = chatentry.message.utext
            # parts = text.split("  ")  # split@double-space (not in name, right?)


class KOSCheckerThread(QThread):
    kos_result = pyqtSignal(str, str, str, bool)

    def __init__(self):
        QThread.__init__(self)
        self.q = Queue()
        
    def add_request(self, names, request_type, only_kos=False):
        self.q.put((names, request_type, only_kos))
        
    def run(self):
        while True:
            names, request_type, only_kos = self.q.get()
            has_kos = False
            try:
                state = "ok"
                check_result = koschecker.check(names)
                text = koschecker.result_to_text(check_result, only_kos)
                for name, data in check_result.items():
                    if data["kos"] in (koschecker.KOS, koschecker.RED_BY_LAST):
                        has_kos = True
                        break
            except Exception as e:
                state = "error"
                text = str(e)

            # self.emit(SIGNAL("kos_result"), state, text, request_type, has_kos)
            self.kos_result.emit(state, text, request_type, has_kos)


class MapStatisticsThread(QThread):
    statistic_data_update = pyqtSignal(object)

    def __init__(self):
        QThread.__init__(self)
        
    def run(self):
        try:
            statistics = evegate.get_system_statistics()
            time.sleep(5)  # sleeping to prevent a "need 2 arguments"-error
            retdata = {"result": "ok", "statistics": statistics}
            # self.emit(SIGNAL("statistic_data_update"), retdata)
            self.statistic_data_update.emit(retdata)
        except Exception as e:
            retdata = {"result": "error", "text": str(e)}
            # self.statistic_data_update.emit(retdata)
            self.statistic_data_update.emit(retdata)
