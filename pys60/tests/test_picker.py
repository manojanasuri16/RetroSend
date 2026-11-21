# Picker logic test with stand-in UI objects: folders, marking, Send marked.
import os, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "fake_s60")); sys.path.insert(0, os.path.dirname(HERE))
import retrosend, appuifw

class Canvas:
    size = (240, 234)
    def __init__(self, redraw_callback=None, event_callback=None): self.binds = {}; self.ops = 0
    def bind(self, k, f): self.binds[k] = f
    def clear(self, *a, **k): self.ops += 1
    def rectangle(self, *a, **k): self.ops += 1
    def text(self, *a, **k): self.ops += 1
    def blit(self, *a, **k): self.ops += 1
appuifw.Canvas = Canvas

class FakeApp:
    restored = 0
    def log(self, m): print("LOG " + repr(m))
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
pk.activate()                        # unmark b.jpg
check("toggle off", len(pk.marked) == 1)
pk.mark_all()
check("mark all files here", len(pk.marked) == 3)
pk.load_preview()                    # no graphics on PC: must not raise
check("menu shows count", appuifw.app.menu[0][0] == u"Send marked (3)")
pk.finish()
check("finish returns marked paths", sorted(got) == sorted([root + "a.mp3", root + "b.jpg", root + "c.mp4"]))
check("main screen restored", app.restored == 1)
check("clip", retrosend.clip(u"abcdefghij", 6) == u"abcde~")
print(fails and "FAILED" or "ALL PASSED")
sys.exit(len(fails))
