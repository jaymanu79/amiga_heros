#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""HEROS : plus court chemin (en nombre de choix) du début du jeu à l'écran de fin (code secret du concours).

    python3 chemin_fin.py                         # recherche rapide (~15 s) : chemin très court, optimalité non prouvée
    python3 chemin_fin.py --data ../DataHeros     # idem, avec le texte de chaque choix
    python3 chemin_fin.py --poids 0.1             # plus lent, un peu plus court (peut ne pas aboutir : mémoire)
    python3 chemin_fin.py --exact                 # A* admissible : optimal garanti, mais > 5 millions d'états, plusieurs Go
    python3 chemin_fin.py --bfs                   # parcours en largeur (pour comparer)

Le moteur (scènes, routines, drapeaux, vie) est celui de heros_jeu.py.

ÉTAT = (scène, FlagsW, FlagsL, vie).  L'or n'est jamais testé par le jeu : il est ignoré.
ARC  = un choix F1..F5, coût 1.  Mourir renvoie à TFin (Vallée de la Mort), le moteur le gère comme le jeu.
BUT  = TT39 ou T39a, l'écran qui donne le code secret (routine 1bc06, « FIN DU JEU : AFFICHE LE CODE DU CONCOURS »).

POURQUOI UNE HEURISTIQUE : le graphe des scènes est petit (216 nœuds) mais chaque combinaison d'objets et d'événements
(16 + 32 drapeaux) multiplie les états. Un parcours en largeur dépasse 40 millions d'états vers la profondeur 53.

HEURISTIQUES (toutes calculées sur un problème RELAXÉ : on oublie les suppressions de drapeaux, les conditions « inactif »,
les conditions != et la vie ; il ne reste que « pour franchir ce choix il faut être ici et avoir ces drapeaux actifs ») :
  * h_max  : coût d'un choix = 1 + max(coûts des préconditions).  Admissible et cohérente => A* optimal.
             Elle sait que le but est à >= 46 choix, mais sous-estime : elle ne compte pas la somme des objets à chercher.
             Avec elle, A* a prouvé qu'aucun chemin n'a moins de 73 choix (5 millions d'états, ~5 min).
  * h_add  : coût d'un choix = 1 + SOMME des coûts des préconditions.  Inadmissible (peut surestimer) mais compte chaque
             objet/événement à aller chercher : elle guide très bien.  Utilisée seule (poids 1) : 89 choix en 3 s ;
             avec un poids 0.3 devant h (f = g + 0.3 h) : 80 choix en ~15 s.
Règles de réduction d'états : on oublie les bits de drapeaux que le jeu ne teste jamais ; à position et drapeaux égaux,
un état avec moins de vie atteint plus tard est écarté (dominance).
"""
import argparse, collections, heapq, os, re, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import heros_jeu as H

SC, RT, IDX = H.SC, H.RT, H.IDX
BUTS = {IDX['TT39'], IDX['T39a']} if 'T39a' in IDX else {IDX['TT39']}
VIE_MAX = H.VIE_MAX_BARRE


def _compiler():
    """Pré-compile les routines (conditions et effets sur drapeaux) en masques : ~100x plus rapide que heros_jeu.choisir."""
    comp = {}
    for adr, branches in RT.items():
        out = []
        for cond, eff, dest in branches:
            mw = vw = ml = vl = 0; masques = []
            for c in cond.split(' ET '):
                c = c.strip()
                if c == 'toujours':
                    continue
                m = re.fullmatch(r'Flags([WL]) bit (\d+) (actif|inactif)', c)
                if m:
                    b = 1 << int(m.group(2)); on = m.group(3) == 'actif'
                    if m.group(1) == 'W':
                        mw |= b; vw |= b if on else 0
                    else:
                        ml |= b; vl |= b if on else 0
                    continue
                m = re.fullmatch(r'\(FlagsW & (0x[0-9a-fA-F]+)\) (==|!=) (\d+)', c)
                masques.append((int(m.group(1), 16), m.group(2) == '==', int(m.group(3))))
            ops = []
            for e in eff.split(', '):
                m = re.fullmatch(r'(ACTIVE|EFFACE|BASCULE) Flags([WL]) bit (\d+)', e.strip())
                if m:
                    ops.append((m.group(1), m.group(2), 1 << int(m.group(3))))
                    continue
                m = re.fullmatch(r'(Vie|FlagsW|FlagsL) := (\d+)', e.strip())
                if m:
                    ops.append(('SET', {'Vie': 'V', 'FlagsW': 'W', 'FlagsL': 'L'}[m.group(1)], int(m.group(2))))
            out.append((mw, vw, ml, vl, masques, ops, dest))
        comp[adr] = out
    return comp


COMP = _compiler()
# bits de drapeaux réellement testés par une condition : les autres n'influencent jamais le jeu, on les oublie (moins d'états)
RW = RL = 0
for _br in COMP.values():
    for mw, vw, ml, vl, masques, ops, dest in _br:
        RW |= mw; RL |= ml
        for m, eq, v in masques:
            RW |= m


def arriver(sc, W, L, vie, dest):
    vie += SC[dest]['vie']
    W &= RW; L &= RL
    if vie < 0:                                        # routine de mort : retour à TFin, W et vie remis à 0
        return 0, 0, L, 0
    return dest, W, L, min(vie, VIE_MAX)


def successeurs(etat):
    """etat = (sc, W, L, vie) -> [(k, etat_suivant)]. Même règles que heros_jeu.choisir (+ plafond de vie 32)."""
    sc, W, L, vie = etat
    res = []
    for k, lien in enumerate(SC[sc]['liens'], 1):
        if not lien:
            continue
        if lien[0] == 'R':
            res.append((k, arriver(sc, W, L, vie, lien[1]))); continue
        if lien[1] == '1bc06':                             # fin du jeu : affiche le code du concours
            res.append((k, (IDX['TT39'], W, L, vie))); continue
        for mw, vw, ml, vl, masques, ops, dest in COMP[lien[1]]:
            if (W & mw) != vw or (L & ml) != vl or any(((W & m) == v) != eq for m, eq, v in masques):
                continue
            w2, l2, v2 = W, L, vie
            for op, cle, x in ops:
                if op == 'SET':
                    if cle == 'W': w2 = x
                    elif cle == 'L': l2 = x
                    else: v2 = x
                elif cle == 'W':
                    w2 = (w2 | x) if op == 'ACTIVE' else (w2 & ~x) if op == 'EFFACE' else (w2 ^ x)
                else:
                    l2 = (l2 | x) if op == 'ACTIVE' else (l2 & ~x) if op == 'EFFACE' else (l2 ^ x)
            w2 &= RW; l2 &= RL
            if dest == '(aucune)':
                break
            if dest == 'RESTER':
                res.append((k, (sc, w2, l2, v2)))
            else:
                res.append((k, arriver(sc, w2, l2, v2, dest)))
            break
    return res


# --------------------------------------------------------------------------- heuristique
def _actions_relaxees():
    """Problème RELAXÉ : on oublie les suppressions (EFFACE), les conditions « inactif », les conditions != et la vie.
    Un fait = « être dans la scène s » ou « le drapeau W/L bit b est actif ». Une action = un choix Fk (ou une branche de routine) :
    préconditions = scène de départ + drapeaux requis actifs ; effets = scène d'arrivée + drapeaux activés."""
    NS = len(SC); fW = NS; fL = NS + 16          # numérotation des faits : scènes, puis bits W (16), puis bits L (32)
    acts = []
    for s, sc in enumerate(SC):
        for lien in sc['liens']:
            if not lien:
                continue
            if lien[0] == 'R':
                acts.append(([s], [lien[1]]))
            elif lien[1] == '1bc06':
                acts.append(([s], list(BUTS)))
            else:
                for mw, vw, ml, vl, masques, ops, dest in COMP[lien[1]]:
                    pre = [s] + [fW + b for b in range(16) if (mw & vw) >> b & 1] + [fL + b for b in range(32) if (ml & vl) >> b & 1]
                    for m, eq, v in masques:
                        if eq:
                            pre += [fW + b for b in range(16) if v >> b & 1]
                    eff = [d for d in [dest] if isinstance(d, int)]
                    for op, cle, x in ops:
                        if op == 'EFFACE':
                            continue
                        if cle == 'V':
                            continue
                        base = fW if cle == 'W' else fL
                        eff += [base + b for b in range(32) if (x if op == 'SET' else x) >> b & 1]
                    if dest == 'RESTER':
                        eff.append(s)
                    acts.append((sorted(set(pre)), eff))
    users = collections.defaultdict(list)
    for i, (pre, eff) in enumerate(acts):
        for f in pre:
            users[f].append(i)
    return acts, users, NS, fW, fL


ACTS, USERS, NS, FW, FL = _actions_relaxees()
BUT_FAITS = set(BUTS)


def h_max(sc, W, L):
    """Coût minimal (en choix) pour atteindre un but dans le problème relaxé, à partir de l'état (sc, W, L).
    Parcours par couches : un fait est connu au coût c, une action devient franchissable au coût max(préconditions)+1.
    Admissible (le relaxé a plus de possibilités que le vrai jeu) et cohérente (coûts unitaires)."""
    cout = {sc: 0}
    front = [sc]
    for b in range(16):
        if W >> b & 1: cout[FW + b] = 0; front.append(FW + b)
    for b in range(32):
        if L >> b & 1: cout[FL + b] = 0; front.append(FL + b)
    manque = [len(p) for p, e in ACTS]
    # actions sans précondition connue : toutes ont au moins la scène de départ
    c = 0
    while front:
        suiv = []
        for f in front:
            for i in USERS.get(f, ()):
                manque[i] -= 1
                if manque[i] == 0:
                    for e in ACTS[i][1]:
                        if e not in cout:
                            cout[e] = c + 1; suiv.append(e)
                            if e in BUT_FAITS:
                                return c + 1
        front = suiv; c += 1
    return None


def h_add(sc, W, L):
    """Variante INADMISSIBLE : coût d'une action = 1 + SOMME des coûts de ses préconditions (au lieu du max).
    Elle compte chaque objet / événement à aller chercher, donc elle guide beaucoup mieux, mais peut surestimer."""
    cout = {sc: 0}
    for b in range(16):
        if W >> b & 1: cout[FW + b] = 0
    for b in range(32):
        if L >> b & 1: cout[FL + b] = 0
    tas = [(0, f) for f in cout]; heapq.heapify(tas)
    manque = [len(p) for p, e in ACTS]; somme = [0] * len(ACTS)
    while tas:
        c, f = heapq.heappop(tas)
        if c > cout[f]:
            continue
        if f in BUT_FAITS:
            return c
        for i in USERS.get(f, ()):
            manque[i] -= 1; somme[i] += c
            if manque[i] == 0:
                ca = somme[i] + 1
                for e in ACTS[i][1]:
                    if ca < cout.get(e, 1 << 30):
                        cout[e] = ca; heapq.heappush(tas, (ca, e))
    return None


def chercher(depart, utiliser_h=True, poids=1.0, somme=False):
    """A* (ou largeur si utiliser_h est faux). Retourne (chemin[(k, état)], nombre d'états développés)."""
    cache_h = {}
    def h(e):
        if not utiliser_h:
            return 0
        k = e[:3]
        if k not in cache_h:
            cache_h[k] = (h_add if somme else h_max)(*k)
        return cache_h[k]
    pere = {depart: None}; g = {depart: 0}
    front_vie = collections.defaultdict(list)       # (sc,W,L) -> [(g, vie)] : dominance (même position, moins de vie, pas plus tôt)
    h0 = h(depart)
    tas = [(poids * h0, 0, depart)]
    n = 0; fmax = 0; t0 = time.time()
    while tas:
        f, gc, e = heapq.heappop(tas)
        if gc > g[e]:
            continue
        if f >= fmax + 1:
            fmax = f; print('  f = %d : %d états développés, %.0f s' % (f, n, time.time() - t0), file=sys.stderr, flush=True)
        if e[0] in BUTS:
            chemin = []
            while pere[e]:
                p, k = pere[e]; chemin.append((k, e)); e = p
            return chemin[::-1], n
        n += 1
        for k, e2 in successeurs(e):
            c = gc + 1
            if c >= g.get(e2, 1 << 30):
                continue
            he = h(e2)
            if he is None:                       # but inatteignable même dans le relaxé
                continue
            cle = e2[:3]
            if any(g2 <= c and v2 >= e2[3] for g2, v2 in front_vie[cle]):
                continue
            front_vie[cle].append((c, e2[3]))
            g[e2] = c; pere[e2] = (e, k)
            heapq.heappush(tas, (c + poids * he, c, e2))
    return None, n


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--bfs', action='store_true', help='parcours en largeur (sans heuristique)')
    ap.add_argument('--exact', action='store_true', help='A* avec h_max (admissible) : chemin optimal garanti, très long')
    ap.add_argument('--poids', type=float, default=0.3, help='poids de h_add dans f = g + poids*h (défaut 0.3 ; plus petit = plus court mais plus lent)')
    ap.add_argument('--data', help='fichier DataHeros : affiche le texte de chaque choix')
    a = ap.parse_args()
    # le jeu commence en TC1 ; l'état initial a vie 0, TC6 donne +28
    dep = (IDX['TC1'], 0, 0, 0)
    t0 = time.time()
    chemin, n = chercher(dep, not a.bfs, 1.0 if a.exact else a.poids, not a.exact)
    dt = time.time() - t0
    if chemin is None:
        sys.exit('Aucun chemin trouvé (%d états développés).' % n)
    T = H.Textes(H.trouver_data(a.data)) if a.data else None

    def choix_txt(nom, k):
        if T is None:
            return ''
        try:
            L = T.lignes(nom)
        except KeyError:
            return ''
        for i, x in enumerate(L):
            m = re.match(r'\s*< ?F%d ?>\s*(.*)' % k, x)
            if m:
                t, j = m.group(1).strip(), i + 1
                while j < len(L) and L[j].startswith('   ') and not re.match(r'\s*< ?F\d', L[j]):
                    t += ' ' + L[j].strip(); j += 1
                return t
        return ''
    print('%s : %d choix, %d états développés, %.1f s\n' % ('Largeur' if a.bfs else 'A* exact' if a.exact else 'A* (h_add, poids %g)' % a.poids, len(chemin), n, dt))
    sc = dep[0]
    print('départ  %s' % SC[sc]['nom'])
    for i, (k, e) in enumerate(chemin, 1):
        print('%3d. %-5s F%d -> %-5s vie %2d  %s' % (i, SC[sc]['nom'], k, SC[e[0]]['nom'], e[3], choix_txt(SC[sc]['nom'], k)[:70]))
        sc = e[0]


if __name__ == '__main__':
    main()
