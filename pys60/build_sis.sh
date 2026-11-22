#!/bin/sh
# Builds the native S60 3rd Edition app from retrosend.py (+ media.py).
#   dist/RetroSend.sis              app only (needs Python for S60 1.4.5 installed);
#                                   installs to phone memory or the memory card,
#                                   wherever Python is (retrosend_rscfix.exe, see
#                                   rscfix/README.md)
#   dist/RetroSend_with_Python.sis  only with MERGE=1 (not recommended, see below)
# Run ../tools/setup.sh once first to download the tools.
set -e
cd "$(dirname "$0")"
PY=../tools/mamba/py27/bin/python2
ENS=../tools/ensymble/src/ensymble.py
RUNTIME=../phone-installs/PythonForS60_1_4_5_3rdEd.sis
# the version lives in retrosend.py (VERSION = u"x.y.z"); bump it for every release
VERSION=$(sed -n 's/^VERSION = u"\([0-9.]*\)".*/\1/p' retrosend.py)
[ -n "$VERSION" ] || { echo "VERSION not found in retrosend.py"; exit 1; }
echo "building RetroSend $VERSION"
mkdir -p build dist cert

# Self-signed certificate, valid 2008-2037 so it also installs when the phone's
# date is set back (Nokia's runtime certificate has expired). Keep the key private.
if [ ! -f cert/retrosend_key.pem ]; then
  openssl req -x509 -newkey rsa:1024 -sha1 -nodes \
    -not_before 20080101000000Z -not_after 20371231000000Z \
    -subj "/CN=RetroSend/O=RetroSend" \
    -keyout cert/retrosend_key.pem -out cert/retrosend_cert.pem
  openssl rsa -in cert/retrosend_key.pem -traditional -out cert/retrosend_key.pem
fi

# One file for the phone: paste media.py, grid.py and webshare.py in place
# of their "#@INLINE name.py" marker and the import line after it.
python3 - <<'PY'
lines = open("retrosend.py").read().split("\n")
out = []
i = 0
while i < len(lines):
    if lines[i].startswith("#@INLINE "):
        name = lines[i].split(" ", 1)[1].strip()
        out.append(open(name).read())
        i = i + 2  # skip the marker and the PC import line
        continue
    out.append(lines[i])
    i = i + 1
text = "\n".join(out)
assert text.find("#@INLINE") < 0
open("build/default.py", "w").write(text)
PY
python3 tools/check_py22.py build/default.py
cp build/default.py dist/retrosend.py   # single-file version for the Script Shell

# The installed app is split into modules: the phone compiles each one
# separately (less memory at start-up than one 130 KB file), and the tiny
# starter shows any loading error on screen. Files go to \private\<uid>\.
rm -rf build/app && mkdir -p build/app
cp launcher.py build/app/default.py
cp retrosend.py build/app/rs_app.py
# every module the app imports (keep in sync with the #@INLINE markers)
for m in $(sed -n 's/^#@INLINE \(.*\.py\)$/\1/p' retrosend.py); do cp "$m" build/app/; done
for f in build/app/*.py; do python3 tools/check_py22.py "$f" >/dev/null; done

# Memory card or phone memory: retrosend_rscfix.exe, run once by the installer,
# puts appuifw's resource file on the app's drive (see rscfix/README.md).
EXTRAS=""
if [ -f ../native/out/retrosend_rscfix.exe ]; then
  mkdir -p build/app/root/sys/bin build/app/root/resource/retrosend
  cp ../native/out/retrosend_rscfix.exe build/app/root/sys/bin/
  cp rscfix/appuifwmodule.rsc build/app/root/resource/retrosend/
  EXTRAS="--extrasdir=root"
  echo "including retrosend_rscfix.exe (any-drive install)"
else
  echo "WARNING: ../native/out/retrosend_rscfix.exe not built (native/build.sh):"
  echo "         the app will only start on the same drive as Python for S60"
fi

$PY tools/py2sis_rscfix.py "$(dirname $ENS)" --uid=0xE7A3D5C1 --appname=RetroSend --version=$VERSION \
  --caption=RetroSend --shortcaption=RetroSend --vendor=RetroSend --icon=icon.svg \
  --caps=NetworkServices+LocalServices+ReadUserData+WriteUserData+UserEnvironment \
  --heapsize=4k,8M --cert=cert/retrosend_cert.pem --privkey=cert/retrosend_key.pem \
  $EXTRAS build/app dist/RetroSend.sis </dev/null >build/py2sis.log
grep "rscfix" build/py2sis.log || true
echo "built dist/RetroSend.sis"

# The combined package is off by default: it registers the Python runtime as
# part of RetroSend, so installing the app-only package over it (or removing
# RetroSend) removes Python too and every Python app stops opening.
if [ "$MERGE" = 1 ] && [ -f "$RUNTIME" ]; then
  $PY $ENS mergesis --cert=cert/retrosend_cert.pem --privkey=cert/retrosend_key.pem \
    dist/RetroSend.sis "$RUNTIME" dist/RetroSend_with_Python.sis </dev/null >build/mergesis.log
  echo "built dist/RetroSend_with_Python.sis"
else
  rm -f dist/RetroSend_with_Python.sis
fi
ls -la dist
