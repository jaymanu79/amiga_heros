"""Mini interpreteur 68000 : juste ce qu'il faut pour executer le decompresseur de HerosExe."""
import struct
M32=0xFFFFFFFF
class CPU:
    def __init__(s, mem):
        s.m=mem; s.d=[0]*8; s.a=[0]*8; s.pc=0; s.N=s.Z=s.V=s.C=s.X=0; s.hooks={}
    # memoire
    def rb(s,a): return s.m[a]
    def rw(s,a): return (s.m[a]<<8)|s.m[a+1]
    def rl(s,a): return struct.unpack('>I',bytes(s.m[a:a+4]))[0]
    def wb(s,a,v): s.m[a]=v&255
    def ww(s,a,v): s.m[a]=(v>>8)&255; s.m[a+1]=v&255
    def wl(s,a,v): s.m[a:a+4]=struct.pack('>I',v&M32)
    def rd(s,a,sz): return s.rb(a) if sz==1 else s.rw(a) if sz==2 else s.rl(a)
    def wr(s,a,sz,v): (s.wb if sz==1 else s.ww if sz==2 else s.wl)(a,v)
    def fetch(s):
        v=s.rw(s.pc); s.pc+=2; return v
    def fetchl(s):
        v=s.rl(s.pc); s.pc+=4; return v
    def sx(s,v,sz):
        b=sz*8; v&=(1<<b)-1
        return v-(1<<b) if v>>(b-1)&1 else v
    def mask(s,sz): return (1<<(sz*8))-1
    # adressage effectif : retourne ('d',n) ('a',n) ('m',addr) ('i',val)
    def ea(s,mode,reg,sz):
        if mode==0: return ('d',reg)
        if mode==1: return ('a',reg)
        if mode==2: return ('m',s.a[reg])
        if mode==3:
            a=s.a[reg]; s.a[reg]=(a+(2 if (sz==1 and reg==7) else sz))&M32; return ('m',a)
        if mode==4:
            s.a[reg]=(s.a[reg]-(2 if (sz==1 and reg==7) else sz))&M32; return ('m',s.a[reg])
        if mode==5: return ('m',(s.a[reg]+s.sx(s.fetch(),2))&M32)
        if mode==6:
            e=s.fetch(); r=(s.a if e&0x8000 else s.d)[e>>12&7]
            if not e&0x800: r=s.sx(r,2)
            return ('m',(s.a[reg]+s.sx(e&255,1)+r)&M32)
        if mode==7:
            if reg==0: return ('m',s.sx(s.fetch(),2)&M32)
            if reg==1: return ('m',s.fetchl())
            if reg==2:
                p=s.pc; return ('m',(p+s.sx(s.fetch(),2))&M32)
            if reg==3:
                p=s.pc; e=s.fetch(); r=(s.a if e&0x8000 else s.d)[e>>12&7]
                if not e&0x800: r=s.sx(r,2)
                return ('m',(p+s.sx(e&255,1)+r)&M32)
            if reg==4:
                if sz==4: return ('i',s.fetchl())
                return ('i',s.fetch()&s.mask(sz))
        raise Exception('ea %d %d'%(mode,reg))
    def get(s,e,sz):
        k,v=e
        if k=='d': return s.d[v]&s.mask(sz)
        if k=='a': return s.a[v]&s.mask(sz)
        if k=='i': return v
        return s.rd(v,sz)
    def put(s,e,sz,val):
        k,v=e; val&=s.mask(sz)
        if k=='d': s.d[v]=(s.d[v]&~s.mask(sz)&M32)|val
        elif k=='a': s.a[v]=s.sx(val,sz)&M32
        else: s.wr(v,sz,val)
    def nz(s,v,sz):
        v&=s.mask(sz); s.Z=int(v==0); s.N=v>>(sz*8-1)&1
    def cc(s,c):
        N,Z,V,C=s.N,s.Z,s.V,s.C
        return [True,False,not(C or Z),bool(C or Z),not C,bool(C),not Z,bool(Z),not V,bool(V),not N,bool(N),N==V,N!=V,(not Z) and N==V,bool(Z) or N!=V][c]
    def addsub(s,a,b,sz,sub,store=True):
        m=s.mask(sz); a&=m; b&=m
        r=(b-a if sub else b+a)
        c=int(r<0) if sub else int(r>m); r&=m
        sb=1<<(sz*8-1)
        v=int((((b^a)&(b^r)) if sub else (~(a^b)&(a^r)))&sb!=0)
        s.N=int(r&sb!=0); s.Z=int(r==0); s.V=v; s.C=c
        if store: s.X=c
        return r
    def push(s,v): s.a[7]=(s.a[7]-4)&M32; s.wl(s.a[7],v)
    def pop(s):
        v=s.rl(s.a[7]); s.a[7]=(s.a[7]+4)&M32; return v
    def run(s, stop):
        while s.pc!=stop:
            if s.pc in s.hooks: s.hooks[s.pc](s); continue
            s.step()
    def step(s):
        o=s.fetch(); t=o>>12; m=o>>3&7; r=o&7; sz3={0:1,1:2,2:4}
        if t==0:
            if o&0x100 or (o>>9&7)==4:       # btst/bchg/bclr/bset
                if o&0x100: n=s.d[o>>9&7]
                else: n=s.fetch()&255
                e=s.ea(m,r,1)
                if e[0]=='d': n&=31; v=s.d[e[1]]; s.Z=int(not v>>n&1)
                else: n&=7; v=s.get(e,1); s.Z=int(not v>>n&1)
                k=o>>6&3
                if k==1: v^=1<<n
                elif k==2: v&=~(1<<n)
                elif k==3: v|=1<<n
                if k:
                    if e[0]=='d': s.d[e[1]]=v&M32
                    else: s.put(e,1,v)
                return
            if o&0xf00 in (0x000,0x200,0x400,0x600,0xa00,0xc00) and (o>>6&3)<3 and (o&0xff00)!=0x0800:
                sz=sz3[o>>6&3]; imm=(s.fetchl() if sz==4 else s.fetch())&s.mask(sz)
                e=s.ea(m,r,sz); v=s.get(e,sz); k=o>>8&15
                if k==0xc: s.addsub(imm,v,sz,True); return
                if k==4: res=s.addsub(imm,v,sz,True)
                elif k==6: res=s.addsub(imm,v,sz,False)
                else:
                    res=(v|imm) if k==0 else (v&imm) if k==2 else (v^imm); s.nz(res,sz); s.V=s.C=0
                s.put(e,sz,res); return
            raise Exception('op0 %04x'%o)
        if t in (1,2,3):
            sz={1:1,3:2,2:4}[t]; src=s.ea(m,r,sz); v=s.get(src,sz)
            dm=o>>6&7; dr=o>>9&7; d=s.ea(dm,dr,sz)
            if dm==1:
                s.a[dr]=s.sx(v,sz)&M32
            else:
                s.put(d,sz,v); s.nz(v,sz); s.V=s.C=0
            return
        if t==4:
            if o==0x4e75: s.pc=s.pop(); return
            if o&0xfff8==0x4e50: raise Exception('link')
            if o&0xffc0==0x4e80: e=s.ea(m,r,4); s.push(s.pc); s.pc=e[1]; return
            if o&0xffc0==0x4ec0: e=s.ea(m,r,4); s.pc=e[1]; return
            if o&0xf1c0==0x41c0: e=s.ea(m,r,4); s.a[o>>9&7]=e[1]; return
            if o&0xfff8==0x4840: v=s.d[r]; s.d[r]=((v<<16)|(v>>16))&M32; s.nz(s.d[r],4); s.V=s.C=0; return
            if o&0xfb80==0x4880:
                mask=s.fetch(); sz=4 if o&0x40 else 2
                if o&0x400:
                    e=s.ea(m,r,sz); a=e[1]
                    for i in range(16):
                        if mask>>i&1:
                            v=s.rd(a,sz) if sz==4 else s.sx(s.rw(a),2)&M32
                            (s.d if i<8 else s.a)[i&7]=v; a+=sz
                    if m==3: s.a[r]=a&M32
                else:
                    if m==4:
                        a=s.a[r]
                        for i in range(16):      # masque inverse en predecrement
                            if mask>>i&1:
                                j=15-i; a-=sz
                                s.wr(a,sz,(s.d if j<8 else s.a)[j&7])
                        s.a[r]=a&M32
                    else: raise Exception('movem w')
                return
            k=o>>9&7
            if o&0xc0!=0xc0 and k in (1,5):
                sz=sz3[o>>6&3]; e=s.ea(m,r,sz)
                if k==1: s.put(e,sz,0); s.Z=1;s.N=s.V=s.C=0
                else: s.nz(s.get(e,sz),sz); s.V=s.C=0
                return
            raise Exception('op4 %04x pc=%x'%(o,s.pc-2))
        if t==5:
            if o>>6&3==3:
                c=o>>8&15
                if m==1:
                    p=s.pc; d=s.sx(s.fetch(),2)
                    if not s.cc(c):
                        w=(s.d[r]-1)&0xFFFF; s.d[r]=(s.d[r]&0xFFFF0000)|w
                        if w!=0xFFFF: s.pc=(p+d)&M32
                    return
                raise Exception('scc')
            q=(o>>9&7) or 8; sz=sz3[o>>6&3]; e=s.ea(m,r,sz)
            if e[0]=='a': s.a[e[1]]=(s.a[e[1]]+(-q if o&0x100 else q))&M32; return
            v=s.get(e,sz); s.put(e,sz,s.addsub(q,v,sz,bool(o&0x100))); return
        if t==6:
            c=o>>8&15; p=s.pc; d=s.sx(o&255,1)
            if o&255==0: d=s.sx(s.fetch(),2)
            if c==1: s.push(s.pc); s.pc=(p+d)&M32; return
            if c==0 or s.cc(c): s.pc=(p+d)&M32
            return
        if t==7: v=s.sx(o&255,1)&M32; s.d[o>>9&7]=v; s.nz(v,4); s.V=s.C=0; return
        if t in (8,0xc):
            k=o>>6&7; dn=o>>9&7
            if t==8 and k==3:
                src=s.get(s.ea(m,r,2),2); dv=s.d[dn]&M32
                if src==0: raise Exception('div0')
                q=dv//src; rm=dv%src
                s.d[dn]=((rm&0xFFFF)<<16)|(q&0xFFFF); s.nz(q,2); s.V=s.C=0; return
            if t==0xc and k==3:
                s.d[dn]=(s.d[dn]&0xFFFF)*(s.get(s.ea(m,r,2),2))&M32; s.nz(s.d[dn],4); s.V=s.C=0; return
            if t==0xc and o&0x1f8 in (0x140,0x148,0x188):
                f=o&0x1f8
                if f==0x140: s.d[dn],s.d[r]=s.d[r],s.d[dn]
                elif f==0x148: s.a[dn],s.a[r]=s.a[r],s.a[dn]
                else: s.d[dn],s.a[r]=s.a[r],s.d[dn]
                return
            sz=sz3[k&3]; e=s.ea(m,r,sz)
            if k<3: res=(s.get(e,sz) | s.d[dn]&s.mask(sz)) if t==8 else (s.get(e,sz)&s.d[dn]&s.mask(sz)); s.put(('d',dn),sz,res)
            else: res=(s.get(e,sz)|s.d[dn]) if t==8 else (s.get(e,sz)&s.d[dn]); s.put(e,sz,res)
            s.nz(res,sz); s.V=s.C=0; return
        if t in (9,0xd):
            k=o>>6&7; dn=o>>9&7; sub=(t==9)
            if k in (3,7):
                sz=2 if k==3 else 4; e=s.ea(m,r,sz); v=s.sx(s.get(e,sz),sz)
                s.a[dn]=(s.a[dn]-v if sub else s.a[dn]+v)&M32; return
            if k in (4,5,6) and m==0:            # addx/subx Dy,Dx
                sz=sz3[k&3]; mk=s.mask(sz); a=s.d[r]&mk; b=s.d[dn]&mk
                rr=(b-a-s.X) if sub else (b+a+s.X); c=int(rr<0) if sub else int(rr>mk); rr&=mk
                sb=1<<(sz*8-1)
                s.V=int((((b^a)&(b^rr)) if sub else (~(a^b)&(a^rr)))&sb!=0)
                s.N=int(rr&sb!=0); s.C=s.X=c
                if rr: s.Z=0
                s.put(('d',dn),sz,rr); return
            sz=sz3[k&3]; e=s.ea(m,r,sz)
            if k<3: s.put(('d',dn),sz,s.addsub(s.get(e,sz),s.d[dn],sz,sub))
            else: s.put(e,sz,s.addsub(s.d[dn],s.get(e,sz),sz,sub))
            return
        if t==0xb:
            k=o>>6&7; dn=o>>9&7
            if k in (3,7):
                sz=2 if k==3 else 4; e=s.ea(m,r,sz); v=s.sx(s.get(e,sz),sz)&M32
                s.addsub(v,s.a[dn],4,True); return
            sz=sz3[k&3]; e=s.ea(m,r,sz)
            if k<3: s.addsub(s.get(e,sz),s.d[dn],sz,True)
            else:
                res=s.get(e,sz)^s.d[dn]; s.put(e,sz,res); s.nz(res,sz); s.V=s.C=0
            return
        if t==0xe:
            sz=sz3[o>>6&3]; typ=o>>3&3; left=bool(o&0x100)
            cnt=(s.d[o>>9&7]&63) if o&0x20 else ((o>>9&7) or 8)
            v=s.d[r]&s.mask(sz); bits=sz*8; c=0
            if typ==1:        # lsl/lsr
                for _ in range(cnt):
                    if left: c=v>>(bits-1)&1; v=(v<<1)&s.mask(sz)
                    else: c=v&1; v>>=1
                if cnt: s.X=s.C=c
                else: s.C=0
            elif typ==3:      # rol/ror
                cn=cnt%bits
                if left: v=((v<<cn)|(v>>(bits-cn)))&s.mask(sz) if cn else v
                else: v=((v>>cn)|(v<<(bits-cn)))&s.mask(sz) if cn else v
                s.C=(v&1 if not left else v>>(bits-1)&1) if cnt else 0
            else: raise Exception('shift typ %d'%typ)
            s.put(('d',r),sz,v); s.nz(v,sz); s.V=0; return
        raise Exception('op %04x pc=%x'%(o,s.pc-2))
