# input: DirectInput state requests; output: Mac keyboard and mouse state; pos: input bridge.
import struct
# DirectInput keyboard scancode → Windows VK (US layout); the game binds VKs in user.cfg but polls DIK state.
SCAN={0x01:27,0x0e:8,0x0f:9,0x1c:13,0x1d:17,0x2a:16,0x36:16,0x38:18,0x39:32,0xc8:38,0xd0:40,0xcb:37,0xcd:39,
 **{0x02+i:49+i for i in range(9)},0x0b:48,**{0x3b+i:112+i for i in range(10)},
 **{sc:ord(c) for row,start in (('QWERTYUIOP',0x10),('ASDFGHJKL',0x1e),('ZXCVBNM',0x2c)) for sc,c in zip(range(start,start+len(row)),row)}}
class Input:
 def __init__(self,r):self.r=r;self.devices={};self.last_mouse=(0,0)
 def object(self,kind):
  r=self.r;p=r.alloc(16);v=r.alloc(160);r.w32(p,v)
  for i in range(40):r.w32(v+i*4,r.stub(f'{kind}:{i}'))
  return p
 def call(self,n,a,host):
  r=self.r;u=r.u
  if n.startswith('DirectInputCreate'):
   r.w32(a[3] if n.endswith('Ex') else a[2],self.object('Input'));return 0,5 if n.endswith('Ex') else 4
  kind,index=n.split(':');i=int(index)
  if i==0:r.w32(a[2],a[0]);return 0,3
  if i in [1,2]:return 1,1
  if kind=='Input':
   if i in [3,9]:
    p=self.object('Device');self.devices[p]=r.r32(a[1]);r.w32(a[3] if i==9 else a[2],p);return 0,5 if i==9 else 4
   if i==4:return 0,5
  if kind=='Device':
   if i in [7,8,25]:return 0,1
   if i==9:
    b=bytearray(a[1]);guid=self.devices[a[0]]
    if guid==0x6f1d2b61 and host:
     for sc,vk in SCAN.items():b[sc]=128 if host.host_key(vk) else 0
    elif host and len(b)>=16:
     x,y=host.host_mouse(3),host.host_mouse(4);struct.pack_into('<iii',b,0,x-self.last_mouse[0],y-self.last_mouse[1],0);self.last_mouse=(x,y)
     buttons=host.host_mouse(2);b[12]=128 if buttons&1 else 0;b[13]=128 if buttons&2 else 0
    u.mem_write(a[2],bytes(b));return 0,3
   if i==10:r.w32(a[3],0);return 0,5
   if i in [5,6,13]:return 0,3
   if i==11:return 0,2
   if i==3:return 0,2
   if i==4:return 0,4
  raise NotImplementedError(n)
