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

import sqlite3
import threading
import time

from vi.cache.dbstructure import update_database


class Cache(object):

    # Cache checks PATH_TO_CACHE when init, so you can set this on a
    # central place for all Cache instances.
    PATH_TO_CACHE = None

    # Ok, this is dirty. To make sure we check the database only
    # one time/runtime we will change this classvariable after the
    # check. Following inits of Cache will now, that we allready checked.
    VERSION_CHECKED = False

    # Cache-Instances in various threads: must handle concurrent writings
    SQLITE_WRITE_LOCK = threading.Lock()

    def __init__(self, db="cache.sqlite3"):
        """ db=path to sqlite-file to save the cache.
               will be ignored if you set Cache.PATH_TO_CACHE before init"""
        if Cache.PATH_TO_CACHE:
            db = Cache.PATH_TO_CACHE
        self.con = sqlite3.connect(db)
        if not Cache.VERSION_CHECKED:
            with Cache.SQLITE_WRITE_LOCK:
                self.check_version()
        Cache.VERSION_CHECKED = True

    def check_version(self):
        query = "SELECT version FROM version;"
        version = 0
        try:
            version = self.con.execute(query).fetchall()[0][0]
        except Exception as e:
            if isinstance(e, sqlite3.OperationalError) and "no such table: version" in str(e):
                pass
            elif isinstance(e, IndexError):
                pass
            else:
                raise e
        update_database(version, self.con)

    def put_into_cache(self, key, value, max_age=60*60*24*3):
        """ Putting something in the cache
            max_age is maximum age in soconds"""
        with Cache.SQLITE_WRITE_LOCK:
            query = "DELETE FROM cache WHERE key = ?"
            self.con.execute(query, (key,))
            query = """INSERT INTO cache (key, data, modified, maxage)
                       VALUES (?, ?, ?, ?)"""
            self.con.execute(query, (key, value, time.time(), max_age))
            self.con.commit()

    def get_from_cache(self, key, outdated=False):
        """ Getting a value from cache 
            key = the key for the value
            outdated = returns the value also if it is outdated"""
        query = "SELECT key, data, modified, maxage FROM cache WHERE key = ?"
        founds = self.con.execute(query, (key,)).fetchall()
        if len(founds) == 0:
            return None
        elif founds[0][2] + founds[0][3] < time.time() and not outdated:
            return None
        else:
            return founds[0][1]

    def put_playername(self, name, status):
        """ Putting a playername into the cache """
        with Cache.SQLITE_WRITE_LOCK:
            query = "DELETE FROM playernames WHERE charname = ?"
            self.con.execute(query, (name,))
            query = """INSERT INTO playernames (charname, status, modified)
                    VALUES (?, ?, ?)"""
            self.con.execute(query, (name, status, time.time()))
            self.con.commit()

    def get_playername(self, name):
        """ Getting back infos about playername from Cache.
            Returns None if the name was not found, else it
            returns the status"""
        selectquery = """SELECT charname, status FROM playernames
                         WHERE charname = ?"""
        founds = self.con.execute(selectquery, (name,)).fetchall()
        if len(founds) == 0:
            return None
        else:
            return founds[0][1]

    def put_avatar(self, name, data):
        """ Put the picture of an player into the cache"""
        with Cache.SQLITE_WRITE_LOCK:
            # data is a blob, so we have to change it to buffer
            # data = buffer(str(data))

            query = "DELETE FROM avatars WHERE charname = ?"
            self.con.execute(query, (name,))
            query = """INSERT INTO avatars (charname, data, modified)
                    VALUES (?, ?, ?)"""
            self.con.execute(query, (name, str(data), time.time()))
            self.con.commit()
        
    def get_avatar(self, name):
        """ Getting the avatars_pictures data from the Cache.
            Returns None if there is no entry in the cache"""
        selectquery = """SELECT data FROM avatars
                         WHERE charname = ?"""
        founds = self.con.execute(selectquery, (name,)).fetchall()
        if len(founds) == 0:
            return None
        else:
            # dats is buffer, we convert it back to str
            data = str(founds[0][0])
            return data

    def remove_avatar(self, name):
        """ Removing an avatar from the cache"""
        with Cache.SQLITE_WRITE_LOCK:
            query = "DELETE FROM avatars WHERE charname = ?"
            self.con.execute(query, (name,))
            self.con.commit()
