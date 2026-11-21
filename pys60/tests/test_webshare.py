# -*- coding: utf-8 -*-
# Browser sharing (webshare.py) on the PC with the async SelectNet.
import os, sys, time, socket, threading, tempfile, httplib, urllib, random
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "fake_s60")); sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))
import retrosend, pcnet

if hasattr(retrosend, "WebShare"):
    WebShare = retrosend.WebShare
else:
    import webshare
    webshare.__dict__.update(dict([(k, v) for (k, v) in retrosend.__dict__.items()
                                   if not k.startswith("__")]))
    WebShare = webshare.WebShare

PORT = 53420
NET = pcnet.SelectNet()
lt = threading.Thread(target=NET.run); lt.setDaemon(True); lt.start()
fails = []
def check(n, c):
    print((c and "PASS " or "FAIL ") + n)
    if not c: fails.append(n)

class Ev(object):
    def __init__(self): self.fin = []; self.texts = []; self.logs = []
    def log(self, m): self.logs.append(m)
    def finished(self, m): self.fin.append(m)
    def progress(self, *a): pass
    def text_received(self, d, t): self.texts.append((d["alias"], t))

work = tempfile.mkdtemp() + "/"
updir = work + "in/"; os.mkdir(updir)
def path_for(name):
    p = updir + name.encode("utf-8")
    n = 1
    while os.path.exists(p):
        p = updir + ("%d_" % n) + name.encode("utf-8"); n += 1
    return p

ev = Ev()
ws = WebShare({"alias": u"Nokia N79"}, ev, path_for)
big = work + "song.mp3"; bigdata = os.urandom(1024 * 1024); open(big, "wb").write(bigdata)
uni = work + u"Photo é ✓.jpg".encode("utf-8"); open(uni, "wb").write("jpegdata")
ws.set_shared([big, uni])

def on_conn(conn, ip):
    st = {"buf": ""}
    def got(data):
        if not data:
            conn.close(); return
        st["buf"] += data
        i = st["buf"].find("\r\n\r\n")
        if i < 0:
            conn.recv(got); return
        first, headers = retrosend.parse_head(st["buf"][:i])
        method, target = first.split(" ")[0], first.split(" ")[1]
        ws.handle(conn, ip, method, target, headers, st["buf"][i + 4:])
    conn.recv(got)
NET.call(lambda: NET.listen(PORT, on_conn))
time.sleep(0.3)

def get(path):
    c = httplib.HTTPConnection("127.0.0.1", PORT, timeout=15)
    c.request("GET", path); r = c.getresponse(); d = r.read(); c.close()
    return r, d

# index
r, d = get("/")
check("index 200 html", r.status == 200 and r.getheader("content-type").startswith("text/html"))
check("index lists files", d.find("song.mp3") >= 0 and d.find("/dl/0/") >= 0 and d.find("/dl/1/") >= 0
      and d.find("Nokia N79") >= 0 and d.find('enctype="multipart/form-data"') >= 0)
# download
r, d = get("/dl/0/song.mp3")
check("download 1 MB identical", r.status == 200 and d == bigdata)
check("download headers", r.getheader("content-length") == str(len(bigdata))
      and r.getheader("content-type") == "audio/mpeg"
      and r.getheader("content-disposition").find('filename="song.mp3"') >= 0)
r, d = get("/dl/1/" + urllib.quote(u"Photo é ✓.jpg".encode("utf-8")))
cd = r.getheader("content-disposition") or ""
check("UTF-8 name download", r.status == 200 and d == "jpegdata"
      and cd.find("filename*=UTF-8''Photo%20%C3%A9%20%E2%9C%93.jpg") >= 0 and cd.find('filename="Photo _ _.jpg"') >= 0)
r, d = get("/dl/9/x")
check("download bad index 404", r.status == 404)
r, d = get("/nope")
check("unknown path 404", r.status == 404)

# upload of 2 files in odd-sized chunks
def multipart(parts, boundary):
    out = []
    for name, fname, data in parts:
        out.append("--" + boundary + "\r\n")
        if fname is None:
            out.append('Content-Disposition: form-data; name="%s"\r\n\r\n' % name)
        else:
            out.append('Content-Disposition: form-data; name="%s"; filename="%s"\r\n'
                       'Content-Type: application/octet-stream\r\n\r\n' % (name, fname))
        out.append(data + "\r\n")
    out.append("--" + boundary + "--\r\n")
    return "".join(out)

b = "----RetroBoundary7MA4YWxk"
f1 = os.urandom(700 * 1024) + ("\r\n--" + b[:-3])   # near-boundary bytes inside data
f2 = "hello\r\nworld"
body = multipart([("f", "big.bin", f1), ("note", None, "ignored"), ("f", "../evil/x.txt", f2)], b)
s = socket.create_connection(("127.0.0.1", PORT))
s.sendall("POST /upload HTTP/1.1\r\nHost: x\r\nContent-Type: multipart/form-data; boundary=%s\r\n"
          "Content-Length: %d\r\n\r\n" % (b, len(body)))
for i in range(0, len(body), 1000):
    s.sendall(body[i:i + 1000])
resp = ""
while 1:
    x = s.recv(65536)
    if not x: break
    resp += x
s.close()
check("upload 200 says 2 files", resp.startswith("HTTP/1.1 200") and resp.find("Received 2 file(s)") >= 0)
check("uploaded big file identical", open(updir + "big.bin", "rb").read() == f1)
check("uploaded name sanitized (../evil/x.txt -> x.txt)", os.path.exists(updir + "x.txt")
      and open(updir + "x.txt", "rb").read() == f2)
check("finished event", u"Received 2 file(s) from browser" in ev.fin)

# text message
c = httplib.HTTPConnection("127.0.0.1", PORT, timeout=15)
c.request("POST", "/text", urllib.urlencode({"msg": u"hi from browser é".encode("utf-8")}),
          {"Content-Type": "application/x-www-form-urlencoded"})
r = c.getresponse(); r.read(); c.close()
check("text message delivered", r.status == 200 and (u"Browser", u"hi from browser é") in ev.texts)

# disconnect mid-upload deletes the partial file
body = multipart([("f", "partial.bin", os.urandom(300000))], b)
s = socket.create_connection(("127.0.0.1", PORT))
s.sendall("POST /upload HTTP/1.1\r\nContent-Type: multipart/form-data; boundary=%s\r\n"
          "Content-Length: %d\r\n\r\n" % (b, len(body)))
s.sendall(body[:150000]); time.sleep(0.4)
check("partial file exists while uploading", os.path.exists(updir + "partial.bin"))
s.close(); time.sleep(0.5)
check("partial file deleted after disconnect", not os.path.exists(updir + "partial.bin"))

print(fails and "FAILED" or "ALL PASSED")
sys.stdout.flush()
os._exit(len(fails))
