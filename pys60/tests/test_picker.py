# Picker logic test with stand-in UI objects: folders, marking, Send marked.
import os, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "fake_s60")); sys.path.insert(0, os.path.dirname(HERE))
import retrosend, appuifw

class Canvas:
    size = (240, 234)
    def __init__(self, redraw_callback=None, event_callback=None):
        self.binds = {}; self.ops = 0; self.texts = []; self.fills = []
    def bind(self, k, f): self.binds[k] = f
    def clear(self, *a, **k): self.ops += 1; self.texts = []; self.fills = []
    def rectangle(self, *a, **k): self.ops += 1; self.fills.append(k.get("fill"))
    def line(self, *a, **k): self.ops += 1
    def text(self, pos, t, **k): self.ops += 1; self.texts.append(t)
    def blit(self, *a, **k): self.ops += 1
appuifw.Canvas = Canvas

class FakeApp:
    restored = 0
    logs = []
    def log(self, m): print("LOG " + repr(m)); self.logs.append(m)
    def restore_main(self): self.restored += 1

fails = []
def check(n, c):
    print((c and "PASS " or "FAIL ") + n)
    if not c: fails.append(n)

root = tempfile.mkdtemp() + os.sep
os.mkdir(root + "Album"); os.mkdir(root + "_PAlbTN")
for n in ["b.jpg", "a.mp3", "c.mp4"]: open(root + n, "wb").write("x" * 10)
open(root + "Album" + os.sep + "d.png", "wb").write("y")
retrosend_sep = os.sep
got = []
app = FakeApp()
pk = retrosend.Picker(app, root, lambda paths, names=None: got.extend(paths))
# Picker uses "\\" as folder separator on the phone; use os.sep on the PC
src = open(retrosend.__file__.replace(".pyc", ".py")).read()
pk.show()
names = [e[0] for e in pk.entries]
check("hidden _PAlbTN skipped, folders first", names == [u"Album", u"a.mp3", u"b.jpg", u"c.mp4"])
check("canvas drew something", pk.canvas.ops > 5)
pk.move(1); pk.activate()            # mark a.mp3
pk.move(1); pk.activate()            # mark b.jpg
check("two marked", len(pk.marked) == 2)
left, right = pk.header_text()
check("header shows folder and marked size: %r" % right, right == u"2 marked \u00b7 20 B")
check("header drawn", right in pk.canvas.texts)
check("footer hint drawn", u"Centre: mark   Options: send" in pk.canvas.texts)
check("no scroll indicator for a short list", retrosend.SCROLL not in pk.canvas.fills)
check("marked rows tinted", retrosend.TINT in pk.canvas.fills)
pk.activate()                        # unmark b.jpg
check("toggle off", len(pk.marked) == 1)
check("marked total follows unmark", retrosend.marked_total(pk.marked) == 10)
pk.mark_all()
check("mark all files here", len(pk.marked) == 3)
pk.load_preview()                    # no graphics on PC: must not raise
check("menu shows count", appuifw.app.menu[0][0] == u"Send marked (3)")
pk.finish()
check("finish returns marked paths", sorted(got) == sorted([root + "a.mp3", root + "b.jpg", root + "c.mp4"]))
check("main screen restored", app.restored == 1)
check("clip", retrosend.clip(u"abcdefghij", 6) == u"abcde~")
check("no draw errors", not [m for m in app.logs if m.find(u"draw") >= 0])

# badges per type
B = retrosend.badge_for
check("badge IMG blue", B(u"a.JPG", 0) == (u"IMG", 0x146EDC, 0xFFFFFF))
check("badge MUS purple", B(u"a.mp3", 0)[:2] == (u"MUS", 0x8E44AD))
check("badge VID orange", B(u"a.3gp", 0)[:2] == (u"VID", 0xE67E22))
check("badge DIR yellow, dark text", B(u"Album", 1) == (u"DIR", 0xF1C40F, 0x202020))
check("badge other grey", B(u"doc.pdf", 0) == (u"PDF", 0x7A8CA5, 0xFFFFFF))

# long list: scroll indicator, and view-only footer
big = tempfile.mkdtemp() + os.sep
for k in range(30): open(big + "f%02d.txt" % k, "wb").write("z")
pv = retrosend.Picker(app, big, lambda paths, names=None: None, 1)
pv.show()
check("scroll indicator for a long list", retrosend.SCROLL in pv.canvas.fills)
check("view-only footer hint", u"Centre: open   Options: more" in pv.canvas.texts)
check("header without marks shows only the folder", pv.header_text()[1] == u"")
empty = tempfile.mkdtemp() + os.sep
pe = retrosend.Picker(app, empty, lambda paths, names=None: None)
pe.show()
check("empty folder message", u"This folder is empty" in pe.canvas.texts)
print(fails and "FAILED" or "ALL PASSED")
sys.exit(len(fails))
