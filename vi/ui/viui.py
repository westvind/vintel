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

import datetime
import sys
import time
import webbrowser
import requests
import pickle
import base64
import logging
import json

from PyQt5 import QtGui, uic, QtCore, QtWidgets
from PyQt5.QtGui import QImage, QPixmap
from PyQt5.QtWidgets import QMessageBox, QMainWindow, QDialog, QWidget, QApplication, QActionGroup, QAction
from PyQt5.QtWebEngineWidgets import QWebEnginePage, QWebEngineView
from PyQt5 import QtWebChannel
from PyQt5.Qt import QWebEngineScript

from PyQt5.QtCore import QUrl, QPoint, pyqtSignal

from vi.ui.systemtray import TrayContextMenu
from vi.ui.threads import AvatarFindThread, KOSCheckerThread
from vi.ui.threads import MapStatisticsThread
import vi.version
from vi import chatparser, dotlan, filewatcher
from vi.chatparser.chatparser import ChatParser
from vi import sound, drachenjaeger, evegate
from vi.cache.cache import Cache
from vi import states

from vi.resources import resource_path

VERSION = vi.version.VERSION
DEBUG = True
log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)


class MainWindow(QMainWindow):
    sig_chatmessage_added = pyqtSignal(object)
    sig_avatar_loaded     = pyqtSignal(str, object)

    def __init__(self, path_to_logs, trayicon):
        """ systems = list of system-objects creted by dotlan.py
        """
        QMainWindow.__init__(self)
        uic.loadUi(resource_path('vi/ui/MainWindow.ui'), self)
        self.setWindowTitle("Vintel " + VERSION)
        self.setWindowIcon(QtGui.QIcon(resource_path("vi/ui/res/logo_small.png")))
        self.path_to_logs = path_to_logs
        self.trayicon = trayicon
        self.trayicon.activated.connect(self.systray_activated)
        c = Cache()
        regionname = c.get_from_cache("regionname")
        if not regionname:
            regionname = "Providence"
        # is it a local map?
        svg = None
        try:
            with open(resource_path("vi/ui/res/mapdata/{0}.svg".format(regionname))) as svg_file:
                svg = svg_file.read()
        except Exception as e:
            pass

        try:
            self.dotlan = dotlan.Map(regionname, svg)
        except dotlan.DotlanException as e:
            QMessageBox.critical(None, "Error getting map", str(e), QMessageBox.Close)
            sys.exit(1)

        if self.dotlan.outdated_cache_error:
            e = self.dotlan.outdated_cache_error
            diatext = "I tried to get and process the data for the map "\
                "but something went wrong. To proceed I use the data I "\
                "have in my cache. This could be outdated.\nIf this problem "\
                "is permanent, there might be a change in the dotlan data "\
                "and VINTEL must be modified. Check for a newer version "\
                "and inform the maintainer.\n\nWhat went wrong: {0} {1}"\
                .format(type(e), str(e))
            QMessageBox.warning(None, "Using map from my cache", diatext, QMessageBox.Ok)

        jumpbridge_url = c.get_from_cache("jumpbridge_url")
        self.set_jumpbridges(jumpbridge_url)
        self.init_map_position = None  # we read this after first rendering
        # self.systems = self.dotlan.systems
        self.chatentries = []

        self.kos_request_thread = KOSCheckerThread()
        self.kos_request_thread.kos_result.connect(self.show_kos_result)
        self.kos_request_thread.start()

        self.avatar_find_thread = AvatarFindThread()
        self.avatar_find_thread.avatar_update.connect(self.update_avatar_on_chatentry)
        self.avatar_find_thread.start()

        self.clipboard = QApplication.clipboard()
        self.clipboard.clear(mode=self.clipboard.Clipboard)
        self.old_clipboard_content = (0, "")
        self.clipboard.changed.connect(self.clipboard_changed)

        self.zoomin           .clicked.connect(self.zoomMapIn)
        self.zoomout          .clicked.connect(self.zoomMapOut)
        self.actionStatistics .clicked.connect(self.dotlan.change_statistics_visibility)
        self.chat_large       .clicked.connect(self.chat_larger)
        self.chat_small       .clicked.connect(self.chat_smaller)
        self.jumpBridgesButton.clicked.connect(self.change_jumpbridge_view)
        self.sound_button     .clicked.connect(self.show_sound_setup)

        self.actionInfo             .triggered.connect(self.show_info)
        self.actionShow_Chat_Avatars.triggered.connect(self.change_show_avatars)
        self.actionAlways_on_top    .triggered.connect(self.change_always_on_top)
        self.choose_chatrooms_button.triggered.connect(self.show_chatroom_chooser)
        self.choose_region_button   .triggered.connect(self.show_region_chooser)
        self.action_show_chat       .triggered.connect(self.change_chat_visibility)
        self.actionSound_Setup      .triggered.connect(self.show_sound_setup)

        self.opacity_group = QActionGroup(self.menu)
        for i in (100, 80, 60, 40, 20):
            action = QAction("Opacity {0}%".format(i), None, checkable=True)

            if i == 100:
                action.setChecked(True)

            action.opacity = i / 100.0
            action.triggered.connect(self.change_opacity)

            self.opacity_group.addAction(action)
            self.menuTransparency.addAction(action)

        # map with menu =======================================================
        self.custom_content_page = MainWindowPage()
        self.custom_content_page.sig_link_clicked.connect(self.map_link_clicked)
        self.map.setPage(self.custom_content_page)
        self.map.page().set_svg(self.dotlan.svg)

        self.map.contextmenu = TrayContextMenu(self.trayicon)

        def map_contextmenu_event(event):
            self.map.contextmenu.exec_(self.mapToGlobal(QPoint(event.x(),event.y())))

        self.map.contextMenuEvent = map_contextmenu_event
        # self.map.connect(self.map, Qt.SIGNAL("linkClicked(const QUrl&)"), self.map_link_clicked)
        # self.map.page().linkClicked.connect(self.map_link_clicked)
        # http://stackoverflow.com/questions/40747827/qwebenginepage-disable-links
        # end map =============================================================

        self.filewatcher_thread = filewatcher.FileWatcher(self.path_to_logs, 60*60*24)
        # self.connect(self.filewatcher_thread, QtCore.SIGNAL("fchange"), self.logfile_changed)
        self.filewatcher_thread.fchange.connect(self.logfile_changed)
        self.filewatcher_thread.start()

        if False:
            self.last_statistics_update = 0
            self.maptimer = QtCore.QTimer(self)
            # self.connect(self.maptimer, QtCore.SIGNAL("timeout()"), self.update_map)
            self.maptimer.timeout.connect(self.update_map)
            self.maptimer.start(1000)

        self.trayicon.sig_alarm_distance.connect(self.change_alarm_distance)
        self.trayicon.sig_change_frameless.connect(self.change_frameless)

        self.frameButton.clicked.connect(self.change_frameless)
        self.frameButton.setVisible(False)

        self.actionFrameless_Window.triggered.connect(self.change_frameless)

        self.is_frameless = None  # we need this because 2 places to change
        self.alarm_distance = 0
        self.actionActivate_Sound.triggered.connect(self.change_sound)

        if not sound.SOUND_AVAILABLE:
            self.change_sound(disable=True)
        else:
            self.change_sound()

        self.jumpbridgedata_button.triggered.connect(self.show_jumbridge_chooser)

        # load something from cache =====================================
        self.known_playernames = c.get_from_cache("known_playernames")
        if self.known_playernames:
            self.known_playernames = set(self.known_playernames.split(","))
        else:
            self.known_playernames = set()
        roomnames = c.get_from_cache("roomnames")
        if roomnames:
            roomnames = roomnames.split(",")
        else:
            roomnames = ("TheCitadel", "North Provi Intel")
            c.put_into_cache("roomnames", ",".join(roomnames), 60*60*24*365*5)

        self.set_sound_volume(75)  # default - maybe overwritten by the settings

        try:
            settings = c.get_from_cache("settings")
            if settings:
                settings = pickle.loads(base64.b64decode(settings))

                for setting in settings:
                    try:
                        if not setting[0]:
                            obj = self
                        else:
                            obj = getattr(self, setting[0])

                        getattr(obj, setting[1])(setting[2])
                    except Exception as e:
                        log.error(str(e))
        except Exception as e:
            self.trayicon.showMessage(
                "Can't remember",
                "Something went wrong when I load my last state:\n{0}".format(str(e)),
                1
            )
        # load cache ends ===============================================
        self.actionQuit.triggered.connect(self.close)
        self.trayicon.sig_quit.connect(self.close)

        self.chatparser = ChatParser(self.path_to_logs, roomnames, self.dotlan.systems)

        version_check_thread = drachenjaeger.NotifyNewVersionThread()
        version_check_thread.newer_version.connect(self.notify_newer_version)
        version_check_thread.run()
        
    def notify_newer_version(self, newest_version):
        self.trayicon.showMessage("Newer Version", 
                ("A newer Version of VINTEL is available.\n"
                 "Find the URL in the info!"), 1)
        
    def change_chat_visibility(self, new_value=None):
        if new_value is not None:
            self.action_show_chat.setChecked(new_value)
        self.chatbox.setVisible(self.action_show_chat.isChecked())
        
    def change_opacity(self, lvl=None):
        if isinstance(lvl, float):
            opacityVal = lvl
        elif self.sender():
            opacityVal = self.sender().opacity
        else:
            opacityVal = 1.0

        if opacityVal:
            for action in self.opacity_group.actions():
                if action.opacity == opacityVal:
                    action.setChecked(True)

        action = self.opacity_group.checkedAction()
        self.setWindowOpacity(action.opacity)

    def change_sound(self, new_value=None, disable=False):
        if disable:
            self.actionActivate_Sound.setChecked(False)
            self.actionActivate_Sound.setEnabled(False)
            self.actionSound_Setup.setEnabled(False)
            self.sound_button.setEnabled(False)
            QMessageBox.warning(
                None,
                "Sound disabled",
                "I can't find the lib 'pygame' which I use to play sounds, so I have to disable the soundsystem.\n"
                "If you want sound, please install the 'pygame' library.",
                QMessageBox.Ok
            )
        else:
            if new_value is not None:
                self.actionActivate_Sound.setChecked(new_value)
            sound.sound_active = self.actionActivate_Sound.isChecked()
        
    def add_message_to_intelchat(self, message):
        scroll_to_bottom = False
        if (self.chatListWidget.verticalScrollBar().value() == self.chatListWidget.verticalScrollBar().maximum()):
            scroll_to_bottom = True

        entry = ChatEntry(message)
        listWidgetItem = QtWidgets.QListWidgetItem(self.chatListWidget)
        listWidgetItem.setSizeHint(entry.sizeHint())
        self.chatListWidget.addItem(listWidgetItem)
        self.chatListWidget.setItemWidget(listWidgetItem, entry)
        if ChatEntry.SHOW_AVATAR:
            # log.debug('requesting "{0}" avatar'.format(entry.message.user))
            self.avatar_find_thread.add_chatentry(entry)
        # else:
            # log.debug('requesting "{0}" avatar disabled in options'.format(entry.message.user))
        self.chatentries.append(entry)
        entry.mark_system.connect(self.mark_system_on_map)
        self.sig_chatmessage_added.emit(entry)
        if scroll_to_bottom:
            self.chatListWidget.scrollToBottom()

    def change_always_on_top(self, new_value=None):
        self.hide()
        if new_value is not None:
            self.actionAlways_on_top.setChecked(new_value)
        always_on_top = self.actionAlways_on_top.isChecked()
        if always_on_top:
            self.setWindowFlags(self.windowFlags() |
                                QtCore.Qt.WindowStaysOnTopHint)
        else:
            self.setWindowFlags(self.windowFlags() &
                                (~QtCore.Qt.WindowStaysOnTopHint))
        self.show()
        
    def change_frameless(self, new_value=None):
        self.hide()
        if new_value is None:
            if self.is_frameless is None:
                self.is_frameless = False
            new_value = not self.is_frameless
        if new_value:
            self.setWindowFlags(QtCore.Qt.FramelessWindowHint)
            self.menubar.setVisible(False)
            self.frameButton.setVisible(True)
        else:
            self.setWindowFlags(self.windowFlags() &
                                (~QtCore.Qt.FramelessWindowHint))
            self.menubar.setVisible(True)
            self.frameButton.setVisible(False)
        self.change_always_on_top(new_value)
        self.is_frameless = new_value
        self.actionFrameless_Window.setChecked(new_value)
        for cm in TrayContextMenu.INSTANCES:
            cm.frameless_check.setChecked(new_value)
        self.show()
            
    def change_show_avatars(self, new_value=None):
        if new_value is not None:
            self.actionShow_Chat_Avatars.setChecked(new_value)
        show = self.actionShow_Chat_Avatars.isChecked()
        ChatEntry.SHOW_AVATAR = show
        for entry in self.chatentries:
            entry.avatar_label.setVisible(show)

    def chat_smaller(self):
        new_size = ChatEntry.TEXTSIZE - 1
        ChatEntry.TEXTSIZE = new_size
        for entry in self.chatentries:
            entry.change_fontsize(new_size)

    def chat_larger(self):
        new_size = ChatEntry.TEXTSIZE + 1
        ChatEntry.TEXTSIZE = new_size
        for entry in self.chatentries:
            entry.change_fontsize(new_size)
            
    def change_alarm_distance(self, distance):
        self.alarm_distance = distance
        for cm in TrayContextMenu.INSTANCES:
            for action in cm.distance_group.actions():
                if action.alarm_distance_value == distance:
                    action.setChecked(True)
        self.trayicon.alarm_distance_value = distance
            
    def change_jumpbridge_view(self):
        self.dotlan.change_jumpbrigde_visibility()
        self.update_map()
            
    def clipboard_changed(self, mode):
        if mode == 0 and self.action_kos_clipboard_active.isChecked():
            content = str(self.clipboard.text())
            last_modified, old_content = self.old_clipboard_content
            if content == old_content and time.time() - last_modified < 3:
                parts = content.split("\n")
                for part in parts:
                    if part in self.known_playernames:
                        self.trayicon.setIcon(QtGui.QIcon(resource_path("vi/ui/res/logo_small_green.png")))
                        self.kos_request_thread.add_request(parts, "clipboard", True)
                        self.old_clipboard_content = (0, "")
                        break
            else:
                self.old_clipboard_content = (time.time(), content)
                
    def closeEvent(self, event):
        """ writing the cache before closing the window """
        c = Cache()
        # known playernames
        if self.known_playernames:
            value = ",".join(self.known_playernames)
            c.put_into_cache("known_playernames", value, 60*60*24*365)
        # program state to cache (to read it on next startup)
        settings = (
            (None,                          "restoreGeometry",             self.saveGeometry()),
            (None,                          "restoreState",                self.saveState()),
            (None,                          "change_opacity",              self.opacity_group.checkedAction().opacity),
            (None,                          "change_always_on_top",        self.actionAlways_on_top.isChecked()),
            ("splitter",                    "restoreGeometry",             self.splitter.saveGeometry()),
            ("splitter",                    "restoreState",                self.splitter.saveState()),
            (None,                          "change_show_avatars",         self.actionShow_Chat_Avatars.isChecked()),
            (None,                          "change_alarm_distance",       self.alarm_distance),
            ("action_kos_clipboard_active", "setChecked",                  self.action_kos_clipboard_active.isChecked()),
            (None,                          "change_sound",                self.actionActivate_Sound.isChecked()),
            (None,                          "change_chat_visibility",      self.action_show_chat.isChecked()),
            ("map",                         "setZoomFactor",               self.map.zoomFactor()),
            (None,                          "set_init_map_scrollposition", (self.map.page().scrollPosition().x(),
                                                                            self.map.page().scrollPosition().y())),
            (None,                          "set_sound_volume",            self.sound_volume),
            (None,                          "change_frameless",            self.actionFrameless_Window.isChecked()),
        )
        settings = pickle.dumps(settings, protocol=pickle.HIGHEST_PROTOCOL)
        c.put_into_cache("settings", base64.b64encode(settings), 60*60*24*365)
        event.accept()
          
    def map_link_clicked(self, url):
        systemname = str(url.path().split("/")[-1]).upper()
        system = self.dotlan.systems[str(systemname)]
        sc = SystemChat(self, SystemChat.SYSTEM, system, self.chatentries, self.known_playernames)
        self.sig_chatmessage_added.connect(sc.add_chatentry)
        self.sig_avatar_loaded.connect(sc.new_avatar_available)
        sc.sig_location_set.connect(self.set_location)
        sc.show()
        
    def mark_system_on_map(self, systemname):
        self.map.page().mark_system(systemname)

        # self.dotlan.systems[str(systemname)].mark()
        # self.update_map()

    def set_location(self, char, new_system):
        self.map.page().mark_player(char, new_system)

        """
        for system in self.dotlan.systems.values():
            system.remove_located_character(char)

        if not new_system == "?" and new_system in self.dotlan.systems:
            self.dotlan.systems[new_system].add_located_character(char)
            self.set_map_content(self.dotlan.svg)
        """
        
    def set_init_map_scrollposition(self, xy):
        self.init_map_position = QPoint(xy[0], xy[1])
        
    def show_chatroom_chooser(self):
        chooser = ChatroomsChooser(self)
        chooser.rooms_changed.connect(self.changed_roomnames)
        chooser.show()
        
    def show_jumbridge_chooser(self):
        cache = Cache()
        url = cache.get_from_cache("jumpbridge_url")
        chooser = JumpBridgeChooser(self, url)
        chooser.set_jb_url.connect(self.set_jumpbridges)
        chooser.show()
        
    def set_sound_volume(self, value):
        if value < 0:
            value = 0
        elif value > 100:
            value = 100

        self.sound_volume = value
        sound.set_sound_volume(float(value) / 100.0)
        
    def set_jumpbridges(self, url):
        if url is None:
            url = ""
        try:
            data = []
            if url != "":
                content = requests.get(url).text
                for line in content.split("\n"):
                    parts = line.strip().split()
                    if len(parts) == 3:
                        data.append(parts)
            else:
                data = drachenjaeger.get_jumpbridge_data(
                    self.dotlan.region.lower())
            self.dotlan.set_jumpbridges(data)
            c = Cache()
            c.put_into_cache("jumpbridge_url", url, 60*60*24*365*8)
        except Exception as e:
            QMessageBox.warning(None, "Loading jumpbridges failed!", "Error: {0}".format(str(e)), QMessageBox.Ok)
        
    def show_region_chooser(self):
        chooser = RegionChooser(self)
        chooser.show()

    def show_kos_result(self, state, text, request_type, has_kos):
        if has_kos:
            sound.play_sound("beep")

        self.trayicon.setIcon(QtGui.QIcon(resource_path("vi/ui/res/logo_small.png")))

        if state == "ok":
            if request_type == "xxx":  # a xxx request out of the chat
                self.trayicon.showMessage("A xxx KOS-Check", text, 1)
            elif request_type == "clipboard":  # request from clipboard-change
                if len(text) <= 0:
                    text = "Noone KOS"

                self.trayicon.showMessage("Your KOS-Check", text, 1)

            text = text.replace("\n\n", "<br>")
            message = chatparser.chatparser.Message("Vintel KOS-Check", text, 
                evegate.current_eve_time(), "VINTEL", [], states.NOT_CHANGE,
                text.upper(), text)

            self.add_message_to_intelchat(message)
        elif state == "error":
            self.trayicon.showMessage("KOS Failure", text, 3)

    def changed_roomnames(self, new_roomnames):
        cache = Cache()
        cache.put_into_cache("roomnames", u",".join(new_roomnames), 60*60*24*365*5)
        self.chatparser.rooms = new_roomnames
        
    def show_info(self):
        info_dialog = QDialog(self)
        uic.loadUi(resource_path("vi/ui/Info.ui"), info_dialog)
        info_dialog.version_label.setText(u"Version: {0}".format(VERSION))
        info_dialog.logo_label.setPixmap(QtGui.QPixmap(resource_path("vi/ui/res/logo.png")))
        info_dialog.close_button.clicked.connect(info_dialog.accept)
        info_dialog.show()
        
    def show_sound_setup(self):
        dialog = QDialog(self)
        uic.loadUi(resource_path("vi/ui/SoundSetup.ui"), dialog)
        dialog.volumeSlider.setValue(self.sound_volume)
        dialog.volumeSlider.valueChanged.connect(self.set_sound_volume)
        dialog.testsound_button.clicked.connect(sound.play_sound)
        dialog.close_button.clicked.connect(dialog.accept)
        dialog.show()

    def systray_activated(self, reason):
        if reason == QtWidgets.QSystemTrayIcon.Trigger:
            if self.isMinimized():
                self.showNormal()
                self.activateWindow()
            elif not self.isActiveWindow():
                self.activateWindow()
            else:
                self.showMinimized()

    def update_avatar_on_chatentry(self, chatentry, avatar_data):
        updated = chatentry.update_avatar(avatar_data)
        if not updated:
            self.avatar_find_thread.add_chatentry(chatentry, clear_cache=True)
        else:
            self.avatar_loaded.emit(chatentry.message.user, avatar_data)

    """
    def update_map(self):
        # log.debug('check')

        def update_statistics_on_map(data):
            if data["result"] == "ok":
                self.dotlan.add_system_statistics(data["statistics"])
            elif data["result"] == "error":
                text = data["text"]
                self.trayicon.showMessage("Loading statstics failed", text, 3)

        if self.last_statistics_update < (time.time() - 5 * 60):
            self.last_statistics_update = time.time()
            statistic_thread = MapStatisticsThread()
            # self.connect(statistic_thread, Qt.SIGNAL("statistic_data_update"), update_statistics_on_map)
            statistic_thread.statistic_data_update.connect(update_statistics_on_map)
            statistic_thread.start()

        self.set_map_content(self.dotlan.svg)

    def set_map_content(self, content):
        if self.init_map_position is None:
            scrollposition = self.map.page().scrollPosition()
            # scrollposition = self.map.scrollPosition()
        else:
            scrollposition = self.init_map_position
            self.init_map_position = None

        if True:
            # array = QByteArray().append(content)
            # self.map.page().setContent(array, mimeType=str('image/svg+xml'))

            if not self.set_map_content_done:
                self.map.page().set_svg(content)
                self.set_map_content_done = True
        else:
            # self.map.setContent(content)
            self.map.page().setHtml(content)

            if isinstance(scrollposition, QtCore.QPointF):
                script_str = "window.scrollTo({0}, {1});".format(
                    scrollposition.toPoint().x(),
                    scrollposition.toPoint().y()
                )
            elif isinstance(scrollposition, QtCore.QPoint):
                script_str = "window.scrollTo({0}, {1});".format(scrollposition.x(), scrollposition.y())
            else:
                script_str = None
                log.warning('unknown object type {0}'.format(type(scrollposition)))
            # script_str = "window.scrollTop(340);"

            # log.debug('current scroll is {0}x{1}'.format(scrollposition.toPoint().x(), scrollposition.toPoint().y()))
            # log.debug(script_str)

            # self.map.page().setScrollPosition(scrollposition)
            # self.map.page().scrollPosition = scrollposition;

            self.map.page().runJavaScript(script_str)
        # time.sleep(1)
        # self.map.page().setLinkDelegationPolicy(QWebEnginePage.DelegateAllLinks)
    """

    def zoomMapIn(self):
        self.map.setZoomFactor(self.map.zoomFactor() + 0.1)

    def zoomMapOut(self):
        self.map.setZoomFactor(self.map.zoomFactor() - 0.1)

    def logfile_changed(self, path, roomname):
        messages = self.chatparser.file_modified(path, roomname)
        for message in messages:
            # if players location changed
            if message.status == states.LOCATION:
                self.known_playernames.add(message.user)
                self.set_location(message.user, message.systems[0])
            # soundtest special
            elif message.status == states.SOUNDTEST and message.user in self.known_playernames:
                words = message.message.split()
                if len(words) > 1:
                    sound.play_sound(words[1])
            # KOS request
            elif message.status == states.KOS_STATUS_REQUEST:
                text = message.message[4:]
                text = text.replace("  ", ",")
                parts = (name.strip() for name in text.split(","))
                self.trayicon.setIcon(QtGui.QIcon(resource_path("vi/ui/res/logo_small_green.png")))
                self.kos_request_thread.add_request(parts, "xxx", False)
            # if it is a 'normal' chat message
            elif message.user not in ("EVE-System", "EVE System") and message.status != states.IGNORE:
                self.add_message_to_intelchat(message)

                if message.systems:
                    for system in message.systems:
                        systemname = system.name
                        # self.dotlan.set_system_status(systemname, message.status)
                        self.map.page().set_system_status(system, message)

                        if message.status in (states.REQUEST, states.ALARM) \
                                and message.user not in self.known_playernames:
                            if message.status == states.ALARM:
                                alarm_distance = self.alarm_distance
                            else:
                                alarm_distance = 0

                            for nsystem, data in system.get_neighbours(alarm_distance).items():
                                distance = data["distance"]
                                chars = nsystem.get_located_characters()
                                if len(chars) > 0 and message.user not in chars:
                                    self.trayicon.show_notification(message, system.name, ", ".join(chars), distance)

                # self.set_map_content(self.dotlan.svg)


class Bridge(QtCore.QObject):
    js_message  = pyqtSignal(str)
    sig_message = pyqtSignal(object)

    def __init__(self):
        super(Bridge, self).__init__()

        self.bridge_ready = False
        self.message_buffer = []

    def __process_buffered(self):
        log.debug('sending buffered messages')

        for msg in self.message_buffer:
            self.js_message.emit(msg)

    @QtCore.pyqtSlot(name='bridge_ready')
    def bridge_ready(self):
        log.debug('bridge ready')
        self.bridge_ready = True
        self.__process_buffered()

    @QtCore.pyqtSlot(str, name='from_page')
    def from_page(self, msg, *args):
        # log.debug('received message from page: {0}'.format(msg))
        obj = json.loads(msg)
        self.sig_message.emit(obj)

    def to_page(self, msg, *args):
        if self.bridge_ready:
            # log.debug('sending msg into page')
            self.js_message.emit(msg)
        else:
            log.debug('buffering msg')
            self.message_buffer.append(msg)


class MainWindowPage(QWebEnginePage):
    sig_link_clicked = pyqtSignal(QUrl)

    def __init__(self):
        super(MainWindowPage, self).__init__()
        self.m_pView = QWebEngineView()
        self.m_pView.setPage(self)
        self.channel = QtWebChannel.QWebChannel(self)
        self.bridge = Bridge()
        self.bridge.sig_message.connect(self.page_event)
        self.m_pView.page().setWebChannel(self.channel)
        self.m_pView.page().profile().scripts().insert(self.__client_script('jquery-3.1.1.min'))
        self.m_pView.page().profile().scripts().insert(self.__client_script('clientscript'))
        # self.m_pView.page().profile().scripts().insert(self.__client_script('firebug-lite'))

        self.m_pView.page().setHtml(self.__client_html())
        self.channel.registerObject('VIntelAPI', self.bridge)

    def acceptNavigationRequest(self, url, nav_type, is_main):
        return False

    def javaScriptAlert(self, url, msg):
        log.debug(msg)
        # const QUrl &securityOrigin, const QString &msg

    def javaScriptConsoleMessage(self, level, message, line_num, src_id):
        log.debug('CONSOLE (line {0}): {1}'.format(line_num, message))

    @QtCore.pyqtSlot(str, str, name='set_system_status')
    def set_system_status(self, sys, msg):
        # log.debug('setting system status {0}'.format(sysname))
        if not isinstance(sys, dotlan.System):
            raise Exception('unknown system type')

        if isinstance(msg, chatparser.chatparser.Message):
            str = json.dumps({
                'type':    'status_change',
                'sysname' : sys.name,
                'sysid'   : sys.systemid,
                'status'  : msg.status
            })
        elif isinstance(msg, dict):
            str = json.dumps({
                'type':    'status_change',
                'sysname': sys.name,
                'sysid': sys.systemid,
                'status':  msg['status']
            })
        else:
            raise Exception('unknown message type')

        self.bridge.to_page(str)

    def mark_system(self, sysname):
        self.bridge.to_page(json.dumps({
            'type':    'mark_system',
            'sysname': sysname
        }))

    def mark_player(self, char, new_system):
        self.bridge.to_page(json.dumps({
            'type':    'mark_player',
            'sysname': new_system,
            'name':    char
        }))

    def set_svg(self, svg):
        log.debug('setting SVG')
        str = json.dumps({
            'type': 'load_svg',
            'data': svg
        })
        self.bridge.to_page(str)

    def page_event(self, e):
        if isinstance(e, dict):
            if 'type' in e:
                if e['type'] == 'test':
                    log.debug('event test ok')
                elif e['type'] == 'click':
                    log.debug('event click')
                    self.sig_link_clicked.emit(QUrl(e['sys_href']))
                else:
                    log.debug('event "{0}" on page!'.format(e['type']))
            else:
                raise Exception('unknown page event format')
        else:
            raise Exception('invalid page event')

    @staticmethod
    def __client_script(scriptname):
        log.debug('loading script {0}.js'.format(scriptname))
        script = QWebEngineScript()
        with open(resource_path('vi/ui/res/{0}.js'.format(scriptname))) as src_file:
            script_content = src_file.read()
        script.setSourceCode(script_content)
        script.setName(scriptname)
        script.setWorldId(QWebEngineScript.MainWorld)
        script.setInjectionPoint(QWebEngineScript.DocumentReady)
        script.setRunsOnSubFrames(True)
        return script

    @staticmethod
    def __client_html():
        return '''
<!DOCTYPE html>
<html>
<head>
    <!-- <script type="text/javascript" src="https://getfirebug.com/firebug-lite.js#disableXHRListener=true,overrideConsole=false,startOpened=true"></script> -->
    <script type="text/javascript" src="qrc:///qtwebchannel/qwebchannel.js"></script>
    <style type="text/css">
        .sys .so, .sys .er { display: none; }
        .stopwatch .so, .stopwatch .er { display: block; }
    </style>
</head>
<body>
<div id="svg_container"></div>
</body></html>'''


class ChatroomsChooser(QDialog):
    rooms_changed = pyqtSignal(object)
    
    def __init__(self, parent):
        QDialog.__init__(self, parent)
        uic.loadUi(resource_path("vi/ui/ChatroomsChooser.ui"), self)
        self.default_button.clicked.connect(self.set_defaults)
        self.cancel_button .clicked.connect(self.accept)
        self.save_button   .clicked.connect(self.save_clicked)
        cache = Cache()
        roomnames = cache.get_from_cache("roomnames")
        if not roomnames:
            roomnames = u"TheCitadel, North Provi Intel"
        self.roomnames_field.setPlainText(roomnames)
        
    def save_clicked(self):
        text = str(self.roomnames_field.toPlainText())
        rooms = [str(name.strip()) for name in text.split(",")]
        self.rooms_changed.emit(rooms)
        self.accept()
        
    def set_defaults(self):
        self.roomnames_field.setPlainText(u"TheCitadel,North Provi Intel")
        
        
class RegionChooser(QDialog):
    
    def __init__(self, parent):
        QDialog.__init__(self, parent)
        uic.loadUi(resource_path("vi/ui/RegionChooser.ui"), self)
        self.default_button.clicked.connect(self.set_defaults)
        self.cancel_button.clicked.connect(self.accept)
        self.save_button.clicked.connect(self.save_clicked)
        cache = Cache()
        regionname = cache.get_from_cache("regionname")
        if not regionname:
            regionname = u"Providence"
        self.regionname_field.setPlainText(regionname)
        
    def save_clicked(self):
        text = str(self.regionname_field.toPlainText())
        text = dotlan.convert_regionname(text)
        self.regionname_field.setPlainText(text)
        correct = False
        try:
            url = dotlan.Map.DOTLAN_BASIC_URL.format(text)
            content = requests.get(url).text
            # request = urllib.request.urlopen(url)
            # content = request.read()
            if u"not found" in content:
                correct = False
                # Fallback -> ships vintel with this map?
                try:
                    with open(resource_path("vi/ui/res/mapdata/{0}.svg".format(text))) as _:
                        correct = True
                except Exception as e:
                    print(str(e))
                    correct = False
                if not correct:
                    QMessageBox.warning(None, u"No such region!", u"I can't find a region called '{0}'".format(text), QMessageBox.Ok)
            else:
                correct = True
        except Exception as e:
            QMessageBox.critical(None, u"Something went wrong!", u"Error while testing existing '{0}'".format(str(e)), QMessageBox.Ok)
            correct = False
        if correct:
            c = Cache()
            c.put_into_cache("regionname", text, 60*60*24*365)
            QMessageBox.information(None, u"VINTEL needs restart", u"Region was changed, you need to restart VINTEL!", QMessageBox.Ok)
            self.accept()
        
    def set_defaults(self):
        self.regionname_field.setPlainText(u"Providence")
        
        
class SystemChat(QDialog):
    sig_location_set = pyqtSignal(str, str)

    SYSTEM = 0
    
    def __init__(self, parent, chat_type, selector, chatentries, known_playernames):
        QDialog.__init__(self, parent)
        uic.loadUi(resource_path("vi/ui/SystemChat.ui"), self)
        self.parent = parent
        self.chat_type = 0
        self.selector = selector

        self.chatentries = []
        for entry in chatentries:
            self.add_chatentry(entry)

        titlename = ""
        if self.chat_type == SystemChat.SYSTEM:
            titlename = self.selector.name
            self.system = selector
        self.setWindowTitle("Chat for {0}".format(titlename))

        for name in known_playernames:
            self.playernames_box.addItem(name)

        self.close_button   .clicked.connect(self.close_dialog)
        self.alarm_button   .clicked.connect(self.set_system_alarm)
        self.clear_button   .clicked.connect(self.set_system_clear)
        self.location_button.clicked.connect(self.location_set)

    def _add_message_to_chat(self, message, avatar_pixmap):
        scroll_to_bottom = False
        if (self.chat.verticalScrollBar().value() ==
            self.chat.verticalScrollBar().maximum()):
            scroll_to_bottom = True
        entry = ChatEntry(message)
        entry.avatar_label.setPixmap(avatar_pixmap)
        listWidgetItem = QtWidgets.QListWidgetItem(self.chat)
        listWidgetItem.setSizeHint(entry.sizeHint())
        self.chat.addItem(listWidgetItem)
        self.chat.setItemWidget(listWidgetItem, entry)
        self.chatentries.append(entry)
        entry.mark_system.connect(self.parent.mark_system_on_map)
        if scroll_to_bottom:
            self.chat.scrollToBottom()

    def add_chatentry(self, entry):
        if self.chat_type == SystemChat.SYSTEM:
            message = entry.message
            avatar_pixmap = entry.avatar_label.pixmap()
            if self.selector in message.systems:
                self._add_message_to_chat(message, avatar_pixmap)

    def location_set(self):
        char = str(self.playernames_box.currentText())
        self.sig_location_set.emit(char, self.system.name)

    def new_avatar_available(self, charname, avatar_data):
        for entry in self.chatentries:
            if entry.message.user == charname:
                entry.update_avatar(avatar_data)
        
    def set_system_alarm(self):
        # self.system.set_status(states.ALARM)
        # self.parent.update_map()
        # self.parent.dotlan.system_status_changed(self.system.name, states.ALARM)
        self.parent.map.page().set_system_status(self.system, { 'status' : states.ALARM })
            
    def set_system_clear(self):
        # self.system.set_status(states.CLEAR)
        # self.parent.update_map()
        # self.parent.dotlan.system_status_changed(self.system.name, states.CLEAR)
        self.parent.map.page().set_system_status(self.system, { 'status' : states.CLEAR })
          
    def close_dialog(self):
        self.accept()
        

class ChatEntry(QWidget):
    mark_system = pyqtSignal(str)

    TEXTSIZE = 9
    SHOW_AVATAR = True

    def __init__(self, message):
        QWidget.__init__(self)
        uic.loadUi(resource_path("vi/ui/ChatEntry.ui"), self)
        self.avatar_label.setPixmap(QtGui.QPixmap(resource_path("vi/ui/res/qmark.png")))
        self.message = message
        self.update_text()
        self.text_label.linkActivated.connect(self.link_clicked)
        self.change_fontsize(self.TEXTSIZE)
        if not ChatEntry.SHOW_AVATAR:
            self.avatar_label.setVisible(False)
    
    def link_clicked(self, link):
        link = str(link)
        function, parameter = link.split("/", 1)
        if function == "mark_system":
            self.mark_system.emit(parameter)
        if function == "link":
            webbrowser.open(parameter)

    def update_text(self):
        time = datetime.datetime.strftime(self.message.timestamp, "%H:%M:%S")
        text = u"<small>{time} - <b>{user}</b> - <i>{room}</i></small><br>{text}".format(
            user=self.message.user,
            room=self.message.room,
            time=time,
            text=self.message.message
        )
        self.text_label.setText(text)

    def update_avatar(self, avatar_data):
        image = QImage.fromData(avatar_data)
        pixmap = QPixmap.fromImage(image)
        if pixmap.isNull():
            return False
        scaled_avatar = pixmap.scaled(32, 32)
        self.avatar_label.setPixmap(scaled_avatar)
        return True

    def change_fontsize(self, new_size):
        font = self.text_label.font()
        font.setPointSize(new_size)
        self.text_label.setFont(font)


class JumpBridgeChooser(QDialog):
    set_jb_url = pyqtSignal(str)

    def __init__(self, parent, url):
        QDialog.__init__(self, parent)
        uic.loadUi(resource_path("vi/ui/JumpbridgeChooser.ui"), self)
        self.save_button.clicked.connect(self.save_path)
        self.cancel_button.clicked.connect(self.accept)
        self.url_field.setText(url)
        # loading format explanation from textfile
        with open(resource_path("docs/jumpbridgeformat.txt")) as f:
            self.format_info_field.setPlainText(f.read())
        
    def save_path(self):
        try:
            url = str(self.url_field.text())
            if url != "":
                req = requests.get(url)
                req.raise_for_status()
            self.set_jb_url.emit(url)
            self.accept()
        except Exception as e:
            QMessageBox.critical(None, "Finding Jumpbridgedata failed", "Error: {0}".format(str(e)), QMessageBox.Ok)
