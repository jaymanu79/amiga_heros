#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HEROS (Amiga, 1994, Olivier Thil / DREAM) : jeu en mode texte + extracteur, en UN seul programme.

UTILISATION   (le fichier DataHeros doit etre dans le meme dossier que ce programme)
    python3 heros_jeu.py                       # jouer (pages d'introduction, puis l'histoire)
    python3 heros_jeu.py --sans-intro          # saute l'intro : village, Vie 28
    python3 heros_jeu.py --charge 1            # reprend la sauvegarde n°1
    python3 heros_jeu.py --no-sound            # sans musique (alias : --sans-son)
    python3 heros_jeu.py --wav TL1 tl1.wav     # ecrit la musique d'une scene dans un WAV (ou 'intro')
    python3 heros_jeu.py --extraire            # au lieu de jouer : ecrit heros_complet.txt
    python3 heros_jeu.py --extraire sortie.txt # ... ou dans le fichier de votre choix
    python3 heros_jeu.py --data /chemin/DataHeros   # si DataHeros est ailleurs

TOUCHES EN JEU
    F1..F5 ou & é " ' (   choisir (la rangee des chiffres d'un clavier AZERTY, sans Maj)
    S sauver / C charger (9 emplacements)       B retour arriere (repetable)
    T ecran de triche : aller a une scene (par son code), Vie 28, Or, objets
    M musique on/off  (si la machine n'a pas de sortie son, le jeu continue en silence)
    Q quitter        (pages d'intro : une touche = suite, Echap = sauter l'intro)

LA LOGIQUE DU JEU
    DataHeros contient les textes (codes). L'enchainement des scenes, les objets, la vie et
    l'or sont dans l'executable HerosExe (compresse) : ils ont ete decodes une fois depuis un
    dump memoire et sont INTEGRES ci-dessous (variable LOGIC). Seul DataHeros est necessaire.

FORMAT DE DataHeros (big-endian, 68000)
    u32 debut_des_donnees ; puis (debut-4)/8 entrees : char[4] nom, u32 DEBUT du bloc de ce nom.
    Chaque bloc = XOR 0x55 octet par octet ; texte decode :
       colonne ligne caracteres... 0xFF  (une ligne d'ecran) ... 0x00 (fin).
       "@" + chiffre = changement de couleur (@1 = normal).
    Bloc protege (code du concours, scene 'TT39') : XOR 0x55 puis NOT (= cle 0xAA).
    Scene = enregistrement (nom de 4 caracteres = bloc de texte, 5 liens F1..F5, delta de VIE).
    Nom donne deux fois (TM70, TT43) : deux scenes distinctes au meme texte : NOM#1 / NOM#2.
"""
import argparse
import array
import atexit
import base64
import collections
import io
import itertools
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import threading
import time
import wave
import zlib

CLES = (0x55, 0xAA)          # 0xAA = 0x55 puis NOT : bloc protege
FIN_LIGNE, FIN_BLOC = 0xFF, 0x00

OBJ = {0: 'Serre-tête', 1: 'Bracelet de bronze', 2: "Anneau d'argent",
       3: 'Gemme rouge', 4: 'Gemme verte', 5: 'Clé',
       6: 'Bracelets ailés (enfilés) ?', 7: 'Cape Rouge', 8: 'Pendentif en Or',
       9: 'Écailles de dragon', 10: 'Nourriture (viande séchée)', 11: 'Épée',
       12: 'Sac (torche, silex, vêtements)', 13: 'Pierre Noire ovoïde',
       14: 'Deuxième pierre (donnée par le Sorcier) ?', 15: 'Bouts de champignons'}

# Notes par nom de scene / de bloc.
NOTES = {
    'TC1': ["ÉCRAN TITRE : F1 = nouvelle partie, F2 = quitter."],
    'TFin': ["PAGE DE MORT « Vallée de la Mort » : F1 = recommencer, F2 = quitter."],
    'TT39': ["*** CODE DU CONCOURS (VRAI) : BLOC PROTÉGÉ, clé XOR 0x55 puis NOT (0xAA). ***",
             "Atteinte uniquement par la routine finale 0x1BC06 (depuis le retour sur Terre) qui déchiffre",
             "ce bloc en mémoire (inversion des octets) puis affiche la scène. Confirmé : TOTEM est le vrai code."],
    'T39a': ["*** LEURRE : code « PYRAMIDE » (clé ordinaire 0x55, lisible par n'importe quel décodeur). ***",
             "Aucune scène ne l'affiche jamais. Qui enverrait ce code au concours prouverait qu'il a triché."],
    'TIN1': ["Page de présentation (titre), affichée par le programme, pas par une scène."],
    'TIN2': ["Page « LES PARTENAIRES », affichée par le programme."],
    'TIN3': ["Page « RÈGLE DU JEU », affichée par le programme."],
    'TIN4': ["Page « NOTE DE L'AUTEUR », affichée par le programme."],
}


# Noms parlants des evenements (FlagsL) : (nom, role). Deduits des scenes qui les posent/testent.
EVT = {
    0: ("CLAIRIERE_VOLEUR_VUE", "1ère fois : rencontre du Voleur (TM4) ; ensuite : clairière déjà vue (TM11)"),
    1: ("CLAIRIERE_ORQUES_VUE", "clairière des 3 Orques : embuscade au 1er passage (TM29), « de retour » ensuite (M31a/M31b)"),
    2: ("SABLES_MOUVANTS_VUS", "1er passage : piégé dans les sables mouvants (TM32) ; ensuite : on sait les éviter (TM34)"),
    3: ("CLAIRIERE_CADAVRE_VUE", "clairière du combat Orques/homme mort (TM37) ; au retour TM40/TM41/TM37"),
    4: ("PLATEAU_SCORPIONS_VU", "plateau rocailleux aux scorpions : 1ère fois TM43/TM47, ensuite TM45/TM48"),
    5: ("CLAIRIERE_BASSIN_VUE", "clairière du bassin d'eau pure : 1ère fois TM49 (soin), ensuite TM52 (flèches)"),
    6: ("CLAIRIERE_GEANT_VUE", "clairière du Géant : 1ère fois TM55, ensuite TM62/TM63 (selon la Cape)"),
    7: ("COLLINE_BATAILLE_VUE", "colline de la bataille Orques/Elfes : 1ère fois TM67, ensuite TM71"),
    8: ("TOUR_SORCIER_VUE", "île de la tour du Sorcier déjà visitée (1ère visite TM72 ; ensuite selon pierre/pendentif)"),
    9: ("CLAIRIERE_TRONC_VUE", "clairière au tronc creux : 1ère fois TM86, ensuite TM91"),
    10: ("CLAIRIERE_LOUVE_VUE", "clairière de la Louve et du Druide : 1ère fois TM93, ensuite M100/M101/TM99"),
    11: ("FORET_NORD_REPARCOURUE", "alternance des deux versions de la remontée de la forêt vers le Nord (M110 puis M111)"),
    24: ("MARAIS_ALTERNANCE", "BASCULE à chaque passage dans le marais (M105) : alterne les deux variantes M106/M107 et M108/M109"),
    25: ("SORCIER_RENCONTRE", "on est entré dans la tour et vu le Sorcier (conditionne le retour : pierre ou pas)"),
    26: ("PIERRE_NOIRE_DECOUVERTE", "pierre noire ovoïde déjà trouvée sur l'homme mort (qu'on l'ait prise ou enterrée)"),
    27: ("ORQUES_TUES", "les 3 Orques ont été tués (pendentif pris ou laissé) : la clairière devient M31b"),
    28: ("VOLEUR_TUE", "le Voleur a été tué (Cape fouillée, prise ou laissée) : plus de combat au retour"),
    29: ("POTION_DRUIDE", "écailles de dragon remises au Druide : immunité contre le Mal ; sans elle, le chemin du Temple mène à la mort (M116)"),
    30: ("DRUIDE_RENCONTRE", "le Druide a déjà été rencontré (1ère rencontre faite)"),
    31: ("OURS_COMBATTU", "l'Ours du tronc creux a déjà été combattu (TM89 -> TM90 ; ensuite TM92)"),
}


def evn(n):
    return 'evenement %d "%s"' % (n, EVT[n][0]) if n in EVT else 'evenement %d' % n

ROUTINE_TITRES = {'1bb78': 'NOUVELLE PARTIE', '1bb9a': 'QUITTER',
                  '1bc3a': "FIN DE PARTIE / MORT : page 'Vallée de la Mort'",
                  '1bc06': 'FIN DU JEU : AFFICHE LE CODE DU CONCOURS'}



# Logique du jeu (scenes, routines) decodee depuis un dump memoire. Ne pas modifier.
LOGIC = json.loads(r'''{"scenes":[{"nom":"TFin","adr":93548,"liens":[["@","1bb78"],["@","1bb9a"],null,null,null],"vie":0},{"nom":"TC1","adr":93606,"liens":[["R",2],null,null,null,null],"vie":0},{"nom":"TC2","adr":93664,"liens":[["R",3],["R",4],null,null,null],"vie":0},{"nom":"TC3","adr":93722,"liens":[["R",4],null,null,null,null],"vie":0},{"nom":"TC4","adr":93780,"liens":[["R",5],null,null,null,null],"vie":0},{"nom":"TC5","adr":93838,"liens":[["@","1bb5e"],null,null,null,null],"vie":0},{"nom":"TC6","adr":93896,"liens":[["R",7],null,null,null,null],"vie":28},{"nom":"TL1","adr":93954,"liens":[["R",8],["R",12],["R",9],null,null],"vie":0},{"nom":"TL2","adr":94012,"liens":[["@","1bc3a"],null,null,null,null],"vie":0},{"nom":"TL3","adr":94070,"liens":[["R",11],["R",10],null,null,null],"vie":0},{"nom":"TL4","adr":94128,"liens":[["@","1bc3a"],null,null,null,null],"vie":0},{"nom":"TL5","adr":94186,"liens":[["R",13],null,null,null,null],"vie":0},{"nom":"TL6","adr":94244,"liens":[["R",13],null,null,null,null],"vie":0},{"nom":"TL7","adr":94302,"liens":[["R",14],null,null,null,null],"vie":-2},{"nom":"TL7a","adr":94360,"liens":[["R",15],["R",16],["R",18],["R",17],["R",19]],"vie":0},{"nom":"TL8","adr":94418,"liens":[["@","1ba96"],["R",21],null,null,null],"vie":0},{"nom":"TL9","adr":94476,"liens":[["@","1ba96"],["R",21],null,null,null],"vie":0},{"nom":"TL10","adr":94534,"liens":[["R",22],null,null,null,null],"vie":0},{"nom":"TL11","adr":94592,"liens":[["R",23],["R",27],["R",28],null,null],"vie":0},{"nom":"TL12","adr":94650,"liens":[["@","1ba96"],null,null,null,null],"vie":0},{"nom":"TL13","adr":94708,"liens":[["R",26],null,null,null,null],"vie":0},{"nom":"TL14","adr":94766,"liens":[["@","1ba84"],null,null,null,null],"vie":-2},{"nom":"TL15","adr":94824,"liens":[["R",24],["R",25],null,null,null],"vie":0},{"nom":"TL16","adr":94882,"liens":[["R",8],null,null,null,null],"vie":0},{"nom":"TL17","adr":94940,"liens":[["@","1ba84"],null,null,null,null],"vie":-1},{"nom":"TL18","adr":94998,"liens":[["@","1bad8"],["@","1bae8"],null,null,null],"vie":0},{"nom":"TL19","adr":95056,"liens":[["@","1bb46"],null,null,null,null],"vie":0},{"nom":"TL27","adr":95114,"liens":[["R",29],null,null,null,null],"vie":0},{"nom":"TL28","adr":95172,"liens":[["R",29],null,null,null,null],"vie":0},{"nom":"L28a","adr":95230,"liens":[["@","1baf8"],null,null,null,null],"vie":0},{"nom":"TL29","adr":95288,"liens":[["R",31],["R",32],["R",33],null,null],"vie":0},{"nom":"L29a","adr":95346,"liens":[["@","1bc3a"],null,null,null,null],"vie":0},{"nom":"L29b","adr":95404,"liens":[["@","1bac8"],["@","1bac8"],null,null,null],"vie":-6},{"nom":"L29c","adr":95462,"liens":[["@","1bb08"],null,null,null,null],"vie":-4},{"nom":"TL30","adr":95520,"liens":[["R",37],["R",36],null,null,null],"vie":0},{"nom":"TL34","adr":95578,"liens":[["@","1bab8"],null,null,null,null],"vie":2},{"nom":"L34a","adr":95636,"liens":[["R",37],null,null,null,null],"vie":0},{"nom":"TL35","adr":95694,"liens":[["@","1bb16"],["@","1bb26"],["@","1bb36"],null,null],"vie":-1},{"nom":"TL36","adr":95752,"liens":[["R",41],null,null,null,null],"vie":-1},{"nom":"TL37","adr":95810,"liens":[["R",38],null,null,null,null],"vie":-2},{"nom":"TL38","adr":95868,"liens":[["@","1baa8"],null,null,null,null],"vie":0},{"nom":"TM1","adr":95926,"liens":[["@","1bc7a"],["R",67],["R",43],["R",42],null],"vie":0},{"nom":"TM2","adr":95984,"liens":[["R",43],null,null,null,null],"vie":0},{"nom":"TM3","adr":96042,"liens":[["@","1bc3a"],null,null,null,null],"vie":0},{"nom":"TM4","adr":96100,"liens":[["R",45],["R",50],["R",48],null,null],"vie":0},{"nom":"TM5","adr":96158,"liens":[["R",46],["R",47],null,null,null],"vie":0},{"nom":"TM6","adr":96216,"liens":[["R",48],["R",49],null,null,null],"vie":-2},{"nom":"TM7","adr":96274,"liens":[["R",48],null,null,null,null],"vie":0},{"nom":"TM8","adr":96332,"liens":[["@","1b74a"],["@","1b756"],null,null,null],"vie":1},{"nom":"TM9","adr":96390,"liens":[["R",41],["R",52],["@","1bd18"],null,null],"vie":0},{"nom":"TM10","adr":96448,"liens":[["@","1b768"],null,null,null,null],"vie":-4},{"nom":"TM11","adr":96506,"liens":[["@","1b782"],null,null,null,null],"vie":0},{"nom":"TM12","adr":96564,"liens":[["R",67],["@","1bc7a"],["@","1bc94"],null,null],"vie":-2},{"nom":"TM13","adr":96622,"liens":[["R",60],["R",54],null,null,null],"vie":0},{"nom":"TM14","adr":96680,"liens":[["R",55],["@","1b9cc"],["R",57],["R",64],null],"vie":0},{"nom":"TM15","adr":96738,"liens":[["R",59],["R",56],["R",57],null,null],"vie":-2},{"nom":"TM16","adr":96796,"liens":[["@","1bc3a"],null,null,null,null],"vie":0},{"nom":"TM17","adr":96854,"liens":[["@","1bc3a"],null,null,null,null],"vie":0},{"nom":"TM18","adr":96912,"liens":[["@","1b7a0"],null,null,null,null],"vie":0},{"nom":"TM19","adr":96970,"liens":[["@","1bd18"],null,null,null,null],"vie":0},{"nom":"TM20","adr":97028,"liens":[["R",61],["R",55],["R",63],["R",64],["R",57]],"vie":0},{"nom":"TM21","adr":97086,"liens":[["R",59],["R",62],["R",63],null,null],"vie":0},{"nom":"M21c","adr":97144,"liens":[["@","1bc3a"],null,null,null,null],"vie":0},{"nom":"TM22","adr":97202,"liens":[["R",55],["@","1b9cc"],["R",57],["R",64],null],"vie":0},{"nom":"TM23","adr":97260,"liens":[["@","1bd18"],null,null,null,null],"vie":0},{"nom":"TM24","adr":97318,"liens":[["@","1bc94"],["R",66],["@","1bcd6"],null,null],"vie":0},{"nom":"TM25","adr":97376,"liens":[["R",65],["@","1bea2"],["R",156],["@","1be46"],null],"vie":-1},{"nom":"TM26","adr":97434,"liens":[["R",52],["R",41],["R",68],null,null],"vie":0},{"nom":"TM27","adr":97492,"liens":[["R",69],null,null,null,null],"vie":0},{"nom":"TM28","adr":97550,"liens":[["R",97],["R",70],null,null,null],"vie":0},{"nom":"M28a","adr":97608,"liens":[["@","1bc94"],null,null,null,null],"vie":-2},{"nom":"TM29","adr":97666,"liens":[["R",72],["R",73],null,null,null],"vie":-1},{"nom":"TM30","adr":97724,"liens":[["@","1b7b2"],["@","1b7be"],null,null,null],"vie":-1},{"nom":"TM31","adr":97782,"liens":[["R",65],["R",52],["R",156],null,null],"vie":0},{"nom":"M31a","adr":97840,"liens":[["R",72],null,null,null,null],"vie":0},{"nom":"M31b","adr":97898,"liens":[["R",73],null,null,null,null],"vie":0},{"nom":"TM32","adr":97956,"liens":[["R",79],["R",80],null,null,null],"vie":0},{"nom":"TM33","adr":98014,"liens":[["R",99],null,null,null,null],"vie":-2},{"nom":"TM34","adr":98072,"liens":[["R",77],["@","1bd7c"],null,null,null],"vie":0},{"nom":"TM35","adr":98130,"liens":[["@","1bc3a"],null,null,null,null],"vie":0},{"nom":"TM36","adr":98188,"liens":[["@","1bd7c"],null,null,null,null],"vie":-2},{"nom":"TM37","adr":98246,"liens":[["R",82],["R",83],null,null,null],"vie":0},{"nom":"TM38","adr":98304,"liens":[["@","1b7d0"],["@","1b7dc"],null,null,null],"vie":0},{"nom":"TM39","adr":98362,"liens":[["R",65],["@","1be46"],["@","1bd18"],null,null],"vie":0},{"nom":"TM40","adr":98420,"liens":[["R",83],null,null,null,null],"vie":0},{"nom":"TM41","adr":98478,"liens":[["R",83],["@","1b7d0"],null,null,null],"vie":0},{"nom":"TM42","adr":98536,"liens":[["@","1bd7c"],["@","1bdae"],["@","1be64"],null,null],"vie":0},{"nom":"TM43","adr":98594,"liens":[["R",88],null,null,null,null],"vie":-4},{"nom":"TM44","adr":98652,"liens":[["R",53],["@","1bcd6"],["@","1bc7a"],null,null],"vie":0},{"nom":"TM45","adr":98710,"liens":[["R",90],["R",88],null,null,null],"vie":0},{"nom":"TM46","adr":98768,"liens":[["R",88],null,null,null,null],"vie":-4},{"nom":"TM47","adr":98826,"liens":[["@","1b7ee"],["R",88],null,null,null],"vie":0},{"nom":"TM48","adr":98884,"liens":[["R",88],["@","1b7ee"],null,null,null],"vie":0},{"nom":"TM49","adr":98942,"liens":[["@","1be46"],["R",95],["R",94],null,null],"vie":0},{"nom":"TM50","adr":99000,"liens":[["@","1be46"],["R",95],null,null,null],"vie":0},{"nom":"TM51","adr":99058,"liens":[["@","1be46"],null,null,null,null],"vie":6},{"nom":"TM52","adr":99116,"liens":[["@","1be46"],null,null,null,null],"vie":0},{"nom":"TM53","adr":99174,"liens":[["R",98],null,null,null,null],"vie":0},{"nom":"TM54","adr":99232,"liens":[["R",156],["@","1bdcc"],null,null,null],"vie":0},{"nom":"TM55","adr":99290,"liens":[["R",100],["R",101],null,null,null],"vie":0},{"nom":"TM56","adr":99348,"liens":[["@","1b800"],null,null,null,null],"vie":0},{"nom":"TM57","adr":99406,"liens":[["R",102],["R",103],null,null,null],"vie":-4},{"nom":"TM58","adr":99464,"liens":[["@","1bc3a"],null,null,null,null],"vie":0},{"nom":"TM59","adr":99522,"liens":[["R",156],["R",86],["@","1bcbc"],["@","1bea2"],null],"vie":0},{"nom":"TM60","adr":99580,"liens":[["@","1b81e"],null,null,null,null],"vie":0},{"nom":"TM61","adr":99638,"liens":[["R",103],null,null,null,null],"vie":0},{"nom":"TM62","adr":99696,"liens":[["R",103],null,null,null,null],"vie":0},{"nom":"TM63","adr":99754,"liens":[["@","1b800"],null,null,null,null],"vie":0},{"nom":"TM64","adr":99812,"liens":[["R",103],null,null,null,null],"vie":0},{"nom":"TM65","adr":99870,"liens":[["R",103],null,null,null,null],"vie":0},{"nom":"TM66","adr":99928,"liens":[["@","1b860"],["R",103],null,null,null],"vie":0},{"nom":"M66a","adr":99986,"liens":[["R",103],null,null,null,null],"vie":0},{"nom":"TM67","adr":100044,"liens":[["R",113],["R",114],["R",115],["R",116],null],"vie":0},{"nom":"TM68","adr":100102,"liens":[["@","1bc3a"],null,null,null,null],"vie":0},{"nom":"TM69","adr":100160,"liens":[["@","1bc3a"],null,null,null,null],"vie":0},{"nom":"TM70","adr":100218,"liens":[["R",86],null,null,null,null],"vie":0},{"nom":"TM70","adr":100276,"liens":[["R",163],null,null,null,null],"vie":0},{"nom":"TM71","adr":100334,"liens":[["R",86],["R",163],null,null,null],"vie":0},{"nom":"TM72","adr":100392,"liens":[["@","1b872"],["R",125],["R",98],null,null],"vie":0},{"nom":"M72b","adr":100450,"liens":[["@","1b872"],["R",125],["R",98],null,null],"vie":0},{"nom":"TM73","adr":100508,"liens":[["R",123],["R",122],["R",121],null,null],"vie":0},{"nom":"TM74","adr":100566,"liens":[["@","1bc3a"],null,null,null,null],"vie":0},{"nom":"TM75","adr":100624,"liens":[["@","1bc3a"],null,null,null,null],"vie":0},{"nom":"TM76","adr":100682,"liens":[["@","1bc3a"],null,null,null,null],"vie":0},{"nom":"TM77","adr":100740,"liens":[["@","1b8ba"],null,null,null,null],"vie":0},{"nom":"TM78","adr":100798,"liens":[["R",126],["R",127],null,null,null],"vie":0},{"nom":"TM79","adr":100856,"liens":[["@","1bc3a"],null,null,null,null],"vie":0},{"nom":"TM80","adr":100914,"liens":[["@","1bc3a"],null,null,null,null],"vie":0},{"nom":"TM81","adr":100972,"liens":[["@","1b89c"],null,null,null,null],"vie":0},{"nom":"TM82","adr":101030,"liens":[["R",98],null,null,null,null],"vie":0},{"nom":"TM83","adr":101088,"liens":[["@","1bc3a"],null,null,null,null],"vie":0},{"nom":"TM84","adr":101146,"liens":[["R",98],null,null,null,null],"vie":0},{"nom":"TM85","adr":101204,"liens":[["R",98],null,null,null,null],"vie":0},{"nom":"M85a","adr":101262,"liens":[["@","1bc3a"],null,null,null,null],"vie":0},{"nom":"M85b","adr":101320,"liens":[["@","1b8d0"],null,null,null,null],"vie":0},{"nom":"TM86","adr":101378,"liens":[["R",138],["R",136],["R",137],null,null],"vie":0},{"nom":"TM87","adr":101436,"liens":[["R",138],["R",137],null,null,null],"vie":2},{"nom":"TM88","adr":101494,"liens":[["@","1bcd6"],["R",66],["@","1bd5e"],null,null],"vie":0},{"nom":"TM89","adr":101552,"liens":[["R",137],["@","1b900"],null,null,null],"vie":0},{"nom":"TM90","adr":101610,"liens":[["R",137],null,null,null,null],"vie":-4},{"nom":"TM91","adr":101668,"liens":[["@","1b8e2"],["R",137],null,null,null],"vie":0},{"nom":"TM92","adr":101726,"liens":[["R",137],null,null,null,null],"vie":0},{"nom":"TM93","adr":101784,"liens":[["R",153],["@","1b998"],["R",143],null,null],"vie":0},{"nom":"TM94","adr":101842,"liens":[["R",86],["@","1bea2"],null,null,null],"vie":0},{"nom":"TM95","adr":101900,"liens":[["@","1b912"],null,null,null,null],"vie":0},{"nom":"TM96","adr":101958,"liens":[["@","1bc3a"],null,null,null,null],"vie":0},{"nom":"TM97","adr":102016,"liens":[["@","1b9aa"],["@","1b9bc"],null,null,null],"vie":0},{"nom":"TM98","adr":102074,"liens":[["@","1bea2"],["R",86],null,null,null],"vie":4},{"nom":"TM99","adr":102132,"liens":[["@","1bea2"],["R",86],null,null,null],"vie":0},{"nom":"M100","adr":102190,"liens":[["R",153],["@","1b998"],["R",143],null,null],"vie":0},{"nom":"M101","adr":102248,"liens":[["@","1bea2"],["R",86],["@","1b954"],null,null],"vie":0},{"nom":"M102","adr":102306,"liens":[["@","1b9bc"],["@","1b9aa"],null,null,null],"vie":0},{"nom":"M103","adr":102364,"liens":[["@","1bc3a"],null,null,null,null],"vie":0},{"nom":"M104","adr":102422,"liens":[["@","1bc3a"],null,null,null,null],"vie":0},{"nom":"104a","adr":102480,"liens":[["@","1bc3a"],null,null,null,null],"vie":0},{"nom":"104b","adr":102538,"liens":[["@","1b9ea"],["@","1b9fa"],null,null,null],"vie":0},{"nom":"M105","adr":102596,"liens":[["@","1ba0c"],["@","1ba2a"],null,null,null],"vie":0},{"nom":"M106","adr":102654,"liens":[["R",66],["R",98],["@","1bc94"],["@","1bd7c"],null],"vie":0},{"nom":"M107","adr":102712,"liens":[["R",66],["R",98],["@","1bc94"],["@","1bd7c"],null],"vie":-1},{"nom":"M108","adr":102770,"liens":[["R",66],["R",98],["@","1bc94"],["@","1bd7c"],null],"vie":-1},{"nom":"M109","adr":102828,"liens":[["R",66],["R",98],["@","1bc94"],["@","1bd7c"],null],"vie":0},{"nom":"M110","adr":102886,"liens":[["@","1be64"],["R",66],["@","1bd7c"],null,null],"vie":0},{"nom":"M111","adr":102944,"liens":[["@","1be64"],["R",66],["@","1bd7c"],null,null],"vie":0},{"nom":"M112","adr":103002,"liens":[["@","1ba48"],["@","1bdae"],null,null,null],"vie":0},{"nom":"M113","adr":103060,"liens":[["@","1ba66"],["@","1bdae"],null,null,null],"vie":0},{"nom":"M114","adr":103118,"liens":[["@","1bc3a"],null,null,null,null],"vie":0},{"nom":"M115","adr":103176,"liens":[["R",210],null,null,null,null],"vie":0},{"nom":"M116","adr":103234,"liens":[["@","1bc3a"],null,null,null,null],"vie":0},{"nom":"TT1","adr":103292,"liens":[["R",177],["R",174],null,null,null],"vie":0},{"nom":"TT2","adr":103350,"liens":[["R",184],["R",188],["R",185],null,null],"vie":0},{"nom":"TT3","adr":103408,"liens":[["@","1bc3a"],null,null,null,null],"vie":0},{"nom":"TT4","adr":103466,"liens":[["R",169],null,null,null,null],"vie":0},{"nom":"TT6","adr":103524,"liens":[["R",192],["R",178],null,null,null],"vie":0},{"nom":"TT7","adr":103582,"liens":[["R",205],null,null,null,null],"vie":0},{"nom":"TT9","adr":103640,"liens":[["R",185],["@","1bbc8"],["R",169],null,null],"vie":0},{"nom":"TT10","adr":103698,"liens":[["@","1b68e"],["@","1b6a0"],["@","1b6b2"],["R",173],null],"vie":0},{"nom":"TT11","adr":103756,"liens":[["R",185],["R",172],["@","1b580"],["@","1b592"],["@","1b5a4"]],"vie":0},{"nom":"TT13","adr":103814,"liens":[["R",179],["R",174],null,null,null],"vie":-2},{"nom":"TT16","adr":103872,"liens":[["R",192],null,null,null,null],"vie":-4},{"nom":"TT17","adr":103930,"liens":[["R",177],["R",174],null,null,null],"vie":-4},{"nom":"TT18","adr":103988,"liens":[["R",176],["R",172],null,null,null],"vie":0},{"nom":"T18a","adr":104046,"liens":[["@","1bba4"],["R",172],null,null,null],"vie":0},{"nom":"T18b","adr":104104,"liens":[["@","1bbb6"],["R",172],null,null,null],"vie":0},{"nom":"T18c","adr":104162,"liens":[["R",172],["R",169],null,null,null],"vie":0},{"nom":"TT19","adr":104220,"liens":[["R",191],null,null,null,null],"vie":-10},{"nom":"TT20","adr":104278,"liens":[["@","1bbc8"],["R",169],null,null,null],"vie":0},{"nom":"TT21","adr":104336,"liens":[["@","1b738"],["R",189],["@","1b5ba"],null,null],"vie":0},{"nom":"TT22","adr":104394,"liens":[["R",189],["@","1b5ba"],null,null,null],"vie":0},{"nom":"TT23","adr":104452,"liens":[["@","1b6e6"],null,null,null,null],"vie":6},{"nom":"TT24","adr":104510,"liens":[["@","1bc3a"],null,null,null,null],"vie":0},{"nom":"TT25","adr":104568,"liens":[["R",199],["R",211],["@","1b6f8"],null,null],"vie":0},{"nom":"TT26","adr":104626,"liens":[["R",199],["R",190],null,null,null],"vie":0},{"nom":"TT27","adr":104684,"liens":[["R",185],null,null,null,null],"vie":0},{"nom":"TT28","adr":104742,"liens":[["R",189],["@","1b738"],null,null,null],"vie":0},{"nom":"TT29","adr":104800,"liens":[["R",189],null,null,null,null],"vie":0},{"nom":"TT30","adr":104858,"liens":[["R",204],["R",200],null,null,null],"vie":0},{"nom":"TT31","adr":104916,"liens":[["R",190],["R",211],null,null,null],"vie":0},{"nom":"TT32","adr":104974,"liens":[["@","1b618"],["@","1b622"],["@","1b62c"],["R",206],null],"vie":0},{"nom":"TT33","adr":105032,"liens":[["@","1b64c"],null,null,null,null],"vie":0},{"nom":"TT34","adr":105090,"liens":[["R",203],["R",196],null,null,null],"vie":0},{"nom":"TT36","adr":105148,"liens":[["@","1b64c"],["R",204],null,null,null],"vie":0},{"nom":"TT38","adr":105206,"liens":[["R",197],["R",208],null,null,null],"vie":0},{"nom":"TT39","adr":105264,"liens":[null,null,null,null,null],"vie":0},{"nom":"TT40","adr":105322,"liens":[["R",196],null,null,null,null],"vie":0},{"nom":"TT41","adr":105380,"liens":[["@","1b5f0"],["@","1b606"],null,null,null],"vie":0},{"nom":"TT42","adr":105438,"liens":[["@","1bc06"],null,null,null,null],"vie":0},{"nom":"TT43","adr":105496,"liens":[["@","1b64c"],["R",198],null,null,null],"vie":0},{"nom":"TT44","adr":105554,"liens":[["R",195],null,null,null,null],"vie":0},{"nom":"TT43","adr":105612,"liens":[["@","1b64c"],["R",197],null,null,null],"vie":0},{"nom":"TT46","adr":105670,"liens":[["@","1b5d2"],["@","1b5da"],["@","1b5d2"],["@","1b5d2"],null],"vie":0},{"nom":"TT47","adr":105728,"liens":[["@","1b6c8"],null,null,null,null],"vie":0},{"nom":"TT48","adr":105786,"liens":[["@","1bc3a"],null,null,null,null],"vie":0}],"routines":{"1b580":[["toujours","ACTIVE FlagsW bit 3",171]],"1b592":[["toujours","ACTIVE FlagsW bit 4",171]],"1b5a4":[["toujours","ACTIVE FlagsW bit 3, ACTIVE FlagsW bit 4",171]],"1b5ba":[["(FlagsW & 0x18) != 24","EFFACE FlagsW bit 3, EFFACE FlagsW bit 4",189],["(FlagsW & 0x18) == 24","aucun effet",209]],"1b5d2":[["toujours","EFFACE FlagsW bit 3, EFFACE FlagsW bit 4",189]],"1b5da":[["toujours","EFFACE FlagsW bit 3, EFFACE FlagsW bit 4",207]],"1b5f0":[["toujours","ACTIVE FlagsW bit 5, ACTIVE FlagsW bit 6",201]],"1b606":[["toujours","ACTIVE FlagsW bit 5",201]],"1b618":[["toujours","BASCULE FlagsW bit 0, redessine l'inventaire \u00e0 l'\u00e9cran (appel $0970 puis copie blitter)","RESTER"]],"1b622":[["toujours","BASCULE FlagsW bit 1, redessine l'inventaire \u00e0 l'\u00e9cran (appel $0970 puis copie blitter)","RESTER"]],"1b62c":[["toujours","BASCULE FlagsW bit 2, redessine l'inventaire \u00e0 l'\u00e9cran (appel $0970 puis copie blitter)","RESTER"]],"1b64c":[["FlagsW bit 6 inactif ET (FlagsW & 0x7) != 4 ET (FlagsW & 0x7) != 5","aucun effet",170],["FlagsW bit 6 inactif ET (FlagsW & 0x7) != 4 ET (FlagsW & 0x7) == 5","aucun effet",175],["FlagsW bit 6 inactif ET (FlagsW & 0x7) == 4","aucun effet",173],["FlagsW bit 6 actif","aucun effet",170]],"1b68e":[["toujours","EFFACE FlagsW bit 0",173]],"1b6a0":[["toujours","EFFACE FlagsW bit 2",170]],"1b6b2":[["toujours","EFFACE FlagsW bit 0, EFFACE FlagsW bit 2",170]],"1b6c8":[["toujours","EFFACE FlagsW bit 7, EFFACE FlagsW bit 8, EFFACE FlagsW bit 9, EFFACE FlagsW bit 14",168]],"1b6e6":[["toujours","ACTIVE FlagsW bit 15",184]],"1b6f8":[["(FlagsW & 0x18) == 0 ET FlagsW bit 15 actif","aucun effet",193],["(FlagsW & 0x18) == 0 ET FlagsW bit 15 inactif","aucun effet",194],["(FlagsW & 0x18) != 0 ET FlagsW bit 15 actif","aucun effet",186],["(FlagsW & 0x18) != 0 ET FlagsW bit 15 inactif","aucun effet",187]],"1b738":[["toujours","EFFACE FlagsW bit 15",189]],"1b74a":[["toujours","ACTIVE FlagsW bit 7, ACTIVE FlagsL bit 28",49]],"1b756":[["toujours","ACTIVE FlagsL bit 28",49]],"1b768":[["toujours","EFFACE FlagsW bit 8, EFFACE FlagsW bit 9, Compteur := 0",49]],"1b782":[["FlagsL bit 28 inactif","aucun effet",48],["FlagsL bit 28 actif","aucun effet",49]],"1b7a0":[["toujours","ACTIVE FlagsW bit 9",64]],"1b7b2":[["toujours","ACTIVE FlagsW bit 8, ACTIVE FlagsL bit 27",73]],"1b7be":[["toujours","ACTIVE FlagsL bit 27",73]],"1b7d0":[["toujours","ACTIVE FlagsW bit 13, ACTIVE FlagsL bit 26",83]],"1b7dc":[["toujours","ACTIVE FlagsL bit 26",83]],"1b7ee":[["toujours","EFFACE FlagsW bit 8",88]],"1b800":[["FlagsW bit 7 actif","aucun effet",104],["FlagsW bit 7 inactif","aucun effet",105]],"1b81e":[["FlagsW bit 8 inactif ET FlagsW bit 13 inactif ET FlagsW bit 9 inactif","EFFACE FlagsW bit 7",111],["FlagsW bit 8 inactif ET FlagsW bit 13 inactif ET FlagsW bit 9 actif","EFFACE FlagsW bit 7",109],["FlagsW bit 8 inactif ET FlagsW bit 13 actif","EFFACE FlagsW bit 7",108],["FlagsW bit 8 actif","EFFACE FlagsW bit 7",110]],"1b860":[["toujours","EFFACE FlagsW bit 8",103]],"1b872":[["FlagsW bit 8 actif","ACTIVE FlagsL bit 25",120],["FlagsW bit 8 inactif","ACTIVE FlagsL bit 25",128]],"1b89c":[["FlagsW bit 13 actif","aucun effet",124],["FlagsW bit 13 inactif","aucun effet",129]],"1b8ba":[["toujours","EFFACE FlagsW bit 13, ACTIVE FlagsW bit 14",98]],"1b8d0":[["toujours","EFFACE FlagsW bit 8",98]],"1b8e2":[["FlagsL bit 31 actif","aucun effet",141],["FlagsL bit 31 inactif","aucun effet",138]],"1b900":[["toujours","ACTIVE FlagsL bit 31",139]],"1b912":[["FlagsW bit 8 inactif ET FlagsW bit 9 inactif","ACTIVE FlagsL bit 30",147],["FlagsW bit 8 inactif ET FlagsW bit 9 actif","ACTIVE FlagsL bit 30, ACTIVE FlagsL bit 29",146],["FlagsW bit 8 actif","ACTIVE FlagsL bit 30",145]],"1b954":[["FlagsW bit 9 actif ET FlagsW bit 8 actif","ACTIVE FlagsL bit 29",155],["FlagsW bit 9 actif ET FlagsW bit 8 inactif","ACTIVE FlagsL bit 29",151],["FlagsW bit 9 inactif ET FlagsW bit 8 actif","aucun effet",154],["FlagsW bit 9 inactif ET FlagsW bit 8 inactif","aucun effet",152]],"1b998":[["toujours","EFFACE FlagsW bit 10",144]],"1b9aa":[["toujours","EFFACE FlagsW bit 9",86]],"1b9bc":[["FlagsL bit 11 actif","EFFACE FlagsW bit 9, ACTIVE FlagsL bit 11",162],["FlagsL bit 11 inactif","EFFACE FlagsW bit 9, ACTIVE FlagsL bit 11",161]],"1b9cc":[["FlagsW bit 9 actif","aucun effet",56],["FlagsW bit 9 inactif","aucun effet",58]],"1b9ea":[["FlagsL bit 11 actif","EFFACE FlagsW bit 8, ACTIVE FlagsL bit 11",162],["FlagsL bit 11 inactif","EFFACE FlagsW bit 8, ACTIVE FlagsL bit 11",161]],"1b9fa":[["toujours","EFFACE FlagsW bit 8",86]],"1ba0c":[["FlagsL bit 24 inactif","BASCULE FlagsL bit 24",158],["FlagsL bit 24 actif","BASCULE FlagsL bit 24",157]],"1ba2a":[["FlagsL bit 24 inactif","BASCULE FlagsL bit 24",160],["FlagsL bit 24 actif","BASCULE FlagsL bit 24",159]],"1ba48":[["FlagsW bit 14 actif","aucun effet",164],["FlagsW bit 14 inactif","aucun effet",165]],"1ba66":[["FlagsL bit 29 actif","aucun effet",166],["FlagsL bit 29 inactif","aucun effet",167]],"1ba84":[["toujours","EFFACE FlagsW bit 11",26]],"1ba96":[["toujours","EFFACE FlagsW bit 11",20]],"1baa8":[["toujours","Compteur -= 1",41]],"1bab8":[["toujours","Compteur -= 4",41]],"1bac8":[["toujours","Compteur := 1",40]],"1bad8":[["toujours","Compteur := 4",35]],"1bae8":[["toujours","Compteur := 4",37]],"1baf8":[["toujours","Compteur := 4",30]],"1bb08":[["toujours","Compteur := 0",41]],"1bb16":[["toujours","Compteur -= 2",38]],"1bb26":[["toujours","Compteur -= 2",39]],"1bb36":[["toujours","Compteur -= 2",40]],"1bb46":[["toujours","Compteur := 3, ACTIVE FlagsW bit 11",34]],"1bb5e":[["toujours","ACTIVE FlagsW bit 10, ACTIVE FlagsW bit 11, ACTIVE FlagsW bit 12",6]],"1bb78":[["toujours","flag_eb0 := faux, Vie := 28, FlagsW := 7168, Compteur := 0, FlagsL := 0",7]],"1bb9a":[["toujours","flag_quitter := vrai, flag_6af5 := faux","(aucune)"]],"1bba4":[["toujours","ACTIVE FlagsW bit 4",171]],"1bbb6":[["toujours","ACTIVE FlagsW bit 3",171]],"1bbc8":[["(FlagsW & 0x18) != 0 ET (FlagsW & 0x18) != 24 ET (FlagsW & 0x18) != 8","aucun effet",182],["(FlagsW & 0x18) != 0 ET (FlagsW & 0x18) != 24 ET (FlagsW & 0x18) == 8","aucun effet",181],["(FlagsW & 0x18) != 0 ET (FlagsW & 0x18) == 24","aucun effet",183],["(FlagsW & 0x18) == 0","aucun effet",180]],"1bc3a":[["toujours","flag_eb0 := vrai, Vie := 0, FlagsW := 0, Compteur := 0",0]],"1bc7a":[["FlagsL bit 0 actif","ACTIVE FlagsL bit 0",51],["FlagsL bit 0 inactif","ACTIVE FlagsL bit 0",44]],"1bc94":[["FlagsL bit 1 actif ET FlagsL bit 27 actif","ACTIVE FlagsL bit 1",75],["FlagsL bit 1 actif ET FlagsL bit 27 inactif","ACTIVE FlagsL bit 1",74],["FlagsL bit 1 inactif","ACTIVE FlagsL bit 1",71]],"1bcbc":[["FlagsL bit 2 actif","ACTIVE FlagsL bit 2",78],["FlagsL bit 2 inactif","ACTIVE FlagsL bit 2",76]],"1bcd6":[["FlagsL bit 3 actif ET FlagsL bit 26 actif ET (FlagsW & 0x6000) != 0","ACTIVE FlagsL bit 3",84],["FlagsL bit 3 actif ET FlagsL bit 26 actif ET (FlagsW & 0x6000) == 0","ACTIVE FlagsL bit 3",85],["FlagsL bit 3 actif ET FlagsL bit 26 inactif","ACTIVE FlagsL bit 3",81],["FlagsL bit 3 inactif","ACTIVE FlagsL bit 3",81]],"1bd18":[["FlagsL bit 4 actif ET FlagsW bit 8 actif","ACTIVE FlagsL bit 4",92],["FlagsL bit 4 actif ET FlagsW bit 8 inactif","ACTIVE FlagsL bit 4",89],["FlagsL bit 4 inactif ET FlagsW bit 8 actif","ACTIVE FlagsL bit 4",91],["FlagsL bit 4 inactif ET FlagsW bit 8 inactif","ACTIVE FlagsL bit 4",87]],"1bd5e":[["FlagsL bit 5 actif","ACTIVE FlagsL bit 5",96],["FlagsL bit 5 inactif","ACTIVE FlagsL bit 5",93]],"1bd7c":[["FlagsL bit 6 actif ET FlagsW bit 7 actif","ACTIVE FlagsL bit 6",107],["FlagsL bit 6 actif ET FlagsW bit 7 inactif","ACTIVE FlagsL bit 6",106],["FlagsL bit 6 inactif","ACTIVE FlagsL bit 6",99]],"1bdae":[["FlagsL bit 7 actif","ACTIVE FlagsL bit 7",117],["FlagsL bit 7 inactif","ACTIVE FlagsL bit 7",112]],"1bdcc":[["FlagsL bit 8 actif ET FlagsL bit 25 actif ET FlagsW bit 14 inactif ET FlagsW bit 13 actif ET FlagsW bit 8 actif","ACTIVE FlagsL bit 8, EFFACE FlagsW bit 13, ACTIVE FlagsW bit 14",134],["FlagsL bit 8 actif ET FlagsL bit 25 actif ET FlagsW bit 14 inactif ET FlagsW bit 13 actif ET FlagsW bit 8 inactif","ACTIVE FlagsL bit 8, EFFACE FlagsW bit 13, ACTIVE FlagsW bit 14",131],["FlagsL bit 8 actif ET FlagsL bit 25 actif ET FlagsW bit 14 inactif ET FlagsW bit 13 inactif ET FlagsW bit 8 actif","ACTIVE FlagsL bit 8",133],["FlagsL bit 8 actif ET FlagsL bit 25 actif ET FlagsW bit 14 inactif ET FlagsW bit 13 inactif ET FlagsW bit 8 inactif","ACTIVE FlagsL bit 8",130],["FlagsL bit 8 actif ET FlagsL bit 25 actif ET FlagsW bit 14 actif","ACTIVE FlagsL bit 8",132],["FlagsL bit 8 actif ET FlagsL bit 25 inactif","ACTIVE FlagsL bit 8",119],["FlagsL bit 8 inactif","ACTIVE FlagsL bit 8",118]],"1be46":[["FlagsL bit 9 actif","ACTIVE FlagsL bit 9",140],["FlagsL bit 9 inactif","ACTIVE FlagsL bit 9",135]],"1be64":[["FlagsL bit 10 actif ET FlagsL bit 29 inactif ET FlagsL bit 30 actif","ACTIVE FlagsL bit 10",150],["FlagsL bit 10 actif ET FlagsL bit 29 inactif ET FlagsL bit 30 inactif","ACTIVE FlagsL bit 10",149],["FlagsL bit 10 actif ET FlagsL bit 29 actif","ACTIVE FlagsL bit 10",148],["FlagsL bit 10 inactif","ACTIVE FlagsL bit 10",142]],"1bea2":[["FlagsL bit 11 actif","ACTIVE FlagsL bit 11",162],["FlagsL bit 11 inactif","ACTIVE FlagsL bit 11",161]]}}''')


def xor(octets, cle):
    return bytes(b ^ cle for b in octets)


def analyser_texte(flux):
    """[(colonne, ligne, octets)] ou None si le flux n'est pas du texte."""
    lignes, i = [], 0
    while i < len(flux):
        if flux[i] == FIN_BLOC:
            break
        if i + 2 > len(flux):
            return None
        col, lig = flux[i], flux[i + 1]
        if col >= 80 or lig >= 64:       # garde-fou : mauvaise cle
            return None
        i += 2
        deb = i
        while i < len(flux) and flux[i] not in (FIN_LIGNE, FIN_BLOC):
            i += 1
        lignes.append((col, lig, flux[deb:i]))
        if i < len(flux) and flux[i] == FIN_LIGNE:
            i += 1
    if not lignes:
        return None
    tot = sum(len(t) for _, _, t in lignes)
    ok = sum(1 for _, _, t in lignes for b in t if 0x20 <= b < 0x7F or b >= 0xA0)
    return lignes if tot and ok / tot >= 0.9 else None


def decoder_bloc(octets):
    for cle in CLES:
        flux = xor(octets, cle)
        lignes = analyser_texte(flux)
        if lignes is not None:
            return cle, flux, lignes
    return None, xor(octets, CLES[0]), None


def texte(octets):
    return "".join(chr(b) if 0x20 <= b < 0x7F or b >= 0xA0 else "\\x%02x" % b
                   for b in octets)


def hexdump(octets, larg=16):
    out = []
    for o in range(0, len(octets), larg):
        m = octets[o:o + larg]
        out.append("%06x  %-*s  %s" % (o, larg * 3, " ".join("%02x" % b for b in m),
                                       "".join(chr(b) if 32 <= b < 127 else "." for b in m)))
    return "\n".join(out)


# ==========================================================================
# 2) Traduction de la logique en langage lisible
# ==========================================================================
def objn(n):
    return 'objet %d "%s"' % (n, OBJ.get(n, '?'))


def bits_of(mask):
    return [b for b in range(16) if mask >> b & 1]


def render_mask_group(mask, atoms):
    bs = bits_of(mask)

    def conj(v):
        if len(bs) >= 3:
            have = [OBJ[b] for b in bs if v >> b & 1]
            return 'possède exactement {%s} parmi (%s)' % (
                ', '.join(have) if have else 'rien', ', '.join(OBJ[b] for b in bs))
        return ' ET '.join(('POSSEDE ' if v >> b & 1 else 'NON POSSEDE ') + objn(b) for b in bs)
    tous = [sum(bit << b for bit, b in zip(c, bs)) for c in itertools.product([0, 1], repeat=len(bs))]
    permis = [v for v in tous if all((v == val) == eq for eq, val in atoms)]
    if len(permis) == 1:
        return conj(permis[0])
    if len(permis) > len(tous) // 2:
        exclus = [v for v in tous if v not in permis]
        if exclus == [0]:
            return 'POSSEDE au moins un parmi : ' + ', '.join(objn(b) for b in bs)
        return ' ET '.join('PAS (%s)' % conj(v) for v in exclus)
    return ' OU '.join('(%s)' % conj(v) for v in permis)


def render_cond(c):
    if c == 'toujours':
        return None
    wb, lb, groupes, parts = {}, {}, collections.OrderedDict(), []
    for a in c.split(' ET '):
        a = a.strip()
        m = re.fullmatch(r'Flags([WL]) bit (\d+) (actif|inactif)', a)
        if m:
            (wb if m.group(1) == 'W' else lb)[int(m.group(2))] = (m.group(3) == 'actif')
            continue
        m = re.fullmatch(r'\(FlagsW & 0x([0-9a-f]+)\) (==|!=) (\d+)', a)
        if m:
            groupes.setdefault(int(m.group(1), 16), []).append((m.group(2) == '==', int(m.group(3))))
            continue
        raise ValueError('condition inconnue : ' + a)
    for b, v in sorted(wb.items()):
        parts.append(('POSSEDE ' if v else 'NON POSSEDE ') + objn(b))
    for b, v in sorted(lb.items()):
        parts.append(('DEJAVU' if v else 'PAS DEJAVU') + ' ' + evn(b))
    for mask, atoms in groupes.items():
        parts.append(render_mask_group(mask, atoms))
    return ' ET '.join(parts)


def render_actions(eff):
    out = []
    for a in [x.strip() for x in eff.split(', ')]:
        if a in ('aucun effet', ''):
            continue
        m = re.fullmatch(r'ACTIVE FlagsW bit (\d+)', a)
        if m: out.append('PRENDS ' + objn(int(m.group(1)))); continue
        m = re.fullmatch(r'EFFACE FlagsW bit (\d+)', a)
        if m: out.append('POSE ' + objn(int(m.group(1))) + '   (perdu / utilisé)'); continue
        m = re.fullmatch(r'BASCULE FlagsW bit (\d+)', a)
        if m: out.append('BASCULE ' + objn(int(m.group(1))) + '   (prendre <-> poser)'); continue
        m = re.fullmatch(r'ACTIVE FlagsL bit (\d+)', a)
        if m: out.append('DEJAVU ' + evn(int(m.group(1)))); continue
        m = re.fullmatch(r'BASCULE FlagsL bit (\d+)', a)
        if m: out.append('BASCULE ' + evn(int(m.group(1))) + '   (DEJAVU <-> pas DEJAVU)'); continue
        m = re.fullmatch(r'Compteur -= (\d+)', a)
        if m: out.append('OR -%s' % m.group(1)); continue
        m = re.fullmatch(r'Compteur := (\d+)', a)
        if m:
            out.append('OR = %s' % m.group(1) + ('   (remise à zéro)' if m.group(1) == '0'
                                                  else "   (fixe le total, ne s'ajoute pas)"))
            continue
        m = re.fullmatch(r'Vie := (\d+)', a)
        if m: out.append('VIE = %s' % m.group(1)); continue
        if a == 'FlagsW := 7168':
            out.append('OBJETS = ' + ', '.join('"%s"' % OBJ[b] for b in (10, 11, 12))); continue
        if a == 'FlagsW := 0':
            out.append('OBJETS = aucun (tout est perdu)'); continue
        if a == 'FlagsL := 0':
            out.append('EVENEMENTS = tous remis à zéro (plus aucun DEJAVU)'); continue
        if a == 'CODE_FINAL': out.append("DÉCHIFFRE (NOT) ET AFFICHE LE CODE DU CONCOURS"); continue
        if a.startswith('flag_eb0 := vrai'): out.append('(drapeau interne "mort" = vrai)'); continue
        if a.startswith('flag_eb0 := faux'): out.append('(drapeau interne "mort" = faux)'); continue
        if a.startswith('flag_quitter := vrai'): out.append('QUITTER LE JEU'); continue
        if a.startswith('flag_6af5'): continue
        if a.startswith('redessine'): out.append("REDESSINE l'inventaire à l'écran"); continue
        out.append('??? ' + a)
    return out



def choix_du_bloc(lignes):
    """{numero: texte du choix} d'apres les lignes decodees."""
    L = [re.sub(r'@\d', '', texte(t)) for _, _, t in lignes]
    out = {}
    for i, x in enumerate(L):
        m = re.match(r'\s*< ?F(\d+) ?>\s*(.*)', x)
        if m:
            t, j = m.group(2).strip(), i + 1
            while j < len(L) and L[j].startswith('  ') and not re.match(r'\s*< ?F\d', L[j]):
                t += ' ' + L[j].strip()
                j += 1
            out[int(m.group(1))] = t
    return out



# ==========================================================================
# 3) Scenes, liens, routines
# ==========================================================================
RT0 = LOGIC['routines']
SC = LOGIC['scenes']                      # [{nom, adr, liens[5], vie}]
RT = LOGIC['routines']                    # {adresse_hex: [[cond, effets, dest]]}
RT['1bc06'] = [['toujours', 'CODE_FINAL', next(i for i, s in enumerate(SC) if s['nom'] == 'TT39')]]
_cnt = collections.Counter(s['nom'] for s in SC)
_occ, LAB = collections.Counter(), []
for s in SC:
    _occ[s['nom']] += 1
    LAB.append(s['nom'] if _cnt[s['nom']] == 1 else '%s#%d' % (s['nom'], _occ[s['nom']]))


def lab(j):
    return LAB[j]


def render_branches(branches, ind):
    L = []
    for cond, eff, dest in branches:
        c = render_cond(cond)
        acts = render_actions(eff)
        if dest == 'RESTER':
            d = 'RESTER sur la scène courante'
        elif isinstance(dest, str):
            d = None
        else:
            d = 'ALLER ' + lab(dest)
        pre = ind
        if c:
            L.append(ind + 'SI ' + c + ' :')
            pre = ind + '    '
        for a in acts:
            L.append(pre + a)
        if d:
            L.append(pre + '-> ' + d)
        elif not acts:
            L.append(pre + '(aucun effet)')
    return L


def dests_lien(l):
    """Scenes pouvant suivre un lien (scene directe ou via routine)."""
    if l is None:
        return []
    if l[0] == 'R':
        return [l[1]]
    return sorted({b[2] for b in RT[l[1]] if isinstance(b[2], int)})


def predecesseurs():
    pred = collections.defaultdict(list)
    for i, s in enumerate(SC):
        for k, l in enumerate(s['liens']):
            if l is None:
                continue
            for d in dests_lien(l):
                pred[d].append('%s/F%d%s' % (lab(i), k + 1, ' (via routine 0x%s)' % l[1] if l[0] == '@' else ''))
    return pred


def atteignables(departs):
    vus, pile = set(departs), list(departs)
    while pile:
        n = pile.pop()
        for l in SC[n]['liens']:
            for d in dests_lien(l):
                if d not in vus:
                    vus.add(d)
                    pile.append(d)
    return vus


def lire_index(donnees):
    debut = struct.unpack(">I", donnees[0:4])[0]
    return [(donnees[p:p + 4].strip(b"\0").decode("latin-1"),
             struct.unpack(">I", donnees[p + 4:p + 8])[0]) for p in range(4, debut, 8)]


def bloc(donnees, debut, fins):
    fin = min([f for f in fins if f > debut] + [len(donnees)])
    return donnees[debut:fin]


def entete(O, titre, adr, cle, lignes, extra):
    O += ["", "#" * 78, "# " + titre]
    if cle is None:
        O.append("# DÉCHIFFREMENT : aucune clé connue ne donne du texte (dump brut ci-dessous)")
    elif cle == 0xAA:
        O.append("# DÉCHIFFREMENT : XOR 0x55 puis NOT   [BLOC PROTÉGÉ]")
    else:
        O.append("# DÉCHIFFREMENT : XOR 0x55")
    O += extra
    if lignes:
        cols = sorted({c for c, _, _ in lignes})
        O.append("# AFFICHAGE     : colonne %s, lignes %d à %d" % (
            '/'.join(map(str, cols)), min(l for _, l, _ in lignes), max(l for _, l, _ in lignes)))
    O.append("#" * 78)


def extraire(chemin_data, sortie):
    """Ecrit le descriptif complet du jeu dans le fichier `sortie`."""
    donnees = open(chemin_data, "rb").read()
    index = lire_index(donnees)
    debut = {}
    for n, s in index:
        debut.setdefault(n, s)
    fins = sorted({s for _, s in index})
    R = RT
    pred = predecesseurs()

    O = ["=" * 78, "HEROS (Amiga, 1994, Olivier Thil / DREAM) : DESCRIPTIF COMPLET DU JEU", "=" * 78, "",
         "Fichier produit par extract_heros.py (v2) à partir de DataHeros seul.", "",
         "VOCABULAIRE",
         '  PRENDS objet N "nom"   l\'objet entre dans l\'inventaire',
         '  POSE objet N "nom"     l\'objet quitte l\'inventaire (perdu, donné, utilisé)',
         '  BASCULE objet N        prendre si on ne l\'a pas, poser sinon',
         '  DEJAVU evenement N     marque l\'événement N (sert à changer de scène au passage suivant)',
         "  OR +k / -k / = k       pièces d'or (variable interne « Compteur »)",
         "  VIE +k / -k / = k      points de vie ; ceux des scènes sont appliqués À L'ARRIVÉE dans la scène",
         "  SI ... :               les SI d'une même routine s'excluent : le premier vrai est appliqué",
         "  -> ALLER X             scène suivante",
         "  @0 @1 @2 ...           codes de couleur dans le texte (@1 = retour à la couleur normale)", "",
         "OBJETS"] + ["  objet %2d : %s" % (b, OBJ[b]) for b in range(16)]
    O += ["", "ÉVÉNEMENTS (DEJAVU) : drapeaux 32 bits « déjà vu / déjà fait » (noms déduits des scènes, non écrits dans le jeu)"]
    O += ["  evenement %2d %-26s %s" % (n, v[0], v[1]) for n, v in sorted(EVT.items())]
    O += ["", "NOTES DE LECTURE",
          "  - OR : petit compteur de pièces (Compteur), affiché en 4 cases en haut de l'écran. Aucun test ne le lit :",
          "    le jeu ne compare jamais l'or. Les cas « pas assez d'argent » sont codés en dur dans l'enchaînement des scènes.",
          "    L'or n'est jamais ajouté : il est FIXÉ à la valeur reçue (OR = 4, OR = 3, OR = 1) puis diminué (OR -k)",
          "    à la sortie de l'auberge ; il est remis à 0 par le vol (TM10), la mort et la nouvelle partie. Voir TABLE DE L'OR.",
          "  - VIE : à chaque arrivée dans une scène, le jeu ajoute son delta à la Vie (Vie += delta).",
          "    Si la Vie devient NÉGATIVE (< 0) : mort immédiate (page « Vallée de la Mort »). Vie = 0 : encore vivant.",
          "    Aucun plafond n'est appliqué à la valeur ; la jauge à l'écran n'a que 32 cases.",
          "    Départ : l'introduction (scène TC6) ajoute +28 ; 'nouvelle partie' après une mort remet Vie = 28 (et saute l'intro).",
          "    Aucune routine ne modifie la Vie autrement (hors nouvelle partie et mort). Voir la table VIE en fin de fichier.",
          "  - Nouvelle partie -> scène %s (introduction)." % lab(RT['1bb78'][0][2]),
          "  - Les noms de scènes sont ceux du jeu (nom d'enregistrement = nom du bloc de texte affiché).",
          "  - Les noms d'objet marqués d'un ? sont déduits avec moins de certitude.", ""]

    utilises = set()
    stats = collections.Counter()
    for i, s in enumerate(SC):
        nom = s['nom']
        deb = debut[nom]
        utilises.add(deb)
        cle, flux, lignes = decoder_bloc(bloc(donnees, deb, fins))
        extra = ["# TEXTE         : bloc nommé '%s' (offset 0x%x)" % (nom, deb)]
        extra.append("# À L'ARRIVÉE   : " + ("VIE %+d%s" % (s['vie'], "   (mort si la Vie passe sous 0)" if s['vie'] < 0 else "")
                                             if s['vie'] else "aucun effet automatique"))
        extra.append("# ATTEINT DEPUIS: " + (", ".join(pred[i]) if i in pred else
                                             "(aucun lien F ; voir notes)"))
        for n in NOTES.get(nom, []):
            extra.append("# " + n if n.startswith("*") else "# *** " + n)
        if cle == 0xAA:
            stats['protégés'] += 1
        stats['scènes'] += 1
        entete(O, "SCÈNE %s   (enregistrement n°%d, mémoire 0x%x)" % (lab(i), i, s['adr']), deb, cle, lignes, extra)
        if lignes is None:
            O.append(hexdump(flux))
            continue
        for _, _, t in lignes:
            O.append("    " + texte(t))
        txt = choix_du_bloc(lignes)
        O += ["", "  --- CHOIX ET ACTIONS ---"]
        liens = [(k + 1, l) for k, l in enumerate(s['liens']) if l]
        if not liens:
            O.append("  (aucun choix : scène sans sortie)")
        for k, l in liens:
            O.append("  F%d « %s »" % (k, txt.get(k, '(texte du choix absent)')))
            if l[0] == '@':
                tit = ROUTINE_TITRES.get(l[1])
                O.append("      [routine 0x%s%s]" % (l[1], ' : ' + tit if tit else ''))
                O += render_branches(R[l[1]], "      ")
            else:
                O.append("      -> ALLER " + lab(l[1]))
        stats['choix'] += len(liens)

    # blocs que aucune scene n'affiche
    O += ["", "=" * 78, "BLOCS NON AFFICHÉS PAR UNE SCÈNE", "=" * 78]
    for n, d in index:
        if d in utilises:
            continue
        cle, flux, lignes = decoder_bloc(bloc(donnees, d, fins))
        extra = ["# TEXTE         : bloc nommé '%s' (offset 0x%x)" % (n, d)]
        for t in NOTES.get(n, ["Bloc affiché par le programme lui-même (non relié à une scène)."]):
            extra.append("# " + t if t.startswith("*") else "# *** " + t)
        entete(O, "BLOC %s" % n, d, cle, lignes, extra)
        if lignes is None:
            O.append(hexdump(flux))
        else:
            for _, _, t in lignes:
                O.append("    " + texte(t))
        stats['hors scène'] += 1

    # table de la vie
    O += ["", "=" * 78, "TABLE DE LA VIE (delta appliqué à chaque arrivée dans la scène)", "=" * 78]
    gains = [(i, s['vie']) for i, s in enumerate(SC) if s['vie'] > 0]
    pertes = [(i, s['vie']) for i, s in enumerate(SC) if s['vie'] < 0]
    O.append("Gains  (%d scènes) : %s" % (len(gains), ', '.join('%s %+d' % (lab(i), v) for i, v in gains)))
    O.append("Pertes (%d scènes) : %s" % (len(pertes), ', '.join('%s %+d' % (lab(i), v) for i, v in pertes)))
    O.append("Total des pertes si on passait par toutes : %d ; total des gains : %+d" % (
        sum(v for _, v in pertes), sum(v for _, v in gains if SC[_]['nom'] != 'TC6')))
    O.append("Vie de départ : 28 (TC6 +28 à l'introduction, ou 'nouvelle partie' après une mort).")

    # table de l'or
    O += ["", "=" * 78, "TABLE DE L'OR (compteur de pièces, jamais testé par le jeu)", "=" * 78]
    for i, sc in enumerate(SC):
        for k, l in enumerate(sc['liens']):
            if l and l[0] == '@' and any('Compteur' in b[1] for b in RT[l[1]]) and l[1] not in ('1bb78', '1bc3a'):
                eff = [a for b in RT[l[1]] for a in render_actions(b[1]) if a.startswith('OR')]
                dest = ', '.join(lab(d) for d in dests_lien(l))
                O.append("  %s/F%d : %s   -> ALLER %s" % (lab(i), k + 1, ' ; '.join(eff), dest))
    O.append("  (nouvelle partie, mort : OR = 0.  Le vol de TM10 remet aussi OR = 0.)")

    # anomalies
    vus = atteignables([1, RT['1bb78'][0][2]])
    nonvus = [lab(i) for i in range(len(SC)) if i not in vus]
    O += ["", "=" * 78, "ANOMALIES ET POINTS NON RÉSOLUS", "=" * 78,
          "Scènes atteignables depuis l'écran titre (F1 nouvelle partie) : %d sur %d" % (len(vus), len(SC)),
          "Scènes sans chemin depuis le début : " + (', '.join(nonvus) or 'aucune'),
          "Blocs protégés (clé 0xAA) : %d" % stats['protégés']]
    open(sortie, "w", encoding="utf-8").write("\n".join(O) + "\n")
    print("%d scènes (dont %d protégée), %d choix, %d blocs hors scène -> %s" % (
        stats['scènes'], stats['protégés'], stats['choix'], stats['hors scène'], sortie))




# ==========================================================================
# 3b) LE SON : musique du jeu, SANS bibliotheque externe (ni pygame, ni numpy)
# ==========================================================================
# La musique d'origine est un module de type ProTracker a 3 voies : 15 echantillons 8 bits,
# 30 patterns de 64 lignes, et pour chaque scene une "liste" de patterns (avec une position de
# bouclage). Tout est integre ci-dessous (SON_B64, ~70 Ko, compresse), extrait d'un dump memoire.
#
# Le programme synthetise lui-meme le son (22050 Hz, 16 bits, mono) puis le confie au lecteur
# audio du systeme :
#   Linux   : aplay, paplay, pw-play, play (sox) ou ffplay, en flux continu (stdin)
#   macOS   : afplay (fichier WAV temporaire)
#   Windows : winsound (module standard de Python)
# S'il n'y a aucun lecteur, ou pas de sortie son (machine sans carte son, serveur...), le jeu
# continue en silence sans le moindre message d'erreur.   Option --no-sound : aucun son.
FREQ = 22050                  # frequence de sortie
PAULA = 3546895               # horloge de l'Amiga (PAL) : frequence d'un echantillon = PAULA / periode
TICK = FREQ // 50             # le lecteur d'origine tourne a 50 Hz ; 6 ticks par ligne
VITESSE = 6
GAIN = 2                      # le module d'origine est discret : on double (le melange ne depasse jamais ~50000, borne ensuite)


class Module:
    """Les donnees musicales + le synthetiseur (generateur de blocs PCM)."""

    def __init__(self):
        brut = zlib.decompress(base64.b64decode(SON_B64))
        i = brut.index(b'\0')
        meta = json.loads(brut[:i])
        corps = brut[i + 1:]
        self.listes = meta['listes']          # [[patterns..., position de bouclage], ...]
        self.scene = meta['scene']            # pour chaque scene (indice de SC) : numero de liste
        self.intro = meta['intro']            # liste jouee pendant les pages d'introduction
        self.ech, p = [], 0
        for ln, vol, ls, ll in meta['ech']:
            octets = corps[p:p + 2 * ln]
            p += 2 * ln
            data = [b - 256 if b > 127 else b for b in octets]
            fin = 2 * (ls + ll) if ll > 1 else 2 * ln          # echantillon bouclant ou non
            self.ech.append((data, min(vol & 0x7F, 64), 2 * ls, max(2 * ll, 0), min(fin, 2 * ln)))
        self.patterns = corps[p:p + 30 * 768]

    def blocs(self, num_liste, debut=0, une_fois=False):
        """Generateur de blocs PCM (bytes, 1 tick = 20 ms chacun) pour une liste de patterns.
        debut : position de depart dans la liste ; une_fois : s'arrete a la fin de la liste
        (sinon boucle indefiniment sur la position de bouclage)."""
        ordre, boucle = self.listes[num_liste]
        voies = [{'smp': None, 'pos': 0.0, 'per': 0, 'vol': 0, 'fin': 0, 'ls': 0, 'll': 0, 'num': 0}
                 for _ in range(3)]
        pos_ordre = debut
        big = sys.byteorder == 'big'
        while True:
            if pos_ordre >= len(ordre):
                if une_fois:
                    return
                pos_ordre = boucle if boucle < len(ordre) else 0
            base = ordre[pos_ordre] * 768
            for ligne in range(64):
                cellules = []
                for v in range(3):
                    o = base + ligne * 12 + v * 4
                    b0, b1, b2, b3 = self.patterns[o:o + 4]
                    cellules.append(((b0 & 0xF0) | (b2 >> 4), ((b0 & 15) << 8) | b1, b2 & 15, b3))
                for tick in range(VITESSE):
                    mix = [0] * TICK
                    for v in range(3):
                        vo = voies[v]
                        samp, per, eff, par = cellules[v]
                        if tick == 0:                       # debut de ligne : nouvelle note ?
                            if samp:
                                vo['num'] = samp
                                if samp - 1 < len(self.ech):
                                    vo['vol'] = self.ech[samp - 1][1]
                            if per:
                                vo['per'] = per
                                if 0 < vo['num'] <= len(self.ech):
                                    d_, vol_, ls_, ll_, fin_ = self.ech[vo['num'] - 1]
                                    vo['smp'], vo['pos'] = d_, 0.0
                                    vo['fin'], vo['ls'], vo['ll'] = fin_, ls_, ll_
                            if eff == 0xC:
                                vo['vol'] = min(par, 64)
                        elif eff == 1 and vo['per']:        # glissando vers l'aigu
                            vo['per'] = max(113, vo['per'] - par)
                        elif eff == 2 and vo['per']:        # glissando vers le grave
                            vo['per'] = min(856, vo['per'] + par)
                        smp, per_, vol = vo['smp'], vo['per'], vo['vol']
                        if smp is None or not per_ or not vol:
                            continue
                        pas = PAULA / per_ / FREQ
                        vol *= GAIN
                        pos, fin, ls, ll = vo['pos'], vo['fin'], vo['ls'], vo['ll']
                        for i in range(TICK):
                            if pos >= fin:
                                if ll > 2:
                                    pos -= ll
                                else:
                                    vo['smp'] = None
                                    break
                            mix[i] += smp[int(pos)] * vol
                            pos += pas
                        vo['pos'] = pos
                    bloc = array.array('h', [m if -32768 <= m <= 32767 else (32767 if m > 0 else -32768)
                                             for m in mix])
                    if big:
                        bloc.byteswap()
                    yield bloc.tobytes()
            pos_ordre += 1


def ecrire_wav(chemin, octets):
    with wave.open(chemin, 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(FREQ)
        w.writeframes(octets)


def rendre(module, num_liste, debut=0):
    """Une passe complete de la liste (a partir de 'debut') -> octets PCM."""
    return b''.join(module.blocs(num_liste, debut, une_fois=True))


def commandes_lecteur():
    """Lecteurs capables de lire du PCM brut (16 bits, mono) sur leur entree standard."""
    c = []
    if shutil.which('aplay'):
        c.append(['aplay', '-q', '-t', 'raw', '-f', 'S16_LE', '-r', str(FREQ), '-c', '1', '-'])
    if shutil.which('paplay'):
        c.append(['paplay', '--raw', '--format=s16le', '--rate=%d' % FREQ, '--channels=1'])
    if shutil.which('pw-play'):
        c.append(['pw-play', '--rate', str(FREQ), '--channels', '1', '--format', 's16', '-'])
    if shutil.which('play'):
        c.append(['play', '-q', '-t', 'raw', '-r', str(FREQ), '-e', 'signed', '-b', '16', '-c', '1', '-'])
    if shutil.which('ffplay'):
        c.append(['ffplay', '-nodisp', '-autoexit', '-loglevel', 'quiet',
                  '-f', 's16le', '-ar', str(FREQ), '-ac', '1', '-i', '-'])
    return c


def tuer(proc):
    """Arrete un lecteur audio proprement (sans 'Broken pipe' a la fermeture du tampon)."""
    try:
        proc.kill()
    except Exception:
        pass
    for f in (proc.stdin,):
        try:
            if f is not None:
                f.close()                  # le tampon non ecrit peut lever BrokenPipe : on l'ignore
        except Exception:
            pass
    try:
        proc.wait(0.5)
    except Exception:
        pass


class Son:
    """Lecture de la musique en arriere-plan. Ne leve JAMAIS d'exception vers le jeu :
    au moindre probleme (pas de lecteur, pas de carte son...) le son se desactive."""

    def __init__(self):
        self.actif = False          # le son est-il autorise (option --no-sound, touche M) ?
        self.indisponible = False   # aucun moyen de jouer du son sur cette machine
        self.module = None
        self.liste = None           # liste en cours de lecture
        self.fil = None
        self.arret = threading.Event()
        self.proc = None
        self.cmd_ok = None          # commande de lecteur qui a fonctionne
        self.verrou = threading.Lock()
        atexit.register(self.arreter)

    # ---- API utilisee par le jeu
    def activer(self):
        self.actif = True

    def scene(self, indice):
        """Appele a chaque affichage d'une scene. Ne relance pas si la liste est deja en cours."""
        try:
            if self.actif and not self.indisponible:
                self._charger()
                self.jouer(self.module.scene[indice])
        except Exception:
            self._panne()

    def intro(self):
        try:
            if self.actif and not self.indisponible:
                self._charger()
                self.jouer(self.module.intro)
        except Exception:
            self._panne()

    def basculer(self):
        """Touche M. Retourne un message a afficher."""
        if self.indisponible:
            return "Pas de sortie son disponible sur cette machine."
        if self.actif:
            self.actif = False
            self.arreter()
            return 'Son coupé (M pour le remettre).'
        self.actif = True
        return 'Son activé.'

    # ---- interne
    def _charger(self):
        if self.module is None:
            self.module = Module()

    def _panne(self):
        self.indisponible = True
        self.arreter()

    def jouer(self, num_liste):
        with self.verrou:
            if num_liste == self.liste and self.fil is not None and self.fil.is_alive():
                return
            self._arreter_interne()
            self.liste = num_liste
            self.arret = threading.Event()
            self.fil = threading.Thread(target=self._travail, args=(num_liste, self.arret), daemon=True)
            self.fil.start()

    def arreter(self):
        try:
            with self.verrou:
                self._arreter_interne()
        except Exception:
            pass

    def _arreter_interne(self):
        self.arret.set()
        p, self.proc = self.proc, None
        if p is not None:
            tuer(p)
        if os.name == 'nt':
            try:
                import winsound
                winsound.PlaySound(None, winsound.SND_PURGE)
            except Exception:
                pass
        self.liste = None
        fil, self.fil = self.fil, None
        if fil is not None and fil is not threading.current_thread():
            fil.join(0.5)

    def _travail(self, num_liste, arret):
        try:
            if os.name == 'nt':
                self._lire_fichiers(num_liste, arret, windows=True)
            elif sys.platform == 'darwin' and shutil.which('afplay'):
                self._lire_fichiers(num_liste, arret, windows=False)
            else:
                self._lire_flux(num_liste, arret)
        except Exception:
            self._panne_si_actuel(arret)

    def _panne_si_actuel(self, arret):
        if not arret.is_set():
            self.indisponible = True

    # -- Linux & co : flux PCM envoye a un lecteur externe
    def _lire_flux(self, num_liste, arret):
        cmds = [self.cmd_ok] if self.cmd_ok else commandes_lecteur()
        for cmd in cmds:
            try:
                proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                                        stderr=subprocess.DEVNULL)
            except OSError:
                continue
            gen = self.module.blocs(num_liste)
            tampon, debut = [], time.time()
            ok = True
            self.proc = proc
            try:
                for bloc in gen:
                    if arret.is_set():
                        ok = None
                        break
                    tampon.append(bloc)
                    if len(tampon) >= 10:                       # ecrit par 0,2 s
                        proc.stdin.write(b''.join(tampon))
                        proc.stdin.flush()
                        tampon = []
                        if self.cmd_ok is None and time.time() - debut < 1.0 and proc.poll() is not None:
                            ok = False                          # le lecteur est mort aussitot : pas de son
                            break
                        if self.cmd_ok is None and time.time() - debut > 0.3:
                            self.cmd_ok = cmd                   # il tient : on garde ce lecteur
            except (BrokenPipeError, OSError, ValueError):
                ok = None if arret.is_set() else (False if self.cmd_ok is None else None)
            finally:
                tuer(proc)
                if self.proc is proc:
                    self.proc = None
            if ok is None or arret.is_set():
                return
            if ok is False:
                continue                                        # essaie le lecteur suivant
        if not arret.is_set() and self.cmd_ok is None:
            self.indisponible = True                            # aucun lecteur n'a fonctionne

    # -- Windows / macOS : fichiers WAV (intro + boucle)
    def _lire_fichiers(self, num_liste, arret, windows):
        m = self.module
        boucle = m.listes[num_liste][1]
        premier = rendre(m, num_liste, 0)
        if arret.is_set():
            return
        suite = rendre(m, num_liste, boucle) if boucle else premier
        octets = premier
        while not arret.is_set():
            if windows:
                import winsound
                wav = io.BytesIO()
                with wave.open(wav, 'wb') as w:
                    w.setnchannels(1); w.setsampwidth(2); w.setframerate(FREQ)
                    w.writeframes(octets)
                t0 = time.time()
                winsound.PlaySound(wav.getvalue(), winsound.SND_MEMORY)      # bloque jusqu'a la fin
                if time.time() - t0 < 0.5 and not arret.is_set():
                    self.indisponible = True                # retour immediat : pas de sortie son
                    return
            else:
                fd, chemin = tempfile.mkstemp(suffix='.wav')
                os.close(fd)
                try:
                    ecrire_wav(chemin, octets)
                    proc = subprocess.Popen(['afplay', chemin], stdout=subprocess.DEVNULL,
                                            stderr=subprocess.DEVNULL)
                    self.proc = proc
                    t0 = time.time()
                    proc.wait()
                    if time.time() - t0 < 0.5 and not arret.is_set():
                        self.indisponible = True                # afplay a echoue aussitot
                        return
                finally:
                    try:
                        os.remove(chemin)
                    except OSError:
                        pass
            octets = suite                                  # ensuite on boucle sur la partie qui boucle


MOTEUR = Son()


def exporter_wav(code, chemin):
    """--wav SCENE FICHIER : ecrit la musique d'une scene (ou 'intro') dans un WAV, sans la jouer.
    Une passe complete suivie d'une passe de boucle."""
    m = Module()
    if code.lower() == 'intro':
        n = m.intro
    else:
        i = trouver_scene(code)
        if i is None:
            sys.exit('Scène inconnue : %s' % code)
        n = m.scene[i]
    boucle = m.listes[n][1]
    ecrire_wav(chemin, rendre(m, n, 0) + (rendre(m, n, boucle) if boucle else b''))
    print('%s : liste %d (patterns %s, boucle en position %d) -> %s'
          % (code, n, m.listes[n][0], boucle, chemin))


SON_B64 = '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'


# ==========================================================================
# 4) LE JEU EN MODE TEXTE
# ==========================================================================
IDX = {}
for _i, _s in enumerate(SC):
    IDX.setdefault(_s['nom'], _i)
VIE_MAX_BARRE = 32
VIE_DEPART = 28
OR_TRICHE_DEFAUT = 4     # l'or n'est jamais teste par le jeu : aucune valeur ne bloque ; 4 = maximum de l'affichage d'origine

# noms courts des objets pour la barre d'etat
OBJETS = {0: 'Serre-tête', 1: 'Bracelet de bronze', 2: "Anneau d'argent",
          3: 'Gemme rouge', 4: 'Gemme verte', 5: 'Clé',
          6: 'Bracelets ailés', 7: 'Cape Rouge', 8: 'Pendentif en Or',
          9: 'Écailles de dragon', 10: 'Nourriture', 11: 'Épée',
          12: 'Sac', 13: 'Pierre noire', 14: 'Deuxième pierre',
          15: 'Champignons'}

# Clavier AZERTY : la rangee des chiffres donne & é " ' ( - è _ ç sans Maj
CHIFFRES = {'&': 1, 'é': 2, '"': 3, "'": 4, '(': 5, '-': 6, 'è': 7, '_': 8, 'ç': 9,
            'É': 2, 'È': 7, 'Ç': 9}


class Textes:
    """Lit DataHeros : index (nom[4] + offset), puis blocs de texte codes."""

    def __init__(self, chemin):
        self.d = open(chemin, 'rb').read()
        index = lire_index(self.d)
        self.debut = {}
        for n, s in index:
            self.debut.setdefault(n, s)
        self.fins = sorted({s for _, s in index})
        self.cache = {}

    def lignes(self, nom):
        if nom not in self.cache:
            l = decoder_bloc(bloc(self.d, self.debut[nom], self.fins))[2] or []
            m = min([c for c, _, _ in l] or [0])        # on retire la marge d'ecran
            res, prec = [], None
            for col, lig, t in l:
                if prec is not None and lig - prec > 1:
                    res.append('')                       # ligne vide
                s = t.decode('latin-1').replace('\xad', '-')   # soulignement
                res.append(' ' * (col - m) + s)
                prec = lig
            self.cache[nom] = res
        return self.cache[nom]


def trouver_data(arg):
    """DataHeros : parametre --data, sinon dossier du programme, sinon dossier courant."""
    if arg:
        return arg
    for dossier in (os.path.dirname(os.path.abspath(__file__)), os.getcwd()):
        try:
            for nom in sorted(os.listdir(dossier)):
                if nom.lower().startswith('dataheros'):
                    return os.path.join(dossier, nom)
        except OSError:
            pass
    sys.exit("Fichier DataHeros introuvable : placez-le dans le même dossier que ce "
             "programme (ou utilisez l'option --data CHEMIN).")


def mettre_en_forme(lignes, ansi):
    """Codes de couleur du jeu : @1 = normal, @0 et @2 = texte en evidence (gras)."""
    gras, res = False, []
    for s in lignes:
        out = ''
        if ansi and gras:
            out += '\033[1m'
        for m in re.split(r'(@\d)', s):
            if re.fullmatch(r'@\d', m):
                gras = m[1] != '1'
                if ansi:
                    out += '\033[1m' if gras else '\033[0m'
            else:
                out += m
        if ansi:
            out += '\033[0m'
        res.append(out)
    return res


# -------------------------------------------------------------------- moteur
def _bit(v, n):
    return (v >> n) & 1


def cond_vraie(cond, W, L):
    for c in cond.split(' ET '):
        c = c.strip()
        if c == 'toujours':
            continue
        m = re.fullmatch(r'Flags([WL]) bit (\d+) (actif|inactif)', c)
        if m:
            v = W if m.group(1) == 'W' else L
            if bool(_bit(v, int(m.group(2)))) != (m.group(3) == 'actif'):
                return False
            continue
        m = re.fullmatch(r'\(FlagsW & (0x[0-9a-fA-F]+)\) (==|!=) (\d+)', c)
        if m:
            eq = (W & int(m.group(1), 16)) == int(m.group(3))
            if eq != (m.group(2) == '=='):
                return False
            continue
        raise ValueError('condition inconnue : ' + c)
    return True


def appliquer(eff, st):
    for e in eff.split(', '):
        e = e.strip()
        m = re.fullmatch(r'(ACTIVE|EFFACE|BASCULE) Flags([WL]) bit (\d+)', e)
        if m:
            cle = 'W' if m.group(2) == 'W' else 'L'
            b = 1 << int(m.group(3))
            if m.group(1) == 'ACTIVE':
                st[cle] |= b
            elif m.group(1) == 'EFFACE':
                st[cle] &= ~b
            else:
                st[cle] ^= b
            continue
        m = re.fullmatch(r'Compteur (-=|:=) (\d+)', e)
        if m:
            k = int(m.group(2))
            st['or'] = st['or'] - k if m.group(1) == '-=' else k
            continue
        m = re.fullmatch(r'(Vie|FlagsW|FlagsL) := (\d+)', e)
        if m:
            st[{'Vie': 'vie', 'FlagsW': 'W', 'FlagsL': 'L'}[m.group(1)]] = int(m.group(2))
            continue
        # 'aucun effet', 'redessine ...', CODE_FINAL, flag_... : sans objet ici


def nouvel_etat():
    return {'sc': IDX['TC1'], 'W': 0, 'L': 0, 'vie': 0, 'or': 0}


def arriver(st, dest):
    """Entre dans la scene dest : applique le delta de vie ; mort si Vie < 0."""
    st['sc'] = dest
    st['vie'] += SC[dest]['vie']
    if st['vie'] < 0:                      # routine de mort 0x1BC3A
        st['vie'], st['W'], st['or'] = 0, 0, 0
        st['sc'] = 0                       # page TFin (Vallee de la Mort)


def choix_valides(st):
    return [k + 1 for k, l in enumerate(SC[st['sc']]['liens']) if l]


def choisir(st, k):
    """Applique le choix Fk. Retourne 'quitter' si le jeu doit s'arreter, sinon None."""
    lien = SC[st['sc']]['liens'][k - 1]
    if lien[0] == 'R':
        arriver(st, lien[1])
        return None
    for cond, eff, dest in RT[lien[1]]:
        if cond_vraie(cond, st['W'], st['L']):
            appliquer(eff, st)
            if dest == '(aucune)':
                return 'quitter'
            if dest != 'RESTER':
                arriver(st, dest)
            return None
    return None


# ------------------------------------------------------------------ affichage
def barre_vie(v):
    n = max(0, min(v, VIE_MAX_BARRE))
    return '[' + '#' * n + '.' * (VIE_MAX_BARRE - n) + ']'


def objets_portes(W):
    return [OBJETS[b] for b in range(16) if _bit(W, b)]


def barre_etat(st):
    obj = objets_portes(st['W'])
    return ['-' * 72,
            ' Objets : ' + (', '.join(obj) if obj else '(rien)'),
            ' VIE : %3d %s' % (st['vie'], barre_vie(st['vie'])),
            ' OR  : %3d' % st['or'],
            '-' * 72]


def ecran(textes, st, message=''):
    s = SC[st['sc']]
    L = ['=' * 72, '  H E R O S   -   scène %s' % LAB[st['sc']], '=' * 72, '']
    L += ['  ' + t for t in mettre_en_forme(textes.lignes(s['nom']), sys.stdout.isatty())]
    if not choix_valides(st):
        L += ['', '  *** FIN DU JEU ***']
    L += [''] + barre_etat(st)
    L += [' Choisir : F1..F5   ou   & é " \' (   (= 1 2 3 4 5, sans Maj)',
          ' S sauver  C charger  B retour  T triche  M son  Q quitter']
    if message:
        L += [' >> ' + message]
    return '\n'.join(L)


def effacer():
    if sys.stdout.isatty():
        sys.stdout.write('\033[2J\033[H')


# --------------------------------------------------------------------- touches
def _touche_posix():
    import select
    import termios
    import tty
    fd = sys.stdin.fileno()
    ancien = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        b = os.read(fd, 32)                       # toute la sequence d'un coup
        if b == b'\x1b' and select.select([fd], [], [], 0.05)[0]:
            b += os.read(fd, 32)
        s = b.decode('utf-8', 'ignore')
        if s.startswith('\x1b'):
            table = {'OP': 'F1', 'OQ': 'F2', 'OR': 'F3', 'OS': 'F4', '[11~': 'F1',
                     '[12~': 'F2', '[13~': 'F3', '[14~': 'F4', '[15~': 'F5',
                     '[[A': 'F1', '[[B': 'F2', '[[C': 'F3', '[[D': 'F4', '[[E': 'F5',
                     '[P': 'F1', '[Q': 'F2', '[R': 'F3', '[S': 'F4'}
            return table.get(s[1:], 'ESC' if s == '\x1b' else '')
        return s[:1]
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, ancien)


def _touche_windows():
    import msvcrt
    c = msvcrt.getwch()
    if c in ('\x00', '\xe0'):
        return {';': 'F1', '<': 'F2', '=': 'F3', '>': 'F4', '?': 'F5'}.get(msvcrt.getwch(), '')
    return c


def lire_touche():
    """'F1'..'F5', 'ESC', 'CTRL' (Ctrl-C/D), ou le caractere tape ('' si touche inconnue)."""
    if not sys.stdin.isatty():           # entree redirigee : un ordre par ligne
        ligne = sys.stdin.readline()
        if ligne == '':
            return 'CTRL'
        c = ligne.strip()
        if c.upper() in ('ESC', 'ECHAP'):
            return 'ESC'
        return c[:2].upper() if re.fullmatch(r'[fF][1-5]', c) else c[:1]
    c = _touche_windows() if os.name == 'nt' else _touche_posix()
    if c in ('\x03', '\x04'):
        return 'CTRL'
    if c == '\x1b':
        return 'ESC'
    return c


def normaliser(c):
    """Touche -> numero de choix (int) ou lettre majuscule."""
    if re.fullmatch(r'F[1-5]', c):
        return int(c[1])
    if c in CHIFFRES:
        return CHIFFRES[c]
    if len(c) == 1 and c.isdigit():
        return int(c)
    return c.upper() if len(c) == 1 else c


def lire_ligne(invite):
    try:
        return input(invite).strip()
    except EOFError:
        return ''


# ----------------------------------------------------------------- sauvegarde
def fichier_slot(n):
    return 'heros_sauvegarde_%d.json' % n


def sauver(n, hist):
    with open(fichier_slot(n), 'w') as f:
        json.dump({'version': 1, 'historique': hist}, f)


def charger(n):
    with open(fichier_slot(n)) as f:
        d = json.load(f)
    hist = d['historique']
    for e in hist:
        assert set(e) == {'sc', 'W', 'L', 'vie', 'or'} and 0 <= e['sc'] < len(SC)
    assert hist
    return hist


def resume_slot(n):
    try:
        e = charger(n)[-1]
        return 'scène %s, Vie %d, Or %d' % (LAB[e['sc']], e['vie'], e['or'])
    except (OSError, ValueError, KeyError, AssertionError, TypeError):
        return '(vide)'


def demander_slot(action):
    print()
    for n in range(1, 10):
        print('  %s (touche %d) : %s' % ('&é"\'(-è_ç'[n - 1], n, resume_slot(n)))
    print(' %s : choisir l\'emplacement (touche & é " \' ( - è _ ç), autre touche = annuler' % action)
    sys.stdout.flush()
    c = normaliser(lire_touche())
    return c if isinstance(c, int) and 1 <= c <= 9 else None


# --------------------------------------------------------------------- triche
def trouver_scene(code):
    """'TM12' -> indice ; 'TM70#2' -> 2e scene de ce nom ; None si inconnue."""
    c = code.strip().upper()
    for i, l in enumerate(LAB):
        if l.upper() == c:
            return i
    for i, s in enumerate(SC):                      # nom partage : prend la 1ere
        if s['nom'].upper() == c:
            return i
    return None


def liste_scenes():
    codes = list(LAB)
    larg = max(len(c) for c in codes) + 2
    n = max(1, 72 // larg)
    return ['  ' + ''.join(c.ljust(larg) for c in codes[i:i + n]) for i in range(0, len(codes), n)]


def menu_objets(st):
    """Ajoute/enleve n'importe quel objet : touches A..P."""
    msg = ''
    while True:
        effacer()
        print('=' * 72 + '\n  TRICHE - OBJETS   (touche = prendre / poser)\n' + '=' * 72)
        for b in range(16):
            print('   %s  [%s] %s' % (chr(65 + b), 'X' if _bit(st['W'], b) else ' ', OBJETS[b]))
        print('\n  Attention : un inventaire "impossible" peut donner des scènes inattendues.')
        print('  Échap : retour au menu triche')
        if msg:
            print(' >> ' + msg)
        c = normaliser(lire_touche())
        if c in ('ESC', 'CTRL', 'T'):
            return
        if isinstance(c, str) and len(c) == 1 and 'A' <= c <= 'P':
            st['W'] ^= 1 << (ord(c) - 65)
            msg = '%s : %s' % (OBJETS[ord(c) - 65],
                               'pris' if _bit(st['W'], ord(c) - 65) else 'posé')
        else:
            msg = ''


def ecran_triche(textes, st):
    """Ecran de triche (touche T). Retourne le nouvel etat si modifie, sinon None."""
    nv, msg = dict(st), ''
    while True:
        effacer()
        print('=' * 72 + '\n  T R I C H E\n' + '=' * 72)
        print('  Scène actuelle : %s' % LAB[nv['sc']])
        print()
        print('\n'.join(barre_etat(nv)))
        print('  A  aller (se téléporter) à une scène à partir de son code')
        print('  L  liste des codes de scènes')
        print('  V  remettre la VIE à %d' % VIE_DEPART)
        print('  O  fixer l\'OR (conseil : %d ; l\'or n\'est jamais testé, rien ne bloque)' % OR_TRICHE_DEFAUT)
        print('  I  objets : ajouter / enlever')
        print('  Échap ou T : retour au jeu')
        if msg:
            print(' >> ' + msg)
        msg = ''
        c = normaliser(lire_touche())
        if c in ('ESC', 'CTRL', 'T'):
            return nv if nv != st else None
        if c == 'A':
            code = lire_ligne('  Code de la scène (ex. TL1, TM12, TT39 ; vide = annuler) : ')
            if code:
                i = trouver_scene(code)
                if i is None:
                    msg = 'Code inconnu : %s  (touche L pour la liste)' % code
                else:
                    nv['sc'] = i             # teleportation : pas de delta de vie
                    msg = 'Téléporté en %s' % LAB[i]
        elif c == 'L':
            print('\n' + '\n'.join(liste_scenes()))
            print('\n  (une touche pour continuer)')
            lire_touche()
        elif c == 'V':
            nv['vie'] = VIE_DEPART
            msg = 'Vie remise à %d' % VIE_DEPART
        elif c == 'O':
            v = lire_ligne('  Nouvelle valeur de l\'or (0-99, vide = %d) : ' % OR_TRICHE_DEFAUT)
            if v == '':
                v = str(OR_TRICHE_DEFAUT)
            if v.isdigit() and int(v) <= 99:
                nv['or'] = int(v)
                msg = 'Or fixé à %d' % nv['or']
            else:
                msg = 'Valeur refusée : %s' % v
        elif c == 'I':
            menu_objets(nv)


# ------------------------------------------------------------------ boucle
def intro(textes):
    """Pages TIN1..TIN4 : une touche = suite, Echap = sauter. Retourne False si on quitte (Ctrl-C)."""
    MOTEUR.intro()                               # la musique d'intro dure pendant les 4 pages
    for n in range(1, 5):
        effacer()
        print('=' * 72)
        print('  H E R O S   -   introduction (%d/4)' % n)
        print('=' * 72)
        print()
        for t in mettre_en_forme(textes.lignes('TIN%d' % n), sys.stdout.isatty()):
            print('  ' + t)
        print()
        print('-' * 72)
        print(' Une touche : page suivante     Échap : sauter l\'introduction')
        sys.stdout.flush()
        c = lire_touche()
        if c == 'CTRL':
            return False
        if c == 'ESC':
            break
    return True


def jouer(textes, hist, message=''):
    while True:
        st = hist[-1]
        MOTEUR.scene(st['sc'])                   # musique de la scene (sans relancer si identique)
        effacer()
        print(ecran(textes, st, message))
        sys.stdout.flush()
        message = ''
        c = normaliser(lire_touche())
        if isinstance(c, int):
            if c in choix_valides(st):
                nv = dict(st)
                if choisir(nv, c) == 'quitter':
                    print('\nÀ bientôt !')
                    return
                hist.append(nv)
            else:
                message = 'Ce choix n\'existe pas dans cette scène.'
        elif c in ('Q', 'CTRL'):
            print('\nÀ bientôt !')
            return
        elif c == 'M':
            message = MOTEUR.basculer()
        elif c == 'B':
            if len(hist) > 1:
                hist.pop()
                message = 'Retour arrière (%d écran(s) en réserve).' % (len(hist) - 1)
            else:
                message = 'Pas d\'écran antérieur.'
        elif c == 'T':
            nv = ecran_triche(textes, st)
            if nv is not None:
                hist.append(nv)
                message = 'Triche appliquée (B pour l\'annuler).'
        elif c == 'S':
            n = demander_slot('SAUVER')
            if n:
                try:
                    sauver(n, hist)
                    message = 'Partie sauvée dans %s' % fichier_slot(n)
                except OSError as e:
                    message = 'Échec de la sauvegarde : %s' % e
            else:
                message = 'Sauvegarde annulée.'
        elif c == 'C':
            n = demander_slot('CHARGER')
            if n:
                try:
                    hist[:] = charger(n)
                    message = 'Partie chargée (emplacement %d).' % n
                except (OSError, ValueError, KeyError, AssertionError, TypeError):
                    message = 'Emplacement %d vide ou illisible.' % n
            else:
                message = 'Chargement annulé.'


def jeu(chemin, sans_intro, charge):
    textes = Textes(chemin)
    st = nouvel_etat()
    if sans_intro:
        st = {'sc': IDX['TL1'], 'W': 0x1C00, 'L': 0, 'vie': VIE_DEPART, 'or': 0}
    hist, msg = [st], ''
    if charge:
        try:
            hist = charger(charge)
        except (OSError, ValueError, KeyError, AssertionError, TypeError):
            msg = 'Sauvegarde %d introuvable : nouvelle partie.' % charge
    if not sans_intro and not charge and not intro(textes):
        return
    jouer(textes, hist, msg)


def main():
    ap = argparse.ArgumentParser(description='HEROS en mode texte (et extracteur)')
    ap.add_argument('--data', metavar='FICHIER',
                    help='fichier DataHeros (par défaut : cherché dans le dossier du programme)')
    ap.add_argument('--extraire', nargs='?', const='heros_complet.txt', metavar='SORTIE',
                    help='au lieu de jouer, écrit le descriptif complet du jeu dans ce fichier '
                         '(défaut : heros_complet.txt)')
    ap.add_argument('--sans-intro', action='store_true',
                    help="saute les pages d'intro et l'histoire : village, Vie 28")
    ap.add_argument('--charge', type=int, metavar='N', help='reprend la sauvegarde N')
    ap.add_argument('--no-sound', '--sans-son', dest='sans_son', action='store_true',
                    help='aucun son (par défaut la musique est jouée si la machine a une sortie son)')
    ap.add_argument('--wav', nargs=2, metavar=('SCENE', 'FICHIER'),
                    help="écrit la musique d'une scène (ou 'intro') dans un fichier WAV, sans jouer")
    a = ap.parse_args()
    if a.wav:
        exporter_wav(a.wav[0], a.wav[1])
        return
    chemin = trouver_data(a.data)
    if a.extraire:
        extraire(chemin, a.extraire)
    else:
        if not a.sans_son:
            MOTEUR.activer()
        jeu(chemin, a.sans_intro, a.charge)


if __name__ == '__main__':
    sys.exit(main())
