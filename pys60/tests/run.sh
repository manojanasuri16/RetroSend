#!/bin/sh
# Checks retrosend.py for Python 2.2 compatibility, then runs the protocol tests with Python 2.7.
set -e
cd "$(dirname "$0")/.."
PY2=../tools/mamba/py27/bin/python2
python3 tools/check_py22.py retrosend.py
python3 tools/check_py22.py media.py
$PY2 tests/test_pys60.py
"$PY2" tests/test_sweep.py
"$PY2" tests/test_media.py
"$PY2" tests/test_picker.py
"$PY2" -u tests/test_cancel.py
python3 tools/check_py22.py grid.py
"$PY2" tests/test_grid.py
python3 tools/check_py22.py webshare.py
"$PY2" -u tests/test_webshare.py
"$PY2" tests/test_app.py
"$PY2" -u tests/test_web_routing.py
