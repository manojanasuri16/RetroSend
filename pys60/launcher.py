# RetroSend starter (installed as default.py by build_sis.sh).
# Kept tiny on purpose: it opens the log and imports the real app (rs_app.py,
# shipped next to it) so that any error while loading -- out of memory,
# a missing module, a syntax error -- is shown on screen and logged instead
# of the app silently not opening. Python 2.2 compatible.
import sys
import os
import appuifw
import e32

UID = "e7a3d5c1"


def _log(msg):
    for d in ["E:\\", "C:\\Data\\", "C:\\"]:
        try:
            f = open(d + "retrosend_log.txt", "a")
            f.write(msg + "\n")
            f.close()
            return
        except:
            pass


for _drive in ["C", "E"]:
    _p = _drive + ":\\private\\" + UID + "\\"
    if os.path.exists(_p + "rs_app.py") and _p not in sys.path:
        sys.path.insert(0, _p)

try:
    import rs_app  # runs the app
except:
    _t = str(sys.exc_info()[1])
    try:
        import traceback
        _t = "".join(apply(traceback.format_exception, sys.exc_info()))
    except:
        pass
    _log("LAUNCH ERROR (python " + sys.version.split(" ")[0] + "):\n" + _t)
    try:
        appuifw.note(unicode("RetroSend could not start: " + str(sys.exc_info()[1]),
                             "latin-1"), "error")
        appuifw.query(u"Error details (also in retrosend_log.txt)", "text",
                      unicode(_t, "latin-1"))
    except:
        pass
