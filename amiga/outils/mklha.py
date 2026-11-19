#!/usr/bin/env python3
"""Fabrique HEROS.lha (installation sur disque dur) : archive LHA niveau 0, methode -lh0- (sans compression,
lisible par tous les LHA, y compris sur Amiga 1.3).  Usage : mklha.py sortie.lha dossier_source"""
import os, struct, sys, time

def crc16(data, crc=0):
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return crc

def dostime(t):
    lt = time.localtime(t)
    return ((lt.tm_year - 1980) << 25) | (lt.tm_mon << 21) | (lt.tm_mday << 16) | (lt.tm_hour << 11) | (lt.tm_min << 5) | (lt.tm_sec // 2)

def entry(name, data, t):
    nm = name.encode('latin-1')            # noms Amiga : ISO-8859-1
    body = b'-lh0-' + struct.pack('<II', len(data), len(data)) + struct.pack('<I', dostime(t)) + bytes([0x20, 0]) \
         + bytes([len(nm)]) + nm + struct.pack('<H', crc16(data))
    chk = sum(body) & 0xFF
    return bytes([len(body), chk]) + body + data

def build(out, src):
    items = []
    for root, dirs, files in os.walk(src):
        dirs.sort()
        for f in sorted(files):
            p = os.path.join(root, f)
            items.append((os.path.relpath(p, src).replace(os.sep, '/'), p))
    with open(out, 'wb') as o:
        for name, p in items:
            o.write(entry(name, open(p, 'rb').read(), 1778592000))   # date fixe : build reproductible
        o.write(b'\0')
    return [n for n, _ in items]

if __name__ == '__main__':
    for n in build(sys.argv[1], sys.argv[2]): print(n)
