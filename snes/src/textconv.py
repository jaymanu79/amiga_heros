# Mise en page + rendu des textes de HEROS en tuiles 2bpp (police 6x10, 42 colonnes, interligne 10)
import re, sys, os
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import heros_texte as HT
from fontk import G6

CELLS = 42; MARG = 2; PITCH = 10; VIEW = 160; TOP = 8

def parse_cells(by, acc):
    """octets (avec codes @0 @1 @2) -> liste de (car, accent) ; l'etat d'accent se transmet d'une ligne a l'autre"""
    out = []; s = by.decode('latin-1'); i = 0
    while i < len(s):
        if s[i] == '@' and i + 1 < len(s) and s[i + 1].isdigit():
            acc = s[i + 1] != '1'; i += 2; continue
        out.append((s[i], acc)); i += 1
    return out, acc

def plain(cells): return ''.join(c for c, a in cells)

def squeeze(cells, need):
    """supprime les suites d'espaces interieurs (garde 1) tant que la ligne depasse"""
    out = []; prev_sp = False; seen = False
    for c, a in cells:
        if c == ' ':
            if seen and prev_sp: continue
            prev_sp = True
        else:
            seen = True; prev_sp = False
        out.append((c, a))
    return out

def wrap(cells, width, hang=0):
    words = []; cur = []
    for c in cells:
        if c[0] == ' ':
            if cur: words.append(cur); cur = []
        else: cur.append(c)
    if cur: words.append(cur)
    lines = []; line = []
    for w in words:
        ll = len(line) + (1 if line else 0) + len(w)
        if line and ll > width - (hang if lines else 0):
            lines.append(line); line = list(w)
        else:
            line = line + ([(' ', w[0][1])] if line else []) + list(w)
    if line: lines.append(line)
    return [([(' ', 0)] * (hang if i else 0)) + l for i, l in enumerate(lines)]

def strip(cells):
    a = 0; b = len(cells)
    while a < b and cells[a][0] == ' ': a += 1
    while b > a and cells[b - 1][0] == ' ': b -= 1
    return cells[a:b]

SNES_RULES = {
 'fr': ["HEROS est un jeu d'aventure accessible à tout le monde.",
        "Lisez le texte qui vous est proposé, en le faisant défiler avec la croix directionnelle (haut / bas).",
        "A l'issue de la lecture, vous devrez prendre une décision en pressant le bouton de couleur indiqué devant le choix : A rouge, B jaune, X bleu, Y vert, R gris.",
        "SELECT revient en arrière. START ouvre le menu : sauvegarde, chargement, vie au maximum.",
        "Vous devrez surtout préserver votre capital de vie, en évitant les nombreux pièges."],
 'en': ["HEROS is an adventure game accessible to everyone.",
        "Read the text you are given, scrolling it with the directional pad (up / down).",
        "When you finish reading, you must make a decision by pressing the coloured button shown beside the choice: A red, B yellow, X blue, Y green, R grey.",
        "SELECT goes back one step. START opens the menu: save, load, maximum life.",
        "Above all you must protect your life points, by avoiding the many traps."]}

def layout(name, lines, lang):
    """-> liste de (rang, xcell, cells). rang = numero de ligne (de 10 px) depuis le haut du bloc."""
    acc = False; L = []
    for col, lig, by in lines:
        cells, acc = parse_cells(by, acc); L.append((col, lig, cells))
    out = []
    if name == 'TIN3':
        # texte adapté à la manette
        L = [(9, 1, parse_cells(b'     R E G L E' if lang == 'fr' else b'    R U L E S', False)[0]),
             (9, 2, [('\xad', False)] * 19)] + L[:0]
        rows = []; r = 0
        title = 'R E G L E S' if lang == 'fr' else 'R U L E S'
        t = [(c, False) for c in title]
        rows.append(((CELLS - len(t)) // 2, 0, t)); rows.append(((CELLS - 19) // 2, 1, [('\xad', False)] * 19)); r = 3
        for p in SNES_RULES[lang]:
            for l in wrap([(c, False) for c in p], CELLS):
                rows.append((0, r, l)); r += 1
            r += 1
        return [(rg, x, c) for x, rg, c in rows]
    if name in ('TIN1', 'TIN2', 'TIN4', 'TM81'):
        base = min(c for c, l, ce in L if plain(ce).strip())
        first = min(l for c, l, ce in L)
        rows = []; i = 0
        # regroupe en paragraphes : lignes consécutives de même colonne
        groups = []
        for c, l, ce in L:
            if groups and groups[-1][-1][1] == l - 1 and groups[-1][-1][0] == c and plain(ce).strip() and plain(groups[-1][-1][2]).strip():
                groups[-1].append((c, l, ce))
            else: groups.append([(c, l, ce)])
        r = 0; prev_l = None
        for g in groups:
            c0, l0, _ = g[0]
            if prev_l is not None: r += l0 - prev_l - 1 if l0 - prev_l - 1 > 0 else 0
            ov = any((c - base) + len(plain(ce)) > CELLS for c, l, ce in g)
            if name == 'TIN4' and plain(g[0][2]).startswith(('Pour me contacter', 'To contact me')):
                pass
            if ov and len(g) > 1 and all(plain(ce).strip() and '\xad' not in plain(ce) and not plain(ce).startswith('---') for c, l, ce in g):
                cells = []
                for c, l, ce in g: cells += squeeze(ce, 0) + [(' ', 0)]
                for ln in wrap(cells, CELLS - (c0 - base)):
                    rows.append((r, c0 - base, ln)); r += 1
            else:
                for c, l, ce in g:
                    x = c - base
                    if len(strip(ce)) > CELLS - 2 and name != 'TIN2' and '\xad' not in plain(ce):
                        for ln in wrap(squeeze(strip(ce), 0), CELLS):
                            rows.append((r, (CELLS - len(ln)) // 2, ln)); r += 1
                        continue
                    if (c >= 17 and name in ('TIN1', 'TIN2', 'TIN4')) and (c > 17 or len(plain(ce).strip()) < 40) and name != 'TIN2':
                        s = strip(ce); x = (CELLS - len(s)) // 2; ce = s
                    elif x + len(ce) > CELLS:
                        ce = squeeze(ce, 0)
                        if x + len(ce) > CELLS:
                            lead = 0
                            while lead < len(ce) and ce[lead][0] == ' ': lead += 1
                            cut = min(lead, x + len(ce) - CELLS); ce = ce[cut:]
                            if x + len(ce) > CELLS: ce = ce[:CELLS - x]
                    rows.append((r, x, ce)); r += 1
            prev_l = g[-1][1]
        if name == 'TM81':
            pass
        return [(rg, x, c) for rg, x, c in rows]
    first = min(l for c, l, ce in L)
    return [(l - first, c - 18, ce) for c, l, ce in L]

CH_RE = re.compile(r'^(\s*)< ?F(\d) ?>')

def render(rows):
    """rows -> (image uint8 [H][256], choix {k:(y,x)}) ; le marqueur '< Fk >' est remplacé par 6 espaces"""
    nrows = max(r for r, x, c in rows) + 1
    H = nrows * PITCH + 4 + TOP
    H = (H + 7) // 8 * 8
    img = np.zeros((H, 256), np.uint8); choix = {}
    for r, x, cells in rows:
        txt = plain(cells)
        m = CH_RE.match(txt)
        cells = list(cells)
        if m:
            k = int(m.group(2)); s = m.end(1); e = m.end()
            cells[s:e] = [(' ', 0)] * (e - s)
            choix[k] = (r * PITCH + TOP, MARG + (x + s) * 6)
        y0 = r * PITCH + TOP
        for i, (ch, ac) in enumerate(cells):
            if ch == ' ': continue
            g = G6.get(ch)
            if g is None: g = G6['?']
            px = MARG + (x + i) * 6
            assert 0 <= px and px + 6 <= 256, (rows[0:2], x, i, txt)
            for yy in range(10):
                v = g[yy]
                if not v: continue
                for xx in range(6):
                    if v >> (5 - xx) & 1: img[y0 + yy, px + xx] = 2 if ac else 1
    return img, choix, nrows

def tiles_of(img):
    H = img.shape[0]; T = img.reshape(H // 8, 8, 32, 8).transpose(0, 2, 1, 3)   # [ty][tx][8][8]
    return T

def enc2bpp(t):
    out = bytearray()
    for y in range(8):
        p0 = p1 = 0
        for x in range(8):
            v = int(t[y][x]); p0 |= (v & 1) << (7 - x); p1 |= ((v >> 1) & 1) << (7 - x)
        out += bytes([p0, p1])
    return bytes(out)
