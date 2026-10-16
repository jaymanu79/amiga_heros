"""Mini-assembleur 68000 (sous-ensemble) : asm(source, org=0, syms={}) -> (bytes, labels).
Syntaxe Motorola : label:  mnemonic.sz op,op ; commentaire.   Directives : dc.b dc.w dc.l ds.b even equ(=)"""
import re, struct

CC = {'t':0,'f':1,'hi':2,'ls':3,'cc':4,'hs':4,'cs':5,'lo':5,'ne':6,'eq':7,'vc':8,'vs':9,'pl':10,'mi':11,'ge':12,'lt':13,'gt':14,'le':15}
SZ = {'b':0,'w':1,'l':2}

class AsmError(Exception): pass

def split_ops(s):
    out=[];cur='';depth=0;q=None
    for ch in s:
        if q:
            cur+=ch
            if ch==q: q=None
            continue
        if ch in '"\'': q=ch; cur+=ch; continue
        if ch=='(' : depth+=1
        if ch==')' : depth-=1
        if ch==',' and depth==0: out.append(cur.strip()); cur=''
        else: cur+=ch
    if cur.strip(): out.append(cur.strip())
    return out

class Asm:
    def __init__(s, syms=None):
        s.syms=dict(syms or {})
    def ev(s, expr, pc=None, final=True):
        e=expr.strip()
        e=re.sub(r'\$([0-9a-fA-F]+)', lambda m:'0x'+m.group(1), e)
        e=re.sub(r"'(.)'", lambda m:str(ord(m.group(1))), e)
        names=dict(s.syms)
        if pc is not None: names['__pc']=pc
        e=e.replace('*','__pc') if pc is not None and e.strip()=='*' else e
        try:
            return int(eval(e,{'__builtins__':{}},names))
        except NameError as ex:
            if final: raise AsmError('symbole inconnu dans %r: %s'%(expr,ex))
            return 0
    # ---- operande -> (mode, reg, extwords_builder)
    def parse_ea(s, op, size):
        """retourne dict(kind=..., mode, reg, ext=[(valeur_fonction, taille)])"""
        o=op.strip()
        m=re.fullmatch(r'[dD]([0-7])',o)
        if m: return dict(k='dn',mode=0,reg=int(m.group(1)),ext=[])
        m=re.fullmatch(r'[aA]([0-7])|sp',o,re.I)
        if m: return dict(k='an',mode=1,reg=int(m.group(1)) if m.group(1) else 7,ext=[])
        m=re.fullmatch(r'\((?:[aA]([0-7])|sp)\)',o,re.I)
        if m: return dict(k='ind',mode=2,reg=int(m.group(1)) if m.group(1) else 7,ext=[])
        m=re.fullmatch(r'\((?:[aA]([0-7])|sp)\)\+',o,re.I)
        if m: return dict(k='post',mode=3,reg=int(m.group(1)) if m.group(1) else 7,ext=[])
        m=re.fullmatch(r'-\((?:[aA]([0-7])|sp)\)',o,re.I)
        if m: return dict(k='pre',mode=4,reg=int(m.group(1)) if m.group(1) else 7,ext=[])
        m=re.fullmatch(r'#(.+)',o)
        if m:
            ex=m.group(1)
            return dict(k='imm',mode=7,reg=4,ext=[('imm',ex,size)])
        # d8(An,Xn) / d8(PC,Xn)
        m=re.fullmatch(r'(.*)\(\s*([aA][0-7]|sp|pc)\s*,\s*([dDaA][0-7])(?:\.([wlWL]))?\s*\)',o,re.I)
        if m:
            d=m.group(1).strip() or '0'; base=m.group(2).lower(); xn=m.group(3).lower(); xs=(m.group(4) or 'w').lower()
            xi=int(xn[1])+(8 if xn[0]=='a' else 0)
            if base=='pc': return dict(k='pcx',mode=7,reg=3,ext=[('idx',d,(xi,xs,True))])
            r=7 if base=='sp' else int(base[1])
            return dict(k='idx',mode=6,reg=r,ext=[('idx',d,(xi,xs,False))])
        m=re.fullmatch(r'(.*)\(\s*([aA][0-7]|sp|pc)\s*\)',o,re.I)
        if m:
            d=m.group(1).strip() or '0'; base=m.group(2).lower()
            if base=='pc': return dict(k='pc',mode=7,reg=2,ext=[('pcd',d,2)])
            r=7 if base=='sp' else int(base[1])
            return dict(k='disp',mode=5,reg=r,ext=[('w',d,2)])
        m=re.fullmatch(r'(.*)\.([wlWL])',o)
        if m:
            sz=m.group(2).lower()
            if sz=='w': return dict(k='absw',mode=7,reg=0,ext=[('w',m.group(1),2)])
            return dict(k='absl',mode=7,reg=1,ext=[('l',m.group(1),4)])
        # absolu : .l par defaut si inconnu
        return dict(k='absl',mode=7,reg=1,ext=[('l',o,4)])
    def ea_bits(s,e): return (e['mode']<<3)|e['reg']
    def ext_bytes(s, e, pc_of_ext, final):
        out=b''
        for t,ex,sz in e['ext']:
            if t=='imm':
                v=s.ev(ex,final=final)
                if sz==0: out+=struct.pack('>H',(v)&0xFF)    # .b #imm : mot, octet bas
                elif sz==1: out+=struct.pack('>H',v&0xFFFF)
                else: out+=struct.pack('>I',v&0xFFFFFFFF)
            elif t=='w':
                v=s.ev(ex,final=final); out+=struct.pack('>H',v&0xFFFF)
            elif t=='l':
                v=s.ev(ex,final=final); out+=struct.pack('>I',v&0xFFFFFFFF)
            elif t=='pcd':
                v=s.ev(ex,final=final); d=v-(pc_of_ext+len(out));
                if final and not -32768<=d<=32767: raise AsmError('pc-rel hors portee: '+ex)
                out+=struct.pack('>H',d&0xFFFF)
            elif t=='idx':
                xi,xs,ispc=sz; v=s.ev(ex,final=final)
                if ispc: v=v-(pc_of_ext+len(out))
                if final and not -128<=v<=127: raise AsmError('d8 hors portee: '+ex)
                w=(xi<<12)|((1<<11) if xs=='l' else 0)|(v&0xFF)
                out+=struct.pack('>H',w)
        return out
    # ---- instruction
    def instr(s, mn, ops, pc, final):
        mn=mn.lower(); size=None
        if '.' in mn:
            mn,sf=mn.split('.',1); sf=sf.lower()
            if sf=='s': size='s'
            else: size=sf
        W=lambda *ws: b''.join(struct.pack('>H',w&0xFFFF) for w in ws)
        def sz(default='w'):
            z=size or default
            return SZ[z]
        n=len(ops)
        # sans operande
        simple={'rts':0x4E75,'rte':0x4E73,'nop':0x4E71,'rtr':0x4E77,'reset':0x4E70,'illegal':0x4AFC}
        if mn in simple: return W(simple[mn])
        if mn in ('bra','bsr') or (mn[0]=='b' and mn[1:] in CC and mn not in ('btst','bset','bclr','bchg')):
            cc=0 if mn=='bra' else 1 if mn=='bsr' else CC[mn[1:]]
            tgt=s.ev(ops[0],final=final); d=tgt-(pc+2)
            if size=='s' or (size is None and -128<=d<=127 and d!=0):
                if final and not(-128<=d<=127 and d!=0): raise AsmError('bcc.s hors portee')
                return W(0x6000|(cc<<8)|(d&0xFF))
            if final and not -32768<=d<=32767: raise AsmError('bcc.w hors portee')
            return W(0x6000|(cc<<8),d&0xFFFF)
        if mn.startswith('db') and mn[2:] in CC or mn=='dbra':
            cc=1 if mn=='dbra' else CC[mn[2:]]
            r=int(ops[0][1]); tgt=s.ev(ops[1],final=final); d=tgt-(pc+2)
            if final and not -32768<=d<=32767: raise AsmError('dbcc hors portee')
            return W(0x50C8|(cc<<8)|r,d&0xFFFF)
        if mn[0]=='s' and mn[1:] in CC and mn not in ('sub','swap') and n==1:
            e=s.parse_ea(ops[0],1); return W(0x50C0|(CC[mn[1:]]<<8)|s.ea_bits(e))+s.ext_bytes(e,pc+2,final)
        if mn=='moveq':
            v=s.ev(ops[0][1:],final=final); r=int(ops[1][1]); return W(0x7000|(r<<9)|(v&0xFF))
        if mn in ('move','movea'):
            z=sz('w'); src=s.parse_ea(ops[0],z); dst=s.parse_ea(ops[1],z)
            if dst['k']=='an' or mn=='movea':
                if z==0: raise AsmError('movea.b')
            code={0:1,1:3,2:2}[z]
            op=(code<<12)|(dst['reg']<<9)|(dst['mode']<<6)|s.ea_bits(src)
            b=W(op)+s.ext_bytes(src,pc+2,final); b+=s.ext_bytes(dst,pc+len(b),final)
            return b
        if mn=='lea':
            e=s.parse_ea(ops[0],2); r=int(ops[1][1]); return W(0x41C0|(r<<9)|s.ea_bits(e))+s.ext_bytes(e,pc+2,final)
        if mn=='pea':
            e=s.parse_ea(ops[0],2); return W(0x4840|s.ea_bits(e))+s.ext_bytes(e,pc+2,final)
        if mn in ('jsr','jmp'):
            e=s.parse_ea(ops[0],2); return W((0x4E80 if mn=='jsr' else 0x4EC0)|s.ea_bits(e))+s.ext_bytes(e,pc+2,final)
        if mn in ('add','sub','and','or','cmp','eor','adda','suba','cmpa','addi','subi','andi','ori','eori','cmpi','addq','subq'):
            z=sz('w')
            base={'add':0xD000,'sub':0x9000,'and':0xC000,'or':0x8000,'cmp':0xB000,'eor':0xB000}
            if mn in ('adda','suba','cmpa') or (mn in ('add','sub','cmp') and ops[1].lower()[0]=='a' and re.fullmatch(r'[aA][0-7]|sp',ops[1],re.I)):
                z=sz('w'); src=s.parse_ea(ops[0],z); r=7 if ops[1].lower()=='sp' else int(ops[1][1])
                b={'add':0xD000,'adda':0xD000,'sub':0x9000,'suba':0x9000,'cmp':0xB000,'cmpa':0xB000}[mn]
                return W(b|(r<<9)|((3 if z==1 else 7)<<6)|s.ea_bits(src))+s.ext_bytes(src,pc+2,final)
            if mn in ('addi','subi','andi','ori','eori','cmpi'):
                code={'addi':0x0600,'subi':0x0400,'andi':0x0200,'ori':0x0000,'eori':0x0A00,'cmpi':0x0C00}[mn]
                src=s.parse_ea(ops[0],z); dst=s.parse_ea(ops[1],z)
                b=W(code|(z<<6)|s.ea_bits(dst))+s.ext_bytes(src,pc+2,final); b+=s.ext_bytes(dst,pc+len(b),final); return b
            if mn in ('addq','subq'):
                v=s.ev(ops[0][1:],final=final); dst=s.parse_ea(ops[1],z)
                if final and not 1<=v<=8: raise AsmError('addq hors 1..8')
                return W((0x5000 if mn=='addq' else 0x5100)|((v&7)<<9)|(z<<6)|s.ea_bits(dst))+s.ext_bytes(dst,pc+2,final)
            # add/sub/and/or/cmp/eor : immediat -> variante I ; sinon Dn
            src=s.parse_ea(ops[0],z); dst=s.parse_ea(ops[1],z)
            if src['k']=='imm' and dst['k']!='dn' or (src['k']=='imm' and mn in('and','or','eor','add','sub','cmp') and dst['k']=='dn' and False):
                pass
            if mn=='eor' or (dst['k']!='dn' and mn!='cmp'):
                if src['k']!='dn': raise AsmError('%s %s,%s'%(mn,ops[0],ops[1]))
                op=base[mn]|(src['reg']<<9)|((z+4)<<6)|s.ea_bits(dst)
                return W(op)+s.ext_bytes(dst,pc+2,final)
            if mn=='cmp' and dst['k']!='dn': raise AsmError('cmp vers non-Dn')
            op=base[mn]|(dst['reg']<<9)|(z<<6)|s.ea_bits(src)
            return W(op)+s.ext_bytes(src,pc+2,final)
        if mn in ('tst','clr','neg','not','negx'):
            z=sz('w'); e=s.parse_ea(ops[0],z)
            code={'tst':0x4A00,'clr':0x4200,'neg':0x4400,'not':0x4600,'negx':0x4000}[mn]
            return W(code|(z<<6)|s.ea_bits(e))+s.ext_bytes(e,pc+2,final)
        if mn=='swap': return W(0x4840|int(ops[0][1]))
        if mn=='ext':
            r=int(ops[0][1]); return W((0x48C0 if size=='l' else 0x4880)|r)
        if mn=='unlk': return W(0x4E58|int(ops[0][1]))
        if mn=='link':
            v=s.ev(ops[1][1:],final=final); return W(0x4E50|int(ops[0][1]),v&0xFFFF)
        if mn in ('btst','bset','bclr','bchg'):
            t={'btst':0,'bchg':1,'bclr':2,'bset':3}[mn]
            if ops[0].startswith('#'):
                dst=s.parse_ea(ops[1],1); v=s.ev(ops[0][1:],final=final)
                return W(0x0800|(t<<6)|s.ea_bits(dst),v&0xFF)+s.ext_bytes(dst,pc+4,final)
            dst=s.parse_ea(ops[1],1)
            return W(0x0100|(int(ops[0][1])<<9)|(t<<6)|s.ea_bits(dst))+s.ext_bytes(dst,pc+2,final)
        if mn in ('mulu','muls','divu','divs'):
            e=s.parse_ea(ops[0],1); r=int(ops[1][1])
            code={'mulu':0xC0C0,'muls':0xC1C0,'divu':0x80C0,'divs':0x81C0}[mn]
            return W(code|(r<<9)|s.ea_bits(e))+s.ext_bytes(e,pc+2,final)
        if mn=='exg':
            a,b=ops[0].lower(),ops[1].lower()
            if a[0]=='d' and b[0]=='d': return W(0xC140|(int(a[1])<<9)|int(b[1]))
            if a[0]=='a' and b[0]=='a': return W(0xC148|(int(a[1])<<9)|int(b[1]))
            if a[0]=='d': return W(0xC188|(int(a[1])<<9)|int(b[1]))
            return W(0xC188|(int(b[1])<<9)|int(a[1]))
        if mn in ('lsl','lsr','asl','asr','rol','ror','roxl','roxr'):
            z=sz('w'); typ={'as':0,'ls':1,'rox':2,'ro':3}[mn[:-1]]; d=1 if mn[-1]=='l' else 0
            if n==1:
                e=s.parse_ea(ops[0],1); return W(0xE0C0|(typ<<9)|(d<<8)|s.ea_bits(e))+s.ext_bytes(e,pc+2,final)
            r=int(ops[1][1])
            if ops[0].startswith('#'):
                c=s.ev(ops[0][1:],final=final); return W(0xE000|((c&7)<<9)|(d<<8)|(z<<6)|(typ<<3)|r)
            return W(0xE000|(int(ops[0][1])<<9)|(d<<8)|(z<<6)|0x20|(typ<<3)|r)
        if mn=='movem':
            z=sz('w'); sl=0x40 if z==2 else 0
            def mask(rs,rev):
                m=0
                for part in rs.split('/'):
                    if '-' in part:
                        a,b=part.split('-'); ai=(8 if a[0].lower()=='a' else 0)+int(a[1]); bi=(8 if b[0].lower()=='a' else 0)+int(b[1])
                        idx=range(ai,bi+1)
                    else: idx=[(8 if part[0].lower()=='a' else 0)+int(part[1])]
                    for i in idx: m|=1<<(15-i if rev else i)
                return m
            if re.fullmatch(r'[dDaA][0-7]([-/][dDaA][0-7])*',ops[0]) :   # regs -> mem
                e=s.parse_ea(ops[1],z); rev=e['k']=='pre'
                return W(0x4880|sl|s.ea_bits(e),mask(ops[0],rev))+s.ext_bytes(e,pc+4,final)
            e=s.parse_ea(ops[0],z)
            return W(0x4C80|sl|s.ea_bits(e),mask(ops[1],False))+s.ext_bytes(e,pc+4,final)
        raise AsmError('instruction inconnue: %s %s'%(mn,ops))
    def assemble(s, src, org=0):
        lines=[]
        for ln in src.split('\n'):
            ln=s._strip_comment(ln).rstrip()
            if ln.strip(): lines.append(ln)
        base=dict(s.syms); labels={}
        for it in range(12):
            s.syms=dict(base); s.syms.update(labels)
            pc=org; newlabels={}; items=[]
            for ln in lines:
                body=ln
                m=re.match(r'^\s*([A-Za-z_.][\w.]*)\s*:(.*)$',body)
                if m: newlabels[m.group(1)]=pc; body=m.group(2)
                body=body.strip()
                if not body: continue
                m2=re.match(r'^([A-Za-z_]\w*)\s*(=|\bequ\b)\s*(.+)$',body)
                if m2:
                    s.syms[m2.group(1)]=s.ev(m2.group(3),final=False); base[m2.group(1)]=s.syms[m2.group(1)]; continue
                items.append((pc,body))
                s.syms.update(newlabels)
                pc+=len(s.encode_line(body,pc,False))
            if newlabels==labels: break
            labels=newlabels
        else: raise AsmError('pas de convergence')
        s.syms=dict(base); s.syms.update(labels)
        out=bytearray()
        for pc0,body in items:
            assert pc0==org+len(out),(pc0,org+len(out),body)
            out+=s.encode_line(body,pc0,True)
        return bytes(out), dict(labels)
    def _strip_comment(s,ln):
        q=None
        for i,ch in enumerate(ln):
            if q:
                if ch==q: q=None
            elif ch in '"\'': q=ch
            elif ch==';': return ln[:i]
        return ln
    def encode_line(s, body, pc, final):
        m=re.match(r'^(\S+)\s*(.*)$',body)
        mn=m.group(1); rest=m.group(2)
        low=mn.lower()
        if low in ('dc.b','dc.w','dc.l'):
            z=low[-1]; out=b''
            for p in split_ops(rest):
                if z=='b' and p.startswith(('"',"'")) and len(p)>=2:
                    out+=p[1:-1].encode('latin-1')
                elif z=='b': out+=struct.pack('>B',s.ev(p,pc,final)&0xFF)
                elif z=='w': out+=struct.pack('>H',s.ev(p,pc,final)&0xFFFF)
                else: out+=struct.pack('>I',s.ev(p,pc,final)&0xFFFFFFFF)
            return out
        if low=='ds.b': return bytes(s.ev(rest,final=final))
        if low=='ds.w': return bytes(2*s.ev(rest,final=final))
        if low=='even': return b'\0' if pc%2 else b''
        ops=split_ops(rest)
        # fixe la forme courte des bcc : essai court si la passe n'a pas encore tranche
        r=s.instr(mn,ops,pc,final)
        return r

def asm(src, org=0, syms=None):
    a=Asm(syms); a._ext_syms=set((syms or {}).keys())
    return a.assemble(src, org)

if __name__=='__main__':
    t='''
start:  moveq #0,d0
        move.l 2942(a6),d0
        lea 0(a6,d0.l),a1
        jsr 3406(a6)
        bra.s start
loop:   dbf d7,loop
        movem.l d0-d7/a0-a6,-(a7)
        movem.l (a7)+,d0-d7/a0-a6
        move.b #$55,(a0)+
        cmpi.b #$20,d2
        rts
        dc.b 'TIN0',0
'''
    b,l=asm(t); print(b.hex(' ',2)); print(l)
