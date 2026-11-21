# Browser sharing through the real Server on one port, next to the LocalSend API.
import os, sys, time, json, threading, tempfile, httplib
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "fake_s60")); sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))
import retrosend, pcnet
NET = pcnet.SelectNet(); t = threading.Thread(target=NET.run); t.setDaemon(True); t.start()
fails = []
def check(n, c):
    print((c and "PASS " or "FAIL ") + n)
    if not c: fails.append(n)
class Ev(object):
    fin = []
    def log(self, m): pass
    def peer(self, d): pass
    def ask_accept(self, d, f, total, answer): answer(1)
    def text_received(self, d, t): self.fin.append(t)
    def progress(self, *a): pass
    def finished(self, m): self.fin.append(m)
work = tempfile.mkdtemp() + "/"
cfg = {"alias": u"Nokia N79", "fingerprint": "fp", "port": 53420, "savedir": work, "sort": 0}
ev = Ev()
srv = retrosend.Server(cfg, ev, NET)
NET.call(srv.start); time.sleep(0.3)
shared = work + "share.txt"; open(shared, "wb").write("hello browser")
def get(path, method="GET", body=None, headers={}):
    c = httplib.HTTPConnection("127.0.0.1", 53420, timeout=10)
    c.request(method, path, body, headers); r = c.getresponse(); return r.status, r.read()
code, _ = get("/")
check("web off: / is 404", code == 404)
web = retrosend.WebShare(cfg, ev, lambda name: srv.create_path(retrosend.safe_name(name)))
web.set_shared([shared])
srv.web = web
code, page = get("/")
check("web on: index lists shared file", code == 200 and page.find("share.txt") >= 0)
code, data = get("/dl/0/share.txt")
check("download works", code == 200 and data == "hello browser")
code, info = get("/api/localsend/v2/info")
check("LocalSend API still answered on same port", code == 200 and json.loads(info)["alias"] == u"Nokia N79")
b = "XyZ123"
body = "--%s\r\nContent-Disposition: form-data; name=\"f\"; filename=\"up.bin\"\r\nContent-Type: application/octet-stream\r\n\r\n%s\r\n--%s--\r\n" % (b, "u" * 50000, b)
code, _ = get("/upload", "POST", body, {"Content-Type": "multipart/form-data; boundary=" + b, "Content-Length": str(len(body))})
check("browser upload saved via server path", code == 200 and open(work + "up.bin", "rb").read() == "u" * 50000)
print(fails and "FAILED" or "ALL PASSED"); sys.stdout.flush(); os._exit(len(fails))
