"""HerosExe final : on garde l'executable ORIGINAL (stub + donnees compressees, 136 Ko) et on y ajoute
un patcheur qui, apres decompression, applique nos modifications (TIN0, langue, B/T/S/L plus tard...) sur l'image.
Fichier ~137 Ko au lieu de 250 Ko : Workbench refuse de lancer un outil trop gros par rapport a la memoire libre."""
import struct, sys
sys.path.insert(0,'.')
import patch_heros as P
def U(o): return struct.pack('>I',o)
def W(*ws): return b''.join(struct.pack('>H',w&0xFFFF) for w in ws)

def build_packed(orig_exe, image, debug=False):
    patched,info_p=P.build(image, debug=debug)
    n0=len(image)
    # liste des differences
    runs=[]; i=0
    while i<n0:
        if image[i]!=patched[i]:
            j=i
            while j<n0 and (image[j]!=patched[j] or any(image[k]!=patched[k] for k in range(j,min(j+8,n0)))): j+=1
            runs.append((i,j)); i=j
        else: i+=1
    patches=[(a,patched[a:b]) for a,b in runs]+[(n0,patched[n0:])]
    tab=b''
    for off,data in patches:
        tab+=U(off)+struct.pack('>H',len(data))+data
        if len(tab)%2: tab+=b'\0'
    tab+=U(0xFFFFFFFF)
    # routine
    r=bytearray()
    r+=W(0x48e7,0xc0a0)                       # movem.l d0-d1/a0/a2,-(a7)
    p_tab=len(r); r+=W(0x41fa,0)              # lea tab(pc),a0
    lp=len(r)
    r+=W(0x2018); p_bmi=len(r); r+=b'\x6b\x00'    # move.l (a0)+,d0 ; bmi dn
    r+=W(0x3218,0x45f1,0x0800,0x5341)         # move.w (a0)+,d1 ; lea 0(a1,d0.l),a2 ; subq.w #1,d1
    r+=W(0x14d8,0x51c9,0xfffc)                # cp: move.b (a0)+,(a2)+ ; dbf d1,cp
    r+=W(0x2008,0x5280,0x0880,0x0000,0x2040)  # move.l a0,d0 ; addq.l #1,d0 ; bclr #0,d0 ; movea.l d0,a0
    d=lp-(len(r)+2); r+=bytes([0x60,d&255])   # bra lp
    dn=len(r)
    r[p_bmi+1]=(dn-(p_bmi+2))&255
    r+=W(0x4cdf,0x0503,0x2f49,0x003c)         # movem.l (a7)+,d0-d1/a0/a2 ; move.l a1,60(a7)
    p_back=len(r); r+=W(0x6000,0)             # bra.w $2e
    tab_off=len(r)
    if len(r)%2: r+=b'\0'
    tab_off=len(r)
    code=bytearray(r)+tab
    while len(code)%4: code+=b'\0'
    # stub original
    HDR=0x24
    st=bytearray(orig_exe[0x2c:0x2c+72])
    assert st[0x2a:0x2e]==W(0x2f49,0x003c)
    R0=72                                      # debut de la routine dans le hunk 0
    st[0x2a:0x2e]=W(0x6000,(R0-(0x2a+2)))
    code[p_tab+2:p_tab+4]=struct.pack('>h',tab_off-(p_tab+2))
    code[p_back+2:p_back+4]=struct.pack('>h',0x2e-(R0+p_back+2))
    h0=bytes(st)+bytes(code)
    # nouvel en-tete
    ext=len(patched)-n0
    hunk1_longs=(0xf376*4+ ((ext+3)&~3) + ((info_p['bss']+3)&~3))//4
    out=bytearray(orig_exe)
    assert struct.unpack('>I',out[0x14:0x18])[0]==0x12
    out[0x14:0x18]=U(len(h0)//4)
    out[0x18:0x1c]=U(0x40000000|hunk1_longs)
    new=bytes(out[:0x24])+U(0x3e9)+U(len(h0)//4)+h0+bytes(out[0x2c+72:])
    return new, patched, dict(patches=len(patches),routine=len(code),hunk0=len(h0))

if __name__=='__main__':
    orig=open('../adf/dream13/HEROS/HerosExe','rb').read()
    img=open('image.bin','rb').read()
    dbg='debug' in sys.argv
    new,patched,info=build_packed(orig,img,dbg)
    open('HerosExe-packed-debug' if dbg else 'HerosExe-packed','wb').write(new)
    print(len(new),info)
