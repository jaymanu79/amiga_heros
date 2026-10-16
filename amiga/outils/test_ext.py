import sys,struct; sys.path.insert(0,'.')
from m68k import CPU
img=open('image_patched.bin','rb').read()
BASE=0x10000; EXEC=0x20000; TASK=0x30000; MSG=0x31000; ARGL=0x31100; NAME=0x31200; ARG=0x80000
def run(mode, args="", wbname=None, numargs=2, fail=False):
    mem=bytearray(0x100000); mem[BASE:BASE+len(img)]=img
    struct.pack_into('>I',mem,4,EXEC)
    s=args.encode(); mem[ARG:ARG+len(s)]=s
    struct.pack_into('>I',mem,TASK+172,1 if mode=='cli' else 0)
    if wbname is not None:
        mem[NAME:NAME+len(wbname)+1]=wbname.encode('latin-1')+b'\0'
    struct.pack_into('>I',mem,MSG+28,numargs)
    struct.pack_into('>I',mem,MSG+36,ARGL)
    struct.pack_into(">IIII",mem,ARGL,0x1234,0x2222,0,NAME if wbname is not None else 0)
    c=CPU(mem); c.a[7]=0xF0000; c.push(0xDEAD0); c.push(BASE+4)
    if mode=='cli': c.d[0]=len(s); c.a[0]=ARG
    else: c.d[0]=0; c.a[0]=0
    calls=[]
    def mk(nm,ret):
        def h(cpu):
            calls.append(nm); cpu.d[0]=ret(cpu) if callable(ret) else ret; cpu.pc=cpu.pop()
        return h
    c.hooks[EXEC-294]=mk('FindTask',TASK)
    c.hooks[EXEC-384]=mk('WaitPort',MSG)
    c.hooks[EXEC-372]=mk('GetMsg',MSG)
    DOS=0x40000; INT=0x50000; cd=[]
    def openlib(cpu):
        n=bytes(mem[cpu.a[1]:cpu.a[1]+20]).split(b'\0')[0].decode(); calls.append('Open:'+n)
        cpu.d[0]=DOS if n=='dos.library' else INT if n=='intuition.library' else 0; cpu.pc=cpu.pop()
    c.hooks[EXEC-552]=openlib
    def curdir(cpu): cd.append(cpu.d[1]); cpu.d[0]=0; cpu.pc=cpu.pop()
    c.hooks[DOS-126]=curdir
    c.hooks[INT-96]=mk('Beep',0)
    def alert(cpu):
        a=cpu.a[0]; txt=[]
        while True:
            x=cpu.rw(a); y=mem[a+2]; a+=3; z=a
            while mem[a]: a+=1
            txt.append((x,y,bytes(mem[z:a]).decode())); cont=mem[a+1]; a+=2
            if not cont: break
        calls.append(('Alert',cpu.d[0],cpu.d[1],txt)); cpu.d[0]=0; cpu.pc=cpu.pop()
    c.hooks[INT-90]=alert
    c.hooks[EXEC-216]=mk('AvailMem',150*1024+777)
    res={}
    def h(cpu):
        p=cpu.rl(BASE+0x51e); res['name']=bytes(mem[p:p+30]).split(b'\0')[0].decode()
        cpu.d[0]=-1 if fail else 0; cpu.d[0]&=0xFFFFFFFF; cpu.N=int(fail); cpu.pc=cpu.pop()
    c.hooks[BASE+0x8c]=h
    c.pc=BASE+0x700; c.run(BASE+4)
    res['calls']=calls; res['cd']=cd; res['d0']=c.d[0]; res['N']=c.N; res['sp_ok']=c.a[7]==0xF0000-4
    return res
for a in ["en\n","FR ","","  de\n","\n","abcdefghijklmnop\n"]: print('CLI',repr(a),run('cli',a))
print('WB outil seul',run('wb',wbname=None,numargs=1))
print('WB projet en',run('wb',wbname='en'))
print('WB heros - francais',run('wb',wbname='h\xe9ros - fran\xe7ais'))
print('WB heros - english',run('wb',wbname='h\xe9ros - english'))
print('WB echec init',run('wb',wbname='en',fail=True))
print('WB projet Francais.x',run('wb',wbname='de'))
print('WB arg nul',run('wb',wbname=None,numargs=2))
