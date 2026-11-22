#!/bin/sh
# Builds retrosend_rscfix.exe (GCCE, release) into out/. Needs the Symbian
# toolchain next to the repository: see RetroTorch's tools/symbian-sdk/setup.sh
# (github.com/manojanasuri16/RetroTorch).
set -e
cd "$(dirname "$0")"
SDK=$(cd ../../symbian-sdk && pwd)
export EPOCROOT=$SDK/s60_32/
export PATH=$SDK/gnupoc-bin:$SDK/csl-gcc/bin:$PATH
cd group
bldmake bldfiles
abld build gcce urel
cd ..
mkdir -p out
cp "$EPOCROOT/epoc32/release/gcce/urel/retrosend_rscfix.exe" out/
ls -la out
