#!/usr/bin/env python3
"""Cree l'icone projet <langue>.info (dragon de HEROS + pastille de langue) et le fichier <langue>.
   python3 make_icon.py en ../HerosExe.info  repertoire_sortie  [X] [Y]  [outil_par_defaut]
Double-clic sur l'icone -> Workbench lance l'outil par defaut avec le nom du projet en argument -> DataHeros-<langue>."""
import struct,sys,os
F={'A':'01110 10001 10001 11111 10001 10001 10001','B':'11110 10001 10001 11110 10001 10001 11110','C':'01110 10001 10000 10000 10000 10001 01110',
'D':'11110 10001 10001 10001 10001 10001 11110','E':'11111 10000 10000 11110 10000 10000 11111','F':'11111 10000 10000 11110 10000 10000 10000',
'G':'01110 10001 10000 10111 10001 10001 01111','H':'10001 10001 10001 11111 10001 10001 10001','I':'01110 00100 00100 00100 00100 00100 01110',
'J':'00111 00010 00010 00010 00010 10010 01100','K':'10001 10010 10100 11000 10100 10010 10001','L':'10000 10000 10000 10000 10000 10000 11111',
'M':'10001 11011 10101 10101 10001 10001 10001','N':'10001 11001 10101 10011 10001 10001 10001','O':'01110 10001 10001 10001 10001 10001 01110',
'P':'11110 10001 10001 11110 10000 10000 10000','Q':'01110 10001 10001 10001 10101 10010 01101','R':'11110 10001 10001 11110 10100 10010 10001',
'S':'01111 10000 10000 01110 00001 00001 11110','T':'11111 00100 00100 00100 00100 00100 00100','U':'10001 10001 10001 10001 10001 10001 01110',
'V':'10001 10001 10001 10001 10001 01010 00100','W':'10001 10001 10001 10101 10101 11011 10001','X':'10001 10001 01010 00100 01010 10001 10001',
'Y':'10001 10001 01010 00100 00100 00100 00100','Z':'11111 00001 00010 00100 01000 10000 11111'}
def u16(d,o): return struct.unpack('>H',d[o:o+2])[0]
def decode(d,o):
    w,h,dep=struct.unpack('>HHH',d[o+4:o+10]); rb=2*((w+15)//16)
    px=[[0]*w for _ in range(h)]
    for y in range(h):
        for x in range(w):
            v=0
            for p in range(dep):
                if d[o+20+p*rb*h+y*rb+x//8]>>(7-x%8)&1: v|=1<<p
            px[y][x]=v
    return w,h,dep,px,d[o:o+20]
def encode(w,h,dep,px,hdr):
    rb=2*((w+15)//16); out=bytearray(rb*h*dep)
    for y in range(h):
        for x in range(w):
            v=px[y][x]
            for p in range(dep):
                if v>>p&1: out[p*rb*h+y*rb+x//8]|=1<<(7-x%8)
    return bytes(hdr)+bytes(out)
def badge(w,h,px,text):
    n=len(text); bw=n*6+5; bh=11; x0=w-bw-4; y0=h-bh-4
    for y in range(bh):
        for x in range(bw):
            px[y0+y][x0+x]=3 if (0<y<bh-1 and 0<x<bw-1) else 2      # fond orange, cadre noir
    for i,c in enumerate(text):
        g=F[c].split()
        for gy in range(7):
            for gx in range(5):
                if g[gy][gx]=='1': px[y0+2+gy][x0+3+i*6+gx]=2
def main(fname,badge_txt,src,outdir,X=4,Y=4,tool='HEROS:HerosExe'):
    """fname = nom affiche sous l'icone, ex. 'h\xe9ros - fran\xe7ais' ; badge_txt = 'FR'.
       Le jeu prend les 2 premieres lettres du DERNIER MOT du nom comme suffixe : 'fran\xe7ais' -> DataHeros-fr."""
    d=open(src,'rb').read()
    o1=0x4e; w,h,dep,p1,h1=decode(d,o1); o2=o1+20+2*((w+15)//16)*h*dep
    w2,h2,dep2,p2,h2h=decode(d,o2)
    for px in (p1,p2): badge(w,h,px,badge_txt.upper())
    head=bytearray(d[:0x4e])
    head[0x30]=4                                  # WBPROJECT
    struct.pack_into('>I',head,0x32,1)            # outil par defaut present
    struct.pack_into('>I',head,0x36,0)            # pas de tooltypes
    struct.pack_into('>i',head,0x3a,X); struct.pack_into('>i',head,0x3e,Y)
    t=tool.encode('latin-1')+b'\0'
    blob=bytes(head)+encode(w,h,dep,p1,h1)+encode(w2,h2,dep2,p2,h2h)+struct.pack('>I',len(t))+t
    os.makedirs(outdir,exist_ok=True)
    open(os.path.join(outdir,fname+'.info'),'wb').write(blob)
    open(os.path.join(outdir,fname),'wb').write(('HEROS - %s\n'%fname).encode('latin-1'))

def disk_icon(src,diskinfo,out,win=(0x20,0x0d,0x154,0x70)):
    """icone de disquette : dragon de HEROS, type WBDISK, fenetre racine elargie."""
    d=open(src,'rb').read(); di=open(diskinfo,'rb').read()
    o1=0x4e; w,h,dep,p1,h1=decode(d,o1); o2=o1+20+2*((w+15)//16)*h*dep
    w2,h2,dep2,p2,h2h=decode(d,o2)
    head=bytearray(d[:0x4e]); head[0x30]=1
    struct.pack_into('>I',head,0x32,0); struct.pack_into('>I',head,0x36,0)
    struct.pack_into('>I',head,0x42,1)            # DrawerData present
    struct.pack_into('>I',head,0x4a,0)
    head[0x3a:0x42]=di[0x3a:0x42]                 # position de l'icone disque d'origine
    dd=bytearray(di[0x4e:0x4e+56]); struct.pack_into('>HHHH',dd,0,*win)
    open(out,'wb').write(bytes(head)+bytes(dd)+encode(w,h,dep,p1,h1)+encode(w2,h2,dep2,p2,h2h))
if __name__=='__main__':
    a=sys.argv
    main(a[1],a[2],a[3],a[4],*(int(x) for x in a[5:7]),*a[7:8])
