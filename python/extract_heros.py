#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
extract_heros.py - descriptif complet du jeu Amiga HEROS (Olivier Thil, 1994, concours DREAM)
a partir du seul fichier de donnees "DataHeros".   (version 2)

Produit UN fichier texte lisible : pour chaque SCENE (enregistrement du jeu)
    - en-tete : traitement a l'arrivee (points de vie), scenes qui y menent,
      emplacement et dechiffrement du texte, notes ;
    - le texte decode ;
    - la liste des choix F1..F5 avec leurs actions (PRENDS, POSE, BASCULE,
      DEJAVU, OR, ALLER...).
En fin de fichier : les blocs que AUCUNE scene n'affiche (page du leurre
PYRAMIDE, pages de presentation) et les anomalies.

POURQUOI UN SEUL FICHIER SUFFIT
-------------------------------
* DataHeros contient les textes : le script le lit.
* L'enchainement des scenes (liens F1..F5), les routines (objets, or, vie) sont dans
  l'executable HerosExe, COMPRESSE : un script ne peut pas le lire. Cette logique a ete
  decodee une fois depuis un dump memoire du jeu en marche et est INTEGREE en bas de ce
  script (variable LOGIC). HerosExe n'est donc pas necessaire (valable pour CETTE version).

FORMAT DE DataHeros (big-endian, 68000)
---------------------------------------
  u32 debut_des_donnees ; puis (debut-4)/8 entrees : char[4] nom, u32 DEBUT du bloc de ce nom.
  (Le bloc va de ce debut jusqu'a l'octet 0x00 qui termine le texte.)
  Chaque bloc = XOR 0x55 octet par octet. Bloc de texte decode :
     colonne ligne caracteres... 0xFF  (une ligne d'ecran) ... 0x00 (fin).
     "@" + chiffre dans le texte = changement de couleur.
  Bloc protege (code du concours, scene 'TT39') : XOR 0x55 puis inversion de tous les bits
  (= cle 0xAA). Le jeu ne le dechiffre en memoire qu'a la toute fin (routine 0x1BC06).

SCENES
------
  La table des scenes (en memoire) a un enregistrement par scene : nom de 4 caracteres,
  5 liens (F1..F5) et un delta de VIE. Le nom designe le bloc de texte affiche.
  Un lien est soit une autre scene, soit une routine speciale (conditions/effets).
  Nom donne deux fois (ex. TT42) : deux scenes distinctes qui affichent le MEME texte
  (ex. 1ere visite / visite suivante) : elles sont notees NOM#1 / NOM#2.

Utilisation :   python3 extract_heros.py DataHeros heros_complet.txt
"""

import argparse
import collections
import itertools
import json
import re
import struct
import sys

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


# ==========================================================================
# 2) Traduction de la logique en langage lisible
# ==========================================================================
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


def main():
    ap = argparse.ArgumentParser(description="Descriptif complet de HEROS a partir de DataHeros")
    ap.add_argument("fichier", help="fichier de données (DataHeros)")
    ap.add_argument("sortie", help="fichier texte à produire")
    args = ap.parse_args()
    donnees = open(args.fichier, "rb").read()
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
    open(args.sortie, "w", encoding="utf-8").write("\n".join(O) + "\n")
    print("%d scènes (dont %d protégée), %d choix, %d blocs hors scène -> %s" % (
        stats['scènes'], stats['protégés'], stats['choix'], stats['hors scène'], args.sortie))


if __name__ == "__main__":
    sys.exit(main())
