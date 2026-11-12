"""Patch de HerosExe (image decompressee) : page TIN0 + choix de la langue DataHeros-<arg>."""
import struct, sys
sys.path.insert(0,'.')
from hunk import ecrire_exe
import hooks
sys.path.insert(0,'../m3')
import mapdata

def W(*ws): return b''.join(struct.pack('>H',w&0xFFFF) for w in ws)
def L(v): return struct.pack('>I',v&0xFFFFFFFF)
def br(op,frm,to):      # bcc.s ; frm = adresse de l'octet d'opcode
    d=to-(frm+2); assert -128<=d<=127 and d!=0, d
    return bytes([op,d&255])

import os
CLOSEWB=os.environ.get('CLOSEWB')=='1'
FSTEP=int(os.environ.get('FSTEP','3'))
def build(image, bufsize=0x20000, debug=False):
    img=bytearray(image)
    hooks.ZTAB=mapdata.ztab([image[0x18ec+i*58+0x18:0x18ec+i*58+0x1c].strip(b'\0').decode('latin-1') for i in range(212)]); hooks.SLOTS=mapdata.slots()
    base_len=len(img)
    assert base_len==0x3cdd8
    # --- 1. constantes de taille du buffer DataHeros
    n=0
    for off in range(0,0x400):
        if img[off:off+4]==L(0x1b3aa): img[off:off+4]=L(bufsize); n+=1
    assert n==4, n
    # --- 2. chargeur : nom = pointeur stocke en 0x51e
    assert img[0x1fc:0x200]==W(0x41ed,0x051e)
    img[0x1fc:0x200]=W(0x206d,0x051e)
    # --- 3. region intro 0x6b8..0x715
    INTRO=0x6b8; END=0x716
    assert img[INTRO:INTRO+10]==bytes.fromhex('203c0000734d4eae6e28')
    c=bytearray()
    c+=W(0x203c)+L(0x734d)+W(0x4eae,0x6e28)          # musique/prep
    pos_lea=len(c); c+=W(0x41fa,0)                    # lea names(pc),a0  (disp a completer)
    c+=W(0x2f08)                                      # move.l a0,-(a7)
    loop=len(c)
    c+=W(0x2057,0x2250,0x5897)                        # movea.l (a7),a0 ; movea.l (a0),a1 ; addq.l #4,(a7)
    c+=W(0x203c)+L(0x088c)+W(0x4eae,0x0716)          # move.l #$88c,d0 ; jsr 1814(a6)
    c+=W(0x4a2e,0x6af2)                               # tst.b 27378(a6)
    pos_bmi=len(c); c+=b'\x6b\x00'
    c+=W(0x2057,0x4a90)                               # movea.l (a7),a0 ; tst.l (a0)
    pos_bne=len(c); c+=b'\x66\x00'
    done=len(c)
    c+=W(0x588f,0x4e75)                               # addq.l #4,a7 ; rts
    c[pos_bmi:pos_bmi+2]=br(0x6b,pos_bmi,done)
    c[pos_bne:pos_bne+2]=br(0x66,pos_bne,loop)
    names=len(c)
    for nm in (b'TIN0',b'TIN1',b'TIN2',b'TIN3',b'TIN4'): c+=nm
    c+=L(0)
    c[pos_lea+2:pos_lea+4]=struct.pack('>h',names-(pos_lea+2))
    gw=len(c)
    GW=INTRO+gw
    ext_off=base_len
    # passerelle : lea 0(pc),a1 ; adda.l #D,a1 ; jmp (a1)
    c+=W(0x43fa,0x0000)+W(0xd3fc)+L(ext_off-(GW+2))+W(0x4ed1)
    assert len(c)<=END-INTRO, len(c)
    c+=b'\x4e\x71'*((END-INTRO-len(c))//2)
    img[INTRO:END]=c
    # --- 4b. accroches : stub commun (jsr $70c(a6)) + pointeur rempli par le code ext
    assert img[0x70c:0x716]==b'\x4e\x71'*5 or True
    img[0x70c:0x716]=W(0x2f3a,0x0004,0x4e75)+L(0)
    assert img[0xb52:0xb56]==W(0x202e,0x0b7e)
    if not os.environ.get('NOHOOKS') and not os.environ.get('NOH1'): img[0xb52:0xb56]=W(0x4eae,0x070c)
    assert img[0x5664:0x5668]==W(0x4eae,0x6aaa)
    if not os.environ.get('NOHOOKS') and not os.environ.get('NOH2'): img[0x5664:0x5668]=W(0x4eae,0x070c)
    assert img[0x732:0x736]==W(0x4eae,0x0964)
    if not os.environ.get('NOHOOKS'): img[0x732:0x736]=W(0x4eae,0x070c)     # site 4 : attente de clic des pages d'intro (touche L)
    assert img[0x5e8:0x5ec]==W(0x4eae,0x0964)
    if not os.environ.get('NOHOOKS'): img[0x5e8:0x5ec]=W(0x4eae,0x070c)     # site 5 : ecran-titre
    assert img[0x577c:0x5780]==W(0x4eae,0x0964)
    if not os.environ.get('NOHOOKS'): img[0x577c:0x5780]=W(0x4eae,0x070c)     # site 6 : fondus plus courts
    assert img[0x6d7a:0x6d7e]==W(0x3019,0x322a)
    assert img[0x5756:0x575a]==W(0x3e3c,0x000f)
    if not os.environ.get('NOHOOKS'):
        img[0x6d7a:0x6d7e]=W(0x4eae,0x070c)     # site 7 : fondu de palette plus rapide (pas de 2)
        img[0x5756:0x575a]=W(0x3e3c,(15+FSTEP-1)//FSTEP-1)     # 15/FSTEP etapes au lieu de 16
    assert img[0xba4:0xba8]==W(0xd16e,0x0b84)
    if not os.environ.get('NOHOOKS'): img[0xba4:0xba8]=W(0x4eae,0x070c)     # site 8 : plafond de vie a 32
    assert img[0x2f0:0x2f4]==W(0x4ead,0x0476)
    if not os.environ.get('NOHOOKS'): img[0x2f0:0x2f4]=W(0x4ead,0x070c)     # jsr $70c(a5) : effacement des donnees saute pendant S/L
    # --- 4. point d'entree : bsr.w GW
    assert img[0:4]==W(0x6100,0x008a)
    img[0:4]=W(0x6000)+struct.pack('>H',GW-2)   # bra.w : le code ext appelle lui-meme la suite (offset 4) en sous-programme
    # --- 5. code ext
    e=bytearray()
    dbgfix=[]
    def dbg_alert(tag):
        if not debug: return
        e.extend(W(0x48e7,0xfffe,0x2c78,0x0004))
        dbgfix.append((len(e),'int')); e.extend(W(0x43fa,0))
        e.extend(W(0x7000,0x4eae,0xfdd8,0x4a80)); q=len(e); e.extend(b'\x67\x00')
        e.extend(W(0x2c40,0x7000))
        dbgfix.append((len(e),tag)); e.extend(W(0x41fa,0))
        e.extend(W(0x723c,0x4eae,0xffa6,0x224e,0x2c78,0x0004,0x4eae,0xfe62))
        e[q:q+2]=br(0x67,q,len(e))
        e.extend(W(0x4cdf,0x7fff))
    # d0 = longueur des arguments, a0 = arguments (CLI) : le stub les restaure avant d'entrer dans l'image.
    # Depuis Workbench : on lit le message WBStartup ; si une icone "projet" a ete cliquee, son nom
    # (arg 1) sert de suffixe : en.info -> DataHeros-en
    pass  # S0 retire
    e+=W(0x7a00)                              # moveq #0,d5 (message WBStartup)
    e+=W(0x2600,0x2848,0x7808)                # move.l d0,d3 ; movea.l a0,a4 ; moveq #8,d4 (longueur max du suffixe)
    e+=W(0x2c78,0x0004)                       # movea.l 4.w,a6
    e+=W(0x93c9,0x4eae,0xfeda)                # suba.l a1,a1 ; jsr -294(a6)  FindTask(0)
    e+=W(0x2640,0x4aab,0x00ac)                # movea.l d0,a3 ; tst.l 172(a3)  pr_CLI
    q_cli=len(e); e+=b'\x66\x00'              # bne cli
    e+=W(0x47eb,0x005c,0x204b,0x4eae,0xfe80)  # lea 92(a3),a3 ; movea.l a3,a0 ; jsr -384(a6) WaitPort
    e+=W(0x202b,0x0014,0x4e71)                # move.l 20(a3),d0 (1er message, SANS le retirer : le jeu fait lui-meme GetMsg/ReplyMsg) ; nop
    e+=W(0x4a80); q_w1=len(e); e+=b'\x67\x00'  # tst.l d0 ; beq wbno
    e+=W(0x4e71)                              # (d5 reste 0 : le jeu repond lui-meme au message)
    e+=W(0x2640,0x7201,0xb2ab,0x001c)         # movea.l d0,a3 ; moveq #1,d1 ; cmp.l 28(a3),d1
    q_w2=len(e); e+=b'\x6e\x00'              # bgt wbno  (aucun argument)
    e+=W(0x246b,0x0024)                       # movea.l 36(a3),a2   (ArgList)
    e+=W(0x4a92); q_nl=len(e); e+=b'\x67\x00'  # tst.l (a2) ; beq nolock
    e+=W(0x2a4e)                              # movea.l a6,a5  (exec)
    p_dosn=len(e); e+=W(0x43fa,0x0000)        # lea 0(pc),a1  -> base+0x512 apres correction
    p_dosn2=len(e); e+=W(0x93fc)+L(0)         # suba.l #X,a1
    e+=W(0x7000,0x4eae,0xfdd8)                # moveq #0,d0 ; jsr -552(a6)  OpenLibrary("dos.library")
    e+=W(0x4a80); q_nl2=len(e); e+=b'\x67\x00'  # tst.l d0 ; beq nolock
    e+=W(0x2c40,0x2212,0x4eae,0xff82)         # movea.l d0,a6 ; move.l (a2),d1 ; jsr -126(a6)  CurrentDir(lock du repertoire de l'outil)
    e+=W(0x2c4d)                              # movea.l a5,a6
    nolock=len(e)
    e+=W(0x7202,0xb2ab,0x001c)                # moveq #2,d1 ; cmp.l 28(a3),d1
    q_w2b=len(e); e+=b'\x6e\x00'             # bgt wbno  (pas de projet)
    e+=W(0x286a,0x000c)                       # movea.l 12(a2),a4  (nom du projet)
    e+=W(0xb8fc,0x0000); q_w3=len(e); e+=b'\x67\x00'   # cmpa.w #0,a4 ; beq wbno
    # nom du projet "heros - francais" : le suffixe = 2 premieres lettres du dernier mot ("fr")
    e+=W(0x204c)                              # movea.l a4,a0
    sc=len(e); e+=W(0x1418); q_sc=len(e); e+=b'\x67\x00'   # move.b (a0)+,d2 ; beq fin
    e+=W(0x0c02,0x0020); e+=br(0x66,len(e),sc)             # cmpi.b #$20,d2 ; bne sc
    e+=W(0x2848); e+=br(0x60,len(e),sc)                    # movea.l a0,a4 ; bra sc
    scend=len(e); e[q_sc:q_sc+2]=br(0x67,q_sc,scend)
    e+=W(0x7a02) if False else b''
    e+=W(0x7802)                              # moveq #2,d4
    e+=W(0x7620); q_br=len(e); e+=b'\x60\x00'  # moveq #32,d3 ; bra cli
    wbno=len(e); e+=W(0x7600)                 # moveq #0,d3
    cli=len(e); e+=W(0x2003,0x204c)           # move.l d3,d0 ; movea.l a4,a0
    for p,op,t in ((q_cli,0x66,cli),(q_w1,0x67,wbno),(q_w2,0x6e,wbno),(q_nl,0x67,nolock),(q_nl2,0x67,nolock),(q_w2b,0x6e,wbno),(q_w3,0x67,wbno)):
        e[p:p+2]=br(op,p,t)
    e[p_dosn+2:p_dosn+4]=W(0)
    e[p_dosn2+2:p_dosn2+6]=L(ext_off+p_dosn+2-0x512)
    e[q_br:q_br+2]=br(0x60,q_br,cli)
    p_lea_name=len(e); e+=W(0x45fa,0)    # lea name+10(pc),a2
    e+=W(0x7200)                  # moveq #0,d1
    lp=len(e)
    e+=W(0x4a80); p1=len(e); e+=b'\x6f\x00'      # tst.l d0 ; ble done
    e+=W(0x1418,0x5380)           # move.b (a0)+,d2 ; subq.l #1,d0
    e+=W(0x4a81); p2=len(e); e+=b'\x66\x00'      # tst.l d1 ; bne tok
    e+=W(0x0c02,0x0020); e+=br(0x67,len(e),lp)   # cmpi.b #$20,d2 ; beq lp
    e+=W(0x0c02,0x0009); e+=br(0x67,len(e),lp)   # cmpi.b #9,d2 ; beq lp
    tok=len(e)
    e+=W(0x0c02,0x0020); p3=len(e); e+=b'\x63\x00'   # cmpi.b #$20,d2 ; bls done
    e+=W(0xb244); p4=len(e); e+=b'\x6c\x00'   # cmp.w d4,d1 ; bge done
    e+=W(0x14c2,0x5281); e+=br(0x60,len(e),lp)       # move.b d2,(a2)+ ; addq.l #1,d1 ; bra lp
    dn=len(e)
    for p,op in ((p1,0x6f),(p3,0x63),(p4,0x6c)): e[p:p+2]=br(op,p,dn)
    e[p2:p2+2]=br(0x66,p2,tok)
    e+=W(0x4a81); p5=len(e); e+=b'\x66\x00'          # tst.l d1 ; bne hav
    e+=W(0x14fc,0x0066,0x14fc,0x0072)                # 'f','r'
    hav=len(e); e[p5:p5+2]=br(0x66,p5,hav)
    e+=W(0x4212)                                     # clr.b (a2)
    # a1 = base
    p_ref=len(e); e+=W(0x43fa,0x0000)                # lea 0(pc),a1 (a1 = ext+p_ref+2)
    p_sub=len(e); e+=W(0x93fc)+L(0)                  # suba.l #(ext_off+p_ref+2),a1
    e[p_sub+2:p_sub+6]=L(ext_off+p_ref+2)
    e+=W(0x2449)                                     # movea.l a1,a2  (base)
    p_hkp=len(e); e+=W(0x41fa,0)                     # lea HK(pc),a0
    e+=W(0x2548,0x0712)                              # move.l a0,$712(a2)   (pointeur du stub)
    p_bss0=len(e); e+=W(0x41fa,0)                    # lea BSS(pc),a0
    e+=W(0x303c,hooks.BSS_SIZE//4-1)                 # move.w #n-1,d0 : toute la BSS est remise a zero (la memoire du hunk n'est pas effacee par le chargeur)
    e+=W(0x4298,0x51c8,0xfffc)                       # clr.l (a0)+ ; dbf d0,-4
    p_lea2=len(e); e+=W(0x41fa,0)                    # lea name(pc),a0
    e+=W(0x2548,0x051e)                              # move.l a0,$51e(a2)
    if debug:   # copie le nom dans le message S1
        dbgfix.append((len(e),'name')); e+=W(0x41fa,0)
        dbgfix.append((len(e),'S1txt')); e+=W(0x43fa,0)
        e+=W(0x700b,0x12d8,0x51c8,0xfffc)            # moveq #11,d0 ; move.b (a0)+,(a1)+ ; dbf
    dbg_alert('S1')
    # ferme Workbench pour liberer de la CHIP (rouvert a la sortie)
    p_int0=len(e); e+=W(0x43fa,0)                    # lea intname(pc),a1
    e+=W(0x7000,0x4eae,0xfdd8)                       # moveq #0,d0 ; jsr -552(a6) OpenLibrary(intuition)
    e+=W(0x2c00)                                     # move.l d0,d6
    q_ni=len(e); e+=b'\x67\x00'                      # beq noint
    e+=W(0x2c40)+(W(0x4eae,0xffb2) if CLOSEWB else W(0x4e71,0x4e71))+W(0x2c78,0x0004)         # movea.l d0,a6 ; jsr -78(a6) CloseWorkBench ; movea.l 4.w,a6
    noint=len(e); e[q_ni:q_ni+2]=br(0x67,q_ni,noint)
    e+=W(0x2f05,0x2f06)                              # move.l d5,-(a7) ; move.l d6,-(a7)
    p_back=len(e); e+=W(0x41fa,0)                    # lea back(pc),a0
    e+=W(0x2f08)                                     # move.l a0,-(a7)
    e+=W(0x41ea,0x0004,0x2f08)                       # lea 4(a2),a0 ; move.l a0,-(a7)  (continuation = offset 4)
    e+=W(0x43ea,0x008c)                              # lea $8c(a2),a1
    e+=W(0x4e91)                                     # jsr (a1)  : init du jeu
    p_ok=len(e); e+=b'\x6a\x00\x00\x00'                # bpl.w ok
    e+=W(0x2c78,0x0004)                              # echec : alerte lisible (DisplayAlert) avec la plus grande zone CHIP libre
    e+=W(0x223c,0x0002,0x0002,0x4eae,0xff28)         # move.l #$20002,d1 ; jsr -216(a6)  AvailMem(CHIP|LARGEST)
    e+=W(0xe088,0xe488)                              # lsr.l #8,d0 ; lsr.l #2,d0  -> Ko
    p_num=len(e); e+=W(0x41fa,0)                     # lea msgnum+3(pc),a0
    e+=W(0x7403)                                     # moveq #3,d2
    dl=len(e)
    e+=W(0x80fc,0x000a,0x4840,0x0600,0x0030,0x1080,0x5388,0x4240,0x4840)   # divu #10,d0 ; swap ; addi.b #'0' ; move.b d0,(a0) ; subq.l #1,a0 ; clr.w d0 ; swap
    e+=W(0x51ca,(dl-(len(e)+2))&0xFFFF)              # dbf d2,dl
    # diagnostic : le fichier DataHeros-xx s'ouvre-t-il ? (sinon "file missing", sinon "low memory")
    p_srcB=len(e); e+=W(0x45fa,0)                    # lea srcB(pc),a2
    p_dosn3=len(e); e+=W(0x43fa,0)                   # lea dosname(pc),a1
    e+=W(0x7000,0x4eae,0xfdd8)                       # moveq #0,d0 ; jsr -552(a6) OpenLibrary(dos)
    e+=W(0x4a80); q_d1=len(e); e+=b'\x67\x00'        # tst.l d0 ; beq chosen
    e+=W(0x2c40)                                     # movea.l d0,a6
    p_nm=len(e); e+=W(0x41fa,0)                      # lea name(pc),a0
    e+=W(0x2208,0x243c,0x0000,0x03ed,0x4eae,0xffe2)  # move.l a0,d1 ; move.l #1005,d2 ; jsr -30(a6) Open
    e+=W(0x2200); q_d2=len(e); e+=b'\x67\x00'        # move.l d0,d1 ; beq nofile
    e+=W(0x4eae,0xffdc)                              # jsr -36(a6) Close
    q_d3=len(e); e+=b'\x60\x00'                      # bra chosen
    nofile=len(e); p_srcA=len(e); e+=W(0x45fa,0)     # lea srcA(pc),a2
    chosen=len(e)
    e[q_d1:q_d1+2]=br(0x67,q_d1,chosen); e[q_d2:q_d2+2]=br(0x67,q_d2,nofile); e[q_d3:q_d3+2]=br(0x60,q_d3,chosen)
    e+=W(0x2c78,0x0004)                              # movea.l 4.w,a6
    p_ph=len(e); e+=W(0x41fa,0)                      # lea ph(pc),a0
    e+=W(0x700c,0x10da,0x51c8,0xfffc)                # moveq #12,d0 ; cp: move.b (a2)+,(a0)+ ; dbf d0,cp
    p_int=len(e); e+=W(0x43fa,0)                     # lea intname(pc),a1
    e+=W(0x7000,0x4eae,0xfdd8)                       # moveq #0,d0 ; jsr -552(a6)  OpenLibrary(intuition)
    e+=W(0x4a80); p_nb=len(e); e+=b'\x67\x00'        # tst.l d0 ; beq fin
    e+=W(0x2c40,0x7000)                              # movea.l d0,a6 ; moveq #0,d0
    p_msg=len(e); e+=W(0x41fa,0)                     # lea msg(pc),a0
    e+=W(0x7250,0x4eae,0xffa6)                       # moveq #80,d1 ; jsr -90(a6)  DisplayAlert(RECOVERY)
    fin=len(e); e+=W(0x70ff)                         # moveq #-1,d0
    ok=len(e); e+=W(0x4e75)                          # rts  (-> continuation du jeu, offset 4, flags d'init)
    back=len(e)
    e+=W(0x2e00)
    dbg_alert('S3')
    e+=W(0x2c1f,0x2a1f,0x2c78,0x0004)         # move.l d0,d7 ; move.l (a7)+,d6 ; move.l (a7)+,d5 ; movea.l 4.w,a6
    e+=W(0x4a86); q_nb=len(e); e+=b'\x67\x00'        # tst.l d6 ; beq nowb
    e+=W(0x2c46,0x4eae,0xff2e,0x2c78,0x0004,0x2246,0x4eae,0xfe62)  # a6=d6 ; jsr -210 OpenWorkBench ; a6=exec ; a1=d6 ; jsr -414 CloseLibrary
    nowb=len(e); e[q_nb:q_nb+2]=br(0x67,q_nb,nowb)
    e+=W(0x4a85); q_nm=len(e); e+=b'\x67\x00'        # tst.l d5 ; beq nomsg
    e+=W(0x4eae,0xff7c,0x2245,0x4eae,0xfe86)         # jsr -132 Forbid ; movea.l d5,a1 ; jsr -378 ReplyMsg
    nomsg=len(e); e[q_nm:q_nm+2]=br(0x67,q_nm,nomsg)
    e+=W(0x2007,0x4e75)                              # move.l d7,d0 ; rts
    e[p_ok+2:p_ok+4]=struct.pack('>h',ok-(p_ok+2)); e[p_nb:p_nb+2]=br(0x67,p_nb,fin)
    hk_pos=len(e)
    def hsyms(bss,recs):
        d=dict(BSS=bss, NHIST=hooks.NHIST, EXTHK=ext_off+hk_pos, NSCENES=hooks.NSCENES, SCENE0=hooks.SCENE0, RECSZ=hooks.RECSZ, VERS=0x00010003, NZONES=len(hooks.SLOTS), NZ1=len(mapdata.ZONES), FADEMASK=int(os.environ.get('FADEMASK','1')), FSTEP=FSTEP)
        for i,pg in enumerate(hooks.PAGES): d['REC_'+pg]=ext_off+recs+i*hooks.RECSZ
        d['REC_FIRST']=ext_off+recs; d['REC_END']=ext_off+recs+len(hooks.PAGES)*hooks.RECSZ
        return d
    hk0,hl0=hooks.assemble(hk_pos,hsyms(0,0)); e+=hk0
    rec_pos=len(e); e+=b'\0'*(len(hooks.PAGES)*hooks.RECSZ)
    if len(e)%2: e+=b'\0'
    name=len(e); e+=b'DataHeros-'+b'\0'*12
    intn=len(e); e+=b'intuition.library\0'
    dosn=len(e); e+=b'dos.library\0'
    srcA=len(e); e+=b'file missing '
    srcB=len(e); e+=b'low memory   '
    if len(e)%2: e+=b'\0'
    dl={}
    if debug:
        def seg0(t): return struct.pack('>HB',24,16)+t+b'\0\0'
        dl['S0']=len(e); e+=seg0(b'S0: ext code reached')
        dl['S1']=len(e); e+=struct.pack('>HB',24,16)+b'S1 name='; dl['S1txt']=len(e); e+=b'?'*12+b'\0\0'
        dl['S3']=len(e); e+=seg0(b'S3: game returned')
        dl['int']=intn; dl['name']=name
        for p,t in dbgfix: e[p+2:p+4]=struct.pack('>h',dl[t]-(p+2))
    def seg(x,y,t,c): return struct.pack('>HB',x,y)+t+b'\0'+bytes([c])
    pre=b'Largest CHIP block: '
    msgo=len(e)
    e+=seg(24,16,b'HEROS: START FAILED',1)+seg(24,32,b'Cause: '+b'?'*13,1)
    phpos=msgo+len(seg(24,16,b'HEROS: START FAILED',1))+3+7
    e+=struct.pack('>HB',24,48)+pre; numo=len(e); e+=b'0000 KB (needs about 150)\0\0'
    e[p_msg+2:p_msg+4]=struct.pack('>h',msgo-(p_msg+2))
    e[p_num+2:p_num+4]=struct.pack('>h',numo+3-(p_num+2))
    for p,t in ((p_srcB,srcB),(p_dosn3,dosn),(p_nm,name),(p_srcA,srcA),(p_ph,phpos)): e[p+2:p+4]=struct.pack('>h',t-(p+2))
    e[p_int+2:p_int+4]=struct.pack('>h',intn-(p_int+2))
    e[p_int0+2:p_int0+4]=struct.pack('>h',intn-(p_int0+2))
    e[p_back+2:p_back+4]=struct.pack('>h',back-(p_back+2))
    e[p_lea_name+2:p_lea_name+4]=struct.pack('>h',name+10-(p_lea_name+2))
    e[p_lea2+2:p_lea2+4]=struct.pack('>h',name-(p_lea2+2))
    while len(e)%4: e+=b'\0'
    bss_off=len(e)
    hk1,hl=hooks.assemble(hk_pos,hsyms(ext_off+bss_off-ext_off,rec_pos)); assert len(hk1)==len(hk0) and hl==hl0
    e[hk_pos:hk_pos+len(hk1)]=hk1
    recs=hooks.build_records(bytes(image[0x1926:0x1926+hooks.RECSZ]),ext_off,hl,rec_pos)
    e[rec_pos:rec_pos+len(recs)]=recs
    e[p_hkp+2:p_hkp+4]=struct.pack('>h',hk_pos-(p_hkp+2))
    e[p_bss0+2:p_bss0+4]=struct.pack('>h',bss_off-(p_bss0+2))
    img+=e
    return bytes(img), dict(GW=GW, ext=ext_off, name=ext_off+name, extlen=len(e), intro_used=gw+12, bss=hooks.BSS_SIZE)

if __name__=='__main__':
    img=open('image.bin','rb').read()
    out,info=build(img)
    print(info)
    open('image_patched.bin','wb').write(out)
    print(ecrire_exe('Heros-patch',out), 'octets')
