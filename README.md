# HEROS (Amiga, 1994) — version adaptée / adapted version

**▶ Jouer dans le navigateur : https://jaymanu79.github.io/amiga_heros/**
**▶ Play in your browser: https://jaymanu79.github.io/amiga_heros/?lang=en**

*HEROS* est un jeu d'aventure textuel « dont vous êtes le héros » écrit sur Amiga par **Olivier Thil** (1994, shareware, concours DREAM). Ce dépôt le conserve et le rend plus confortable, avec l'aide d'une IA (Claude).

## Contenu

| Chemin | Contenu |
|---|---|
| `index.html`, `jeu/` | Site GitHub Pages : page d'accueil (contexte, drapeau FR/EN, téléchargement) et jeu jouable dans le navigateur (`jeu/`). |
| `HEROS.lha` | Le jeu seul pour disque dur / carte CF (`amiga/outils/mklha.py` le fabrique). |
| `snes/` | Version Super Nintendo complète : ROM `heros_snes.sfc`, sources 65816, tests. |
| `HEROS.adf` | Disquette Amiga (880 Ko, A500 / Kickstart 1.3) avec le jeu adapté, en français et en anglais. |
| `amiga/` | Fichiers de la disquette (`HerosExe` patché, `DataHeros-fr/-en`, icônes) et outils pour la reconstruire (`outils/`). |
| `python/` | Version Python (console `heros_jeu.py`, interface Tk `heros_gui.py`) et extracteurs de textes, images et sons. |
| `DataHeros`, `HerosExe`, `HerosExe.info` | Binaires d'origine, intacts. |

## Nos modifications (Amiga et navigateur)

- Page d'introduction : mention « adaptation réalisée avec une IA » + liste des touches en couleurs.
- `B` retour arrière · `V` vie à 32 · `S` / `L` sauver / charger (4 emplacements) · `M` carte du monde en 2 pages avec la zone actuelle en surbrillance.
- Vie plafonnée à 32 ; changements d'écran plus rapides (Amiga).
- Version anglaise complète ; choix de la langue par icône (Amiga) ou drapeau (navigateur).
- Le jeu Amiga reste sur sa disquette protégée : seul `HerosSave-N` est écrit.

Les téléchargements (ADF, LHA, SNES) et les étapes de partie dans le navigateur (début, falaise, temple, fin) sont comptés anonymement avec GoatCounter (compte `jaymanu`, le même que Relief Action).

Le détail est sur la page d'accueil et dans `amiga/LISEZMOI.txt`.

## Crédits

Jeu original : Olivier Thil, 1994 (shareware, DREAM). Adaptations : jaymanu, avec Claude (Anthropic). Projet de préservation non commercial ; si vous êtes l'auteur et souhaitez un retrait ou une modification, ouvrez une *issue*.

---

# English

*HEROS* is a text adventure written for the Amiga by **Olivier Thil** (1994, shareware, DREAM contest). This repository preserves it and makes it more comfortable, with the help of an AI (Claude).

- `index.html`, `jeu/` — GitHub Pages site: home page (background, FR/EN flag, download) and the browser game.
- `HEROS.adf` — 880 KB Amiga floppy image (A500 / Kickstart 1.3) with the adapted game, French and English.
- `amiga/` — disk contents (patched `HerosExe`, `DataHeros-fr/-en`, icons) and rebuild tools.
- `python/` — Python version (console and Tk GUI) and text/image/sound extractors.
- `DataHeros`, `HerosExe`, `HerosExe.info` — untouched original binaries.

Changes: AI-adaptation notice and colour key list on the intro page; `B` undo, `V` life 32, `S`/`L` save/load (4 slots), `M` two-page map; life capped at 32; faster fades; full English version; language by icon (Amiga) or flag (browser).

Credits: original game by Olivier Thil (1994); adaptations by jaymanu with Claude (Anthropic). Non-commercial preservation project; open an issue if anything should be removed.
