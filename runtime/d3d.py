# input: original IDirect3D3/IDirect3DDevice3/IDirect3DViewport3 calls; output: d3dgl draws on the Mac GL context; pos: Direct3D 6 adapter.
import struct,time,ctypes as C
from com import Obj
HAL=bytes.fromhex('e03de684aa46cf11816f0000c020156e')
FORMAT_ORDER=[0,1,2,3,4]
def device_desc(size):
 b=bytearray(max(size,252))
 prim=struct.pack('<14I',56,0x7f,0xffff,0xff,0x1fff,0x1fff,0xff,0xfffff,0x1ff|0x40,0x3ffff,0xff,0x1f,32,32)
 struct.pack_into('<4I',b,0,size,0x7ff,2,0xfffff)
 struct.pack_into('<2I',b,16,8,1);struct.pack_into('<I',b,24,1);struct.pack_into('<4I',b,28,16,0xf,1,8)
 b[44:100]=prim;b[100:156]=prim
 struct.pack_into('<8I',b,156,0x400|0x100,0x400|0x200|0x100,0,65535,1,1,2048,2048)
 struct.pack_into('<3I',b,204,2048,2048,1)
 struct.pack_into('<4f',b,216,-4096,-4096,4096,4096)
 struct.pack_into('<3I',b,236,0,0x80008|2,0x3ffffff);struct.pack_into('<2H',b,248,2,2)
 return bytes(b[:size])
class Viewport(Obj):
 kinds=('VP3',)
 def __init__(self,d3d):self.d3d=d3d;self.data=(0,0,640,480,0.0,1.0);self.bg=0;self.lights=[]
 def method(self,kind,i,a):return self.d3d.viewport(self,i,a)
class Light(Obj):
 kinds=('Light',)
 def __init__(self,d3d):self.d3d=d3d;self.data=None
 def method(self,kind,i,a):
  r=self.d3d.r
  if i==3:return 0,2
  if i==4:
   size=r.r32(a[1]);self.data=bytes(r.u.mem_read(a[1],max(76,min(size,80))));self.d3d.lights_dirty=True;return 0,2
  if i==5:
   if self.data:r.u.mem_write(a[1],self.data[:r.r32(a[1]) or len(self.data)])
   return 0,2
  return super().method(kind,i,a)
class Material(Obj):
 kinds=('Mat3',)
 def __init__(self,d3d):self.d3d=d3d;self.values=(1,1,1,1,1,1,1,1,0,0,0,0,0,0,0,0,0)
 def method(self,kind,i,a):
  r=self.d3d.r
  if i==3:self.values=struct.unpack('<17f',bytes(r.u.mem_read(a[1]+4,68)));self.d3d.material_dirty=True;return 0,2
  if i==4:r.u.mem_write(a[1]+4,struct.pack('<17f',*self.values));return 0,2
  if i==5:r.w32(a[2],self.d3d.dd.com.ptr(self,'Mat3'));return 0,3
  return super().method(kind,i,a)
class Device(Obj):
 kinds=('Dev3',)
 def __init__(self,d3d,rt):self.d3d=d3d;self.rt=rt;self.viewports=[];self.current=None
 def method(self,kind,i,a):return self.d3d.device(self,i,a)
class Buffer(Obj):
 kinds=('VB',)
 def __init__(self,r,fvf,count,size):self.fvf=fvf;self.count=count;self.data=r.alloc(size*count)
 def method(self,kind,i,a):
  r=self.r
  if i==3:r.w32(a[2],self.data);a[3] and r.w32(a[3],0);return 0,4
  if i==4:return 0,1
  return super().method(kind,i,a)
class D3D:
 def __init__(self,r):self.r=r;self.draws=0;self.frames=0;self._lights=True;self.material=None;self._material=False;self.vp=None
 # Either flag sends draws back through Python so lights/material reach GL before the native path resumes.
 @property
 def lights_dirty(self):return self._lights
 @lights_dirty.setter
 def lights_dirty(self,v):self._lights=v;self.r.update_gate()
 @property
 def material_dirty(self):return self._material
 @material_dirty.setter
 def material_dirty(self,v):self._material=v;self.r.update_gate()
 @property
 def dd(self):return self.r.api.dd
 def direct3d(self,dd,i,a):
  r=self.r
  if i==3:
   hal=r.blob(device_desc(252));hel=r.blob(device_desc(252));r.w32(hel+8,0)
   r.queue_callbacks([(a[1],[r.blob(HAL),r.blob(b'Direct3D HAL\0'),r.blob(b'Mac OpenGL\0'),hal,hel,a[2]])]);return 0,3
  if i==4:l=Light(self);r.w32(a[1],dd.com.wrap(l,'Light'));return 0,3
  if i==5:m=Material(self);r.w32(a[1],dd.com.wrap(m,'Mat3'));return 0,3
  if i==6:vp=Viewport(self);r.w32(a[1],dd.com.wrap(vp,'VP3'));return 0,3
  if i==7:
   out=a[2];size=r.r32(out) or 0
   r.u.mem_write(out+4,HAL);r.u.mem_write(out+20,device_desc(252)[:max(0,size-20)//2]);return 0,3
  if i==8:
   rt=dd.com.get(a[2]);dev=Device(self,rt);dd.rt=rt;rt.loc='sys';dd.gl_ready()
   print('D3D DEVICE on',rt.w,rt.h,flush=True);r.w32(a[3],dd.com.wrap(dev,'Dev3'));return 0,5
  if i==9:
   d=a[1];fvf=r.r32(d+12);n=r.r32(d+16);vb=Buffer(r,fvf,n,self.stride(fvf));vb.r=r;r.w32(a[2],dd.com.wrap(vb,'VB'));return 0,5
  if i==10:
   calls=[]
   for bits,mask in [(16,0xffff),(24,0xffffff)]:
    pf=r.alloc(32);r.u.mem_write(pf,struct.pack('<8I',32,0x400,0,bits if bits==16 else 32,0,mask,0,0));r.w32(pf+12,bits);calls.append((a[2],[pf,a[3]]))
   r.queue_callbacks(calls);return 0,4
  if i==11:return 0,1
  raise NotImplementedError(f'D3D3:{i}')
 def stride(self,fvf):
  s={2:12,4:16,6:16,8:20,0xa:24,0xc:28,0xe:32}.get(fvf&0xe,0)
  return s+(12 if fvf&0x10 else 0)+(4 if fvf&0x20 else 0)+(4 if fvf&0x40 else 0)+(4 if fvf&0x80 else 0)+8*((fvf>>8)&15)
 def apply_viewport(self,vp):
  x,y,w,h,mn,mx=vp.data;self.dd.gl.gl_viewport(x,y,w,h,mn,mx)
 def viewport(self,vp,i,a):
  r=self.r;u=r.u
  if i==3:return 0,2
  if i in (5,17):
   d=a[1];vals=struct.unpack('<5I6f',bytes(u.mem_read(d,44)));vp.data=(vals[1],vals[2],vals[3],vals[4],vals[9],vals[10])
   if self.dd.gl:self.apply_viewport(vp)
   return 0,2
  if i in (4,16):
   x,y,w,h,mn,mx=vp.data;size=r.r32(a[1]) or 44
   body=struct.pack('<5I6f',size,x,y,w,h,*( (1,1,1,1) if i==4 else (-1,1,2,2)),mn,mx);u.mem_write(a[1],body[:size]);return 0,2
  if i==8:vp.bg=a[1];return 0,2
  if i==9:r.w32(a[1],vp.bg);r.w32(a[2],0);return 0,3
  if i in (10,18):return 0,2
  if i in (11,19):r.w32(a[1],0);a[2] and r.w32(a[2],0);return 0,3
  if i in (12,20):
   # Clear(count,rects,flags) / Clear2(count,rects,flags,color,z,stencil)
   n=a[1];flags=a[3];color=a[4] if i==20 else 0;z=struct.unpack('<f',struct.pack('<I',a[5]))[0] if i==20 else 1.0
   rt=self.dd.rt;self.dd.to_gl(rt)
   if a[2] and n:
    for k in range(n):x0,y0,x1,y1=struct.unpack('<4i',bytes(u.mem_read(a[2]+16*k,16)));self.dd.gl.gl_clear(x0,y0,x1-x0,y1-y0,flags,color,z)
   else:x,y,w,h,_,_=vp.data;self.dd.gl.gl_clear(x,y,w,h,flags,color,z)
   return 0,(4 if i==12 else 7)
  if i==13:vp.lights.append(self.dd.com.get(a[1]));self.lights_dirty=True;return 0,2
  if i==14:
   l=self.dd.com.get(a[1])
   if l in vp.lights:vp.lights.remove(l)
   self.lights_dirty=True;return 0,2
  if i==15:r.w32(a[2],0);return 0,4
  if i in (6,7):return 0x80004001,(6 if i==6 else 3)
  return Obj.method(vp,'VP3',i,a)
 def texture(self,p):
  s=self.dd.com.get(p) if p else None
  if s is None:return 0
  if s.dirty or not s.tex:
   gl=self.dd.gl;key=s.key is not None
   s.tex=gl.gl_texture(s.tex,self.r.host(s.pixels),s.w,s.h,s.pitch,s.fmt,int(key),*(s.key or (0,0)));s.dirty=False
  self.r.fast.fast_tex_put(p,s.tex);s.fast_ptrs.add(p)
  return s.tex
 def push_lights(self,dev):
  self.lights_dirty=False;vp=dev.current;lights=[l for l in (vp.lights if vp else []) if l and l.data][:8]
  for k in range(8):
   if k<len(lights):
    d=lights[k].data;size,typ=struct.unpack('<2I',d[:8]);f=struct.unpack('<17f',d[8:76]);flags=struct.unpack('<I',d[76:80])[0] if len(d)>=80 else 1
    F=C.c_float
    self.dd.gl.gl_light(k,int(flags&1 or size<80),typ,(F*4)(*f[0:4]),(F*3)(*f[4:7]),(F*3)(*f[7:10]),f[10],f[12],f[13],f[14],f[15],f[16])
   else:self.dd.gl.gl_light(k,0,0,(C.c_float*4)(),(C.c_float*3)(),(C.c_float*3)(),0,0,0,0,0,0)
 def draw(self,dev,prim,fvf,verts,count,idx,icount,flags=0):
  dd=self.dd;dd.to_gl(dev.rt)
  if self.lights_dirty:self.push_lights(dev)
  if self.material_dirty and self.material:dd.gl.gl_material((C.c_float*17)(*self.material.values));self.material_dirty=False
  for st in (0,1):dd.gl.gl_bind(st,self.texture(self.r.fast.fast_texture(st)))
  err=dd.gl.gl_draw(prim,fvf,self.r.host(verts),count,self.r.host(idx) if idx else None,icount,flags)
  self.draws+=1
  if err and self.draws<50:print('GL error',hex(err),'fvf',hex(fvf),flush=True)
 def device(self,dev,i,a):
  r=self.r;u=r.u;gl=self.dd.gl
  if i==3:
   for p in a[1:3]:
    if p:u.mem_write(p,device_desc(r.r32(p) or 252))
   return 0,3
  if i==5:dev.viewports.append(a[1]);return 0,2
  if i==6:return 0,2
  if i==8:
   calls=[]
   for f in FORMAT_ORDER:pf=r.alloc(32);self.dd.write_pf(pf,f);calls.append((a[1],[pf,a[2]]))
   r.queue_callbacks(calls);return 0,3
  if i==9:return 0,1
  if i==10:
   self.frames+=1;now=time.monotonic();dt=now-getattr(self,'last_end',now);self.worst=max(getattr(self,'worst',0),dt);self.last_end=now
   if dt>0.025:self.slow=getattr(self,'slow',0)+1
   if self.frames%120==1:print('FRAME',self.frames,'draws',self.draws+self.r.fast.fast_draws(),'t',round(now,2),'worst_ms',round(self.worst*1000),'slow',getattr(self,'slow',0),flush=True);self.worst=0;self.slow=0
   return 0,1
  if i==11:r.w32(a[1],self.dd.com.ptr(self.dd,'D3D3'));return 0,2
  if i==12:dev.current=self.dd.com.get(a[1]);self.apply_viewport(dev.current);self.lights_dirty=True;return 0,2
  if i==13:r.w32(a[1],self.dd.com.ptrs.get((id(dev.current),'VP3'),0));return 0,2
  if i==14:dev.rt=self.dd.com.get(a[1]);self.dd.rt=dev.rt;r.update_gate();return 0,3
  if i==15:r.w32(a[1],self.dd.com.ptr(dev.rt,'Surf4'));return 0,2
  if i==21:r.w32(a[2],gl.gl_get_render_state(a[1]));return 0,3
  if i==22:
   gl.gl_render_state(a[1],a[2])
   if a[1]==1:self.r.fast.fast_set_texture(0,a[2])
   if a[1]==21:self.legacy_blend(a[2])
   return 0,3
  if i==23:r.w32(a[2],self.light_state.get(a[1],0) if hasattr(self,'light_state') else 0);return 0,3
  if i==24:
   if not hasattr(self,'light_state'):self.light_state={}
   self.light_state[a[1]]=a[2]
   if a[1]==1:self.material=self.dd.com.get(a[2]);self.material_dirty=True
   if a[1]==2:gl.gl_ambient(a[2])
   return 0,3
  if i==25:gl.gl_transform(a[1],r.host(a[2]));return 0,3
  if i==26:gl.gl_get_transform(a[1],r.host(a[2]));return 0,3
  if i==27:
   cur=(C.c_float*16)();gl.gl_get_transform(a[1],cur);m=struct.unpack('<16f',bytes(u.mem_read(a[2],64)))
   out=[sum(m[r_*4+k]*cur[k*4+c] for k in range(4)) for r_ in range(4) for c in range(4)]
   gl.gl_transform(a[1],(C.c_float*16)(*out));return 0,3
  if i==28:self.draw(dev,a[1],a[2],a[3],a[4],0,0,a[5]);return 0,6
  if i==29:self.draw(dev,a[1],a[2],a[3],a[4],a[5],a[6],a[7]);return 0,8
  if i in (30,31):return 0,2
  if i==34:vb=self.dd.com.get(a[2]);self.draw(dev,a[1],vb.fvf,vb.data+a[3]*self.stride(vb.fvf),a[4],0,0,a[5]);return 0,6
  if i==35:vb=self.dd.com.get(a[2]);self.draw(dev,a[1],vb.fvf,vb.data,vb.count,a[3],a[4],a[5]);return 0,6
  if i==37:r.w32(a[2],self.r.fast.fast_texture(a[1]));return 0,3
  if i==38:
   self.r.fast.fast_set_texture(a[1],a[2]);return 0,3
  if i==39:r.w32(a[3],gl.gl_get_stage_state(a[1],a[2]));return 0,4
  if i==40:gl.gl_stage_state(a[1],a[2],a[3]);return 0,4
  if i==41:r.w32(a[1],1);return 0,2
  return Obj.method(dev,'Dev3',i,a)
 def legacy_blend(self,mode):
  # D3DRENDERSTATE_TEXTUREMAPBLEND → stage 0 states (DECAL, MODULATE, DECALALPHA, MODULATEALPHA, ADD).
  gl=self.dd.gl
  table={1:(2,2,1,2,2,1),2:(4,2,1,2,2,1),3:(13,2,1,2,1,1),4:(4,2,1,4,2,1),7:(7,2,1,2,1,1),5:(2,2,1,2,2,1)}
  if mode in table:
   for st,v in zip((1,2,3,4,5,6),table[mode]):gl.gl_stage_state(0,st,v)
