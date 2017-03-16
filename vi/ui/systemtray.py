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

import time

from PyQt5 import QtGui, QtWidgets
from PyQt5.QtCore import pyqtSignal
# from PyQt5.QtWidgets import QSystemTrayIcon, QMenu

from vi.resources import resource_path
from vi import sound, states


class TrayContextMenu(QtWidgets.QMenu):
    INSTANCES = set()
    
    def __init__(self, trayicon):
        """ trayicon = the object with the methods to call"""
        QtWidgets.QMenu.__init__(self)
        TrayContextMenu.INSTANCES.add(self)
        self.trayicon = trayicon
        self._build_menu()
        
    def _build_menu(self):
        self.frameless_check = QtWidgets.QAction("Frameless Window",                  self, checkable = True)
        self.request_check   = QtWidgets.QAction("Show status request notifications", self, checkable = True)
        self.alarm_check     = QtWidgets.QAction("Show alarm notifications",          self, checkable = True)
        self.action_quit     = QtWidgets.QAction("Quit",                              self)

        self.request_check.setChecked(True)
        self.alarm_check.setChecked(True)

        self.frameless_check.triggered.connect(self.trayicon.change_frameless)
        self.request_check  .triggered.connect(self.trayicon.switch_request)
        self.alarm_check    .triggered.connect(self.trayicon.switch_alarm)
        self.action_quit    .triggered.connect(self.trayicon.quit)

        # self.connect(self.frameless_check, QtCore.SIGNAL("triggered()"), self.trayicon.change_frameless)
        # self.connect(self.request_check,   QtCore.SIGNAL("triggered()"), self.trayicon.switch_request)
        # self.connect(self.alarm_check,     QtCore.SIGNAL("triggered()"), self.trayicon.switch_alarm)
        # self.connect(self.action_quit,     QtCore.SIGNAL("triggered()"), self.trayicon.quit)

        distance_menu = self.addMenu("Alarm Distance")
        self.distance_group = QtWidgets.QActionGroup(self)
        for i in range(0, 6):
            action = QtWidgets.QAction("{0} Jumps".format(i), None, checkable = True)

            if i == 0:
                action.setChecked(True)

            action.alarm_distance_value = i
            action.triggered.connect(self.change_alarm_distance)
            # self.connect(action, QtCore.SIGNAL("triggered()"), self.change_alarm_distance)
            self.distance_group.addAction(action)
            distance_menu.addAction(action)

        self.addAction(self.frameless_check)
        self.addSeparator()
        self.addAction(self.request_check)
        self.addAction(self.alarm_check)
        self.addMenu(distance_menu)
        self.addSeparator()
        self.addAction(self.action_quit)
        
    def change_alarm_distance(self):
        for action in self.distance_group.actions():
            if action.isChecked():
                self.trayicon.alarm_distance_value = action.alarm_distance_value
                self.trayicon.change_alarm_distance()
                break


class TrayIcon(QtWidgets.QSystemTrayIcon):
    sig_alarm_distance   = pyqtSignal(int)
    sig_change_frameless = pyqtSignal()
    sig_quit             = pyqtSignal()

    # Min seconds between tow notifications
    MIN_WAIT_NOTIFICATION = 15
  
    def __init__(self, app):
        self.icon = QtGui.QIcon(resource_path("vi/ui/res/logo_small.png"))
        QtWidgets.QSystemTrayIcon.__init__(self, self.icon, app)
        self.setToolTip("Your Vintel-Information-Service! :)")
        self.last_notifications = {}
        self.setContextMenu(TrayContextMenu(self))
        self.show_alarm = True
        self.show_request = True
        self.alarm_distance_value = 0

    def change_alarm_distance(self):
        distance = self.alarm_distance_value
        # self.emit(Qt.SIGNAL("alarm_distance"), distance)
        self.sig_alarm_distance.emit(distance)
        
    def change_frameless(self):
        # self.emit(Qt.SIGNAL("change_frameless"))
        self.sig_change_frameless.emit()
        
    @property
    def distance_group(self):
        return self.contextMenu().distance_group

    def quit(self):
        # self.emit(Qt.SIGNAL("quit"))
        self.quit_signal.emit()

    def switch_alarm(self):
        new_value = not self.show_alarm
        for cm in TrayContextMenu.INSTANCES:
            cm.alarm_check.setChecked(new_value)
        self.show_alarm = new_value

    def switch_request(self):
        new_value = not self.show_request
        for cm in TrayContextMenu.INSTANCES:
            cm.request_check.setChecked(new_value)
        self.show_request = new_value

    def show_notification(self, message, system, char, distance):
        room = message.room
        title = None
        text = None
        icon = None
        text = ""
        if (message.status == states.ALARM and self.show_alarm 
            and self.last_notifications.get(states.ALARM, 0)
                < time.time() - self.MIN_WAIT_NOTIFICATION):
            title = "ALARM!"
            text = (u"{system} was alarmed in {room}. "
                    u"Chars {distance} jumps out: {char}\n"
                    u"Text: {message_text}")
            icon = 2
            message_text = message.plain_text
            self.last_notifications[states.ALARM] = time.time()
            sound.play_sound("alarm")
        elif (message.status == states.REQUEST and self.show_request
              and self.last_notifications.get(states.REQUEST, 0)
                < time.time() - self.MIN_WAIT_NOTIFICATION):
            title = "Status request"
            icon = 1
            text = (u"Someone is requesting status of {system} in {room}. " 
                    u"(Your chars there: {char})")
            self.last_notifications[states.REQUEST] = time.time()
            sound.play_sound("request")
        if title and text and icon:
            text = text.format(**locals())
            self.showMessage(title, text, icon)
