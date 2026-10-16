import struct, sys
sys.path.insert(0,'.')
from m68k import CPU
exe=open('/mnt/user-data/uploads/HerosExe','rb').read()
payload=exe[0x8c:0x8c+135988]
mem=bytearray(0x400000)
P=0x1000; DEST=0x200000
mem[P:P+len(payload)]=payload
RET=0x3FFFF0; SENT=0x3FFFE0
c=CPU(mem)
c.a[7]=0x3F0000; c.push(RET)
c.d[6]=2; c.a[4]=SENT; c.pc=P
def stub(cpu):          # sous-programme du stub : a1 = debut du bloc (hunk) d6+1 -> ici le bloc image
    assert cpu.d[6]&0xFFFF==0, cpu.d[6]
    cpu.a[1]=DEST; cpu.pc=cpu.pop()
c.hooks[SENT]=stub
c.run(RET)
img=bytes(mem[DEST:DEST+0xf376*4])
open('image.bin','wb').write(img)
print(len(img), img[:32].hex(' '))
