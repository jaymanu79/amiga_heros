import struct,os,sys
D=open(sys.argv[1],'rb').read(); OUT=sys.argv[2]
def L(b,o): return struct.unpack('>I',D[b*512+o:b*512+o+4])[0]
def S(b,o): return struct.unpack('>i',D[b*512+o:b*512+o+4])[0]
def name(b):
    o=b*512+0x1b0; n=D[o]; return D[o+1:o+1+n].decode('latin-1')
def walk(blk,path):
    for i in range(72):
        h=L(blk,24+4*i)
        while h:
            typ=S(h,508); nm=name(h)
            p=os.path.join(path,nm.replace('/','_'))
            if typ==2:
                os.makedirs(p,exist_ok=True); print('D',p); walk(h,p)
            elif typ==-3:
                size=L(h,324); data=b''; db=L(h,16)
                while db and len(data)<size:
                    sz=L(db,12); data+=D[db*512+24:db*512+24+sz]; db=L(db,16)
                open(p,'wb').write(data[:size]); print('F',p,size)
            h=L(h,496)
os.makedirs(OUT,exist_ok=True)
print('disk',name(880))
walk(880,OUT)
