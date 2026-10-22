; ===========================================================================
; HEROS - version SNES complete (Olivier Thil, 1994)
; ===========================================================================
.INCLUDE "out/layout.inc"
.LOROM
.SNESHEADER
    ID      "HRS2"
    NAME    "HEROS SNES          "
    LOROM
    SLOWROM
    CARTRIDGETYPE $02
    ROMSIZE       $0B
    SRAMSIZE      $03
    COUNTRY       $02
    LICENSEECODE  $00
    VERSION       $00
.ENDSNES

.MEMORYMAP
    SLOTSIZE    $8000
    DEFAULTSLOT 0
    SLOT 0      $8000
.ENDME
.ROMBANKSIZE $8000
.ROMBANKS    ROMBANKS

.SNESNATIVEVECTOR
    COP    Dummy
    BRK    Dummy
    ABORT  Dummy
    NMI    Dummy
    IRQ    Dummy
.ENDNATIVEVECTOR
.SNESEMUVECTOR
    COP    Dummy
    ABORT  Dummy
    NMI    Dummy
    RESET  Reset
    IRQBRK Dummy
.ENDEMUVECTOR

.DEFINE SPCLEN 47694

; ---- variables (page directe) : bloc d'etat = $20..$2B
.DEFINE SC      $20
.DEFINE GW      $22
.DEFINE GL      $24
.DEFINE VIE     $28
.DEFINE GOLD    $2A
.DEFINE HIDX    $2C
.DEFINE HCNT    $2D
.DEFINE LANG    $2E
.DEFINE MODE    $2F
.DEFINE JCUR    $30
.DEFINE JOLD    $32
.DEFINE JNEW    $34
.DEFINE SCROLL  $36
.DEFINE SMAX    $38
.DEFINE CURCMD  $3A
.DEFINE CURDEC  $3B
.DEFINE MAPMODE $3C
.DEFINE SCRON   $3D
.DEFINE NTILES  $3E
.DEFINE NROWS   $40
.DEFINE QUIT    $41
.DEFINE PTR     $44
.DEFINE PTR2    $48
.DEFINE T0      $50
.DEFINE T1      $52
.DEFINE T2      $54
.DEFINE T3      $56
.DEFINE T4      $58
.DEFINE T5      $5A
.DEFINE T6      $5C
.DEFINE T7      $5E
.DEFINE CHY     $60
.DEFINE CHX     $6A
.DEFINE MSEL    $74
.DEFINE MCTX    $75
.DEFINE MSG     $76
.DEFINE IPAGE   $77
.DEFINE CEND    $78
.DEFINE CNT     $7A
.DEFINE REPT    $7C
.DEFINE LASTCMD $7D
.DEFINE HIST    $0400
.DEFINE OAMBUF  $0A00
.DEFINE LINEBUF $0D40

.MACRO A8
    SEP #$20
    .ACCU 8
.ENDM
.MACRO A16
    REP #$20
    .ACCU 16
.ENDM

; DMA vers VRAM depuis une etiquette (adresse fixe), longueur fixe
.MACRO VramDma ARGS dst src len bnk
    A16
    LDA #dst
    STA $2116
    LDA #src
    STA $4302
    LDA #len
    STA $4305
    A8
    LDA #bnk
    STA $4304
    LDA #$01
    STA $4300
    LDA #$18
    STA $4301
    LDA #$01
    STA $420B
.ENDM

.BANK 0 SLOT 0
.ORG 0

Dummy:
    RTI

; ===========================================================================
Reset:
    SEI
    CLC
    XCE
    REP #$38
    .ACCU 16
    .INDEX 16
    LDX #$1FFF
    TXS
    LDA #$0000
    TCD
    A8
    LDA #$8F
    STA $2100
    PHK
    PLB
    STZ $4200
    STZ $420B
    STZ $420C
    ; efface la WRAM basse (variables, historique, OAM)
    A16
    LDX #$0000
    LDA #$0000
@clr:
    STA $0000,X
    INX
    INX
    CPX #$1F00
    BNE @clr
    A8
    JSR UploadSpc
    LDA #$01
    STA $4200
    JSR InitPpu
    JSR InitStatic
    LDA #$FF
    STA CURCMD
    STA CURDEC
    STA LASTCMD
    JSR LoadLangSram
    JMP TitleStart

; ---------------------------------------------------------------------------
InitPpu:
    .ACCU 8
    LDA #$03
    STA $2101            ; sprites 8x8 / 16x16, base $6000
    LDA #$09
    STA $2105            ; mode 1, BG3 prioritaire
    STZ $2106
    LDA #$68
    STA $2107            ; BG1 map $6800
    LDA #$6C
    STA $2108            ; BG2 map $6C00
    LDA #$72
    STA $2109            ; BG3 map $7000, 32x64
    STZ $210B            ; BG1/BG2 chars $0000
    LDA #$04
    STA $210C            ; BG3 chars $4000
    LDX #$0000
@sc:
    STZ $210D,X
    STZ $210D,X
    INX
    CPX #$0008
    BNE @sc
    STZ $2111
    STZ $2111
    STZ $2112
    STZ $2112
    LDA #$17
    STA $212C
    LDA #$01
    STA $212D
    LDA #$04
    STA $212E            ; fenetre : masque BG3
    LDA #$02
    STA $2124            ; BG3 : fenetre 1 active
    LDA #$02
    STA $2130
    LDA #$42
    STA $2131            ; demi-addition du sous-ecran sur BG2 (panneau translucide)
    ; HDMA canal 1 : fenetre 1 (masque BG3 au-dessus de y=64)
    LDA #$01
    STA $4310
    LDA #$26
    STA $4311
    A16
    LDA #HdmaWin
    STA $4312
    A8
    STZ $4314
    LDA #$02
    STA $420C
    RTS

HdmaWin:
    .db 64, 0, 255
    .db 127, 255, 0
    .db 33, 255, 0
    .db 0

; ---------------------------------------------------------------------------
; tuiles du panneau (BG2), sprites, police 8x8, carte BG2, palettes de sprites
InitStatic:
    .ACCU 8
    ; tuiles 1000 (pleine, couleur 1), 1001 (bord haut : ligne 0 couleur 2), 1002 (vide)
    A16
    LDA #$3E80
    STA $2116
    A8
    LDA #$80
    STA $2115
    LDX #0
@pt:
    LDA.W PanelTiles,X
    STA $2118
    LDA.W PanelTiles+1,X
    STA $2119
    INX
    INX
    CPX #96
    BNE @pt
    ; sprites -> $6000
    A16
    LDA #$6000
    STA $2116
    LDA #SPR_A
    STA $4302
    LDA #3584
    STA $4305
    A8
    LDA #SPR_B
    STA $4304
    LDA #$01
    STA $4300
    LDA #$18
    STA $4301
    LDA #$01
    STA $420B
    ; palettes de sprites -> CGRAM 128 (64 octets)
    LDA #128
    STA $2121
    A16
    LDA #(SPR_A+3584)
    STA $4302
    LDA #64
    STA $4305
    A8
    LDA #SPR_B
    STA $4304
    STZ $4300
    LDA #$22
    STA $4301
    LDA #$01
    STA $420B
    ; carte BG2 : lignes 0-7 vides (tuile 1002), ligne 8 bord, lignes 9-27 pleines
    A16
    LDA #$6C00
    STA $2116
    LDX #0
@m2:
    TXA
    LSR
    LSR
    LSR
    LSR
    LSR
    LSR                  ; ligne = X / 64 (2 octets par case, 32 cases)
    CMP #8
    BCC @mv
    BNE @mf
    LDA #$37E9
    BRA @mw
@mf:
    LDA #$37E8
    BRA @mw
@mv:
    LDA #$17EA
@mw:
    STA $2118
    INX
    INX
    CPX #2048
    BNE @m2
    A8
    RTS

PanelTiles:
    ; tuile pleine couleur 1 : plan0 = $FF, autres 0
    .REPT 8
    .db $FF, $00
    .ENDR
    .REPT 8
    .db $00, $00
    .ENDR
    ; bord : ligne 0 = couleur 2 (plan1), lignes 1-7 couleur 1
    .db $00, $FF
    .REPT 7
    .db $FF, $00
    .ENDR
    .REPT 8
    .db $00, $00
    .ENDR
    ; vide
    .REPT 16
    .db $00, $00
    .ENDR

; ---------------------------------------------------------------------------
; envoi du pilote + donnees dans le SPC700 (protocole IPL)
UploadSpc:
    .ACCU 8
    A16
@w1:
    LDA $2140
    CMP #$BBAA
    BNE @w1
    LDA #$0200
    STA $2142
    A8
    LDA #$01
    STA $2141
    LDA #$CC
    STA $2140
@w2:
    LDA $2140
    CMP #$CC
    BNE @w2
    A16
    LDA #$8000
    STA PTR
    A8
    LDA #:SpcA
    STA PTR+2
    STZ CNT
    LDX #SPCLEN
@up:
    LDA [PTR]
    STA $2141
    LDA CNT
    STA $2140
@echo:
    CMP $2140
    BNE @echo
    INC CNT
    A16
    INC PTR
    A8
    BNE @nw
    LDA #$80
    STA PTR+1
    INC PTR+2
@nw:
    DEX
    BNE @up
    A16
    LDA #$0200
    STA $2142
    A8
    STZ $2141
    LDA CNT
    INC A
    STA $2140
@w3:
    LDA $2141
    CMP #$5A
    BNE @w3
    RTS

; ---------------------------------------------------------------------------
WaitVB:
    .ACCU 8
@w:
    LDA $4210
    BPL @w
    RTS

; commande musicale A (0 = rien)
SetMusic:
    .ACCU 8
    CMP CURCMD
    BEQ @x
    STA CURCMD
    STA $2140
@x:
    RTS

; ---------------------------------------------------------------------------
FadeOut:
    .ACCU 8
    LDA SCRON
    BEQ @d
    LDA #14
@l:
    PHA
    JSR WaitVB
    PLA
    STA $2100
    DEC A
    BPL @l
@d:
    STZ SCRON
    LDA #$80
    STA $2100
    RTS

FadeIn:
    .ACCU 8
    LDA #1
@l:
    PHA
    JSR WaitVB
    PLA
    STA $2100
    INC A
    CMP #16
    BNE @l
    LDA #1
    STA SCRON
    RTS

; ---------------------------------------------------------------------------
; lecture manette : JCUR, JNEW (fronts montants)
ReadJoy:
    .ACCU 8
@w:
    LDA $4212
    AND #$01
    BNE @w
    A16
    LDA $4218
    STA JCUR
    LDA JOLD
    EOR #$FFFF
    AND JCUR
    STA JNEW
    LDA JCUR
    STA JOLD
    A8
    RTS

; une image : attente VBlank, OAM, defilement, manette
Frame:
    .ACCU 8
    JSR WaitVB
    STZ $2102
    STZ $2103
    A16
    LDA #OAMBUF
    STA $4302
    LDA #544
    STA $4305
    A8
    STZ $4304
    STZ $4300
    LDA #$04
    STA $4301
    LDA #$01
    STA $420B
    JSR SetVofs
    JSR ReadJoy
    RTS

; registre de defilement vertical BG3 selon le mode
SetVofs:
    .ACCU 8
    LDA MODE
    BEQ @v0
    CMP #3
    BEQ @v0
    A16
    LDA SCROLL
    SEC
    SBC #65
    AND #$01FF
    BRA @vs
@v0:
    A16
    LDA #0
@vs:
    A8
    STA $2112
    XBA
    STA $2112
    RTS

; ---------------------------------------------------------------------------
; Carte BG1 du jeu (texture miroir) et reglages d'ecran de jeu
LoadGameMap:
    .ACCU 8
    VramDma $6800 T_BG1MAP 2048 0
    LDA #1
    STA MAPMODE
    LDA #$FF
    STA CURDEC
    LDA #$17
    STA $212C
    RTS

; A = numero de decor
LoadDecor:
    .ACCU 8
    A16
    AND #$00FF
    ASL
    ASL
    TAX
    LDA T_DECOR,X
    STA $4302
    STA PTR2
    LDA T_DECOR+2,X
    STA PTR2+2
    LDA #$0000
    STA $2116
    LDA #8192
    STA $4305
    A8
    LDA PTR2+2
    STA $4304
    LDA #$80
    STA $2115
    LDA #$01
    STA $4300
    LDA #$18
    STA $4301
    LDA #$01
    STA $420B
    ; palette 32 octets -> CGRAM 64
    A16
    LDA PTR2
    CLC
    ADC #8192
    STA $4302
    LDA #32
    STA $4305
    A8
    LDA #64
    STA $2121
    STZ $4300
    LDA #$22
    STA $4301
    LDA #$01
    STA $420B
    RTS

; ---------------------------------------------------------------------------
; efface la carte BG3 (4096 octets)
ClearBG3:
    .ACCU 8
    LDA #$80
    STA $2115
    A16
    LDA #$7000
    STA $2116
    LDA #ZeroByte
    STA $4302
    LDA #4096
    STA $4305
    A8
    STZ $4304
    LDA #$09
    STA $4300
    LDA #$18
    STA $4301
    LDA #$01
    STA $420B
    RTS
ZeroByte:
    .db 0

; ---------------------------------------------------------------------------
; Affiche la scene SC (ou la page d'intro) : fondu, decor, palettes, texte, musique
ShowScene:
    .ACCU 8
    JSR FadeOut
    LDA MAPMODE
    CMP #1
    BEQ @mapok
    JSR LoadGameMap
@mapok:
    ; --- decor
    A16
    LDA SC
    ASL
    ASL
    ASL
    ASL
    TAX
    A8
    LDA T_SCENE+1,X
    CMP CURDEC
    BEQ @decok
    STA CURDEC
    PHX
    JSR LoadDecor
    PLX
@decok:
    LDA T_SCENE+2,X
    STA T7                  ; commande musicale de la scene
    ; --- palettes de la scene
    A16
    LDA SC
    ASL
    ASL
    ASL
    TAX
    A8
    STZ $2121
    STZ $2122
    STZ $2122
    LDA T_PAL,X
    STA $2122
    LDA T_PAL+1,X
    STA $2122
    LDA T_PAL+2,X
    STA $2122
    LDA T_PAL+3,X
    STA $2122
    LDA T_PAL,X
    STA $2122
    LDA T_PAL+1,X
    STA $2122
    LDA #81
    STA $2121
    LDA T_PAL+4,X
    STA $2122
    LDA T_PAL+5,X
    STA $2122
    LDA T_PAL+6,X
    STA $2122
    LDA T_PAL+7,X
    STA $2122
    JSR LoadText
    A16
    STZ SCROLL
    A8
    LDA T7
    JSR SetMusic
    JSR BuildOAM
    JSR SetVofs
    JSR FadeIn
    RTS

; ---------------------------------------------------------------------------
; Charge le bloc de texte de la scene : tuiles BG3 + carte
LoadText:
    .ACCU 8
    A16
    LDA SC
    ASL
    ASL
    TAX
    A8
    LDA LANG
    BNE @en
    A16
    LDA T_TXTFR,X
    STA PTR
    LDA T_TXTFR+2,X
    STA PTR+2
    BRA @got
@en:
    A16
    LDA T_TXTEN,X
    STA PTR
    LDA T_TXTEN+2,X
    STA PTR+2
@got:
    LDA [PTR]
    STA NTILES
    LDY #2
    LDA [PTR],Y
    STA SMAX
    LDY #4
    LDA [PTR],Y
    AND #$00FF
    STA NROWS
    ; en-tetes des choix : 5 x (y, x)
    LDX #0
    LDY #6
@ch:
    LDA [PTR],Y
    STA CHY,X
    INY
    INY
    LDA [PTR],Y
    STA CHX,X
    INY
    INY
    INX
    INX
    CPX #10
    BNE @ch
    A8
    JSR ClearBG3
    ; tuile 0 vide + tuiles du bloc -> $4000
    A16
    LDA #$4000
    STA $2116
    A8
    LDA #$80
    STA $2115
    LDX #8
@z:
    STZ $2118
    STZ $2119
    DEX
    BNE @z
    A16
    LDA NTILES
    BEQ @nomap
    STA CNT
    LDY #26
    A8
    LDA #$01
    STA $4300
    LDA #$18
    STA $4301
    A16
@g:
    LDA [PTR],Y
    STA T1
    AND #$07FF
    ASL
    ASL
    ASL
    ASL
    ORA #$8000
    STA $4302
    LDA T1
    XBA
    AND #$00FF
    LSR
    LSR
    LSR
    CLC
    ADC #POOL0
    A8
    STA $4304
    A16
    LDA #16
    STA $4305
    A8
    LDA #$01
    STA $420B
    A16
    INY
    INY
    DEC CNT
    BNE @g
@nomap:
    ; carte : Y = 26 + 2*NTILES
    A16
    LDA NTILES
    ASL
    CLC
    ADC #26
    TAY
    LDA NROWS
    ASL
    ASL
    ASL
    ASL
    ASL
    STA T2                  ; nombre total de cases
    LDA #$7000
    STA $2116
    STZ T3                  ; case courante
@m:
    LDA T3
    CMP T2
    BCS @md
    LDA [PTR],Y
    INY
    INY
    CMP #$8000
    BCS @run
    STA $2118
    INC T3
    BRA @m
@run:
    AND #$7FFF
    CLC
    ADC T3
    STA T3
    CLC
    ADC #$7000
    STA $2116
    BRA @m
@md:
    A8
    RTS

; ---------------------------------------------------------------------------
; Tampon OAM : objets (0-15), disques de choix (16-20), HUD (21-26)
BuildOAM:
    .ACCU 8
    LDX #0
    LDA #$F0
@h:
    STA OAMBUF+1,X
    INX
    INX
    INX
    INX
    CPX #512
    BNE @h
    ; table haute : 0-20 grands, le reste petit
    LDX #0
    LDA #$AA
@t:
    STA OAMBUF+512,X
    INX
    CPX #5
    BNE @t
    LDA #$02
    STA OAMBUF+517
    STZ OAMBUF+518
    LDA MODE
    CMP #2
    BEQ @game
    CMP #1
    BNE @out
    JMP DrawArrows
@out:
    RTS
@game:
    ; ---- objets
    A16
    LDA GW
    STA T0
    A8
    LDX #0
    STZ T1
    STZ T2
@o:
    A16
    LSR T0
    A8
    BCC @on
    LDA T1
    STA OAMBUF,X
    STZ OAMBUF+1,X
    LDA T2
    AND #$07
    ASL
    STA T3
    LDA T2
    AND #$08
    BEQ @lo
    LDA T3
    CLC
    ADC #32
    STA T3
@lo:
    LDA T3
    STA OAMBUF+2,X
    LDA #$30
    STA OAMBUF+3,X
@on:
    INX
    INX
    INX
    INX
    LDA T1
    CLC
    ADC #16
    STA T1
    INC T2
    LDA T2
    CMP #16
    BNE @o
    ; ---- disques de choix
    A16
    LDA SC
    ASL
    ASL
    ASL
    ASL
    STA T3
    LDX #0
@d:
    TXA
    CLC
    ADC T3
    TAY
    LDA T_SCENE+4,Y
    CMP #$FFFF
    BEQ @dn
    LDA CHY,X
    CMP #$FFFF
    BEQ @dn
    CLC
    ADC #61
    SEC
    SBC SCROLL
    BMI @dn
    CMP #62
    BCC @dn
    CMP #218
    BCS @dn
    STA T4
    TXA
    ASL
    CLC
    ADC #64
    TAY
    A8
    LDA CHX,X
    CLC
    ADC #9
    STA OAMBUF,Y
    LDA T4
    STA OAMBUF+1,Y
    TXA
    CLC
    ADC #64
    STA OAMBUF+2,Y
    LDA #$32
    STA OAMBUF+3,Y
    A16
@dn:
    INX
    INX
    CPX #10
    BNE @d
    A8
    ; ---- HUD : coeur + vie, piece + or
    LDA #2
    STA OAMBUF+84
    LDA #19
    STA OAMBUF+85
    LDA #106
    STA OAMBUF+86
    LDA #$32
    STA OAMBUF+87
    A16
    LDA VIE
    A8
    LDX #88
    JSR PutNum2
    LDA #34
    STA OAMBUF+96
    LDA #19
    STA OAMBUF+97
    LDA #107
    STA OAMBUF+98
    LDA #$32
    STA OAMBUF+99
    A16
    LDA GOLD
    BPL @gp
    LDA #0
@gp:
    A8
    LDX #100
    JSR PutNum2
    JMP DrawArrows

; fleches de defilement (sprites 27 et 28)
DrawArrows:
    .ACCU 8
    A16
    LDA SCROLL
    CMP SMAX
    A8
    BCS @nd
    LDA #244
    STA OAMBUF+108
    LDA #212
    STA OAMBUF+109
    LDA #108
    STA OAMBUF+110
    LDA #$32
    STA OAMBUF+111
@nd:
    A16
    LDA SCROLL
    A8
    BEQ @nu
    A16
    LDA SCROLL
    A8
    BEQ @nu
    LDA #244
    STA OAMBUF+112
    LDA #66
    STA OAMBUF+113
    LDA #109
    STA OAMBUF+114
    LDA #$32
    STA OAMBUF+115
@nu:
    RTS

; A16 = valeur (0..) ; X = offset OAM : deux chiffres (clamp 99)
PutNum2:
    .ACCU 8
    A16
    CMP #100
    BCC @ok
    LDA #99
@ok:
    A8
    LDY #0
@t:
    CMP #10
    BCC @u
    SBC #10
    INY
    BRA @t
@u:
    STA T4
    ; dizaines (Y)
    TYA
    CLC
    ADC #96
    STA OAMBUF+2,X
    LDA #$32
    STA OAMBUF+3,X
    A16
    TXA
    CLC
    ADC #4
    TAY
    A8
    LDA T4
    CLC
    ADC #96
    STA OAMBUF+2,Y
    LDA #$32
    STA OAMBUF+3,Y
    ; positions : X de base selon X
    LDA OAMBUF-4+0,X        ; (x du sprite precedent : coeur ou piece)
    CLC
    ADC #11
    STA OAMBUF,X
    CLC
    ADC #7
    STA OAMBUF,Y
    LDA #19
    STA OAMBUF+1,X
    STA OAMBUF+1,Y
    RTS

BitTab:
    .dw $0001,$0002,$0004,$0008,$0010,$0020,$0040,$0080
    .dw $0100,$0200,$0400,$0800,$1000,$2000,$4000,$8000

; ===========================================================================
; MOTEUR : arrivee dans une scene, choix, routines
; ===========================================================================
; A16 = scene d'arrivee
Arrive:
    .ACCU 16
    STA SC
    ASL
    ASL
    ASL
    ASL
    TAX
    LDA T_SCENE,X
    AND #$00FF
    CMP #$0080
    BCC @p
    ORA #$FF00
@p:
    CLC
    ADC VIE
    STA VIE
    SEC
    SBC #33
    BMI @le
    LDA #32
    STA VIE
@le:
    LDA VIE
    BPL @ok
    STZ VIE
    STZ GW
    STZ GOLD
    STZ SC
@ok:
    RTS

; A8 = numero de choix 0..4 ; sortie : carry = 1 si choix invalide ; QUIT = 1 si fin
DoChoice:
    .ACCU 8
    STZ QUIT
    A16
    AND #$00FF
    ASL
    STA T0
    LDA SC
    ASL
    ASL
    ASL
    ASL
    CLC
    ADC T0
    TAX
    LDA T_SCENE+4,X
    CMP #$FFFF
    BNE @v
    A8
    SEC
    RTS
@v:
    .ACCU 16
    CMP #$8000
    BCS @rt
    JSR Arrive
    A8
    CLC
    RTS
@rt:
    .ACCU 16
    AND #$7FFF
    ASL
    TAX
    LDA T_ROUT,X
    STA PTR
    STZ PTR+2
    LDY #0
@br:
    A8
    LDA [PTR],Y
    CMP #$FF
    BNE @b1
    CLC
    RTS                     ; aucune branche : rien ne change
@b1:
    INY
    A16
    AND #$00FF
    STA T1
    TYA
    CLC
    ADC T1
    STA CEND
@cl:
    CPY CEND
    BEQ @cok
    A8
    LDA [PTR],Y
    INY
    CMP #4
    BCS @mk
    STA T3
    LDA [PTR],Y
    INY
    STA T4
    JSR TestBit
    EOR T3
    AND #$01
    BNE @cl
    BRA @fail
@mk:
    STA T3
    A16
    LDA [PTR],Y
    INY
    INY
    STA T5
    LDA [PTR],Y
    INY
    INY
    STA T6
    LDA GW
    AND T5
    CMP T6
    A8
    BEQ @eq
    LDA T3
    CMP #5
    BEQ @cl
    BRA @fail
@eq:
    LDA T3
    CMP #4
    BEQ @cl
@fail:
    A16
    LDY CEND
    A8
    LDA [PTR],Y
    INY
    A16
    AND #$00FF
    STA T1
    TYA
    CLC
    ADC T1
    CLC
    ADC #2
    TAY
    JMP @br
@cok:
    A8
    LDA [PTR],Y
    INY
    A16
    AND #$00FF
    STA T1
    TYA
    CLC
    ADC T1
    STA T2                  ; fin des effets
@el:
    CPY T2
    BNE @elgo
    JMP @edone
@elgo:
    A8
    LDA [PTR],Y
    INY
    STA T3
    CMP #6
    BCC @eb
    BEQ @e6
    CMP #8
    BCC @e7
    BEQ @e8
    CMP #9
    BEQ @e9
    ; type 10 : L := dword
    A16
    LDA [PTR],Y
    STA GL
    INY
    INY
    LDA [PTR],Y
    STA GL+2
    INY
    INY
    JMP @el
@e6:
    .ACCU 8
    LDA [PTR],Y
    INY
    A16
    AND #$00FF
    STA GOLD
    JMP @el
@e7:
    .ACCU 8
    LDA [PTR],Y
    INY
    A16
    AND #$00FF
    STA T4
    LDA GOLD
    SEC
    SBC T4
    STA GOLD
    JMP @el
@e8:
    .ACCU 8
    LDA [PTR],Y
    INY
    A16
    AND #$00FF
    STA VIE
    JMP @el
@e9:
    A16
    LDA [PTR],Y
    STA GW
    INY
    INY
    JMP @el
@eb:
    .ACCU 8
    LDA [PTR],Y
    INY
    STA T4
    A16
    AND #$000F
    ASL
    TAX
    LDA.W BitTab,X
    STA T5
    A8
    LDX #GW
    LDA T3
    CMP #3
    BCC @w2
    SBC #3
    STA T3
    LDX #GL
    LDA T4
    AND #$10
    BEQ @w2
    LDX #(GL+2)
@w2:
    A16
    LDA T3
    AND #$00FF
    BEQ @set
    CMP #1
    BEQ @clr
    LDA $00,X
    EOR T5
    STA $00,X
    JMP @el
@set:
    LDA $00,X
    ORA T5
    STA $00,X
    JMP @el
@clr:
    LDA T5
    EOR #$FFFF
    AND $00,X
    STA $00,X
    JMP @el
@edone:
    A16
    LDA [PTR],Y
    CMP #$FFFF
    BEQ @stay
    CMP #$FFFE
    BNE @go
    A8
    LDA #1
    STA QUIT
    CLC
    RTS
@go:
    JSR Arrive
@stay:
    A8
    CLC
    RTS

; T3 = type (bit0 ignore ; bit1 : 0 = W, 1 = L) ; T4 = numero de bit ; sortie A8 = 0/1
TestBit:
    .ACCU 8
    A16
    LDA T4
    AND #$000F
    ASL
    TAX
    LDA.W BitTab,X
    STA T5
    A8
    LDA T3
    AND #$02
    BNE @l
    A16
    LDA GW
    BRA @t
@l:
    .ACCU 8
    LDA T4
    AND #$10
    BNE @hi
    A16
    LDA GL
    BRA @t
@hi:
    A16
    LDA GL+2
@t:
    AND T5
    A8
    BEQ @z
    LDA #1
    RTS
@z:
    LDA #0
    RTS

; ---------------------------------------------------------------------------
; historique (anneau de 128 etats de 12 octets)
HistOff:
    .ACCU 16
    LDA HIDX
    AND #$007F
    STA T0
    ASL
    ASL
    STA T1
    LDA T0
    ASL
    ASL
    ASL
    CLC
    ADC T1
    TAX
    RTS

StoreState:
    .ACCU 8
    A16
    JSR HistOff
    LDY #0
@l:
    LDA $20,Y
    STA HIST,X
    INX
    INX
    INY
    INY
    CPY #12
    BNE @l
    A8
    RTS

LoadState:
    .ACCU 8
    A16
    JSR HistOff
    LDY #0
@l:
    LDA HIST,X
    STA $20,Y
    INX
    INX
    INY
    INY
    CPY #12
    BNE @l
    A8
    RTS

PushHist:
    .ACCU 8
    LDA HIDX
    INC A
    AND #$7F
    STA HIDX
    LDA HCNT
    CMP #128
    BCS @f
    INC HCNT
@f:
    JMP StoreState

; carry = 1 si impossible
PopHist:
    .ACCU 8
    LDA HCNT
    CMP #2
    BCS @ok
    SEC
    RTS
@ok:
    DEC HCNT
    LDA HIDX
    DEC A
    AND #$7F
    STA HIDX
    JSR LoadState
    CLC
    RTS

NewGame:
    .ACCU 8
    A16
    LDA #TC1
    STA SC
    STZ GW
    STZ GL
    STZ GL+2
    STZ VIE
    STZ GOLD
    A8
    STZ HIDX
    LDA #1
    STA HCNT
    JSR StoreState
    RTS

; ===========================================================================
; SRAM : 4 emplacements de $800 octets
;   +0 "HRS1"  +4 nb d'etats  +6 somme de controle  +8 etats (12 octets chacun, du plus ancien au plus recent)
; langue : $7F8 = $A5, $7F9 = langue
; ===========================================================================
LoadLangSram:
    .ACCU 8
    LDA.L $7007F8
    CMP #$A5
    BNE @x
    LDA.L $7007F9
    AND #$01
    STA LANG
@x:
    RTS

SaveLangSram:
    .ACCU 8
    LDA #$A5
    STA.L $7007F8
    LDA LANG
    STA.L $7007F9
    RTS

; A8 = emplacement 0..3 ; sortie : carry = 1 si invalide ; T0 = base, T1 = nb d'etats
SlotCheck:
    .ACCU 8
    A16
    AND #$0003
    ASL
    ASL
    ASL
    XBA
    STA T0
    TAX
    A8
    LDA.L $700000,X
    CMP #'H'
    BNE @bad
    LDA.L $700001,X
    CMP #'R'
    BNE @bad
    LDA.L $700002,X
    CMP #'S'
    BNE @bad
    LDA.L $700003,X
    CMP #'1'
    BNE @bad
    LDA.L $700004,X
    BEQ @bad
    CMP #129
    BCS @bad
    STA T1
    STZ T1+1
    ; somme
    A16
    LDA T1
    STA T3
    TXA
    CLC
    ADC #8
    TAX
    ; octets a sommer = T1 * 12
    LDA T1
    ASL
    ASL
    STA T2
    LDA T1
    ASL
    ASL
    ASL
    CLC
    ADC T2
    STA T2
@s:
    A8
    LDA.L $700000,X
    A16
    AND #$00FF
    CLC
    ADC T3
    STA T3
    INX
    DEC T2
    BNE @s
    LDX T0
    LDA.L $700006,X
    CMP T3
    A8
    BNE @bad
    CLC
    RTS
@bad:
    A8
    SEC
    RTS

; A8 = emplacement 0..3
SaveSlot:
    .ACCU 8
    A16
    AND #$0003
    ASL
    ASL
    ASL
    XBA
    STA T0
    TAX
    A8
    LDA #'H'
    STA.L $700000,X
    LDA #'R'
    STA.L $700001,X
    LDA #'S'
    STA.L $700002,X
    LDA #'1'
    STA.L $700003,X
    LDA HCNT
    STA.L $700004,X
    STZ T1+1
    LDA HCNT
    STA T1
    A16
    LDA T1
    STA T3                      ; somme initiale
    TXA
    CLC
    ADC #8
    TAX
    A8
    LDA HIDX
    SEC
    SBC HCNT
    INC A
    AND #$7F
    STA T5
    LDA HCNT
    STA T4
@e:
    A16
    LDA T5
    AND #$007F
    STA T6
    ASL
    ASL
    STA T7
    LDA T6
    ASL
    ASL
    ASL
    CLC
    ADC T7
    TAY
    LDA #12
    STA T2
@b:
    A8
    LDA HIST,Y
    STA.L $700000,X
    A16
    AND #$00FF
    CLC
    ADC T3
    STA T3
    INX
    INY
    DEC T2
    BNE @b
    A8
    LDA T5
    INC A
    AND #$7F
    STA T5
    DEC T4
    BNE @e
    A16
    LDX T0
    LDA T3
    STA.L $700006,X
    A8
    RTS

; A8 = emplacement ; sortie : carry = 1 si echec ; charge l'historique et l'etat
LoadSlot:
    .ACCU 8
    PHA
    JSR SlotCheck
    BCC @ok
    PLA
    SEC
    RTS
@ok:
    PLA
    A16
    LDA T0
    CLC
    ADC #8
    TAX
    LDA T1
    ASL
    ASL
    STA T2
    LDA T1
    ASL
    ASL
    ASL
    CLC
    ADC T2
    STA T2
    LDY #0
@c:
    A8
    LDA.L $700000,X
    STA HIST,Y
    INX
    INY
    A16
    DEC T2
    BNE @c
    A8
    LDA T1
    STA HCNT
    DEC A
    STA HIDX
    JSR LoadState
    CLC
    RTS

; ===========================================================================
; TEXTE 8x8 (menus, titre)
; ===========================================================================
; A8 = numero de chaine -> T4 = pointeur
GetStr:
    .ACCU 8
    A16
    AND #$00FF
    ASL
    TAX
    A8
    LDA LANG
    BNE @en
    A16
    LDA T_STRFR,X
    STA T4
    A8
    RTS
@en:
    A16
    LDA T_STREN,X
    STA T4
    A8
    RTS

; T4 = chaine, T5 = adresse VRAM, T6 = decalage de glyphe (0 ou 128)
PutStr:
    .ACCU 8
    A16
    LDA T5
    STA $2116
    A8
    LDA #$80
    STA $2115
    LDY #0
@l:
    LDA (T4),Y
    CMP #$FF
    BEQ @d
    CLC
    ADC T6
    STA $2118
    LDA #$20
    STA $2119
    INY
    BRA @l
@d:
    RTS

LoadFont:
    .ACCU 8
    A16
    LDA #$4000
    STA $2116
    LDA #FNT_A
    STA $4302
    LDA #4096
    STA $4305
    A8
    LDA #FNT_B
    STA $4304
    LDA #$80
    STA $2115
    LDA #$01
    STA $4300
    LDA #$18
    STA $4301
    LDA #$01
    STA $420B
    RTS

; ===========================================================================
; TITRE
; ===========================================================================
TitleStart:
    .ACCU 8
    JSR FadeOut
    STZ MODE
    ; tuiles du dragon -> $0000
    A16
    LDA #$0000
    STA $2116
    LDA #TITLE_A
    STA $4302
    LDA #24608
    STA $4305
    A8
    LDA #TITLE_B
    STA $4304
    LDA #$80
    STA $2115
    LDA #$01
    STA $4300
    LDA #$18
    STA $4301
    LDA #$01
    STA $420B
    ; carte -> $6800
    A16
    LDA #$6800
    STA $2116
    LDA #(TITLE_A+24608)
    STA $4302
    LDA #2048
    STA $4305
    A8
    LDA #$01
    STA $420B
    ; palette -> CGRAM 64
    LDA #64
    STA $2121
    A16
    LDA #(TITLE_A+24608+2048)
    STA $4302
    LDA #32
    STA $4305
    A8
    STZ $4300
    LDA #$22
    STA $4301
    LDA #$01
    STA $420B
    LDA #2
    STA MAPMODE
    LDA #$FF
    STA CURDEC
    LDA #$15
    STA $212C
    JSR ClearBG3
    JSR LoadFont
    ; couleurs du texte : blanc / or
    STZ $2121
    STZ $2122
    STZ $2122
    LDA #$FF
    STA $2122
    LDA #$7F
    STA $2122
    LDA #$3F
    STA $2122
    LDA #$03
    STA $2122
    LDA #$FF
    STA $2122
    LDA #$7F
    STA $2122
    JSR DrawTitleText
    LDA #2
    JSR SetMusic
    JSR BuildOAM
    JSR SetVofs
    JSR FadeIn
@l:
    JSR Frame
    A16
    LDA JNEW
    AND #$1000
    BEQ @ns
    A8
    JMP IntroStart
@ns:
    .ACCU 16
    LDA JNEW
    AND #$0030
    BEQ @nl
    A8
    LDA #1
    STA MCTX
    LDA #5
    STA MSEL
    JMP OpenMenu
@nl:
    .ACCU 16
    LDA JNEW
    AND #$2000
    BEQ @nsel
    A8
    LDA LANG
    EOR #1
    STA LANG
    JSR SaveLangSram
    JSR DrawTitleText
    BRA @l
@nsel:
    A8
    BRA @l

DrawTitleText:
    .ACCU 8
    ; efface les lignes 24-27 puis ecrit
    A16
    LDA #(24*32 + $7000)
    STA $2116
    A8
    LDA #$80
    STA $2115
    LDX #128
@c:
    STZ $2118
    STZ $2119
    DEX
    BNE @c
    LDA #14
    JSR GetStr
    A16
    LDA #(24*32 + 4 + $7000)
    STA T5
    STZ T6
    A8
    JSR PutStr
    LDA #0
    JSR GetStr
    A16
    LDA #(25*32 + 4 + $7000)
    STA T5
    LDA #128
    STA T6
    A8
    JSR PutStr
    LDA #1
    JSR GetStr
    A16
    LDA #(26*32 + 4 + $7000)
    STA T5
    STZ T6
    A8
    JSR PutStr
    RTS

; ===========================================================================
; PAGES D'INTRODUCTION (TIN1..TIN4) puis nouvelle partie
; ===========================================================================
IntroStart:
    .ACCU 8
    LDA #1
    STA MODE
    STZ IPAGE
@p:
    A16
    LDA IPAGE
    AND #$00FF
    CLC
    ADC #NS
    STA SC
    A8
    JSR ShowScene
@w:
    JSR Frame
    A16
    LDA JNEW
    AND #$1000
    BNE @skip
    LDA JNEW
    AND #$C0F0
    BEQ @ss
    A8
    INC IPAGE
    LDA IPAGE
    CMP #4
    BEQ @skip8
    BRA @p
@skip8:
    .ACCU 8
    BRA @go
@ss:
    .ACCU 16
    ; defilement (pages longues)
    JSR ScrollInput
    A8
    JSR BuildOAM
    BRA @w
@skip:
    A8
@go:
    JSR NewGame
    LDA #2
    STA MODE
    JSR ShowScene
    JMP GameLoop

; defilement par la croix (A16 en entree/sortie)
ScrollInput:
    .ACCU 16
    LDA JCUR
    AND #$0800
    BEQ @nu
    LDA SCROLL
    SEC
    SBC #3
    BPL @su
    LDA #0
@su:
    STA SCROLL
@nu:
    LDA JCUR
    AND #$0400
    BEQ @nd
    LDA SCROLL
    CLC
    ADC #3
    CMP SMAX
    BCC @sd
    BEQ @sd
    LDA SMAX
@sd:
    STA SCROLL
@nd:
    LDA JNEW
    AND #$0200
    BEQ @nl
    LDA SCROLL
    SEC
    SBC #120
    BPL @sl
    LDA #0
@sl:
    STA SCROLL
@nl:
    LDA JNEW
    AND #$0100
    BEQ @nr
    LDA SCROLL
    CLC
    ADC #120
    CMP SMAX
    BCC @sr
    BEQ @sr
    LDA SMAX
@sr:
    STA SCROLL
@nr:
    RTS

; ===========================================================================
; BOUCLE DE JEU
; ===========================================================================
BtnMask:
    .dw $0080, $8000, $0040, $4000, $0030

GameLoop:
    .ACCU 8
    JSR Frame
    A16
    LDA JNEW
    AND #$1000
    BEQ @nm
    A8
    STZ MCTX
    STZ MSEL
    JMP OpenMenu
@nm:
    .ACCU 16
    LDA JNEW
    AND #$2000
    BEQ @nu
    A8
    JSR PopHist
    BCS @gl
    JSR ShowScene
@gl:
    JMP GameLoop
@nu:
    .ACCU 16
    LDX #0
@k:
    LDA JNEW
    AND.W BtnMask,X
    BNE @hit
    INX
    INX
    CPX #10
    BNE @k
    JSR ScrollInput
    A8
    JSR BuildOAM
    JMP GameLoop
@hit:
    .ACCU 16
    TXA
    LSR
    A8
    JSR DoChoice
    BCS @gl
    LDA QUIT
    BEQ @nq
    JMP TitleStart
@nq:
    JSR PushHist
    JSR ShowScene
    JMP GameLoop

; ===========================================================================
; MENU (START) : reprendre / sauver 1-4 / charger 1-4 / vie max / langue / titre
; ===========================================================================
.DEFINE SLOTOK  $0D00
.DEFINE SLOTSC  $0D04
.DEFINE SLOTVIE $0D0C

ScanSlots:
    .ACCU 8
    STZ CNT
@l:
    LDA CNT
    JSR SlotCheck
    BCS @bad
    A16
    LDA T1
    DEC A
    STA T2
    ASL
    ASL
    STA T3
    LDA T2
    ASL
    ASL
    ASL
    CLC
    ADC T3
    CLC
    ADC T0
    TAX
    LDA CNT
    AND #$00FF
    TAY
    A8
    LDA #1
    STA SLOTOK,Y
    A16
    TYA
    ASL
    TAY
    LDA.L $700008,X
    STA SLOTSC,Y
    LDA.L $700010,X
    STA SLOTVIE,Y
    A8
    BRA @n
@bad:
    A16
    LDA CNT
    AND #$00FF
    TAY
    A8
    LDA #0
    STA SLOTOK,Y
@n:
    A8
    INC CNT
    LDA CNT
    CMP #4
    BNE @l
    RTS

; construit la ligne de l'element A8=i dans LINEBUF (codes de glyphes)
BuildLine:
    .ACCU 8
    STA T7
    LDX #0
    LDA #0
@z:
    STA LINEBUF,X
    INX
    CPX #28
    BNE @z
    LDA T7
    BEQ @s0
    CMP #5
    BCC @s1
    CMP #9
    BCC @s2
    BEQ @s3
    CMP #10
    BEQ @s4
    LDA #8
    BRA @sg
@s0:
    LDA #3
    BRA @sg
@s1:
    LDA #4
    BRA @sg
@s2:
    LDA #5
    BRA @sg
@s3:
    LDA #6
    BRA @sg
@s4:
    LDA #7
@sg:
    JSR GetStr
    LDY #0
@c:
    LDA (T4),Y
    CMP #$FF
    BEQ @cd
    STA LINEBUF,Y
    INY
    BRA @c
@cd:
    LDA T7
    BNE @c1
    RTS
@c1:
    CMP #9
    BCC @c2
    RTS
@c2:
    ; numero d'emplacement : (i-1)&3
    SEC
    SBC #1
    AND #$03
    STA T3
    INC A
    CLC
    ADC #16
    STA LINEBUF+8
    ; infos
    A16
    LDA T3
    AND #$00FF
    TAX
    A8
    LDA SLOTOK,X
    BNE @full
    LDA #9
    JSR GetStr
    LDY #0
@e:
    LDA (T4),Y
    CMP #$FF
    BNE @ecp
    RTS
@ecp:
    STA LINEBUF+11,Y
    INY
    BRA @e
@full:
    A16
    TXA
    ASL
    TAY
    LDA SLOTSC,Y
    ASL
    ASL
    TAX                      ; nom de scene : T_SCNAME + sc*4
    LDY #0
@nm:
    A8
    LDA T_SCNAME,X
    STA LINEBUF+11,Y
    INX
    INY
    CPY #4
    BNE @nm
    LDA #0
    STA LINEBUF+15
    LDA #('V'-32)
    STA LINEBUF+16
    A16
    LDA T3
    AND #$00FF
    ASL
    TAX
    LDA SLOTVIE,X
    A8
    LDY #0
@t:
    CMP #10
    BCC @u
    SBC #10
    INY
    BRA @t
@u:
    STA T4
    TYA
    CLC
    ADC #16
    STA LINEBUF+17
    LDA T4
    CLC
    ADC #16
    STA LINEBUF+18
@end:
    RTS

; A8 = i ; T6 = decalage glyphe (0/128) ; ecrit la ligne dans la carte BG3
DrawItem:
    .ACCU 8
    PHA
    JSR BuildLine
    PLA
    A16
    AND #$00FF
    CLC
    ADC #11
    ASL
    ASL
    ASL
    ASL
    ASL
    CLC
    ADC #($7000 + 3)
    STA $2116
    A8
    LDA #$80
    STA $2115
    LDA T6
    BEQ @nc
    LDA #(30+128)
    BRA @cw
@nc:
    LDA #0
@cw:
    STA $2118
    LDA #$20
    STA $2119
    LDX #0
@w:
    LDA LINEBUF,X
    CLC
    ADC T6
    STA $2118
    LDA #$20
    STA $2119
    INX
    CPX #28
    BNE @w
    RTS

DrawMenuAll:
    .ACCU 8
    LDA #2
    JSR GetStr
    A16
    LDA #(9*32 + 14 + $7000)
    STA T5
    LDA #128
    STA T6
    A8
    JSR PutStr
    LDX #0
@i:
    PHX
    STZ T6
    TXA
    CMP MSEL
    BNE @nsel
    LDA #128
    STA T6
    TXA
@nsel:
    TXA
    JSR DrawItem
    PLX
    INX
    CPX #12
    BNE @i
    RTS

; A8 = numero de message : ecrit a la ligne 25
ShowMsg:
    .ACCU 8
    PHA
    A16
    LDA #(25*32 + $7000)
    STA $2116
    A8
    LDA #$80
    STA $2115
    LDX #32
@c:
    STZ $2118
    STZ $2119
    DEX
    BNE @c
    PLA
    JSR GetStr
    A16
    LDA #(25*32 + 4 + $7000)
    STA T5
    STZ T6
    A8
    JSR PutStr
    RTS

OpenMenu:
    .ACCU 8
    JSR ScanSlots
    JSR FadeOut
    LDA #3
    STA MODE
    LDA MCTX
    BEQ @g
    LDA #$04
    STA $212C
@g:
    JSR BuildOAM
    JSR LoadFont
    JSR ClearBG3
    JSR DrawMenuAll
    A16
    STZ SCROLL
    A8
    JSR SetVofs
    JSR FadeIn
MenuLoop:
    .ACCU 8
    JSR Frame
    A16
    LDA JNEW
    AND #$0800
    BEQ @nu
    A8
    LDA MSEL
    PHA
    BNE @dec
    LDA #11
    BRA @st
@dec:
    DEC A
@st:
    STA MSEL
    BRA @redraw
@nu:
    .ACCU 16
    LDA JNEW
    AND #$0400
    BEQ @nd
    A8
    LDA MSEL
    PHA
    INC A
    CMP #12
    BCC @st
    LDA #0
    BRA @st
@nd:
    .ACCU 16
    LDA JNEW
    AND #$1000
    BNE @close
    LDA JNEW
    AND #$8000
    BNE @close
    LDA JNEW
    AND #$0080
    BEQ @loop
    A8
    JMP MenuAction
@close:
    A8
    STZ MSEL
    JMP MenuAction
@loop:
    A8
    BRA MenuLoop
@redraw:
    .ACCU 8
    PLA
    STZ T6
    JSR DrawItem
    LDA #128
    STA T6
    LDA MSEL
    JSR DrawItem
    BRA MenuLoop

MenuAction:
    .ACCU 8
    LDA #$80
    STA $2100
    LDA MSEL
    BNE @n0
    ; reprendre
    LDA MCTX
    BEQ @res
    JMP TitleStart
@res:
    LDA #2
    STA MODE
    JSR ShowScene
    JMP GameLoop
@n0:
    CMP #5
    BCS @n1
    ; sauver
    LDA MCTX
    BNE @ml
    LDA MSEL
    DEC A
    JSR SaveSlot
    JSR ScanSlots
    LDA #128
    STA T6
    LDA MSEL
    JSR DrawItem
    LDA #10
    JSR ShowMsg
@ml:
    JMP MenuBack
@n1:
    CMP #9
    BCS @n2
    ; charger
    SEC
    SBC #5
    JSR LoadSlot
    BCC @lok
    LDA #12
    JSR ShowMsg
    JMP MenuBack
@lok:
    LDA #2
    STA MODE
    JSR ShowScene
    JMP GameLoop
@n2:
    BNE @n3
    ; vie max
    LDA MCTX
    BNE @ml
    A16
    LDA #32
    STA VIE
    A8
    JSR StoreState
    LDA #13
    JSR ShowMsg
    JMP MenuBack
@n3:
    CMP #10
    BNE @n4
    LDA LANG
    EOR #1
    STA LANG
    JSR SaveLangSram
    JSR ClearBG3
    JSR DrawMenuAll
    JMP MenuBack
@n4:
    JMP TitleStart


MenuBack:
    .ACCU 8
    LDA #$0F
    STA $2100
    JMP MenuLoop

.ORG $4000
.INCBIN "out/tab0.bin"
.INCLUDE "out/banks.inc"

.BANK 1 SLOT 0
.ORG 0
SpcA:     .incbin "../spc/spc_a.bin"

.BANK 2 SLOT 0
.ORG 0
SpcB:     .incbin "../spc/spc_b.bin"


