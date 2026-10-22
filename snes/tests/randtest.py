import json,sys,random,struct,subprocess
sys.path.insert(0,'.')
import refengine as R
seed=int(sys.argv[1]); N=int(sys.argv[2]); random.seed(seed)
btn={1:'A',2:'B',3:'X',4:'Y',5:'R'}
pres=[[200,'START',3],[300,'START',3]]; f=420
st=R.nouvel_etat(); hist=[dict(st)]; exp=[]; dump=[]
for i in range(N):
    sc=st['sc']; valid=[k for k in range(1,6) if R.SC[sc]['liens'][k-1] is not None]
    r=random.random()
    if r<0.12 and len(hist)>1:
        pres.append([f,'SELECT',3]); hist.pop(); st=dict(hist[-1]); quit_=False
    elif r<0.17 and valid:   # appui invalide
        bad=[k for k in range(1,6) if k not in valid]
        if bad: pres.append([f,btn[random.choice(bad)],3])
        quit_=False
    elif valid:
        k=random.choice(valid); pres.append([f,btn[k],3])
        nv=dict(st); res=R.choisir(nv,k)
        if res=='quitter':
            exp.append((f+75,None)); f+=80
            st=R.nouvel_etat(); hist=[dict(st)]
            pres.append([f+60,'START',3]); pres.append([f+160,'START',3]); f+=300
            continue
        st=nv; hist.append(dict(st))
    else:
        pres.append([f,'SELECT',3]); 
        if len(hist)>1: hist.pop(); st=dict(hist[-1])
    exp.append((f+75,dict(st))); dump.append(f+75); f+=80
json.dump({'frames':f+20,'presses':pres,'dump':dump,'wav':'/tmp/t5.wav'},open('t5.json','w'))
json.dump([(a,b) for a,b in exp if b is not None],open('t5_exp.json','w'))
print('frames',f)
