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

import urllib
import json

from PyQt5 import Qt
from PyQt5.QtCore import QThread, pyqtSignal
from bs4 import BeautifulSoup

from vi.cache.cache import Cache
from vi import version


def get_jumpbridge_data(region):
    cachekey = "jb_" + region
    try:
        cache = Cache()
        data = cache.get_from_cache(cachekey)
        if data:
            data = json.loads(data)
        else:
            data = []
            url = "http://yophant.ru/vintel/{region}_jb.txt"
            # request = urllib2.urlopen(url.format(region=region))
            # content = request.read()
            content = urllib.request.urlopen(url.format(region=region), data=None)
            for line in content.split("\n"):
                splits = line.strip().split()
                if len(splits) == 3:
                    data.append(splits)
            cache.put_into_cache(cachekey, json.dumps(data), 60*60*24)
        return data
    except Exception as e:
        print("Getting Jumpbridgedata failed with: {0}".format(str(e)))
        return []
        
        
        
def get_newest_version():
    try:
        url = "http://yophant.ru/vintel/version.html"
        # request = urllib2.urlopen(url)
        # content = request.read()
        content = urllib.request.urlopen(url, data=None)
        soup = BeautifulSoup(content, "html.parser")
        newest_version = soup.select("#version")[0].text
        ret = float(newest_version)
        return ret
    except Exception as e:
        print("Failed version-request: {0}".format(str(e)))
        return 0.0


class NotifyNewVersionThread(QThread):
    newer_version = pyqtSignal()

    def __init__(self):
        QThread.__init__(self)

    def run(self):
        # is there a newer version available?
        newest_version = float(get_newest_version())
        if newest_version and newest_version > float(version.VERSION):
            # self.emit(Qt.SIGNAL("newer_version"), newest_version)
            self.newer_version.emit(newest_version)