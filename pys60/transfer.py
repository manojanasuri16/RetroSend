# Transfer progress screen for RetroSend (pasted into the app by build_sis.sh).
# Python 2.2 compatible. Uses the app module's helpers at call time:
# appuifw, e32, key_codes, to_u, human_size, human_duration, clip, err_text.
import time

BLUE = 0x146EDC
LIGHT = 0xEEF3FA
TEXT = 0x202020
GREY = 0x7A8CA5
WHITE = 0xFFFFFF
GREEN = 0x1E9E4A
RED = 0xD03030


def wrap_text(s, n):
    """Splits s into lines of at most n characters, at spaces where possible."""
    s = to_u(s)
    n = int(n)
    if n < 4:
        n = 4
    lines = []
    for para in s.split(u"\n"):
        words = para.split(u" ")
        line = u""
        for w in words:
            while len(w) > n:
                if line:
                    lines.append(line)
                    line = u""
                lines.append(w[:n])
                w = w[n:]
            if not line:
                line = w
            elif len(line) + 1 + len(w) <= n:
                line = line + u" " + w
            else:
                lines.append(line)
                line = w
        lines.append(line)
    return lines


class TransferScreen:
    def __init__(self, app):
        self.app = app
        self.canvas = None
        self.shown = 0
        self.state = "idle"     # "running", "done"
        self.kind = "send"
        self.peer = u""
        self.nfiles = 1
        self.total = 0
        self.done = 0
        self.name = u""
        self.names = {}         # name -> file number
        self.fileno = 0
        self.samples = []       # (time, bytes) of the last ~3 s
        self.last_draw = 0
        self.result = u""
        self.ok = 1
        self.timer = None
        self.tick = 0

    # ---- showing / hiding

    def visible(self):
        return self.shown

    def show_canvas(self):
        a = appuifw.app
        try:
            a.set_tabs([], None)
        except:
            pass
        self.canvas = appuifw.Canvas(redraw_callback=self.redraw)
        a.body = self.canvas
        try:
            self.canvas.bind(key_codes.EKeySelect, self.select)
        except:
            pass
        a.exit_key_handler = self.hide
        self.shown = 1

    def start(self, kind, peer, nfiles, total_bytes):
        self.cancel_timer()
        self.kind = kind
        self.peer = to_u(peer)
        self.nfiles = nfiles or 1
        self.total = total_bytes or 0
        self.done = 0
        self.name = u""
        self.names = {}
        self.fileno = 0
        self.samples = [(time.time(), 0)]
        self.last_draw = 0
        self.state = "running"
        self.result = u""
        self.show_canvas()
        self.set_menu()
        self.draw_now()

    def set_menu(self):
        if self.state == "running":
            if self.kind == "send":
                menu = [(u"Cancel sending", self.app.cancel_send)]
            else:
                menu = [(u"Stop receiving", self.app.stop_receiving)]
            menu.append((u"Hide (keep running)", self.hide))
        else:
            menu = [(u"OK", self.hide)]
        appuifw.app.menu = menu

    def hide(self):
        self.cancel_timer()
        if not self.shown:
            return
        self.shown = 0
        self.canvas = None
        if self.state == "done":
            self.state = "idle"
        self.app.restore_main()

    def select(self):
        if self.state == "done":
            self.hide()

    def cancel_timer(self):
        if self.timer is not None:
            try:
                self.timer.cancel()
            except:
                pass
            self.timer = None

    # ---- progress

    def update(self, name, done, total):
        now = time.time()
        if name:
            name = to_u(name)
            if not self.names.has_key(name):
                self.fileno = self.fileno + 1
                self.names[name] = self.fileno
            self.name = name
        if total:
            self.total = total
        self.done = done
        self.samples.append((now, done))
        while len(self.samples) > 2 and now - self.samples[0][0] > 3:
            del self.samples[0]
        if self.total and done >= self.total:
            self.draw_now()
        elif now - self.last_draw >= 0.25:
            self.draw_now()

    def rate(self):
        """Bytes per second over the last ~3 seconds, or 0 if unknown."""
        if len(self.samples) < 2:
            return 0
        t0, b0 = self.samples[0]
        t1, b1 = self.samples[-1]
        if t1 - t0 < 0.3 or b1 < b0:
            return 0
        return (b1 - b0) / (t1 - t0)

    def speed_text(self):
        r = self.rate()
        if r <= 0:
            return u""
        s = human_size(r) + u"/s"
        if self.total and self.done < self.total:
            s = s + u"  " + human_duration(int((self.total - self.done) / r)) + u" left"
        return s

    def finish(self, message, ok):
        self.result = to_u(message)
        self.ok = ok
        self.state = "done"
        if not self.shown:
            self.show_canvas()
        self.set_menu()
        self.draw_now()
        self.cancel_timer()
        try:
            self.timer = e32.Ao_timer()
            self.timer.after(4, self.auto_hide)
        except:
            self.timer = None

    def auto_hide(self):
        self.timer = None
        if self.state == "done" and self.shown:
            self.hide()

    # ---- drawing

    def draw_now(self):
        self.last_draw = time.time()
        self.redraw(None)

    def redraw(self, rect):
        c = self.canvas
        if c is None or not self.shown:
            return
        try:
            self.draw(c)
        except:
            try:
                self.app.log(u"transfer draw: " + err_text())
            except:
                pass

    def size(self):
        try:
            return self.canvas.size
        except:
            return (240, 234)

    def arrow(self, c, x, y, up):
        # simple arrow icon, 18x20 at (x, y)
        if up:
            pts = [(x + 9, y), (x + 18, y + 9), (x + 12, y + 9), (x + 12, y + 20),
                   (x + 6, y + 20), (x + 6, y + 9), (x, y + 9)]
        else:
            pts = [(x + 9, y + 20), (x + 18, y + 11), (x + 12, y + 11), (x + 12, y),
                   (x + 6, y), (x + 6, y + 11), (x, y + 11)]
        c.polygon(pts, fill=WHITE, outline=WHITE)

    def draw(self, c):
        w, h = self.size()
        cols = (w - 16) / 6
        c.clear(WHITE)
        # header band
        c.rectangle((0, 0, w, 34), fill=BLUE)
        self.arrow(c, 8, 7, self.kind == "send")
        if self.kind == "send":
            title = u"Sending to " + self.peer
        else:
            title = u"Receiving from " + self.peer
        c.text((34, 23), clip(title, (w - 40) / 7), fill=WHITE, font="title")
        if self.state == "done":
            self.draw_result(c, w, h, cols)
            return
        y = 56
        name = self.name or u"Waiting..."
        c.text((8, y), clip(name, cols), fill=TEXT, font="dense")
        y = y + 16
        if self.nfiles > 1:
            n = self.fileno
            if n < 1:
                n = 1
            c.text((8, y), u"File %d of %d" % (n, self.nfiles), fill=GREY, font="dense")
        y = y + 12
        # progress bar
        bx1 = 8
        bx2 = w - 8
        by1 = y
        by2 = y + 22
        c.rectangle((bx1, by1, bx2, by2), outline=BLUE, fill=LIGHT)
        c.rectangle((bx1 + 1, by1 - 1, bx2 - 1, by1), outline=WHITE)  # soften corners
        if self.total:
            pct = int(self.done * 100 / self.total)
            if pct > 100:
                pct = 100
            fw = int((bx2 - bx1 - 4) * pct / 100)
            if fw > 0:
                c.rectangle((bx1 + 2, by1 + 2, bx1 + 2 + fw, by2 - 2), fill=BLUE)
            label = u"%d%%" % pct
            col = TEXT
            if pct >= 50:
                col = WHITE
            c.text(((bx1 + bx2) / 2 - 10, by2 - 6), label, fill=col, font="dense")
        else:
            # indeterminate: a moving stripe
            self.tick = (self.tick + 1) % 8
            sw = (bx2 - bx1) / 4
            sx = bx1 + 2 + ((bx2 - bx1 - sw - 4) * self.tick) / 7
            c.rectangle((sx, by1 + 2, sx + sw, by2 - 2), fill=BLUE)
        y = by2 + 18
        if self.total:
            c.text((8, y), human_size(self.done) + u" of " + human_size(self.total),
                   fill=TEXT, font="dense")
        else:
            c.text((8, y), u"Waiting...", fill=GREY, font="dense")
        y = y + 16
        sp = self.speed_text()
        if sp:
            c.text((8, y), sp, fill=TEXT, font="dense")
        # footer hint
        c.rectangle((0, h - 18, w, h), fill=LIGHT)
        c.text((6, h - 5), clip(u"Options: Cancel   Right: Hide", cols), fill=GREY,
               font="dense")

    def draw_result(self, c, w, h, cols):
        cx = w / 2
        cy = 70
        if self.ok:
            c.ellipse((cx - 22, cy - 22, cx + 22, cy + 22), fill=GREEN)
            c.line([(cx - 11, cy), (cx - 3, cy + 9), (cx + 12, cy - 9)], outline=WHITE, width=5)
        else:
            c.ellipse((cx - 22, cy - 22, cx + 22, cy + 22), fill=RED)
            c.line([(cx - 9, cy - 9), (cx + 9, cy + 9)], outline=WHITE, width=5)
            c.line([(cx - 9, cy + 9), (cx + 9, cy - 9)], outline=WHITE, width=5)
        y = cy + 40
        for line in wrap_text(self.result, cols)[:5]:
            c.text((8, y), line, fill=TEXT, font="dense")
            y = y + 15
        c.rectangle((0, h - 18, w, h), fill=LIGHT)
        c.text((6, h - 5), u"Centre: OK", fill=GREY, font="dense")
