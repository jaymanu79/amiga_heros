import json,struct,sys
lang=int(sys.argv[1]); 
NSC=212
pokes=[]; pres=[]; shots=[]; f=300
pres.append([200,'START',3]); pres.append([260,'START',3])
for sc in range(NSC):
    ent=struct.pack('<HHIhh',sc,0xFFFF if sc%2 else 0x00F0,0,20,3)
    cs=1+sum(ent)
    hdr=b'HRS1'+bytes([1,0])+struct.pack('<H',cs&0xFFFF)
    pokes.append([f,0,(hdr+ent).hex()])
    if sc==0: pokes.append([f,0x7F8,('A5%02X'%lang)])
    pres.append([f+3,'START',3])
    for d in range(5): pres.append([f+50+d*6,'DOWN',3])
    pres.append([f+100,'A',3]); shots.append(f+175)
    f+=200
json.dump({'frames':f+10,'presses':pres,'pokes':pokes,'shots':shots,'wav':'/tmp/t8.wav'},open('t8.json','w'))
