# Media helpers for RetroSend (Python 2.2 / PyS60 1.4.5 compatible).
# read_id3(path): song title/artist/album and album art from ID3 tags.
# video_info(path): duration in seconds of MP4/3GP/M4A files.
# Never raise: errors give None values.

import os
import struct

MAX_TAG = 2 * 1024 * 1024


def _empty():
    return {u"title": None, u"artist": None, u"album": None, "art": None, "art_ext": None}


def _syncsafe(b):
    return ((ord(b[0]) & 0x7f) << 21) | ((ord(b[1]) & 0x7f) << 14) | \
           ((ord(b[2]) & 0x7f) << 7) | (ord(b[3]) & 0x7f)


def _be32(b):
    return (ord(b[0]) << 24) | (ord(b[1]) << 16) | (ord(b[2]) << 8) | ord(b[3])


def _be24(b):
    return (ord(b[0]) << 16) | (ord(b[1]) << 8) | ord(b[2])


def _strip_nul(s):
    while s[-1:] == u"\x00":
        s = s[:-1]
    return s


def _decode(enc, data):
    try:
        if enc == 0:
            s = unicode(data, "latin-1")
        elif enc == 1:
            s = unicode(data, "utf-16")
        elif enc == 2:
            s = unicode(data, "utf-16-be")
        elif enc == 3:
            s = unicode(data, "utf-8")
        else:
            s = unicode(data, "latin-1")
    except:
        try:
            s = unicode(data, "latin-1")
        except:
            return None
    s = _strip_nul(s).strip()
    if not s:
        return None
    return s


def _text_frame(data):
    if not data:
        return None
    enc = ord(data[0])
    body = data[1:]
    # a text frame may hold several NUL-separated values; keep the first
    if enc == 1 or enc == 2:
        i = 0
        while i + 1 < len(body):
            if body[i] == "\x00" and body[i + 1] == "\x00":
                body = body[:i]
                break
            i = i + 2
    else:
        i = body.find("\x00")
        if i >= 0:
            body = body[:i]
    return _decode(enc, body)


def _skip_cstring(enc, data, pos):
    """Returns the position after a NUL-terminated string in encoding enc."""
    if enc == 1 or enc == 2:
        i = pos
        while i + 1 < len(data):
            if data[i] == "\x00" and data[i + 1] == "\x00":
                return i + 2
            i = i + 2
        return len(data)
    i = data.find("\x00", pos)
    if i < 0:
        return len(data)
    return i + 1


def _art_ext(mime, img):
    m = mime.lower()
    if img[:8] == "\x89PNG\r\n\x1a\n" or m.find("png") >= 0:
        return "png"
    if img[:3] == "\xff\xd8\xff" or m.find("jp") >= 0:
        return "jpg"
    return None


def _apic(data):
    """APIC (v2.3/2.4): enc, mime\\0, picture type, description\\0, image."""
    enc = ord(data[0])
    i = data.find("\x00", 1)
    if i < 0:
        return None, None
    mime = data[1:i]
    pos = i + 2  # skip NUL and picture type byte
    pos = _skip_cstring(enc, data, pos)
    img = data[pos:]
    if not img:
        return None, None
    return img, _art_ext(mime, img)


def _pic(data):
    """PIC (v2.2): enc, 3-char format, picture type, description\\0, image."""
    enc = ord(data[0])
    fmt = data[1:4]
    pos = _skip_cstring(enc, data, 5)
    img = data[pos:]
    if not img:
        return None, None
    return img, _art_ext(fmt, img)


def _id3v1(f, out):
    try:
        f.seek(0, 2)
        size = f.tell()
        if size < 128:
            return
        f.seek(size - 128)
        b = f.read(128)
        if b[:3] != "TAG":
            return
        out[u"title"] = _decode(0, b[3:33].split("\x00")[0])
        out[u"artist"] = _decode(0, b[33:63].split("\x00")[0])
        out[u"album"] = _decode(0, b[63:93].split("\x00")[0])
    except:
        pass


def read_id3(path):
    out = _empty()
    f = None
    try:
        try:
            f = open(path, "rb")
            head = f.read(10)
            if len(head) < 10 or head[:3] != "ID3":
                _id3v1(f, out)
                return out
            ver = ord(head[3])
            flags = ord(head[5])
            size = _syncsafe(head[6:10])
            if size > MAX_TAG:
                size = MAX_TAG
            data = f.read(size)
            if ver < 4 and (flags & 0x80):
                data = data.replace("\xff\x00", "\xff")
            pos = 0
            if ver >= 3 and (flags & 0x40):
                if len(data) < 4:
                    return out
                if ver == 4:
                    pos = _syncsafe(data[0:4])
                else:
                    pos = _be32(data[0:4]) + 4
            if ver == 2:
                hlen = 6
                names = {"TT2": u"title", "TP1": u"artist", "TAL": u"album"}
            else:
                hlen = 10
                names = {"TIT2": u"title", "TPE1": u"artist", "TALB": u"album"}
            while pos + hlen <= len(data):
                if data[pos] == "\x00":
                    break  # padding
                if ver == 2:
                    fid = data[pos:pos + 3]
                    fsize = _be24(data[pos + 3:pos + 6])
                elif ver == 4:
                    fid = data[pos:pos + 4]
                    fsize = _syncsafe(data[pos + 4:pos + 8])
                else:
                    fid = data[pos:pos + 4]
                    fsize = _be32(data[pos + 4:pos + 8])
                pos = pos + hlen
                if fsize <= 0 or pos + fsize > len(data):
                    break
                body = data[pos:pos + fsize]
                pos = pos + fsize
                if names.has_key(fid):
                    if out[names[fid]] is None:
                        out[names[fid]] = _text_frame(body)
                elif (fid == "APIC" or fid == "PIC") and out["art"] is None:
                    try:
                        if fid == "PIC":
                            img, ext = _pic(body)
                        else:
                            img, ext = _apic(body)
                        out["art"] = img
                        out["art_ext"] = ext
                    except:
                        pass
            if out[u"title"] is None and out[u"artist"] is None and out[u"album"] is None:
                _id3v1(f, out)
        except:
            pass
    finally:
        if f is not None:
            try:
                f.close()
            except:
                pass
    return out


def _find_mvhd(f, start, end, depth):
    pos = start
    while pos + 8 <= end:
        f.seek(pos)
        h = f.read(8)
        if len(h) < 8:
            return None
        size = _be32(h[0:4])
        kind = h[4:8]
        hdr = 8
        if size == 1:
            big = f.read(8)
            if len(big) < 8:
                return None
            size = (_be32(big[0:4]) * 4294967296.0) + _be32(big[4:8])
            size = long(size)
            hdr = 16
        elif size == 0:
            size = end - pos
        if size < hdr:
            return None
        if kind == "mvhd":
            f.seek(pos + hdr)
            b = f.read(32)
            if len(b) < 20:
                return None
            v = ord(b[0])
            if v == 1:
                if len(b) < 32:
                    return None
                scale = _be32(b[20:24])
                dur = _be32(b[24:28]) * 4294967296.0 + _be32(b[28:32])
            else:
                scale = _be32(b[12:16])
                dur = float(_be32(b[16:20]))
            if scale == 0:
                return None
            return dur / scale
        if kind == "moov" and depth < 3:
            r = _find_mvhd(f, pos + hdr, pos + size, depth + 1)
            if r is not None:
                return r
        pos = pos + size
    return None


def video_info(path):
    f = None
    try:
        try:
            f = open(path, "rb")
            f.seek(0, 2)
            end = f.tell()
            f.seek(0)
            h = f.read(8)
            if len(h) < 8 or h[4:8] not in ("ftyp", "moov", "mdat", "free", "wide", "skip"):
                return None
            return _find_mvhd(f, 0, end, 0)
        except:
            return None
    finally:
        if f is not None:
            try:
                f.close()
            except:
                pass


def human_duration(seconds):
    try:
        s = int(seconds + 0.5)
    except:
        return u"?"
    h = s / 3600
    m = (s % 3600) / 60
    sec = s % 60
    if h:
        return u"%d:%02d:%02d" % (h, m, sec)
    return u"%d:%02d" % (m, sec)
