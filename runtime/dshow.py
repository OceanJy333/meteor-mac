# input: CoCreateInstance(CLSID_FilterGraph) and the DirectShow calls of the game's music player; output: host-decoded mp3 voices; pos: background-music adapter.
# The game plays music/*.mp3 through IGraphBuilder::RenderFile + IMediaControl/IMediaSeeking/IMediaEventEx/IBasicAudio;
# video interfaces stay unsupported, which the player already tolerates (audio-only files).
import struct,ctypes as C
from com import Obj
E_ABORT=0x80004004;EC_COMPLETE=1;UNITS=10_000_000
class Graph(Obj):
 kinds=('FG','MC','MS','ME','BA')
 def __init__(self,r,api):
  self.r=r;self.api=api;api.audio();self.lib=api.sound.lib;self.voice=-1;self.done_sent=False;self.vol=0;self.bal=0;self.file=''
  lib=self.lib
  for n,t,res in [('au_stream_open',[C.c_char_p],C.c_int),('au_stream_close',[C.c_int],None),('au_length',[C.c_int],C.c_uint)]:
   f=getattr(lib,n);f.argtypes=t;f.restype=res
 def seconds(self,b):return b/(44100*4)
 def length(self):return self.seconds(self.lib.au_length(self.voice)) if self.voice>=0 else 0.0
 def position(self):return self.seconds(self.lib.au_get_pos(self.voice)) if self.voice>=0 else 0.0
 def put64(self,p,v):
  if p:self.r.u.mem_write(p,struct.pack('<q',int(v)))
 def method(self,kind,i,a):
  r=self.r;lib=self.lib;v=self.voice
  if 3<=i<=6 and kind in ('MC','ME','BA'):return 0x80004001,{3:2,4:4,5:6,6:9}[i]  # IDispatch
  if kind=='FG':
   if i==13:
    # RenderFile(LPCWSTR file, LPCWSTR playlist)
    raw=b'';p=a[1]
    while len(raw)<1024:
     c=bytes(r.u.mem_read(p+len(raw),2))
     if c==b'\0\0':break
     raw+=c
    self.file=raw.decode('utf-16-le');path=self.api.resolve(self.file)
    if v>=0:lib.au_stream_close(v)
    self.voice=lib.au_stream_open(str(path).encode());print('MUSIC',self.file,path.exists(),'voice',self.voice,flush=True)
    return (0 if self.voice>=0 else 0x80040216),3
   if i in (3,4,7,8,9,10,11,12,14,15,16,17):return 0x80004001,{3:3,4:2,7:4,8:2,9:2,10:1,11:3,12:2,14:4,15:2,16:1,17:1}[i]
  if kind=='MC':
   if i==7:
    if v>=0:lib.au_volume(v,self.vol);lib.au_pan(v,self.bal);lib.au_play(v,0);self.done_sent=False
    return 0,1
   if i==8:
    if v>=0:lib.au_stop(v)
    return 0,1
   if i==9:
    if v>=0:lib.au_stop(v);lib.au_set_pos(v,0)
    return 0,1
   if i==10:r.w32(a[2],2 if v>=0 and lib.au_status(v) else 0);return 0,3
   if i==11:return 0x80004001,2
   if i==15:return 0,1
  if kind=='MS':
   if i==3:r.w32(a[1],0x7f);return 0,2
   if i==4:return 0,2
   if i==5 or i==8:return 0,2
   if i==6 or i==7:r.u.mem_write(a[1],struct.pack('<IHH8s',0x7b785574,0x8c82,0x11cf,bytes.fromhex('bc0c00aa00ac74f6')));return 0,2  # TIME_FORMAT_MEDIA_TIME
   if i==9:return 0,2
   if i==10 or i==11:self.put64(a[1],self.length()*UNITS);return 0,2
   if i==12:self.put64(a[1],self.position()*UNITS);return 0,2
   if i==14:
    # SetPositions(pCurrent, flags, pStop, flags): only absolute current position is used for looping/restart.
    if a[1] and a[2]&3 and v>=0:
     t=struct.unpack('<q',bytes(r.u.mem_read(a[1],8)))[0]/UNITS;lib.au_set_pos(v,int(t*44100)*4);self.done_sent=False
    return 0,5
   if i==15:self.put64(a[1],self.position()*UNITS);self.put64(a[2],self.length()*UNITS);return 0,3
   if i==16:self.put64(a[1],0);self.put64(a[2],self.length()*UNITS);return 0,3
   if i==17:return 0,3
   if i==18:r.u.mem_write(a[1],struct.pack('<d',1.0));return 0,2
   if i==19:self.put64(a[1],0);return 0,2
  if kind=='ME':
   if i==7:r.w32(a[1],0);return 0,2
   if i==8:
    # GetEvent: report EC_COMPLETE once when the track has ended.
    if v>=0 and not lib.au_status(v) and not self.done_sent and self.position()>=self.length()-0.05:
     self.done_sent=True;r.w32(a[1],EC_COMPLETE);r.w32(a[2],0);r.w32(a[3],0);return 0,5
    return E_ABORT,5
   if i==9:r.w32(a[2],0);return E_ABORT,3
   if i in (10,11):return 0,2
   if i==12:return 0,4
   if i==13:return 0,4
   if i==14:return 0,2
   if i==15:r.w32(a[1],0);return 0,2
  if kind=='BA':
   if i==7:
    self.vol=struct.unpack('<i',struct.pack('<I',a[1]))[0]
    if v>=0:lib.au_volume(v,self.vol)
    return 0,2
   if i==8:r.w32(a[1],self.vol&0xffffffff);return 0,2
   if i==9:
    self.bal=struct.unpack('<i',struct.pack('<I',a[1]))[0]
    if v>=0:lib.au_pan(v,self.bal)
    return 0,2
   if i==10:r.w32(a[1],self.bal&0xffffffff);return 0,2
  return super().method(kind,i,a)
 def on_release(self):
  if self.voice>=0:self.lib.au_stream_close(self.voice);self.voice=-1
