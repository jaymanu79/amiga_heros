# moteur de reference (portage de index.html) : sert a verifier le jeu SNES
import json, re, os
D = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', '../data/data.json')))
SC = D['logic']['scenes']; RT = D['logic']['routines']; VIE_MAX = 32
def cond_vraie(cond, W, L):
    for c in cond.split(' ET '):
        c = c.strip()
        if c == 'toujours': continue
        m = re.match(r'^Flags([WL]) bit (\d+) (actif|inactif)$', c)
        if m:
            v = W if m.group(1) == 'W' else L
            if (((v >> int(m.group(2))) & 1) == 1) != (m.group(3) == 'actif'): return False
            continue
        m = re.match(r'^\(FlagsW & (0x[0-9a-fA-F]+)\) (==|!=) (\d+)$', c)
        if m:
            eq = (W & int(m.group(1), 16)) == int(m.group(3))
            if eq != (m.group(2) == '=='): return False
            continue
        raise Exception(c)
    return True
def appliquer(eff, st):
    for e in eff.split(', '):
        e = e.strip()
        m = re.match(r'^(ACTIVE|EFFACE|BASCULE) Flags([WL]) bit (\d+)$', e)
        if m:
            k = m.group(2); n = 1 << int(m.group(3))
            if m.group(1) == 'ACTIVE': st[k] |= n
            elif m.group(1) == 'EFFACE': st[k] &= ~n
            else: st[k] ^= n
            continue
        m = re.match(r'^Compteur (-=|:=) (\d+)$', e)
        if m: st['or'] = st['or'] - int(m.group(2)) if m.group(1) == '-=' else int(m.group(2)); continue
        m = re.match(r'^(Vie|FlagsW|FlagsL) := (\d+)$', e)
        if m: st[{'Vie': 'vie', 'FlagsW': 'W', 'FlagsL': 'L'}[m.group(1)]] = int(m.group(2))
def nouvel_etat(): return {'sc': 1, 'W': 0, 'L': 0, 'vie': 0, 'or': 0}
def arriver(st, dest):
    st['sc'] = dest; st['vie'] = min(VIE_MAX, st['vie'] + SC[dest]['vie'])
    if st['vie'] < 0: st['vie'] = 0; st['W'] = 0; st['or'] = 0; st['sc'] = 0
def choisir(st, k):
    lien = SC[st['sc']]['liens'][k - 1]
    if lien is None: return 'invalide'
    if lien[0] == 'R': arriver(st, lien[1]); return None
    for cond, eff, dest in RT[lien[1]]:
        if cond_vraie(cond, st['W'], st['L']):
            appliquer(eff, st)
            if dest == '(aucune)': return 'quitter'
            if dest != 'RESTER': arriver(st, dest)
            return None
    return None
def path_from(txt):
    ks = []
    for ln in open(txt):
        m = re.match(r'\s*\d+\.\s+\S+\s+F(\d)\s+->', ln)
        if m: ks.append(int(m.group(1)))
    return ks
if __name__ == '__main__':
    ks = path_from('/tmp/path.txt'); st = nouvel_etat()
    for k in ks: choisir(st, k)
    print(len(ks), st, D['lab'][st['sc']])
