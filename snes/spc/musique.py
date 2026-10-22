#!/usr/bin/env python3
"""musique.py : convertit la musique de HEROS (heros_tout.mod + ambiances_par_scene.txt)
en donnees pour le SPC700 : echantillons BRR, directory, patterns compacts, listes d'ordre.
Sortie : spcdata.bin (a charger a l'adresse DATA0), consts.inc (adresses pour le pilote), musique.json."""
import struct, re, sys, json, os

MOD, AMB, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
SCALE = 0.8             # amplitude des echantillons (compensee par MVOL dans le pilote)
DATA0 = 0x0800          # adresse SPC de debut des donnees
d = open(MOD, 'rb').read()
NB_ECH, NB_PAT = 15, 30
ents = [struct.unpack('>HBBHH', d[20+30*i+22:20+30*i+30]) for i in range(NB_ECH)]
PATDATA = 1084
smp, p = [], PATDATA + 1024 * NB_PAT
for ln, ft, vol, ls, ll in ents:
    smp.append(d[p:p+2*ln]); p += 2*ln

# ---------------- BRR ----------------
def clamp16(x): return -32768 if x < -32768 else 32767 if x > 32767 else x
def wrap15(x):
    x = clamp16(x)
    return ((x * 2 + 32768) & 0xFFFF) - 32768 >> 1
def predict(f, p1, p2):
    """Prediction du decodeur materiel (formules exactes de SPC_DSP.cpp). p1, p2 : 2 echantillons precedents
    (domaine 15 bits). En interne le DSP memorise 2*echantillon : p1h = 2*p1, p2h = p2."""
    if f == 0: return 0
    p1h = p1 * 2
    if f == 1: return (p1h >> 1) + ((-p1h) >> 5)
    if f == 2: return p1h - p2 + (p2 >> 4) + ((p1h * -3) >> 6)
    return p1h - p2 + ((p1h * -13) >> 7) + ((p2 * 3) >> 4)

def enc_block(t, p1, p2, f, r):
    out, err, nib = [], 0, []
    for x in t:
        pr = predict(f, p1, p2)
        best = None
        n0 = round((x - pr) * 2 / (1 << r)) if r else (x - pr) * 2
        for n in (n0 - 1, n0, n0 + 1):
            if n < -8 or n > 7: continue
            u = ((n << r) >> 1) + pr
            if u > 16383 or u < -16384: continue          # debordement 15 bits = repliement
            v = wrap15(u)
            e = (x - v) ** 2
            if best is None or e < best[0]: best = (e, n, v)
        if best is None:                    # aucun candidat valide : ce (filtre, plage) est inutilisable
            return 1e30, [0] * 16, p1, p2
        err += best[0]; nib.append(best[1] & 15); p2, p1 = p1, best[2]
    return err, nib, p1, p2

def brr(pcm8, loop_start_blk, loop, ):
    """pcm8 : liste d'entiers signes 8 bits (longueur multiple de 16)."""
    t = [int(round(v * 128 * SCALE)) for v in pcm8]
    out = bytearray(); p1 = p2 = 0; nb = len(t) // 16
    for b in range(nb):
        blk = t[16*b:16*b+16]
        first = (b == 0 or b == loop_start_blk)
        best = None
        for f in ((0,) if first else (0, 1, 2, 3)):
            for r in range(0, 13):
                e, nib, q1, q2 = enc_block(blk, 0 if first else p1, 0 if first else p2, f, r)
                if best is None or e < best[0]: best = (e, f, r, nib, q1, q2)
        e, f, r, nib, p1, p2 = best
        hdr = (r << 4) | (f << 2) | (2 if loop else 0) | (1 if b == nb - 1 else 0)
        out.append(hdr)
        for i in range(0, 16, 2): out.append((nib[i] << 4) | nib[i+1])
    return bytes(out)

def prep(i):
    ln, ft, vol, ls, ll = ents[i]; ln *= 2; ls *= 2; ll *= 2
    s = list(struct.unpack('%db' % ln, smp[i][:ln]))
    if ll <= 2:                                        # pas de boucle
        pad = (-len(s)) % 16
        return s + [0]*pad, 0, False
    s = s[:ls+ll]
    lead = (-ls) % 16                                  # alignement du debut de boucle
    s = [0]*lead + s; ls += lead
    n = len(s)
    if n % 16:
        tgt = round(n / 16) * 16
        if tgt < ls + 16: tgt = ls + 16
        if tgt <= n: s = s[:tgt]
        else:
            lp = s[ls:]
            while len(s) < tgt: s += lp[:tgt - len(s)]
    return s, ls // 16, True

blobs, info = [], []
for i in range(NB_ECH):
    s, lb, lp = prep(i)
    blobs.append((brr(s, lb, lp), lb, lp))
    info.append(dict(i=i+1, pcm=len(s), brr=len(blobs[-1][0]), loop=lp, loopblk=lb, vol=ents[i][2]))

# ---------------- patterns compacts ----------------
def cell(pi, r, c):
    o = PATDATA + pi*1024 + r*16 + c*4
    b = d[o:o+4]
    return (((b[0] & 15) << 8) | b[1], (b[0] & 0xF0) | (b[2] >> 4), b[2] & 15, b[3])
pats = []
for pi in range(NB_PAT):
    s = bytearray()
    for r in range(64):
        mask, cells = 0, bytearray()
        for c in range(3):
            per, ins, ef, pa = cell(pi, r, c)
            eff = {0: 0, 1: 1, 2: 2, 12: 3}.get(ef, 0)
            if eff == 0: pa = 0
            if not (per or ins or eff): continue
            mask |= 1 << c
            cells.append(ins | (eff << 4) | (0x40 if per else 0))
            if per: cells += struct.pack('<H', per)
            if eff: cells.append(min(pa, 255))
        s.append(mask); s += cells
    pats.append(bytes(s))

# ---------------- ordonnancement ----------------
seqs = []
for ln in open(AMB, encoding='utf-8'):
    m = re.match(r'seq_(\d+)\.mod\s+patterns \[([\d, ]+)\], boucle sur la position (\d+)\s+<- (\d+) sc.nes : (.*)', ln)
    if m:
        seqs.append(dict(n=int(m.group(1)), pats=[int(x) for x in m.group(2).split(',')],
                         loop=int(m.group(3)), nsc=int(m.group(4)),
                         scenes=re.findall(r'([A-Za-z0-9]+)\(-?\d+\)', m.group(5))))
seqs.sort(key=lambda x: x['n'])
assert len(seqs) == 32, len(seqs)

# ---------------- table de hauteurs : periode Amiga -> pitch DSP ----------------
PAL = 3546895.0
ptab = b''.join(struct.pack('<H', min(0x3FFF, round(PAL / per * 4096 / 32000))) for per in range(113, 857))

# ---------------- implantation ----------------
img = bytearray(); addr = DATA0
def place(blob, align=1):
    global addr
    while addr % align: img.append(0); addr += 1
    a = addr; img.extend(blob); addr += len(blob); return a
A = {}
A['PTAB'] = place(ptab)
A['DIR'] = place(b'', 256)
dir_at = len(img)
img.extend(bytes(4*NB_ECH)); addr += 4*NB_ECH
A['INSVOL'] = place(bytes(min(64, e[2]) for e in ents))
ordaddr = []
olists = [bytes(s['pats'] + [0xFF, s['loop']]) for s in seqs]
A['ORDTAB'] = place(b'\0' * (2 * len(seqs)))
ordtab_at = A['ORDTAB'] - DATA0
for ol in olists: ordaddr.append(place(ol))
for k, a in enumerate(ordaddr): img[ordtab_at + 2*k: ordtab_at + 2*k + 2] = struct.pack('<H', a)
A['PATTAB'] = place(b'\0' * (2 * NB_PAT))
pattab_at = A['PATTAB'] - DATA0
for k, pt in enumerate(pats):
    a = place(pt); img[pattab_at + 2*k: pattab_at + 2*k + 2] = struct.pack('<H', a)
A['SAMPLES'] = addr
dirent = b''
for b, lb, lp in blobs:
    a = place(b)
    dirent += struct.pack('<HH', a, a + lb*9 if lp else a)
img[dir_at:dir_at + len(dirent)] = dirent
assert addr <= 0xFFC0, hex(addr)
open(os.path.join(OUT, 'spcdata.bin'), 'wb').write(bytes(img))
with open(os.path.join(OUT, 'consts.inc'), 'w') as f:
    for k, v in A.items(): f.write('.define %s $%04X\n' % (k, v))
    f.write('.define NSONGS %d\n' % len(seqs))
json.dump(dict(addr_fin=addr, taille_samples=sum(len(b) for b, _, _ in blobs), taille_patterns=sum(len(p) for p in pats),
               taille_ptab=len(ptab), info=info, seqs=seqs, A=A), open(os.path.join(OUT, 'musique.json'), 'w'), indent=1)
print('fin des donnees SPC : $%04X (%d octets sur 65536)' % (addr, addr))
print('echantillons BRR', sum(len(b) for b, _, _ in blobs), ' patterns', sum(len(p) for p in pats), ' table hauteurs', len(ptab))
