#!/usr/bin/env python3
"""conv.py : donnees du jeu HEROS SNES -> out/ (banques, tables, layout.inc)"""
import sys, os, json, re, struct, collections
import numpy as np
from PIL import Image
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import textconv as TC
from fontk import G6, glyph8
HERE = os.path.dirname(os.path.abspath(__file__)); OUT = os.path.join(HERE, 'out'); os.makedirs(OUT, exist_ok=True)
ROOT = os.path.dirname(HERE); DATA = os.path.join(ROOT, 'data')
IMG = os.path.join(ROOT, '..', 'jeu', 'img')       # decor0..38.png, icons.png (depot amiga_heros)
D = json.load(open(os.path.join(DATA, 'data.json')))
SC = D['logic']['scenes']; VIS = D['vis']; RT = D['logic']['routines']; LAB = D['lab']
NS = len(SC)                       # 212
NSC = NS + 4                       # + pages d'intro TIN1..4
def bgr15(c): return ((c[2] >> 3) << 10) | ((c[1] >> 3) << 5) | (c[0] >> 3)
def hexc(h): return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))

# ------------------------------------------------------------------ musique : scene -> commande
AMB = os.path.join(DATA, 'ambiances_par_scene.txt')
cmd = [0] * NSC
for ln in open(AMB, encoding='utf-8'):
    m = re.match(r'seq_(\d\d)\.mod .*<-.*?:\s*(.*)$', ln.strip())
    if not m: continue
    seq = int(m.group(1))
    for nm, num in re.findall(r'(\w+)\((-?\d+)\)', m.group(2)):
        idx = int(num) + 1
        assert LAB[idx].split('#')[0] == nm, (nm, num, LAB[idx])
        cmd[idx] = seq + 1
for i in range(NS): assert cmd[i], LAB[i]
for i in range(NS, NSC): cmd[i] = 2

# ------------------------------------------------------------------ routines -> bytecode
ridx = {}; rblob = bytearray(); roffs = []
def enc_cond(c):
    c = c.strip()
    if c == 'toujours': return b''
    m = re.fullmatch(r'Flags([WL]) bit (\d+) (actif|inactif)', c)
    if m:
        t = (0 if m.group(1) == 'W' else 2) + (0 if m.group(3) == 'actif' else 1)
        return bytes([t, int(m.group(2))])
    m = re.fullmatch(r'\(FlagsW & (0x[0-9a-fA-F]+)\) (==|!=) (\d+)', c)
    if m:
        mk = int(m.group(1), 16); k = int(m.group(3))
        return bytes([4 if m.group(2) == '==' else 5, mk & 255, mk >> 8, k & 255, k >> 8])
    raise Exception(c)
def enc_eff(e):
    e = e.strip()
    m = re.fullmatch(r'(ACTIVE|EFFACE|BASCULE) Flags([WL]) bit (\d+)', e)
    if m:
        t = {'ACTIVE': 0, 'EFFACE': 1, 'BASCULE': 2}[m.group(1)] + (0 if m.group(2) == 'W' else 3)
        return bytes([t, int(m.group(3))])
    m = re.fullmatch(r'Compteur (-=|:=) (\d+)', e)
    if m: return bytes([7 if m.group(1) == '-=' else 6, int(m.group(2))])
    m = re.fullmatch(r'(Vie|FlagsW|FlagsL) := (\d+)', e)
    if m:
        v = int(m.group(2))
        if m.group(1) == 'Vie': return bytes([8, v])
        if m.group(1) == 'FlagsW': return bytes([9, v & 255, v >> 8])
        return bytes([10]) + struct.pack('<I', v)
    return b''           # sans effet (aucun effet, drapeaux internes, redessin)
used = []
for s in SC:
    for l in s['liens']:
        if l and l[0] == '@' and l[1] not in used: used.append(l[1])
for k in RT:
    if k not in used: used.append(k)
for k in used:
    ridx[k] = len(roffs); roffs.append(len(rblob))
    for cond, eff, dest in RT[k]:
        cb = b''.join(enc_cond(c) for c in cond.split(' ET '))
        eb = b''.join(enc_eff(e) for e in eff.split(', '))
        dv = 0xFFFF if dest == 'RESTER' else 0xFFFE if dest == '(aucune)' else int(dest)
        rblob += bytes([len(cb)]) + cb + bytes([len(eb)]) + eb + struct.pack('<H', dv)
    rblob += b'\xff'
NR = len(roffs)

# ------------------------------------------------------------------ table des scenes
scene_tab = bytearray(); pal_tab = bytearray()
for i in range(NSC):
    if i < NS:
        s = SC[i]; v = VIS[i]; vie = s['vie']; links = s['liens']
    else:
        s = None; v = VIS[1]; vie = 0; links = [None] * 5
    rec = bytearray([vie & 255, v['d'], cmd[i], 0])
    for l in links:
        if l is None: w = 0xFFFF
        elif l[0] == 'R': w = l[1]
        else: w = 0x8000 | ridx[l[1]]
        rec += struct.pack('<H', w)
    rec += bytes(2)
    scene_tab += rec
    pal_tab += struct.pack('<4H', bgr15(hexc(v['n'])), bgr15(hexc(v['a'])), bgr15(hexc(v['f'])), bgr15(hexc(v['b'])))
assert len(scene_tab) == NSC * 16

# ------------------------------------------------------------------ textes : tuiles + blobs
pool = {}; pool_list = []
def tid(t):
    b = TC.enc2bpp(t)
    if b not in pool: pool[b] = len(pool_list); pool_list.append(b)
    return pool[b]
blobs = {}
def build_block(name, lines, lang):
    rows = TC.layout(name, lines, lang)
    img, choix, nrows = TC.render(rows)
    T = TC.tiles_of(img); nty = T.shape[0]
    assert nty <= 64, (name, nty)
    local = {}; ids = []; cells = []
    for ty in range(nty):
        for tx in range(32):
            t = T[ty][tx]
            if not t.any(): cells.append(None); continue
            g = tid(t)
            if g not in local: local[g] = len(local) + 1; ids.append(g)
            cells.append(local[g])
    assert len(ids) <= 1022, (name, len(ids))
    words = []; run = 0
    for c in cells:
        if c is None: run += 1
        else:
            if run: words.append(0x8000 | run); run = 0
            words.append(0x2000 | c)
    if run: words.append(0x8000 | run)
    H = (nrows) * TC.PITCH + 2 + TC.TOP
    smax = max(0, H - TC.VIEW)
    hdr = struct.pack('<HHBB', len(ids), smax, nty, 0)
    for k in range(1, 6):
        if k in choix: hdr += struct.pack('<HH', choix[k][0], choix[k][1])
        else: hdr += struct.pack('<HH', 0xFFFF, 0)
    return hdr + b''.join(struct.pack('<H', g) for g in ids) + b''.join(struct.pack('<H', w) for w in words)
nm_of = [LAB[i].split('#')[0] for i in range(NS)] + ['TIN1', 'TIN2', 'TIN3', 'TIN4']
text_ptr = {}
for lang in ('fr', 'en'):
    bl, _ = TC.HT.lire_dataheros(open(os.path.join(ROOT, '..', 'amiga', 'DataHeros-' + lang), 'rb').read())
    B = {b['nom']: b for b in bl}
    cache = {}
    for i, nm in enumerate(nm_of):
        if nm not in cache:
            cache[nm] = build_block(nm, B[nm]['lignes'], lang)
        blobs[(lang, i)] = cache[nm]
print('tuiles uniques', len(pool_list), '-> %d Ko' % (len(pool_list) * 16 // 1024), ' blobs texte (uniques) %d Ko' % (sum(len(v) for v in {id(x): x for x in blobs.values()}.values()) // 1024))

# ------------------------------------------------------------------ decors (4bpp 256x64) + cartes
decor_blobs = []
for d in range(39):
    src = Image.open(os.path.join(IMG, 'decor%d.png' % d)).convert('RGB').crop((0, 0, 608, 152)).resize((256, 64), Image.LANCZOS)
    q = src.quantize(colors=15, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.FLOYDSTEINBERG)
    pal = q.getpalette()[:45]; px = np.array(q, np.uint8) + 1
    cols = [(pal[3 * i], pal[3 * i + 1], pal[3 * i + 2]) for i in range(15)]
    pb = struct.pack('<H', 0) + b''.join(struct.pack('<H', bgr15(c)) for c in cols)
    pb += bytes(32 - len(pb))
    tb = bytearray()
    for ty in range(8):
        for tx in range(32):
            blk = px[ty * 8:ty * 8 + 8, tx * 8:tx * 8 + 8]
            t0 = bytearray(); t1 = bytearray()
            for y in range(8):
                b = [0, 0, 0, 0]
                for x in range(8):
                    v = int(blk[y][x])
                    for k in range(4): b[k] |= ((v >> k) & 1) << (7 - x)
                t0 += bytes([b[0], b[1]]); t1 += bytes([b[2], b[3]])
            tb += t0 + t1
    decor_blobs.append(bytes(tb) + pb)
bg1map = bytearray()
for r in range(32):
    b = r % 16; fl = b >= 8; tr = 15 - b if fl else b
    for c in range(32):
        bg1map += struct.pack('<H', (tr * 32 + c) | (4 << 10) | (0x8000 if fl else 0))

# ------------------------------------------------------------------ titre (reprend le POC)
src = Image.open(os.path.join(DATA, 'titre.png')).convert('RGB')
tpal = sorted([c for _, c in src.getcolors()], key=lambda c: sum(c))
pimg = Image.new('P', (1, 1)); flat = []
for c in tpal: flat += list(c)
pimg.putpalette(flat + [0] * (768 - len(flat)))
q = src.resize((256, 192), Image.LANCZOS).quantize(palette=pimg, dither=Image.Dither.FLOYDSTEINBERG)
tpx = list(q.getdata()); ttiles = bytearray()
for ty in range(24):
    for tx in range(32):
        rows = [[tpx[(ty * 8 + y) * 256 + tx * 8 + x] for x in range(8)] for y in range(8)]
        t0 = bytearray(); t1 = bytearray()
        for y in range(8):
            b = [0, 0, 0, 0]
            for x in range(8):
                v = rows[y][x]
                for k in range(4): b[k] |= ((v >> k) & 1) << (7 - x)
            t0 += bytes([b[0], b[1]]); t1 += bytes([b[2], b[3]])
        ttiles += t0 + t1
ttiles += bytes(32)
tmap = bytearray()
for ty in range(32):
    for tx in range(32):
        tmap += struct.pack('<H', (ty * 32 + tx if ty < 24 else 768) | (4 << 10))
tpalb = b''.join(struct.pack('<H', bgr15(c)) for c in tpal) + bytes(32 - 2 * len(tpal))
title_blob = bytes(ttiles) + bytes(tmap) + tpalb      # 24608 + 2048 + 32

# ------------------------------------------------------------------ sprites
sheet = np.zeros((56, 128), np.uint8)
ic = Image.open(os.path.join(IMG, 'icons.png')).convert('RGBA')
cols = sorted({p for p in ic.getdata() if p[3] > 0}); assert len(cols) <= 15
icpal = [(0, 0, 0)] + [c[:3] for c in cols]
def inkrows(f):
    return [y for y in range(17) if any(ic.getpixel((f * 16 + x, y))[3] for x in range(16))]
for b in range(16):
    f = b + 1; rr = inkrows(f); y0 = 1 if (rr and rr[0] >= 1 and 16 not in rr) else 0
    if rr and 16 in rr and 0 not in rr: y0 = 1
    ox = (b % 8) * 16; oy = (b // 8) * 16
    for y in range(16):
        for x in range(16):
            p = ic.getpixel((f * 16 + x, y0 + y))
            if p[3] > 0: sheet[oy + y, ox + x] = icpal.index(p[:3])
SP1 = [(0, 0, 0), (0, 0, 0), (255, 255, 255), (205, 35, 35), (245, 215, 40), (55, 100, 240), (45, 175, 65), (165, 165, 165),
       (225, 30, 65), (255, 160, 170), (255, 215, 0), (165, 115, 0)]
def glyph_bits(ch):
    return [[(row >> (7 - x)) & 1 for x in range(8)] for row in glyph8(ch)]
for k, (ch, colr) in enumerate((('A', 3), ('B', 4), ('X', 5), ('Y', 6), ('R', 7))):
    ox = 64 + k * 16 - 64 + 0; oy = 32          # lignes 4-5 de tuiles : y=32..47
    ox = k * 16
    for y in range(16):
        for x in range(16):
            dx = x - 7.5; dy = y - 7.5; r = (dx * dx + dy * dy) ** .5
            if r <= 6.9: sheet[oy + y, ox + x] = 1 if r > 5.6 else colr
    g = glyph_bits(ch)
    for y in range(8):
        for x in range(8):
            if g[y][x]: sheet[oy + 4 + y, ox + 4 + x - 1 + 0] = 2
for dgt in range(10):
    g = glyph_bits(str(dgt)); ox = dgt * 8; oy = 48
    for y in range(8):
        for x in range(8):
            if g[y][x]:
                if y + 1 < 8 and x + 1 < 8 and not sheet[oy + y + 1, ox + x + 1]: sheet[oy + y + 1, ox + x + 1] = 1
    for y in range(8):
        for x in range(8):
            if g[y][x]: sheet[oy + y, ox + x] = 2
HEART = ["........", ".##.##..", "#@@#@@#.", "#@@@@@#.", ".#@@@#..", "..#@#...", "...#....", "........"]
COIN = ["..####..", ".#AAAA#.", "#ABBBBA#", "#ABAABA#", "#ABAABA#", "#ABBBBA#", ".#AAAA#.", "..####.."]
for j, (pat, mp) in enumerate(((HEART, {'#': 8, '@': 9}), (COIN, {'#': 11, 'A': 10, 'B': 10}))):
    ox = (10 + j) * 8; oy = 48
    for y in range(8):
        for x in range(8):
            ch = pat[y][x]
            if ch in mp: sheet[oy + y, ox + x] = mp[ch]
# fleches de defilement : tuile 108 (bas), 109 (haut)
DOWN = ["#######.", ".#####..", "..###...", "...#....", "........", "........", "........", "........"]
for j, pat in enumerate((DOWN, DOWN[3::-1] + ["........"] * 4)):
    ox = (12 + j) * 8; oy = 48
    pts = [(x, y) for y in range(8) for x in range(8) if pat[y][x] == '#']
    for (x, y) in pts:
        if x + 1 < 8 and y + 1 < 8: sheet[oy + y + 1, ox + x + 1] = 1
    for (x, y) in pts: sheet[oy + y, ox + x] = 2
# '+' (plus) : tuile 108
for (x, y) in ((3, 2), (3, 3), (3, 4), (2, 3), (4, 3), (1, 3), (5, 3), (3, 5), (3, 1)):
    pass
spr = bytearray()
for ty in range(7):
    for tx in range(16):
        blk = sheet[ty * 8:ty * 8 + 8, tx * 8:tx * 8 + 8]
        t0 = bytearray(); t1 = bytearray()
        for y in range(8):
            b = [0, 0, 0, 0]
            for x in range(8):
                v = int(blk[y][x])
                for k in range(4): b[k] |= ((v >> k) & 1) << (7 - x)
            t0 += bytes([b[0], b[1]]); t1 += bytes([b[2], b[3]])
        spr += t0 + t1
sprpal = b''.join(struct.pack('<H', bgr15(c)) for c in icpal) + bytes(32 - 2 * len(icpal))
sprpal += b''.join(struct.pack('<H', bgr15(c)) for c in SP1) + bytes(32 - 2 * len(SP1))
spr_blob = bytes(spr) + sprpal                         # 3584 + 64
dbg = Image.fromarray(sheet * 17); dbg.resize((512, 224), Image.NEAREST).save(os.path.join(HERE, 'prev_sprites.png'))

# ------------------------------------------------------------------ police 8x8 (menus) + chaines
ACC8 = 'àâçèéêîïôùû'
def code8(ch):
    if ' ' <= ch <= '~': return ord(ch) - 32
    if ch in ACC8: return 95 + ACC8.index(ch)
    return 0
fnt = bytearray()
for acc in (0, 1):
    for c in range(128):
        ch = chr(c + 32) if c < 95 else ACC8[c - 95] if c - 95 < len(ACC8) else ' '
        g = glyph8(ch) if c < 95 + len(ACC8) else [0] * 8
        for y in range(8): fnt += bytes([0, g[y]]) if acc else bytes([g[y], 0])
def enc8(s): return bytes(code8(c) for c in s) + b'\xff'
STR = {'fr': ['START  Nouvelle partie', 'L Charger   SELECT English', 'MENU', 'Reprendre', 'Sauver', 'Charger', 'Vie au maximum',
              'Langue : Français', 'Retour au titre', 'vide', 'Sauvegardé !', 'Chargé !', 'Aucune sauvegarde', 'Vie au maximum !', 'HEROS  -  version SNES'],
       'en': ['START  New game', 'L Load      SELECT Français', 'MENU', 'Resume', 'Save', 'Load', 'Maximum life',
              'Language: English', 'Back to title', 'empty', 'Saved!', 'Loaded!', 'No save', 'Maximum life!', 'HEROS  -  SNES version']}
NSTR = len(STR['fr'])
scname = b''.join((enc8(LAB[i].split('#')[0])[:-1] + bytes(code8(' ') for _ in range(4)))[:4] for i in range(NS)) + b''.join(enc8(n)[:-1] for n in ('TIN1', 'TIN2', 'TIN3', 'TIN4'))

# ------------------------------------------------------------------ emission : banques
banks = {}      # numero -> bytearray
NEXT = [3]
def new_bank():
    b = NEXT[0]; NEXT[0] += 1; banks[b] = bytearray(); return b
def alloc(data, align=1):
    assert len(data) <= 0x8000
    for b in banks:
        o = (len(banks[b]) + align - 1) // align * align
        if o + len(data) <= 0x8000 and b not in POOLB:
            banks[b] += bytes(o - len(banks[b])) + data; return b, 0x8000 + o
    b = new_bank(); banks[b] += data; return b, 0x8000
POOLB = set()
# pool de tuiles : banques consecutives, 2048 tuiles chacune
POOL0 = NEXT[0]
nb = (len(pool_list) + 2047) // 2048
for i in range(nb):
    b = new_bank(); POOLB.add(b)
    banks[b] += b''.join(pool_list[i * 2048:(i + 1) * 2048])
defs = {'POOL0': POOL0}
# gros blocs d'abord
items = []
for (lang, i), blob in blobs.items(): items.append(('txt', lang, i, blob))
items.sort(key=lambda t: -len(t[3]))
placed = {}
txt_addr = {}
for kind, lang, i, blob in items:
    key = (lang, id(blob))
    if key not in placed: placed[key] = alloc(blob)
    txt_addr[(lang, i)] = placed[key]
dec_addr = [alloc(b) for b in decor_blobs]
ttl_addr = alloc(title_blob)
spr_addr = alloc(spr_blob)
fnt_addr = alloc(bytes(fnt))
nbanks_total = NEXT[0]
# tables en banque 0
tab = bytearray(); T0 = 0xC000
def add(name, data):
    global tab
    defs[name] = T0 + len(tab); tab += data
    return defs[name]
add('T_SCENE', bytes(scene_tab)); add('T_PAL', bytes(pal_tab))
for lang, nm in (('fr', 'T_TXTFR'), ('en', 'T_TXTEN')):
    t = b''.join(struct.pack('<HBB', txt_addr[(lang, i)][1], txt_addr[(lang, i)][0], 0) for i in range(NSC)); add(nm, t)
add('T_DECOR', b''.join(struct.pack('<HBB', a, b, 0) for b, a in dec_addr))
rb_base = T0 + len(tab) + NR * 2
add('T_ROUT', b''.join(struct.pack('<H', rb_base + o) for o in roffs)); add('T_ROUTB', bytes(rblob))
add('T_SCNAME', scname)
for lang, nm in (('fr', 'T_STRFR'), ('en', 'T_STREN')):
    base = T0 + len(tab) + NSTR * 2; blob = b''; offs = []
    for s in STR[lang]: offs.append(base + len(blob)); blob += enc8(s)
    add(nm, b''.join(struct.pack('<H', o) for o in offs) + blob)
add('T_BG1MAP', bytes(bg1map))
assert len(tab) <= 0x4000, len(tab)
open(os.path.join(OUT, 'tab0.bin'), 'wb').write(tab)
def bk(name, ba):
    defs[name + '_B'] = ba[0]; defs[name + '_A'] = ba[1]
bk('TITLE', ttl_addr); bk('SPR', spr_addr); bk('FNT', fnt_addr)
defs['NSC'] = NSC; defs['NS'] = NS; defs['NSTR'] = NSTR
defs['TC1'] = 1
for b, data in banks.items(): open(os.path.join(OUT, 'bank%02d.bin' % b), 'wb').write(bytes(data) + bytes(0x8000 - len(data)))
rom_banks = 64 if nbanks_total <= 64 else 128
with open(os.path.join(OUT, 'layout.inc'), 'w') as f:
    for k, v in defs.items(): f.write('.define %s %d\n' % (k, v))
    f.write('.define ROMBANKS %d\n' % rom_banks)
with open(os.path.join(OUT, 'banks.inc'), 'w') as f:
    for b in sorted(banks): f.write('.BANK %d SLOT 0\n.ORG 0\n.incbin "out/bank%02d.bin"\n' % (b, b))
json.dump({'ridx': ridx, 'cmd': cmd, 'nbanks': nbanks_total, 'NR': NR}, open(os.path.join(OUT, 'meta.json'), 'w'))
print('banques utilisees', nbanks_total, 'tables %d o' % len(tab), 'routines', NR, len(rblob), 'o', 'ROM', rom_banks * 32, 'Ko')
