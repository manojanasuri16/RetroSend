# PhotoGrid logic test with stand-in UI objects (canvas, graphics, timers).
import os, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "fake_s60")); sys.path.insert(0, os.path.dirname(HERE))
import retrosend, appuifw
import grid
if not hasattr(retrosend, "PhotoGrid"):
    grid.__dict__.update(dict([(k, v) for k, v in retrosend.__dict__.items() if not k.startswith("__")]))
    PhotoGrid = grid.PhotoGrid
else:
    PhotoGrid = retrosend.PhotoGrid
G = sys.modules[PhotoGrid.__module__].__dict__   # globals PhotoGrid uses

class Canvas:
    size = (240, 234)
    def __init__(self, redraw_callback=None, event_callback=None):
        self.binds = {}; self.ops = 0; self.blits = 0; self.texts = []; self.fills = []
    def bind(self, k, f): self.binds[k] = f
    def clear(self, *a, **k): self.ops += 1; self.texts = []; self.fills = []
    def rectangle(self, *a, **k): self.ops += 1; self.fills.append(k.get("fill"))
    def line(self, *a, **k): self.ops += 1
    def text(self, pos, t, **k): self.ops += 1; self.texts.append(t)
    def blit(self, *a, **k): self.ops += 1; self.blits += 1
appuifw.Canvas = Canvas

class Img:
    def __init__(self, size): self.size = size
    def resize(self, wh, keepaspect=0): return Img((wh[0], wh[1] * 3 / 4))
opened = []
class FakeImage:
    def open(path): opened.append(path); return Img((160, 120))
    open = staticmethod(open)
    def inspect(path): return {"size": (640, 480)}
    inspect = staticmethod(inspect)
class FakeGraphics: Image = FakeImage
G["graphics"] = FakeGraphics

# manual timers: run pending callbacks explicitly
pending = []
class Timer:
    def after(self, sec, cb): pending.append(cb)
    def cancel(self):
        del pending[:]
class FakeE32:
    Ao_timer = Timer
G["e32"] = FakeE32
def run_timers(limit=1000):
    n = 0
    while pending and n < limit:
        pending.pop(0)(); n += 1
    return n

class FakeApp:
    def __init__(self): self.restored = 0; self.switched = None
    logs = []
    def log(self, m): print("LOG " + repr(m)); self.logs.append(m)
    def restore_main(self): self.restored += 1
    def switch_to_list(self, d, marked): self.switched = (d, marked)

fails = []
def check(n, c):
    print((c and "PASS " or "FAIL ") + n)
    if not c: fails.append(n)

root = tempfile.mkdtemp() + os.sep
os.mkdir(root + "Album"); os.mkdir(root + "_PAlbTN")
for k in range(10):
    open(root + "p%02d.jpg" % k, "wb").write("x")
open(root + "song.mp3", "wb").write("x"); open(root + "clip.mp4", "wb").write("x")

got = []
app = FakeApp()
shared = {}
g = PhotoGrid(app, root, lambda paths: got.extend(paths), shared)
g.show()
kinds = [e[2] for e in g.entries]
names = [e[0] for e in g.entries]
check("only folders + images, hidden skipped", names == [u"Album"] + [u"p%02d.jpg" % k for k in range(10)])
check("no '..' at start folder", kinds[0] == "dir")
check("3 columns on 240 px", g.columns() == 3)

# lazy loader fills visible tiles one per timer step, then stops
check("loader scheduled", len(pending) == 1)
steps = run_timers()
check("2 visible rows of 80 px cells", g.visible_rows() == 2 and g.cell_size() == (80, 80))
check("loaded visible photos one per step", steps == 5 and len(g.cache) == 5)
check("loader stopped", not g.loading and not pending)
check("thumbnails drawn", g.canvas.blits >= 5)

# 2D navigation
g.cur = 0
g.move(-1); check("left at first tile stays", g.cur == 0)
g.move_row(-1); check("up from top row stays", g.cur == 0)
g.move_row(1); check("down moves one row", g.cur == 3)
g.move(1); check("right moves one", g.cur == 4)
g.cur = 8; g.move_row(1); check("down into short last row goes to last tile", g.cur == 10)
g.move_row(1); check("down on last row stays", g.cur == 10)
g.move(1); check("right at last tile stays", g.cur == 10)
check("scrolled so cursor visible", g.top_row == 2)
run_timers()
check("scrolling loads newly visible photos", g.cache.has_key(root + "p09.jpg") and g.cache.has_key(root + "p08.jpg"))

# marking
g.cur = 1; g.activate(); g.cur = 2; g.activate()
check("two marked (shared dict)", len(shared) == 2 and shared is g.marked)
left, right = g.header_text()
check("grid header shows marked count and size: %r" % right, right == u"2 marked \u00b7 2 B")
check("grid header drawn", right in g.canvas.texts and left in g.canvas.texts)
check("grid footer hint drawn", u"Centre: mark   Options: send" in g.canvas.texts)
g.top_row = 0; g.redraw(None)   # the marked tiles were scrolled out of view above
check("marked tiles tinted", G["TINT"] in g.canvas.fills)
g.activate(); check("toggle off", len(shared) == 1)
g.cur = 0; g.activate()     # folder: must not mark (opening uses \\ paths on the phone)
check("menu shows count", appuifw.app.menu[0][0] == u"Send marked (1)" or len(shared) == 1)
g2 = PhotoGrid(app, root, lambda p: None, {})
g2.show(); run_timers()
g2.mark_all(); check("mark all photos here", len(g2.marked) == 10)
g2.unmark_all(); check("unmark all", len(g2.marked) == 0)
g2.mark_all(); g2.list_view()
check("list view gets dir + marked", app.switched == (root, g2.marked) and len(app.switched[1]) == 10)
check("list view stops loader", not pending)

# finish
g3 = PhotoGrid(app, root, lambda paths: got.extend(paths), {})
g3.show(); run_timers()
g3.cur = 3; g3.activate(); g3.cur = 1; g3.activate()
r0 = app.restored
g3.finish()
check("finish returns sorted marked", got == [root + "p00.jpg", root + "p02.jpg"])
check("finish restores main", app.restored == r0 + 1)
del got[:]
g4 = PhotoGrid(app, root, lambda paths: got.extend(paths), {})
g4.show(); g4.cur = 5; g4.finish()
check("finish with none marked sends current", got == [root + "p04.jpg"])
g5 = PhotoGrid(app, root, lambda p: None, {}); g5.show()
r0 = app.restored; g5.back()
check("right softkey at start closes", app.restored == r0 + 1 and g5.closed)
check("close cancels timer", not pending)

# cache limit
for k in range(60):
    open(root + "q%02d.jpg" % k, "wb").write("x")
g6 = PhotoGrid(app, root, lambda p: None, {}); g6.show()
for k in range(0, 80, 3):
    g6.cur = k; g6.moved(); run_timers()
check("cache limited to 40", len(g6.cache) <= 40 and len(g6.cache_order) <= 40)
g7 = PhotoGrid(app, tempfile.mkdtemp() + os.sep, lambda p: None, {}); g7.show()
check("grid: no scroll indicator for a short folder", G["SCROLL"] not in g7.canvas.fills)
check("grid: empty message", u"No photos or folders here" in g7.canvas.texts)
check("grid: scroll indicator for a long folder", G["SCROLL"] in g6.canvas.fills)
check("grid: no draw errors", not [m for m in app.logs if m.find(u"draw") >= 0])
print(fails and "FAILED" or "ALL PASSED")
sys.exit(len(fails))
