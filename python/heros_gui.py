#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""HEROS - version graphique (Amiga, Olivier Thil, 1994).

Programme séparé de heros_jeu.py (il s'en sert pour toute la logique du jeu, le son et
les sauvegardes : gardez les deux fichiers dans le même dossier, avec DataHeros).

    python3 heros_gui.py                  # jeu complet : image-titre, introduction, partie
    python3 heros_gui.py --no-sound       # sans musique
    python3 heros_gui.py --sans-intro     # saute le titre et l'introduction (village, Vie 28)
    python3 heros_gui.py --charge 2       # reprend la sauvegarde n° 2
    python3 heros_gui.py --echelle 1.5    # zoom du texte (0.5 à 4 ; défaut : automatique)

Variables d'environnement (réglages permanents) : HEROS_ECHELLE (zoom du texte, comme --echelle),
HEROS_ECHELLE_UI (zoom des boutons et du HUD, 1.0 = normal), HEROS_DPI (densité de l'écran, si mal détectée).

Uniquement la bibliothèque standard (tkinter). Toutes les images (décors, parchemin,
écran-titre, icônes d'objets) sont fabriquées à partir de données extraites du jeu original
et incluses à la fin de ce fichier. Le texte est écrit avec une police vectorielle à chasse fixe.

Clavier : F1..F5 (ou 1..5, ou & é " ' ( sur AZERTY) = choix ; B retour ; S sauver ; C charger ;
T triche ; M son ; Q quitter ; flèches / PgUp / PgDn / Début / Fin / molette = défilement du parchemin.
Tout est aussi cliquable (texte des choix, boutons).
"""
import argparse
import base64
import json
import os
import re
import struct
import sys
import zlib
from operator import itemgetter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    import tkinter as tk
    from tkinter import font as tkfont
except ImportError:                                            # pragma: no cover
    sys.exit("tkinter est introuvable. Sous Linux : installez le paquet « python3-tk » "
             "(sudo apt install python3-tk). Windows et macOS l'incluent normalement.")
try:
    import heros_jeu as H
except ImportError:                                            # pragma: no cover
    sys.exit("heros_jeu.py est introuvable : placez heros_gui.py dans le même dossier que heros_jeu.py.")

# ====================================================================== images
_ASSETS = None


def assets():
    """Décode (une seule fois) les données graphiques incluses en fin de fichier."""
    global _ASSETS
    if _ASSETS is None:
        o = json.loads(zlib.decompress(base64.b64decode(_BLOB)))
        tiles = base64.b64decode(o['tiles'])
        o['TR'] = [[tiles[k * 1024 + y * 32:k * 1024 + y * 32 + 32] for y in range(32)]
                   for k in range(120)]
        o['MP'] = {k: base64.b64decode(v) for k, v in o['maps'].items()}
        _ASSETS = o
    return _ASSETS


def rgb12(mot):
    """$0RGB Amiga -> (r, v, b) sur 8 bits."""
    return ((mot >> 8 & 15) * 17, (mot >> 4 & 15) * 17, (mot & 15) * 17)


def pal_triplet(t):
    """3 couleurs -> palette de 4 entrées : indice 0 = noir/transparent, indice k = couleur k-1."""
    return [(0, 0, 0)] + [rgb12(c) for c in t]


def pal_sombre(t):
    """Palette du parchemin assombrie (meilleur contraste avec le texte)."""
    return [(0, 0, 0)] + [tuple(int(v * 0.5) for v in rgb12(c)) for c in t]


def lignes_carte(cle):
    """Carte de tuiles -> liste de lignes de pixels (indices 0..3), 608 pixels de large."""
    A = assets()
    data, rows = A['MP'][cle], []
    for r in range(len(data) // 19):
        ks = data[r * 19:(r + 1) * 19]
        for y in range(32):
            rows.append(b''.join([A['TR'][k][y] for k in ks]))
    return rows


def _chunk(t, d):
    c = struct.pack('>I', len(d)) + t + d
    return c + struct.pack('>I', zlib.crc32(t + d) & 0xFFFFFFFF)


def png_mis_a_echelle(parties, W, Hh, alpha=False):
    """Assemble verticalement des (lignes d'indices, palette) et les met à la taille W x Hh
    (agrandissement 'plus proche voisin'). Retourne les octets d'un PNG (RGB ou RGBA)."""
    nch = 4 if alpha else 3
    lignes = []                                     # (octets RGB(A) a la largeur W) par ligne source
    for rows, pal in parties:
        sw = len(rows[0])
        xs = itemgetter(*[min(sw - 1, x * sw // W) for x in range(W)])
        pal = list(pal) + [(0, 0, 0)] * (256 - len(pal))
        tr = [bytes(c[i] for c in pal) for i in range(3)]
        ta = bytes([0] + [255] * 255)
        cache = {}
        for r in rows:
            if r not in cache:
                idx = bytes(xs(r))
                out = bytearray(W * nch)
                for i in range(3):
                    out[i::nch] = idx.translate(tr[i])
                if alpha:
                    out[3::nch] = idx.translate(ta)
                cache[r] = bytes(out)
            lignes.append(cache[r])
    sh = len(lignes)
    brut = b''.join([b'\0' + lignes[min(sh - 1, y * sh // Hh)] for y in range(Hh)])
    ihdr = struct.pack('>IIBBBBB', W, Hh, 8, 6 if alpha else 2, 0, 0, 0)
    return (b'\x89PNG\r\n\x1a\n' + _chunk(b'IHDR', ihdr)
            + _chunk(b'IDAT', zlib.compress(brut, 1)) + _chunk(b'IEND', b''))


def photo(png):
    return tk.PhotoImage(data=base64.b64encode(png))


# ================================================================== utilitaires
def melanger(c, vers, t):
    return tuple(int(c[i] + (vers[i] - c[i]) * t) for i in range(3))


def hexa(c):
    return '#%02x%02x%02x' % tuple(c)


OBJETS = dict(H.OBJETS)
OBJETS[12] = 'Torche'          # le sac du village contient nourriture, épée (bits 10-11) et torche (bit 12)

CHIFFRES_CLAVIER = dict(H.CHIFFRES)
for _i in range(1, 10):
    CHIFFRES_CLAVIER[str(_i)] = _i

FOND = '#1a120c'        # fond des barres
CLAIR = '#f0d9a8'       # texte des barres
DOUX = '#b89868'
BOUTON = '#3a2616'
BOUTON_ACTIF = '#5c3a1c'


def clavier(ev):
    """Évènement clavier -> int (choix 1..9), 'F1'..: voir plus bas, ou une chaîne en majuscule."""
    ks = ev.keysym
    m = re.fullmatch(r'F([1-9])', ks)
    if m:
        return int(m.group(1))
    m = re.fullmatch(r'KP_([1-9])', ks)
    if m:
        return int(m.group(1))
    if ev.char and ev.char in CHIFFRES_CLAVIER:
        return CHIFFRES_CLAVIER[ev.char]
    if ks in ('Escape', 'Return', 'KP_Enter', 'space', 'Up', 'Down', 'Prior', 'Next', 'Home', 'End'):
        return ks
    if ev.char and ev.char.isalpha():
        return ev.char.upper()
    return None


# ================================================================ dialogues
class Modale(tk.Toplevel):
    """Petite fenêtre modale, centrée sur la fenêtre principale."""

    def __init__(self, app, titre):
        super().__init__(app.root, bg=FOND)
        self.app = app
        self.title(titre)
        self.transient(app.root)
        self.resizable(False, False)
        self.resultat = None
        self.protocol('WM_DELETE_WINDOW', self.fermer)
        self.bind('<Escape>', lambda e: self.fermer())

    def montrer(self):
        self.update_idletasks()
        r = self.app.root
        x = r.winfo_rootx() + max(0, (r.winfo_width() - self.winfo_reqwidth()) // 2)
        y = r.winfo_rooty() + max(0, (r.winfo_height() - self.winfo_reqheight()) // 3)
        self.geometry('+%d+%d' % (x, y))
        try:
            self.wait_visibility()
            self.grab_set()
        except tk.TclError:
            pass
        try:
            self.focus_force()
        except tk.TclError:
            pass
        self.app.root.wait_window(self)
        return self.resultat

    def fermer(self, valeur=None):
        self.resultat = valeur
        try:
            self.grab_release()
        except tk.TclError:
            pass
        self.destroy()

    def etiquette(self, texte, **kw):
        kw.setdefault('fg', CLAIR)
        kw.setdefault('bg', FOND)
        kw.setdefault('font', self.app.f_ui)
        kw.setdefault('justify', 'left')
        return tk.Label(self, text=texte, **kw)

    def bouton(self, parent, texte, cmd, **kw):
        return self.app.bouton(parent, texte, cmd, **kw)


def dialogue_slot(app, action):
    """Choix de l'emplacement de sauvegarde 1..9. Retourne le numéro ou None."""
    d = Modale(app, action)
    d.etiquette('%s - choisissez un emplacement (clic, ou touche 1..9 / & é " \' ( - è _ ç) :'
                % action.capitalize()).pack(padx=14, pady=(12, 6), anchor='w')
    for n in range(1, 10):
        t = '%d    %s' % (n, H.resume_slot(n))
        b = d.bouton(d, t, lambda n=n: d.fermer(n), anchor='w', width=44)
        b.pack(padx=14, pady=2, fill='x')
    d.bouton(d, 'Annuler  [Échap]', d.fermer).pack(padx=14, pady=(8, 12))

    def touche(ev):
        c = clavier(ev)
        if isinstance(c, int) and 1 <= c <= 9:
            d.fermer(c)
    d.bind('<Key>', touche)
    return d.montrer()


def dialogue_confirmer(app, question):
    d = Modale(app, 'Confirmation')
    d.etiquette(question, font=app.f_ui_gras).pack(padx=20, pady=(16, 10))
    f = tk.Frame(d, bg=FOND)
    f.pack(padx=14, pady=(0, 14))
    d.bouton(f, 'Oui  [O]', lambda: d.fermer(True)).pack(side='left', padx=6)
    b = d.bouton(f, 'Non  [N]', lambda: d.fermer(False))
    b.pack(side='left', padx=6)
    b.focus_set()

    def touche(ev):
        c = (ev.char or '').lower()
        if c in ('o', 'y'):
            d.fermer(True)
        elif c == 'n':
            d.fermer(False)
        elif ev.keysym in ('Return', 'KP_Enter'):
            d.fermer(True if d.focus_get() is not b else False)
    d.bind('<Key>', touche)
    return bool(d.montrer())


def dialogue_triche(app, st):
    """Fenêtre de triche : retourne le nouvel état s'il a changé, sinon None."""
    nv = dict(st)
    d = Modale(app, 'Triche')
    lab_sc = d.etiquette('', font=app.f_ui_gras)
    lab_sc.pack(padx=14, pady=(12, 2), anchor='w')
    lab_msg = d.etiquette('', fg='#ffd070')

    def rafraichir(msg=''):
        lab_sc.config(text='Scène actuelle : %s     Vie : %d     Or : %d' % (H.LAB[nv['sc']], nv['vie'], nv['or']))
        lab_msg.config(text=msg)
        for b in range(16):
            var[b].set(1 if H._bit(nv['W'], b) else 0)
        v_or.set(str(nv['or']))
    # --- aller à une scène
    f1 = tk.Frame(d, bg=FOND)
    f1.pack(padx=14, pady=(8, 2), fill='x')
    tk.Label(f1, text='Aller à la scène (code, ex. TL1, TM12, TT39) :', fg=CLAIR, bg=FOND,
             font=app.f_ui).pack(side='left')
    v_code = tk.StringVar()
    e = tk.Entry(f1, textvariable=v_code, width=9, font=app.f_ui)
    e.pack(side='left', padx=6)

    def aller(code=None):
        code = (code or v_code.get()).strip()
        if not code:
            return
        i = H.trouver_scene(code)
        if i is None:
            rafraichir('Code inconnu : %s' % code)
        else:
            nv['sc'] = i                       # téléportation : pas de delta de vie
            rafraichir('Téléporté en %s' % H.LAB[i])
    d.bouton(f1, 'Aller  [Entrée]', aller).pack(side='left')
    e.bind('<Return>', lambda ev: aller())
    # --- liste des scènes
    f2 = tk.Frame(d, bg=FOND)
    f2.pack(padx=14, pady=4, fill='x')
    sb = tk.Scrollbar(f2)
    lb = tk.Listbox(f2, height=6, width=60, yscrollcommand=sb.set, exportselection=False,
                    bg='#2a1c10', fg=CLAIR, selectbackground=BOUTON_ACTIF, font=app.f_ui)
    sb.config(command=lb.yview)
    lb.pack(side='left', fill='x', expand=True)
    sb.pack(side='left', fill='y')
    for i, c in enumerate(H.LAB):
        lb.insert('end', '%-8s %s' % (c, ''))
    lb.bind('<Double-Button-1>', lambda ev: lb.curselection() and aller(H.LAB[lb.curselection()[0]]))
    d.etiquette('(double-clic sur un code de la liste pour s\'y rendre)', fg=DOUX).pack(padx=14, anchor='w')
    # --- vie / or
    f3 = tk.Frame(d, bg=FOND)
    f3.pack(padx=14, pady=(8, 2), fill='x')

    def vie():
        nv['vie'] = H.VIE_DEPART
        rafraichir('Vie remise à %d' % H.VIE_DEPART)
    d.bouton(f3, 'Vie = %d' % H.VIE_DEPART, vie).pack(side='left')
    tk.Label(f3, text='   Or :', fg=CLAIR, bg=FOND, font=app.f_ui).pack(side='left')
    v_or = tk.StringVar(value=str(nv['or']))
    tk.Entry(f3, textvariable=v_or, width=4, font=app.f_ui).pack(side='left', padx=4)

    def fixer_or():
        v = v_or.get().strip() or str(H.OR_TRICHE_DEFAUT)
        if v.isdigit() and int(v) <= 99:
            nv['or'] = int(v)
            rafraichir('Or fixé à %d' % nv['or'])
        else:
            rafraichir('Valeur refusée : %s (0 à 99)' % v)
    d.bouton(f3, 'Appliquer', fixer_or).pack(side='left')
    d.etiquette("(l'or n'est jamais testé par le jeu : conseil %d, rien ne bloque)" % H.OR_TRICHE_DEFAUT,
                fg=DOUX).pack(padx=14, anchor='w')
    # --- objets
    d.etiquette('Objets (cocher = prendre, décocher = poser) :', font=app.f_ui_gras).pack(
        padx=14, pady=(8, 2), anchor='w')
    f4 = tk.Frame(d, bg=FOND)
    f4.pack(padx=14, fill='x')
    var = []

    def basculer(b):
        nv['W'] ^= 1 << b
        rafraichir('%s : %s' % (OBJETS[b], 'pris' if H._bit(nv['W'], b) else 'posé'))
    for b in range(16):
        v = tk.IntVar(value=1 if H._bit(nv['W'], b) else 0)
        var.append(v)
        tk.Checkbutton(f4, text=OBJETS[b], variable=v, command=lambda b=b: basculer(b),
                       fg=CLAIR, bg=FOND, selectcolor='#2a1c10', activebackground=FOND,
                       activeforeground='#fff', font=app.f_ui, anchor='w').grid(
            row=b % 8, column=b // 8, sticky='w', padx=(0, 16))
    d.etiquette('Attention : un inventaire « impossible » peut donner des scènes inattendues.',
                fg=DOUX).pack(padx=14, pady=(6, 0), anchor='w')
    lab_msg.pack(padx=14, anchor='w')
    f5 = tk.Frame(d, bg=FOND)
    f5.pack(pady=(6, 12))
    d.bouton(f5, 'Fermer  [Échap]', d.fermer).pack()
    rafraichir()
    e.focus_set()
    d.montrer()
    return nv if nv != st else None


# ================================================================== application
class Appli:
    def __init__(self, textes, echelle, sans_intro, charge, son):
        self.textes = textes
        self.raw_cache = {}
        self.root = tk.Tk()
        self.root.title('HEROS')
        self.root.configure(bg='#000')
        self.son = son
        self.mode = 'titre'
        self.hist = [H.nouvel_etat()]
        self.intro_n = 0
        self.msg_attente = ''
        self.photos = {}
        self.cache_png = {}
        self.groupes = []
        self.survol = None
        self.off = 0
        self.bas_contenu = 0
        self.page_h = 0
        self.choix_btn = []
        self._tip = False

        self.root.resizable(True, True)
        self.root.minsize(660, 420)
        sh, sw = self.root.winfo_screenheight(), self.root.winfo_screenwidth()
        self.dpi = self._densite()
        self.sbw = int(max(260, min(560, 330 * self.dpi / 96.0)))          # colonne de droite (déplaçable)
        if echelle:
            f = echelle
        else:       # taille de lettre agréable (~13,5 pt réels), limitée à ce qui tient dans l'écran
            f = 0.6 * (13.5 * self.dpi / 72.0) / 11.2
            f = max(0.6, min(3.0, f, (sh - 110) / 600.0, (sw - 60 - self.sbw) / 851.0))
        self.cols = 6
        self.auto = echelle is None          # zoom du texte : suit la largeur de la colonne de gauche
        self.auto_ui = echelle is None       # zoom de l'interface : suit la largeur de la colonne de droite
        try:                                   # zoom de l'interface, relatif à la densité de l'écran
            self.fu = max(0.5, min(3.0, float(os.environ['HEROS_ECHELLE_UI'])))
        except (KeyError, ValueError):
            self.fu = 1.0
        self.plein = False
        self.pret = False
        self.f_ui = tkfont.Font(root=self.root, family=self._famille(proportionnelle=True), size=10)
        self.f_ui_gras = tkfont.Font(root=self.root, font=self.f_ui)
        self.f_ui_gras.configure(weight='bold')
        self._mesures(f)
        self._ui_mesures(self.fu)
        self.cw, self.Hv = self.W, int(320 * self.SY)
        self.page_h = max(int(640 * self.SY), self.Hv)
        self._dim, self._rd = None, None

        # ---- colonne de droite : HUD en haut ; choix, commandes et message en bas
        self.pw = tk.PanedWindow(self.root, orient='horizontal', sashwidth=8, sashrelief='raised', bg='#6a5238',
                                 bd=0, opaqueresize=True, showhandle=False)
        self.pw.pack(fill='both', expand=True)
        self.lateral = tk.Frame(self.pw, bg=FOND, width=self.sbw)
        self.pw.add(self.lateral, width=self.sbw, minsize=int(230 * self.dpi / 96.0), stretch='never')
        self.lateral.pack_propagate(False)
        self.lab_msg = tk.Label(self.lateral, text='', bg=FOND, fg='#ffd070', font=self.f_ui, anchor='w',
                                justify='left', wraplength=self.sbw - 16)
        self.lab_msg.pack(side='bottom', fill='x', padx=8, pady=(0, 6))
        self.zone_vue = tk.Frame(self.lateral, bg=FOND)
        self.zone_vue.pack(side='bottom', fill='x', padx=6)
        self.zone_cmd = tk.Frame(self.lateral, bg=FOND)
        self.zone_cmd.pack(side='bottom', fill='x', padx=6, pady=(6, 0))
        self.cmds = {}
        for i, (cle, texte, cmd) in enumerate((('B', 'Retour [B]', self.retour), ('S', 'Sauver [S]', self.sauver),
                                               ('C', 'Charger [C]', self.charger), ('T', 'Triche [T]', self.triche),
                                               ('M', 'Son [M]', self.basculer_son), ('Q', 'Quitter [Q]', self.quitter))):
            b = self.bouton(self.zone_cmd, texte, cmd)
            b.grid(row=i // 2, column=i % 2, sticky='ew', padx=2, pady=2)
            self.cmds[cle] = b
        for i, (texte, cmd) in enumerate((('Texte A\u2212 [-]', lambda: self.zoom(1 / 1.12)),
                                          ('Texte A+ [+]', lambda: self.zoom(1.12)),
                                          ('Interf. A\u2212', lambda: self.zoom_ui(1 / 1.12)),
                                          ('Interf. A+', lambda: self.zoom_ui(1.12)),
                                          ('Ajuster [0]', self.ajuster), ('Plein écran [F11]', self.plein_ecran))):
            self.bouton(self.zone_vue, texte, cmd).grid(row=i // 2, column=i % 2, sticky='ew', padx=2, pady=2)
        for fr in (self.zone_cmd, self.zone_vue):
            fr.columnconfigure(0, weight=1, uniform='c')
            fr.columnconfigure(1, weight=1, uniform='c')
        self.zone_choix = tk.Frame(self.lateral, bg=FOND)       # les choix s'empilent vers le haut
        self.zone_choix.pack(side='bottom', fill='x', padx=6, pady=(6, 4))
        self.etat = tk.Canvas(self.lateral, width=self.sbw, height=100, bg=FOND, highlightthickness=0)
        self.etat.pack(side='top', fill='x')
        self._icones()

        zone = tk.Frame(self.pw, bg='#000')
        self.pw.add(zone, before=self.lateral, minsize=300, stretch='always')
        self.sb = tk.Scrollbar(zone, orient='vertical', command=self._sb_cmd)
        self.sb.pack(side='right', fill='y')
        self.cv = tk.Canvas(zone, width=self.W, height=self.Hv, bg='#000', highlightthickness=0,
                            yscrollincrement=1)
        self.cv.pack(side='left', fill='both', expand=True)
        self.cv.configure(scrollregion=(0, 0, self.W, self.page_h))
        self.fond_id = self.cv.create_image(0, 0, anchor='nw', tags='fond')
        self.parch_id = self.cv.create_image(0, 0, anchor='nw', tags='parch')
        self.cv.tag_raise('parch')

        # ---- évènements
        self.root.bind('<Key>', self.touche)
        self.root.protocol('WM_DELETE_WINDOW', self.fermer_fenetre)
        for w in (self.cv, zone):
            w.bind('<Button-1>', self.clic)
            w.bind('<Motion>', self.mouvement)
            w.bind('<Leave>', lambda e: self._survoler(None))
        self.cv.bind('<Configure>', self._config_cv)
        self.root.bind('<Configure>', lambda e: e.widget is self.root and self._planifier())
        self.root.bind('<MouseWheel>', self.molette)
        self.root.bind('<Control-MouseWheel>', lambda e: self._zoom_molette(e, 1.12 if e.delta > 0 else 1 / 1.12))
        self.root.bind('<Control-Button-4>', lambda e: self._zoom_molette(e, 1.12))
        self.root.bind('<Control-Button-5>', lambda e: self._zoom_molette(e, 1 / 1.12))
        self.root.bind('<Button-4>', lambda e: self.defiler(-3 * self.lh))
        self.root.bind('<Button-5>', lambda e: self.defiler(3 * self.lh))

        self.sans_intro, self.charge = sans_intro, charge
        self.root.geometry('%dx%d' % (min(sw - 20, int(851 * f) + self.sbw + 24), min(sh - 70, int(600 * f) + 24)))
        self.root.after(30, self.demarrer)

    # ------------------------------------------------------------- polices
    def _famille(self, proportionnelle=False):
        fams = set(tkfont.families(self.root))
        if proportionnelle:
            ordre = ['Segoe UI', 'Helvetica Neue', 'DejaVu Sans', 'Liberation Sans', 'Arial', 'Helvetica']
        else:
            ordre = ['DejaVu Sans Mono', 'Menlo', 'Consolas', 'Liberation Mono', 'Lucida Console',
                     'Noto Sans Mono', 'Courier New', 'FreeMono', 'Courier']
        for n in ordre:
            if n in fams:
                return n
        return tkfont.nametofont('TkFixedFont' if not proportionnelle else 'TkDefaultFont').actual('family')

    def _police_texte(self, cible):
        """Police vectorielle à chasse fixe dont la largeur de lettre vaut ~ cible pixels."""
        fam = self._famille()
        taille = -max(9, int(cible / 0.6))
        for _ in range(14):
            f = tkfont.Font(root=self.root, family=fam, size=taille)
            m = f.measure('0')
            if m == round(cible) or (m > cible and m - cible < 0.6):
                break
            taille += -1 if m < cible else 1
            if taille > -8:
                break
        if hasattr(self, 'f_txt'):
            self.f_txt.configure(size=taille)
            self.f_txt_gras.configure(size=taille)
        else:
            self.f_txt = tkfont.Font(root=self.root, family=fam, size=taille)
            self.f_txt_gras = tkfont.Font(root=self.root, family=fam, size=taille, weight='bold')

    def _mesures(self, f):
        """Toutes les dimensions découlent de l'échelle f (1.0 = 851 pixels de large)."""
        self.f = f
        self._police_texte(8 * 1.4 * f)
        self.cell = self.f_txt.measure('0')
        self.SX = self.cell / 8.0
        self.ls = self.f_txt.metrics('linespace')
        self.SY = max(self.SX * 1.875 / 1.4, self.ls * 1.04 / 12.0)
        self.W = int(608 * self.SX)
        self.lh = 12 * self.SY                       # hauteur d'une ligne de texte (pixels)

    def _densite(self):
        """Densité de pixels de l'écran (points par pouce), estimée à partir de la taille physique
        déclarée et de la résolution."""
        r = self.root
        try:
            return max(50.0, min(400.0, float(os.environ['HEROS_DPI'])))     # réglage manuel
        except (KeyError, ValueError):
            pass
        sw = r.winfo_screenwidth()
        dpi = r.winfo_fpixels('1i')
        try:
            mm = r.winfo_screenmmwidth()
            if mm > 0 and 70 <= sw * 25.4 / mm <= 450:
                dpi = max(dpi, sw * 25.4 / mm)
        except tk.TclError:
            pass
        if sw >= 2200:                       # grande résolution : les pixels sont forcément plus petits
            dpi = max(dpi, 96.0 * sw / 1920.0)
        return max(72.0, min(300.0, dpi))

    def _ui_mesures(self, fu):
        """Dimensions de la colonne de droite (boutons, icônes) : zoom indépendant du texte."""
        self.fu = fu
        taille = -max(11, int(10 * self.dpi / 72.0 * fu))       # pixels : police vectorielle
        self.f_ui.configure(size=taille)
        self.f_ui_gras.configure(size=taille)
        self._slot()

    def _slot(self):
        """Taille et nombre de colonnes de la grille d'objets : assez grandes pour être belles,
        assez petites pour que choix et commandes restent visibles."""
        cible = int(48 * self.dpi / 96.0 * self.fu)
        w = max(self.sbw - 12, 100)
        h = self.root.winfo_height()
        budget = 0.26 * max(h if h > 50 else 800, 500)
        for cols in (4, 6, 8):
            slot = max(20, min(72, w // cols - 2, cible))
            if -(-16 // cols) * (slot + 2) <= budget:
                break
        self.cols, self.slot = cols, slot

    def zoom_ui(self, facteur):
        self.auto_ui = False
        self._ui_mesures(max(0.6, min(3.0, self.fu * facteur)))
        self._icones()
        self.redessiner()

    def _zoom_molette(self, ev, facteur):
        w = ev.widget
        if str(w).startswith(str(self.lateral)):
            self.zoom_ui(facteur)
        else:
            self.zoom(facteur)

    def appliquer_echelle(self, f):
        self._mesures(f)
        self.cache_png.clear()
        self._icones()
        self.redessiner()

    def _config_cv(self, ev):
        if (ev.width, ev.height) != self._dim:
            self._dim = (ev.width, ev.height)
            self._planifier()

    def _planifier(self):
        if self._rd:
            self.root.after_cancel(self._rd)
        self._rd = self.root.after(120, self._apres_taille)

    def _apres_taille(self):
        self._rd = None
        if not self.pret:
            return
        nsb = self.lateral.winfo_width()
        if nsb < 50:
            return
        self.sbw = nsb
        self.etat.configure(width=nsb)
        self.lab_msg.configure(wraplength=nsb - 16)
        ancien = (self.cols, self.slot)
        self._slot()
        if (self.cols, self.slot) != ancien:
            self._icones()
        if self.auto:
            f = self._f_auto(self.cv.winfo_width())
            if abs(f / self.f - 1) > 0.03:
                self.appliquer_echelle(f)
                return
        self.redessiner()

    def _f_auto(self, cw):
        """Échelle qui tient dans la colonne de gauche (largeur et hauteur)."""
        return max(0.5, min(4.0, cw / 851.2, max(self.cv.winfo_height(), 200) / 600.0))

    def zoom(self, facteur):
        self.auto = False
        self.appliquer_echelle(max(0.5, min(4.0, self.f * facteur)))
        if not self.plein:                           # la fenêtre suit la nouvelle largeur
            w = min(self.W + self.sb.winfo_reqwidth() + 4 + 8 + self.lateral.winfo_width(), self.root.winfo_screenwidth())
            self.root.geometry('%dx%d' % (w, self.root.winfo_height()))

    def ajuster(self):
        self.auto = self.auto_ui = True
        self._ui_mesures(1.0)
        self.appliquer_echelle(self._f_auto(self.cv.winfo_width()))

    def plein_ecran(self):
        self.plein = not self.plein
        try:
            self.root.attributes('-fullscreen', self.plein)
        except tk.TclError:
            self.plein = False
        if self.plein:
            self.auto = self.auto_ui = True

    def redessiner(self):
        """Réorganise l'affichage après un changement de taille ou d'échelle."""
        if not self.pret:
            return
        self.cw = max(self.cv.winfo_width(), 100)
        if self.cv.winfo_height() > 1:
            self.Hv = self.cv.winfo_height()
        self.page_h = max(int(640 * self.SY), self.Hv)
        ox = max(0, (self.cw - self.W) // 2)         # image centrée dans la fenêtre
        self.cv.configure(scrollregion=(-ox, 0, self.cw - ox, self.page_h))
        self.cv.xview_moveto(0)
        if self.mode == 'jeu':
            self.afficher(self.lab_msg.cget('text'))
        elif self.mode == 'intro':
            self.intro_n -= 1
            self.suite_intro()
        else:
            self.afficher_titre(False)

    def bouton(self, parent, texte, cmd, **kw):
        kw.setdefault('anchor', 'center')
        return tk.Button(parent, text=texte, command=cmd, bg=BOUTON, fg=CLAIR, activebackground=BOUTON_ACTIF,
                         activeforeground='#fff', relief='flat', bd=0, padx=10, pady=3, font=self.f_ui,
                         highlightthickness=0, takefocus=0, cursor='hand2', **kw)

    # -------------------------------------------------------------- images
    def _png(self, cle, fabrique):
        if cle not in self.cache_png:
            if len(self.cache_png) > 24:
                self.cache_png.clear()
            self.cache_png[cle] = photo(fabrique())
        return self.cache_png[cle]

    def image_decor(self, sc):
        c = assets()['scenes'][sc]
        cle = ('decor', c[2], tuple(c[3]), c[4], tuple(c[5]), self.W, self.Hv)
        return self._png(cle, lambda: png_mis_a_echelle(
            [(lignes_carte(c[2]), pal_triplet(c[3])), (lignes_carte(c[4]), pal_triplet(c[5]))],
            self.W, self.Hv))

    def image_parchemin(self, sc):
        c = assets()['scenes'][sc]
        cle = ('parch', c[0], tuple(c[1]), self.W, self.page_h)
        return self._png(cle, lambda: png_mis_a_echelle(
            [(lignes_carte(c[0]), pal_sombre(c[1]))], self.W, self.page_h, alpha=True))

    def _icones(self):
        """Prépare les 17 icônes (cadre vide + 16 objets) à la taille des cases."""
        A = assets()
        pix = base64.b64decode(A['icons']['pix'])
        pal = [rgb12(c) for c in A['icons']['pal']]
        self.icones = []
        for j in range(17):
            rows = [pix[y * 288 + j * 16:y * 288 + j * 16 + 16] for y in range(17)]
            self.icones.append(photo(png_mis_a_echelle([(rows, pal)], self.slot, int(self.slot * 17 / 16))))
        self.slot_h = int(self.slot * 17 / 16)

    # ---------------------------------------------------------- texte du jeu
    def brut(self, nom):
        if nom not in self.raw_cache:
            t = self.textes
            self.raw_cache[nom] = H.decoder_bloc(H.bloc(t.d, t.debut[nom], t.fins))[2] or []
        return self.raw_cache[nom]

    def segments(self, nom):
        """[(col, lig, [(décalage, texte, accent)])] ; les codes @0 @1 @2 changent l'accent."""
        res, accent = [], False
        for col, lig, b in self.brut(nom):
            s = b.decode('latin-1').replace('\xad', '─')
            segs, dec = [], 0
            for m in re.split(r'(@\d)', s):
                if re.fullmatch(r'@\d', m):
                    accent = m[1] != '1'
                elif m:
                    segs.append((dec, m, accent))
                    dec += len(m)
            res.append((col, lig, segs))
        return res

    def dessiner_page(self, nom, couleurs, valides, panneau=False):
        """Écrit le texte sur le parchemin ; repère les blocs de choix cliquables."""
        cv = self.cv
        cv.delete('texte')
        self.groupes, self.survol = [], None
        clair = rgb12(couleurs[0])
        normal = melanger(clair, (255, 255, 255), 0.6)       # texte éclairci
        accent = melanger(clair, (255, 255, 255), 0.92)
        self.c_normal, self.c_accent, self.c_survol = hexa(normal), hexa(accent), '#ffe27a'
        lignes = self.segments(nom)
        if panneau and lignes:         # pages d'introduction : texte plus large que le parchemin
            bas = (max(l for _, l, _ in lignes) + 3) * self.lh
            cv.create_rectangle(7 * self.cell, 0, 69 * self.cell, max(bas, self.Hv), tags='texte',
                                fill=hexa(tuple(int(v * 0.5) for v in rgb12(couleurs[2]))), outline=hexa(rgb12(couleurs[0])), width=3)
        courant, prec = None, None
        for col, lig, segs in lignes:
            plain = ''.join(s[1] for s in segs)
            m = re.match(r'\s*<\s*F(\d)\s*>', plain)
            if m:
                courant = int(m.group(1))
                self.groupes.append({'k': courant, 'items': [], 'rect': [10 ** 6, 10 ** 6, -1, -1]})
            elif courant is not None and (prec is None or lig != prec + 1 or not plain.strip()):
                courant = None
            y = lig * self.lh
            ids = []
            for dec, t, acc in segs:
                x = (col + dec) * self.cell
                it = cv.create_text(x, y, text=t, anchor='nw', tags='texte',
                                    fill=self.c_accent if acc else self.c_normal,
                                    font=self.f_txt_gras if acc else self.f_txt)
                ids.append((it, acc))
            if courant is not None and ids and self.groupes[-1]['k'] == courant:
                g = self.groupes[-1]
                g['items'] += ids
                x0 = col * self.cell
                x1 = (col + len(plain)) * self.cell
                r = g['rect']
                r[0], r[1] = min(r[0], x0), min(r[1], y)
                r[2], r[3] = max(r[2], x1), max(r[3], y + self.lh)
            prec = lig
        self.groupes = [g for g in self.groupes if g['k'] in valides]
        if lignes:
            lm = [l for _, l, _ in lignes]
            self.bas_contenu = (max(lm) + 2.5) * self.lh
            return min(lm), max(lm)
        self.bas_contenu = 0
        return 0, 0

    def decalage_initial(self, premiere, derniere):
        off = (premiere - 2) * self.lh
        off = min(off, (derniere + 3) * self.lh - self.Hv)
        return max(0, off)

    # ----------------------------------------------------------- défilement
    def _sb_cmd(self, *args):
        if args[0] == 'moveto':
            self.fixer_decalage(float(args[1]) * self.page_h)
        elif args[0] == 'scroll':
            n = int(args[1])
            self.defiler(n * (self.Hv * 0.9 if args[2] == 'pages' else self.lh))

    def fixer_decalage(self, v):
        maxi = max(0, self.page_h - self.Hv)
        self.off = int(max(0, min(maxi, v)))
        self.cv.yview_moveto(self.off / float(self.page_h))
        self.cv.coords(self.fond_id, 0, self.off)
        self.sb.set(self.off / float(self.page_h), (self.off + self.Hv) / float(self.page_h))
        self._fleches()

    def defiler(self, delta):
        if self.mode in ('jeu', 'intro'):
            self.fixer_decalage(self.off + delta)

    def molette(self, ev):
        self.defiler(-ev.delta / (120.0 if abs(ev.delta) >= 120 else 1.0) * 3 * self.lh)

    def _fleches(self):
        cv = self.cv
        cv.delete('fleche')
        if self.mode not in ('jeu', 'intro'):
            return
        maxi = max(0, self.page_h - self.Hv)
        x = min(self.W, self.cv.winfo_width()) - max(34, int(46 * self.SX / 1.4))
        for sens, ok in (('haut', self.off > 0), ('bas', self.off < maxi and self.off + self.Hv < self.bas_contenu)):
            if not ok:
                continue
            h = 13
            y = self.off + (22 if sens == 'haut' else self.Hv - 22)
            s = -1 if sens == 'haut' else 1          # sommet du triangle vers le haut / le bas
            for dx, col in ((1, '#000'), (0, '#ffe9b0')):
                cv.create_polygon(x - 15 + dx, y - s * h + dx, x + 15 + dx, y - s * h + dx, x + dx, y + s * h + dx,
                                  fill=col, outline=col, tags='fleche')
        cv.tag_raise('fleche')

    # -------------------------------------------------------------- survol
    def _groupe_sous(self, ev):
        x, y = self.cv.canvasx(ev.x), self.cv.canvasy(ev.y)
        for g in self.groupes:
            r = g['rect']
            if r[0] - 6 <= x <= r[2] + 6 and r[1] - 2 <= y <= r[3] + 2:
                return g
        return None

    def mouvement(self, ev):
        if self.mode == 'jeu':
            self._survoler(self._groupe_sous(ev))

    def _survoler(self, g):
        if g is self.survol:
            return
        cv = self.cv
        if self.survol:
            for it, acc in self.survol['items']:
                cv.itemconfig(it, fill=self.c_accent if acc else self.c_normal)
            cv.delete('cadre')
        self.survol = g
        if g:
            for it, _ in g['items']:
                cv.itemconfig(it, fill=self.c_survol)
            r = g['rect']
            cv.create_rectangle(r[0] - 8, r[1] - 1, r[2] + 8, r[3] + 1, outline=self.c_survol,
                                tags=('texte', 'cadre'))
            cv.config(cursor='hand2')
        else:
            cv.config(cursor='')

    def clic(self, ev):
        if self.mode in ('titre', 'intro'):
            self.suite_intro()
        elif self.mode == 'jeu':
            g = self._groupe_sous(ev)
            if g:
                self.choisir(g['k'])

    # ------------------------------------------------------------ barre d'état
    def maj_etat(self, st=None):
        e = self.etat
        e.delete('all')
        if st is None:
            e.configure(height=4)
            return
        w, cols, s, sh = self.sbw, self.cols, self.slot, self.slot_h
        pad = max(4, (w - cols * (s + 2)) // 2)
        self.zones_obj = []
        for b in range(16):                         # objets : l'icône quand on le porte, sinon la case vide
            r, c = divmod(b, cols)
            x, y = pad + c * (s + 2), 4 + r * (sh + 2)
            j = b + 1 if H._bit(st['W'], b) else 0
            e.create_image(x, y, anchor='nw', image=self.icones[j])
            self.zones_obj.append((x, x + s, y, y + sh, b, j != 0))
        y = 4 + ((16 + cols - 1) // cols) * (sh + 2) + 10
        lh = self.f_ui_gras.metrics('linespace')
        e.create_text(pad, y, text='Vie  %d' % st['vie'], anchor='nw', fill=CLAIR, font=self.f_ui_gras)
        y += lh + 6
        pas = (w - 2 * pad) / 16.0                  # 32 coeurs sur 2 rangées
        for i in range(H.VIE_MAX_BARRE):
            self._coeur(pad + (i % 16) * pas + pas / 2, y + (i // 16) * pas * 1.05 + pas / 2, pas * 0.88,
                        i < max(0, st['vie']))
        y += 2 * pas * 1.05 + 10
        e.create_text(pad, y + lh / 2, text='Or', anchor='w', fill=CLAIR, font=self.f_ui_gras)
        px = pad + self.f_ui_gras.measure('Or') + 14
        r = lh * 0.5
        n = max(0, min(st['or'], 4))
        for i in range(n):
            self._piece(px + r + i * r * 1.15, y + lh / 2, r)
        e.create_text(px + r + max(1, n) * r * 1.15 + r * 0.6, y + lh / 2, text='\u00d7 %d' % st['or'],
                      anchor='w', fill=CLAIR, font=self.f_ui_gras)
        e.configure(height=int(y + lh + 12))

    def _coeur(self, cx, cy, t, plein):
        a, b = t / 2.0, t / 2.0
        pts = [cx, cy + b * 0.95,
               cx - a * 1.15, cy - b * 0.05,
               cx - a * 0.95, cy - b * 0.75,
               cx - a * 0.35, cy - b * 0.9,
               cx, cy - b * 0.45,
               cx + a * 0.35, cy - b * 0.9,
               cx + a * 0.95, cy - b * 0.75,
               cx + a * 1.15, cy - b * 0.05]
        self.etat.create_polygon(pts, smooth=True, splinesteps=10,
                                 fill='#e0151f' if plein else '#2c2420',
                                 outline='#ff7a80' if plein else '#5a4a40')

    def _piece(self, cx, cy, r):
        e = self.etat
        e.create_oval(cx - r, cy - r, cx + r, cy + r, fill='#e8b412', outline='#7a5200', width=2)
        e.create_oval(cx - r * 0.62, cy - r * 0.62, cx + r * 0.62, cy + r * 0.62, outline='#b07f06')
        e.create_arc(cx - r * 0.8, cy - r * 0.8, cx + r * 0.8, cy + r * 0.8, start=100, extent=70,
                     style='arc', outline='#fff2a0', width=2)

    def _infobulle(self, ev):
        for x0, x1, y0, y1, b, port in getattr(self, 'zones_obj', []):
            if x0 <= ev.x <= x1 and y0 <= ev.y <= y1:
                self.lab_msg.config(text=(OBJETS[b] if port else '(emplacement vide : %s)' % OBJETS[b]))
                self._tip = True
                return
        if self._tip:
            self.lab_msg.config(text='')
            self._tip = False

    # ---------------------------------------------------------------- jeu
    def message(self, texte=''):
        self.lab_msg.config(text=texte)

    def demarrer(self):
        self.pret = True
        self.cw = max(self.cv.winfo_width(), 100)
        if self.cv.winfo_height() > 1:
            self.Hv = self.cv.winfo_height()
        self.page_h = max(int(640 * self.SY), self.Hv)
        ox = max(0, (self.cw - self.W) // 2)
        self.cv.configure(scrollregion=(-ox, 0, self.cw - ox, self.page_h))
        self.etat.bind('<Motion>', lambda ev: (self._infobulle(ev)))
        if self.charge:
            try:
                self.hist = H.charger(self.charge)
                self.mode = 'jeu'
                self.afficher()
                self.message('Partie chargée (emplacement %d).' % self.charge)
                return
            except (OSError, ValueError, KeyError, AssertionError, TypeError):
                self.msg_attente = 'Sauvegarde %d introuvable : nouvelle partie.' % self.charge
        if self.sans_intro:
            self.hist = [{'sc': H.IDX['TL1'], 'W': 0x1C00, 'L': 0, 'vie': H.VIE_DEPART, 'or': 0}]
            self.mode = 'jeu'
            self.afficher()
            if self.msg_attente:
                self.message(self.msg_attente)
            return
        self.afficher_titre()

    def activer_commandes(self, actif):
        for cle, b in self.cmds.items():
            b.config(state='normal' if (actif or cle in ('M', 'Q')) else 'disabled')

    def afficher_titre(self, relancer_son=True):
        self.mode = 'titre'
        if relancer_son:
            self.son.intro()
        A = assets()['title']
        pix = base64.b64decode(A['pix'])
        rows = [pix[y * 608:(y + 1) * 608] for y in range(240)]
        wt = min(self.W, int(self.Hv / 480.0 * 608))
        ht = int(wt * 480 / 608)
        self.titre_img = photo(png_mis_a_echelle([(rows, [rgb12(c) for c in A['pal']])], wt, ht))
        cv = self.cv
        cv.delete('texte')
        cv.itemconfig(self.fond_id, image='')
        cv.itemconfig(self.parch_id, image='')
        cv.delete('titre')
        cv.create_image(self.W // 2, (self.Hv - ht) // 2, anchor='n', image=self.titre_img, tags='titre')
        t = 'Appuyez sur une touche ou cliquez pour commencer'
        cv.create_text(self.W // 2 + 1, self.Hv - 15, text=t, fill='#000', font=self.f_ui_gras, tags='titre')
        cv.create_text(self.W // 2, self.Hv - 16, text=t, fill='#ffe9b0', font=self.f_ui_gras, tags='titre')
        self.fixer_decalage(0)
        self.sb.set(0, 1)
        self.activer_commandes(False)
        self.maj_etat(None)
        self.vider_choix()

    def suite_intro(self):
        """Titre -> TIN1 -> ... -> TIN4 -> partie."""
        self.cv.delete('titre')
        self.intro_n += 1
        if self.intro_n > 4:
            self.mode = 'jeu'
            self.intro_n = 0
            self.afficher()
            return
        self.mode = 'intro'
        sc = H.IDX['TC1']
        self.cv.itemconfig(self.fond_id, image=self.image_decor(sc))
        self.cv.itemconfig(self.parch_id, image='')
        c = assets()['scenes'][sc]
        p, d = self.dessiner_page('TIN%d' % self.intro_n, c[1], [], panneau=True)
        self.fixer_decalage(self.decalage_initial(p, d))
        self.message('Introduction %d/4 - une touche ou un clic : page suivante - Échap : sauter l\'introduction'
                     % self.intro_n)
        self.vider_choix()

    def sauter_intro(self):
        self.cv.delete('titre')
        self.mode = 'jeu'
        self.intro_n = 0
        self.afficher()

    def vider_choix(self):
        for w in self.zone_choix.winfo_children():
            w.destroy()

    def afficher(self, message=''):
        st = self.hist[-1]
        self.son.scene(st['sc'])
        sc = st['sc']
        nom = H.SC[sc]['nom']
        c = assets()['scenes'][sc]
        self.cv.delete('titre')
        self.cv.itemconfig(self.fond_id, image=self.image_decor(sc))
        self.cv.itemconfig(self.parch_id, image=self.image_parchemin(sc))
        valides = H.choix_valides(st)
        p, d = self.dessiner_page(nom, c[1], valides)
        self.fixer_decalage(self.decalage_initial(p, d))
        self.maj_etat(st)
        self.activer_commandes(True)
        self.cmds['B'].config(state='normal' if len(self.hist) > 1 else 'disabled')
        # boutons de choix (toujours visibles, même si le texte est plus bas dans le parchemin)
        self.vider_choix()
        texte_choix = self.resumes_choix(nom)
        for k in valides:
            lbl = 'F%d' % k
            r = texte_choix.get(k, '')
            b = self.bouton(self.zone_choix, '%s  %s' % (lbl, r), lambda k=k: self.choisir(k), anchor='w',
                            justify='left', wraplength=self.sbw - 50)
            b.pack(fill='x', padx=2, pady=2)
        if not valides:
            tk.Label(self.zone_choix, text='*** FIN DU JEU ***   (B : retour, Q : quitter)',
                     bg=FOND, fg='#ffd070', font=self.f_ui_gras, wraplength=self.sbw - 30, justify='left').pack(pady=4)
        self.message(message)

    def resumes_choix(self, nom):
        """k -> début du texte du choix (pour les boutons)."""
        res, courant = {}, None
        for col, lig, segs in self.segments(nom):
            plain = ''.join(s[1] for s in segs).strip()
            m = re.match(r'<\s*F(\d)\s*>\s*(.*)', plain)
            if m:
                courant = int(m.group(1))
                res[courant] = m.group(2)
            elif courant is not None and plain:
                res[courant] += ' ' + plain
            else:
                courant = None
        out = dict(res)
        return out

    # ----------------------------------------------------------- actions
    def choisir(self, k):
        if self.mode != 'jeu':
            return
        st = self.hist[-1]
        if k not in H.choix_valides(st):
            self.message("Ce choix n'existe pas dans cette scène.")
            return
        nv = dict(st)
        if H.choisir(nv, k) == 'quitter':
            self.terminer()
            return
        self.hist.append(nv)
        self.afficher()

    def retour(self):
        if self.mode != 'jeu':
            return
        if len(self.hist) > 1:
            self.hist.pop()
            self.afficher('Retour arrière (%d écran(s) en réserve).' % (len(self.hist) - 1))
        else:
            self.message("Pas d'écran antérieur.")

    def sauver(self):
        if self.mode != 'jeu':
            return
        n = dialogue_slot(self, 'SAUVER')
        if n:
            try:
                H.sauver(n, self.hist)
                self.message('Partie sauvée dans %s' % H.fichier_slot(n))
            except OSError as e:
                self.message('Échec de la sauvegarde : %s' % e)
        else:
            self.message('Sauvegarde annulée.')

    def charger(self):
        if self.mode != 'jeu':
            return
        n = dialogue_slot(self, 'CHARGER')
        if n:
            try:
                self.hist[:] = H.charger(n)
                self.afficher('Partie chargée (emplacement %d).' % n)
            except (OSError, ValueError, KeyError, AssertionError, TypeError):
                self.message('Emplacement %d vide ou illisible.' % n)
        else:
            self.message('Chargement annulé.')

    def triche(self):
        if self.mode != 'jeu':
            return
        nv = dialogue_triche(self, self.hist[-1])
        if nv is not None:
            self.hist.append(nv)
            self.afficher('Triche appliquée (B pour l\'annuler).')

    def basculer_son(self):
        self.message(self.son.basculer())

    def quitter(self):
        if dialogue_confirmer(self, 'Quitter le jeu ?'):
            self.terminer()

    def fermer_fenetre(self):
        self.quitter() if self.mode == 'jeu' else self.terminer()

    def terminer(self):
        try:
            self.son.arreter()
        except Exception:
            pass
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    # ------------------------------------------------------------- clavier
    def touche(self, ev):
        ks = ev.keysym
        st = getattr(ev, 'state', 0)
        ctrl = bool(st & 4) if isinstance(st, int) else False
        if ks in ('plus', 'KP_Add', 'equal'):
            return (self.zoom_ui if ctrl else self.zoom)(1.12)
        if ks in ('minus', 'KP_Subtract'):
            return (self.zoom_ui if ctrl else self.zoom)(1 / 1.12)
        if ks in ('0', 'KP_0', 'KP_Insert'):
            return self.ajuster()
        if ks == 'F11':
            return self.plein_ecran()
        if ks == 'Escape' and self.plein:
            return self.plein_ecran()
        c = clavier(ev)
        if c is None:
            return
        if self.mode == 'titre':
            if c == 'Escape':
                self.sauter_intro()
            else:
                self.suite_intro()
            return
        if self.mode == 'intro':
            if c == 'Escape':
                self.sauter_intro()
            elif c == 'Q':
                self.quitter()
            elif c == 'Up':
                self.defiler(-self.lh)
            elif c == 'Down':
                self.defiler(self.lh)
            elif c == 'Prior':
                self.defiler(-self.Hv * 0.9)
            elif c == 'Next':
                self.defiler(self.Hv * 0.9)
            else:
                self.suite_intro()
            return
        if isinstance(c, int):
            self.choisir(c)
        elif c == 'Up':
            self.defiler(-self.lh)
        elif c == 'Down':
            self.defiler(self.lh)
        elif c == 'Prior':
            self.defiler(-self.Hv * 0.9)
        elif c == 'Next':
            self.defiler(self.Hv * 0.9)
        elif c == 'Home':
            self.fixer_decalage(0)
        elif c == 'End':
            self.fixer_decalage(self.page_h)
        elif c == 'B':
            self.retour()
        elif c == 'S':
            self.sauver()
        elif c == 'C':
            self.charger()
        elif c == 'T':
            self.triche()
        elif c == 'M':
            self.basculer_son()
        elif c == 'Q':
            self.quitter()

    def lancer(self):
        self.root.mainloop()


# ==================================================================== main
def main():
    ap = argparse.ArgumentParser(description='HEROS - version graphique')
    ap.add_argument('--data', metavar='FICHIER',
                    help='fichier DataHeros (par défaut : cherché dans le dossier du programme)')
    ap.add_argument('--sans-intro', action='store_true', help="saute le titre et l'introduction (village, Vie 28)")
    ap.add_argument('--charge', type=int, metavar='N', help='reprend la sauvegarde N')
    ap.add_argument('--no-sound', '--sans-son', dest='sans_son', action='store_true',
                    help='aucun son (par défaut la musique est jouée si la machine a une sortie son)')
    ap.add_argument('--echelle', type=float, metavar='F',
                    help='zoom du texte d\'aventure : 0.5 à 4 (défaut : automatique selon l\'écran ; variable HEROS_ECHELLE)')
    a = ap.parse_args()
    textes = H.Textes(H.trouver_data(a.data))
    if not a.sans_son:
        H.MOTEUR.activer()
    ech = a.echelle
    if not ech:
        try:
            ech = float(os.environ['HEROS_ECHELLE'])
        except (KeyError, ValueError):
            ech = None
    ech = max(0.5, min(4.0, ech)) if ech else None
    try:
        app = Appli(textes, ech, a.sans_intro, a.charge, H.MOTEUR)
    except tk.TclError as e:
        sys.exit("Impossible d'ouvrir une fenêtre graphique : %s" % e)
    app.lancer()


_BLOB = """
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
5ecup71/ray0/XdNP8ZbMnco7PBG5rmzZ2qfGCGKXVE9mobStz+kuc0eoNBT21MP/NknGqtm37Wl5n0UH8QF6r6ywS4J5R+rSinjuPmVdciPJ6
TVu/lln6kSo3IPd1capWYq5nMLOcnU0fSr5YzWvk+UOlLm6xK6BeirAnGE+SOEbBcuWwt7bPtQkHI//J1ThO1umlTq/OR2zblK7ka/B+S2Otow
W1XPg+aX1ZtdsEPwbwBnUmkSsZZF8jJ2rNjQYXTHO6rVi89fwYqJFTIXon+EY9eNk/BPrNHuqxg3WefrHf0FvlYK+SYz2I2tcpjlcnN4D9TfR4
Mm3hwv/vx7+x3oGZG2HxC1huRodf4WUeR+t9wf7cubbE6YPrc4EzRwHzREJvPWXuwWj2Sluo0X8+2PtpPpw/MBzYdwc4qs1eLY7VkDH7khSbP+
8d/H/od2rK6dGU2aasCEf7eY3Kxm3zf3lPkFhy2Vu51jV+Ta3+T4pTQTzmb8kQzJforVOAurfUyT9BrpIRf2rxVJH/3dwb2FeZ9mQjxFC7exN5
YjvPDzXXfO/5JY60J5/fafzu8Pj7MqfyejJeE3f3SvKdaH9Nl93nE+M9742/YvBjf/zA+11UHjk1eFJYi6Pm3ZPs7cZyv2VvRG5/sWcDpkDiWo
Kal7nmTI7P1HrNxGukYh5luY/u2XmMc0M6/yBjxhAzn0Xu637cv9bJV7X+8HePfeYF3xZ+Lvi7h3/zo+iPze/B+rfLa9m7ibUOovc7vrcfWc3J
ReaGlnvIZ1tjgWeHxlg85xnIa/VcIX9AjsHx+2NPVsV1Fu/C6li2147VJPN67nHOS79hPzbW0qm9E/3YnEf579G6n9dzp9Zbvieuo7H+i7XGnj
9T7gN73xvXqHVzjfmU7yDe0zhz+A7ynJr3U9ca9w3yvs7cI+r+3l5vtSfD2D736t+d/tlYf/lsUxb5ytvpjalc27rGlAvWt7Enm3vG/mxTrgQ5
/tFcy6Unv3+J3/6CMVx47dJci/Y8/rTz6T7KfePe3LVk8pH5PTivWDPdWlPOgyZ7bnytT9y+rnH2m3Pr2LWxe62Vg3RwXbvX7sgGf0BGvM9ZuW
TvNXRQ95rLz+mvHvzqz//+l/tf/Y//86tHn33/H49/9T9+tRrs8/z5EN96N9/djPTw6y+yaT/4lxOd/kaTO/1tHIbi874a48MbFxc/LLdfDPP8
ff7DF2s6fvh6nJfhdM8XX5Z73c6O3nzp6PbaLctXf/h72ZavhvhqOsOhju6Ce/LmT/kPn8fbL+mPJ38ghtOzbr8qxv7w9vTcN6f3OsMft1+Nf3
ya//Lt6X1OS3T3YjwtqYtvb8t7zX6c6OqrId5/cTL1v/wyb/dhPr//ObzkT+O5+cOffB3j306+zDwPFG+vaZn/s44xflneeX74db3XG3av8W9X
9r2evP2vMsa5da/QutdvxHt933qvF2W+Ip+vP61Q0v88bYdH//7rR1enbfDtw7999d3tZ/Or1y++e/3566++e/T5d69f/e3rV5+/ePX69Tffvf
phePnd7aPw7cNHX3/3aPjm1Q9ffffqdfq3R69fvXr04uWrzz//+rtXf7v5bnr21el+r9X9Xq+f+/b0+/n6+buHz776bvrr+bnr5149+jz/2+vX
n3/17fqcR9+8/u7VZ9++evQ6nJ717Xefv96ef7u9h3jvm+9ePd2GdfX8bW9Y01/Dd6+enV/52/SIb9ZH/JBm5cnVw3I4+CY8cjgmil8MS3zh4n
0Y56ff18Vmh8PDxjn92/31abW/dPObz2ET/pYdjmWpVS8iP7T1Xre42Nfu73M9aPxwwMYRh6OM8RXfhN88tDchbujm4bjj9/o7tYTJH5uHg+xD
O/7t6e6hlfeqwuSNJUy2bfD8+fenbRD+MT/66r/ePn35cBhOV0zl93/cPv/6H8tnL29ff/HNwz+++Pa/8u+v/u95+vz0lPkfX42vHn/1j1h+fv
Pqd19+O/1w/fV3d79+OT78v+rP8PCr7948+Xr8jOZXL8Zvys/w7Ov/ur96+d2zz7+5/YP/9tVf0s+7Z+p90u8vH8r3Sb/fvtqG9ej752l30zDl
XXTeqf8BNsC3ZXfHMH0Jf/ic8mqdZm14CjG7mHf3afff/id85HdZ9I/06Ilf8F55dzPRe16VfOquT/OItslv82qx3bWeiLy7/fXwd4DFh9u8u0
+7ou769USkXTTS/UvEks4D33bR+WSzMeZd9GL8bVVV5xOB9/pyse8Fau98uuq95qc4X9+xe8EYP//jgfean97Cvd7gfPltWrZt8Ozt09M2ePHt
m/++drf/z/XfX/35xd/jX67/dP/Diz+9vbv+dvnrzZ+ulvCdv7/59un/DuP09xv38H/d/IPS3+/+X/nZ9Pe/hT+Jzzp57/JZee/y2Xd4rzSsR/
9+GtbrH/7w5vUPP5y+//Dv6f/Tz9/97jef/+63v/nh9P15+v/t99+8fvSX3/zm9R9PP/9Y/n/9ff3c+T7r/eCe7PO/K/c83es3r/+y3if/3P5/
vZe4T37Hcp/6Xuv/v9mG9fDp2+3QfjPQK1QvL6fhPh2Aq9POOG2C2b84H9phfvM2iUumXs6bIW2qNyudYHn61UjT+dBeu2RnfPENeVQvYxbxUv
Qujx777V6/cfNbd9qBJ7F7fz60g0tBrs8XLnpPIvr7pEJP73NWRbdfn/52fXp+SDbL705m9jwuD79wy5vzof1i+OZpEhhZVMfr8+E4zUMiTsxc
HZ/mKI/R0dv8zufD8TILms8jv9fpmf9p3+t1Flqv5b2mYZuvaeH3On0ujfGNuJcfWu81udm0VU9z9321196ezXatcrKILypHqKA/FpWjVNCmav
7jt58/+v63j4c/vvlzVkWbyvndF6///LvHf/zLv//5r/dJFW0q58+P/td/PBn+9va/v3r4h1eb6tHvk99Tvk/5/X/+6v978Kv7t9//9/cnx+T3
v0+eyYPfP3n6+NmDx88fP33w+Mmzx/+WbdUHv3909fDqweNnnz1+8OT5k+0PZ2vvwe9/ffX0wbNHjx88/Ld/ewD3ef7Z1XafR1dPH+J9Pnv06M
Gj50+uHjx68vwZ3Ofx6cIH21/Pf1hvtlqE5s3ONsLpZg9P7/Ps6fMHj3/9ZOdW7ff6J7nVjzJX2xo+vXpw9fDBo0e4fI+eXT073eK0ER49fPpw
75UuvM/ZdOrc5+rRg9OtHr77pty9wXu/QXsqzvbAg98/+/XVgycPnz1gR8uaiw+1Nrvn9PmjqwfPnz64enr1nqt8/E4f7p1+jnf6154nfUJ+2j
l6b5lxvnx95uMnz69+8tv8HLfhwaHtKa6rk63w+KS7HrH3eXJ6xZNKe3SSdo+P6dJf6n32Fuy9d1CyD67O/3Za3POH3m9kF9xq12pZ993DZ88f
PHv8vvP98OH5Jicj9vl7Du/4O3XU/slfPs/Ur88fefbr9xleNtBP873uAzHp7yL2L7jXrjx58vhskjw82Z0fw7a5UE7+OLd4F8P3ZzmQX8ZcPH
v69Ly7uHWB2+7Qizx7+sy4iz7Se67Aw0ermHn4fsf54G12T9/j8+SuvvuTJ8/fw774QPf5QLOzfuTqZKgIoXL5BP24y/UvO80fyi198vjh2W5/
hHNzslQfPPv18/M/HhzVYY30Iyq3n+mtHp4k4pPTfw+f/mh32p30n+Cdfrw7PX70688ePPrs4Xk/P3nyY95sb95/ujf7UW/2yUT8QLfYkM3TEj
w1vaWLlia5S89PfsnV44cCwz7po+dnffTk/Ld/hTvtupU/xTs17eJtH1w9f/D8swdPcCdt//Ts8b/ADXIM5umj9ezsYhC7d7p6fF6A7XbvaeR9
QrA/3enTnX6Rezyp2ALXrZ95d1V98D57wcx/9fc5gI+/v/C++Fa7UPsHfKvDeu4XOr5/+gW84K3OFLlPK/hpX304FsDP6S67+PEvbkQ/zl1Ot3
j+7GTevBcCsnOH93+HT3f4+azFp/3w8ecB7NhMG/kQvsdPcK9DNv/Paow/4g7awbEO+1U7oe7EJua64kwzvnr02Zlq/CHvsrdGjx+egepnz85j
evz03X3Fw/fZmeMnz56c40HvwRD6gLSsD0Xhv5zetTdLjx8dmqUfk3H20/Dg9vHeDzbnR3fmB1q7j/8+P8/Z/klv9aNIlbePV4H52fOfIW/0Z8
Zm/ckk8M9TRv3T74RPA/znHeCHC9988PF9AI77hwuYfdqeHyqz4J3yPY+91ukvf/3TX3/4/lye6C9/+luuUPHp69PXp69PX5++fo5fN+5c7CPe
nb7vbz5Nx6evT1+tc3L3Yi34shbVORdB/DQpn74+fZn6ZKvVlyrT3d58Oiufvj598a9id53PyvL2S0drQbhfwJv/0murf/r+5Xyfz8nJ7lrtrb
ub03k5/386Jz+zd61fpW4z1G4/+Vb3tOnB88/79ff67+X3LBuMa9afN9vP/JXvmT+n/naD18DvN/q91ufebM8m8T713uef23VE1j34u5rjvB6X
q5f5d7cWr1y+GuPVy3G5te7L5ii9Y3nP9P/n/bHJ0/U62vbJ+n2Sq3Tr159z+Zn/Xf39LItP318My5svt/8//TwXsNz+fZPV8Sy7b32V2Web5z
bvzdP/3+Wf19uc3eX3Od//9Kz7G/C5z3Wp09/v+O+U9ML6+Zh0xPm5m/+xjfk89ntK/smX52fmOUrrkf79NLfrPcpnb87P3z6/PvP8XmkO188l
Wy69M52uX+fvFueLf+d/JzHP8DneB7sUusV+d3lty57c2dOwXwj32439WX4W8G+49+VZ0Nff37TOWD0r962zAn9vnxUXr74+nQl4v6tzdea1aO
y4xOu9s5Lvm5/TOCvX4qzAWhprW9cyn40v8WyI3z33m+/W83/aa+yMJFuI+FlY93/yH857lZ2j0/c9ybOyFtXN/sdaYDfrjrrft7Oa/74+t65F
PO/19d9f2PZY/vzti3S/dAbXs5vn8Zq9p57HIguYDNJnJZ+J9Ldqf1U9Is8K3XAbU+odJvfLfuPygp+zegblHm+elRuuz3r7n25s3UNKN9ZxKt
14/tzL85k47ZEb2PMvx/gwnZWrF7beZGfFHAfIWDwrcu280CegV7Y9YOkRrmfevrDPyh2eke19Fqp7n/I+jwmXSjolv2fdx0nGr++27f+zHsrX
rHv2rp6VolPiqpfWZ61nJeuFuJ3N9Z5Zb+V75H2zvvt6ftO52wpfz0X+XHfPxtw4G0rfBLsX9UnXGHvUkP9t26meFYKz0tQd5nPwMy09Is+G/R
5k7FN+Vra5753Vp2dbK5/RYkudzsrp359+Xc9Kfcd6jvlZUfpqk4mwB/kZEGfH1zWPbE2FHpFn5qx3rtPe3GyhmPXlfd1Xyz3HpWLWJ0lOx+1z
q33UOit0m+yt6Ld9nN5xyXqryMbrdD423Zp8lKRrs12YPit0XHleljOU9FB611jssBeNb25zUePspH/P9temT9D+ut89K1yP3Df1jLXvxVm5EW
flRuzVznNse86yydK/QXyLnzt5VrjOofOZOJ0HPLvprCzrOUl7Qp1r8NPumzYsnpX1d7Vmt801RBsN9Idli531y4syB8lmqXE/M+a36Zh5PVtb
3CNm+yvpm7nYSXBWkh6irIfu8hlLegvw4XxWNzs0645Nf8TbdD7O9uBdeR6cTfRR6lnOfk+UekSeFUMWyZ/bPDftL8t+6OsV/rvwK5SPYegO9C
UO6LOunrHOylm2ne2k9I22b9VvEm+AM/j1Zn/xs4vvt609Kb0lfjdtWHFWSKyt1/6LtBki6pUv2E9+VnySt+kM3F7nNajnIsvtvKfvq67Y5P0m
y/KZUGflLvsW4C8UGXWdba/qk1QfZpMt6brNf9r2/iY//NoAZH6b9FY6H0vyUbazluzEu6SXora9qC1r9FnJ857tr1uJf5ky19YrZPozws9AWW
qdO6VXBF5k4GBNnIqd8foedy9X2U+rLHy52Uy3N4bvLfVTuubqq3E+21im/rxBLKOe9zrePVlTzkpMcxGZ3JN6xQu5yG0w7p/Is/LlignFtJeo
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
Iv1n/kPZUKL5LevqJ9gnHTTLSAig9epZMvcGDaXtrhfVxgfbv85wLnyVdhzr78/BTymr543iBW3juma4Y4Fmd3/9oYkfKSpp8MYEWIvabk/ymc
JZbMntBeh1FjqH/Nl8HeysxisLt0rlzZ/GPlP1Tud2fny0f1s1RnUPQUh8w7D5yTIeugVVgxlYZ+q/6cfalKndjputzgPOlFrl3J+3rqU2XAk9
WthftAuAaoA0DmCf5q8+2n8pJR9yGoOGxC7JVyk0sfYy9W4xLzCKE+/Ee/rOQv0dU9mZnlKxaxIp4HrP6F/PsrwYRt5i2dUpMTNBTmN8CK0wMf
YZa4gZVFxErtw3KB3uHsPNrh/MJ++VLNg8g8MYzBbehhVlhZ/g/BSLtfcjBrhHwvFnOVWNbr8Wo1Lr42T50f9vOxl57vaLEXz1depBxf1//6uB
JepS2cMQF7h1jJ54oBrRSvHUd0FtpYsSS3l7AyoA+Lx03OPZp+gUo+uyA/+S34teA5QmZ3X/669S0x5jKtmVVdW5n3HIleTi/mJZOyNus61B/D
in4+dXXvZq57OSVfkbCi8u+Fc+TaqB33+gokexLoqDz0WU+3wgp6zy+4h2v+WmP0zy17ndduzRpIoPNwSmM7aqXA3Lyffzd//dndkzHXkVZyzc
/hsdcD0ZWKtfQxa+JIa1Y7V7R61adqxlY5T6xU/xK4YFrNuOo/+sep61/kPLkqec9L0TPWPD7S70CDa0u8OOgxnsdK5VHneb/AM0b9LvREl/wX
ZV5wnEsp8+/CPMnHXzl3b9aCj7SSJd+LHHuRs+TSxXmJmqeonyuduO//obqXFtNZKS9q5CuUd5/WuK7/xWMvEsNJWBnPYAXrTsTTks160f6eWD
MeK9+UPEdCdF3euM7Wgbcjm73CurI1f3Ce5H93neuU75fuseFjL65R2NOzRKrZ2no/N0r+8GflKVqfRTy/6M8shkrniqr/pcpU/9+v//v1/9cv
If7625e//Y//9v/87T/+y9cvD19//8eXv//+z9++/P3y8PXL33/7/fcvf//ln1+//Hr5/Z9fft1//vLr199/+/LLP367fPnl636Tf/zy636vX/
Y7PPzjty+//ub+98svv/7X//zyt//+sfy/69/+43/+7X/89//vb//xt0f7/vw43a+P0/v3RzN9378/P5r7/rv3q/+b+51xt5mu+XfTtL/m9dnf
x/1s7+ExrH+c1v3jbd3vJrz/Hlbw57+7LXP/7rbNO7//8357f/9wG/L6X8Pt3fP7K/ksPP/+/fXJbP41fg+/48//0H7903t5/en5/WttvH/zej
Vb567TfjTcf5h0veJj7ksh3jY85jdz2X++vMZrtd9uf8z9dk/OEmo/3sNt7+73zyZcs/h68DPdU950//z5wXud7q+PdtuPJfr833wod/m+h+su
3LiR+5t3FyrE221X+vrvr+GzuV9jqG/Ka8r33/82PRnrPof3HQLv1fvfwxHt9V/3x7z6z3DKj+vXyv5ZxzWT33/4OdzfhM/i1a2L2Fbcb2PeWR
jmrufkHuv1ycs3X0aHT39tk1ySXff32O1h0nu+f/j870+P5f4p1Yl/z/f3MsXh7+79bMM3s2A46a6Jp0dG6cKbKxfvazrd3wTq18Xf370+Fka+
luffr4fZbuz503/79e6e3WPt3w17/rc9THnDX9L7u/cVX79///463fzz7WGk+2zy7crz7+vAXX/3uZhYUrw/m839Pu4d/mt//ul1/4y3/fpe/P
vb17tbf99cqPbo08B1D4c7V/qI9zfhM3aYtg6nry6ku7pUZb/Ut/1xTbp/oeTa/TYONxc3PrhvvW4PSs8fnjP+vH/fXGvY3/9bCuu8XJ7DpFsn
5fU/OTxM73ntu/u6a1Vef7jdvv73n93rvLzta/KJvv/7m//8y3UJ95+M39NCWnsJr39//+7xgzTb/lqn/f3G978/9v7aOrcfmrhHhL1u/8y8pd
K+98nXf/+7G4MK139/jB3/dgrXL8gxD6777VPq/f7769gfx+1vfml/D+/rHtKJ6fLkn3/y99/DRXf93Tpwtpb7/dz6djKWXh4wPr9f466lGa6/
+7z3x/vmPwvrP9NI9/KYc/mXXxf763dnqdt/3XWPa+/icez2Gbj++17QfQt7hHvM6ZvB92/Mm2td0uu/v37jUgW3HtxreLiG9/0e1v3kXtP+ur
2U0XSN69+dk6/+cwn4vYZr7vDh97Bvj0a4/vu1ewq0z2vML/f3sl8zG6gPO8b3a++utTsD0mvbseTXf7dfgsmvq9AW+br/7mL8mbWnOPH6O5y8
uNcf1pOTfFte+fPn6+//7W6bLAK6pyjj7K91XOuDS3Hi9QvpTnrvxn9+38P197f9vr/WcGb5z9pdk45f/55d/++PJu9/Htf+9Yf915XvntyeGH
Dw7lNnf/399x2D/nq/x7PKfbm4y5/V/Pp/D6/fpXj39DmO4foHSaZvpnOhWrj+7jP11/b+FNnu3931j6Xg/TauZLtj0rjP3JLr/2TC+g170AbP
7/DnHsytH78X+T29SEy5z9TvQdfw+n29zq+X+Ppf/frf/Ps23kJyM9/DXubwsD2H6+b3Y+P3sbwHhff/tM1P3za4/j5eMGmvd2vgLdzf/2xCWe
ihnAPhOf3z7Z//0/46wnU3IY4MlEEXQwrXfwqaIOm5fVnP79VeFvrV5Nb3+hzWi9tvuxROO1zGdfDVrxO/J/rbWCd15co7Lv5x1/85XH+/B72W
538PuHP7vsebe/973FFKJWkPusXX79b46Pf+8Prj+vfXOq5Dd65ewlkyLTe3boyPS8LzOwwbf35cwp7m1o9Z4fq7sybLpt/iPvMMZ7IveZZzfx
2DdYc7u9YQE/u959Wt1df9/e6Xwr9n8fo/2e2Wnns/Q9z1v37zZZ6tB2vwZx8vuPewTfH6v5v4+v31d6Pq+2u9hfWWLBqS7JiPfU3cg8Y9FnKf
+/cQO/prenvycZZ//6bIT0Q6r7v+/v6X1zgy/Fqu/0b2oHgehuthZ7+3+evv11fag5wc2BafP3z+eP3Ttc0xmLv+1v8c17zfc8w3fyaT8qg7f0
IcbNz1d9d3j/nk6/8crv/6+i1Kfxp3Fvk17c6BZSyy7/41udfq1qz7bF2M8JzXjx9hD+Vvd6absPa7GAN15frffb0/XsMYu7s14ve6p6cQfySM
48h7xOdlDOvJfYbp+TeyB7n3H+Ihfx7vv7tfDXz+JuL7W1hPviQXzu4c/zyna59iS1M+E/zvlj6/HLvG1+9zPZ/7uevrqUna9b95zDgrU79kw/
WPsZD/fdgXwvM/+jzG720FD/n8DXL94frv5695f4k2JV15//717o/p95vX+Pq9TFkY9fWvP5zp01ewlnmP63fza2J/nWOK30LscYnxj4+fy5r0
ewNe/3um28P1v8Z9BK9/xEr6eo85l/854uCS7+9x6R/zHt9/zIunNKYq7v/Pfj8w8Tr7c3Ye4zWKudfm99qQ/5iQV7jYYoq5gH0Pr93HK64kfT
dxn+32z/8lrX+fv0zp+juKlR/dfo33j9d/CfvPFHMBG/adgLtw/0jJca91JM/v4rYtfI+YiPuDw8b9Sp/f5RFuFH6L97/HWN/vQe75n8N9i3XG
fv3T+4S1bvL9w3Xq9vexmbimQvxjAt6/+fhJuv4Rv/H67+fsLdQW/OcWzhUTX7/H7j3GMSbef7rmPTLt0RGT+94f938b7m/g+ru43cy3eP94/f
1aNaHOEWI/jyd7z/f30hbBau6VPr+7zuGahTxhfU37cb7++fldHu7Phtdw/xR7+D3I578pv037UPycTfjdJew9+fnvPofxkrHTml+/CfWNuG7f
42dB/nM5QjrDw/iRPz/uMVYL53qsVVzzdZ/ucP+cf5T6g70n/EL94X4tz+/qPJurO6Tr7/aNeM1MeH4b44xc2k/33+JYrM/18flf02v1a8q4tZ
POyer5b+E5l30dTLh/u+uQnz/muXGfT+svPd6FvH9XQ9if89Wvf3sXSRy5bpm/3nPtMMVOcd9Kn5vDdKl1xs/S5Hg13T+dQfeYc7zHzx9um+pU
4ba3cP6mPMXtgc4+wZ9R8f4hhsmvdUp1NhPPpQt/fheD3uL9/f4T41Hp+U3cd8dv5h33A4+j+Py59hNqrPdnWHcm5Av5+cPn72OWezyThOtv71
Dbi/8u6zqu7Vg/teka5ucJ565N6/6Otb98zcr98TNJ9dvy2YS9Idayp3Survj8/gwI1wzub6F2mF9/fsx8/4SHsH7Y8+drFs4GeP3+mqfXn54L
7n8tuCfPD+vSP792/UMNvNRm05oI/0718rimoM7/PV9fxM7h/Seol6f7v38neyKsyXBN4f6p10Cfv7xPfH7/GeL9Yd+qn/+54IC8/mtcg+X1p3
4Be/0H71+8/tDm+fvff/099np+/edvX359+Mc/v/zy298vXy6//P7ll7//8uXiWkG/PXz59fffvn759beHX7/8cvn14cvff9//9evll9++/PLr
5et//c///F8sL61Q
"""

if __name__ == '__main__':
    main()
