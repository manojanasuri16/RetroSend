# File picker screen for RetroSend (pasted into the app by build_sis.sh).
# Python 2.2 compatible. Uses the app module's helpers at call time
# (to_u, human_size, read_id3, video_info, graphics, key_codes, ...).
import os

# ---------------------------------------------------------------- file picker
#
# A Canvas screen: preview box on top (photo thumbnail, album art, video
# length), a list with checkboxes below. Up/Down move, centre key opens a
# folder or marks a file, Left goes up a folder, Options > Send marked.

IMAGE_EXT = ["jpg", "jpeg", "png", "gif", "bmp"]
AUDIO_EXT = ["mp3", "m4a", "aac", "amr", "wav", "wma"]
VIDEO_EXT = ["mp4", "3gp", "m4v", "3g2"]


def file_ext(name):
    i = name.rfind(".")
    if i < 0:
        return ""
    return name[i + 1:].lower()


def ext_in(name, lst):
    e = file_ext(name)
    for x in lst:
        if x == e:
            return 1
    return 0


def exif_thumb(path):
    """The small JPEG preview that cameras store inside the photo, or None."""
    try:
        f = open(path, "rb")
        head = f.read(65536)
        f.close()
    except:
        return None
    if head[:2] != "\xff\xd8":
        return None
    # FFD8 followed by FF: a real start marker (plain FFD8 can occur in EXIF data)
    i = head.find("\xff\xd8\xff", 2)
    if i < 0:
        return None
    j = head.find("\xff\xd9", i)
    if j < 0:
        return None
    return head[i:j + 2]


def temp_dir():
    for d in ["D:\\", "C:\\Data\\", "E:\\"]:
        if os.path.isdir(d):
            return d
    return ""


class Picker:
    def __init__(self, app, start, on_done, view_only=0, marked=None, root=None):
        self.app = app
        self.path = start
        self.root = root or start
        self.on_done = on_done
        self.view_only = view_only
        if marked is None:
            marked = {}
        self.marked = marked    # path -> 1 (shared with the photo grid)
        self.names = {}         # path -> name to send, e.g. u"Album/song.mp3"
        self.entries = []       # (label, name, is_dir)
        self.cur = 0
        self.top = 0
        self.cache = {}         # path -> image or None
        self.cache_order = []
        self.info = {}          # path -> list of text lines
        self.timer = None
        self.canvas = None
        self.closed = 0

    # ---- set up / tear down

    def show(self):
        a = appuifw.app
        self.saved = (a.body, a.menu, a.exit_key_handler, a.title)
        try:
            a.set_tabs([], None)
        except:
            pass
        self.canvas = appuifw.Canvas(redraw_callback=self.redraw)
        a.body = self.canvas
        a.exit_key_handler = self.back
        c = self.canvas
        c.bind(key_codes.EKeyUpArrow, lambda self=self: self.move(-1))
        c.bind(key_codes.EKeyDownArrow, lambda self=self: self.move(1))
        c.bind(key_codes.EKeySelect, self.activate)
        c.bind(key_codes.EKeyLeftArrow, self.up)
        c.bind(key_codes.EKeyRightArrow, self.activate)
        try:
            c.bind(key_codes.EKey5, self.activate)
            c.bind(key_codes.EKey2, lambda self=self: self.move(-1))
            c.bind(key_codes.EKey8, lambda self=self: self.move(1))
        except:
            pass
        self.load_dir()
        self.update_menu()

    def update_menu(self):
        n = len(self.marked)
        menu = [(u"Send marked (%d)" % n, self.finish)]
        if self.view_only:
            menu.append((u"Open file", self.open_current))
            menu.append((u"Mark / unmark", self.toggle_current))
        else:
            menu.append((u"Mark / unmark", self.toggle_current))
            menu.append((u"Open file", self.open_current))
        menu.append((u"Mark whole folder", self.mark_folder))
        menu.append((u"Mark all files here", self.mark_all))
        menu.append((u"Unmark all", self.unmark_all))
        menu.append((u"Grid view (photos)", self.to_grid))
        menu.append((u"Close", self.cancel))
        appuifw.app.menu = menu
        title = u"%d marked" % n
        if n == 0:
            title = to_u(self.path)[-28:]
        appuifw.app.title = title

    def close(self):
        if self.closed:
            return
        self.closed = 1
        if self.timer is not None:
            try:
                self.timer.cancel()
            except:
                pass
        self.cache = {}
        self.app.restore_main()

    def cancel(self):
        self.close()

    def finish(self):
        paths = self.marked.keys()
        if not paths:
            cur = self.current_file()
            if cur is None:
                appuifw.note(u"Mark files with the centre key first.", "info")
                return
            paths = [cur]
        paths.sort()
        names = self.names
        self.close()
        self.on_done(paths, names)

    def open_current(self):
        p = self.current_file()
        if p is None:
            appuifw.note(u"Select a file first.", "info")
            return
        self.app.open_file(p)

    def to_grid(self):
        marked = self.marked
        path = self.path
        self.close()
        self.app.switch_to_grid(path, marked, self.root)

    def mark_folder(self):
        """Marks every file in the selected folder (and its subfolders)."""
        e = self.current()
        if e is None or not e[2] or e[1] is None:
            appuifw.note(u"Select a folder first (not ..).", "info")
            return
        top = self.path + e[1] + "\\"
        stack = [(top, to_u(e[1]) + u"/")]
        count = 0
        while stack and count < 500:
            d, prefix = stack[0]
            del stack[0]
            try:
                names = os.listdir(d)
            except:
                continue
            names.sort()
            for n in names:
                if n[:1] == "_" or n[:1] == ".":
                    continue
                full = d + n
                if os.path.isdir(full):
                    stack.append((full + "\\", prefix + to_u(n) + u"/"))
                elif count < 500:
                    self.marked[full] = 1
                    self.names[full] = prefix + to_u(n)
                    count = count + 1
        appuifw.note(u"Marked %d file(s) in %s" % (count, to_u(e[1])), "info")
        self.update_menu()
        self.redraw(None)

    # ---- folder contents

    def load_dir(self):
        try:
            names = os.listdir(self.path)
        except:
            appuifw.note(u"Cannot open " + to_u(self.path), "error")
            names = []
        dirs = []
        files = []
        for n in names:
            if n[:1] == "_" or n[:1] == ".":
                continue  # hidden system folders like _PAlbTN
            if os.path.isdir(self.path + n):
                dirs.append(n)
            else:
                files.append(n)
        dirs.sort()
        files.sort()
        self.entries = []
        if self.path != self.root and len(self.path) > 3:
            self.entries.append((u"..", None, 1))
        for n in dirs:
            self.entries.append((to_u(n), n, 1))
        for n in files:
            self.entries.append((to_u(n), n, 0))
        self.cur = 0
        self.top = 0
        self.schedule_preview()
        self.redraw(None)

    def current(self):
        if 0 <= self.cur < len(self.entries):
            return self.entries[self.cur]
        return None

    def current_file(self):
        e = self.current()
        if e is None or e[2]:
            return None
        return self.path + e[1]

    # ---- keys

    def move(self, d):
        if not self.entries:
            return
        self.cur = (self.cur + d) % len(self.entries)
        self.schedule_preview()
        self.redraw(None)

    def activate(self):
        e = self.current()
        if e is None:
            return
        if e[2]:
            if e[1] is None:
                self.up()
            else:
                self.path = self.path + e[1] + "\\"
                self.load_dir()
            return
        if self.view_only:
            self.open_current()
        else:
            self.toggle_current()

    def toggle_current(self):
        p = self.current_file()
        if p is None:
            return
        if self.marked.has_key(p):
            del self.marked[p]
        else:
            self.marked[p] = 1
        self.update_menu()
        self.redraw(None)

    def mark_all(self):
        for e in self.entries:
            if not e[2]:
                self.marked[self.path + e[1]] = 1
        self.update_menu()
        self.redraw(None)

    def unmark_all(self):
        self.marked.clear()
        self.names.clear()
        self.update_menu()
        self.redraw(None)

    def up(self):
        if self.path == self.root or len(self.path) <= 3:
            return
        p = self.path[:-1]
        self.path = p[:p.rfind("\\") + 1]
        self.load_dir()

    def back(self):
        if self.path != self.root and len(self.path) > 3:
            self.up()
        else:
            self.cancel()

    # ---- preview

    def schedule_preview(self):
        if self.timer is not None:
            try:
                self.timer.cancel()
            except:
                pass
        p = self.current_file()
        if p is None or self.cache.has_key(p):
            return
        try:
            self.timer = e32.Ao_timer()
            self.timer.after(0.3, self.load_preview)  # wait until scrolling stops
        except:
            self.load_preview()

    def load_preview(self):
        p = self.current_file()
        if p is None or self.closed or self.cache.has_key(p):
            return
        img = None
        lines = []
        name = os.path.basename(p)
        try:
            size = os.path.getsize(p)
        except:
            size = 0
        lines.append(human_size(size))
        try:
            if ext_in(name, IMAGE_EXT):
                img = self.image_preview(p, size, lines)
            elif ext_in(name, AUDIO_EXT):
                img = self.audio_preview(p, lines)
            elif ext_in(name, VIDEO_EXT):
                secs = video_info(p)
                if secs:
                    lines.append(u"Video " + human_duration(secs))
                else:
                    lines.append(u"Video")
        except:
            self.app.log(u"preview: " + err_text())
        self.remember(p, img, lines)
        self.redraw(None)

    def remember(self, p, img, lines):
        self.cache[p] = img
        self.info[p] = lines
        self.cache_order.append(p)
        if len(self.cache_order) > 12:
            old = self.cache_order[0]
            del self.cache_order[0]
            try:
                del self.cache[old]
            except:
                pass

    def fit(self, img):
        w, h = self.box_size()
        try:
            return img.resize((w, h), keepaspect=1)
        except:
            return img

    def open_bytes(self, data, ext):
        tmp = temp_dir() + "retrosend_preview." + ext
        f = open(tmp, "wb")
        f.write(data)
        f.close()
        return graphics.Image.open(tmp)

    def image_preview(self, p, size, lines):
        t = exif_thumb(p)
        if t:
            try:
                return self.fit(self.open_bytes(t, "jpg"))
            except:
                pass
        try:
            dims = graphics.Image.inspect(p)["size"]
            lines.append(u"%dx%d" % (dims[0], dims[1]))
            if dims[0] * dims[1] > 1300000:
                lines.append(u"(too big to preview)")
                return None
        except:
            if size > 600000:
                return None
        return self.fit(graphics.Image.open(p))

    def audio_preview(self, p, lines):
        tag = read_id3(p)
        if tag.get(u"title"):
            lines.append(tag[u"title"])
        if tag.get(u"artist"):
            lines.append(tag[u"artist"])
        if tag.get(u"album"):
            lines.append(tag[u"album"])
        if tag.get("art"):
            try:
                return self.fit(self.open_bytes(tag["art"], tag.get("art_ext") or "jpg"))
            except:
                lines.append(u"(art not readable)")
        return None

    # ---- drawing

    def box_size(self):
        w, h = self.canvas_size()
        ph = self.preview_height()
        bw = int(w * 45 / 100)
        return (bw - 6, ph - 10)

    def canvas_size(self):
        try:
            return self.canvas.size
        except:
            return (240, 234)

    def preview_height(self):
        w, h = self.canvas_size()
        ph = int((h - BAR_H - FOOT_H) * 42 / 100)
        if ph > 130:
            ph = 130
        return ph

    def list_rows(self):
        w, h = self.canvas_size()
        rows = (h - BAR_H - self.preview_height() - FOOT_H - 2) / ROW_H
        if rows < 1:
            rows = 1
        return rows

    def header_text(self):
        """(left, right) of the header bar: folder name and marked summary."""
        return (folder_name(self.path), marked_summary(self.marked))

    def footer_text(self):
        if self.view_only:
            return u"Centre: open   Options: more"
        return u"Centre: mark   Options: send"

    def redraw(self, rect):
        c = self.canvas
        if c is None or self.closed:
            return
        try:
            self.draw(c)
        except:
            self.app.log(u"draw: " + err_text())

    def draw(self, c):
        w, h = self.canvas_size()
        ph = self.preview_height()
        c.clear(WHITE)
        left, right = self.header_text()
        draw_header(c, w, left, right)
        top = BAR_H
        # preview area
        c.rectangle((0, top, w, top + ph), fill=LIGHT)
        bw, bh = self.box_size()
        bx = 4
        by = top + 5
        draw_card(c, bx, by, bx + bw, by + bh, 0xB0C4DE, WHITE)
        p = self.current_file()
        e = self.current()
        tx = bx + bw + 8
        chars = (w - tx - 2) / 6
        if p is not None:
            img = self.cache.get(p)
            if img is not None:
                iw, ih = img.size
                c.blit(img, target=(bx + (bw - iw) / 2, by + (bh - ih) / 2))
            else:
                label, bg, fg = badge_for(os.path.basename(p), 0)
                if not self.cache.has_key(p):
                    label = u"..."
                draw_badge(c, bx + bw / 2 - 14, by + bh / 2 - 7, label, bg, fg)
            name = to_u(os.path.basename(p))
            y = top + 18
            if len(name) * 8 <= w - tx - 2:
                c.text((tx, y), name, fill=TEXT, font="title")
            else:
                c.text((tx, y), clip(name, chars), fill=TEXT, font="dense")
            y = y + 17
            for line in self.info.get(p, [])[:5]:
                c.text((tx, y), clip(line, chars), fill=GREY, font="dense")
                y = y + 15
            if self.marked.has_key(p):
                draw_checkbox(c, tx, top + ph - 16, 1, BLUE)
                c.text((tx + 14, top + ph - 6), u"marked", fill=BLUE, font="dense")
        elif e is not None:
            draw_folder(c, bx + bw / 2 - 16, by + bh / 2 - 12, 32, 24)
            c.text((tx, top + 24), u"Folder", fill=GREY, font="dense")
            c.text((tx, top + 40), clip(e[0], chars), fill=TEXT, font="dense")
        # list
        rows = self.list_rows()
        if self.cur < self.top:
            self.top = self.cur
        if self.cur >= self.top + rows:
            self.top = self.cur - rows + 1
        y0 = top + ph + 2
        y = y0
        i = self.top
        while i < len(self.entries) and i < self.top + rows:
            label, name, is_dir = self.entries[i]
            full = None
            if name is not None:
                full = self.path + name
            sel = (i == self.cur)
            marked = (not is_dir) and self.marked.has_key(full)
            fg = TEXT
            sub = GREY
            if sel:
                c.rectangle((0, y, w, y + ROW_H), fill=BLUE)
                fg = WHITE
                sub = 0xD6E4F7
            elif marked:
                c.rectangle((0, y, w, y + ROW_H), fill=TINT)
            x = 4
            if not is_dir:
                draw_checkbox(c, x, y + 4, marked, fg)
            x = x + 14
            blabel, bg, bfg = badge_for(label, is_dir)
            if name is None:
                blabel = u"UP"
            draw_badge(c, x, y + 3, blabel, bg, bfg)
            x = x + 32
            size = u""
            if not is_dir:
                size = human_size(file_size(full))
            sw = len(size) * 6
            room = (w - x - sw - 12) / 6
            c.text((x, y + ROW_H - 5), clip(label, room), fill=fg, font="dense")
            if size:
                c.text((w - sw - 8, y + ROW_H - 5), size, fill=sub, font="dense")
            y = y + ROW_H
            i = i + 1
        if len(self.entries) > rows:
            draw_scrollbar(c, w, y0, y0 + rows * ROW_H, self.top, rows, len(self.entries))
        if not self.entries:
            msg = u"This folder is empty"
            c.text(((w - len(msg) * 6) / 2, y0 + (h - y0 - FOOT_H) / 2), msg, fill=GREY,
                   font="dense")
        draw_footer(c, w, h, self.footer_text())


# ---------------------------------------------------------------- look
#
# Shared by the picker and the photo grid: one colour theme, a header bar,
# a footer hint bar, type badges, checkboxes and a scroll indicator.

BLUE = 0x146EDC
LIGHT = 0xEEF3FA
TEXT = 0x202020
GREY = 0x7A8CA5
TINT = 0xDCE9FB
WHITE = 0xFFFFFF
SCROLL = 0x9FB6D6
BAR_H = 18
FOOT_H = 16
ROW_H = 20

SIZE_CACHE = {}   # path -> size in bytes (marked totals, row sizes)


def file_size(path):
    if path is None:
        return 0
    if SIZE_CACHE.has_key(path):
        return SIZE_CACHE[path]
    try:
        n = os.path.getsize(path)
    except:
        n = 0
    if len(SIZE_CACHE) > 2000:
        SIZE_CACHE.clear()
    SIZE_CACHE[path] = n
    return n


def marked_total(marked):
    total = 0
    for p in marked.keys():
        total = total + file_size(p)
    return total


def marked_summary(marked):
    """u"3 marked \u00b7 4.2 MB", or u"" when nothing is marked."""
    n = len(marked)
    if not n:
        return u""
    return u"%d marked \u00b7 %s" % (n, human_size(marked_total(marked)))


def folder_name(path):
    p = to_u(path)
    while p[-1:] == u"\\" or p[-1:] == u"/":
        p = p[:-1]
    i = p.rfind(u"\\")
    j = p.rfind(u"/")
    if j > i:
        i = j
    name = p[i + 1:]
    if not name:
        name = p
    if len(name) <= 2 and name[-1:] == u":":
        name = name + u"\\"
    return name


def badge_for(name, is_dir):
    """(label, background, text colour) for a row's type badge."""
    if is_dir:
        return (u"DIR", 0xF1C40F, TEXT)
    if ext_in(name, IMAGE_EXT):
        return (u"IMG", BLUE, WHITE)
    if ext_in(name, AUDIO_EXT):
        return (u"MUS", 0x8E44AD, WHITE)
    if ext_in(name, VIDEO_EXT):
        return (u"VID", 0xE67E22, WHITE)
    e = to_u(file_ext(name)).upper()[:3]
    if not e:
        e = u"FIL"
    return (e, GREY, WHITE)


def draw_header(c, w, left, right):
    c.rectangle((0, 0, w, BAR_H), fill=BLUE)
    room = (w - 8) / 6
    if right:
        room = room - len(right) - 2
        c.text((w - len(right) * 6 - 4, BAR_H - 5), right, fill=WHITE, font="dense")
    c.text((4, BAR_H - 5), clip(left, room), fill=WHITE, font="dense")


def draw_footer(c, w, h, text):
    c.rectangle((0, h - FOOT_H, w, h), fill=LIGHT)
    c.line((0, h - FOOT_H, w, h - FOOT_H), outline=0xC8D4E6)
    c.text((4, h - 4), clip(text, (w - 8) / 6), fill=GREY, font="dense")


def draw_card(c, x1, y1, x2, y2, border, fill):
    """A box with cut corners, which reads as rounded on a small screen."""
    c.rectangle((x1 + 2, y1, x2 - 2, y2), fill=border)
    c.rectangle((x1, y1 + 2, x2, y2 - 2), fill=border)
    c.rectangle((x1 + 2, y1 + 1, x2 - 2, y2 - 1), fill=fill)
    c.rectangle((x1 + 1, y1 + 2, x2 - 1, y2 - 2), fill=fill)


def draw_badge(c, x, y, label, bg, fg):
    c.rectangle((x, y, x + 28, y + 14), fill=bg)
    c.text((x + 4, y + 11), label, fill=fg, font="dense")


def draw_tick(c, x, y, s, colour):
    """A tick mark in an s x s square at (x, y)."""
    c.line((x + s / 5, y + s / 2, x + s * 2 / 5, y + s * 4 / 5), outline=colour, width=2)
    c.line((x + s * 2 / 5, y + s * 4 / 5, x + s * 4 / 5, y + s / 5), outline=colour, width=2)


def draw_checkbox(c, x, y, checked, colour):
    c.rectangle((x, y, x + 11, y + 11), outline=colour)
    if checked:
        draw_tick(c, x, y, 11, colour)


def draw_folder(c, x, y, w, h):
    c.rectangle((x, y, x + w * 2 / 5, y + h / 5), fill=0xD4A50C)
    c.rectangle((x, y + h / 5, x + w, y + h), fill=0xF1C40F)


def draw_scrollbar(c, w, y1, y2, first, shown, total):
    """A thin thumb on the right edge showing which part of the list is visible."""
    span = y2 - y1
    if total <= shown or span <= 0:
        return
    th = span * shown / total
    if th < 8:
        th = 8
    ty = y1 + (span - th) * first / (total - shown)
    c.rectangle((w - 3, y1, w, y2), fill=LIGHT)
    c.rectangle((w - 3, ty, w, ty + th), fill=SCROLL)


def on_off(flag):
    if flag:
        return u"ON"
    return u"OFF"


def entry_labels(entries):
    out = []
    for label, action in entries:
        out.append(label)
    return out


def clip(s, n):
    s = to_u(s)
    n = int(n)
    if n < 4:
        n = 4
    if len(s) > n:
        return s[:n - 1] + u"~"
    return s
