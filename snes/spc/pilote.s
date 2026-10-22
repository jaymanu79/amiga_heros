; ---------------------------------------------------------------
; pilote.s : lecteur de modules ProTracker (3 voies) pour SPC700
; Lit les patterns compactes produites par musique.py.
; Port 0 (CPU->SPC) : 1..32 = jouer la piste n, $FF = stop
; Retour : $F4 = ack, $F5 = position dans la liste, $F6 = ligne
; ---------------------------------------------------------------
.memorymap
  defaultslot 0
  slotsize $0600
  slot 0 start $0200
.endme
.rombankmap
  bankstotal 1
  banksize $0600
  banks 1
.endro
.include "consts.inc"

.define PLAYING $10
.define LASTCMD $11
.define TICKC   $12
.define ROW     $13
.define ORDPOS  $14
.define KON     $15
.define MASK    $16
.define FLG     $17
.define VB      $18
.define FULLV   $1A
.define QV      $1B
.define MV      $1C
.define VL      $1D
.define VR      $1E
.define ORDP    $20
.define ORDP1   $21
.define PP      $22
.define PP1     $23
.define TMP     $24
.define TMP1    $25
.define TMP2    $26
.define TMP21   $27
.define C113    $28
.define C113H   $29
.define CMAX    $2A
.define CMAXH   $2B
.define PTABW   $2C
.define PTABWH  $2D
.define PERL    $30
.define PERH    $31
.define VOL     $38
.define INST    $40
.define EFF     $48
.define PAR     $50
.define PTAB1   PTAB+1
.define PATTAB1 PATTAB+1
.define ORDTAB1 ORDTAB+1

.bank 0 slot 0
.org 0

reset:
    mov x,#$ef
    mov sp,x
    mov a,#0
    mov x,#0
clr:
    mov (x)+,a
    cmp x,#$ef
    bne clr
    mov C113,#113
    mov CMAX,#<856
    mov CMAXH,#>856
    mov PTABW,#<PTAB
    mov PTABWH,#>PTAB
    mov y,#$6c      ; FLG : pas d'ecriture echo, pas de mute
    mov a,#$20
    call !wr
    mov y,#$0c
    mov a,#$78
    call !wr         ; MVOLL
    mov y,#$1c
    call !wr         ; MVOLR
    mov a,#0
    mov y,#$2c
    call !wr
    mov y,#$3c
    call !wr
    mov y,#$0d
    call !wr
    mov y,#$2d
    call !wr
    mov y,#$3d
    call !wr
    mov y,#$4d
    call !wr
    mov y,#$5c
    call !wr
    mov y,#$4c
    call !wr
    mov y,#$7d
    call !wr         ; EDL = 0
    mov y,#$6d
    mov a,#$ff
    call !wr         ; ESA
    mov y,#$5d
    mov a,#>DIR
    call !wr         ; DIR
    mov x,#0
vinit:
    mov a,x
    asl a
    asl a
    asl a           ; x*8 = voix*16
    clrc
    adc a,#5
    mov y,a         ; ADSR1
    mov a,#0
    call !wr
    inc y
    inc y           ; GAIN
    mov a,#$7f
    call !wr
    inc x
    inc x
    cmp x,#6
    bne vinit
    mov $fa,#160    ; timer 0 : 8000/160 = 50 Hz
    mov $f1,#$31    ; vide les ports d'entree + timer 0 on
    mov $f5,#$5a    ; "pret"
mainloop:
    mov a,$f4
    cmp a,LASTCMD
    beq nocmd
    mov LASTCMD,a
    call !startsong
nocmd:
    mov a,$fd
    beq mainloop
    mov a,PLAYING
    beq mainloop
    call !tick
    bra mainloop

wr:
    mov $f2,y
    mov $f3,a
    ret

startsong:
    cmp a,#0
    bne ss1
    ret
ss1:
    cmp a,#$ff
    beq stopsong
    dec a
    asl a
    mov y,a
    mov a,!ORDTAB+y
    mov ORDP,a
    mov a,!ORDTAB1+y
    mov ORDP1,a
    mov ROW,#64
    mov ORDPOS,#$ff
    mov TICKC,#0
    mov KON,#0
    mov x,#0
sclr:
    mov a,#0
    mov VOL+x,a
    mov EFF+x,a
    mov a,#1
    mov INST+x,a
    inc x
    inc x
    cmp x,#6
    bne sclr
    mov PLAYING,#1
    mov a,LASTCMD
    mov $f4,a
    ret
stopsong:
    mov PLAYING,#0
    mov x,#0
    mov a,#0
stclr:
    mov VOL+x,a
    inc x
    inc x
    cmp x,#6
    bne stclr
    call !updatedsp
    mov a,LASTCMD
    mov $f4,a
    ret

tick:
    mov a,TICKC
    bne dofx
    call !newrow
    bra updt
dofx:
    call !applyfx
updt:
    call !updatedsp
    inc TICKC
    mov a,TICKC
    cmp a,#6
    bne tk1
    mov TICKC,#0
tk1:
    mov a,ORDPOS
    mov $f5,a
    mov a,ROW
    mov $f6,a
    ret

nextpat:
    mov ROW,#0
    inc ORDPOS
    mov y,ORDPOS
    mov a,[ORDP]+y
    cmp a,#$ff
    bne gotpat
    inc y
    mov a,[ORDP]+y
    mov ORDPOS,a
    mov y,a
    mov a,[ORDP]+y
gotpat:
    asl a
    mov y,a
    mov a,!PATTAB+y
    mov PP,a
    mov a,!PATTAB1+y
    mov PP1,a
    ret

newrow:
    mov a,ROW
    cmp a,#64
    bne nr0
    call !nextpat
nr0:
    mov y,#0
    mov a,[PP]+y
    incw PP
    mov MASK,a
    mov x,#0
chloop:
    lsr MASK
    bcc nocell
    mov a,[PP]+y
    incw PP
    mov FLG,a
    and a,#$0f
    beq noinst
    mov INST+x,a
    dec a
    mov y,a
    mov a,!INSVOL+y
    mov VOL+x,a
    mov y,#0
noinst:
    mov a,FLG
    and a,#$40
    beq noper
    mov a,[PP]+y
    incw PP
    mov PERL+x,a
    mov a,[PP]+y
    incw PP
    mov PERH+x,a
    mov a,!BITS+x
    or a,KON
    mov KON,a
noper:
    mov a,FLG
    and a,#$30
    xcn a
    mov EFF+x,a
    beq nxtch
    mov a,[PP]+y
    incw PP
    mov PAR+x,a
    mov a,EFF+x
    cmp a,#3
    bne nxtch
    mov a,PAR+x
    mov VOL+x,a
    mov a,#0
    mov EFF+x,a
    bra nxtch
nocell:
    mov a,#0
    mov EFF+x,a
nxtch:
    inc x
    inc x
    cmp x,#6
    bne chloop
    inc ROW
    ret

applyfx:
    mov x,#0
fxl:
    mov a,EFF+x
    beq fxn
    mov a,PAR+x
    mov TMP,a
    mov TMP1,#0
    mov a,EFF+x
    cmp a,#1
    bne fxdown
    mov a,PERL+x
    mov y,PERH+x
    subw ya,TMP
    bcc fxmin
    cmpw ya,C113
    bcs fxset
fxmin:
    movw ya,C113
    bra fxset
fxdown:
    mov a,PERL+x
    mov y,PERH+x
    addw ya,TMP
    cmpw ya,CMAX
    bcc fxset
    movw ya,CMAX
fxset:
    mov PERL+x,a
    mov PERH+x,y
fxn:
    inc x
    inc x
    cmp x,#6
    bne fxl
    ret

updatedsp:
    mov x,#0
udl:
    call !updch
    inc x
    inc x
    cmp x,#6
    bne udl
    mov a,KON
    beq udend
    mov y,#$4c
    call !wr
    mov KON,#0
udend:
    ret

updch:
    mov a,x
    asl a
    asl a
    asl a
    mov VB,a
    mov a,!BITS+x
    and a,KON
    beq nosrc
    mov a,VB
    clrc
    adc a,#4
    mov y,a
    mov a,INST+x
    dec a
    call !wr
nosrc:
    mov a,PERL+x
    mov y,PERH+x
    subw ya,C113
    movw TMP,ya
    addw ya,TMP
    addw ya,PTABW
    movw TMP,ya
    mov y,#0
    mov a,[TMP]+y
    mov TMP2,a
    inc y
    mov a,[TMP]+y
    mov TMP21,a
    mov a,VB
    clrc
    adc a,#2
    mov y,a
    mov a,TMP2
    call !wr
    inc y
    mov a,TMP21
    call !wr
    mov a,VOL+x
    mov FULLV,a
    lsr a
    lsr a
    mov QV,a
    mov a,FULLV
    setc
    sbc a,QV
    mov MV,a
    cmp x,#2
    beq pan1
    bcs pan2
    mov a,FULLV
    mov VL,a
    mov a,QV
    mov VR,a
    bra panw
pan1:
    mov a,QV
    mov VL,a
    mov a,FULLV
    mov VR,a
    bra panw
pan2:
    mov a,MV
    mov VL,a
    mov VR,a
panw:
    mov y,VB
    mov a,VL
    call !wr
    inc y
    mov a,VR
    call !wr
    ret

BITS: .db 1,0,2,0,4,0
