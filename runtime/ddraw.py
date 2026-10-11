# input: original IDirectDraw/IDirectDraw4/surface calls; output: guest surfaces kept in sync with the GL render target; pos: DirectDraw adapter.
import struct,ctypes as C,pathlib
from com import Com,Obj
LIB=pathlib.Path(__file__).with_name('libd3dgl.dylib')
FORMATS={0:(0x40,16,0xf800,0x7e0,0x1f,0),1:(0x41,16,0x7c00,0x3e0,0x1f,0x8000),2:(0x41,16,0xf00,0xf0,0xf,0xf000),3:(0x40,16,0x7c00,0x3e0,0x1f,0),4:(0x41,32,0xff0000,0xff00,0xff,0xff000000),5:(0x40,32,0xff0000,0xff00,0xff,0)}
CAP_PRIMARY=0x200;CAP_BACK=0x4;CAP_TEXTURE=0x1000;CAP_3D=0x2000;CAP_Z=0x20000;CAP_MIPMAP=0x400000;CAP_FLIP=0x10;CAP_COMPLEX=0x8
def load_gl():
 g=C.CDLL(str(LIB));P=C.c_void_p;I=C.c_int;U=C.c_uint
 for n,t,res in [('gl_reset',[I,I],None),('gl_render_state',[I,U],None),('gl_get_render_state',[I],U),('gl_stage_state',[I,I,U],None),('gl_get_stage_state',[I,I],U),
  ('gl_transform',[I,P],None),('gl_get_transform',[I,P],None),('gl_viewport',[I,I,I,I,C.c_float,C.c_float],None),('gl_bind',[I,U],None),
  ('gl_texture',[U,P,I,I,I,I,I,U,U],U),('gl_delete_texture',[U],None),('gl_draw',[I,U,P,I,P,I,I],I),('gl_light',[I,I,I,P,P,P]+[C.c_float]*6,None),('gl_material',[P],None),('gl_ambient',[U],None),('gl_clear',[I,I,I,I,I,U,C.c_float],None),
  ('gl_blit',[P,I,I,I,I,I,I,I,I,I,I,I,U,U],None),('gl_readback',[P,I,I,I],None),
  ('sw_blit',[P,I,I,I,I,I,I,I,P,I,I,I,I,I,I,I,I,I,U,U],None),('sw_fill',[P,I,I,I,I,I,I,I,I,U],None),('sw_text',[P,I,I,I,I,C.c_char_p,I,I,I,I,U],None),
  ('fast_install',[P,P,U,U,P,P,P],I),('fast_stub',[U,I,U],None),('fast_gate',[I],None),('fast_tex_put',[U,U],None),('fast_tex_drop',[U],None),
  ('fast_set_texture',[I,U],None),('fast_texture',[I],U),('fast_draws',[],C.c_long),('gl_drawable',[P],None),('gl_grab',[P,I,P],I),('gl_mode',[I,I],None)]:
  f=getattr(g,n);f.argtypes=t;f.restype=res
 return g
class Surface(Obj):
 kinds=('Surf','Surf4','Tex2')
 def __init__(self,dd,w,h,fmt,caps):
  self.dd=dd;self.w=w;self.h=h;self.fmt=fmt;self.bpp=4 if fmt>=4 else 2;self.pitch=w*self.bpp;self.caps=caps
  self.pixels=dd.r.alloc(max(1,self.pitch*h));dd.r.u.mem_write(self.pixels,b'\0'*(self.pitch*h))
  self.fast_ptrs=set();self.key=None;self.attached=[];self.tex=0;self.dirty=True;self.loc='sys';self.clipper=0
 def method(self,kind,i,a):return self.dd.surface_method(self,kind,i,a)
 # The native draw path caches GL ids per texture pointer and needs the render target on the GPU; keep both in sync.
 @property
 def dirty(self):return self._dirty
 @dirty.setter
 def dirty(self,v):
  self._dirty=v
  if v and self.fast_ptrs:
   for p in self.fast_ptrs:self.dd.r.fast.fast_tex_drop(p)
 @property
 def loc(self):return self._loc
 @loc.setter
 def loc(self,v):
  self._loc=v
  if self is self.dd.rt:self.dd.r.update_gate()
class Clipper(Obj):
 kinds=('Clipper',)
 def method(self,kind,i,a):
  if i==8:return 0,3 # SetHWnd
  if i==4:self.dd.r.w32(a[1],20);return 0,2
  if i==7:return 0,3
  return super().method(kind,i,a)
class DirectDraw(Obj):
 kinds=('DD','DD4','D3D3')
 def __init__(self,r):
  self.r=r;self.com=Com(r);self.w=640;self.h=480;self.depth=16;self.primary=None;self.rt=None;self.scale=1.0;self.gl=None;self.host=None
  self.surfaces={};self.gl_dcs={}
 # ---- helpers
 def hp(self,p):return self.r.host(p)
 def gl_ready(self):
  if not self.gl:self.gl=self.gl_or_none();self.host.host_gl_open();self.gl.gl_reset(self.w,self.h)
  return self.gl
 def new_surface(self,w,h,fmt,caps,kind):
  s=Surface(self,w,h,fmt,caps);p=self.com.wrap(s,kind);self.register(s);return s,p
 def register(self,s):
  for k in ('Surf','Surf4','Tex2'):
   p=self.com.ptrs.get((id(s),k))
   if p:self.surfaces[p]=(s.w,s.h,s.bpp*8,s.pixels)
 def write_pf(self,p,fmt):
  f,bits,rm,gm,bm,am=FORMATS[fmt];self.r.u.mem_write(p,struct.pack('<8I',32,f,0,bits,rm,gm,bm,am))
 def read_fmt(self,p):
  size,flags,fourcc,bits,rm,gm,bm,am=struct.unpack('<8I',bytes(self.r.u.mem_read(p,32)))
  for k,(f,b,R,G,B,A) in FORMATS.items():
   if bits==b and rm==R and gm==G and bm==B and (am==A or not flags&1 and A==0):return k
  return 0 if bits<=16 else 5
 def write_desc(self,p,s,lock_ptr=None):
  size=self.r.r32(p) or 124;size=124 if size>=124 else 108
  self.r.u.mem_write(p,b'\0'*size)
  self.r.u.mem_write(p,struct.pack('<5I',size,0x100f|0x800,s.h,s.w,s.pitch));self.r.w32(p+36,lock_ptr if lock_ptr is not None else s.pixels)
  if s.key:self.r.u.mem_write(p+64,struct.pack('<2I',*s.key))
  self.write_pf(p+72,s.fmt);self.r.w32(p+104,s.caps|(0x4000 if not s.caps&0x800 else 0))
 # ---- render target synchronisation
 def to_sys(self,s):
  if s is self.rt and self.gl and s.loc!='sys':
   if s.loc=='gl':self.gl.gl_readback(self.hp(s.pixels),s.pitch,s.w,s.h)
   s.loc='sys'
 def dc_sys(self,h):
  # A GDI call that needs real pixels: fall back to system memory for this DC.
  s=self.gl_dcs.pop(h,None)
  if s:self.to_sys(s)
 def gl_text(self,h,x,y,mask,mw,mh,px,dw,dh):
  # mask is rasterized at display-pixel scale; dw×dh is its size in game pixels.
  s=self.gl_dcs[h];lib=self.gl;pitch=mw*s.bpp;key=px^1;buf=C.create_string_buffer(pitch*mh);p=C.addressof(buf)
  lib.sw_fill(p,pitch,mw,mh,0,0,mw,mh,s.bpp,key);lib.sw_text(p,pitch,mw,mh,s.bpp,mask,mw,mh,0,0,px)
  lib.gl_blit(p,pitch,s.fmt,0,0,mw,mh,x,y,dw,dh,1,key,key)
 def gl_fill(self,h,l,t,rr,bb,c):
  self.gl.gl_clear(l,t,rr-l,bb-t,1,(c&255)<<16|(c&0xff00)|(c>>16)&255|0xff000000,1.0)
 def to_gl(self,s):
  if s.loc=='sys':self.gl_ready().gl_blit(self.hp(s.pixels),s.pitch,s.fmt,0,0,s.w,s.h,0,0,s.w,s.h,0,0,0)
  s.loc='gl'
 def present(self,s):
  # GL back buffer == render target. Presenting a system surface overwrites it; after a swap its
  # contents are undefined, so a GL-only frame becomes 'lost' (the game clears before drawing again).
  self.gl_ready();was=s.loc
  if s is not self.rt and self.rt and self.rt.loc=='gl':self.rt.loc='lost'
  s.loc='sys' if was=='lost' and s is not self.rt else s.loc
  self.to_gl(s);self.snapshot();self.swap()
  s.loc='sys' if (was=='sys' or s is not self.rt) else 'lost'
 def swap(self):
  # After each flip, refresh the Retina drawable / letterbox so the next frame maps game pixels onto it.
  self.host.host_gl_swap();d=(C.c_int*6)();self.host.host_gl_drawable(d);self.gl.gl_drawable(d);self.scale=max(1.0,d[4]/self.w)
 def snapshot(self):
  # Debug capture of the presented frame: METEOR_SNAP=<seconds> writes logs/snap-N.png.
  import os,time
  every=float(os.environ.get('METEOR_SNAP','0') or 0)
  if not every or time.monotonic()-getattr(self,'snap_at',0)<every:return
  self.snap_at=time.monotonic();self.snaps=getattr(self,'snaps',0)+1
  cap=4096*4096*4;buf=getattr(self,'grab',None) or C.create_string_buffer(cap);self.grab=buf;size=(C.c_int*2)()
  if not self.gl.gl_grab(buf,cap,size):return
  from PIL import Image
  im=Image.frombuffer('RGBA',(size[0],size[1]),buf,'raw','RGBA',0,-1).convert('RGB')
  out=__import__('paths').LOGS/f'snap-{self.snaps:03d}.png';im.save(out)
 # ---- IDirectDraw / IDirectDraw4 / IDirect3D3
 def method(self,kind,i,a):
  if kind=='D3D3':return self.r.api.d3d.direct3d(self,i,a)
  r=self.r;v4=kind=='DD4'
  if i==4:c=Clipper();c.dd=self;r.w32(a[2],self.com.wrap(c,'Clipper'));return 0,4
  if i==5:r.w32(a[3],0);return 0x80004001,5
  if i==6:return self.create_surface(a,v4),4
  if i==8:
   calls=[]
   for w,h in [(640,480),(800,600),(1024,768)]:
    for bpp in (16,32):
     d=r.alloc(124);fmt=0 if bpp==16 else 5;s=Surface.__new__(Surface);s.w,s.h,s.fmt,s.pitch,s.caps,s.key,s.pixels=w,h,fmt,w*bpp//8,0,None,0
     r.w32(d,124 if v4 else 108);self.write_desc(d,s);r.w32(d+4,0x100e);calls.append((a[4],[d,a[3]]))
   r.queue_callbacks(calls);return 0,5
  if i==11:
   for p in a[1:3]:
    if p:
     size=r.r32(p);r.u.mem_write(p+4,b'\0'*(size-4));r.w32(p+4,0x1|0x40|0x200|0x400000|0x4000000|0x10000000);r.w32(p+12,0x200)
     r.w32(p+56,0x400|0x200);r.w32(p+60,256<<20);r.w32(p+64,192<<20);r.w32(p+132,0x1000|0x2000|0x20000|0x4000|0x10|0x200|4|0x40|8|0x400000|0x800)
     if size>=380:r.w32(p+364,r.r32(p+132))
   return 0,3
  if i==12:
   s=Surface.__new__(Surface);s.w,s.h,s.fmt,s.pitch,s.caps,s.key,s.pixels=self.w,self.h,0 if self.depth==16 else 5,self.w*self.depth//8,0,None,0
   self.write_desc(a[1],s);return 0,2
  if i==19:return 0,1
  if i==20:return 0,3
  if i==10:return 0,1  # FlipToGDISurface
  if i==21:
   # SetDisplayMode is the authority for game-space size; window mapping and GL follow it.
   self.w,self.h,self.depth=a[1],a[2],a[3];print('DISPLAY MODE',a[1:4],flush=True)
   if self.host:self.host.host_set_mode(self.w,self.h)
   if self.gl:self.gl.gl_mode(self.w,self.h)
   return 0,(6 if kind!='DD' else 4)
  if i==22:return 0,3
  if i==23 and v4:
   if a[2]:r.w32(a[2],256<<20)
   if a[3]:r.w32(a[3],192<<20)
   return 0,4
  if i==25 and v4:return 0,1
  if i==26 and v4:return 0,1
  if i==27 and v4:
   r.u.mem_write(a[1],b'\0'*1064);r.u.mem_write(a[1],b'macOS OpenGL D3D6 adapter\0');r.u.mem_write(a[1]+512,b'Apple Silicon (REA port)\0');return 0,3
  return super().method(kind,i,a)
 def create_surface(self,a,v4):
  r=self.r;d=a[1];flags=r.r32(d+4);caps=r.r32(d+104) if flags&1 else 0
  w=r.r32(d+12) if flags&4 else self.w;h=r.r32(d+8) if flags&2 else self.h
  fmt=self.read_fmt(d+72) if flags&0x1000 else (0 if self.depth==16 else 5)
  kind='Surf4' if v4 else 'Surf'
  if caps&CAP_Z:fmt=0
  s,p=self.new_surface(w,h,fmt,caps,kind)
  if flags&0x10000:s.key=struct.unpack('<2I',bytes(r.u.mem_read(d+64,8)))
  if caps&CAP_PRIMARY:
   self.primary=s
   if flags&0x20 and r.r32(d+20):
    b,_=self.new_surface(w,h,fmt,CAP_BACK|CAP_3D|(caps&0x4000),kind);s.attached.append(b);b.attached.append(s)
  if caps&CAP_MIPMAP and flags&0x20000:
   parent=s
   for lvl in range(1,r.r32(d+24)):
    c,_=self.new_surface(max(1,w>>lvl),max(1,h>>lvl),fmt,caps,kind);parent.attached.append(c);parent=c
  print('SURFACE',w,h,'fmt',fmt,'caps',hex(caps),'flags',hex(flags),hex(p),flush=True)
  r.w32(a[2],p);return 0
 # ---- IDirectDrawSurface (1..4) and IDirect3DTexture2
 def surface_method(self,s,kind,i,a):
  r=self.r;gl=self.gl
  if kind=='Tex2':
   if i==3:r.w32(a[2],a[0]);return 0,3
   if i==4:return 0,3
   if i==5:
    src=self.com.get(a[1]);r.u.mem_write(s.pixels,bytes(r.u.mem_read(src.pixels,min(s.pitch*s.h,src.pitch*src.h))));s.key=src.key or s.key;s.dirty=True;return 0,2
   return super(Surface,s).method(kind,i,a)
  if i==3:
   z=self.com.get(a[1]);s.attached.append(z);return 0,2
  if i==5:return self.blt(s,a),6
  if i==7:
   src=self.com.get(a[3]);sr=self.rect(a[4],src);x,y=struct.unpack('<2i',struct.pack('<2I',a[1],a[2]))
   self.copy(s,(x,y,x+sr[2]-sr[0],y+sr[3]-sr[1]),src,sr,bool(a[5]&1));return 0,6
  if i==8:return 0,3
  if i==9:return 0,3
  if i==11:
   back=next((x for x in s.attached if x.caps&CAP_BACK),s);self.present(back);return 0,3
  if i==12:
   want=r.r32(a[1]);m=[x for x in s.attached if x.caps&want]
   if not m:r.w32(a[2],0);print('NO ATTACHED',hex(want),flush=True);return 0x887600ff,3
   r.w32(a[2],self.com.wrap(m[0],kind));self.register(m[0]);return 0,3
  if i==13 or i==18:return 0,2
  if i==14:r.w32(a[1],s.caps);return 0,2
  if i==15:r.w32(a[1],s.clipper);return 0,2
  if i==16:
   if not s.key:return 0x887600d0,3 # DDERR_NOCOLORKEY
   r.u.mem_write(a[2],struct.pack('<2I',*s.key));return 0,3
  if i==17:
   # HUD/chat text draws through a DC on the live render target; keep it on the GPU instead of a full readback.
   r.w32(a[1],a[0]);self.register(s)
   if s is self.rt and s.loc=='gl' and self.gl:self.gl_dcs[a[0]]=s
   else:self.gl_dcs.pop(a[0],None);self.to_sys(s)
   return 0,2
  if i==20:r.w32(a[1],0);return 0x887600e1,2
  if i==21:self.write_pf(a[1],s.fmt);return 0,2
  if i==22:self.write_desc(a[1],s);return 0,2
  if i==24:return 0,1
  if i==25:
   self.to_sys(s);rc=self.rect(a[1],s);ptr=s.pixels+rc[1]*s.pitch+rc[0]*s.bpp;self.write_desc(a[2],s,ptr);return 0,5
  if i==26:s.dirty=True;return 0,2
  if i==27:return 0,1
  if i==28:s.clipper=a[1];return 0,2
  if i==29:
   if a[2]:s.key=struct.unpack('<2I',bytes(r.u.mem_read(a[2],8)))
   else:s.key=None
   s.dirty=True;return 0,3
  if i==31:return 0,2
  if i==32:s.dirty=True;return 0,2
  if i==36:r.w32(a[1],self.com.ptr(self,'DD4' if kind=='Surf4' else 'DD'));return 0,2
  if i in (37,38):return 0,2 if i==37 else 2
  if i==43:r.w32(a[1],1);return 0,2
  if i in (40,41,42):return 0x80004001,5 if i==40 else 4 if i==41 else 2
  return super(Surface,s).method(kind,i,a)
 def rect(self,p,s):
  if not p:return (0,0,s.w,s.h)
  return struct.unpack('<4i',bytes(self.r.u.mem_read(p,16)))
 def blt(self,dst,a):
  r=self.r;flags=a[4];dr=self.rect(a[1],dst)
  if flags&0x2000000:
   if self.gl:self.gl.gl_clear(dr[0],dr[1],dr[2]-dr[0],dr[3]-dr[1],2,0,1.0)
   return 0
  if flags&0x400:
   c=r.r32(a[5]+80)
   if dst is self.rt and dst.loc!='sys':
    rgb=((c>>11)&31)*255//31<<16|((c>>5)&63)*255//63<<8|(c&31)*255//31 if dst.bpp==2 else c
    self.gl.gl_clear(dr[0],dr[1],dr[2]-dr[0],dr[3]-dr[1],1,rgb|0xff000000,1.0);dst.loc='gl'
   else:
    self.gl and self.to_sys(dst);self.gl_or_none().sw_fill(self.hp(dst.pixels),dst.pitch,dst.w,dst.h,*dr,dst.bpp,c);dst.dirty=True
   return 0
  src=self.com.get(a[2])
  if src is None:return 0
  key=bool(flags&0x18000)
  if flags&0x10000 and a[5]:src_key=struct.unpack('<2I',bytes(r.u.mem_read(a[5]+92,8)))
  else:src_key=src.key
  self.copy(dst,dr,src,self.rect(a[3],src),key,src_key);return 0
 def gl_or_none(self):
  # Native helpers without requiring the GL context (software blits run before CreateDevice).
  if not hasattr(self,'lib'):self.lib=load_gl()
  return self.lib
 def copy(self,dst,dr,src,sr,key,src_key=None):
  src_key=src_key or src.key or (0,0);key=key and src.key is not None or (key and src_key!=(0,0))
  if dst is self.primary and src is self.rt and not key and src.loc=='gl':
   self.snapshot();self.swap();src.loc='lost';return
  if dst is self.primary:
   self.to_sys(src);self.gl_or_none().sw_blit(self.hp(dst.pixels),dst.pitch,dst.w,dst.h,*dr,self.hp(src.pixels),src.pitch,src.w,src.h,*sr,dst.bpp,int(key),*src_key);self.present(dst);return
  if dst is self.rt and dst.loc!='sys' and src is not self.rt:
   self.gl.gl_blit(self.hp(src.pixels),src.pitch,src.fmt,sr[0],sr[1],sr[2]-sr[0],sr[3]-sr[1],dr[0],dr[1],dr[2]-dr[0],dr[3]-dr[1],int(key),*src_key);dst.loc='gl';return
  self.to_sys(dst);self.to_sys(src)
  self.gl_or_none().sw_blit(self.hp(dst.pixels),dst.pitch,dst.w,dst.h,*dr,self.hp(src.pixels),src.pitch,src.w,src.h,*sr,dst.bpp,int(key),*src_key);dst.dirty=True
 def call(self,n,a):
  if n=='DirectDrawCreate':
   self.r.w32(a[1],self.com.wrap(self,'DD'));return 0,3
  if n=='DirectDrawEnumerateA':
   self.r.queue_callbacks([(a[0],[0,self.r.blob(b'Primary Display Driver\0'),self.r.blob(b'display\0'),a[1]])]);return 0,2
  kind,idx=n.split(':');return self.com.call(kind,int(idx),a)
