#!/bin/sh
# Construit heros_snes.sfc (ROM LoROM 2 Mo avec SRAM 8 Ko).
# Pre-requis : python3 + Pillow + numpy, WLA-DX (wla-65816, wlalink) dans le PATH, le depot amiga_heros complet
# (le dossier snes/ est a sa racine : on y lit jeu/img/*.png et amiga/DataHeros-*).
set -e
cd "$(dirname "$0")/src"
[ -f ../data/data.json ] || python3 mkdata_json.py
python3 conv.py
wla-65816 -o main.o main.s
printf '[objects]\nmain.o\n' > main.lnk
wlalink -S main.lnk ../heros_snes.sfc
rm -f main.o main.lnk
ls -l ../heros_snes.sfc
