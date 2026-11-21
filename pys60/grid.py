# ---------------------------------------------------------------- photo grid
#
# A Canvas screen showing photos as thumbnail tiles (plus folder tiles).
# Arrows move, centre marks a photo or opens a folder, right softkey goes up
# a folder or closes. Options: Send marked, Mark all, Unmark all, List view.
# Thumbnails load one at a time on a short timer chain so keys stay
# responsive; at most GRID_CACHE thumbnails are kept in memory.
#
# Pasted into retrosend.py after the Picker class; uses its globals
# (appuifw, e32, graphics, key_codes, os, to_u, clip, exif_thumb, temp_dir,
# IMAGE_EXT, ext_in, err_text).

GRID_CACHE = 40
GRID_CELL = 76


class PhotoGrid:
    def __init__(self, app, start, on_done, marked=None):
        self.app = app
        self.path = start
        self.root = start
        self.on_done = on_done
        if marked is None:
            marked = {}
        self.marked = marked     # path -> 1, shared with the list view
        self.entries = []        # (label, name, kind) kind: "up", "dir", "img"
        self.cur = 0
        self.top_row = 0
        self.cache = {}          # path -> image, or None when no preview
        self.cache_order = []
        self.timer = None
        self.loading = 0
        self.canvas = None
        self.closed = 0

    # ---- set up / tear down

    def show(self):
        a = appuifw.app
        try:
            a.set_tabs([], None)
        except:
            pass
        self.canvas = appuifw.Canvas(redraw_callback=self.redraw)
        a.body = self.canvas
        a.exit_key_handler = self.back
        c = self.canvas
        c.bind(key_codes.EKeyUpArrow, lambda self=self: self.move_row(-1))
        c.bind(key_codes.EKeyDownArrow, lambda self=self: self.move_row(1))
        c.bind(key_codes.EKeyLeftArrow, lambda self=self: self.move(-1))
        c.bind(key_codes.EKeyRightArrow, lambda self=self: self.move(1))
        c.bind(key_codes.EKeySelect, self.activate)
        try:
            c.bind(key_codes.EKey5, self.activate)
            c.bind(key_codes.EKey2, lambda self=self: self.move_row(-1))
            c.bind(key_codes.EKey8, lambda self=self: self.move_row(1))
            c.bind(key_codes.EKey4, lambda self=self: self.move(-1))
            c.bind(key_codes.EKey6, lambda self=self: self.move(1))
        except:
            pass
        self.load_dir()
        self.update_menu()

    def update_menu(self):
        n = len(self.marked)
        appuifw.app.menu = [(u"Send marked (%d)" % n, self.finish),
                            (u"Mark all photos here", self.mark_all),
                            (u"Unmark all", self.unmark_all),
                            (u"List view", self.list_view),
                            (u"Cancel", self.cancel)]
        if n:
            title = u"%d marked" % n
        else:
            title = to_u(self.path)[-28:]
        appuifw.app.title = title

    def stop_loader(self):
        self.loading = 0
        if self.timer is not None:
            try:
                self.timer.cancel()
            except:
                pass
            self.timer = None

    def release(self):
        if self.closed:
            return 0
        self.closed = 1
        self.stop_loader()
        self.cache = {}
        self.cache_order = []
        return 1

    def close(self):
        if self.release():
            self.app.restore_main()

    def cancel(self):
        self.close()

    def list_view(self):
        if self.release():
            self.app.switch_to_list(self.path, self.marked)

    def finish(self):
        paths = self.marked.keys()
        if not paths:
            cur = self.current_photo()
            if cur is None:
                appuifw.note(u"Mark photos with the centre key first.", "info")
                return
            paths = [cur]
        paths.sort()
        self.close()
        self.on_done(paths)

    # ---- folder contents

    def at_root(self):
        return self.path == self.root or len(self.path) <= 3

    def load_dir(self):
        self.stop_loader()
        try:
            names = os.listdir(self.path)
        except:
            appuifw.note(u"Cannot open " + to_u(self.path), "error")
            names = []
        dirs = []
        imgs = []
        for n in names:
            if n[:1] == "_" or n[:1] == ".":
                continue  # hidden system folders like _PAlbTN
            if os.path.isdir(self.path + n):
                dirs.append(n)
            elif ext_in(n, IMAGE_EXT):
                imgs.append(n)
        dirs.sort()
        imgs.sort()
        self.entries = []
        if not self.at_root():
            self.entries.append((u"..", None, "up"))
        for n in dirs:
            self.entries.append((to_u(n), n, "dir"))
        for n in imgs:
            self.entries.append((to_u(n), n, "img"))
        self.cur = 0
        self.top_row = 0
        self.redraw(None)
        self.start_loader()

    def current(self):
        if 0 <= self.cur < len(self.entries):
            return self.entries[self.cur]
        return None

    def current_photo(self):
        e = self.current()
        if e is None or e[2] != "img":
            return None
        return self.path + e[1]

    # ---- layout

    def canvas_size(self):
        try:
            return self.canvas.size
        except:
            return (240, 234)

    def columns(self):
        w, h = self.canvas_size()
        cols = int(w / GRID_CELL)
        if cols < 1:
            cols = 1
        return cols

    def cell_size(self):
        w, h = self.canvas_size()
        cw = int(w / self.columns())
        return (cw, cw)

    def visible_rows(self):
        w, h = self.canvas_size()
        cw, ch = self.cell_size()
        rows = int(h / ch)
        if rows < 1:
            rows = 1
        return rows

    def keep_visible(self):
        cols = self.columns()
        rows = self.visible_rows()
        row = self.cur / cols
        if row < self.top_row:
            self.top_row = row
        if row >= self.top_row + rows:
            self.top_row = row - rows + 1

    # ---- keys

    def move(self, d):
        n = len(self.entries)
        if not n:
            return
        i = self.cur + d
        if i < 0:
            i = 0
        if i > n - 1:
            i = n - 1
        self.cur = i
        self.moved()

    def move_row(self, d):
        n = len(self.entries)
        if not n:
            return
        cols = self.columns()
        i = self.cur + d * cols
        if i < 0:
            return  # top row: stay
        if i > n - 1:
            # moving down into a short last row: go to its last tile
            if self.cur / cols < (n - 1) / cols:
                i = n - 1
            else:
                return
        self.cur = i
        self.moved()

    def moved(self):
        self.keep_visible()
        self.redraw(None)
        self.start_loader()

    def activate(self):
        e = self.current()
        if e is None:
            return
        if e[2] == "up":
            self.up()
        elif e[2] == "dir":
            self.path = self.path + e[1] + "\\"
            self.load_dir()
        else:
            self.toggle(self.path + e[1])

    def toggle(self, p):
        if self.marked.has_key(p):
            del self.marked[p]
        else:
            self.marked[p] = 1
        self.update_menu()
        self.redraw(None)

    def mark_all(self):
        for e in self.entries:
            if e[2] == "img":
                self.marked[self.path + e[1]] = 1
        self.update_menu()
        self.redraw(None)

    def unmark_all(self):
        self.marked.clear()
        self.update_menu()
        self.redraw(None)

    def up(self):
        if self.at_root():
            return
        p = self.path[:-1]
        self.path = p[:p.rfind("\\") + 1]
        self.load_dir()

    def back(self):
        if not self.at_root():
            self.up()
        else:
            self.cancel()

    # ---- lazy thumbnail loading

    def next_to_load(self):
        cols = self.columns()
        first = self.top_row * cols
        last = first + self.visible_rows() * cols
        i = first
        while i < last and i < len(self.entries):
            e = self.entries[i]
            if e[2] == "img" and not self.cache.has_key(self.path + e[1]):
                return self.path + e[1]
            i = i + 1
        return None

    def start_loader(self):
        if self.closed or self.loading:
            return
        if self.next_to_load() is None:
            return
        self.loading = 1
        self.schedule()

    def schedule(self):
        try:
            self.timer = e32.Ao_timer()
            self.timer.after(0.05, self.load_step)
        except:
            self.loading = 0

    def load_step(self):
        self.timer = None
        if self.closed:
            self.loading = 0
            return
        p = self.next_to_load()
        if p is None:
            self.loading = 0
            return
        img = None
        try:
            img = self.thumbnail(p)
        except:
            try:
                self.app.log(u"grid thumb: " + err_text())
            except:
                pass
        self.remember(p, img)
        self.redraw(None)
        if self.next_to_load() is None:
            self.loading = 0
        else:
            self.schedule()

    def remember(self, p, img):
        if not self.cache.has_key(p):
            self.cache_order.append(p)
        self.cache[p] = img
        while len(self.cache_order) > GRID_CACHE:
            old = self.cache_order[0]
            del self.cache_order[0]
            try:
                del self.cache[old]
            except:
                pass

    def fit(self, img):
        cw, ch = self.cell_size()
        try:
            return img.resize((cw - 8, ch - 8), keepaspect=1)
        except:
            return img

    def thumbnail(self, p):
        t = exif_thumb(p)
        if t:
            try:
                tmp = temp_dir() + "retrosend_grid.jpg"
                f = open(tmp, "wb")
                f.write(t)
                f.close()
                return self.fit(graphics.Image.open(tmp))
            except:
                pass
        try:
            dims = graphics.Image.inspect(p)["size"]
        except:
            return None
        if dims[0] * dims[1] > 1300000:
            return None  # too big to decode on the phone
        return self.fit(graphics.Image.open(p))

    # ---- drawing

    def redraw(self, rect):
        c = self.canvas
        if c is None or self.closed:
            return
        try:
            self.draw(c)
        except:
            try:
                self.app.log(u"grid draw: " + err_text())
            except:
                pass

    def draw(self, c):
        BLUE = 0x146EDC
        w, h = self.canvas_size()
        cols = self.columns()
        cw, ch = self.cell_size()
        rows = self.visible_rows()
        c.clear(0xFFFFFF)
        if not self.entries:
            c.text((8, 24), u"(no photos or folders here)", fill=0x7A8CA5, font="dense")
            return
        i = self.top_row * cols
        last = i + rows * cols
        while i < last and i < len(self.entries):
            label, name, kind = self.entries[i]
            col = i % cols
            row = i / cols - self.top_row
            x = col * cw
            y = row * ch
            sel = (i == self.cur)
            if kind == "img":
                p = self.path + name
                c.rectangle((x + 2, y + 2, x + cw - 2, y + ch - 2), fill=0xEEF3FA)
                img = self.cache.get(p)
                if img is not None:
                    iw, ih = img.size
                    c.blit(img, target=(x + (cw - iw) / 2, y + (ch - ih) / 2))
                else:
                    ext = to_u(name[name.rfind(".") + 1:]).upper()
                    if not self.cache.has_key(p):
                        ext = u"..."
                    c.text((x + 8, y + ch / 2 + 5), ext, fill=0x7A8CA5, font="dense")
                if self.marked.has_key(p):
                    c.rectangle((x + 1, y + 1, x + cw - 1, y + ch - 1), outline=BLUE)
                    c.rectangle((x + 3, y + 3, x + cw - 3, y + ch - 3), outline=BLUE)
                    c.rectangle((x + cw - 20, y + 4, x + cw - 4, y + 20), fill=BLUE)
                    c.text((x + cw - 16, y + 17), u"x", fill=0xFFFFFF, font="dense")
            else:
                c.rectangle((x + 2, y + 2, x + cw - 2, y + ch - 2), fill=0xFFF4D6,
                            outline=0xE0C070)
                if kind == "up":
                    c.text((x + cw / 2 - 8, y + ch / 2 + 5), u"..", fill=0x202020,
                           font="dense")
                else:
                    c.text((x + 6, y + 18), u"Folder", fill=0x8A6A20, font="dense")
                    c.text((x + 6, y + ch / 2 + 8), clip(label, (cw - 10) / 6),
                           fill=0x202020, font="dense")
            if sel:
                c.rectangle((x, y, x + cw, y + ch), outline=0x000000)
                c.rectangle((x + 1, y + 1, x + cw - 1, y + ch - 1), outline=0x000000)
            i = i + 1
