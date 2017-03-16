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
import os
import time
import logging
from bs4 import BeautifulSoup
from vi.chatparser.parser_functions import parse_urls, parse_ships, parse_systems, parse_status
from vi import states

# Names the local chatlogs could start with (depends on l10n of the client)
LOCAL_NAMES = ("Lokal", "Local")

log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)


class ChatParser(object):
    """ ChatParser will analyze every new line, that was found inside
    the Chatlogs."""

    def __init__(self, path, rooms, systems):
        """ path = the path with the logs
            rooms = the rooms to parse"""
        self.path = path          # the path with the chatlog
        self.rooms = rooms        # the rooms to watch (excl. local)
        self.systems = systems    # the known systems as dict name: system
        self.file_data = {}       # informations about the files in the directory
        self.known_messages = []  # message we allready analyzed
        self.locations = {}       # informations about the location of a char
        self.ignored_pathes = []
        self._collect_init_filedata(path)

    def _collect_init_filedata(self, path):
        current_time = time.time()
        max_diff = 60*60*24  # what is 1 day in seconds
        for fname in os.listdir(path):
            full_path = os.path.join(path, fname)
            file_time = os.path.getmtime(full_path)
            if current_time - file_time < max_diff:
                self.add_file(full_path)
    
    def add_file(self, path):
        # lines = None
        # content = ""
        filename = os.path.basename(path)
        roomname = filename[:-20]
        with open(path, "r", encoding="utf-16-le") as f:
            lines = f.readlines()

        if path not in self.file_data or (roomname in LOCAL_NAMES and "charname" not in self.file_data.get(path, [])):
            self.file_data[path] = {}
            if roomname in LOCAL_NAMES:
                charname = None
                sessionstart = None  
                # for local-chats we need more infos
                for line in lines:
                    if "Listener:" in line:
                        charname = line[line.find(":")+1:].strip()
                    elif "Session started:" in line:
                        sessionstr = line[line.find(":")+1:].strip()
                        sessionstart = datetime.datetime.strptime(sessionstr, "%Y.%m.%d %H:%M:%S")
                    if charname and sessionstart:
                        self.file_data[path]["charname"] = charname
                        self.file_data[path]["sessionstart"] = sessionstart
                        break
        self.file_data[path]["lines"] = len(lines)
        return lines

    def _line_to_message(self, line, roomname):
        # finding the timestamp
        timestart = line.find("[") + 1
        timeends = line.find("]")
        timestr = line[timestart:timeends].strip()
        try:
            timestamp = datetime.datetime.strptime(timestr, "%Y.%m.%d %H:%M:%S")
        except ValueError:
            return None
        # finding the username of the poster
        userends = line.find(">")
        username = line[timeends+1:userends].strip()
        # finding the pure message
        text = line[userends+1:].strip()  # text will the text to work an
        original_text = text
        formated_text = u"<rtext>{0}</rtext>".format(text)
        soup = BeautifulSoup(formated_text, "html.parser")
        rtext = soup.select("rtext")[0]
        systems = set()
        utext = text.upper()
        # KOS request
        if utext.startswith("XXX "):
            return Message(roomname, text, timestamp, username, systems, utext, status=states.KOS_STATUS_REQUEST)
        elif utext.startswith("VINTELSOUNDTEST"):
            return Message(roomname, text, timestamp, username, systems, utext, status=states.SOUNDTEST)

        # and now creating message object
        message = Message(roomname, "", timestamp, username, systems, text, original_text)

        # is the message allready here? may happen if someone plays > 1 account
        if message in self.known_messages:
            message.status = states.IGNORE
            return message

        # and going on with parsing
        remove_chars = ("*", "?", ",", "!")
        for char in remove_chars:
            text = text.replace(char, "")

        # ships in the message?
        run = True
        while run:
            run = parse_ships(rtext)

        # urls in the message?
        run = True
        while run:
            run = parse_urls(rtext)

        # trying to find the system in the text
        run = True
        while run:
            run = parse_systems(self.systems, rtext, systems)

        # and the status
        parsed_status = parse_status(rtext)
        if parsed_status is not None:
            status = parsed_status
        else:
            status = states.ALARM

        # if message says clear and no system? Maybe an answer to a request?
        if status == states.CLEAR and not systems:
            max_search = 2  # we search only max_search messages in the room
            for count, old_message in \
                    enumerate(old_message for old_message in self.known_messages[-1::-1] if
                              old_message.room == roomname):
                if old_message.systems and old_message.status == states.REQUEST:
                    for system in old_message.systems:
                        systems.add(system)
                    break
                if count > max_search:
                    break

        message.message = str(rtext)
        message.status = status
        self.known_messages.append(message)

        if systems:
            for system in systems:
                system.messages.append(message)

        return message 

    def _parse_local(self, path, line):
        message = []
        """ Parsing a line from the local chat. Can contain the system
        of the char"""
        charname = self.file_data[path]["charname"]
        if charname not in self.locations:
            self.locations[charname] = {"system": "?", "timestamp": datetime.datetime(1970, 1, 1, 0, 0, 0, 0)}
        # finding the timestamp
        timestart = line.find("[") + 1
        timeends = line.find("]")
        timestr = line[timestart:timeends].strip()
        timestamp = datetime.datetime.strptime(timestr, "%Y.%m.%d %H:%M:%S")
        # finding the username of the poster
        userends = line.find(">")
        username = line[timeends+1:userends].strip()
        # finding the pure message
        text = line[userends+1:].strip()  # text will the text to work an
        if username in ("EVE-System", "EVE System"):
            if ":" in text:
                system = text.split(":")[1].strip().replace("*", "").upper()
            else:
                system = "?"
            if timestamp > self.locations[charname]["timestamp"]:
                self.locations[charname]["system"] = system
                self.locations[charname]["timestamp"] = timestamp
                message = Message("", "", timestamp, charname, [system, ], "", status=states.LOCATION)
        return message

    def file_modified(self, path, roomname):
        messages = []
        filename = os.path.basename(path)

        if roomname not in self.rooms and roomname not in LOCAL_NAMES:
            self.ignored_pathes.append(filename)

        if filename in self.ignored_pathes:
            # log.debug('file {0} is ignored'.format(filename))
            return messages

        # checking if we must do anything with the changed file.
        # we are only need those, which name is in the rooms-list
        # EvE names the file like room_20140913_200737.txt, so we don't need
        # the last 20 chars
        if path not in self.file_data:
            # seems eve created a new file. New Files have 12 lines header
            self.file_data[path] = {"lines": 13}

        old_length = self.file_data[path]["lines"]
        lines = self.add_file(path)

        for line in lines[old_length-1:]:
            line = line.strip()
            if len(line) > 2:
                if roomname in LOCAL_NAMES:
                    message = self._parse_local(path, line)
                else:
                    message = self._line_to_message(line, roomname)

                if message:
                    messages.append(message)
        return messages


class Message(object):
   
    def __init__(self, room, message, timestamp, user, systems, utext, plain_text="", status=states.ALARM):
        self.room = room              # chatroom the message was posted
        self.message = message        # the messages text
        self.timestamp = timestamp    # time stamp of the massage
        self.user = user              # user who posted the message
        self.systems = systems        # list of systems mentioned in the message
        self.status = status          # status related to the message
        self.utext = utext            # the text in UPPER CASE
        self.plain_text = plain_text  # plain text of the message, as posted
        # if you add the message to a widget, please add it to widgets
        self.widgets = []

    def __key(self):
        return self.room, self.plain_text, self.timestamp, self.user

    def __eq__(x, y):
        return x.__key() == y.__key()

    def __hash__(self):
        return hash(self.__key())
