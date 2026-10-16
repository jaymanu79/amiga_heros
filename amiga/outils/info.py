import struct,sys
def parse(path):
    d=open(path,'rb').read()
    u16=lambda o:struct.unpack('>H',d[o:o+2])[0]; u32=lambda o:struct.unpack('>I',d[o:o+4])[0]
    r=dict(magic=hex(u16(0)),ver=u16(2),gleft=struct.unpack('>h',d[4:6])[0],gtop=struct.unpack('>h',d[6:8])[0],w=u16(8),h=u16(10),flags=u16(12),act=u16(14),gtype=u16(16),
      render=u32(18),select=u32(22),type=d[0x30],deftool=u32(0x32),tt=u32(0x36),x=struct.unpack('>i',d[0x3a:0x3e])[0],y=struct.unpack('>i',d[0x3e:0x42])[0],drawer=u32(0x42),twin=u32(0x46),stack=u32(0x4a))
    o=0x4e
    if r['drawer']:
        r['drawerdata']=d[o:o+56].hex(); o+=56
    imgs=[]
    for key in ('render','select'):
        if r[key]:
            w,h,dep=u16(o+4),u16(o+6),u16(o+8)
            # Image: left,top,w,h,depth,data,pickpn,pickoff,next => 20 octets
            sz=2*((w+15)//16)*h*dep
            imgs.append((key,o,w,h,dep,sz)); o+=20+sz
    r['imgs']=imgs; r['after']=o
    def strs(o):
        n=u32(o); o+=4; out=[]
        return o,n
    if r['deftool']:
        n=u32(o); r['deftool_s']=d[o+4:o+4+n].rstrip(b'\0'); o+=4+n
    tts=[]
    if r['tt']:
        n=u32(o); cnt=n//4-1; o+=4
        for i in range(cnt):
            l=u32(o); tts.append(d[o+4:o+4+l].rstrip(b'\0')); o+=4+l
    r['tooltypes']=tts; r['end']=o; r['len']=len(d)
    return r
if __name__=='__main__':
    for p in sys.argv[1:]: print(p,parse(p))
