import struct
def ecrire_exe(chemin, image, chip=True):
    assert len(image) % 4 == 0
    n = len(image) // 4
    sz = n | (0x40000000 if chip else 0)
    b = struct.pack('>IIIIII', 0x3F3, 0, 1, 0, 0, sz)
    b += struct.pack('>II', 0x3E9, n) + image + struct.pack('>I', 0x3F2)
    open(chemin, 'wb').write(b)
    return len(b)
if __name__ == '__main__':
    img = open('image.bin', 'rb').read()
    print(ecrire_exe('HerosExe-dep', img), 'octets')
