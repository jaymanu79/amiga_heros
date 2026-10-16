"""Code ext : accroches du jeu (retour arriere B, triche T, sauver S, charger L). Assemble avec asm68k.

Principe : trois endroits du jeu appellent le stub commun (jsr $70c(a6) -> HK) :
  site 1 ($b52)  debut de chaque iteration de la boucle des scenes -> empile un instantane de l'etat
  site 2 ($5664) boucle d'attente d'un choix                       -> touches B T S L + fleches
  site 3 ($2f0)  routine d'arret du jeu : l'effacement des donnees est saute pendant S/L
Les pages T/S/L sont de vraies scenes (enregistrements de 58 octets copies de TC1, textes dans DataHeros-xx),
leurs choix F1-F5 appellent des routines de ce code (liens negatifs, comme les routines d'origine)."""
import struct, asm68k

NHIST = 40
SNAP = 16
NSCENES = 212
SCENE0 = 0x18ec
RECSZ = 58
PAGES = ['TMP1', 'TMP2', 'TSAV', 'TLOD', 'TSOK', 'TSER', 'TLER']
BSS_SIZE = 4 + NHIST*SNAP + 4 + 4 + 24 + 4 + 8 + 4     # hcnt+pad, hist, RET, NAV/NOWIPE, BUF, marge

ROUTINES = {   # page -> 5 liens (noms d'etiquettes ; 0 = aucun)
    'TMP1': ['r_ret', 'r_ret', 'r_ret', 'r_ret', 'r_ret'],
    'TMP2': ['r_ret', 'r_ret', 'r_ret', 'r_ret', 'r_ret'],
    'TSAV': ['r_sv1', 'r_sv2', 'r_sv3', 'r_sv4', 'r_ret'],
    'TLOD': ['r_ld1', 'r_ld2', 'r_ld3', 'r_ld4', 'r_ret'],
    'TSOK': ['r_ret', 0, 0, 0, 0],
    'TSER': ['r_ret', 0, 0, 0, 0],
    'TLER': ['r_ret', 0, 0, 0, 0],
}

ZTAB = b''
SLOTS = []

def _dc(label, vals, kind):
    out = [label + ':']
    for i in range(0, len(vals), 12):
        out.append('        dc.%s    %s' % (kind, ','.join(str(v) for v in vals[i:i+12])))
    return '\n'.join(out) + '\n'

import os
DBG = os.environ.get('DBG') == '1'

def source():
    return _source() + _dc('ZTAB', list(ZTAB), 'b') + '        even\n' + _dc('SLOTS', SLOTS, 'w')

def _source():
    return _src().replace('@@DBGKEYS@@', DBGKEYS if DBG else '').replace('@@DBGCODE@@', DBGCODE if DBG else '')

DBGKEYS = '        cmpi.b  #$10,d0\n        beq     kd1\n        cmpi.b  #$11,d0\n        beq     kd2\n        cmpi.b  #$12,d0\n        beq     kd3\n        cmpi.b  #$13,d0\n        beq     kd4\n'
DBGCODE = 'kd1:    move.l  #$27e0,d1\n        bra     kdgo\nkd2:    move.l  #$2f5a,d1\n        bra     kdgo\nkd3:    move.l  #$2c68,d1\n        bra     kdgo\nkd4:    move.l  #$4092,d1\nkdgo:   clr.b   $6af4(a6)\n        move.l  d1,$b7e(a6)\n        clr.w   $b82(a6)\n        st      $6af3(a6)\n        rts\n'

def _src():
    return '''
HCNT    = BSS
HIST    = BSS+4
RET     = BSS+4+NHIST*16
NOPUSH  = BSS+4+NHIST*16+4
NOWIPE  = BSS+4+NHIST*16+5
CZ      = BSS+4+NHIST*16+6
BUF     = BSS+4+NHIST*16+8
LREQ    = BSS+4+NHIST*16+36
ZLONG   = BSS+4+NHIST*16+40
FCNT    = BSS+4+NHIST*16+44

; ---- point d'entree des accroches (jsr $70c(a6) -> stub -> ici) ; pile : [retour dans le jeu]
HK:     movem.l d0-d7/a0-a5,-(a7)
        lea     HK(pc),a0
        suba.l  #EXTHK,a0                 ; a0 = base de l'image
        lea     $b56(a0),a1
        cmpa.l  56(a7),a1
        beq     site1
        lea     $2f4(a0),a1
        cmpa.l  56(a7),a1
        beq     site3
        lea     $736(a0),a1
        cmpa.l  56(a7),a1
        beq     site4
        lea     $5ec(a0),a1
        cmpa.l  56(a7),a1
        beq     site5
        lea     $5780(a0),a1
        cmpa.l  56(a7),a1
        beq     site6
        lea     $6d7e(a0),a1
        cmpa.l  56(a7),a1
        beq     site7
        lea     $ba8(a0),a1
        cmpa.l  56(a7),a1
        beq     site8
        bsr     keys                      ; site 2 : boucle d'attente d'un choix (a6 = base)
        movem.l (a7)+,d0-d7/a0-a5
        jsr     $6aaa(a6)                 ; routine d'origine (touches F1-F5)
        rts
site1:  bsr     push                      ; site 1 : debut d'iteration (a6 = base)
        lea     LREQ(pc),a1
        tst.b   (a1)
        beq     s1_n
        clr.b   (a1)                      ; L demande pendant l'intro : page de chargement avant la 1re scene
        move.l  #REC_TLOD,d1
        bsr     openpg
s1_n:   movem.l (a7)+,d0-d7/a0-a5
        move.l  $b7e(a6),d0               ; instruction d'origine
        rts
site8:  move.w  $b82(a6),d0              ; site 8 : variation de vie, plafonnee a 32 (largeur de la jauge de coeurs)
        add.w   d0,$b84(a6)
        cmpi.w  #32,$b84(a6)
        ble     s8_o
        move.w  #32,$b84(a6)
s8_o:   tst.w   $b84(a6)                  ; les drapeaux servent au bpl d'origine
        movem.l (a7)+,d0-d7/a0-a5
        rts
site7:  movea.l 36(a7),a1                 ; site 7 : remplace la routine d'origine 0x6d7a (fondu de palette, pas de 1) : pas de 2
        movea.l 40(a7),a2
        move.w  30(a7),d7
f_l:    move.w  (a1)+,d0
        move.w  2(a2),d1
        moveq   #0,d5
        move.w  d0,d2
        andi.w  #$f,d2
        move.w  d1,d3
        andi.w  #$f,d3
        sub.w   d3,d2
        cmpi.w  #FSTEP,d2
        ble     f0a
        moveq   #FSTEP,d2
f0a:  cmpi.w  #-2,d2
        bge     f0b
        moveq   #-FSTEP,d2
f0b:  add.w   d2,d3
        or.w    d3,d5
        move.w  d0,d2
        lsr.w   #4,d2
        andi.w  #$f,d2
        move.w  d1,d3
        lsr.w   #4,d3
        andi.w  #$f,d3
        sub.w   d3,d2
        cmpi.w  #FSTEP,d2
        ble     f1a
        moveq   #FSTEP,d2
f1a:  cmpi.w  #-2,d2
        bge     f1b
        moveq   #-FSTEP,d2
f1b:  add.w   d2,d3
        lsl.w   #4,d3
        or.w    d3,d5
        move.w  d0,d2
        lsr.w   #8,d2
        andi.w  #$f,d2
        move.w  d1,d3
        lsr.w   #8,d3
        andi.w  #$f,d3
        sub.w   d3,d2
        cmpi.w  #FSTEP,d2
        ble     f2a
        moveq   #FSTEP,d2
f2a:  cmpi.w  #-2,d2
        bge     f2b
        moveq   #-FSTEP,d2
f2b:  add.w   d2,d3
        lsl.w   #8,d3
        or.w    d3,d5
        move.w  d5,2(a2)
        addq.l  #4,a2
        dbf     d7,f_l
        move.l  a1,36(a7)
        move.l  a2,40(a7)
        lea     $6ddc(a0),a1
        move.l  a1,56(a7)                 ; retour direct au rts d'origine
        movem.l (a7)+,d0-d7/a0-a5
        rts
site6:  lea     FCNT(pc),a1               ; site 6 : fondu enchaine : on n'attend le balayage qu'une iteration sur deux
        addq.b  #1,(a1)
        move.b  (a1),d0
        andi.b  #FADEMASK,d0
        movem.l (a7)+,d0-d7/a0-a5
        bne     s6_n
        jsr     $964(a6)                  ; instruction d'origine
s6_n:   rts
site5:  moveq   #0,d0                     ; site 5 : attente d'un clic sur l'ecran-titre (image du dragon)
        move.b  $6af4(a6),d0
        cmpi.b  #$28,d0                   ; L
        bne     s5_n
        clr.b   $6af4(a6)
        lea     LREQ(pc),a1
        st      (a1)
        lea     $60a(a0),a1
        move.l  a1,56(a7)                 ; sortie de l'attente comme apres un clic
        movem.l (a7)+,d0-d7/a0-a5
        rts
s5_n:   movem.l (a7)+,d0-d7/a0-a5
        jsr     $964(a6)                  ; instruction d'origine
        rts
site4:  lea     LREQ(pc),a1               ; site 4 : attente d'un clic sur les pages d'intro (a6 = base)
        tst.b   (a1)
        bne     s4_l                      ; L deja demande sur l'ecran-titre
        moveq   #0,d0
        move.b  $6af4(a6),d0
        cmpi.b  #$28,d0                   ; L
        bne     s4_n
        clr.b   $6af4(a6)
        st      (a1)
s4_l:
        lea     ZLONG(pc),a1
        move.l  a1,64(a7)                 ; la boucle d'intro croit etre au bout de la liste de pages
        lea     $754(a0),a1
        move.l  a1,56(a7)                 ; sortie de l'attente comme apres un clic
        movem.l (a7)+,d0-d7/a0-a5
        rts
s4_n:   movem.l (a7)+,d0-d7/a0-a5
        jsr     $964(a6)                  ; instruction d'origine
        rts
site3:  lea     NOWIPE(pc),a1             ; site 3 : effacement des donnees du jeu a l'arret
        tst.b   (a1)
        bne     s3_end
        jsr     $476(a0)                  ; (a5 = base aussi) routine d'origine
s3_end: movem.l (a7)+,d0-d7/a0-a5
        rts

; ---- touches
keys:   moveq   #0,d0
        move.b  $6af4(a6),d0
        beq     k_end
        cmpi.b  #$35,d0                   ; B
        beq     k_undo
        cmpi.b  #$34,d0                   ; V : vie au maximum
        beq     k_v
        cmpi.b  #$37,d0                   ; M : carte
        beq     k_m
        cmpi.b  #$29,d0                   ; M sur un clavier AZERTY (touche a droite du L)
        beq     k_m
        cmpi.b  #$21,d0                   ; S
        beq     k_s
        cmpi.b  #$28,d0                   ; L
        beq     k_l
@@DBGKEYS@@k_end:  rts
@@DBGCODE@@k_v:    clr.b   $6af4(a6)
        move.l  $b7e(a6),d0
        cmpi.l  #REC_FIRST,d0
        blt     kv_ns
        cmpi.l  #REC_END,d0
        blt     k_end                     ; sans effet sur une page systeme
kv_ns:  move.w  #32,$b84(a6)
        clr.w   $b82(a6)
        lea     NOPUSH(pc),a0
        st      (a0)                      ; la scene est reaffichee, pas re-empilee
        st      $6af3(a6)
        rts
k_m:    clr.b   $6af4(a6)
        move.l  $b7e(a6),d0
        cmpi.l  #REC_TMP1,d0
        beq     ret_page                  ; M sur une carte : retour au jeu
        cmpi.l  #REC_TMP2,d0
        beq     ret_page
        bsr     patchmap
        lea     CZ(pc),a0
        move.l  #REC_TMP1,d1
        cmpi.b  #NZ1+1,(a0)
        blt     km_go
        move.l  #REC_TMP2,d1              ; zone du temple : page 2
km_go:  bra     openpg

; ---- colore la case courante des cartes : chiffre de couleur '0' (courant) ou '1' dans les blocs TMP1 / TMP2 en memoire
patchmap: movem.l d0-d4/a0-a3,-(a7)
        moveq   #0,d3
        lea     CZ(pc),a0
        move.b  (a0),d3                   ; zone + 1 (0 = inconnue)
        cmpi.w  #NZ1,d3
        ble     pm_1
        moveq   #NZ1,d3                   ; temple : sur la carte 1, on marque la case Temple
pm_1:
        move.l  #$544d5031,d0                ; 'TMP1'
        jsr     $d94(a6)                  ; a0 = bloc de texte (d0 = 0 si trouve)
        tst.l   d0
        bne     pm_e1
        moveq   #0,d4
        cmpi.b  #14,(a0)                  ; colonne de la 1re ligne : en clair ou code (xor $55) ?
        beq     pm_k1
        moveq   #$55,d4
pm_k1: lea    SLOTS+0(pc),a1
        moveq   #1,d2
pm_l1: moveq  #0,d1
        move.w  (a1)+,d1
        moveq   #$31,d0
        cmp.w   d3,d2
        bne     pm_s1
        moveq   #$30,d0
pm_s1: eor.b  d4,d0
        move.b  d0,0(a0,d1.w)
        addq.w  #1,d2
        cmpi.w  #NZ1+1,d2
        blt     pm_l1
pm_e1:
        moveq   #0,d3
        lea     CZ(pc),a0
        move.b  (a0),d3
        move.l  #$544d5032,d0                ; 'TMP2'
        jsr     $d94(a6)                  ; a0 = bloc de texte (d0 = 0 si trouve)
        tst.l   d0
        bne     pm_e2
        moveq   #0,d4
        cmpi.b  #14,(a0)                  ; colonne de la 1re ligne : en clair ou code (xor $55) ?
        beq     pm_k2
        moveq   #$55,d4
pm_k2: lea    SLOTS+NZ1*2(pc),a1
        moveq   #NZ1+1,d2
pm_l2: moveq  #0,d1
        move.w  (a1)+,d1
        moveq   #$31,d0
        cmp.w   d3,d2
        bne     pm_s2
        moveq   #$30,d0
pm_s2: eor.b  d4,d0
        move.b  d0,0(a0,d1.w)
        addq.w  #1,d2
        cmpi.w  #NZONES+1,d2
        blt     pm_l2
pm_e2:
        movem.l (a7)+,d0-d4/a0-a3
        rts
k_s:    clr.b   $6af4(a6)
        move.l  #REC_TSAV,d1
        bra     openpg
k_l:    clr.b   $6af4(a6)
        move.l  #REC_TLOD,d1
        bra     openpg
k_undo: clr.b   $6af4(a6)
        bra     undo

; ---- ouvrir une page systeme (d1 = enregistrement) ; memorise la scene de depart
openpg: move.l  $b7e(a6),d0
        cmpi.l  #REC_FIRST,d0
        blt     op_ns
        cmpi.l  #REC_END,d0
        blt     op_go                     ; deja sur une page systeme : on garde la scene de depart
op_ns:  lea     RET(pc),a0
        move.l  d0,(a0)
op_go:  move.l  d1,$b7e(a6)
        clr.w   $b82(a6)
        st      $6af3(a6)
        rts
ret_page: lea   NOPUSH(pc),a0
        st      (a0)                      ; la scene retrouvee ne doit pas etre empilee une 2e fois
        lea     RET(pc),a0
        move.l  (a0),$b7e(a6)
        clr.w   $b82(a6)
        st      $6af3(a6)
        rts

; ---- choix des pages (appeles par la routine d'origine : liens negatifs)
r_ret:  bra     ret_page
r_sv1:  moveq   #$31,d0
        bra     do_save
r_sv2:  moveq   #$32,d0
        bra     do_save
r_sv3:  moveq   #$33,d0
        bra     do_save
r_sv4:  moveq   #$34,d0
        bra     do_save
r_ld1:  moveq   #$31,d0
        bra     do_load
r_ld2:  moveq   #$32,d0
        bra     do_load
r_ld3:  moveq   #$33,d0
        bra     do_load
r_ld4:  moveq   #$34,d0
        bra     do_load

; ---- instantane de l'etat : scene, vie, objets, evenements, or, drapeau d'etat
push:   move.l  $b7e(a6),d0
        cmpi.l  #REC_FIRST,d0
        blt     p_ns
        cmpi.l  #REC_END,d0
        blt     p_skip                    ; page systeme : jamais dans l'historique
p_ns:   move.l  d0,d1                     ; zone de la carte : memorisee si la scene en a une
        subi.l  #SCENE0,d1
        blt     p_nz
        cmpi.l  #NSCENES*RECSZ,d1
        bge     p_nz
        divu    #RECSZ,d1
        andi.l  #$ffff,d1
        bne     p_zl
        lea     CZ(pc),a1
        clr.b   (a1)                      ; 1re scene du jeu : zone inconnue (ne depend pas du contenu initial de la memoire)
p_zl:   lea     ZTAB(pc),a1
        move.b  0(a1,d1.w),d1
        beq     p_nz
        lea     CZ(pc),a1
        move.b  d1,(a1)
p_nz:   lea     NOPUSH(pc),a1
        tst.b   (a1)
        beq     p_go
        clr.b   (a1)                      ; retour d'une page systeme : deja empilee
p_skip: rts
p_go:   lea     HCNT(pc),a1
        move.w  (a1),d0
        cmpi.w  #NHIST,d0
        blt     p_ok
        lea     HIST+16(pc),a2
        lea     HIST(pc),a3
        move.w  #(NHIST-1)*4-1,d1
p_sh:   move.l  (a2)+,(a3)+
        dbf     d1,p_sh
        move.w  #NHIST-1,d0
p_ok:   lea     HIST(pc),a3
        move.w  d0,d1
        lsl.w   #4,d1
        adda.w  d1,a3
        move.l  $b7e(a6),(a3)+
        move.w  $b84(a6),(a3)+
        move.w  $6a76(a6),(a3)+
        move.l  $6a78(a6),(a3)+
        move.w  $6a7c(a6),(a3)+
        move.b  $eb0(a6),(a3)+
        lea     CZ(pc),a0
        move.b  (a0),(a3)+
        addq.w  #1,d0
        move.w  d0,(a1)
        rts

; ---- retour arriere : revient a l'ecran precedent
undo:   move.l  $b7e(a6),d0
        cmpi.l  #REC_FIRST,d0
        blt     u_ns
        cmpi.l  #REC_END,d0
        blt     u_end                     ; B sans effet sur une page systeme
u_ns:   lea     HCNT(pc),a1
        move.w  (a1),d0
        cmpi.w  #2,d0
        blt     u_end
        subq.w  #2,d0
        move.w  d0,(a1)
        lea     HIST(pc),a3
        lsl.w   #4,d0
        adda.w  d0,a3
        move.l  (a3)+,$b7e(a6)
        move.w  (a3)+,$b84(a6)
        move.w  (a3)+,$6a76(a6)
        move.l  (a3)+,$6a78(a6)
        move.w  (a3)+,$6a7c(a6)
        move.b  (a3)+,$eb0(a6)
        lea     CZ(pc),a0
        move.b  (a3)+,(a0)
        clr.w   $b82(a6)                  ; neutralise la variation de vie en attente
        st      $6af3(a6)                 ; sort de l'attente : la scene est reaffichee
u_end:  rts

; ---- rend la main au systeme (sans effacer les donnees du jeu) / reprend la machine ; a5 = base
sys_out: lea    NOWIPE(pc),a0
        st      (a0)
        movea.l a5,a6
        jsr     $6e78(a6)                 ; son : arret
        jsr     $700a(a6)
        jsr     $288(a5)                  ; liberation du systeme (interruptions, copper, DMA, Permit)
        lea     NOWIPE(pc),a0
        clr.b   (a0)
        rts
sys_in: jsr     $236(a5)                  ; reprise de la machine (Forbid, interruptions)
        movea.l a5,a6
        jsr     $542(a6)                  ; affichage du jeu (copper, DMA, musique)
        jsr     $7f44(a6)                 ; reactive la liste copper de la scene (image + palette)
        rts

; ---- ouvre le fichier de l'emplacement d7 : d2 = mode ; retourne d4 = poignee, a4 = tache, d5 = ancien pr_WindowPtr
dos_open: movea.l 4.w,a6
        suba.l  a1,a1
        jsr     -294(a6)                  ; FindTask(0)
        movea.l d0,a4
        move.l  184(a4),d5
        moveq   #-1,d0
        move.l  d0,184(a4)                ; pas de requester systeme
        movea.l $50a(a5),a6               ; dos.library (ouverte par le jeu)
        lea     FNAME(pc),a0
        move.l  a0,d1
        jsr     -30(a6)                   ; Open
        move.l  d0,d4
        rts

; ---- S : sauvegarde ; d0 = caractere de l'emplacement
do_save: movem.l d1-d7/a0-a6,-(a7)
        movea.l a6,a5
        lea     FNAME(pc),a0
        move.b  d0,10(a0)                 ; emplacement (avant sys_out qui ecrase les registres)
        lea     BUF(pc),a0
        move.l  #$48535631,(a0)+          ; 'HSV1'
        move.l  #VERS,(a0)+
        lea     RET(pc),a1
        move.l  (a1),(a0)+
        move.w  $b84(a5),(a0)+
        move.w  $6a76(a5),(a0)+
        move.l  $6a78(a5),(a0)+
        move.w  $6a7c(a5),(a0)+
        move.b  $eb0(a5),(a0)+
        lea     CZ(pc),a1
        move.b  (a1),(a0)+
        bsr     sys_out
        move.l  #1006,d2
        bsr     dos_open
        moveq   #-1,d6
        tst.l   d4
        beq     sv_cl
        move.l  d4,d1
        lea     BUF(pc),a0
        move.l  a0,d2
        moveq   #24,d3
        jsr     -48(a6)                   ; Write
        moveq   #0,d6
        cmpi.l  #24,d0
        beq     sv_ok
        moveq   #-1,d6
sv_ok:  move.l  d4,d1
        jsr     -36(a6)                   ; Close
sv_cl:  move.l  d5,184(a4)
        bsr     sys_in
        move.l  #REC_TSOK,d1
        tst.l   d6
        beq     sv_nx
        move.l  #REC_TSER,d1
sv_nx:  move.l  d1,$b7e(a5)
        clr.b   $6af4(a5)                 ; oublie la touche (son relachement a pu etre perdu)
        clr.w   $b82(a5)
        st      $6af3(a5)
        movem.l (a7)+,d1-d7/a0-a6
        rts

; ---- L : chargement
do_load: movem.l d1-d7/a0-a6,-(a7)
        movea.l a6,a5
        lea     FNAME(pc),a0
        move.b  d0,10(a0)
        bsr     sys_out
        move.l  #1005,d2
        bsr     dos_open
        moveq   #-1,d6
        tst.l   d4
        beq     ld_cl
        move.l  d4,d1
        lea     BUF(pc),a0
        move.l  a0,d2
        moveq   #24,d3
        jsr     -42(a6)                   ; Read
        cmpi.l  #24,d0
        bne     ld_ok
        moveq   #0,d6
ld_ok:  move.l  d4,d1
        jsr     -36(a6)                   ; Close
ld_cl:  move.l  d5,184(a4)
        bsr     sys_in
        tst.l   d6
        bne     ld_er
        lea     BUF(pc),a0
        cmpi.l  #$48535631,(a0)+
        bne     ld_er
        cmpi.l  #VERS,(a0)+
        bne     ld_er
        move.l  (a0),d0                   ; scene : doit etre un enregistrement valide
        subi.l  #SCENE0,d0
        blt     ld_er
        cmpi.l  #NSCENES*RECSZ,d0
        bge     ld_er
        move.l  (a0)+,$b7e(a5)
        move.w  (a0)+,$b84(a5)
        move.w  (a0)+,$6a76(a5)
        move.l  (a0)+,$6a78(a5)
        move.w  (a0)+,$6a7c(a5)
        move.b  (a0)+,$eb0(a5)
        lea     CZ(pc),a1
        move.b  (a0)+,(a1)
        lea     NOPUSH(pc),a0
        clr.b   (a0)
        lea     HCNT(pc),a0
        clr.w   (a0)                      ; nouvelle partie : historique vide
        bra     ld_go
ld_er:  move.l  #REC_TLER,$b7e(a5)
ld_go:  clr.w   $b82(a5)
        clr.b   $6af4(a5)
        st      $6af3(a5)
        movem.l (a7)+,d1-d7/a0-a6
        rts

FNAME:  dc.b    'HerosSave-1',0
        even
'''

def assemble(org, syms):
    code, labels = asm68k.asm(source(), org, syms)
    return code, labels

def build_records(template, ext_off, labels, rec_ext_off):
    """enregistrements des pages (58 octets chacun) ; liens = -(offset de la routine par rapport a a6)"""
    out = b''
    for pg in PAGES:
        r = bytearray(template)
        r[0x18:0x1c] = pg.encode('latin-1')
        for i, lab in enumerate(ROUTINES[pg]):
            v = 0 if not lab else (-(ext_off + labels[lab])) & 0xFFFFFFFF
            r[0x24+4*i:0x28+4*i] = struct.pack('>I', v)
        r[0x38:0x3a] = b'\0\0'
        out += bytes(r)
    return out
