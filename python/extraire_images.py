#!/usr/bin/env python3
"""Extracteur d'images du jeu HEROS (Amiga) -> PNG.

Usage : python3 extraire_images.py [heroschip.bin] [dossier_sortie]

Comment le jeu fabrique ses images (retrouvé dans le code, routine blitter 0x16222) :
  * Une "planche" de 120 tuiles de 32x32 pixels est stockée en 0x26674 : 2 plans de
    640x192 (80 octets par ligne, 15360 octets par plan). Tuile k : ligne k//20, colonne k%20,
    adresse = 0x26674 + (k//20)*0xA00 + (k%20)*4.
  * Chaque décor est une CARTE : en-tete de 8 octets (taille d'un plan, tampon de destination)
    puis des lignes de 19 numéros de tuile, chacune terminée par 0xFF, la carte par 0x00.
    ATTENTION : numéro de tuile = octet - 1 (le jeu fait "subq.b #1,d0").
  * Un enregistrement de scène contient, juste AVANT son nom (24 octets), 6 pointeurs
    (relatifs à A6 = 0x15468) :  carte du parchemin, couleurs du parchemin,
    carte du décor (256 lignes), couleurs du décor, carte du sol (64 lignes), couleurs du sol.
  * Les couleurs sont 3 mots $0RGB (COLOR01..03 ; l'indice 0 est transparent/noir).
    Le jeu les fait en plus "vaciller" ligne par ligne (copper) : ici on prend la couleur de base.
"""
import os, struct, sys
import numpy as np
from PIL import Image, ImageDraw

fic = sys.argv[1] if len(sys.argv) > 1 else "heroschip.bin"
sortie = sys.argv[2] if len(sys.argv) > 2 else "images_heros"
os.makedirs(os.path.join(sortie, "decors"), exist_ok=True)
d = open(fic, "rb").read()
a = np.frombuffer(d, dtype=np.uint8)

A6, T0, TAILLE_SCENE, NB_SCENES = 0x15468, 0x16DA6, 58, 211
PLANCHE = 0x26674

def L(x): return struct.unpack(">I", d[x:x + 4])[0]

# ---------- petits utilitaires ----------
def plan(adr, larg_oct, haut):
    return np.unpackbits(a[adr:adr + larg_oct * haut].reshape(haut, larg_oct), axis=1)

def palette_amiga(adr, n):
    return [((c >> 8 & 15) * 17, (c >> 4 & 15) * 17, (c & 15) * 17)
            for c in struct.unpack(">%dH" % n, d[adr:adr + 2 * n])]

def colorier(indices, p):
    return Image.fromarray(np.array(p, dtype=np.uint8)[indices])

def palette_triplet(adr):
    """3 couleurs -> palette 4 entrees (indice 0 = noir, indice k = couleur k-1)."""
    return [(0, 0, 0)] + palette_amiga(adr, 3)

GRIS = [(0, 0, 0), (85, 85, 85), (170, 170, 170), (255, 255, 255)]

# ---------- 1) ecran-titre ----------
p = [plan(x, 76, 240) for x in (0x37064, 0x2E1E4, 0x3B7A4, 0x32924)]
v = sum(pl.astype(np.uint8) << i for i, pl in enumerate(p))
im = colorier(v, palette_amiga(0x15AAE, 16))
im.resize((im.width, im.height * 2), Image.NEAREST).save(os.path.join(sortie, "titre.png"))

# ---------- 2) planche de tuiles ----------
def tuile(k):
    base = PLANCHE + (k // 20) * 0xA00 + (k % 20) * 4
    out = np.zeros((32, 32), dtype=np.uint8)
    for pl in range(2):
        for y in range(32):
            out[y] += (np.unpackbits(a[base + pl * 15360 + y * 80: base + pl * 15360 + y * 80 + 4]) << pl).astype(np.uint8)
    return out
TUILES = [tuile(k) for k in range(120)]

planche = np.zeros((192, 640), dtype=np.uint8)
for k in range(120):
    planche[(k // 20) * 32:(k // 20) * 32 + 32, (k % 20) * 32:(k % 20) * 32 + 32] = TUILES[k]
img = colorier(planche, GRIS).resize((1280, 384), Image.NEAREST).convert("RGB")
dr = ImageDraw.Draw(img)
for k in range(120):
    x, y = (k % 20) * 64, (k // 20) * 64
    dr.rectangle([x, y, x + 63, y + 63], outline=(255, 0, 0))
    dr.text((x + 3, y + 3), str(k + 1), fill=(255, 0, 0))   # numero tel qu'ecrit dans les cartes
img.save(os.path.join(sortie, "planche_tuiles.png"))

# ---------- 3) cartes ----------
def carte(adr):
    """adr = pointeur de la scene (adresse reelle). Retourne (image d'indices, hauteur)."""
    haut = L(adr) // 76          # taille d'un plan / 76 octets par ligne
    q, lignes = adr + 8, []
    while d[q] != 0:
        cur = []
        while d[q] != 0xFF:
            cur.append(d[q]); q += 1
        q += 1; lignes.append(cur)
    im = np.zeros((len(lignes) * 32, 19 * 32), dtype=np.uint8)
    for y, r in enumerate(lignes):
        for x, k in enumerate(r):
            im[y * 32:y * 32 + 32, x * 32:x * 32 + 32] = TUILES[k - 1]
    return im

def prefixe(i):
    n = T0 + i * TAILLE_SCENE
    return [L(n - 24 + 4 * j) + A6 for j in range(6)], d[n:n + 4].decode("latin-1").strip("\0")

# ---------- 4) decors de toutes les scenes ----------
combos = {}
for i in range(-1, NB_SCENES):
    pr, nom = prefixe(i)
    if not all(A6 <= x < 0x52238 for x in pr):
        continue
    combos.setdefault((pr[2], pr[3], pr[4], pr[5]), []).append(nom)

index = []
for (mb, cb, ms, cs), noms in combos.items():
    haut = np.vstack([carte(mb), carte(ms)])              # decor (256) au dessus du sol (64)
    # chaque moitie a sa propre palette
    b = colorier(carte(mb), palette_triplet(cb))
    s = colorier(carte(ms), palette_triplet(cs))
    out = Image.new("RGB", (608, 320)); out.paste(b, (0, 0)); out.paste(s, (0, 256))
    fn = "decors/decor_%s.png" % noms[0]
    out.save(os.path.join(sortie, fn))
    index.append("%s : scenes %s (carte decor 0x%X, couleurs 0x%X ; carte sol 0x%X, couleurs 0x%X)"
                 % (fn, " ".join(noms), mb, cb, ms, cs))
    if mb == 0x1A7C2:     # la fresque (scene TT20)
        out.save(os.path.join(sortie, "fresque_scene_TT20.png"))
        # la fresque seule : tuiles colonnes 5..13, lignes 3..5 de la carte
        out.crop((160, 96, 448, 192)).resize((288 * 3, 96 * 3), Image.NEAREST).save(
            os.path.join(sortie, "fresque_seule.png"))
# une image par scene (meme decor que ci-dessus, avec la palette propre a la scene)
os.makedirs(os.path.join(sortie, "par_scene"), exist_ok=True)
for (mb, cb, ms, cs), noms in combos.items():
    src = Image.open(os.path.join(sortie, "decors/decor_%s.png" % noms[0]))
    for nm in noms:
        src.save(os.path.join(sortie, "par_scene", "%s.png" % nm))
# planche-contact des 40 decors
fich = sorted(os.listdir(os.path.join(sortie, "decors")))
feuille = Image.new("RGB", (4 * 308, ((len(fich) + 3) // 4) * 180), (30, 30, 30))
for j, f in enumerate(fich):
    t = Image.open(os.path.join(sortie, "decors", f)).resize((304, 160))
    feuille.paste(t, ((j % 4) * 308, (j // 4) * 180 + 18))
    ImageDraw.Draw(feuille).text(((j % 4) * 308 + 4, (j // 4) * 180 + 3), f[6:-4], fill=(255, 255, 255))
feuille.save(os.path.join(sortie, "planche_contact_decors.png"))
open(os.path.join(sortie, "decors.txt"), "w").write("\n".join(index) + "\n")

# ---------- 5) parchemin (fond et texte de la scene TC1) ----------
pr, _ = prefixe(0)
p = [plan(x, 76, 640) for x in (0x52240, 0x5E040)]
v = p[0] + 2 * p[1]
colorier(v, palette_triplet(pr[1])).save(os.path.join(sortie, "parchemin.png"))
print("images ecrites dans", sortie, ":", len(index), "decors")
