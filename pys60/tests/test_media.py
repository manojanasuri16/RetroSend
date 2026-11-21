# -*- coding: utf-8 -*-
# Tests for media.py (ID3 tags + album art, MP4 duration). Python 2.7.
import os, sys, struct, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import media

fails = []
def check(name, cond):
    print((cond and "PASS " or "FAIL ") + name)
    if not cond:
        fails.append(name)

def syncsafe(n):
    return chr((n >> 21) & 0x7f) + chr((n >> 14) & 0x7f) + chr((n >> 7) & 0x7f) + chr(n & 0x7f)

def tag(ver, frames, flags=0, pad=64):
    body = "".join(frames) + "\x00" * pad
    return "ID3" + chr(ver) + "\x00" + chr(flags) + syncsafe(len(body)) + body

def f23(fid, data): return fid + struct.pack(">I", len(data)) + "\x00\x00" + data
def f24(fid, data): return fid + syncsafe(len(data)) + "\x00\x00" + data
def f22(fid, data): return fid + struct.pack(">I", len(data))[1:] + data

d = tempfile.mkdtemp(prefix="media_test_")
def write(name, data):
    p = os.path.join(d, name); f = open(p, "wb"); f.write(data); f.close(); return p

JPG = "\xff\xd8\xff\xe0" + "jpegdata\xff\x00x" * 20
PNG = "\x89PNG\r\n\x1a\n" + "pngdata" * 20
audio = "\xff\xfb\x90\x00" * 100

# v2.3: UTF-16 title, latin-1 artist, APIC jpeg (with UTF-16 description)
title = u"Caf\xe9 Song"
fr = [f23("TIT2", "\x01" + title.encode("utf-16")),
      f23("TPE1", "\x00" + u"Art\xefst".encode("latin-1")),
      f23("APIC", "\x01image/jpeg\x00\x03" + u"cover".encode("utf-16") + "\x00\x00" + JPG)]
r = media.read_id3(write("a.mp3", tag(3, fr) + audio))
check("v2.3 title utf-16", r[u"title"] == title)
check("v2.3 artist latin-1", r[u"artist"] == u"Art\xefst")
check("v2.3 album none", r[u"album"] is None)
check("v2.3 jpeg art", r["art"] == JPG and r["art_ext"] == "jpg")

# v2.4: UTF-8, syncsafe frame sizes (large frame > 127 bytes), PNG art
big_album = u"Albüm " + u"x" * 200
fr = [f24("TIT2", "\x03" + u"संगीत".encode("utf-8")),
      f24("TALB", "\x03" + big_album.encode("utf-8") + "\x00"),
      f24("APIC", "\x03image/png\x00\x03desc\x00" + PNG)]
r = media.read_id3(write("b.mp3", tag(4, fr) + audio))
check("v2.4 utf-8 title", r[u"title"] == u"संगीत")
check("v2.4 syncsafe big album", r[u"album"] == big_album)
check("v2.4 png art", r["art"] == PNG and r["art_ext"] == "png")

# v2.2 with PIC
fr = [f22("TT2", "\x00Old Song"), f22("TP1", "\x00Old Band"), f22("TAL", "\x00Old Album"),
      f22("PIC", "\x00JPG\x03\x00" + JPG)]
r = media.read_id3(write("c.mp3", tag(2, fr) + audio))
check("v2.2 text", r[u"title"] == u"Old Song" and r[u"artist"] == u"Old Band" and r[u"album"] == u"Old Album")
check("v2.2 PIC art", r["art"] == JPG and r["art_ext"] == "jpg")

# v2.3 unsynchronised tag: 0xFF 0x00 must be removed
fr = [f23("TIT2", "\x00Sync"), f23("APIC", "\x00image/jpeg\x00\x03\x00" + JPG)]
raw = "".join(fr) + "\x00" * 16
uns = raw.replace("\xff", "\xff\x00")
r = media.read_id3(write("u.mp3", "ID3\x03\x00\x80" + syncsafe(len(uns)) + uns + audio))
check("v2.3 unsync", r[u"title"] == u"Sync" and r["art"] == JPG)

# ID3v1 only
v1 = "TAG" + "V1 Title".ljust(30, "\x00") + "V1 Artist".ljust(30, "\x00") + "V1 Album".ljust(30, "\x00") + "2008" + "\x00" * 30 + "\x00"
r = media.read_id3(write("d.mp3", audio + v1))
check("id3v1", r[u"title"] == u"V1 Title" and r[u"artist"] == u"V1 Artist" and r[u"album"] == u"V1 Album" and r["art"] is None)

# garbage / truncated / missing
r = media.read_id3(write("e.mp3", "\x00\x01garbage" * 3))
check("garbage -> None values", r[u"title"] is None and r["art"] is None)
r = media.read_id3(write("t.mp3", "ID3\x03\x00\x00\x00\x00\x10\x00TIT2\x00\x00"))
check("truncated tag ok", r[u"title"] is None)
r = media.read_id3(os.path.join(d, "missing.mp3"))
check("missing file ok", r[u"title"] is None)

# MP4: ftyp + large sparse mdat + moov/mvhd v0
def atom(kind, data): return struct.pack(">I", 8 + len(data)) + kind + data
mvhd0 = atom("mvhd", "\x00\x00\x00\x00" + struct.pack(">IIII", 0, 0, 1000, 83500) + "\x00" * 80)
p = os.path.join(d, "v.mp4"); f = open(p, "wb")
f.write(atom("ftyp", "isom\x00\x00\x02\x00isom"))
mdat_size = 50 * 1024 * 1024
f.write(struct.pack(">I", mdat_size) + "mdat")
f.seek(mdat_size - 8, 1)
f.write(atom("moov", mvhd0)); f.close()
check("mp4 mvhd v0 after big mdat", media.video_info(p) == 83.5)

# mvhd v1 inside moov, and 64-bit largesize mdat
mvhd1 = atom("mvhd", "\x01\x00\x00\x00" + struct.pack(">QQIQ", 0, 0, 600, 600 * 3725) + "\x00" * 80)
mdat64 = struct.pack(">I", 1) + "mdat" + struct.pack(">Q", 16 + 100) + "\x00" * 100
p = write("w.3gp", atom("ftyp", "3gp4\x00\x00\x00\x00") + mdat64 + atom("moov", atom("udta", "") + mvhd1))
check("3gp mvhd v1 + largesize", media.video_info(p) == 3725.0)

check("non-mp4 -> None", media.video_info(write("x.avi", "RIFF" + "\x00" * 100)) is None)
check("missing video -> None", media.video_info(os.path.join(d, "nope.mp4")) is None)

check("duration m:ss", media.human_duration(83.5) == u"1:24")
check("duration h:mm:ss", media.human_duration(3725) == u"1:02:05")

print(fails and "\nFAILED: " + ", ".join(fails) or "\nALL PASSED")
sys.exit(fails and 1 or 0)
