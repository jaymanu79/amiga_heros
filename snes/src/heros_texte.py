#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""HEROS : extraction et reconstruction du fichier de textes DataHeros (Amiga).

    python3 heros_texte.py extract DataHeros heros-fr.txt     # DataHeros -> texte modifiable
    python3 heros_texte.py pack heros-fr.txt DataHeros-new    # texte -> DataHeros (identique à l'original si rien n'a changé)
    python3 heros_texte.py check DataHeros                    # essai : extract puis pack, comparaison octet par octet

Format du fichier texte
-----------------------
    # commentaire (ignoré, comme les lignes vides)
    INDEX: TIN1 TIN2 ...        ordre des entrées dans l'index du fichier (écrit par 'extract')
    === TC1 cle=55              début d'un bloc : nom (4 lettres max) et clé XOR en hexadécimal
    18,8|Vous reprenez conscience...      une ligne d'écran : colonne,ligne|texte
    ...

Les blocs sont écrits dans l'ordre où ils sont rangés dans le fichier. Dans le texte :
  \\xNN = octet NN en hexadécimal (ex. \\xad = le tiret de soulignement du jeu), \\\\ = une barre oblique inverse.
  @0 @1 @2 = codes de couleur du jeu (zéro largeur à l'affichage), à conserver tels quels.
Les lettres accentuées Latin-1 s'écrivent telles quelles.

Pour traduire, on peut aussi écrire un PARAGRAPHE que le programme découpe en lignes :
    colonne,ligne,largeur,retrait|texte long ...
  - 'largeur' = nombre de caractères visibles maximum par ligne, comptés depuis la colonne de départ ;
  - 'retrait' = espaces ajoutés au début des lignes suivantes (0 si omis) ;
  - 'ligne' peut être absolue (12) ou relative (+1 = juste après la dernière ligne écrite, +2 = en laissant
    une ligne vide), pour les lignes simples comme pour les paragraphes.
Exemple :   18,8,42|Vous reprenez conscience... Vous souffrez d'une sourde douleur à la tête.
            18,+2,42,7|< F1 > Vous décidez d'emprunter l'escalier en colimaçon.

Contrôles faits à la reconstruction : colonne < 80, ligne < 64, bord droit <= 64, jeu de caractères
(le jeu n'affiche que 88 symboles : A-Z a-z 0-9 . , ; : ' / ? ! - ( ) < > @ et quelques accents), pas d'octet
00 ni FF dans le texte, taille finale comparée à celle de l'original (111530 octets).
"""
import argparse
import re
import struct
import sys

FIN_LIGNE, FIN_BLOC = 0xFF, 0x00
CLES = (0x55, 0xAA)
TAILLE_ORIGINALE = 111530
BORD_DROIT = 64
# octets de texte présents dans l'original + W X Z (existent dans la police)
ENTETE_OK = (set(b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789 .,;:'/?!-()<>@")
             | {0xE0, 0xE2, 0xE7, 0xE8, 0xE9, 0xEA, 0xEE, 0xEF, 0xF4, 0xF9, 0xFB, 0xAD, 0x09})


class Erreur(Exception):
    pass


# ----------------------------------------------------------------- codage du texte
def echapper(octets):
    out = []
    for b in octets:
        if b == 0x5C:
            out.append('\\\\')
        elif 0x20 <= b < 0x7F or (b >= 0xA0 and b != 0xAD):
            out.append(chr(b))
        else:
            out.append('\\x%02x' % b)
    return ''.join(out)


def deshabiller(s, ctx):
    """chaîne avec échappements -> octets."""
    out, i = bytearray(), 0
    while i < len(s):
        c = s[i]
        if c == '\\':
            if s.startswith('\\\\', i):
                out.append(0x5C)
                i += 2
                continue
            m = re.match(r'\\x([0-9a-fA-F]{2})', s[i:])
            if not m:
                raise Erreur('%s : échappement invalide : %r' % (ctx, s[i:i + 6]))
            out.append(int(m.group(1), 16))
            i += 4
            continue
        if ord(c) > 0xFF:
            raise Erreur('%s : caractère %r (U+%04X) impossible à écrire dans le jeu (Latin-1 seulement)'
                         % (ctx, c, ord(c)))
        out.append(ord(c))
        i += 1
    return bytes(out)


# ------------------------------------------------------------------- lecture du fichier
def xor(octets, cle):
    return bytes(b ^ cle for b in octets)


def lire_lignes(flux):
    """flux décodé -> [(col, lig, octets)] ; la dernière ligne se termine par 00, les autres par FF."""
    lignes, i = [], 0
    while True:
        if i + 2 > len(flux):
            raise Erreur('bloc tronqué')
        col, lig = flux[i], flux[i + 1]
        i += 2
        deb = i
        while i < len(flux) and flux[i] not in (FIN_LIGNE, FIN_BLOC):
            i += 1
        if i >= len(flux):
            raise Erreur('bloc sans fin')
        lignes.append((col, lig, flux[deb:i]))
        fin = flux[i]
        i += 1
        if fin == FIN_BLOC:
            return lignes, i


def plausible(flux):
    """vrai si le flux ressemble à du texte (sert à reconnaître la bonne clé)."""
    try:
        lignes, n = lire_lignes(flux)
    except Erreur:
        return None
    if any(c >= 80 or l >= 64 for c, l, _ in lignes):
        return None
    tot = sum(len(t) for _, _, t in lignes)
    ok = sum(1 for _, _, t in lignes for b in t if 0x20 <= b < 0x7F or b >= 0xA0)
    return lignes if tot and ok / tot >= 0.9 else None


def lire_dataheros(d):
    """-> (blocs dans l'ordre du fichier, ordre de l'index). Bloc = dict(nom, cle, lignes)."""
    debut = struct.unpack('>I', d[:4])[0]
    index = []
    for p in range(4, debut, 8):
        nom = d[p:p + 4]
        if nom != b'\0' * (4 - len(nom.strip(b'\0'))) + nom.strip(b'\0'):
            raise Erreur('nom non standard dans l\'index : %r' % nom)
        index.append((nom.strip(b'\0').decode('latin-1'), struct.unpack('>I', d[p + 4:p + 8])[0]))
    offs = sorted({o for _, o in index})
    if len(offs) != len(index) or offs[0] != debut:
        raise Erreur('index inattendu (adresses en double ou trou avant le premier bloc)')
    blocs = []
    for nom, o in sorted(index, key=lambda x: x[1]):
        fin = min([x for x in offs if x > o] + [len(d)])
        brut = d[o:fin]
        for cle in CLES:
            flux = xor(brut, cle)
            lignes = plausible(flux)
            if lignes is not None:
                break
        else:
            raise Erreur('bloc %s : texte non reconnu' % nom)
        blocs.append({'nom': nom, 'cle': cle, 'lignes': lignes})
    return blocs, [n for n, _ in index]


def ecrire_texte(blocs, ordre):
    out = ['# HEROS - textes du jeu (extrait par heros_texte.py). Voir l\'en-tête du programme pour le format.',
           '# Ne pas changer les lignes "===" ni "INDEX:" ; les codes @0 @1 @2 sont des couleurs.', '',
           'INDEX: ' + ' '.join(ordre), '']
    for b in blocs:
        out.append('=== %s cle=%02x' % (b['nom'], b['cle']))
        for col, lig, t in b['lignes']:
            out.append('%d,%d|%s' % (col, lig, echapper(t)))
        out.append('')
    return '\n'.join(out)


# ------------------------------------------------------------------ lecture du texte
def largeur_visible(s):
    return len(re.sub(rb'@\d', b'', s))


def decouper(mots, largeur, retrait):
    """mots (octets) -> lignes d'au plus 'largeur' caractères visibles ; retrait sur les suivantes."""
    lignes, cur, vis, premiere = [], b'', 0, True
    pre = b' ' * retrait
    for m in mots:
        w = largeur_visible(m)
        marge = 0 if premiere else retrait
        if cur and vis + 1 + w > largeur:
            lignes.append(cur)
            cur, vis, premiere = pre + m, retrait + w, False
        elif cur:
            cur, vis = cur + b' ' + m, vis + 1 + w
        else:
            cur, vis = (pre if not premiere else b'') + m, (retrait if not premiere else 0) + w
    if cur:
        lignes.append(cur)
    return lignes


def lire_texte(contenu):
    """-> (blocs, ordre index). Accepte lignes simples et paragraphes."""
    blocs, ordre, cur, derniere = [], None, None, None
    for n, ligne in enumerate(contenu.split('\n'), 1):
        ligne = ligne.rstrip('\r')
        if not ligne.strip() or ligne.startswith('#'):
            continue
        ctx = 'ligne %d' % n
        if ligne.startswith('INDEX:'):
            ordre = ligne[6:].split()
            continue
        m = re.match(r'===\s+(\S+)\s+cle=([0-9a-fA-F]{2})\s*$', ligne)
        if m:
            cur = {'nom': m.group(1), 'cle': int(m.group(2), 16), 'lignes': []}
            if not re.fullmatch(r'[A-Za-z0-9]{1,4}', cur['nom']) or cur['cle'] not in CLES:
                raise Erreur('%s : bloc invalide : %s' % (ctx, ligne))
            blocs.append(cur)
            derniere = None
            continue
        m = re.match(r'(\d+),(\+?\d+)(?:,(\d+)(?:,(\d+))?)?\|(.*)$', ligne)
        if not m or cur is None:
            raise Erreur('%s : ligne incomprise : %r' % (ctx, ligne[:60]))
        col, lig = int(m.group(1)), m.group(2)
        if lig.startswith('+'):
            if derniere is None:
                raise Erreur('%s : ligne relative sans ligne précédente' % ctx)
            lig = derniere + int(lig)
        else:
            lig = int(lig)
        texte = deshabiller(m.group(5), ctx)
        if m.group(3) is None:                                     # ligne simple
            cur['lignes'].append((col, lig, texte))
            derniere = lig
        else:                                                      # paragraphe
            larg, retrait = int(m.group(3)), int(m.group(4) or 0)
            for k, t in enumerate(decouper(texte.split(), larg, retrait)):
                cur['lignes'].append((col, lig + k, t))
                derniere = lig + k
    if ordre is None:
        ordre = [b['nom'] for b in blocs]
    return blocs, ordre


# --------------------------------------------------------------------- reconstruction
def controler(blocs, libre):
    avert, erreurs = [], []
    for b in blocs:
        if not b['lignes']:
            erreurs.append('bloc %s : vide' % b['nom'])
        for col, lig, t in b['lignes']:
            ou = 'bloc %s, ligne %d' % (b['nom'], lig)
            if col >= 80 or lig >= 64:
                erreurs.append('%s : position (%d,%d) hors écran (colonne < 80, ligne < 64)' % (ou, col, lig))
            if FIN_LIGNE in t or FIN_BLOC in t:
                erreurs.append('%s : octet 00 ou FF interdit dans le texte' % ou)
            if col + largeur_visible(t) > BORD_DROIT:
                avert.append('%s : dépasse le bord droit (col %d + %d > %d) : %r'
                             % (ou, col, largeur_visible(t), BORD_DROIT, t[:30].decode('latin-1')))
            mauvais = sorted({c for c in t if c not in ENTETE_OK})
            if mauvais and not libre:
                erreurs.append('%s : caractère(s) absent(s) de la police du jeu : %s   (ligne : %r)'
                               % (ou, ' '.join(repr(bytes([c]).decode('latin-1')) for c in mauvais),
                                  t.decode('latin-1')[:40]))
    return avert, erreurs


def empaqueter(blocs, ordre):
    noms = [b['nom'] for b in blocs]
    if sorted(noms) != sorted(ordre) or len(set(noms)) != len(noms):
        raise Erreur('INDEX et blocs ne correspondent pas (blocs en double ou manquants)')
    debut = 4 + 8 * len(blocs)
    corps, adr, pos = bytearray(), {}, debut
    for b in blocs:
        flux = bytearray()
        for i, (col, lig, t) in enumerate(b['lignes']):
            flux += bytes([col, lig]) + t + bytes([FIN_BLOC if i == len(b['lignes']) - 1 else FIN_LIGNE])
        octets = xor(bytes(flux), b['cle'])
        adr[b['nom']] = pos
        corps += octets
        pos += len(octets)
    index = b''.join(n.encode('latin-1').rjust(4, b'\0') + struct.pack('>I', adr[n]) for n in ordre)
    return struct.pack('>I', debut) + index + bytes(corps)


# --------------------------------------------------------------------------- commandes
def cmd_extract(a):
    d = open(a.source, 'rb').read()
    blocs, ordre = lire_dataheros(d)
    open(a.sortie, 'w', encoding='utf-8').write(ecrire_texte(blocs, ordre))
    nl = sum(len(b['lignes']) for b in blocs)
    print('%s : %d blocs, %d lignes de texte écrits dans %s' % (a.source, len(blocs), nl, a.sortie))


def cmd_pack(a):
    blocs, ordre = lire_texte(open(a.texte, encoding='utf-8').read())
    avert, erreurs = controler(blocs, a.libre)
    for w in avert:
        print('attention :', w, file=sys.stderr)
    if erreurs:
        for e in erreurs[:40]:
            print('ERREUR :', e, file=sys.stderr)
        if len(erreurs) > 40:
            print('... et %d autres erreurs' % (len(erreurs) - 40), file=sys.stderr)
        sys.exit('Reconstruction annulée (%d erreur(s)).' % len(erreurs))
    d = empaqueter(blocs, ordre)
    open(a.sortie, 'wb').write(d)
    print('%s écrit : %d octets (%d blocs)' % (a.sortie, len(d), len(blocs)))
    if len(d) > TAILLE_ORIGINALE:
        print('ATTENTION : %d octets de plus que l\'original (%d) ; le jeu Amiga risque de refuser ce fichier.'
              % (len(d) - TAILLE_ORIGINALE, TAILLE_ORIGINALE), file=sys.stderr)
    else:
        print('Taille inférieure ou égale à l\'original (%d octets) : %d octets de marge.'
              % (TAILLE_ORIGINALE, TAILLE_ORIGINALE - len(d)))


def cmd_check(a):
    d = open(a.source, 'rb').read()
    blocs, ordre = lire_dataheros(d)
    txt = ecrire_texte(blocs, ordre)
    blocs2, ordre2 = lire_texte(txt)
    d2 = empaqueter(blocs2, ordre2)
    if d2 == d:
        print('OK : extract puis pack redonne le fichier à l\'identique (%d octets, %d blocs).' % (len(d), len(blocs)))
    else:
        i = next((k for k in range(min(len(d), len(d2))) if d[k] != d2[k]), min(len(d), len(d2)))
        sys.exit('DIFFÉRENT : premier octet différent à l\'adresse %d (tailles %d / %d).' % (i, len(d), len(d2)))


def main():
    ap = argparse.ArgumentParser(description='HEROS : DataHeros <-> fichier texte')
    sp = ap.add_subparsers(dest='cmd', required=True)
    p = sp.add_parser('extract', help='DataHeros -> fichier texte')
    p.add_argument('source', help='fichier DataHeros')
    p.add_argument('sortie', nargs='?', default='heros-fr.txt')
    p.set_defaults(f=cmd_extract)
    p = sp.add_parser('pack', help='fichier texte -> DataHeros')
    p.add_argument('texte')
    p.add_argument('sortie', nargs='?', default='DataHeros-new')
    p.add_argument('--libre', action='store_true', help='ne pas contrôler le jeu de caractères')
    p.set_defaults(f=cmd_pack)
    p = sp.add_parser('check', help='essai aller-retour sur un DataHeros')
    p.add_argument('source')
    p.set_defaults(f=cmd_check)
    a = ap.parse_args()
    try:
        a.f(a)
    except Erreur as e:
        sys.exit('Erreur : %s' % e)


if __name__ == '__main__':
    main()
