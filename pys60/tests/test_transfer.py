# TransferScreen logic test with stand-in UI objects (canvas, timers).
import os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "fake_s60")); sys.path.insert(0, os.path.dirname(HERE))
import retrosend, appuifw
import transfer
if hasattr(retrosend, "TransferScreen"):
    TS = retrosend.TransferScreen
else:
    transfer.__dict__.update(dict([(k, v) for k, v in retrosend.__dict__.items() if not k.startswith("__")]))
    TS = transfer.TransferScreen
G = sys.modules[TS.__module__].__dict__

fails = []
def check(n, c):
    print((c and "PASS " or "FAIL ") + n)
    if not c: fails.append(n)

class Canvas:
    size = (240, 234)
    def __init__(self, redraw_callback=None, event_callback=None):
        self.binds = {}; self.texts = []; self.ops = 0; self.clears = 0
    def bind(self, k, f): self.binds[k] = f
    def clear(self, *a, **k): self.clears += 1; self.texts = []
    def rectangle(self, *a, **k): self.ops += 1
    def line(self, *a, **k): self.ops += 1
    def polygon(self, *a, **k): self.ops += 1
    def ellipse(self, *a, **k): self.ops += 1
    def blit(self, *a, **k): self.ops += 1
    def text(self, pos, s, **k): self.texts.append(s)
appuifw.Canvas = Canvas

pending = []
class Timer:
    def after(self, sec, cb): pending.append(cb)
    def cancel(self): pass
class E32:
    Ao_timer = Timer
G["e32"] = E32

class App:
    def __init__(self): self.restored = 0; self.cancels = 0; self.stops = 0
    def restore_main(self): self.restored += 1
    def cancel_send(self): self.cancels += 1
    def stop_receiving(self): self.stops += 1
    def log(self, m): print("LOG " + repr(m))

app = App()
ts = TS(app)
check("not visible before start", not ts.visible())
ts.start("send", u"Solid Blueberry", 3, 3000000)
c = ts.canvas
check("visible after start", ts.visible() and appuifw.app.body is c)
check("header text", u"Sending to Solid Blueberry" in c.texts)
labels = [m[0] for m in appuifw.app.menu]
check("send menu", labels == [u"Cancel sending", u"Hide (keep running)"])
appuifw.app.menu[0][1]()
check("cancel calls app.cancel_send", app.cancels == 1)

# file counter + throttled redraw
before = c.clears
ts.update(u"a.jpg", 100, 3000000)
ts.update(u"a.jpg", 200, 3000000)   # within 0.25 s: no redraw
check("throttled redraw (both within 0.25 s of start)", c.clears == before)
ts.last_draw = 0
ts.update(u"b.jpg", 1000000, 3000000)
check("file counter", u"File 2 of 3" in c.texts and ts.fileno == 2)
check("percent shown", u"33%" in c.texts)
check("size text", [t for t in c.texts if t.find(u" of ") > 0 and t.find(u"MB") > 0] != [])

# speed / ETA from samples
now = time.time()
ts.samples = [(now - 2, 0), (now, 1000000)]
ts.done = 1000000; ts.total = 3000000
sp = ts.speed_text()
check("speed and time left: %r" % sp, sp.find(u"/s") > 0 and sp.find(u"left") > 0)
ts.samples = [(now, 0)]
check("no speed without data", ts.speed_text() == u"")

# finished: result state, auto return
del pending[:]
ts.finish(u"Sent 3 file(s) to Solid Blueberry", 1)
check("done menu", [m[0] for m in appuifw.app.menu] == [u"OK"])
check("result text wrapped", u"Sent 3 file(s) to" in ts.canvas.texts or
      [t for t in ts.canvas.texts if t.find(u"Sent 3") == 0] != [])
check("auto-return timer set", len(pending) == 1)
pending[0]()
check("auto-return restores main", app.restored == 1 and not ts.visible())

# receive flow, hide while running, centre after finish
ts.start("receive", u"PC", 1, 0)
check("receive menu", [m[0] for m in appuifw.app.menu] == [u"Stop receiving", u"Hide (keep running)"])
check("total 0 is safe (waiting)", u"Waiting..." in ts.canvas.texts)
ts.update(u"x" * 300, 10, 0)
ts.last_draw = 0; ts.update(u"x" * 300, 20, 0)
check("long name clipped", max([len(t) for t in ts.canvas.texts]) < 60)
appuifw.app.menu[0][1]()
check("stop calls app.stop_receiving", app.stops == 1)
appuifw.app.exit_key_handler()
check("right softkey hides while running", app.restored == 2 and not ts.visible())
ts.finish(u"Received 1 file(s) from PC. " + u"word " * 40, 0)
check("finish re-shows hidden screen", ts.visible())
ts.canvas.binds.values()[0]()
check("centre after finish hides", app.restored == 3 and not ts.visible())
check("wrap_text", G["wrap_text"](u"aaa bbb ccc", 7) == [u"aaa bbb", u"ccc"])
print(fails and "FAILED" or "ALL PASSED")
sys.exit(len(fails))
