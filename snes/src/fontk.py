# Police 6x10 (koi6x10) + lettres accentuées composées. G6[c] = 10 entiers de 6 bits (x0 = bit 5).
import os
from PIL import ImageFont, Image, ImageDraw
_f = ImageFont.load(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'koi6x10.pil'))
def _base(ch):
    im = Image.new('1', (6, 10), 0); ImageDraw.Draw(im).text((0, 0), ch, font=_f, fill=1)
    return [sum((1 if im.getpixel((x, y)) else 0) << (5 - x) for x in range(6)) for y in range(10)]
def _px(*xs): return sum(1 << (5 - x) for x in xs)
G6 = {chr(c): _base(chr(c)) for c in range(32, 127)}
G6['\t'] = G6[' ']
G6['\xad'] = [0, 0, 0, 0, 0, _px(0, 1, 2, 3, 4, 5), 0, 0, 0, 0]
def _comp(b, rows=None, cedil=False, dotless=False):
    r = list(G6[b])
    if dotless: r[1] = 0
    for y, m in (rows or {}).items(): r[y] |= m
    if cedil: r[8] |= _px(3); r[9] |= _px(2)
    return r
ACU = {1: _px(4), 2: _px(3)}
GRA = {1: _px(2), 2: _px(3)}
CIR = {1: _px(3), 2: _px(2, 4)}
DIA = {1: _px(2, 4)}
for k, (b, a, dl) in {'à': ('a', GRA, 0), 'â': ('a', CIR, 0), 'è': ('e', GRA, 0), 'é': ('e', ACU, 0), 'ê': ('e', CIR, 0),
                      'î': ('i', CIR, 1), 'ï': ('i', DIA, 1), 'ô': ('o', CIR, 0), 'ù': ('u', GRA, 0), 'û': ('u', CIR, 0)}.items():
    G6[k] = _comp(b, a, dotless=bool(dl))
G6['ç'] = _comp('c', cedil=True)
# majuscules accentuées : accent d'un pixel sur la rangée 0 (les textes d'origine n'en ont pas)
for k, (b, a) in {'À': ('A', _px(2)), 'Â': ('A', _px(3)), 'É': ('E', _px(4)), 'È': ('E', _px(2)), 'Ê': ('E', _px(3)), 'Ç': ('C', 0),
                  'Î': ('I', _px(3)), 'Ô': ('O', _px(3)), 'Ù': ('U', _px(2)), 'Û': ('U', _px(3)), 'Ï': ('I', _px(2, 4))}.items():
    r = list(G6[b]); r[0] |= a
    if k == 'Ç': r[8] |= _px(3); r[9] |= _px(2)
    G6[k] = r
# 8x8 pour les menus (lignes 1..8 de la 6x10), bits alignés à gauche d'un octet
def glyph8(ch):
    r = G6.get(ch, G6['?'])
    return [(r[y] << 2) & 0xFF for y in range(1, 9)]
if __name__ == '__main__':
    for ch in 'àéîïçêû':
        print(ch); print('\n'.join(''.join('#' if v >> (5 - x) & 1 else '.' for x in range(6)) for v in G6[ch]))
