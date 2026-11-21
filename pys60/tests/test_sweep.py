# Network sweep test: App.sweep() must find a LocalSend device by contacting
# every address of the subnet (127.0.0.x here) and give up on silent ones.
import os, sys, time, json, threading, BaseHTTPServer, SocketServer
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "fake_s60"))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))
import retrosend, pcnet

class H(BaseHTTPServer.BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length", 0)))
        body = json.dumps({"alias": "Android Test", "fingerprint": "andfp", "deviceModel": "Pixel"})
        self.send_response(200); self.send_header("Content-Length", str(len(body))); self.end_headers()
        self.wfile.write(body)
class S(SocketServer.ThreadingMixIn, BaseHTTPServer.HTTPServer): daemon_threads = True
httpd = S(("127.0.0.5", 53317), H)
threading.Thread(target=httpd.serve_forever).setDaemon(True) or None
t = threading.Thread(target=httpd.serve_forever); t.setDaemon(True); t.start()

retrosend.valid_ip = lambda ip: 1
import tempfile; os.chdir(tempfile.mkdtemp())  # keep retrosend.cfg out of the repo
net = pcnet.SelectNet()
lt = threading.Thread(target=net.run); lt.setDaemon(True); lt.start()
app = retrosend.App()
app.net = net
app.ip = "127.0.0.1"
start = time.time()
net.call(app.sweep)
while time.time() - start < 60:
    time.sleep(0.5)
    if getattr(app, "sweep_left", 1) == 0 and time.time() - start > 1:
        break
names = [p["alias"] + " " + p["ip"] for p in app.peers]
print("peers: %r, sweep finished in %.1fs, left=%r" % (names, time.time() - start, app.sweep_left))
ok = (u"Android Test 127.0.0.5" in names) and app.sweep_left == 0
print(ok and "PASS sweep" or "FAIL sweep")
sys.exit(not ok)
