"""Encodeur BRR avec mise en forme du bruit (noise feedback) : le bruit de quantification
suit le spectre du signal au lieu d'etre blanc (moins de souffle dans les aigus vides)."""
import numpy as np

def clamp16(x): return -32768 if x < -32768 else 32767 if x > 32767 else x
def wrap15(x):
    x = clamp16(x); return (((x * 2 + 32768) & 0xFFFF) - 32768) >> 1
def predict(f, p1, p2):
    if f == 0: return 0
    if f == 1: return p1 - (p1 >> 4)
    if f == 2: return (p1 << 1) - ((p1 + (p1 << 1)) >> 5) - p2 + (p2 >> 4)
    return (p1 << 1) - ((p1 + (p1 << 2) + (p1 << 3)) >> 6) - p2 + ((p2 + (p2 << 1)) >> 4)
def predf(f, p1, p2):             # version flottante pour la boucle de bruit
    if f == 0: return 0.0
    if f == 1: return p1 * 15 / 16
    if f == 2: return p1 * 1.90625 - p2 * 0.9375
    return p1 * 1.796875 - p2 * 0.8125

def enc_block(t, p1, p2, e1, e2, f, r, gam):
    nib = []; werr = 0.0; step = (1 << r) / 2.0
    for x in t:
        pr = predict(f, p1, p2)
        tgt = x - pr - gam * predf(f, e1, e2)
        n0 = int(round(tgt / step))
        best = None
        for n in (n0 - 1, n0, n0 + 1):
            if n < -8 or n > 7: continue
            v = wrap15(((n << r) >> 1) + pr)
            w = (v - pr) - tgt                       # erreur du quantificateur : Q(t) - t
            ee = w * w
            if best is None or ee < best[0]: best = (ee, n, v)
        if best is None:
            n = max(-8, min(7, n0)); v = wrap15(((n << r) >> 1) + pr)
            w = (v - pr) - tgt; best = (w * w, n, v)
        werr += best[0]; nib.append(best[1] & 15)
        e2, e1 = e1, x - best[2]; p2, p1 = p1, best[2]
    return werr, nib, p1, p2, e1, e2

def brr(pcm8, loop_start_blk, loop, gam=0.0):
    t = [v * 128 for v in pcm8]
    out = bytearray(); p1 = p2 = e1 = e2 = 0; nb = len(t) // 16
    for b in range(nb):
        blk = t[16*b:16*b+16]
        first = (b == 0 or b == loop_start_blk)
        if first: p1 = p2 = e1 = e2 = 0
        best = None
        for f in ((0,) if first else (0, 1, 2, 3)):
            for r in range(0, 13):
                res = enc_block(blk, p1, p2, e1, e2, f, r, gam)
                if best is None or res[0] < best[0]: best = (res[0], f, r) + res[1:]
        _, f, r, nib, p1, p2, e1, e2 = best
        out.append((r << 4) | (f << 2) | (2 if loop else 0) | (1 if b == nb - 1 else 0))
        for i in range(0, 16, 2): out.append((nib[i] << 4) | nib[i+1])
    return bytes(out)

def decode(b):
    out = []; p1 = p2 = 0
    for i in range(0, len(b), 9):
        h = b[i]; r = h >> 4; f = (h >> 2) & 3
        for k in range(16):
            n = (b[i+1+k//2] >> (4 if k % 2 == 0 else 0)) & 15
            if n >= 8: n -= 16
            s = wrap15(((n << r) >> 1) + predict(f, p1, p2)); out.append(s); p2, p1 = p1, s
    return np.array(out, float)

def nsr(x, y, nb=16):
    """bruit/signal moyen par bande (spectre pondere : penalise le bruit dans les bandes pauvres)."""
    n = 1024; ratios = []; hop = 512
    e = x - y
    for i in range(0, len(x) - n, hop):
        X = np.abs(np.fft.rfft(x[i:i+n] * np.hanning(n))) ** 2; E = np.abs(np.fft.rfft(e[i:i+n] * np.hanning(n))) ** 2
        Xb = np.array([v.sum() for v in np.array_split(X[1:], nb)]); Eb = np.array([v.sum() for v in np.array_split(E[1:], nb)])
        ratios.append(Eb / (Xb + 1e-3 * Xb.max() + 1))
    r = np.mean(ratios, axis=0)
    return float(np.mean(np.log10(r + 1e-12)) * 10), float(np.max(10 * np.log10(r + 1e-12)))
