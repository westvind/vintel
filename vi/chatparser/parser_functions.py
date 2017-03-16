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

""" 12.02.2015
    I know this is a little bit dirty, but I prefer to have all the functions
    to parse the chat in this file together.
    Wer are now work directly with the html-formated text, which we use to
    display it. We are using a HTML/XML-Parser to have the benefit, that we
    can only work and analyze those text, that is still not on tags, because
    all the text in tags was allready identified.
    f.e. the ship_parser:
        we call it from the chatparser and give them the rtext (richtext).
        if the parser hits a shipname, it will modifiy the tree by creating
        a new tag and replace the old text with it (calls tet_replace),
        than it returns True.
        The chatparser will call the function again until it return False
        (None is False) otherwise.
        We have to call the parser again after a hit, because a hit will change
        the tree and so the original generator is not longer stable.
"""

from bs4 import BeautifulSoup
from bs4.element import NavigableString

import vi.evegate as evegate
from vi import states


chars_to_ignore = ("*", "?", ",", "!")

def text_replace(element, new_text):
    new_text = "<t>" + new_text + "</t>"
    new_elements = []
    for new_part in BeautifulSoup(new_text, "html.parser").select("t")[0].contents:
        new_elements.append(new_part)
    for new_element in new_elements:
        element.insert_before(new_element)
    element.replace_with(str(""))


def parse_status(rtext):
    texts = [t for t in rtext.contents if isinstance(t, NavigableString)]
    for text in texts:
        utext = text.strip().upper()
        for char in chars_to_ignore:
            utext = utext.replace(char, "")
        uwords = utext.split()
        if (("CLEAR" in uwords or "CLR" in uwords) 
            and not utext.endswith("?")):
            return states.CLEAR
        elif ("STAT" in uwords or "STATUS" in uwords):
            return states.REQUEST
        elif ("?" in utext):
            return states.REQUEST
        elif (text.strip().upper() in ("BLUE", "BLUES ONLY", "ONLY BLUE"
                                       "STILL BLUE", "ALL BLUES")):
            return states.CLEAR

def parse_ships(rtext):

    def format_shipname(text, word):
        new_text = u"""<span style="color:#d95911;font-weight:bold">
                    {0}</span>"""
        text = text.replace(word, new_text.format(word))
        return text
    
    texts = [t for t in rtext.contents if isinstance(t, NavigableString)]
    for text in texts:
        utext = text.upper()
        for shipname in evegate.SHIPNAMES:
            if shipname in utext:
                hit = True
                start = utext.find(shipname)
                end = start+len(shipname)
                if ((start > 0 and utext[start-1] not in (" ", "X"))
                  or (end < len(utext)-1 and utext[end] not in ("S"," "))):
                    hit = False
                if hit:
                    shipintext = text[start:end]
                    formated = format_shipname(text, shipintext)
                    text_replace(text, formated)
                    return True



def parse_systems(systems, rtext, found_systems):

    # words to ignore on the system parser. use UPPER CASE
    WORDS_TO_IGNORE = ("IN", "IS", "AS")
    
    def format_system(text, word, system):
        new_text = u"""<a style="color:#CC8800;font-weight:bold" 
                    href="mark_system/{0}">{1}</a>"""
        text = text.replace(word, new_text.format(system, word))
        return text

    sys_names = systems.keys()
    texts = [t for t in rtext.contents if isinstance(t, NavigableString)]
    for text in texts:
        worktext = text
        for char in chars_to_ignore:
            worktext = worktext.replace(char, "")
        words = worktext.split(" ")
        for word in words:
            if len(word.strip()) == 0:
                continue
            uword = word.upper()
            if uword != word and uword in WORDS_TO_IGNORE: continue
            if uword in sys_names:                   # - direct hit on name
                found_systems.add(systems[uword])    #   of the system?
                formated_text = format_system(text, word, uword)
                text_replace(text, formated_text)
                return True
            elif 1 < len(uword) < 5:  # - uword < 4 chars.
                for system in sys_names:             #   system begins with?
                    if system.startswith(uword):
                        found_systems.add(systems[system])
                        formated_text = format_system(text, word,
                                                      system)
                        text_replace(text, formated_text)
                        return True
            elif "-" in uword and len(uword) > 2:  # - short with - (minus)
                uword_parts = uword.split("-")     #   (I-I will bis I43-IF3)
                for system in sys_names:
                    system_parts = system.split("-")
                    if (len(uword_parts) == 2 and
                        len(system_parts) == 2 and
                        len(uword_parts[0]) > 1 and
                        len(uword_parts[1]) > 1 and
                        len(system_parts[0]) > 1 and
                        len(system_parts[1]) > 1 and
                        len(uword_parts) == len(system_parts) and
                        uword_parts[0][0] == system_parts[0][0] and 
                        uword_parts[1][0] == system_parts[1][0]):
                        found_systems.add(systems[system])
                        formated_text = format_system(text, word,
                                                      system)
                        text_replace(text, formated_text)
                        return True
            elif len(uword) > 1:  # what if F-YH58 is named FY?
                for system in sys_names:
                    cleared_system = system.replace("-", "")
                    if cleared_system.startswith(uword):
                        found_systems.add(systems[system])
                        formated_text = format_system(text, word,
                                                      system)
                        text_replace(text, formated_text)
                        return True



def parse_urls(rtext):

    def find_urls(s):
        # yes, this is faster than regex and less complex to read
        urls = []
        prefixes = ("http://", "https://")
        for prefix in prefixes:
            start = 0
            while start >= 0:
                start = s.find(prefix, start)
                if start >= 0:
                    stop = s.find(" ", start)
                    if stop < 0:
                        stop = len(s)
                    urls.append(s[start:stop])
                    start += 1
        return urls
    
    def format_url(text, url):
        new_text = u"""<a style="color:#28a5ed;font-weight:bold"
                       href="link/{0}">{0}</a>"""
        text = text.replace(url, new_text.format(url))
        return text

    texts = [t for t in rtext.contents if isinstance(t, NavigableString)]
    for text in texts:
        urls = find_urls(text)
        for url in urls:
            text_replace(text, format_url(text, url))
            return True
