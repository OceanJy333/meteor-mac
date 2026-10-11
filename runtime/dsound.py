# input: DirectSoundCreate / IDirectSound / IDirectSoundBuffer and waveOut calls; output: voices in libaudio.dylib; pos: sound adapter.
import struct,ctypes as C,pathlib
from com import Obj
LIB=pathlib.Path(__file__).with_name('libaudio.dylib')
DSBCAPS_PRIMARY=1;DSBPLAY_LOOPING=1;DSERR_INVALIDPARAM=0x80070057
def load():
 g=C.CDLL(str(LIB));P=C.c_void_p;I=C.c_int;U=C.c_uint
 for n,t,res in [('au_open',[P],I),('au_voice',[U,U,U,I,I],I),('au_free',[I],None),('au_play',[I,I],None),('au_stop',[I],None),('au_status',[I],I),
  ('au_get_pos',[I],U),('au_set_pos',[I,U],None),('au_volume',[I,I],None),('au_pan',[I,I],None),('au_freq',[I,U],None),('au_master',[C.c_float],None),
  ('au_wave_open',[U,I,I],None),('au_wave_write',[U],I),('au_wave_reset',[],None),('au_wave_close',[],None),('au_wave_pos',[],U),('au_pan_linear',[I,C.c_float],None)]:
  f=getattr(g,n);f.argtypes=t;f.restype=res
 return g
class Buffer(Obj):
 kinds=('DSB','DS3DL','DS3DB')
 def __init__(self,ds,fmt,data,size,primary,share=None):
  self.pos=(0.0,0.0,0.0);self.mind=1.0;self.maxd=1e9;self.mode=0;self.is3d=False
  self.ds=ds;self.fmt=fmt;self.data=data;self.size=size;self.primary=primary;self.vol=0;self.pan=0
  self.freq=fmt[1];self.voice=-1 if primary else ds.lib.au_voice(data,size,fmt[1],fmt[0],fmt[3])
 def method(self,kind,i,a):
  if kind=='DS3DL':return self.ds.listener(i,a)
  if kind=='DS3DB':self.is3d=True;return self.ds.buffer3d(self,i,a)
  return self.ds.buffer(self,i,a)
 def on_release(self):self.ds.release(self)
class DirectSound(Obj):
 kinds=('DS',)
 def __init__(self,r,com):self.r=r;self.com=com;self.buffers=[];self.lpos=(0.0,0.0,0.0);self.front=(0.0,0.0,1.0);self.top=(0.0,1.0,0.0);self.rolloff=1.0;self.lib=load();self.lib.au_open(C.c_void_p(r.base));self.format=(2,22050,0,16)
 def wavefmt(self,p):
  tag,ch,rate,avg,align,bits=struct.unpack('<HHIIHH',bytes(self.r.u.mem_read(p,16)));return (ch,rate,align,bits)
 def method(self,kind,i,a):
  r=self.r
  if i==3:
   size,flags,nbytes,_,wfx=struct.unpack('<5I',bytes(r.u.mem_read(a[1],20)))
   primary=bool(flags&DSBCAPS_PRIMARY)
   fmt=self.wavefmt(wfx) if wfx else self.format
   data=0 if primary else r.alloc(max(4,nbytes))
   if data:r.u.mem_write(data,b'\0'*nbytes)
   b=Buffer(self,fmt,data,nbytes,primary);b.flags=flags;self.buffers.append(b);r.w32(a[2],self.com.wrap(b,'DSB'));return 0,4
  if i==4:r.u.mem_write(a[1]+4,struct.pack('<I',0xf5f));return 0,2
  if i==5:
   src=self.com.get(a[1]);b=Buffer(self,src.fmt,src.data,src.size,False);b.flags=src.flags;self.buffers.append(b);r.w32(a[2],self.com.wrap(b,'DSB'));return 0,3
  if i in (6,7):return 0,(3 if i==6 else 1)
  if i==8:r.w32(a[1],4);return 0,2  # DSSPEAKER_STEREO
  if i==9:return 0,2
  if i==10:return 0,2
  return super().method(kind,i,a)
 def buffer(self,b,i,a):
  r=self.r;lib=self.lib;v=b.voice
  if i==3:r.u.mem_write(a[1]+4,struct.pack('<4I',b.flags,b.size,0,0));return 0,2
  if i==4:
   pos=lib.au_get_pos(v) if v>=0 else 0
   if a[1]:r.w32(a[1],pos)
   if a[2]:r.w32(a[2],(pos+4096)%max(1,b.size) if b.size else 0)
   return 0,3
  if i==5:
   ch,rate,align,bits=b.fmt
   if a[1]:r.u.mem_write(a[1],struct.pack('<HHIIHH',1,ch,rate,rate*align,align,bits)[:a[2]] if a[2] else b'')
   if a[3]:r.w32(a[3],16)
   return 0,4
  if i==6:r.w32(a[1],b.vol&0xffffffff);return 0,2
  if i==7:r.w32(a[1],b.pan&0xffffffff);return 0,2
  if i==8:r.w32(a[1],b.freq);return 0,2
  if i==9:r.w32(a[1],lib.au_status(v) if v>=0 else 1);return 0,2
  if i==10:return 0,3
  if i==11:
   # Lock(offset,bytes,&p1,&n1,&p2,&n2,flags): the buffer already lives in guest RAM, so hand out direct pointers with wrap-around.
   off,n,flags=a[1],a[2],a[7]
   if flags&1 and v>=0:off=lib.au_get_pos(v)
   if flags&2:off,n=0,b.size
   if not b.data:
    for p in (a[3],a[4],a[5],a[6]):
     if p:r.w32(p,0)
    return 0,8
   off%=max(1,b.size);n=min(n,b.size);first=min(n,b.size-off)
   r.w32(a[3],b.data+off);r.w32(a[4],first)
   if a[5]:r.w32(a[5],b.data if n>first else 0)
   if a[6]:r.w32(a[6],n-first)
   return 0,8
  if i==12:
   if v>=0:
    if b.is3d:self.spatial(b)
    lib.au_play(v,int(a[3]&DSBPLAY_LOOPING))
   return 0,4
  if i==13:
   if v>=0:lib.au_set_pos(v,a[1])
   return 0,2
  if i==14:
   if b.primary:self.format=self.wavefmt(a[1]);b.fmt=self.format
   return 0,2
  if i==15:
   b.vol=struct.unpack('<i',struct.pack('<I',a[1]))[0]
   if v>=0:self.spatial(b) if b.is3d else lib.au_volume(v,b.vol)
   else:lib.au_master(0 if b.vol<=-10000 else 10**(b.vol/2000))
   return 0,2
  if i==16:
   b.pan=struct.unpack('<i',struct.pack('<I',a[1]))[0]
   if v>=0:lib.au_pan(v,b.pan)
   return 0,2
  if i==17:
   b.freq=a[1] or b.fmt[1]
   if v>=0:lib.au_freq(v,b.freq)
   return 0,2
  if i==18:
   if v>=0:lib.au_stop(v)
   return 0,1
  if i==19:return 0,5
  if i==20:return 0,1
  return Obj.method(b,'DSB',i,a)
 def release(self,b):
  if b.voice>=0:self.lib.au_free(b.voice);b.voice=-1
  if b in self.buffers:self.buffers.remove(b)
 def floats(self,a,n):return struct.unpack(f'<{n}f',struct.pack(f'<{n}I',*a[:n]))
 def spatial(self,b):
  # Inverse-distance rolloff plus left/right pan from the listener's right vector (left-handed: right = top × front).
  if b.voice<0:return
  d=[p-l for p,l in zip(b.pos,(0,0,0) if b.mode==1 else self.lpos)];dist=sum(x*x for x in d)**.5
  if b.mode==2 or dist<1e-6:self.lib.au_volume(b.voice,b.vol);self.lib.au_pan_linear(b.voice,0);return
  import math
  att=-2000*self.rolloff*math.log10(max(dist,b.mind)/b.mind) if dist<b.maxd else -10000
  t,f=self.top,self.front;right=(t[1]*f[2]-t[2]*f[1],t[2]*f[0]-t[0]*f[2],t[0]*f[1]-t[1]*f[0]);rn=sum(x*x for x in right)**.5 or 1
  self.lib.au_volume(b.voice,int(max(-10000,b.vol+att)));self.lib.au_pan_linear(b.voice,0.8*sum(x*y for x,y in zip(d,right))/rn/dist)
 def listener(self,i,a):
  r=self.r
  if i==7:r.u.mem_write(a[1],struct.pack('<3f',*self.lpos));return 0,2
  if i==11 or i==12:return 0,3
  if i==13:v=self.floats(a[1:],6);self.front,self.top=v[:3],v[3:];self.respatial();return 0,8
  if i==14:self.lpos=self.floats(a[1:],3);self.respatial();return 0,5
  if i==15:self.rolloff=self.floats(a[1:],1)[0];return 0,3
  if i==16:return 0,5
  if i==17:return 0,1
  if i in (4,5,8):r.w32(a[1],0x3f800000);return 0,2
  if i==10:return 0,3
  raise NotImplementedError(f'DS3DL:{i}')
 def respatial(self):
  for b in self.buffers:
   if b.is3d and b.voice>=0 and self.lib.au_status(b.voice):self.spatial(b)
 def buffer3d(self,b,i,a):
  r=self.r
  if i==10:r.u.mem_write(a[1],struct.pack('<3f',*b.pos));return 0,2
  if i==7:r.u.mem_write(a[1],struct.pack('<f',b.maxd));return 0,2
  if i==8:r.u.mem_write(a[1],struct.pack('<f',b.mind));return 0,2
  if i==9:r.w32(a[1],b.mode);return 0,2
  if i==12:return 0,3
  if i==13:return 0,4
  if i in (14,20):return 0,5
  if i==15:return 0,3
  if i==16:b.maxd=self.floats(a[1:],1)[0];return 0,3
  if i==17:b.mind=self.floats(a[1:],1)[0] or 1.0;return 0,3
  if i==18:b.mode=a[1];self.spatial(b);return 0,3
  if i==19:b.pos=self.floats(a[1:],3);self.spatial(b);return 0,5
  raise NotImplementedError(f'DS3DB:{i}')
class WaveOut:
 # waveOut music stream: the game decodes MP3 itself and queues PCM WAVEHDRs.
 def __init__(self,r,ds):self.r=r;self.ds=ds;self.open=False
 def call(self,n,a):
  r=self.r;lib=self.ds.lib
  if n=='waveOutGetNumDevs':return 1,0
  if n=='waveOutOpen':
   ch,rate,align,bits=self.ds.wavefmt(a[2])
   if a[5]&1:return 0,6
   lib.au_wave_open(rate,ch,bits);self.open=True
   if a[0]:r.w32(a[0],0x5eed)
   print('WAVEOUT',ch,rate,bits,hex(a[5]),flush=True);return 0,6
  if n=='waveOutPrepareHeader':r.w32(a[1]+16,r.r32(a[1]+16)|2);return 0,3
  if n=='waveOutUnprepareHeader':r.w32(a[1]+16,r.r32(a[1]+16)&~2);return 0,3
  if n=='waveOutWrite':lib.au_wave_write(a[1]);return 0,3
  if n=='waveOutReset':lib.au_wave_reset();return 0,1
  if n=='waveOutClose':lib.au_wave_close();self.open=False;return 0,1
  raise NotImplementedError(n)
