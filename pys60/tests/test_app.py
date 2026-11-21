# App-level checks with stand-in S60 modules: tab entries, settings round
# trip, remembered devices, received-file list, sorting, speed text.
import os, sys, tempfile, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "fake_s60")); sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))
import retrosend, appuifw

fails = []
def check(n, c):
    print((c and "PASS " or "FAIL ") + n)
    if not c: fails.append(n)

class Later:
    def later(self, s, f): pass
work = tempfile.mkdtemp() + "/"
os.chdir(work)  # the app saves retrosend.cfg in the current folder
app = retrosend.App()
app.cfg_path = work + "retrosend.cfg"
app.net = Later()
titles = []
app.set_title = lambda t: titles.append(t)

# tab entries
send = [e[0] for e in app.send_entries()]
recv = [e[0] + u" " + e[1] for e in app.recv_entries()]
check("send tab has contacts, folder, browser items",
      u"Send contacts" in send and u"Send files or folders" in send and u"Share to a browser" in send)
check("receive tab shows version", (u"About RetroSend " + retrosend.VERSION + u", help") in recv)
check("version looks like x.y.z", len(retrosend.VERSION.split(u".")) == 3)
check("every entry has a callable action",
      len([1 for e in app.send_entries() + app.recv_entries() if not callable(e[2])]) == 0)
check("rows are (title, hint) pairs", [len(r) for r in app.send_items()] == [2] * len(app.send_items()))

# toggles persist
app.cfg["auto"] = 0
app.toggle_auto()
check("toggle auto on", app.cfg["auto"] == 1)
app.toggle_sort(); app.toggle_sort()
check("sort default on and toggles back", app.cfg["sort"] == 1)

# remembered devices round trip
dev = {"alias": u"Solid Blueberry", "ip": "192.168.1.5", "port": 53317, "fingerprint": u"abc",
       "deviceModel": u"Pixel", "protocol": u"http"}
app.peer(dev)
check("peer listed", len(app.peers) == 1)
check("device remembered", app.cfg["devices"][0]["ip"] == "192.168.1.5")
app.peer({"alias": u"bad", "ip": "0.8.0.0", "port": 1, "fingerprint": u"z", "deviceModel": None, "protocol": u"http"})
check("bogus address not remembered", len(app.cfg["devices"]) == 1)
again = retrosend.App(); again.cfg_path = app.cfg_path; again.cfg = again.load_cfg()
check("devices survive restart", again.cfg["devices"] and again.cfg["devices"][0]["alias"] == u"Solid Blueberry")
check("settings survive restart", again.cfg["auto"] == 1 and again.cfg["sort"] == 1)
moved = dict(dev); moved["ip"] = "192.168.1.7"
app.peer(moved)
check("same device with new IP replaces old entry",
      len(app.cfg["devices"]) == 1 and app.cfg["devices"][0]["ip"] == "192.168.1.7")
app.forget_device(app.cfg["devices"][0])
check("forget removes device", app.cfg["devices"] == [] and app.peers == [])

# received files list
for i in range(35):
    app.saved(work + "f%d.jpg" % i)
check("recent capped at 30, newest kept", len(app.cfg["recent"]) == 30 and app.cfg["recent"][-1].endswith("f34.jpg"))

# sorting received files
cfg = {"sort": 1, "savedir": work + "in/"}
check("non-media goes to savedir", retrosend.save_dir_for(cfg, u"doc.pdf") == work + "in/")
cfg["sort"] = 0
check("sorting off keeps savedir", retrosend.save_dir_for(cfg, u"a.jpg") == work + "in/")

# speed / time left in the title
app.progress(u"Sending", 0, 1000000)
app.xfer_t0 = time.time() - 4
app.progress(u"Sending", 400000, 1000000)
t = titles[-1]
check("title shows percent, speed and time left: %r" % t,
      t.startswith(u"40% ") and t.find(u"/s") > 0 and t.find(u"left") > 0)

# file item names for folder sends
p = work + "song.mp3"; open(p, "wb").write("x" * 5)
it = retrosend.make_file_item(p, u"Album/song.mp3")
check("folder send keeps relative name", it["name"] == u"Album/song.mp3" and it["type"] == "audio/mpeg")
print(fails and "FAILED" or "ALL PASSED")
sys.exit(len(fails))
