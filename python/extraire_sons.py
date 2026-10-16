#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
extraire_sons.py : extrait la MUSIQUE / AMBIANCES de HEROS depuis un dump de la chip RAM
(heroschip.bin pris dans le debugger FS-UAE) et la reconstruit en fichiers .mod standard.

    python3 extraire_sons.py heroschip.bin [dossier_de_sortie]

ARCHITECTURE DECOUVERTE (c'est un vrai module de type ProTracker/Soundtracker, a 3 voies) :
  * 15 echantillons PCM 8 bits signes (format brut Amiga), a partir de 0x41A94, mis bout a bout ;
    leur en-tete (8 octets : longueur en mots, volume, debut de boucle, longueur de boucle)
    est a 0x20BD4 = exactement le format d'un en-tete d'echantillon .mod.
  * 30 patterns de 64 lignes x 3 voies x cellules de 4 octets (periode, instrument, effet,
    parametre : cellules ProTracker), a partir de 0x20C74, 768 octets par pattern.
    Effets utilises : 0xC (volume), 0x1 / 0x2 (glissando) ; vitesse 6, tempo VBL 50 Hz.
  * "ordonnancement" : 31 listes de numeros de pattern terminees par 0xFF, a 0x1C7B2.. ;
    chaque SCENE du jeu pointe vers la sienne (2e long mot de l'enregistrement de scene,
    en relatif a A6 = 0x15468) : la musique change selon la zone.
    L'octet qui suit le 0xFF est la POSITION DE RETOUR : arrive en fin de liste, le lecteur
    reprend a cette position (0 = tout rejouer ; 1 = l'intro de la liste n'est jouee qu'une fois).
  * declenchement : la boucle principale (0x15FBC) rappelle, a CHAQUE affichage de scene, la routine
    0x1C28C qui coupe les 4 volumes, remet position/ligne/tick a zero et pointe la liste de la scene ;
    le lecteur proprement dit tourne sous interruption (50 Hz) : 6 ticks par ligne, 64 lignes
    par pattern (12 octets par ligne), puis pattern suivant de la liste.
Sortie : echantillons .wav, un .mod par liste (seq_XX.mod), heros_tout.mod (les 30 patterns),
et ambiances_par_scene.txt.
"""
import os
import struct
import sys
import wave

A6, TAB_SCENES, TAILLE_SCENE, NB_SCENES = 0x15468, 0x16DA6, 58, 211   # scenes 0..210 (TC1..TT48), -1 = TFin
ENTETES, PATTERNS, ECH0, NB_ECH, NB_PAT = 0x20BD4, 0x20C74, 0x41A94, 15, 30
HZ_WAV = 8287           # C-2 (periode 428) : indicatif


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    d = open(sys.argv[1], 'rb').read()[:0x80000]      # la chip RAM est repliee tous les 512 Ko
    sortie = sys.argv[2] if len(sys.argv) > 2 else 'sons_heros'
    os.makedirs(sortie, exist_ok=True)

    # ---- echantillons
    ents = [struct.unpack('>HHHH', d[ENTETES + 8 * i:ENTETES + 8 * i + 8]) for i in range(NB_ECH)]
    donnees, p = [], ECH0
    for ln, vol, ls, ll in ents:
        donnees.append(d[p:p + 2 * ln]); p += 2 * ln
    for i, b in enumerate(donnees):
        with wave.open(os.path.join(sortie, 'echantillon_%02d.wav' % (i + 1)), 'wb') as w:
            w.setnchannels(1); w.setsampwidth(1); w.setframerate(HZ_WAV)
            w.writeframes(bytes((x + 128) & 255 for x in b))

    # ---- patterns : 3 voies -> 4 voies (la 4e reste vide)
    def pattern(n):
        out = bytearray()
        for r in range(64):
            o = PATTERNS + n * 768 + r * 12
            out += d[o:o + 12] + b'\0\0\0\0'
        return bytes(out)

    def ecrire_mod(nom, titre, ordre, boucle=0):
        nbp = max(ordre) + 1
        m = bytearray(titre.encode('ascii')[:20].ljust(20, b'\0'))
        for i in range(31):
            if i < NB_ECH:
                ln, vol, ls, ll = ents[i]
                m += ('HEROS %02d' % (i + 1)).encode().ljust(22, b'\0') + struct.pack('>HBBHH', ln, 0, vol & 0x7f, ls, ll)
            else:
                m += bytes(22) + struct.pack('>HBBHH', 0, 0, 0, 0, 1)
        m += bytes([len(ordre), boucle]) + bytes(ordre) + bytes(128 - len(ordre)) + b'M.K.'
        for n in range(nbp):
            m += pattern(n)
        for b in donnees:
            m += b
        open(os.path.join(sortie, nom), 'wb').write(bytes(m))

    # ---- listes d'ordonnancement, une par scene
    seqs, par_scene = {}, []
    for i in range(-1, NB_SCENES):          # -1 : TFin, juste avant la table
        r = d[TAB_SCENES + i * TAILLE_SCENE:TAB_SCENES + (i + 1) * TAILLE_SCENE]
        nom = r[:4].replace(b'\0', b'').decode('latin-1')
        a = A6 + struct.unpack('>I', r[8:12])[0]
        liste = []
        while d[a] != 0xFF:
            liste.append(d[a]); a += 1
        boucle = d[a + 1]          # l'octet qui suit le 0xFF = position de retour de la boucle
        seqs.setdefault((tuple(liste), boucle), []).append('%s(%d)' % (nom, i))
    L = ['Chaque scène joue une liste de patterns (ordonnancement du module).', '']
    for k, ((liste, boucle), scenes) in enumerate(sorted(seqs.items(), key=lambda x: x[0])):
        nom = 'seq_%02d.mod' % k
        ecrire_mod(nom, 'HEROS seq %d' % k, list(liste), boucle)
        L.append('%s  patterns %s, boucle sur la position %d  <- %d scènes : %s' % (
            nom, list(liste), boucle, len(scenes), ', '.join(scenes)))
    # pages d'introduction (TIN1..TIN4) : le programme lance la liste a 0x734D (relatif a A6) avant la
    # 1re page ; elle joue pendant les 4 pages sans redemarrer (Echap saute la suite)
    a = A6 + 0x734D
    liste = []
    while d[a] != 0xFF:
        liste.append(d[a]); a += 1
    cle = (tuple(liste), d[a + 1])
    k = sorted(seqs).index(cle)
    L += ['', "Pages d'introduction (TIN1..TIN4, titre/règles/partenaires/note) : seq_%02d.mod, patterns %s" % (k, liste)]
    ecrire_mod('heros_tout.mod', 'HEROS tous patterns', list(range(NB_PAT)))
    open(os.path.join(sortie, 'ambiances_par_scene.txt'), 'w', encoding='utf-8').write('\n'.join(L) + '\n')
    print('%d echantillons, %d listes -> %s/' % (NB_ECH, len(seqs), sortie))


if __name__ == '__main__':
    main()
