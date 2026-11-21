# Builds the phone's app folder the way build_sis.sh does (starter as
# default.py, the app as rs_app.py, every #@INLINE module next to it) and
# runs the starter, so a module missing from the phone build fails here.
import os, sys, re, shutil, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.dirname(HERE)
app = tempfile.mkdtemp()
shutil.copy(os.path.join(SRC, "launcher.py"), os.path.join(app, "default.py"))
shutil.copy(os.path.join(SRC, "retrosend.py"), os.path.join(app, "rs_app.py"))
mods = re.findall(r"^#@INLINE (\S+\.py)$", open(os.path.join(SRC, "retrosend.py")).read(), re.M)
for m in mods:
    shutil.copy(os.path.join(SRC, m), app)
os.chdir(app)
sys.path[:0] = [os.path.join(HERE, "fake_s60"), app]
execfile("default.py", {"__name__": "__main__"})
import rs_app
need = ["Picker", "PhotoGrid", "WebShare", "TransferScreen", "read_id3", "exif_thumb", "App"]
missing = [n for n in need if not hasattr(rs_app, n)]
log = open("E:\\retrosend_log.txt").read() if os.path.exists("E:\\retrosend_log.txt") else ""
fails = []
if missing: fails.append("missing in rs_app: %r" % missing)
if log.find("LAUNCH ERROR") >= 0: fails.append("starter logged an error:\n" + log)
print("modules in phone build: %s" % ", ".join(mods))
print(fails and ("FAIL " + "; ".join(fails)) or "PASS starter loads every module")
print(fails and "FAILED" or "ALL PASSED")
sys.exit(len(fails))
