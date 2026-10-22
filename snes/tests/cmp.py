import json,struct,sys
sys.path.insert(0,'.')
import refengine as R
scr=json.load(open(sys.argv[1])); dumps=json.load(open(sys.argv[2]))
ks=R.path_from('/tmp/path.txt'); st=R.nouvel_etat(); bad=0
for i,k in enumerate(ks):
    R.choisir(st,k)
    f=str(scr['dump'][i]); b=bytes.fromhex(dumps[f])
    sc,w,l,vie,gold=struct.unpack_from('<HHIhh',b,0x20)
    ok=(sc,w,l,vie,gold)==(st['sc'],st['W'],st['L'],st['vie'],st['or'])
    if not ok:
        bad+=1
        if bad<6: print('ecart choix',i+1,k,'snes',(sc,w,l,vie,gold),'ref',(st['sc'],st['W'],st['L'],st['vie'],st['or']))
print('choix',len(ks),'ecarts',bad)
