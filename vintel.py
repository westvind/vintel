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

# import cStringIO
import io, os, sys, time, traceback, logging
import ctypes.wintypes
from PyQt5 import QtWidgets, QtGui
from vi import version
from vi.ui import viui, systemtray
from vi.cache import cache
from vi.resources import resource_path
# from PyQt5 import QtWebEngineWidgets

app = QtWidgets.QApplication(sys.argv)

error_file = "error.log"


def excepthook(excType, excValue, tracebackobj):
    """ Global function to catch unhandled exceptions.
    """
    separator = '-' * 80
    notice = \
        """An unhandled exception occurred. Please report the problem\n""" \
        """using via email to <{0}>.\n""" \
        """A log has been written to "{1}".\n\nError information:\n""".format(
            "sparrow.242.de+EVE@gmail.com", error_file)
    versionInfo = version.VERSION
    timeString = time.strftime("%Y-%m-%d, %H:%M:%S")
    tbinfofile = io.StringIO()
    traceback.print_tb(tracebackobj, None, tbinfofile)
    tbinfofile.seek(0)
    tbinfo = tbinfofile.read()
    errmsg = '{0}: \n{1}'.format(str(excType), str(excValue))
    sections = [separator, timeString, separator, errmsg, separator, tbinfo]
    msg = '\n'.join(sections)
    try:
        f = open(error_file, "w")
        f.write(msg)
        f.write(versionInfo)
        f.close()
    except IOError:
        pass
    errorbox = QtWidgets.QMessageBox()
    errorbox.setText(str(notice) + str(msg) + str(versionInfo))
    errorbox.exec_()


sys.excepthook = excepthook

# import os

# from vi.ui import viui, systemtray
# from vi.cache import cache
# from vi.resources import resource_path


def main():
    FORMAT = '%(asctime)-15s %(filename)s L%(lineno)d %(funcName)s: %(message)s'
    logging.basicConfig(level=logging.FATAL, format=FORMAT, datefmt='%d.%m.%Y %H:%M:%S')

    global error_file

    splash = QtWidgets.QSplashScreen(QtGui.QPixmap(resource_path("vi/ui/res/logo.png")))
    splash.show()
    app.processEvents()

    PATH_TO_LOGS = None

    # did we have a manuel path to the logs as an argument at start?
    if len(sys.argv) > 1:
        PATH_TO_LOGS = sys.argv[1]
        print("Try to find Logdir @:", PATH_TO_LOGS)

    # Path to Chatlogs on Linux System using wine
    if not PATH_TO_LOGS or not os.path.exists(PATH_TO_LOGS):
        print("Going on find logdir...")
        PATH_TO_LOGS = os.path.join(os.path.expanduser("~"), "EVE", "logs",
                                    "Chatlogs")
        print("Try to find Logdir @:", PATH_TO_LOGS)
    # Path to Chatlogs on MacOS
    if not os.path.exists(PATH_TO_LOGS):
        print("No logdir @:", PATH_TO_LOGS)
        PATH_TO_LOGS = os.path.join(os.path.expanduser("~"), "Library",
                                    "Application Support", "Eve Online", "p_drive", "User",
                                    "My Documents", "EVE", "logs", "Chatlogs")
        print("Try to find Logdir @:", PATH_TO_LOGS)

    # Path to chatlogs on windows
    if not os.path.exists(PATH_TO_LOGS):
        print("No logdir @: ", PATH_TO_LOGS)
        CSIDL_PERSONAL = 5
        SHGFP_TYPE_CURRENT = 0
        buf = ctypes.create_unicode_buffer(ctypes.wintypes.MAX_PATH)
        ctypes.windll.shell32.SHGetFolderPathW(0, CSIDL_PERSONAL, 0,
                                               SHGFP_TYPE_CURRENT, buf)
        documents_path = buf.value
        print("Documents path? :", documents_path)
        PATH_TO_LOGS = os.path.join(documents_path, "EVE", "logs", "Chatlogs")

    # None of the pathes for logs exists? So we can not work, sorry
    if not os.path.exists(PATH_TO_LOGS):
        QtWidgets.QMessageBox.critical(
            None,
            "No path to Logs",
            "Vintel could not find the directory where the EvE chatlogs are stored. Sorry.",
            QtWidgets.QMessageBox.Close
        )
        sys.exit(1)

    print("I expect logs @:", PATH_TO_LOGS)

    # setting local working directory for cache, etc.
    # datadir = os.path.join(os.path.expanduser("~"), "EVE", "vintel")
    datadir = os.path.join(os.path.dirname(os.path.dirname(PATH_TO_LOGS)), "vintel")
    if not os.path.exists(datadir):
        os.mkdir(datadir)
    print("Vintel writes data in :", datadir)

    cache.Cache.PATH_TO_CACHE = os.path.join(datadir, "cache.sqlite3")
    error_file = os.path.join(datadir, "error.log")

    trayicon = systemtray.TrayIcon(app)
    trayicon.setContextMenu(systemtray.TrayContextMenu(trayicon))
    trayicon.show()

    mw = viui.MainWindow(PATH_TO_LOGS, trayicon)

    mw.show()
    splash.finish(mw)
    app.exec()
    app.quit()
    # app.exit(0)
    # sys.exit()


if __name__ == "__main__":
    main()
