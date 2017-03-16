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

###########################################################################
# Little lib and tool to get the map and information from dotlan          #
###########################################################################

import math
import time
import requests
import logging
import re

import bs4
from bs4 import BeautifulSoup

from vi.cache.cache import Cache
from vi import states
import vi.drachenjaeger
import vi.evegate
# from PyQt5 import QtCore
# from PyQt5.QtCore import QObject, pyqtSignal

log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)


JB_COLORS = ("800000", "808000", "008080", "ff00ff", "c83737",
             "ff6600", "917c6f", "ffcc00", "88aa00")


class DotlanException(Exception):
    
    def __init__(self, *args, **kwargs):
        Exception.__init__(self, *args, **kwargs)


class Map(object):
    # sig_map_ready = pyqtSignal(str)

    """ The map incl. all informations from dotlan"""

    DOTLAN_BASIC_URL = "http://evemaps.dotlan.net/svg/{0}.svg"

    @property
    def svg(self):
        # rerender all systems
        for system in self.systems.values():
            system.update()

        # update the marker
        if not self.marker["opacity"] == "0":
            now = time.time()
            new_value = (1 - (now - float(self.marker["activated"]))/10)
            if new_value < 0:
                new_value = "0"
            self.marker["opacity"] = new_value

        return str(self.soup)

    def __init__(self, region, svg_file=None):
        # QObject.__init__(self)

        self.region = region
        cache = Cache()
        self.outdated_cache_error = None
        if not svg_file:
            # want map from dotlan. Is it in the cache?
            svg = cache.get_from_cache("map_" + self.region)
        else:
            svg = svg_file
        if not svg:
            try:
                svg = self._get_svg_from_dotlan(self.region)
                cache.put_into_cache("map_" + self.region, svg, vi.evegate.seconds_till_downtime() + 60*60)
            except Exception as e:
                self.outdated_cache_error = e
                svg = cache.get_from_cache("map_" + self.region, True)
                if not svg:
                    t = "No Map in cache, nothing from dotlan. Must give up "\
                        "because this happened:\n{0} {1}\n\nThis could be a "\
                        "temporary problem (like dotlan is not reachable), or "\
                        "everythig went to hell. Sorry. This makes no sense "\
                        "without the map.\n\nRemember the site for possible "\
                        "updates: http://drachenjaeger.eu/vintel/vintel.html"\
                        .format(type(e), str(e))
                    raise DotlanException(t)
        # and now creating soup from the svg
        # self.soup = BeautifulSoup(svg, "html.parser")
        self.soup = BeautifulSoup(svg, "xml")
        self.systems = self._extract_systems_from_soup(self.soup)
        self.systems_by_id = {}
        for system in self.systems.values():
            self.systems_by_id[system.systemid] = system
        self._preparing_svg(self.soup, self.systems)
        self._connect_neighbours()
        self._jumpmaps_visible = False
        self._statistics_visible = False
        self.marker = self.soup.select("#select_marker")[0]

    def set_system_status(self, sysname, status):
        self.systems[sysname].set_status(status)
        log.debug('sig_status_changed: {0} {1}'.format(sysname, status))
        # self.sig_system_status_changed.emit(sysname, status)
        
    def change_jumpbrigde_visibility(self):
        new_status = False if self._jumpmaps_visible else True
        value = "visible" if new_status else "hidden"
        for line in self.soup.select(".jumpbridge"):
            line["visibility"] = value
        self._jumpmaps_visible = new_status

    def change_statistics_visibility(self):
        new_status = False if self._statistics_visible else True
        value = "visible" if new_status else "hidden"
        for line in self.soup.select(".statistics"):
            line["visibility"] = value
        self._statistics_visible = new_status

    def _extract_systems_from_soup(self, soup):
        systems = {}
        uses = {}
        for use in soup.select("use"):
            useid = use["xlink:href"][1:]
            uses[useid] = use
        symbols = soup.select("symbol")
        for symbol in symbols:
            symbolid = symbol["id"]
            systemid = symbolid[3:]

            if not systemid.isdigit():
                log.debug('not digits in "{0}"'.format(systemid))
                continue

            # for element in symbol.select(".sys"):
            for element in symbol.find_all(class_=re.compile('^sys\s')):
                name = element.select("text")[0].text.strip().upper()
                # element['href'] = 'vintel://go_system/{0}'.format(name)
                # element['onclick'] = 'alert("check")'
                element['data-systemname'] = name
                element['data-systemid'] = systemid
                del element['target']

                map_coordinates = {}
                for keyname in ("x", "y", "width", "height"):
                    map_coordinates[keyname] = float(uses[symbolid][keyname])
                map_coordinates["center_x"] = (map_coordinates["x"] + (map_coordinates["width"] / 2))
                map_coordinates["center_y"] = (map_coordinates["y"] + (map_coordinates["height"] / 2))

                # log.debug('parsed new system: {0}'.format(name))
                systems[name] = System(name, element, self.soup, map_coordinates, systemid)

        return systems

    # @QtCore.pyqtSlot(str, str, name='system_status_changed')
    # def system_status_changed(self, sysname, newstatus):
    #    self.sig_system_status_changed.emit(sysname, newstatus)

    def _connect_neighbours(self):
        """This will find all neigbours of the systems and connect them.
           It takes a look to all the jumps on the map and get the system under
           which the line ends"""
        for jump in self.soup.select("#jumps")[0].select(".j"):
            if "jumpbridge" in jump["class"]: continue
            parts = jump["id"].split("-")
            if parts[0] == "j":
                start_system = self.systems_by_id[parts[1]]
                stop_system = self.systems_by_id[parts[2]]
                start_system.add_neighbour(stop_system)

    def _get_svg_from_dotlan(self, region):
        url = self.DOTLAN_BASIC_URL.format(region)
        # request = urllib.Request(url)
        # content = urllib.urlopen(request).read()
        # content = urllib.request.urlopen(url, data=None)
        req = requests.get(url)
        req.raise_for_status()

        return req.text
    
    def add_system_statistics(self, statistics):
        if statistics is not None:
            for systemid, system in self.systems_by_id.items():
                if systemid in statistics:
                    system.set_statistics(statistics[systemid])
        else:
            for system in self.systems_by_id.values():
                system.set_statistics(None)
                
    def set_jumpbridges(self, jumpbridge_data):
        """ adding the jumpbridges to the map 
            format of data: tuples with 3 values (sys1, connection, sys2)"""
        soup = self.soup
        for bridge in soup.select(".jumpbridge"):
            bridge.decompose()
        jumps = soup.select("#jumps")[0]
        color_count = 0
        for bridge in jumpbridge_data:
            if color_count > len(JB_COLORS) - 1:
                color_count = 0
            jb_color = JB_COLORS[color_count]
            start = bridge[0]
            linetype = bridge[1]
            stop = bridge[2]
            if not (start in self.systems and stop in self.systems):
                continue
            self.systems[start].set_jumpbridge_color(jb_color)
            self.systems[stop].set_jumpbridge_color(jb_color)
            a_coords = self.systems[start].map_coordinates
            b_coords = self.systems[stop].map_coordinates
            line = soup.new_tag("line", x1=a_coords["center_x"],
                       y1=a_coords["center_y"], x2=b_coords["center_x"],
                       y2=b_coords["center_y"], visibility="hidden",
                       style="stroke:#{0}".format(jb_color))
            line["stroke-width"] = 2
            line["class"] = ["jumpbridge",]
            if "<" in linetype:
                line["marker-start"] = "url(#arrowstart_{0})".format(jb_color)
            if ">" in linetype:
                line["marker-end"] = "url(#arrowend_{0})".format(jb_color)
            jumps.insert(0, line)
            color_count += 1
    
    def _preparing_svg(self, soup, systems):
        for e in self.soup:
            if isinstance(e, bs4.element.ProcessingInstruction) or isinstance(e, bs4.element.Doctype):
                e.extract()
                break

        for elm in self.soup.find_all('script'):
            elm.extract()

        svg = soup.select("svg")[0]
        # svg["onmousedown"] = "return false;"
        del svg["onmousedown"]
        del svg["onload"]

        # qrc:///qtwebchannel/qwebchannel.js
        # http://doc.qt.io/qt-5/qtwebchannel-javascript.html

        soup.select('#controls')[0].extract()

        # making all jumps black
        for line in soup.select("line"):
            line["class"] = "j"

        # the marker we use for marking a selected system
        group = soup.new_tag("g", id="select_marker", opacity="0", activated="0", transform="translate(-10000, -10000)")
        ellipse = soup.new_tag("ellipse", cx="0", cy="0", rx="56", ry="28", style="fill:#462CFF")
        group.append(ellipse)
        coords = ((0, -10000), (-10000, 0), (10000, 0), (0, 10000))
        for coord in coords:
            line = soup.new_tag("line", x1=coord[0], y1=coord[1], x2="0", y2="0", style="stroke:#462CFF")
            group.append(line)
        svg.insert(0, group)

        # marker for jumpbridges
        for jb_color in JB_COLORS:
            startpath = soup.new_tag("path", d="M 10 0 L 10 10 L 0 5 z")
            startmarker = soup.new_tag("marker", viewBox="0 0 20 20",
                id="arrowstart_{0}".format(jb_color),
                markerUnits="strokeWidth", markerWidth="20", markerHeight="15",
                refx="-15", refy="5", orient="auto",
                style="stroke:#{0};fill:#{0}".format(jb_color))
            startmarker.append(startpath)
            svg.insert(0, startmarker)
            endpath = soup.new_tag("path", d="M 0 0 L 10 5 L 0 10 z")
            endmarker = soup.new_tag("marker", viewBox="0 0 20 20",
                id="arrowend_{0}".format(jb_color),
                markerUnits="strokeWidth", markerWidth="20", markerHeight="15",
                refx="25", refy="5", orient="auto",
                style="stroke:#{0};fill:#{0}".format(jb_color))
            endmarker.append(endpath)
            svg.insert(0, endmarker)

        jumps = soup.select("#jumps")[0]
        for systemid, system in self.systems_by_id.items():
            coords = system.map_coordinates
            # stats = system.statistics
            text = "stats n/a"
            style = "text-anchor:middle;font-size:7;font-family:Arial;"
            svgtext = soup.new_tag("text", x=coords["center_x"], 
                                y=coords["y"] + coords["height"] + 7,
                                fill="blue", style=style,
                                visibility="hidden")
            svgtext["id"] = "stats_" +  str(systemid)
            svgtext["class"] = ["statistics",]
            svgtext.string = text
            jumps.append(svgtext)


class System(object):
    # sig_status_changed = pyqtSignal(str, str)
    """ A System in the Map """

    ALARM_COLORS = [
        (60*4,     "#FF0000", "#FFFFFF"),
        (60*10,    "#FF9B0F", "#FFFFFF"),
        (60*15,    "#FFFA0F", "#000000"),
        (60*25,    "#FFFDA2", "#000000"),
        (60*60*24, "#FFFFFF", "#000000")
    ]
    ALARM_COLOR   = ALARM_COLORS[0][1]
    UNKNOWN_COLOR = "#FFFFFF"
    CLEAR_COLOR   = "#59FF6C"

    def __init__(self, name, svg_element, mapsoup, map_coordinates, systemid):
        self.status      = states.UNKNOWN
        self.name        = name
        self.svg_element = svg_element
        self.mapsoup     = mapsoup
        self.orig_slvg_element = svg_element
        self.rect        = svg_element.select("rect")[0]
        self.second_line = svg_element.select("text")[1]
        self.last_alarm_time   = 0
        self.messages    = []
        self.set_status(states.UNKNOWN)
        self.__located_characters = []
        self.background_color = "#FFFFFF"
        self.map_coordinates  = map_coordinates
        self.systemid         = systemid
        self._neighbours      = set()
        self.statistics       = {"jumps": "?", "shipkills": "?", "factionkills": "?", "podkills": "?"}

    def set_jumpbridge_color(self, color):
        idname = self.name + u"_jb_marker"
        for element in self.mapsoup.select(u"#" + idname):
            element.decompose()
        coords = self.map_coordinates
        style = "fill:{0};stroke:{0};stroke-width:2;fill-opacity:0.4"
        tag = self.mapsoup.new_tag("rect", x=coords["x"]-3, y=coords["y"],
            width=coords["width"]+1.5, height=coords["height"], id=idname,
            style=style.format(color), visibility="hidden")
        tag["class"] = ["jumpbridge",]
        jumps = self.mapsoup.select("#jumps")[0]
        jumps.insert(0, tag)
   
    def mark(self):
        marker = self.mapsoup.select("#select_marker")[0]
        x = self.map_coordinates["center_x"]
        y = self.map_coordinates["center_y"]
        marker["transform"] = "translate({x},{y})".format(x=x, y=y)
        marker["opacity"] = "1"
        marker["activated"] = time.time()
        
    def add_located_character(self, charname):
        idname = self.name + "_loc"
        was_located = bool(self.__located_characters)
        if charname not in self.__located_characters:
            self.__located_characters.append(charname)
        if not was_located:
            coords = self.map_coordinates
            new_tag = self.mapsoup.new_tag(
                "ellipse",
                cx=coords["center_x"]-2.5,
                cy=coords["center_y"],
                id=idname,
                rx=coords["width"]/2+4,
                ry=coords["height"]/2+4,
                style="fill:#8b008d"
            )
            jumps = self.mapsoup.select("#jumps")[0]
            jumps.insert(0, new_tag)
            
    def set_background_color(self, color):
        for rect in self.svg_element("rect"):
            if "location" not in rect.get("class", []) and "marked" not in rect.get("class", []):
                rect["style"] = "fill: {0};".format(color)
            
    def get_located_characters(self):
        characters = []
        for c in self.__located_characters:
            characters.append(c)
        return characters

    def remove_located_character(self, charname):
        idname = self.name + "_loc"
        if charname in self.__located_characters:
            self.__located_characters.remove(charname)
            if not self.__located_characters:
                for element in self.mapsoup.select("#" + idname):
                    element.decompose()

    def add_neighbour(self, neighbour_system):
        """Add a neigbour system to this system
           neighbour_system: a system (not a system's name!)"""
        self._neighbours.add(neighbour_system)
        neighbour_system._neighbours.add(self)

    def get_neighbours(self, distance=1):
        """ Get all neigboured system with a distance of distance.
            example: sys1 <-> sys2 <-> sys3 <-> sys4 <-> sys5
                     sys3(distance=1) will find sys2, sys3, sys4
                     sys3(distance=2) will find sys1, sys2, sys3, sys4, sys5
            returns a dictionary with the system (not the system's name!)
                    as key and a dict as value. key "distance" contains the
                    distance. for first example:
                              {sys3: {"distance"}: 0, sys2: {"distance"}: 1}"""
        # neighbours = []
        systems = {self: {"distance": 0}}
        current_distance = 0
        while current_distance < distance:
            current_distance += 1
            new_systems = []
            for system in systems.keys():
                for neighbour in system._neighbours:
                    if neighbour not in systems:
                        new_systems.append(neighbour)
            for new_system in new_systems:
                systems[new_system] = {"distance": current_distance}
        return systems

    def remove_neighbour(self, system):
        """ removes the link between to neighboured systems """
        if system in self._neighbours:
            self._neighbours.remove(system)
        if self in system._neighbours:
            system._neigbours.remove(self)
        
    def set_status(self, new_status):
        if new_status == states.ALARM:
            self.last_alarm_time = time.time()
            if "stopwatch" not in self.second_line["class"]:
                # self.second_line["class"].append("stopwatch")
                self.second_line["class"] += ' stopwatch'
            self.second_line["alarmtime"] = self.last_alarm_time
            self.second_line["style"] = "fill: #FFFFFF;"
            self.set_background_color(self.ALARM_COLOR)
        elif new_status == states.CLEAR:
            self.last_alarm_time = time.time()
            self.set_background_color(self.CLEAR_COLOR)
            self.second_line["alarmtime"] = 0
            if "stopwatch" not in self.second_line["class"]:
                # self.second_line["class"].append("stopwatch")
                self.second_line["class"] += ' stopwatch'
            self.second_line["alarmtime"] = self.last_alarm_time
            self.second_line["style"] = "fill: #000000;"
            self.second_line.string = "clear"
        elif new_status == states.WAS_ALARMED:
            self.set_background_color(self.UNKNOWN_COLOR)
            self.second_line["style"] = "fill: #000000;"
        elif new_status == states.UNKNOWN:
            self.set_background_color(self.UNKNOWN_COLOR)
            # second line in the rects is reserved for the clock
            self.second_line.string = "?"
            self.second_line["style"] = "fill: #000000;"
        if new_status not in (states.NOT_CHANGE, states.REQUEST):  # unknon not affect system status
            self.status = new_status
            
    def set_statistics(self, statistics):
        if statistics is None:
            text = "stats n/a"
        else:
            text = "J:{jumps} | S:{shipkills} F:{factionkills} P:{podkills}"\
                .format(**statistics)
        svgtext = self.mapsoup.select("#stats_" +  str(self.systemid))[0]
        svgtext.string = text
        
    def update(self):
        # state changed?
        if self.status == states.ALARM:
            alarmtime = time.time() - self.last_alarm_time

            for max_diff, alarm_color, second_line_color in self.ALARM_COLORS:
                if alarmtime < max_diff:
                    if self.background_color != alarm_color:
                        self.background_color = alarm_color
                        for rect in self.svg_element("rect"):
                            if "location" not in rect.get("class", []) and "marked" not in rect.get("class", []):
                                rect["style"] = "fill: {0};".format(self.background_color)
                        self.second_line["style"] = "fill: {0};".format(second_line_color)
                    break

        # timer
        if self.status in (states.ALARM, states.WAS_ALARMED, states.CLEAR):
            diff = math.floor(time.time() - self.last_alarm_time)
            minutes = int(math.floor(diff / 60))
            seconds = int(diff - minutes * 60)
            string = "{m:02d}:{s:02d}".format(m=minutes, s=seconds)
            if self.status == states.CLEAR:
                g = 255
                seconds_until_white = 10*60
                calc_val = int(diff / (seconds_until_white / 255.0))
                if calc_val > 255:
                    calc_val = 255
                    self.second_line["style"] = "fill: #008100;"
                string = "clr: {m:02d}:{s:02d}".format(m=minutes, s=seconds)
                self.set_background_color("rgb({r},{g},{b})".format(g=g, r=calc_val, b=calc_val))
            self.second_line.string = string


def convert_regionname(name):
    """ Converts a (system)name to the format that dotland uses """
    converted = []
    next_upper = False
    for i, c in enumerate(name):
        if i == 0:
            converted.append(c.upper())
        else:
            if c in (u" ", u"_"):
                c = "_"
                next_upper = True
            else:
                if next_upper:
                    c = c.upper()
                else:
                    c= c.lower()
                next_upper = False
            converted.append(c)
    return u"".join(converted)


# this is for testing:
if __name__ == "__main__":
    map = Map("Providence", "Providence.svg")
    s = map.systems["I7S-1S"]
    s.set_alarm(True)
    print(map.svg)
