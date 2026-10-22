#!/usr/bin/env python3
"""Extrait de jeu/data.js (version web) les donnees du moteur dans data/data.json."""
import json, re, os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
src = open(os.path.join(ROOT, '..', 'jeu', 'data.js'), encoding='utf-8').read()
i = src.index('window.HEROS=') + len('window.HEROS=')
obj, end = json.JSONDecoder().raw_decode(src, i)
for k in ('dataFr', 'dataEn'):
    m = re.search(r'window\.HEROS\.%s\s*=\s*"([^"]*)"' % k, src)
    obj[k] = m.group(1)
json.dump(obj, open(os.path.join(ROOT, 'data', 'data.json'), 'w'))
print('data.json :', list(obj))
