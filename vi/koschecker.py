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

import json
# import urllib
# import urllib2

from vi import evegate
from vi.cache.cache import Cache

UNKNOWN = "?"
NOT_KOS = 'NOT kos'
KOS = "KOS"
RED_BY_LAST = "RED by last"

def check(parts):
    data = {}
    base_url = "http://kos.cva-eve.org/api/?c=json&type=multi&q="
    names = [name.strip() for name in parts]
    check_by_last_chars = []
    quoted_names = urllib.quote_plus(",".join(names))
    target_url = "".join((base_url, quoted_names))
    request = urllib2.urlopen(target_url)
    kosdata = json.loads(request.read())
    for char in kosdata["results"]:
        charname = char["label"]
        corpname = char["corp"]["label"]
        names.remove(charname)
        if char["kos"] or char["corp"]["kos"] \
           or char["corp"]["alliance"]["kos"]:
            data[charname] = {"kos": KOS}
        elif corpname not in evegate.NPC_CORPS:
            data[charname] = {"kos": NOT_KOS}
        else:
            if char not in check_by_last_chars:
                check_by_last_chars.append(charname)       
    for name in names:  # still names there (the kos checker not found) ?
        check_by_last_chars.append(name)
    # deeper check
    deeper_data = {}
    names_ids = evegate.names_to_ids(check_by_last_chars)
    for name, id in names_ids.items():
        deeper_data[name] = {"id": id, "need_check": False,
                             "corpids": evegate.get_corpids_for_charid(id)}
    corpids = set()
    for name in names_ids.keys():
        for corpid in deeper_data[name]["corpids"]:
            corpids.add(corpid)
    corpid_name = evegate.ids_to_names(corpids)
    for name, ndata in deeper_data.items():
        ndata["corpnames"] = [corpid_name[id] for id in ndata["corpids"]]
        for corpname in ndata["corpnames"]:
            if corpname not in evegate.NPC_CORPS:
                ndata["need_check"] = True
                ndata["corp_to_check"] = corpname
                break
    corps_to_check = set([ndata["corp_to_check"] for ndata 
                          in deeper_data.values()
                          if ndata["need_check"] == True])
    corps_result = {}
    base_url = "http://kos.cva-eve.org/api/?c=json&type=unit&q="
    for corp in corps_to_check:
        quoted_name = urllib.quote_plus(corp)
        target_url = "".join((base_url, quoted_name))
        request = urllib2.urlopen(target_url)
        kosdata = json.loads(request.read())
        kos = False
        for result in kosdata["results"]:
            if result["kos"] == True:
                kos = True
            elif "alliance" in result and \
              result["alliance"]["kos"] == True:
                  kos = True
        corps_result[corp] = kos
    for charname, ndata in deeper_data.items():
        if not ndata["need_check"]:
            data[charname] = {"kos": UNKNOWN}
        if ndata["need_check"] and corps_result[ndata["corp_to_check"]] == True:
            data[charname] = {"kos": RED_BY_LAST}
        else:
            data[charname] = {"kos": UNKNOWN}
    return data


def result_to_text(results, only_kos=False):
    groups = {}
    paragraphs = []
    for charname, result_data in results.items():
        state = result_data["kos"]
        if state not in groups:
            groups[state] = set()
        groups[state].add(charname)
    if KOS in groups:
        paragraphs.append(KOS + u": " +  u", ".join(groups[KOS]))
    if RED_BY_LAST in groups:
        paragraphs.append(RED_BY_LAST + u": " + u", ".join(groups[RED_BY_LAST]))
    if UNKNOWN in groups:
        paragraphs.append(UNKNOWN + u": " + ", ".join(groups[UNKNOWN]))
    if NOT_KOS in groups and not only_kos:
        paragraphs.append(NOT_KOS + u": " + ", ".join(groups[NOT_KOS]))
    return u"\n\n".join(paragraphs)
