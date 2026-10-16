"""Cree un ADF OFS (880 Ko) a partir d'un repertoire. Usage: mkadf.py rep sortie.adf NOM bootblock_source.adf"""
import struct,os,sys,time
rep,out,label,bootsrc=sys.argv[1:5]
BS=512; N=1760; ROOT=880; BM=881
img=bytearray(N*BS)
img[:1024]=open(bootsrc,'rb').read()[:1024]
free=[b for b in range(882,N)]+[b for b in range(2,ROOT)]
used=set()
def alloc():
    b=free.pop(0); used.add(b); return b
def put(b,o,v): struct.pack_into('>i' if v<0 else '>I',img,b*BS+o,v)
def get(b,o): return struct.unpack_from('>I',img,b*BS+o)[0]
def cksum(b):
    struct.pack_into('>I',img,b*BS+20,0)
    s=sum(struct.unpack_from('>128I',img,b*BS))&0xFFFFFFFF
    struct.pack_into('>I',img,b*BS+20,(-s)&0xFFFFFFFF)
def hashn(n):
    h=len(n)
    for c in n:
        o=ord(c); o=o-32 if 97<=o<=122 else o
        h=(h*13+o)&0x7ff
    return h%72
now=int(time.time())-252460800
days,mins,ticks=now//86400,(now%86400)//60,((now%60)*50)
def setname(b,n):
    img[b*BS+0x1b0]=len(n); img[b*BS+0x1b1:b*BS+0x1b1+len(n)]=n.encode('latin-1')
def stamp(b):
    put(b,0x1a4,days);put(b,0x1a8,mins);put(b,0x1ac,ticks)
def link(parent,child,name):
    i=6*4+4*hashn(name); o=parent*BS+i
    cur=struct.unpack_from('>I',img,o)[0]
    if cur==0: struct.pack_into('>I',img,o,child)
    else:
        while get(cur,0x1f0): cur=get(cur,0x1f0)
        put(cur,0x1f0,child)
def mkdir(parent,name):
    b=alloc(); put(b,0,2); put(b,4,b); setname(b,name); stamp(b); put(b,0x1f4,parent); put(b,0x1fc,2)
    link(parent,b,name); return b
def mkfile(parent,name,data,prot=0):
    nd=max(1,(len(data)+487)//488) if data else 0
    h=alloc(); blks=[alloc() for _ in range(nd)]
    for i,db in enumerate(blks):
        ch=data[i*488:(i+1)*488]
        put(db,0,8); put(db,4,h); put(db,8,i+1); put(db,12,len(ch)); put(db,16,blks[i+1] if i+1<nd else 0)
        img[db*BS+24:db*BS+24+len(ch)]=ch; cksum(db)
    put(h,0,2); put(h,4,h); put(h,0x140,prot); put(h,0x144,len(data)); setname(h,name); stamp(h)
    put(h,0x1f4,parent); put(h,0x1fc,-3 & 0xFFFFFFFF); put(h,16,blks[0] if blks else 0)
    # blocs de donnees : 72 par entete, puis blocs d'extension
    cur=h; first=True; idx=0
    while True:
        chunk=blks[idx:idx+72]
        for j,db in enumerate(chunk): put(cur,0x18+4*(71-j),db)
        put(cur,8,len(chunk)); idx+=72
        if idx>=len(blks): break
        e=alloc(); put(cur,0x1f8,e)
        put(e,0,16); put(e,4,e); put(e,0x1f4,h); put(e,0x1fc,-3 & 0xFFFFFFFF)
        cur=e
    # sec_type et checksums
    b=h
    while b:
        nxt=get(b,0x1f8) if b==h or get(b,0)==16 else 0
        cksum(b); b=nxt
    link(parent,h,name); return h
def add(parent,path):
    for n in sorted(os.listdir(path)):
        p=os.path.join(path,n)
        if os.path.isdir(p): add(mkdir(parent,n),p)
        else: mkfile(parent,n,open(p,'rb').read())
put(ROOT,0,2); put(ROOT,12,72); put(ROOT,0x138,0xFFFFFFFF); put(ROOT,0x13c,BM)
used.update([ROOT,BM])
put(ROOT,0x1a4,days);put(ROOT,0x1a8,mins);put(ROOT,0x1ac,ticks)
put(ROOT,0x1d8,days);put(ROOT,0x1dc,mins);put(ROOT,0x1e0,ticks)
put(ROOT,0x1e4,days);put(ROOT,0x1e8,mins);put(ROOT,0x1ec,ticks)
setname(ROOT,label); put(ROOT,0x1fc,1)
add(ROOT,rep)
for b in range(2,N):
    if get(b,0) in (2,16): cksum(b)
# bitmap
words=[0]*(1+55)
for blk in range(2,N):
    if blk not in used: words[1+(blk-2)//32] |= 1<<((blk-2)%32)
struct.pack_into('>56I',img,BM*BS,*words)
s=sum(words[1:])&0xFFFFFFFF
struct.pack_into('>I',img,BM*BS,(-s)&0xFFFFFFFF)
open(out,'wb').write(img)
print('ADF ecrit',out,'blocs libres',len(free))
