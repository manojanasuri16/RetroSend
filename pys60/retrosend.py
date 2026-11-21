# RetroSend for Python for S60 (PyS60 1.4.5, Python 2.2).
# Sends and receives files and text with the LocalSend app (protocol v2,
# plain HTTP: turn Encryption off in LocalSend) over Wi-Fi.
#
# Native app: the phone grants network and file access once, at install,
# and the chosen Wi-Fi access point is remembered, so there are no
# permission or Wi-Fi pop-ups while using it.
#
# Written for Python 2.2: no enumerate/sorted/sets/generators, no
# conditional expressions, no "with", no "except X as e", and
# substring tests use find(). The file also parses as Python 3 so it can
# be checked on a PC (tools/check_py22.py).

import sys
import appuifw
import e32

# ---- startup diagnostics: a log file and an on-screen error, so a crash
# never just closes the app silently.
_LOGFILE = None
for _d in ["E:\\", "C:\\Data\\", "C:\\"]:
    try:
        _name = _d + "retrosend_log.txt"
        _mode = "a"
        try:
            import os as _os
            if _os.path.getsize(_name) > 60000:
                _mode = "w"  # keep the log small
        except:
            pass
        _f = open(_name, _mode)
        _LOGFILE = _f
        break
    except:
        pass


def boot_log(msg):
    if _LOGFILE is not None:
        try:
            try:
                import time as _t
                msg = _t.strftime("%H:%M:%S ") + msg
            except:
                pass
            _LOGFILE.write(msg + "\n")
            _LOGFILE.flush()
        except:
            pass


def show_crash(where):
    try:
        import traceback
        text = "".join(traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1],
                                                  sys.exc_info()[2]))
    except:
        text = str(sys.exc_info()[1])
    boot_log("CRASH in " + where + ":\n" + text)
    try:
        appuifw.note(unicode("RetroSend error (" + where + "): " + str(sys.exc_info()[1]),
                             "latin-1"), "error")
        appuifw.query(u"Error details (also in retrosend_log.txt)", "text",
                      unicode(text, "latin-1"))
    except:
        pass


boot_log("")
boot_log("========== RetroSend started, python " + sys.version.split(" ")[0])
try:
    import os
    import time
    import random
    import types
    import socket
    boot_log("imports ok")
except:
    show_crash("imports")
    raise

try:
    import sysinfo
except:
    sysinfo = None

try:
    import graphics
except:
    graphics = None
try:
    import key_codes
except:
    key_codes = None

import struct

# media.py (ID3 album art, video length) is pasted here by build_sis.sh;
# on the PC it is imported normally.
#@INLINE media.py
from media import read_id3, video_info, human_duration

VERSION = u"1.1.1"  # single source of truth: build_sis.sh reads this
API = "/api/localsend/v2/"
MULTICAST = "224.0.0.167"
DEFAULT_PORT = 53317


def err_text():
    e = sys.exc_info()[1]
    try:
        return unicode(str(e), 'utf-8', 'replace')
    except:
        return u"error"


def to_u(s):
    if type(s) is types.UnicodeType:
        return s
    if s is None:
        return u""
    try:
        return unicode(s, 'utf-8')
    except:
        return unicode(s, 'latin-1')


def to_b(s):
    if type(s) is types.UnicodeType:
        return s.encode('utf-8')
    return str(s)


# ---------------------------------------------------------------- JSON

class Raw:
    """A literal JSON token such as true/false (Python 2.2 has no bool type)."""
    def __init__(self, text):
        self.text = text

JTRUE = Raw("true")
JFALSE = Raw("false")


def _quote(s):
    out = [u'"']
    for ch in s:
        o = ord(ch)
        if ch == u'"':
            out.append(u'\\"')
        elif ch == u'\\':
            out.append(u'\\\\')
        elif ch == u'\n':
            out.append(u'\\n')
        elif ch == u'\r':
            out.append(u'\\r')
        elif ch == u'\t':
            out.append(u'\\t')
        elif o < 32:
            out.append(u'\\u%04x' % o)
        else:
            out.append(ch)
    out.append(u'"')
    return u"".join(out)


_BOOL = type(1 == 1)  # int on Python 2.2, bool on newer versions


def _dump(o):
    t = type(o)
    if o is None:
        return u"null"
    if _BOOL is not types.IntType and t is _BOOL:
        if o:
            return u"true"
        return u"false"
    if isinstance(o, Raw):
        return unicode(o.text)
    if t is types.UnicodeType:
        return _quote(o)
    if t is types.StringType:
        return _quote(to_u(o))
    if t is types.DictType:
        parts = []
        for k in o.keys():
            parts.append(_quote(to_u(k)) + u":" + _dump(o[k]))
        return u"{" + u",".join(parts) + u"}"
    if t is types.ListType or t is types.TupleType:
        parts = []
        for v in o:
            parts.append(_dump(v))
        return u"[" + u",".join(parts) + u"]"
    if t is types.FloatType:
        return unicode(repr(o))
    return unicode(str(o))


def json_dumps(o):
    return _dump(o).encode('utf-8')


class _Parser:
    def __init__(self, s):
        self.s = s
        self.i = 0

    def ws(self):
        s = self.s
        n = len(s)
        while self.i < n and s[self.i] in u" \t\r\n":
            self.i = self.i + 1

    def value(self):
        self.ws()
        s = self.s
        if self.i >= len(s):
            raise ValueError("unexpected end")
        c = s[self.i]
        if c == u'{':
            return self.obj()
        if c == u'[':
            return self.arr()
        if c == u'"':
            return self.string()
        if s[self.i:self.i + 4] == u"true":
            self.i = self.i + 4
            return True
        if s[self.i:self.i + 5] == u"false":
            self.i = self.i + 5
            return False
        if s[self.i:self.i + 4] == u"null":
            self.i = self.i + 4
            return None
        return self.number()

    def obj(self):
        d = {}
        self.i = self.i + 1
        self.ws()
        if self.s[self.i] == u'}':
            self.i = self.i + 1
            return d
        while 1:
            self.ws()
            k = self.string()
            self.ws()
            if self.s[self.i] != u':':
                raise ValueError("expected :")
            self.i = self.i + 1
            v = self.value()
            d[k] = v
            self.ws()
            c = self.s[self.i]
            self.i = self.i + 1
            if c == u'}':
                return d
            if c != u',':
                raise ValueError("bad object")

    def arr(self):
        a = []
        self.i = self.i + 1
        self.ws()
        if self.s[self.i] == u']':
            self.i = self.i + 1
            return a
        while 1:
            a.append(self.value())
            self.ws()
            c = self.s[self.i]
            self.i = self.i + 1
            if c == u']':
                return a
            if c != u',':
                raise ValueError("bad array")

    def string(self):
        s = self.s
        if s[self.i] != u'"':
            raise ValueError("expected string")
        self.i = self.i + 1
        out = []
        while 1:
            c = s[self.i]
            self.i = self.i + 1
            if c == u'"':
                return u"".join(out)
            if c != u'\\':
                out.append(c)
                continue
            e = s[self.i]
            self.i = self.i + 1
            if e == u'n':
                out.append(u'\n')
            elif e == u't':
                out.append(u'\t')
            elif e == u'r':
                out.append(u'\r')
            elif e == u'b':
                out.append(u'\b')
            elif e == u'f':
                out.append(u'\f')
            elif e == u'u':
                out.append(unichr(int(s[self.i:self.i + 4], 16)))
                self.i = self.i + 4
            else:
                out.append(e)

    def number(self):
        s = self.s
        start = self.i
        real = 0
        while self.i < len(s) and s[self.i] in u"0123456789+-.eE":
            if s[self.i] in u".eE":
                real = 1
            self.i = self.i + 1
        t = s[start:self.i]
        if not t:
            raise ValueError("bad value")
        if real:
            return float(t)
        return long(t)


def json_loads(s):
    return _Parser(to_u(s)).value()


def jget(d, key, default=None):
    if type(d) is not types.DictType:
        return default
    if d.has_key(key) and d[key] is not None:
        return d[key]
    return default


# ---------------------------------------------------------------- URLs

_SAFE = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_.~"


def url_quote(s):
    out = []
    for ch in to_b(s):
        if _SAFE.find(ch) >= 0:
            out.append(ch)
        else:
            out.append("%%%02X" % ord(ch))
    return "".join(out)


def url_unquote(s):
    s = s.replace("+", " ")
    out = []
    i = 0
    n = len(s)
    while i < n:
        ch = s[i]
        if ch == "%" and i + 2 < n:
            try:
                out.append(chr(int(s[i + 1:i + 3], 16)))
                i = i + 3
                continue
            except:
                pass
        out.append(ch)
        i = i + 1
    return "".join(out)


def parse_query(q):
    d = {}
    for part in q.split("&"):
        if not part:
            continue
        i = part.find("=")
        if i >= 0:
            d[url_unquote(part[:i])] = url_unquote(part[i + 1:])
        else:
            d[url_unquote(part)] = ""
    return d


REASONS = {200: "OK", 204: "No Content", 400: "Bad Request", 401: "Unauthorized",
           403: "Forbidden", 404: "Not Found", 409: "Conflict", 500: "Internal Server Error"}



# ---------------------------------------------------------------- helpers

MIME = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "gif": "image/gif",
        "bmp": "image/bmp", "mp3": "audio/mpeg", "aac": "audio/aac", "m4a": "audio/mp4",
        "amr": "audio/amr", "wav": "audio/wav", "wma": "audio/x-ms-wma", "mp4": "video/mp4",
        "3gp": "video/3gpp", "txt": "text/plain", "pdf": "application/pdf",
        "zip": "application/zip", "jar": "application/java-archive",
        "sis": "application/vnd.symbian.install", "sisx": "x-epoc/x-sisx-app",
        "vcf": "text/vcard", "apk": "application/vnd.android.package-archive",
        "py": "text/x-python"}


def mime_type(name):
    name = to_u(name).lower()
    i = name.rfind(u".")
    if i < 0:
        return "application/octet-stream"
    return MIME.get(str(name[i + 1:].encode('ascii', 'replace')), "application/octet-stream")


def human_size(n):
    n = long(n)
    if n < 1024:
        return u"%d B" % n
    if n < 1048576:
        return u"%d KB" % (n / 1024)
    return u"%.1f MB" % (n / 1048576.0)


def safe_name(name):
    name = to_u(name)
    out = []
    for ch in name:
        if ord(ch) < 32 or u'/\\:*?"<>|'.find(ch) >= 0:
            out.append(u'_')
        else:
            out.append(ch)
    s = u"".join(out).strip()
    while s[:1] == u".":
        s = s[1:]
    if not s:
        s = u"file"
    if len(s) > 120:
        i = s.rfind(u".")
        ext = u""
        if i > 0 and len(s) - i <= 10:
            ext = s[i:]
        s = s[:120 - len(ext)] + ext
    return s


def random_id():
    # Small ranges only: on Python 2.2 randint(0, 0x7fffffff) overflows
    # ("long int too large to convert to int").
    parts = []
    for k in range(4):
        parts.append("%04x" % random.randrange(0, 0x10000))
    return "".join(parts)


def make_info(cfg, with_net=1, announce=0):
    d = {"alias": to_u(cfg["alias"]), "version": "2.0",
         "deviceModel": to_u(cfg.get("model", u"S60 phone")), "deviceType": "mobile",
         "fingerprint": cfg["fingerprint"], "download": JFALSE}
    if with_net:
        d["port"] = cfg["port"]
        d["protocol"] = "http"
    if announce:
        d["announce"] = JTRUE
    return d


def make_dev(info, ip):
    return {"alias": to_u(jget(info, "alias", u"Unknown")), "ip": ip,
            "port": int(jget(info, "port", DEFAULT_PORT)),
            "fingerprint": to_u(jget(info, "fingerprint", u"")),
            "deviceModel": jget(info, "deviceModel"),
            "protocol": to_u(jget(info, "protocol", u"https"))}


class Refused(Exception):
    pass



def make_file_item(path, name=None):
    path = to_b(path)
    if name is None:
        name = to_u(os.path.basename(path.replace("\\", "/")))
    return {"path": path, "name": to_u(name), "size": long(os.path.getsize(path)),
            "type": mime_type(name), "text": None}


def save_dir_for(cfg, name):
    """Folder for a received file: photos/music/videos go where the phone's
    Gallery and Music player look (if "sort" is on), the rest to savedir."""
    if cfg.get("sort"):
        e = to_b(name).lower()
        e = e[e.rfind(".") + 1:]
        kinds = [(["jpg", "jpeg", "png", "gif", "bmp"], ["E:\\Images\\", "C:\\Data\\Images\\"]),
                 (["mp3", "m4a", "aac", "wma", "wav", "amr"], ["E:\\Music\\", "E:\\Sounds\\", "C:\\Data\\Sounds\\"]),
                 (["mp4", "3gp", "m4v", "3g2"], ["E:\\Videos\\", "C:\\Data\\Videos\\"])]
        for exts, dirs in kinds:
            if exts.count(e):
                for d in dirs:
                    if os.path.isdir(d):
                        return d
    return cfg["savedir"]


def make_text_item(text):
    text = to_u(text)
    return {"path": None, "name": u"message.txt", "size": len(text.encode('utf-8')),
            "type": "text/plain", "text": text}



# ---------------------------------------------------------------- async HTTP
#
# On PyS60 1.4.5 sockets only work on the main thread, through callbacks
# (a background thread has no Symbian active scheduler and freezes the app).
# So everything below is non-blocking and driven by a "net" object:
#   net.listen(port, on_conn)            on_conn(conn, ip)
#   net.connect(host, port, on_ok, on_err)
#   net.later(seconds, func)
#   net.udp_send(host, port, data) / net.udp_listen(port, on_packet)
#   conn.recv(on_data)   on_data("") means closed
#   conn.send(data, on_done, on_err) / conn.close() / conn.local_ip()


class BodyDecoder:
    """Incremental body decoder: Content-Length, chunked, or until close."""
    def __init__(self, headers, is_response=0):
        self.mode = "length"
        self.left = 0
        self.pend = ""
        self.cstate = "size"
        if headers.get("transfer-encoding", "").lower().find("chunked") >= 0:
            self.mode = "chunked"
        elif headers.has_key("content-length"):
            self.left = long(headers["content-length"])
        elif is_response:
            self.mode = "close"
        self.done = (self.mode == "length" and self.left == 0)

    def feed(self, data):
        """Returns body bytes contained in data; sets self.done at the end."""
        if self.done:
            return ""
        if self.mode == "close":
            return data
        if self.mode == "length":
            take = data[:int(min(len(data), self.left))]
            self.left = self.left - len(take)
            if self.left <= 0:
                self.done = 1
            return take
        self.pend = self.pend + data
        out = []
        while 1:
            if self.cstate == "size":
                i = self.pend.find("\r\n")
                if i < 0:
                    break
                line = self.pend[:i]
                self.pend = self.pend[i + 2:]
                semi = line.find(";")
                if semi >= 0:
                    line = line[:semi]
                size = long(line.strip() or "0", 16)
                if size == 0:
                    self.cstate = "trailer"
                else:
                    self.left = size
                    self.cstate = "data"
            elif self.cstate == "data":
                if not self.pend:
                    break
                take = self.pend[:int(min(len(self.pend), self.left))]
                self.pend = self.pend[len(take):]
                self.left = self.left - len(take)
                out.append(take)
                if self.left == 0:
                    self.cstate = "crlf"
            elif self.cstate == "crlf":
                if len(self.pend) < 2:
                    break
                self.pend = self.pend[2:]
                self.cstate = "size"
            else:  # trailer
                if self.pend[:2] == "\r\n" or self.pend.find("\r\n\r\n") >= 0:
                    self.done = 1
                    self.pend = ""
                break
        return "".join(out)


def parse_head(text):
    """Splits a header block into (first line, headers dict)."""
    lines = text.split("\r\n")
    h = {}
    for line in lines[1:]:
        i = line.find(":")
        if i > 0:
            h[line[:i].strip().lower()] = line[i + 1:].strip()
    return lines[0], h


def response_bytes(code, body=None):
    data = ""
    head = "HTTP/1.1 %d %s\r\n" % (code, REASONS.get(code, "Status"))
    if body is not None:
        data = json_dumps(body)
        head = head + "Content-Type: application/json; charset=utf-8\r\n"
    return head + "Content-Length: %d\r\nConnection: close\r\n\r\n" % len(data) + data


def report_ip(events, conn):
    f = getattr(events, "got_ip", None)
    if f is not None:
        try:
            f(conn.local_ip())
        except:
            pass


class HttpRequest:
    """One POST request: connect, send headers + body (bytes or a file), read reply."""
    def __init__(self, net, events, host, port, path, ctype, data=None, fpath=None, length=0,
                 on_progress=None, on_done=None, on_err=None):
        self.net = net
        self.ev = events
        self.host = host
        self.port = port
        self.path = path
        self.ctype = ctype
        self.data = data
        self.fpath = fpath
        self.length = length
        self.on_progress = on_progress
        self.on_done = on_done
        self.on_err = on_err
        self.conn = None
        self.f = None
        self.quiet = 0
        self.finished = 0
        self.buf = ""
        self.head = None
        self.code = 0
        self.dec = None
        self.body = []
        if data is not None:
            self.length = len(data)

    def start(self):
        if not self.quiet:
            self.ev.log(u"-> POST %s:%d %s" % (to_u(self.host), self.port,
                                           to_u(self.path.split("?")[0])))
        self.net.connect(self.host, self.port, self.connected, self.fail)

    def cancel(self):
        self.fail("Cancelled")

    def connected(self, conn):
        if self.finished:
            conn.close()
            return
        self.conn = conn
        report_ip(self.ev, conn)
        head = ("POST %s HTTP/1.1\r\nHost: %s:%d\r\nUser-Agent: RetroSend\r\n"
                "Content-Type: %s\r\nContent-Length: %d\r\nConnection: close\r\n\r\n"
                % (self.path, self.host, self.port, self.ctype, self.length))
        if self.data is not None:
            conn.send(head + self.data, self.wait_reply, self.fail)
        else:
            try:
                self.f = open(self.fpath, "rb")
            except:
                self.fail("cannot open file: " + str(sys.exc_info()[1]))
                return
            self.sent = 0
            conn.send(head, self.send_chunk, self.fail)

    def send_chunk(self):
        if self.finished:
            return
        chunk = self.f.read(16384)
        if not chunk:
            self.f.close()
            self.f = None
            if self.sent != self.length:
                self.fail("file changed while sending")
                return
            self.wait_reply()
            return
        self.sent = self.sent + len(chunk)
        if self.on_progress is not None:
            self.on_progress(len(chunk))
        self.conn.send(chunk, self.send_chunk, self.fail)

    def wait_reply(self):
        if not self.finished:
            self.conn.recv(self.got_data)

    def got_data(self, data):
        if self.finished:
            return
        if not data:
            if self.head is not None and self.dec is not None and self.dec.mode == "close":
                self.finish()
            else:
                self.fail("connection closed by " + self.host)
            return
        if self.head is None:
            self.buf = self.buf + data
            i = self.buf.find("\r\n\r\n")
            if i < 0:
                if len(self.buf) > 32768:
                    self.fail("reply header too long")
                    return
                self.conn.recv(self.got_data)
                return
            first, headers = parse_head(self.buf[:i])
            data = self.buf[i + 4:]
            self.buf = ""
            self.head = headers
            parts = first.split(" ")
            try:
                self.code = int(parts[1])
            except:
                self.fail("bad reply")
                return
            self.dec = BodyDecoder(headers, 1)
        self.body.append(self.dec.feed(data))
        if self.dec.done:
            self.finish()
        else:
            self.conn.recv(self.got_data)

    def cleanup(self):
        self.finished = 1
        if self.f is not None:
            try:
                self.f.close()
            except:
                pass
            self.f = None
        if self.conn is not None:
            try:
                self.conn.close()
            except:
                pass

    def finish(self):
        self.cleanup()
        if not self.quiet:
            self.ev.log(u"<- HTTP %d from %s" % (self.code, to_u(self.host)))
        if self.on_done is not None:
            self.on_done(self.code, "".join(self.body))

    def fail(self, msg):
        if self.finished:
            return
        self.cleanup()
        if not self.quiet:
            self.ev.log(u"!! request to %s failed: %s" % (to_u(self.host), to_u(msg)))
        if self.on_err is not None:
            self.on_err(to_u(msg))


# ---------------------------------------------------------------- receiving

class ServerConn:
    """One incoming HTTP connection."""
    def __init__(self, srv, conn, ip):
        self.srv = srv
        self.conn = conn
        self.ip = ip
        self.buf = ""
        self.state = "head"
        self.dec = None
        self.body = []
        self.closed = 0
        self.out = None
        self.upload = None
        report_ip(srv.ev, conn)
        conn.recv(self.got_data)

    def close(self):
        if not self.closed:
            self.closed = 1
            try:
                self.conn.close()
            except:
                pass
        if self.out is not None:
            self.abort_upload(u"connection closed")

    def respond(self, code, body=None):
        if self.closed:
            return
        if code != 200:
            self.srv.ev.log(u"-> answered %d" % code)
        self.state = "done"
        self.conn.send(response_bytes(code, body), self.close, self.send_failed)

    def send_failed(self, msg):
        self.close()

    def got_data(self, data):
        if self.closed:
            return
        if not data:
            self.close()
            return
        try:
            self.process(data)
        except:
            self.srv.ev.log(u"request: " + err_text())
            if self.out is not None:
                self.abort_upload(err_text())
            self.respond(500)

    def process(self, data):
        if self.state == "head":
            self.buf = self.buf + data
            i = self.buf.find("\r\n\r\n")
            if i < 0:
                if len(self.buf) > 32768:
                    self.respond(400)
                else:
                    self.conn.recv(self.got_data)
                return
            first, headers = parse_head(self.buf[:i])
            data = self.buf[i + 4:]
            self.buf = ""
            parts = first.split(" ")
            if len(parts) < 2:
                self.respond(400)
                return
            self.method = parts[0]
            target = parts[1]
            web = getattr(self.srv, "web", None)
            if web is not None and target[:len("/api/")] != "/api/":
                self.state = "handed"  # browser sharing owns this connection now
                web.handle(self.conn, self.ip, self.method, target, headers, data)
                return
            self.query = {}
            q = target.find("?")
            if q >= 0:
                self.query = parse_query(target[q + 1:])
                target = target[:q]
            if target[:len("/api/localsend/v1/")] == "/api/localsend/v1/":
                target = API + target[len("/api/localsend/v1/"):]
            if target[:len(API)] != API:
                self.respond(404)
                return
            self.route = target[len(API):]
            self.srv.ev.log(u"<- %s %s from %s" % (to_u(self.method), to_u(self.route),
                                                   to_u(self.ip)))
            self.dec = BodyDecoder(headers, 0)
            if self.route == "upload" and self.method == "POST":
                if not self.srv.begin_upload(self):
                    return  # already answered
                self.state = "upload"
            else:
                self.state = "body"
        if self.state == "body":
            self.body.append(self.dec.feed(data))
            if self.dec.done:
                self.state = "dispatch"
                self.srv.dispatch(self, "".join(self.body))
            else:
                self.conn.recv(self.got_data)
        elif self.state == "upload":
            chunk = self.dec.feed(data)
            if chunk:
                self.out.write(chunk)
                self.srv.upload_progress(self, len(chunk))
            if self.dec.done:
                self.srv.end_upload(self)
            else:
                self.conn.recv(self.got_data)

    def abort_upload(self, why):
        self.srv.abort_upload(self, why)


class Server:
    def __init__(self, cfg, events, net):
        self.cfg = cfg
        self.ev = events
        self.net = net
        self.session = None
        self.running = 0

    def start(self):
        self.net.listen(self.cfg["port"], self.incoming)
        self.running = 1
        self.ev.log(u"listening on port %d" % self.cfg["port"])

    def stop(self):
        self.running = 0
        try:
            self.net.stop_listen()
        except:
            pass

    def incoming(self, conn, ip):
        if not self.running:
            conn.close()
            return
        ServerConn(self, conn, ip)

    def dispatch(self, sc, body):
        r = sc.route
        if r == "info":
            sc.respond(200, make_info(self.cfg, 0))
        elif r == "register" and sc.method == "POST":
            try:
                dev = make_dev(json_loads(body), sc.ip)
            except:
                sc.respond(400)
                return
            if dev["fingerprint"] != to_u(self.cfg["fingerprint"]):
                self.ev.peer(dev)
            sc.respond(200, make_info(self.cfg, 0))
        elif r == "prepare-upload" and sc.method == "POST":
            self.prepare(sc, body)
        elif r == "cancel" and sc.method == "POST":
            if self.session is not None:
                self.end_session()
                self.ev.finished(u"The sender cancelled.")
            sc.respond(200)
        else:
            sc.respond(404)

    def receiving(self):
        s = self.session
        return s is not None and s.get("id") is not None

    def stop_receiving(self):
        """User pressed Stop receiving: drop the transfer and partial files."""
        if not self.receiving():
            return 0
        self.end_session()  # closes the uploads; their partial files are deleted
        self.ev.finished(u"Receiving stopped.")
        return 1

    def end_session(self):
        s = self.session
        self.session = None
        if s is not None:
            for sc in s["active"].values():
                try:
                    sc.close()
                except:
                    pass

    def prepare(self, sc, body):
        try:
            req = json_loads(body)
            files = jget(req, u"files")
            dev = make_dev(jget(req, u"info"), sc.ip)
        except:
            sc.respond(400)
            return
        if type(files) is not types.DictType or not files:
            sc.respond(400)
            return
        self.ev.peer(dev)
        if self.session is not None:
            if time.time() - self.session["touched"] < 120:
                sc.respond(409)
                return
            self.end_session()
        flist = files.values()
        if len(flist) == 1:
            f = flist[0]
            ftype = to_u(jget(f, u"fileType", u""))
            if jget(f, u"preview") is not None and (ftype[:5] == u"text/" or ftype == u"text"):
                self.ev.text_received(dev, to_u(jget(f, u"preview")))
                sc.respond(204)
                return
        total = 0
        for f in flist:
            total = total + long(jget(f, u"size", 0))
        # reserve the session while the user decides
        self.session = {"id": None, "touched": time.time(), "active": {}}
        pending = self.session

        def answer(ok, self=self, sc=sc, files=files, dev=dev, total=total, pending=pending):
            if self.session is not pending:
                sc.respond(409)
                return
            if not ok:
                self.session = None
                sc.respond(403)
                return
            sid = random_id()
            tokens = {}
            for fid in files.keys():
                tokens[fid] = random_id()
            pending.update({"id": sid, "ip": sc.ip, "tokens": tokens, "files": files,
                            "done": {}, "total": total, "got": 0, "last": 0,
                            "touched": time.time(), "from": dev["alias"]})
            sc.respond(200, {"sessionId": sid, "files": tokens})
            self.ev.progress(u"Receiving from " + dev["alias"], 0, total)

        self.ev.ask_accept(dev, flist, total, answer)

    def begin_upload(self, sc):
        q = sc.query
        sid = q.get("sessionId")
        fid = to_u(q.get("fileId", ""))
        token = q.get("token")
        s = self.session
        if sid is None or token is None or not fid:
            sc.respond(400)
            return 0
        if s is None or s["id"] is None:
            sc.respond(403)
            return 0
        if s["id"] != sid:
            sc.respond(409)
            return 0
        if s["tokens"].get(fid) != token or s["ip"] != sc.ip or s["done"].has_key(fid):
            sc.respond(403)
            return 0
        f = s["files"][fid]
        name = safe_name(jget(f, u"fileName", u"file"))
        path = self.create_path(name)
        sc.out = open(path, "wb")
        sc.upload = {"fid": fid, "name": name, "path": path, "got": 0,
                     "expected": long(jget(f, u"size", -1)), "session": s}
        s["active"][fid] = sc
        s["touched"] = time.time()
        if sc.dec.done:  # empty file
            self.end_upload(sc)
            return 0
        return 1

    def upload_progress(self, sc, n):
        u = sc.upload
        s = u["session"]
        u["got"] = u["got"] + n
        s["got"] = s["got"] + n
        s["touched"] = time.time()
        if s["got"] - s["last"] > 65536:
            s["last"] = s["got"]
            self.ev.progress(u["name"], s["got"], s["total"])

    def abort_upload(self, sc, why):
        u = sc.upload
        if sc.out is None or u is None:
            return
        try:
            sc.out.close()
        except:
            pass
        sc.out = None
        try:
            os.remove(u["path"])
        except:
            pass
        s = u["session"]
        try:
            del s["active"][u["fid"]]
        except:
            pass
        self.ev.log(u"receive " + u["name"] + u": " + to_u(why))
        if self.session is s:
            self.session = None
            self.ev.finished(u"Receiving failed: " + u["name"])

    def end_upload(self, sc):
        u = sc.upload
        s = u["session"]
        sc.out.close()
        sc.out = None
        try:
            del s["active"][u["fid"]]
        except:
            pass
        if u["expected"] >= 0 and u["got"] != u["expected"]:
            sc.out = open(u["path"], "ab")  # so abort_upload can clean up
            self.abort_upload(sc, u"incomplete file")
            sc.respond(500)
            return
        s["done"][u["fid"]] = 1
        self.ev.log(u"Saved " + to_u(u["path"]))
        f = getattr(self.ev, "saved", None)
        if f is not None:
            f(u["path"])
        sc.respond(200)
        if len(s["done"]) == len(s["tokens"]) and self.session is s:
            self.session = None
            self.ev.finished(u"Received %d file(s) from %s.\nOpen them from Receive > "
                             u"Received files." % (len(s["done"]), s["from"]))

    def create_path(self, name):
        d = save_dir_for(self.cfg, name)
        if not os.path.exists(d):
            os.makedirs(d)
        i = name.rfind(u".")
        base = name
        ext = u""
        if i > 0:
            base = name[:i]
            ext = name[i:]
        n = 0
        while 1:
            cand = name
            if n:
                cand = u"%s (%d)%s" % (base, n, ext)
            path = d + cand.encode('utf-8')
            if not os.path.exists(path):
                return path
            n = n + 1


# ---------------------------------------------------------------- sending

class Client:
    def __init__(self, cfg, events, net):
        self.cfg = cfg
        self.ev = events
        self.net = net
        self.req = None
        self.quiet = 0
        self.cancelled = 0

    def post(self, dev_ip, port, path, ctype, data, on_done, on_err, fpath=None, length=0,
             on_progress=None):
        r = HttpRequest(self.net, self.ev, dev_ip, port, path, ctype, data, fpath, length,
                        on_progress, on_done, on_err)
        r.quiet = self.quiet
        self.req = r
        r.start()

    def cancel(self):
        self.cancelled = 1
        if self.req is not None:
            self.req.cancel()

    def register(self, host, port, on_ok, on_err):
        def done(code, text, host=host, port=port, on_ok=on_ok, on_err=on_err):
            if code != 200:
                on_err(u"HTTP %d" % code)
                return
            try:
                dev = make_dev(json_loads(text), host)
            except:
                on_err(u"bad reply")
                return
            dev["port"] = port
            dev["protocol"] = u"http"
            on_ok(dev)
        self.post(host, port, API + "register", "application/json",
                  json_dumps(make_info(self.cfg)), done, on_err)

    def send(self, dev, items, on_done, on_err):
        self.cancelled = 0
        files = {}
        total = 0
        only_text = 1
        k = 0
        for it in items:
            fid = "f%d" % k
            k = k + 1
            f = {"id": fid, "fileName": it["name"], "size": it["size"], "fileType": it["type"]}
            if it["text"] is not None:
                f["preview"] = it["text"]
            else:
                only_text = 0
            files[fid] = f
            total = total + it["size"]
        st = {"dev": dev, "items": items, "total": total, "sent": 0, "index": 0,
              "done": 0, "last": 0, "tokens": {}, "sid": "",
              "on_done": on_done, "on_err": on_err}
        self.st = st
        self.ev.progress(u"Waiting for " + dev["alias"] + u" to accept", 0, total)

        def prepared(code, text, self=self, st=st, only_text=only_text):
            a = st["dev"]["alias"]
            if code == 204:
                if only_text:
                    st["on_done"](u"Message sent to " + a)
                else:
                    st["on_done"](u"Nothing needed to be sent.")
                return
            if code != 200:
                msgs = {401: a + u" needs a PIN. Turn off \"Require PIN\" in LocalSend.",
                        403: a + u" declined.",
                        409: a + u" is busy with another transfer."}
                st["on_err"](msgs.get(code, a + u" replied with error %d." % code))
                return
            try:
                res = json_loads(text)
                st["sid"] = to_b(jget(res, u"sessionId", u""))
                st["tokens"] = jget(res, u"files", {})
            except:
                st["on_err"](u"bad reply from " + a)
                return
            self.next_file()

        self.post(dev["ip"], dev["port"], API + "prepare-upload", "application/json",
                  json_dumps({"info": make_info(self.cfg), "files": files}),
                  prepared, self.failed)

    def failed(self, msg):
        st = self.st
        if self.cancelled:
            self.cancelled = 0
            if st["sid"]:
                d = st["dev"]
                ignore = lambda *a: None
                self.post(d["ip"], d["port"], API + "cancel?sessionId=" + url_quote(st["sid"]),
                          "application/json", "", ignore, ignore)
            st["on_err"](u"Cancelled.")
            return
        st["on_err"](msg)

    def next_file(self):
        st = self.st
        items = st["items"]
        while st["index"] < len(items):
            i = st["index"]
            it = items[i]
            st["index"] = i + 1
            fid = "f%d" % i
            token = st["tokens"].get(to_u(fid))
            if token is None:
                continue  # receiver skipped this one
            d = st["dev"]
            path = (API + "upload?sessionId=" + url_quote(st["sid"]) + "&fileId=" + fid +
                    "&token=" + url_quote(to_b(token)))

            def uploaded(code, text, self=self, st=st, name=it["name"]):
                if code != 200:
                    self.failed(u"upload of %s failed: HTTP %d" % (name, code))
                    return
                st["sent"] = st["sent"] + 1
                self.next_file()

            if it["text"] is not None:
                self.post(d["ip"], d["port"], path, "text/plain", it["text"].encode('utf-8'),
                          uploaded, self.failed)
            else:
                self.post(d["ip"], d["port"], path, "application/octet-stream", None,
                          uploaded, self.failed, it["path"], it["size"], self.sent_bytes)
            return
        st["on_done"](u"Sent %d file(s) to %s" % (st["sent"], st["dev"]["alias"]))

    def sent_bytes(self, n):
        st = self.st
        st["done"] = st["done"] + n
        if st["done"] - st["last"] > 65536 or st["done"] >= st["total"]:
            st["last"] = st["done"]
            self.ev.progress(u"Sending", st["done"], st["total"])

    def announce(self, local_ip=None):
        msg = json_dumps(make_info(self.cfg, 1, 1))
        targets = [MULTICAST]
        if local_ip:
            targets.append(local_ip[:local_ip.rfind(".")] + ".255")
        for t in targets:
            try:
                self.net.udp_send(t, DEFAULT_PORT, msg)
            except:
                self.ev.log(u"announce " + to_u(t) + u": " + err_text())


# ---------------------------------------------------------------- phone network

def raw(sock):
    """The e32socket object under the socket module's wrapper (takes callbacks)."""
    return getattr(sock, "_sock", sock)


def valid_ip(ip):
    """PyS60's accept() reports a wrong address like 0.8.0.0 for incoming
    connections, so devices are only listed with an address we contacted."""
    ip = to_b(ip or "")
    return ip.count(".") == 3 and ip[:2] != "0." and ip[:4] != "127."


def is_err(res):
    """e32socket callbacks get (exception_class, value) when an operation fails."""
    return (type(res) is types.TupleType and len(res) == 2 and
            type(res[0]) in (types.ClassType, types.TypeType))


# IMPORTANT (PyS60 e32socket): socket.close() also stops the Wi-Fi
# connection and closes the shared socket server, which breaks every other
# socket and crashes the app. So sockets are never close()d while running:
# connected ones get shutdown(2) and are then simply dropped (freeing a
# socket object closes only that socket).


class PhoneConn:
    def __init__(self, sock, app):
        self.sock = sock
        self.app = app

    def recv(self, on_data):
        def cb(res, on_data=on_data, app=self.app):
            if is_err(res) or res is None:
                res = ""
            app.safe(on_data, res)
        try:
            if self.sock is None:
                raise IOError("closed")
            self.sock.recv(16384, 0, cb)
        except:
            self.app.net.later(0, lambda on_data=on_data: on_data(""))

    def send(self, data, on_done, on_err):
        state = {"data": data}

        def cb(res, self=self, state=state, on_done=on_done, on_err=on_err):
            if is_err(res):
                self.app.safe(on_err, str(res[1]))
                return
            n = len(state["data"])
            try:
                if type(res) in (types.IntType, types.LongType) and 0 < res < n:
                    n = int(res)
            except:
                pass
            state["data"] = state["data"][n:]
            if state["data"]:
                go()
            else:
                self.app.safe(on_done)

        def go(self=self, state=state, cb=cb, on_err=on_err):
            try:
                if self.sock is None:
                    raise IOError("closed")
                self.sock.send(state["data"], 0, cb)
            except:
                self.app.safe(on_err, str(sys.exc_info()[1]))
        go()

    def close(self):
        s = self.sock
        self.sock = None
        if s is not None:
            try:
                s.shutdown(2)
            except:
                pass

    def local_ip(self):
        try:
            return self.sock.getsockname()[0]
        except:
            return None


class PhoneNet:
    """Callback-based sockets on the main thread (no threads at all)."""
    def __init__(self, app):
        self.app = app
        self.timers = []
        self.lsock = None

    def later(self, seconds, func):
        t = e32.Ao_timer()
        box = [t]

        def fire(self=self, box=box, func=func):
            try:
                self.timers.remove(box[0])
            except:
                pass
            self.app.safe(func)
        self.timers.append(t)
        t.after(seconds, fire)

    def listen(self, port, on_conn):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        except:
            pass
        s.bind(("0.0.0.0", port))
        s.listen(5)
        self.lsock_wrapper = s
        self.lsock = raw(s)
        self.on_conn = on_conn
        self.arm_accept()

    def arm_accept(self):
        try:
            self.lsock.accept(self.accepted)
        except:
            self.app.log(u"accept: " + err_text())
            self.later(2, self.arm_accept)

    def accepted(self, res):
        if is_err(res):
            self.app.log(u"accept: " + to_u(str(res[1])))
            if self.lsock is not None:
                self.later(1, self.arm_accept)
            return
        sock = res[0]
        addr = res[1]
        self.arm_accept()
        self.app.safe(self.on_conn, PhoneConn(sock, self.app), addr[0])

    def stop_listen(self):
        u = getattr(self, "usock", None)
        self.usock = None
        if u is not None:
            try:
                u.close()
            except:
                pass
        s = self.lsock
        self.lsock = None
        if s is not None:
            try:
                s.close()
            except:
                pass

    def connect(self, host, port, on_ok, on_err):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        except:
            self.later(0, lambda on_err=on_err: on_err(err_text()))
            return

        def cb(res, self=self, s=s, on_ok=on_ok, on_err=on_err):
            if is_err(res):
                # no close() here, see the note above PhoneConn
                self.app.safe(on_err, to_u(str(res[1])))
                return
            self.app.safe(on_ok, PhoneConn(raw(s), self.app))
        try:
            raw(s).connect((host, port), cb)
        except:
            msg = err_text()
            self.later(0, lambda on_err=on_err, msg=msg: on_err(msg))

    def udp_send(self, host, port, data):
        # one reusable sending socket (never closed, see the note above)
        u = getattr(self, "usend", None)
        if u is None:
            u = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                u.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            except:
                pass
            self.usend = u
        try:
            u.sendto(data, (host, port))
        except:
            self.usend = None
            raise

    def udp_listen(self, port, on_packet):
        u = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        u.bind(("0.0.0.0", port))
        self.usock_wrapper = u
        self.usock = raw(u)
        self.on_packet = on_packet
        self.arm_udp()

    def arm_udp(self):
        try:
            self.usock.recvfrom(4096, 0, self.got_udp)
        except:
            self.app.log(u"udp: " + err_text())

    def got_udp(self, res):
        if is_err(res):
            self.app.log(u"udp: " + to_u(str(res[1])))
            self.later(2, self.arm_udp)
            return
        data = res[0]
        addr = res[1]
        self.arm_udp()
        self.app.safe(self.on_packet, data, addr[0])


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
        return (bw - 4, ph - 8)

    def canvas_size(self):
        try:
            return self.canvas.size
        except:
            return (240, 234)

    def preview_height(self):
        w, h = self.canvas_size()
        ph = int(h * 42 / 100)
        if ph > 140:
            ph = 140
        return ph

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
        BLUE = 0x146EDC
        c.clear(0xFFFFFF)
        # preview box
        c.rectangle((0, 0, w, ph), fill=0xEEF3FA)
        bw, bh = self.box_size()
        c.rectangle((2, 4, 2 + bw, 4 + bh), outline=0xB0C4DE, fill=0xFFFFFF)
        p = self.current_file()
        e = self.current()
        tx = bw + 8
        if p is not None:
            img = self.cache.get(p)
            if img is not None:
                iw, ih = img.size
                c.blit(img, target=(2 + (bw - iw) / 2, 4 + (bh - ih) / 2))
            else:
                kind = u"FILE"
                if ext_in(p, IMAGE_EXT):
                    kind = u"PHOTO"
                elif ext_in(p, AUDIO_EXT):
                    kind = u"MUSIC"
                elif ext_in(p, VIDEO_EXT):
                    kind = u"VIDEO"
                if not self.cache.has_key(p):
                    kind = u"..."
                c.text((10, 4 + bh / 2 + 5), kind, fill=0x7A8CA5, font="dense")
            lines = [to_u(os.path.basename(p))] + self.info.get(p, [])
            y = 18
            for line in lines[:6]:
                c.text((tx, y), clip(line, (w - tx) / 6), fill=0x202020, font="dense")
                y = y + 16
            if self.marked.has_key(p):
                c.text((tx, ph - 6), u"[x] marked", fill=BLUE, font="dense")
        elif e is not None:
            c.text((tx, 24), u"Folder", fill=0x202020, font="dense")
            c.text((tx, 40), clip(e[0], (w - tx) / 6), fill=0x202020, font="dense")
            c.text((tx, ph - 6), u"Centre: open", fill=0x7A8CA5, font="dense")
        # list
        rh = 18
        rows = (h - ph - 2) / rh
        if rows < 1:
            rows = 1
        if self.cur < self.top:
            self.top = self.cur
        if self.cur >= self.top + rows:
            self.top = self.cur - rows + 1
        y = ph + 2
        i = self.top
        while i < len(self.entries) and i < self.top + rows:
            label, name, is_dir = self.entries[i]
            sel = (i == self.cur)
            fg = 0x000000
            if sel:
                c.rectangle((0, y, w, y + rh), fill=BLUE)
                fg = 0xFFFFFF
            if is_dir:
                box = u"> "
            elif self.marked.has_key(self.path + name):
                box = u"[x] "
            else:
                box = u"[  ] "
            c.text((4, y + rh - 4), box + clip(label, (w - 30) / 6), fill=fg, font="dense")
            y = y + rh
            i = i + 1
        if not self.entries:
            c.text((8, ph + 20), u"(empty folder)", fill=0x7A8CA5, font="dense")


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


# grid.py (photo grid) and webshare.py (browser sharing) are pasted here by
# build_sis.sh; on the PC they are imported and given this module's helpers.
#@INLINE grid.py
import grid as _gr; _gr.__dict__.update(globals()); PhotoGrid = _gr.PhotoGrid
#@INLINE webshare.py
import webshare as _ws; _ws.__dict__.update(globals()); WebShare = _ws.WebShare


# ---------------------------------------------------------------- phone app

def find_dir(candidates):
    for c in candidates:
        if os.path.isdir(c):
            return c
    return None


def guess_model():
    if sysinfo is not None:
        try:
            v = sysinfo.sw_version()
            for tok in v.replace("(", " ").replace(")", " ").split(" "):
                if len(tok) >= 3 and tok[0] in "NEX" and tok[1:].isdigit():
                    return u"Nokia " + to_u(tok)
        except:
            pass
    return u"Nokia phone"


class App:
    """The user interface. Single-threaded: network events arrive as callbacks."""
    def __init__(self):
        self.lock = e32.Ao_lock()
        self.cfg_path = self.pick_cfg_path()
        self.cfg = self.load_cfg()
        self.net = PhoneNet(self)
        self.peers = []
        self.logs = []
        self.ip = None
        self.server = None
        self.server_error = None
        self.client = None
        self.tab = 0
        self.apo = None
        self.listbox = None
        self.picker = None

    def safe(self, func, *args):
        """Runs a callback; errors are logged instead of breaking the app."""
        try:
            apply(func, args)
        except:
            self.log(u"error: " + err_text())
            try:
                import traceback
                boot_log("".join(traceback.format_exception(sys.exc_info()[0],
                                                            sys.exc_info()[1],
                                                            sys.exc_info()[2])))
            except:
                pass

    def got_ip(self, ip):
        if ip and not self.ip and ip[:4] != "127." and ip != "0.0.0.0":
            self.ip = ip
            self.refresh()

    # ---- settings

    def pick_cfg_path(self):
        for d in ["C:\\Data\\", "E:\\", "C:\\"]:
            if os.path.isdir(d):
                return d + "retrosend.cfg"
        return "retrosend.cfg"

    def load_cfg(self):
        cfg = {}
        try:
            f = open(self.cfg_path, "rb")
            cfg = json_loads(f.read())
            f.close()
        except:
            cfg = {}
        if type(cfg) is not types.DictType:
            cfg = {}
        out = {}
        out["fingerprint"] = to_b(cfg.get(u"fingerprint", random_id() + random_id()))
        out["model"] = guess_model()
        out["alias"] = to_u(cfg.get(u"alias", out["model"]))
        out["port"] = int(cfg.get(u"port", DEFAULT_PORT))
        out["auto"] = int(cfg.get(u"auto", 0))
        out["apid"] = cfg.get(u"apid")
        default_dir = "C:\\Data\\RetroSend\\"
        if os.path.isdir("E:\\"):
            default_dir = "E:\\RetroSend\\"
        out["savedir"] = to_b(cfg.get(u"savedir", to_u(default_dir)))
        out["sort"] = int(cfg.get(u"sort", 1))
        out["web"] = int(cfg.get(u"web", 0))
        out["recent"] = []
        for r in cfg.get(u"recent", []):
            out["recent"].append(to_b(r))
        out["devices"] = []
        for d in cfg.get(u"devices", []):
            if type(d) is types.DictType and d.get(u"ip"):
                out["devices"].append({"alias": to_u(d.get(u"alias", u"?")),
                                       "ip": to_b(d[u"ip"]),
                                       "port": int(d.get(u"port", DEFAULT_PORT)),
                                       "fingerprint": to_u(d.get(u"fingerprint", u"")),
                                       "deviceModel": d.get(u"deviceModel"),
                                       "protocol": u"http"})
        return out

    def save_cfg(self):
        c = self.cfg
        d = {"fingerprint": c["fingerprint"], "alias": c["alias"], "port": c["port"],
             "auto": c["auto"], "savedir": to_u(c["savedir"]), "sort": c["sort"],
             "web": c["web"]}
        rec = []
        for r in c["recent"][-30:]:
            rec.append(to_u(r))
        d["recent"] = rec
        devs = []
        for p in c["devices"][:20]:
            devs.append({"alias": p["alias"], "ip": to_u(p["ip"]), "port": p["port"],
                         "fingerprint": p["fingerprint"],
                         "deviceModel": to_u(p.get("deviceModel") or u"")})
        d["devices"] = devs
        if c["apid"] is not None:
            d["apid"] = c["apid"]
        try:
            f = open(self.cfg_path, "wb")
            f.write(json_dumps(d))
            f.close()
        except:
            self.log(u"save settings: " + err_text())

    # ---- Wi-Fi access point (asked once, then remembered)

    def setup_ap(self, force=0):
        if force or self.cfg["apid"] is None:
            boot_log("asking for access point")
            try:
                apid = socket.select_access_point()
            except:
                apid = None
            boot_log("access point chosen: " + str(apid))
            if apid is None:
                return 0
            self.cfg["apid"] = int(apid)
            self.save_cfg()
        try:
            self.apo = socket.access_point(self.cfg["apid"])
            socket.set_default_access_point(self.apo)
            boot_log("default access point set")
            try:
                boot_log("starting Wi-Fi (phone may ask about offline mode)")
                self.apo.start()
                boot_log("access point started")
                self.got_ip(self.apo.ip())
                boot_log("ip " + str(self.ip))
            except:
                boot_log("ap start/ip: " + str(sys.exc_info()[1]))
            return 1
        except:
            self.log(u"access point: " + err_text())
            self.cfg["apid"] = None
            self.save_cfg()
            return 0

    # ---- events from the protocol code

    def log(self, msg):
        boot_log(to_b(msg))
        self.logs.append(time.strftime("%H:%M ") + to_b(msg))
        if len(self.logs) > 60:
            del self.logs[0]

    def peer(self, dev):
        if not valid_ip(dev["ip"]):
            return  # address unknown; the network sweep will find it
        for i in range(len(self.peers)):
            p = self.peers[i]
            if (dev["fingerprint"] and dev["fingerprint"] == p["fingerprint"]) or \
               (dev["ip"] == p["ip"] and dev["port"] == p["port"]):
                self.peers[i] = dev
                self.remember_device(dev)  # e.g. the router gave it a new IP
                return
        self.peers.append(dev)
        self.log(u"Found " + dev["alias"] + u" " + to_u(dev["ip"]))
        self.remember_device(dev)

    def remember_device(self, dev):
        devs = self.cfg["devices"]
        for i in range(len(devs)):
            p = devs[i]
            if (dev["fingerprint"] and dev["fingerprint"] == p["fingerprint"]) or \
               dev["ip"] == p["ip"]:
                if p["ip"] == dev["ip"] and p["alias"] == dev["alias"]:
                    return  # nothing new
                del devs[i]
                break
        devs.insert(0, {"alias": dev["alias"], "ip": dev["ip"], "port": dev["port"],
                        "fingerprint": dev["fingerprint"],
                        "deviceModel": dev.get("deviceModel"), "protocol": u"http"})
        self.save_cfg()

    def forget_device(self, dev):
        keep = []
        for p in self.cfg["devices"]:
            if p["ip"] != dev["ip"]:
                keep.append(p)
        self.cfg["devices"] = keep
        keep = []
        for p in self.peers:
            if p["ip"] != dev["ip"]:
                keep.append(p)
        self.peers = keep
        self.save_cfg()

    def saved(self, path):
        """A received file was written (called by the server)."""
        rec = self.cfg["recent"]
        rec.append(to_b(path))
        if len(rec) > 30:
            del rec[0]
        self.save_cfg()

    def ask_accept(self, dev, files, total, answer):
        if self.cfg["auto"]:
            answer(1)
            return
        # leave the network callback first, then show the question
        self.net.later(0, lambda self=self, dev=dev, files=files, total=total,
                       answer=answer: self.ask_now(dev, files, total, answer))

    def ask_now(self, dev, files, total, answer):
        names = []
        for f in files[:4]:
            names.append(to_u(jget(f, u"fileName", u"")))
        more = u""
        if len(files) > 4:
            more = u" ..."
        try:
            appuifw.note(u", ".join(names) + more, "info")
        except:
            pass
        msg = u"%s: %d file(s), %s. Accept?" % (dev["alias"], len(files), human_size(total))
        ok = 0
        try:
            if appuifw.query(msg, "query"):
                ok = 1
        except:
            pass
        answer(ok)

    def text_received(self, dev, text):
        self.log(u"Message from " + dev["alias"])
        self.net.later(0, lambda dev=dev, text=text:
                       appuifw.query(u"From " + dev["alias"] + u":", "text", text))

    def progress(self, title, done, total):
        now = time.time()
        if done == 0 or not getattr(self, "xfer_t0", 0) or done < getattr(self, "xfer_last", 0):
            self.xfer_t0 = now
            self.update_menu()  # a transfer just started: show Cancel / Stop
        self.xfer_last = done
        if not total:
            self.set_title(title)
            return
        pct = int(done * 100 / total)
        secs = now - self.xfer_t0
        if done > 0 and secs >= 1:
            rate = done / secs
            left = int((total - done) / rate)
            self.set_title(u"%d%% %s/s %s left" % (pct, human_size(rate), human_duration(left)))
        else:
            self.set_title(u"%d%% %s" % (pct, title))

    def finished(self, msg):
        self.log(msg)
        self.set_title(u"RetroSend")
        self.net.later(0, self.update_menu)
        self.net.later(0, lambda msg=msg: appuifw.note(msg, "conf"))
        self.refresh()

    def open_file(self, path):
        """Opens a file in the phone's own viewer or player."""
        try:
            if getattr(self, "content", None) is None:
                self.content = appuifw.Content_handler()
            try:
                self.content.open_standalone(to_u(path))
            except AttributeError:
                self.content.open(to_u(path))
        except:
            appuifw.note(u"Cannot open this file: " + err_text(), "error")

    def show_recent(self):
        rec = self.cfg["recent"][:]
        rec.reverse()
        keep = []
        for r in rec:
            if os.path.exists(r):
                keep.append(r)
        if not keep:
            appuifw.note(u"Nothing received yet.", "info")
            return
        labels = []
        for r in keep:
            try:
                size = human_size(os.path.getsize(r))
            except:
                size = u""
            labels.append(to_u(os.path.basename(r)) + u"  " + size)
        i = appuifw.selection_list(labels, 1)
        if i is None:
            return
        path = keep[i]
        what = appuifw.popup_menu([u"Open", u"Send to a device", u"Show in folder"],
                                  to_u(os.path.basename(path)))
        if what == 0:
            self.open_file(path)
        elif what == 1:
            self.choose_target([make_file_item(path)])
        elif what == 2:
            self.browse(os.path.dirname(path) + "\\", 1)

    def set_title(self, t):
        try:
            appuifw.app.title = t[:40]
        except:
            pass

    # ---- network

    def start_network(self):
        self.set_title(u"Connecting to Wi-Fi...")
        try:
            e32.ao_yield()  # let the title redraw before the blocking start
        except:
            pass
        boot_log("network: step 1 access point")
        if not self.setup_ap():
            appuifw.note(u"No Wi-Fi chosen. Options > Change Wi-Fi.", "error")
        boot_log("network: step 2 done, ip=" + str(self.ip))
        try:
            self.server = Server(self.cfg, self, self.net)
            self.server.start()
            self.server_error = None
            server = self.server
            self.web = WebShare(self.cfg, self,
                                lambda name, server=server: server.create_path(safe_name(name)))
            self.apply_web()
        except:
            self.server = None
            self.server_error = err_text()
            self.log(u"Cannot receive: " + self.server_error)
            if self.server_error.find(u"13") >= 0 or self.server_error.find(u"in use") >= 0:
                self.server_error = u"RetroSend is already running"
                appuifw.note(u"RetroSend is already running in the background. Hold the "
                             u"Menu key, select the other RetroSend and press C to close "
                             u"it, then open RetroSend again.", "error")
        boot_log("network: step 3 server")
        try:
            self.net.udp_listen(self.cfg["port"], self.got_announce)
            boot_log("network: udp listening")
        except:
            self.log(u"UDP listen: " + err_text())
        self.check_saved_devices()
        self.scan()
        boot_log("network: step 4 scan sent")
        self.set_title(u"RetroSend")
        self.refresh()

    def check_saved_devices(self):
        """Lists remembered devices right away and re-checks their address."""
        for d in self.cfg["devices"]:
            known = 0
            for p in self.peers:
                if p["ip"] == d["ip"]:
                    known = 1
            if not known:
                self.peers.append(d)
            c = Client(self.cfg, self, self.net)
            c.quiet = 1
            ignore = lambda *a: None
            c.register(d["ip"], d["port"], self.peer, ignore)

    def got_announce(self, data, ip):
        try:
            info = json_loads(data)
        except:
            return
        dev = make_dev(info, ip)
        if dev["fingerprint"] == to_u(self.cfg["fingerprint"]):
            return
        self.peer(dev)
        if jget(info, u"announce"):
            ignore = lambda *a: None
            Client(self.cfg, self, self.net).register(dev["ip"], dev["port"], self.peer, ignore)

    def scan(self):
        self.log(u"scan (announce + network sweep)")
        Client(self.cfg, self, self.net).announce(self.ip)
        self.sweep()

    def sweep(self):
        """Asks every address on this Wi-Fi network (x.x.x.1-254) for LocalSend."""
        if not self.ip:
            return
        if getattr(self, "sweep_left", 0) and time.time() - self.sweep_started < 60:
            return  # one is already running
        self.sweep_gen = getattr(self, "sweep_gen", 0) + 1
        self.sweep_started = time.time()
        base = self.ip[:self.ip.rfind(".") + 1]
        try:
            mine = int(self.ip[self.ip.rfind(".") + 1:])
        except:
            mine = 1
        # nearest addresses first: routers hand out neighbouring numbers
        order = []
        for i in range(1, 255):
            if i != mine:
                order.append((abs(i - mine), i))
        order.sort()
        self.sweep_queue = []
        for pair in order:
            self.sweep_queue.append(base + str(pair[1]))
        self.sweep_left = len(self.sweep_queue)
        self.sweep_before = len(self.peers)
        for k in range(8):
            self.sweep_next()

    def sweep_next(self):
        if not self.sweep_queue:
            return
        host = self.sweep_queue[0]
        del self.sweep_queue[0]
        c = Client(self.cfg, self, self.net)
        c.quiet = 1
        state = {"open": 1}
        gen = self.sweep_gen

        def end(*args):
            if not state["open"] or gen != self.sweep_gen:
                return
            state["open"] = 0
            self.sweep_left = self.sweep_left - 1
            if self.sweep_left <= 0:
                self.sweep_left = 0
                self.log(u"sweep done, %d device(s) known" % len(self.peers))
                self.set_title(u"RetroSend")
            elif self.sweep_left % 20 == 0:
                self.set_title(u"Scanning... %d left" % self.sweep_left)
            self.sweep_next()

        def found(dev, end=end):
            self.peer(dev)
            end()
        # No timeout/cancel: cancelling a pending connect would need close().
        # Silent addresses simply fail when the phone's connect times out.
        c.register(host, DEFAULT_PORT, found, end)

    # ---- UI

    def send_entries(self):
        return [(u"Send a photo", lambda self=self: self.pick_media("photo")),
                (u"Send a video", lambda self=self: self.pick_media("video")),
                (u"Send music", lambda self=self: self.pick_media("music")),
                (u"Send any file or folder", self.pick_from_drives),
                (u"Send contacts", self.send_contacts),
                (u"Send text message", self.send_text),
                (u"Share files to a browser", self.share_to_browser),
                (u"Devices", self.show_devices)]

    def recv_entries(self):
        nothing = lambda: None
        if self.server_error:
            status = u"Receiving OFF: " + self.server_error
        elif self.server is None:
            status = u"Starting..."
        else:
            status = u"Ready to receive"
        ip = u"IP: unknown (Options > Change Wi-Fi)"
        if self.ip:
            ip = u"IP: %s:%d" % (to_u(self.ip), self.cfg["port"])
        web = u"Browser sharing: OFF"
        if self.cfg["web"]:
            web = u"Browser sharing: ON"
            if self.ip:
                web = u"Browser: http://%s:%d/" % (to_u(self.ip), self.cfg["port"])
        return [(status, nothing),
                (u"Name: " + self.cfg["alias"], self.rename),
                (ip, nothing),
                (u"Received files", self.show_recent),
                (u"Browse received folder", lambda self=self: self.browse(self.cfg["savedir"], 1)),
                (u"Auto-accept: " + on_off(self.cfg["auto"]), self.toggle_auto),
                (u"Sort into Images/Music/Videos: " + on_off(self.cfg["sort"]), self.toggle_sort),
                (web, self.toggle_web),
                (u"Log", self.show_log),
                (u"About RetroSend " + VERSION, self.help)]

    def send_items(self):
        return entry_labels(self.send_entries())

    def recv_items(self):
        return entry_labels(self.recv_entries())

    def toggle_auto(self):
        self.cfg["auto"] = 1 - self.cfg["auto"]
        self.save_cfg()
        self.refresh()

    def toggle_sort(self):
        self.cfg["sort"] = 1 - self.cfg["sort"]
        self.save_cfg()
        if self.cfg["sort"]:
            appuifw.note(u"Photos, music and videos go to Images, Music and Videos, so "
                         u"Gallery and the Music player find them.", "info")
        self.refresh()

    def toggle_web(self):
        self.cfg["web"] = 1 - self.cfg["web"]
        self.save_cfg()
        self.apply_web()
        if self.cfg["web"]:
            appuifw.note(u"Open http://%s:%d/ in a browser on the same Wi-Fi to upload "
                         u"files or download shared ones." % (to_u(self.ip or "phone-ip"),
                                                              self.cfg["port"]), "info")
        self.refresh()

    def apply_web(self):
        if self.server is None:
            return
        if self.cfg["web"] and getattr(self, "web", None) is not None:
            self.server.web = self.web
        else:
            self.server.web = None

    def share_to_browser(self):
        def share(items, self=self):
            paths = []
            for it in items:
                paths.append(it["path"])
            self.web.set_shared(paths)
            if not self.cfg["web"]:
                self.toggle_web()
            else:
                appuifw.note(u"Sharing %d file(s) at http://%s:%d/" %
                             (len(paths), to_u(self.ip or "phone-ip"), self.cfg["port"]),
                             "info")
        if getattr(self, "web", None) is None:
            appuifw.note(u"Receiving is not running.", "error")
            return
        self.pick_target = share
        self.pick_from_drives()

    def send_contacts(self):
        try:
            import contacts
            db = contacts.open()
        except:
            appuifw.note(u"Cannot read contacts: " + err_text(), "error")
            return
        people = []
        for cid in db.keys():
            try:
                people.append((to_u(db[cid].title), cid))
            except:
                pass
        if not people:
            appuifw.note(u"No contacts.", "info")
            return
        people.sort()
        labels = []
        for name, cid in people:
            labels.append(name or u"(no name)")
        try:
            chosen = appuifw.multi_selection_list(labels, style="checkbox", search_field=1)
        except:
            chosen = None
        if not chosen:
            return
        ids = []
        for i in chosen:
            ids.append(people[i][1])
        try:
            data = db.export_vcards(tuple(ids))
        except:
            appuifw.note(u"Export failed: " + err_text(), "error")
            return
        name = u"contacts.vcf"
        if len(ids) == 1:
            name = safe_name(people[chosen[0]][0] or u"contact") + u".vcf"
        path = temp_dir() + "retrosend_" + to_b(name)
        f = open(path, "wb")
        f.write(data)
        f.close()
        self.log(u"exported %d contact(s)" % len(ids))
        self.choose_target([make_file_item(path, name)])

    def refresh(self):
        if self.listbox is None:
            return
        if self.tab == 0:
            items = self.send_items()
        else:
            items = self.recv_items()
        cur = 0
        try:
            cur = self.listbox.current()
        except:
            pass
        if cur >= len(items):
            cur = 0
        self.listbox.set_list(items, cur)

    def on_tab(self, i):
        boot_log("tab %d" % i)
        self.tab = i
        self.refresh()

    def on_select(self):
        i = self.listbox.current()
        boot_log("selected tab %d item %d" % (self.tab, i))
        if self.tab == 0:
            entries = self.send_entries()
        else:
            entries = self.recv_entries()
        if 0 <= i < len(entries):
            entries[i][1]()

    # ---- choosing files

    def pick_media(self, kind):
        if kind == "photo":
            cands = ["E:\\Images\\", "C:\\Data\\Images\\", "E:\\Photos\\"]
        elif kind == "video":
            cands = ["E:\\Videos\\", "E:\\My Videos\\", "C:\\Data\\Videos\\", "E:\\Images\\"]
        else:
            cands = ["E:\\Music\\", "E:\\Sounds\\", "E:\\My Music\\", "C:\\Data\\Sounds\\"]
        found = []
        for c in cands:
            if os.path.isdir(c):
                found.append(c)
        if not found:
            self.pick_from_drives()
        else:
            start = found[0]
            if len(found) > 1:
                labels = []
                for c in found:
                    labels.append(to_u(c))
                i = appuifw.popup_menu(labels, u"Which folder?")
                if i is None:
                    return
                start = found[i]
            if kind == "photo":
                self.switch_to_grid(start, {})
            else:
                self.browse(start)

    def pick_from_drives(self):
        drives = []
        for d in e32.drive_list():
            d = to_b(d)
            if d[:1].upper() not in "ZD" and os.path.isdir(d + "\\"):
                drives.append(d + "\\")
        labels = []
        for d in drives:
            labels.append(to_u(d))
        i = appuifw.popup_menu(labels, u"Drive")
        if i is not None:
            self.browse(drives[i])

    def browse(self, start, view_only=0):
        """Multi-select picker with previews; marked files go to choose_target."""
        if not os.path.isdir(start):
            appuifw.note(u"Nothing here yet: " + to_u(start), "info")
            return
        self.picker = Picker(self, start, self.picked, view_only)
        self.picker.show()

    def picked(self, paths, names=None):
        if names is None:
            names = {}
        items = []
        for p in paths:
            try:
                items.append(make_file_item(p, names.get(p)))
            except:
                self.log(u"skip " + to_u(p) + u": " + err_text())
        if not items:
            return
        target = getattr(self, "pick_target", None)
        self.pick_target = None
        if target is not None:
            target(items)
        else:
            self.choose_target(items)

    def switch_to_grid(self, path, marked, root=None):
        self.picker = PhotoGrid(self, path, self.picked, marked)
        self.picker.show()

    def switch_to_list(self, path, marked, root=None):
        self.picker = Picker(self, path, self.picked, 0, marked, root)
        self.picker.show()

    def restore_main(self):
        a = appuifw.app
        self.picker = None
        a.body = self.listbox
        self.update_menu()
        a.exit_key_handler = self.exit
        a.title = u"RetroSend"
        try:
            a.set_tabs([u"Send", u"Receive"], self.on_tab)
            a.activate_tab(self.tab)
        except:
            pass
        self.refresh()

    def send_text(self):
        t = appuifw.query(u"Message", "text")
        if t:
            self.choose_target([make_text_item(t)])

    # ---- devices and sending

    def choose_target(self, items):
        self.log(u"choose device for %d item(s), first %s (%d known)" %
                 (len(items), items[0]["name"], len(self.peers)))
        while 1:
            labels = []
            for p in self.peers:
                labels.append(p["alias"] + u" (" + to_u(p["ip"]) + u")")
            labels.append(u"Scan again")
            labels.append(u"Enter IP address...")
            what = u"Send to"
            if len(items) > 1:
                total = 0
                for it in items:
                    total = total + it["size"]
                what = u"Send %d files (%s) to" % (len(items), human_size(total))
            i = appuifw.popup_menu(labels, what)
            if i is None:
                return
            if i < len(self.peers):
                self.start_send(self.peers[i], items)
                return
            if i == len(self.peers):
                self.scan()
                appuifw.note(u"Scanning the Wi-Fi network...", "info")
                before = len(self.peers)
                waited = 0
                while waited < 40 and getattr(self, "sweep_left", 0) and \
                        len(self.peers) == before:
                    e32.ao_sleep(1)  # replies arrive meanwhile
                    waited = waited + 1
            else:
                self.add_by_ip(lambda dev, self=self, items=items: self.start_send(dev, items))
                return

    def add_by_ip(self, then=None):
        t = appuifw.query(u"IP address (as shown in LocalSend)", "text", u"192.168.")
        if not t:
            return
        host = to_b(t).strip()
        port = DEFAULT_PORT
        if host.find(":") >= 0:
            try:
                port = int(host[host.find(":") + 1:])
            except:
                pass
            host = host[:host.find(":")]
        self.set_title(u"Contacting " + to_u(host))

        def ok(dev, self=self, then=then):
            self.set_title(u"RetroSend")
            self.peer(dev)
            if then is not None:
                then(dev)
            else:
                appuifw.note(u"Added " + dev["alias"], "conf")

        def bad(msg, self=self, host=host):
            self.set_title(u"RetroSend")
            appuifw.note(u"Could not reach " + to_u(host) + u". Is LocalSend open with "
                         u"Encryption off, on the same Wi-Fi?\n" + to_u(msg), "error")
        Client(self.cfg, self, self.net).register(host, port, ok, bad)

    def show_devices(self):
        labels = []
        for p in self.peers:
            labels.append(p["alias"] + u" (" + to_u(p["ip"]) + u")")
        labels.append(u"Scan for devices")
        labels.append(u"Add by IP address...")
        i = appuifw.popup_menu(labels, u"Devices")
        if i is None:
            return
        if i == len(self.peers):
            self.scan()
            appuifw.note(u"Asked nearby LocalSend devices to reply.", "info")
        elif i == len(self.peers) + 1:
            self.add_by_ip()
        else:
            p = self.peers[i]
            what = appuifw.popup_menu([u"Details", u"Forget this device"], p["alias"])
            if what == 0:
                appuifw.note(u"%s\n%s:%d\n%s" % (p["alias"], to_u(p["ip"]), p["port"],
                                                 to_u(p.get("deviceModel") or u"")), "info")
            elif what == 1:
                self.forget_device(p)
                appuifw.note(u"Forgot " + p["alias"], "conf")

    def start_send(self, dev, items):
        if self.client is not None:
            appuifw.note(u"Already sending.", "error")
            return
        c = Client(self.cfg, self, self.net)
        self.client = c
        self.update_menu()
        self.log(u"sending to " + dev["alias"] + u" " + to_u(dev["ip"]) + u":%d" % dev["port"])
        self.net.later(0, lambda: appuifw.note(u"Sending. To stop: Options > Cancel sending",
                                               "info"))

        def done(msg, self=self):
            self.client = None
            self.finished(msg)

        def bad(msg, self=self, dev=dev):
            self.client = None
            self.log(u"send: " + to_u(msg))
            if msg == u"Cancelled." or msg[-9:] == u"declined." or msg.find(u"PIN") >= 0 \
               or msg.find(u"busy") >= 0:
                self.finished(msg)
            else:
                self.finished(u"Sending failed: " + to_u(msg) + u"\nIs LocalSend open on " +
                              dev["alias"] + u" with Encryption off?")
        c.send(dev, items, done, bad)

    def cancel_send(self):
        if self.client is not None:
            self.set_title(u"Cancelling...")
            self.client.cancel()
        else:
            appuifw.note(u"Nothing is being sent.", "info")

    def stop_receiving(self):
        if self.server is None or not self.server.stop_receiving():
            appuifw.note(u"Nothing is being received.", "info")
        self.update_menu()

    def update_menu(self):
        """Options menu; Cancel / Stop come first while a transfer runs."""
        if getattr(self, "picker", None) is not None:
            return  # the picker has its own menu
        menu = []
        if self.client is not None:
            menu.append((u"Cancel sending", self.cancel_send))
        if self.server is not None and self.server.receiving():
            menu.append((u"Stop receiving", self.stop_receiving))
        try:
            appuifw.app.menu = menu + self.main_menu
        except:
            pass

    # ---- other screens

    def show_log(self):
        text = u"\n".join(map(to_u, self.logs[-30:]))
        appuifw.query(u"Log", "text", text or u"(empty)")

    def rename(self):
        t = appuifw.query(u"Device name", "text", self.cfg["alias"])
        if t:
            self.cfg["alias"] = t
            self.save_cfg()
            self.refresh()

    def change_ap(self):
        if self.setup_ap(1):
            appuifw.note(u"Wi-Fi saved. Restart RetroSend to use it everywhere.", "info")
        self.refresh()

    def help(self):
        appuifw.note(u"RetroSend " + VERSION + u". On the other device: open LocalSend, Settings > turn Encryption OFF. "
                     u"Same Wi-Fi as this phone. If this phone is not listed there, "
                     u"use Add by IP here with the IP shown in LocalSend.", "info")

    def tick(self):
        self.ticks = self.ticks + 1
        if self.ticks <= 15 or self.ticks % 30 == 0:
            boot_log("tick %d (screen responsive)" % self.ticks)
        self.net.later(2, self.tick)

    def exit(self):
        if self.server is not None:
            self.server.stop()
        self.lock.signal()

    def run(self):
        appuifw.app.title = u"RetroSend"
        appuifw.app.screen = "normal"
        self.listbox = appuifw.Listbox(self.send_items(), self.on_select)
        appuifw.app.body = self.listbox
        appuifw.app.set_tabs([u"Send", u"Receive"], self.on_tab)
        self.main_menu = [(u"Scan for devices", self.scan),
                            (u"Add device by IP", self.add_by_ip),
                            (u"Device name", self.rename),
                            (u"Change Wi-Fi", self.change_ap),
                            (u"Help", self.help),
                            (u"Exit", self.exit)]
        self.update_menu()
        appuifw.app.exit_key_handler = self.exit
        boot_log("ui ready")
        self.refresh()
        self.ticks = 0
        self.net.later(2, self.tick)
        self.net.later(1, self.start_network)
        boot_log("waiting for user")
        self.lock.wait()
        appuifw.app.set_tabs([], None)
        appuifw.app.menu = []
        appuifw.app.body = None


def main():
    boot_log("main")
    try:
        app = App()
        boot_log("app created")
        app.run()
        boot_log("app ended normally")
    except:
        show_crash("main")


if not getattr(appuifw, 'FAKE', 0):
    main()
