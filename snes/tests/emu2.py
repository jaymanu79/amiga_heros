#!/usr/bin/env python3
"""Pilote libretro minimal (snes9x) : python3 emu.py rom.sfc script.json sortie_prefixe
script = {"frames": N, "presses": [[frame, "R", duree], ...], "shots": [frames...], "wav": "x.wav"}"""
import ctypes as C, sys, json, struct, wave, os
from PIL import Image
SO = os.environ.get('SNES9X_CORE', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'snes9x_libretro.so'))
lib = C.CDLL(SO)
rom, scr, outp = sys.argv[1], json.load(open(sys.argv[2])), sys.argv[3]
BTN = dict(B=0, Y=1, SELECT=2, START=3, UP=4, DOWN=5, LEFT=6, RIGHT=7, A=8, X=9, L=10, R=11)
state = dict(fmt=0, frame=None, audio=bytearray(), n=0)
held = set()

ENV = C.CFUNCTYPE(C.c_bool, C.c_uint, C.c_void_p)
VID = C.CFUNCTYPE(None, C.c_void_p, C.c_uint, C.c_uint, C.c_size_t)
AUD = C.CFUNCTYPE(None, C.c_int16, C.c_int16)
AUDB = C.CFUNCTYPE(C.c_size_t, C.c_void_p, C.c_size_t)
POLL = C.CFUNCTYPE(None)
INP = C.CFUNCTYPE(C.c_int16, C.c_uint, C.c_uint, C.c_uint, C.c_uint)

def env(cmd, data):
    if cmd == 10:
        state['fmt'] = C.cast(data, C.POINTER(C.c_int))[0]; return True
    return False
def video(data, w, h, pitch):
    if not data: return
    buf = C.string_at(data, pitch * h)
    state['frame'] = (bytes(buf), w, h, pitch)
def audb(data, frames):
    state['audio'] += C.string_at(data, frames * 4); return frames
def poll(): pass
def inp(port, dev, idx, bid):
    if port == 0 and dev == 1 and bid in held: return 1
    return 0
cbs = (ENV(env), VID(video), AUD(lambda l, r: None), AUDB(audb), POLL(poll), INP(inp))
lib.retro_set_environment(cbs[0]); lib.retro_set_video_refresh(cbs[1]); lib.retro_set_audio_sample(cbs[2])
lib.retro_set_audio_sample_batch(cbs[3]); lib.retro_set_input_poll(cbs[4]); lib.retro_set_input_state(cbs[5])
lib.retro_init()
class Info(C.Structure): _fields_ = [('path', C.c_char_p), ('data', C.c_void_p), ('size', C.c_size_t), ('meta', C.c_char_p)]
data = open(rom, 'rb').read(); buf = C.create_string_buffer(data, len(data))
info = Info(rom.encode(), C.cast(buf, C.c_void_p), len(data), None)
assert lib.retro_load_game(C.byref(info)), 'chargement refuse'
class AV(C.Structure): _fields_ = [('bw', C.c_uint), ('bh', C.c_uint), ('mw', C.c_uint), ('mh', C.c_uint), ('ar', C.c_float), ('fps', C.c_double), ('sr', C.c_double)]
av = AV(); lib.retro_get_system_av_info(C.byref(av)); print('av', av.bw, av.bh, av.fps, av.sr)

def shot(name):
    fr, w, h, pitch = state['frame']
    im = Image.new('RGB', (w, h))
    px = im.load()
    for y in range(h):
        row = fr[y * pitch:(y + 1) * pitch]
        for x in range(w):
            if state['fmt'] == 1:
                b, g, r = row[4*x], row[4*x+1], row[4*x+2]
            else:
                v = row[2*x] | (row[2*x+1] << 8); r = (v >> 11 & 31) << 3; g = (v >> 5 & 63) << 2; b = (v & 31) << 3
            px[x, y] = (r, g, b)
    im.save(name)
lib.retro_get_memory_data.restype = C.c_void_p
lib.retro_get_memory_size.restype = C.c_size_t
def wram(off, n):
    p = lib.retro_get_memory_data(2)
    return C.string_at(p + off, n)
def sram():
    p = lib.retro_get_memory_data(0); sz = lib.retro_get_memory_size(0)
    return C.string_at(p, sz) if p else b''
def vram():
    p = lib.retro_get_memory_data(3); sz = lib.retro_get_memory_size(3)
    return C.string_at(p, sz) if p else b''
marks = {}
dumps = {}
for f in range(scr['frames']):
    held.clear()
    for fr0, b, dur in scr.get('presses', []):
        if fr0 <= f < fr0 + dur: held.add(BTN[b])
    for pf, off, hx in scr.get('pokes', []):
        if pf == f:
            p = lib.retro_get_memory_data(0); C.memmove(p + off, bytes.fromhex(hx), len(hx) // 2)
    lib.retro_run()
    if f in scr.get('shots', []) and state['frame']: shot('%s_%04d.png' % (outp, f))
    marks[f] = len(state['audio'])
    if f in scr.get('dump', []):
        dumps[f] = wram(0, 0x100).hex()
        open(outp + '_vram_%d.bin' % f, 'wb').write(vram())
        open(outp + '_wram_%d.bin' % f, 'wb').write(wram(0, 0x2000))
        open(outp + '_sram_%d.bin' % f, 'wb').write(sram())
a = bytes(state['audio'])
with wave.open(scr.get('wav', outp + '.wav'), 'wb') as w:
    w.setnchannels(2); w.setsampwidth(2); w.setframerate(int(av.sr)); w.writeframes(a)
json.dump(dumps, open(outp + '_dump.json', 'w'))
json.dump({str(k): v for k, v in marks.items() if k % 10 == 0}, open(outp + '_marks.json', 'w'))
print('frames', scr['frames'], 'audio octets', len(a), 'fmt', state['fmt'])
