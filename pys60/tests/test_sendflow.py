# The Send to list keeps the selected files: after a failed IP entry, a
# cancelled IP box, or a failed send, the user comes back to the list.
import os, sys, time, threading, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "fake_s60")); sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))
import retrosend, appuifw, pcnet
work = tempfile.mkdtemp() + "/"; os.chdir(work)
fails = []
def check(n, c):
    print((c and "PASS " or "FAIL ") + n)
    if not c: fails.append(n)

NET = pcnet.SelectNet(); t = threading.Thread(target=NET.run); t.setDaemon(True); t.start()
app = retrosend.App(); app.net = NET; app.ip = "127.0.0.1"
app.set_title = lambda t: None
app.update_menu = lambda: None
popups = []; answers = []
def popup_menu(labels, title=u""):
    popups.append((title, list(labels)))
    if answers: return answers.pop(0)
    return None
appuifw.popup_menu = popup_menu
queries = []
def query(prompt, kind, default=None):
    queries.append(prompt)
    return qanswers and qanswers.pop(0) or None
appuifw.query = query
appuifw.note = lambda *a, **k: None
qanswers = []
p = work + "a.jpg"; open(p, "wb").write("x" * 10)
items = [retrosend.make_file_item(p)]

# 1. Enter IP -> unreachable -> back at Send to
answers[:] = [1, None]      # 0 peers: index 0 = Scan again, 1 = Enter IP; then Back
qanswers[:] = [u"127.0.0.99"]
NET.call(lambda: app.choose_target(items))
time.sleep(2)
titles = [x[0] for x in popups]
check("unreachable IP returns to Send to list", titles.count(u"Send to") == 2)

# 2. cancel the IP box -> back at Send to
del popups[:]
answers[:] = [1, None]; qanswers[:] = []
NET.call(lambda: app.choose_target(items)); time.sleep(0.5)
check("cancelled IP box returns to Send to list", [x[0] for x in popups].count(u"Send to") == 2)

# 3. send to a dead device -> Try again / Choose another device / Give up
del popups[:]
dead = {"alias": u"Gone", "ip": "127.0.0.98", "port": 53317, "fingerprint": u"g", "deviceModel": None, "protocol": u"http"}
app.peers = [dead]
answers[:] = [1, None]      # "Choose another device", then Back on Send to
NET.call(lambda: app.start_send(dead, items)); time.sleep(2)
titles = [x[0] for x in popups]
check("failed send offers retry choices", u"Couldn't reach Gone" in titles)
check("choose another device shows Send to with the same files", titles[-1] == u"Send to")
check("client cleared after failure", app.client is None)
print(fails and "FAILED" or "ALL PASSED"); sys.stdout.flush(); os._exit(len(fails))
