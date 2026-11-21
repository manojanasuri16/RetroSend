# ---------------------------------------------------------------- browser sharing
#
# Any phone or PC on the same Wi-Fi can open http://<phone ip>:53317/ in a
# web browser to download the shared files, upload files to the phone, or
# send a text message. No LocalSend needed on the other side.
#
# Uses only the async net/conn interface (single-threaded, never blocks)
# and streams files in 16 KB chunks. Pasted into retrosend.py at build
# time; it relies on retrosend's helpers (to_u, to_b, human_size,
# mime_type, safe_name, err_text, parse_query, url_quote, url_unquote,
# BodyDecoder, REASONS, os, time).

CHUNK = 16384


def esc(s):
    """HTML-escapes text; returns unicode."""
    s = to_u(s)
    s = s.replace(u"&", u"&amp;").replace(u"<", u"&lt;").replace(u">", u"&gt;")
    return s.replace(u'"', u"&quot;")


def ascii_name(name):
    out = []
    for ch in to_u(name):
        o = ord(ch)
        if o < 32 or o > 126 or ch == u'"' or ch == u"\\":
            out.append("_")
        else:
            out.append(str(ch))
    return "".join(out)


PAGE_HEAD = (u'<html><head><meta http-equiv="Content-Type" content="text/html; charset=utf-8">'
             u'<meta name="viewport" content="width=device-width">'
             u'<title>%s</title></head><body bgcolor="#ffffff">')
PAGE_TAIL = u'</body></html>'


def page(title, body):
    return (PAGE_HEAD % esc(title) + body + PAGE_TAIL).encode('utf-8')


class WebShare:
    def __init__(self, cfg, events, path_for):
        self.cfg = cfg
        self.ev = events
        self.path_for = path_for
        self.shared = []

    def set_shared(self, paths):
        self.shared = []
        for p in paths:
            self.shared.append(to_b(p))

    def handle(self, conn, ip, method, target, headers, body_start):
        WebRequest(self, conn, ip, method, target, headers, body_start).run()

    # ---- pages

    def index_html(self):
        alias = to_u(self.cfg.get("alias", u"RetroSend"))
        b = [u'<h2>%s</h2>' % esc(alias)]
        b.append(u'<h3>Download from this phone</h3>')
        if not self.shared:
            b.append(u'<p>Nothing shared. On the phone: Receive tab &gt; Browser sharing.</p>')
        else:
            b.append(u'<ul>')
            i = 0
            for p in self.shared:
                name = os.path.basename(p.replace("\\", "/"))
                try:
                    size = human_size(os.path.getsize(p))
                except:
                    size = u"?"
                b.append(u'<li><a href="/dl/%d/%s">%s</a> (%s)</li>' %
                         (i, to_u(url_quote(name)), esc(name), size))
                i = i + 1
            b.append(u'</ul>')
        b.append(u'<h3>Send files to this phone</h3>')
        b.append(u'<form method="post" action="/upload" enctype="multipart/form-data">'
                 u'<input type="file" name="f" multiple> '
                 u'<input type="submit" value="Upload"></form>')
        b.append(u'<h3>Send a text message</h3>')
        b.append(u'<form method="post" action="/text">'
                 u'<input type="text" name="msg" size="30"> '
                 u'<input type="submit" value="Send"></form>')
        b.append(u'<p><small>RetroSend</small></p>')
        return page(alias, u"".join(b))


class WebRequest:
    """One browser request on an already-accepted connection."""
    def __init__(self, ws, conn, ip, method, target, headers, body_start):
        self.ws = ws
        self.ev = ws.ev
        self.conn = conn
        self.ip = ip
        self.method = method
        self.headers = headers
        self.body_start = body_start
        q = target.find("?")
        if q >= 0:
            target = target[:q]
        self.path = target
        self.closed = 0
        self.f = None
        self.fpath = None

    def run(self):
        try:
            self.route()
        except:
            self.ev.log(u"web: " + err_text())
            self.abort_file()
            self.html(500, u"Error", u"<p>Error: %s</p>" % esc(err_text()))

    def route(self):
        m = self.method
        p = self.path
        if m == "GET" and (p == "/" or p == "/index.html"):
            self.send_all(self.response(200, "text/html; charset=utf-8",
                                        self.ws.index_html()))
        elif m == "GET" and p[:4] == "/dl/":
            self.download(p[4:])
        elif m == "POST" and p == "/upload":
            self.start_upload()
        elif m == "POST" and p == "/text":
            self.start_text()
        else:
            self.html(404, u"Not found", u'<p>Not found. <a href="/">Back</a></p>')

    # ---- responses

    def response(self, code, ctype, data, extra=""):
        head = ("HTTP/1.1 %d %s\r\nContent-Type: %s\r\nContent-Length: %d\r\n%s"
                "Connection: close\r\n\r\n" % (code, REASONS.get(code, "Status"), ctype,
                                              len(data), extra))
        return head + data

    def html(self, code, title, body):
        self.send_all(self.response(code, "text/html; charset=utf-8", page(title, body)))

    def send_all(self, data):
        if self.closed:
            return
        self.conn.send(data, self.close, self.failed)

    def close(self):
        if not self.closed:
            self.closed = 1
            try:
                self.conn.close()
            except:
                pass

    def failed(self, msg=None):
        self.abort_file()
        self.close()

    # ---- download

    def download(self, rest):
        slash = rest.find("/")
        if slash >= 0:
            rest = rest[:slash]
        try:
            idx = int(rest)
        except:
            idx = -1
        if idx < 0 or idx >= len(self.ws.shared):
            self.html(404, u"Not found", u'<p>No such file. <a href="/">Back</a></p>')
            return
        path = self.ws.shared[idx]
        try:
            size = os.path.getsize(path)
            self.f = open(path, "rb")
        except:
            self.html(404, u"Not found", u'<p>File is gone. <a href="/">Back</a></p>')
            return
        name = os.path.basename(path.replace("\\", "/"))
        self.dl_name = to_u(name)
        self.dl_size = size
        self.dl_sent = 0
        self.dl_last = 0
        disp = ("Content-Disposition: attachment; filename=\"%s\"; filename*=UTF-8''%s\r\n"
                % (ascii_name(name), url_quote(to_b(name))))
        head = ("HTTP/1.1 200 OK\r\nContent-Type: %s\r\nContent-Length: %d\r\n%s"
                "Connection: close\r\n\r\n" % (mime_type(name), size, disp))
        self.ev.log(u"web: download " + self.dl_name + u" by " + to_u(self.ip))
        self.conn.send(head, self.dl_next, self.dl_failed)

    def dl_next(self):
        if self.closed:
            return
        chunk = self.f.read(CHUNK)
        if not chunk:
            self.f.close()
            self.f = None
            self.ev.log(u"web: sent " + self.dl_name)
            self.close()
            return
        self.dl_sent = self.dl_sent + len(chunk)
        if self.dl_sent - self.dl_last > 131072 or self.dl_sent >= self.dl_size:
            self.dl_last = self.dl_sent
            self.ev.progress(u"Browser download", self.dl_sent, self.dl_size)
        self.conn.send(chunk, self.dl_next, self.dl_failed)

    def dl_failed(self, msg=None):
        if self.f is not None:
            try:
                self.f.close()
            except:
                pass
            self.f = None
        self.ev.log(u"web: download stopped")
        self.close()

    # ---- text message

    def start_text(self):
        self.dec = BodyDecoder(self.headers, 0)
        self.text_buf = []
        self.text_feed(self.body_start)

    def text_feed(self, data):
        if self.closed:
            return
        self.text_buf.append(self.dec.feed(data))
        if len("".join(self.text_buf)) > 65536:
            self.html(400, u"Too long", u"<p>Message too long.</p>")
            return
        if self.dec.done:
            q = parse_query("".join(self.text_buf))
            msg = to_u(q.get("msg", "")).strip()
            if msg:
                dev = {"alias": u"Browser", "ip": self.ip, "port": 0, "fingerprint": u"",
                       "deviceModel": None, "protocol": u"http"}
                self.ev.text_received(dev, msg)
                body = u'<p>Message sent to the phone.</p><p><a href="/">Back</a></p>'
            else:
                body = u'<p>Empty message.</p><p><a href="/">Back</a></p>'
            self.html(200, u"Sent", body)
            return
        self.conn.recv(self.text_data)

    def text_data(self, data):
        if not data:
            self.close()
            return
        self.text_feed(data)

    # ---- upload (streaming multipart/form-data)

    def start_upload(self):
        ctype = self.headers.get("content-type", "")
        i = ctype.lower().find("boundary=")
        if i < 0 or ctype.lower().find("multipart/form-data") < 0:
            self.html(400, u"Bad upload", u'<p>Bad upload. <a href="/">Back</a></p>')
            return
        b = ctype[i + 9:]
        semi = b.find(";")
        if semi >= 0:
            b = b[:semi]
        b = b.strip()
        if b[:1] == '"' and b[-1:] == '"':
            b = b[1:-1]
        self.delim = "--" + b
        self.dec = BodyDecoder(self.headers, 0)
        self.mp_state = "start"
        self.buf = ""
        self.saved = []
        self.got = 0
        self.last = 0
        try:
            self.total = long(self.headers.get("content-length", "0"))
        except:
            self.total = 0
        self.ev.log(u"web: upload from " + to_u(self.ip))
        self.up_feed(self.body_start)

    def up_data(self, data):
        if self.closed:
            return
        if not data:
            # browser went away before the end
            self.abort_file()
            self.ev.log(u"web: upload interrupted")
            if self.saved:
                self.ev.finished(u"Received %d file(s) from browser (upload interrupted)"
                                 % len(self.saved))
            self.close()
            return
        try:
            self.up_feed(data)
        except:
            self.ev.log(u"web upload: " + err_text())
            self.abort_file()
            self.html(500, u"Error", u"<p>Upload failed: %s</p>" % esc(err_text()))

    def up_feed(self, data):
        body = self.dec.feed(data)
        self.got = self.got + len(body)
        if self.total and self.got - self.last > 131072:
            self.last = self.got
            self.ev.progress(u"Browser upload", self.got, self.total)
        self.buf = self.buf + body
        self.parse()
        if self.closed:
            return
        if self.mp_state == "end" or self.dec.done:
            self.up_finished()
            return
        self.conn.recv(self.up_data)

    def parse(self):
        d = self.delim
        while 1:
            if self.mp_state == "start":
                i = self.buf.find(d)
                if i < 0:
                    # keep a possible partial delimiter at the end
                    if len(self.buf) > len(d):
                        self.buf = self.buf[-len(d):]
                    return
                rest = self.buf[i + len(d):]
                if len(rest) < 2:
                    self.buf = self.buf[i:]
                    return
                if rest[:2] == "--":
                    self.mp_state = "end"
                    self.buf = ""
                    return
                if rest[:2] != "\r\n":
                    self.buf = rest  # not a real delimiter line; keep looking
                    continue
                self.buf = rest[2:]
                self.mp_state = "headers"
            elif self.mp_state == "headers":
                i = self.buf.find("\r\n\r\n")
                if i < 0:
                    if len(self.buf) > 16384:
                        raise IOError("part header too long")
                    return
                head = self.buf[:i]
                self.buf = self.buf[i + 4:]
                self.open_part(head)
                self.mp_state = "data"
            elif self.mp_state == "data":
                marker = "\r\n" + d
                i = self.buf.find(marker)
                if i < 0:
                    keep = len(marker) - 1
                    if len(self.buf) > keep:
                        self.write_part(self.buf[:-keep])
                        self.buf = self.buf[-keep:]
                    return
                self.write_part(self.buf[:i])
                self.end_part()
                self.buf = self.buf[i + 2:]
                self.mp_state = "start"
            else:
                return

    def open_part(self, head):
        name = None
        for line in head.split("\r\n"):
            if line.lower()[:20] != "content-disposition:":
                continue
            j = line.find('filename="')
            if j >= 0:
                k = line.find('"', j + 10)
                if k > j:
                    name = line[j + 10:k]
        self.part_name = None
        self.f = None
        self.fpath = None
        if not name:
            return  # a normal form field, or no file chosen
        name = name.replace("\\", "/")
        name = name[name.rfind("/") + 1:]
        if not name:
            return
        uname = safe_name(to_u(name))
        self.part_name = uname
        self.fpath = self.ws.path_for(uname)
        self.f = open(self.fpath, "wb")

    def write_part(self, data):
        if self.f is not None and data:
            self.f.write(data)

    def end_part(self):
        if self.f is None:
            return
        self.f.close()
        self.f = None
        self.saved.append(self.fpath)
        self.ev.log(u"web: saved " + to_u(self.fpath))
        self.fpath = None

    def abort_file(self):
        if self.f is not None:
            try:
                self.f.close()
            except:
                pass
            self.f = None
        if self.fpath is not None:
            try:
                os.remove(self.fpath)
            except:
                pass
            self.fpath = None

    def up_finished(self):
        self.abort_file()  # an unterminated last part is incomplete
        n = len(self.saved)
        if n:
            self.ev.finished(u"Received %d file(s) from browser" % n)
        names = []
        for p in self.saved:
            names.append(u"<li>%s</li>" % esc(os.path.basename(p.replace("\\", "/"))))
        body = (u"<p>Received %d file(s).</p><ul>%s</ul><p><a href=\"/\">Back</a></p>"
                % (n, u"".join(names)))
        self.html(200, u"Received", body)
