"""Carte du monde : cases, texte de la page TMP1 (couleur dynamique), table scene -> zone."""
import struct
# (cle, etiquette 5 lettres max, ligne, colonne)
ZONES = [
 ('village','Villa',0,3),('falaise','Falai',1,3),('bergen','RivNo',1,2),('berge','Berge',2,2),('voleur','Voleu',2,3),
 ('plateau','Scorp',2,4),('dragon','Dragn',2,5),('orques','Orque',3,2),('carref','Carrf',3,3),('mort','HMort',3,4),
 ('marais','Marai',4,2),('etang','Etang',4,3),('tronc','Tronc',4,4),('bassin','Bassn',4,5),('pont','Pont',4,1),
 ('ile','Ile',4,0),('geant','Geant',5,2),('sables','Sable',5,1),('foret','ForSd',5,3),('collines','Colli',6,2),
 ('louve','Louve',6,3),('bataille','Batai',7,2),('pierres','Pierr',8,2),('hall','Hall',9,2),('temple','Templ',10,2)]
def R(p,a,b): return ['%s%d'%(p,i) for i in range(a,b+1)]
SCENES = {
 'village': R('TC',1,6)+R('TL',1,26)+R('TL',27,30)+R('TL',34,38)+['L28a','L29a','L29b','L29c','L34a'],
 'falaise': ['TM1','TM2','TM3'],
 'bergen': ['TM26'],
 'berge': ['TM12','TM13','TM27'],
 'voleur': R('TM',4,11),
 'plateau': R('TM',44,49),
 'dragon': R('TM',14,23)+['M21c'],
 'orques': R('TM',29,31)+['M31a','M31b'],
 'carref': ['TM24'],
 'mort': R('TM',37,41),
 'marais': R('M',105,109),
 'etang': ['TM25'],
 'tronc': R('TM',86,92),
 'bassin': R('TM',50,52),
 'pont': ['TM53','TM54'],
 'ile': R('TM',72,85)+['M72b','M85a','M85b'],
 'geant': R('TM',55,66)+['M66a'],
 'sables': R('TM',32,36),
 'foret': ['M110','M111'],
 'collines': ['TM42','TM43'],
 'louve': R('TM',93,99)+R('M',100,104)+['104a','104b'],
 'bataille': R('TM',67,71),
 'pierres': R('M',112,114),
 'hall': ['M115','M116'],
}
# page 2 : le temple (plan schematique deduit de l'enchainement des scenes)
ZONES2 = [('chute','Chute',2,0),('fresque','Fresque',2,1),('eboulis','Eboulis',2,2),
          ('escalier','Escalier',4,0),('secret','Secret',4,1),('galerie','Galerie',4,2)]
SCENES2 = {
 'chute': ['TT1'],
 'fresque': ['TT2','TT3','TT4','TT10','TT20','TT21','TT22','TT23','TT24','TT25','TT27','TT29'],
 'eboulis': ['TT6','TT7','TT13','TT16','TT17','TT18','T18a','T18b','T18c','TT19','TT28','TT30'],
 'galerie': ['TT26','TT32','TT34','TT36','TT40','TT41','TT47'],
 'secret': ['TT31','TT33','TT38','TT39','TT42','TT43','TT44','TT46'],
 'escalier': ['TT9','TT11','TT48'],
}
SCENES['temple'] = []   # la case Temple de la carte 1 est marquee quand on est dans la carte 2

COL0 = 14; ROW0 = 7   # la ligne 6 (ombre du parchemin) sert de titre
EN_LABELS = ['Villg','Cliff','NBank','Bank','Thief','Scorp','Dragn','Orcs','Cross','Dead','Marsh','Pond','Trunk','Basin','Brdg',
             'Isle','Giant','Sands','DkFor','Hills','Wolf','Battl','Stone','Hall','Templ']   # 5 lettres max (memes largeurs que le francais)
assert len(EN_LABELS)==len(ZONES) and all(len(x)<=5 for x in EN_LABELS)
def lines(ZONES=ZONES,NR=11,NC=6,LW=5,TITLE=None):
    """[(col, ligne, texte)], et offsets des octets 'chiffre de couleur' dans le flux du bloc."""
    grid = {(r,c):(i,l) for i,(k,l,r,c) in enumerate(ZONES)}
    out=[]; slots=[None]*len(ZONES); pos=0
    for r in range(NR):
        t=''; 
        for c in range(NC):
            if (r,c) in grid:
                i,l=grid[(r,c)]
                slots[i]=pos+2+len(t)+1       # apres '@'
                t+='@1'+l.ljust(LW)+'@1'
                nxt=(r,c+1) in grid
            else:
                t+=' '*LW; nxt=False
            if c<NC-1: t+=' - ' if ((r,c) in grid and (r,c+1) in grid) else '   '
        t=t.rstrip()
        if not t: continue
        out.append((COL0,ROW0+r,t)); pos+=2+len(t)+1
    return out,slots
def block_lines(fr=True):
    Z=ZONES if fr else [(k,e,r,c) for (k,_,r,c),e in zip(ZONES,EN_LABELS)]
    ls,_=lines(Z)
    out=['%d,%d|%s'%l for l in ls]
    out.append('26,6|@1' + ('CARTE DU MONDE' if fr else 'WORLD MAP'))
    # legende : croix flechee en bas a gauche (zone libre de la carte)
    o = 'O' if fr else 'W'
    for r,t in ((13,'       N'),(14,'       :'),(15,'%s <----:----> E'%o),(16,'       :'),(17,'       S')):
        out.append('14,%d|@1%s'%(r,t))
    return out
def block_lines2(fr=True):
    Z=ZONES2 if fr else [(k,e,r,c) for (k,_,r,c),e in zip(ZONES2,['Fall','Fresco','Rubble','Stairs','Secret','Gallery'])]
    ls,_=lines(Z,5,3,8)
    out=['%d,%d|%s'%l for l in ls]
    out.append('14,6|@1TEMPLE' + (' - plan schematique' if fr else ' - schematic plan'))
    return out
def slots():
    return lines()[1] + lines(ZONES2,5,3,8)[1]
def ztab(names):
    """names : liste des noms de scenes dans l'ordre des enregistrements -> octets (zone+1, 0 = aucune)"""
    idx={}
    for zi,(k,_,_,_) in enumerate(ZONES):
        for n in SCENES[k]: idx[n]=zi+1
    for zi,(k,_,_,_) in enumerate(ZONES2):
        for n in SCENES2[k]: idx[n]=len(ZONES)+zi+1
    return bytes(idx.get(n,0) for n in names)
