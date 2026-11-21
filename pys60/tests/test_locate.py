# The UDP halving search: a LocalSend device that registers with an unknown
# address (PyS60 reports 0.8.0.0) is found by announcing to half of the
# remaining addresses each round and watching whether it answers.
import os, sys, time, json, threading, tempfile, BaseHTTPServer, SocketServer
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "fake_s60")); sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))
import retrosend, pcnet
os.chdir(tempfile.mkdtemp())  # keep retrosend.cfg out of the repo

TARGET = "127.0.0.23"
class H(BaseHTTPServer.BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length", 0)))
        body = json.dumps({"alias": "Solid Blueberry", "fingerprint": "andfp", "deviceModel": "Pixel"})
        self.send_response(200); self.send_header("Content-Length", str(len(body))); self.end_headers()
        self.wfile.write(body)
class S(SocketServer.ThreadingMixIn, BaseHTTPServer.HTTPServer): daemon_threads = True
httpd = S((TARGET, 53317), H)
t = threading.Thread(target=httpd.serve_forever); t.setDaemon(True); t.start()

retrosend.valid_ip = lambda ip: ip != "0.8.0.0"
NET = pcnet.SelectNet()
lt = threading.Thread(target=NET.run); lt.setDaemon(True); lt.start()
app = retrosend.App()
app.net = NET
app.ip = "127.0.0.1"
app.loc_wait = 0.3
bogus = {"alias": u"Solid Blueberry", "ip": "0.8.0.0", "port": 53317, "fingerprint": u"andfp",
         "deviceModel": None, "protocol": u"http"}
sent = {"n": 0}
def udp_send(host, port, data):
    sent["n"] += 1
    if host == TARGET:  # the "phone" answers the announce by registering (bad address)
        NET.later(0.05, lambda: app.peer(dict(bogus)))
NET.udp_send = udp_send

start = time.time()
NET.call(lambda: app.peer(dict(bogus)))  # it registered with us first
while time.time() - start < 20:
    time.sleep(0.2)
    if [p for p in app.peers if p["ip"] == TARGET]:
        break
took = time.time() - start
found = [p["alias"] + " " + p["ip"] for p in app.peers]
print("found %r in %.1fs, %d UDP packets, %d rounds" % (found, took, sent["n"], (app.loc or {}).get("round", 0)))
ok = found == [u"Solid Blueberry " + TARGET] and app.loc is None
print(ok and "PASS locate" or "FAIL locate")
print(ok and "ALL PASSED" or "FAILED")
sys.stdout.flush(); os._exit(not ok)
