# Version Python / Python version

    python3 heros_jeu.py --data ../DataHeros          # console (FR); --sans-intro to skip the intro
    python3 heros_jeu.py --data ../amiga/DataHeros-en # English
    python3 heros_gui.py --data ../DataHeros          # Tk GUI

`heros_texte.py`, `extract_heros.py`, `extraire_images.py`, `extraire_sons.py` extract texts, pictures and sounds from `DataHeros` / `HerosExe`.

## Chemin le plus court vers l'écran de fin

    python3 chemin_fin.py --data ../DataHeros

Cherche la suite de choix la plus courte jusqu'au code secret du concours (scène TT39). Résultat actuel : **80 choix** (borne basse prouvée : 73). Voir l'en-tête du script pour les heuristiques.
