#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Ajoute les pages systeme (triche, sauvegarde, chargement) et met a jour TIN0, puis reconstruit DataHeros-fr / -en.
   python3 mkdata.py   (lit x-fr.txt / x-en.txt = extraction des DataHeros precedents)"""
import re, subprocess, sys
import mapdata
PAGES = ['TMP1','TMP2','TSAV','TLOD','TSOK','TSER','TLER']
BAR = '\\xad'*18

FR = {
'TMP1': mapdata.block_lines(),
'TMP2': mapdata.block_lines2(True),
'TIN0': ["26,1|    H  E  R  O  S", "26,2| "+BAR,
 "11,4,52|Ce jeu d'aventure, HEROS, est l'oeuvre d'Olivier Thil (1994, shareware, concours DREAM).",
 "11,+2,52|Cette version a été adaptée avec l'aide d'une IA (Claude, d'Anthropic), sans que l'auteur ait pu être joint. Textes, images et sons d'origine inchangés.",
 "11,+2,52|Touches ajoutées pendant le jeu :",
 "11,+1,52,9|@2<@1 B @2>@1  retour en arrière ;",
 "11,+1,52,9|@2<@1 M @2>@1  carte du monde ;",
 "11,+1,52,9|@2<@1 V @2>@1  vie au maximum ;",
 "11,+1,52,9|@2<@1 S @2>@1 @2<@1 L @2>@1  sauver/charger (disque non protégé)",
 "11,+2,52|Langue : par les icônes, ou HerosExe fr / en.",
 "11,+1,52|Cliquez pour continuer."],
'TSAV': ["18,8|    S A U V E G A R D E R", "18,9| "+BAR,
 "18,11,40|La partie est écrite sur la disquette (elle ne doit pas être protégée) : fichiers HerosSave-1 à HerosSave-4.",
 "18,+2|< F1 > Emplacement 1.", "18,+1|< F2 > Emplacement 2.", "18,+1|< F3 > Emplacement 3.",
 "18,+1|< F4 > Emplacement 4.", "18,+1|< F5 > Annuler."],
'TLOD': ["18,8|    C H A R G E R", "18,9| "+BAR,
 "18,11,40|Reprendre une partie sauvegardée (fichiers HerosSave-1 à HerosSave-4).",
 "18,+2|< F1 > Emplacement 1.", "18,+1|< F2 > Emplacement 2.", "18,+1|< F3 > Emplacement 3.",
 "18,+1|< F4 > Emplacement 4.", "18,+1|< F5 > Annuler."],
'TSOK': ["18,8|    S A U V E G A R D E", "18,9| "+BAR,
 "18,11,40|La partie a été sauvegardée.", "18,+2|< F1 > Retour au jeu."],
'TSER': ["18,8|    E R R E U R", "18,9| "+BAR,
 "18,11,40|Impossible d'écrire le fichier de sauvegarde. La disquette est peut-être protégée ou pleine.", "18,+2|< F1 > Retour au jeu."],
'TLER': ["18,8|    E R R E U R", "18,9| "+BAR,
 "18,11,40|Aucune sauvegarde valide à cet emplacement.", "18,+2|< F1 > Retour au jeu."],
}
EN = {
'TMP1': mapdata.block_lines(False),
'TMP2': mapdata.block_lines2(False),
'TIN0': ["26,1|    H  E  R  O  S", "26,2| "+BAR,
 "11,4,52|This adventure game, HEROS, is the work of Olivier Thil (1994, shareware, DREAM contest).",
 "11,+2,52|This version was adapted with the help of an AI (Claude, by Anthropic); the original author could not be reached. Original texts, pictures and sounds unchanged.",
 "11,+2,52|Keys added during the game:",
 "11,+1,52,9|@2<@1 B @2>@1  undo;",
 "11,+1,52,9|@2<@1 M @2>@1  world map;",
 "11,+1,52,9|@2<@1 V @2>@1  restore life to maximum;",
 "11,+1,52,9|@2<@1 S @2>@1 @2<@1 L @2>@1  save/load (unprotected disk)",
 "11,+2,52|Language: by icon, or HerosExe fr / en.",
 "11,+1,52|Click to continue."],
'TSAV': ["18,8|    S A V E", "18,9| "+BAR,
 "18,11,40|The game is written on the disk (it must not be write-protected): files HerosSave-1 to HerosSave-4.",
 "18,+2|< F1 > Slot 1.", "18,+1|< F2 > Slot 2.", "18,+1|< F3 > Slot 3.",
 "18,+1|< F4 > Slot 4.", "18,+1|< F5 > Cancel."],
'TLOD': ["18,8|    L O A D", "18,9| "+BAR,
 "18,11,40|Resume a saved game (files HerosSave-1 to HerosSave-4).",
 "18,+2|< F1 > Slot 1.", "18,+1|< F2 > Slot 2.", "18,+1|< F3 > Slot 3.",
 "18,+1|< F4 > Slot 4.", "18,+1|< F5 > Cancel."],
'TSOK': ["18,8|    S A V E D", "18,9| "+BAR,
 "18,11,40|The game has been saved.", "18,+2|< F1 > Back to the game."],
'TSER': ["18,8|    E R R O R", "18,9| "+BAR,
 "18,11,40|Cannot write the save file. The disk may be write-protected or full.", "18,+2|< F1 > Back to the game."],
'TLER': ["18,8|    E R R O R", "18,9| "+BAR,
 "18,11,40|No valid saved game in this slot.", "18,+2|< F1 > Back to the game."],
}

def build(src, dst_txt, dst_bin, pages):
    s = open(src, encoding='utf-8').read()
    # remplace TIN0
    m = re.search(r'^=== TIN0 cle=55\n(.*?)(?=^=== )', s, re.S|re.M)
    s = s[:m.start()] + '=== TIN0 cle=55\n' + '\n'.join(pages['TIN0']) + '\n\n' + s[m.end():]
    if 'INDEX:' in s and 'TSAV' not in s:
        s = re.sub(r'^(INDEX: .*?TIN0)', r'\1 ' + ' '.join(PAGES), s, count=1, flags=re.M)
        i = s.index('=== TIN1 cle=55')
        blocks = ''.join('=== %s cle=55\n%s\n\n' % (n, '\n'.join(pages[n])) for n in PAGES)
        s = s[:i] + blocks + s[i:]
    open(dst_txt, 'w', encoding='utf-8').write(s)
    r = subprocess.run([sys.executable, 'heros_texte.py', 'pack', dst_txt, dst_bin], capture_output=True, text=True)
    print(r.stdout[-300:], r.stderr[-600:])
    assert r.returncode == 0

build('x-fr.txt', 'h3-fr.txt', 'DataHeros-fr', FR)
build('x-en.txt', 'h3-en.txt', 'DataHeros-en', EN)
