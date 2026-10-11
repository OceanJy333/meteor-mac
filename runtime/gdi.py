# input: Win32 bitmap/font calls; output: real guest bitmaps and glyph masks; pos: software UI drawing.
import struct,pathlib
from PIL import Image,ImageDraw,ImageFont
class GDI:
 def __init__(self,r,dd):self.r=r;self.dd=dd;self.objects={};self.contexts={};self.next=10000;self.bottomup={};self.fonts={};self.masks={}
 def handle(self,obj):self.next+=1;self.objects[self.next]=obj;return self.next
 def dc(self,h):return self.contexts.setdefault(h,{'font':None,'bitmap':None,'fg':0xffffff,'bg':0,'opaque':True})
 def font(self,dc):
  f=self.objects.get(dc['font'],('font',16));return self.font_at(max(8,min(96,f[1])))
 def font_at(self,size):
  if size not in self.fonts:
   path='/System/Library/Fonts/STHeiti Light.ttc'
   if not pathlib.Path(path).exists():path='/System/Library/Fonts/Helvetica.ttc'
   self.fonts[size]=ImageFont.truetype(path,size)
  return self.fonts[size]
 def mask(self,txt,dc,k):
  # Chat/HUD lines repeat every frame: rasterize each (text,size,scale) once.
  f=self.objects.get(dc['font'],('font',16));size=max(8,min(192,round(max(8,min(96,f[1]))*k)))
  key=(txt,size);m=self.masks.get(key)
  if not m:
   if size not in self.fonts:self.font_at(size)
   font=self.fonts[size];box=font.getbbox(txt);mw,mh=max(1,box[2]),max(1,box[3]);im=Image.new('L',(mw,mh));ImageDraw.Draw(im).text((0,0),txt,font=font,fill=255)
   if len(self.masks)>2048:self.masks.clear()
   m=self.masks[key]=(im.tobytes(),mw,mh)
  return m
 def target(self,h):
  r=self.r
  self.dd.dc_sys(h)
  if h in self.dd.surfaces:return self.dd.surfaces[h]
  obj=self.objects.get(self.dc(h)['bitmap'])
  return obj[1:] if obj and obj[0]=='bitmap' else None
 def call(self,n,a):
  r=self.r;u=r.u
  if n in ['GetDC','CreateCompatibleDC','CreateDCA']:return self.handle(('dc',)),1 if n!='CreateDCA' else 4
  if n in ['ReleaseDC','DeleteDC','DeleteObject']:return 1,2 if n=='ReleaseDC' else 1
  if n in ['CreateFontA','CreateFontIndirectA']:
   height=a[0] if n=='CreateFontA' else r.r32(a[0]);height=abs(struct.unpack('<i',struct.pack('<I',height))[0]);return self.handle(('font',height or 16)),14 if n=='CreateFontA' else 1
  if n=='SelectObject':
   dc=self.dc(a[0]);kind='font' if self.objects.get(a[1],['bitmap'])[0]=='font' else 'bitmap';old=dc[kind] or 0;dc[kind]=a[1];return old,2
  if n in ['SetTextColor','SetBkColor','SetBkMode']:
   dc=self.dc(a[0]);key={'SetTextColor':'fg','SetBkColor':'bg','SetBkMode':'opaque'}[n];old=dc[key];dc[key]=a[1] if key!='opaque' else a[1]==2;return int(old),2
  if n=='CreateCompatibleBitmap':
   w,h=a[1:3];return self.handle(('bitmap',w,h,32,r.alloc(w*h*4))),3
  if n=='CreateDIBSection':
   size,w,hi,planes,bpp=struct.unpack('<IiiHH',bytes(u.mem_read(a[1],16)));h=abs(hi);stride=((w*bpp+31)//32)*4;p=r.alloc(stride*h);r.w32(a[3],p);self.bottomup[p]=hi>0;return self.handle(('bitmap',w,h,bpp,p)),6
  if n=='GetObjectA':
   obj=self.objects.get(a[0]);
   if not obj or obj[0]!='bitmap':return 0,3
   _,w,h,b,p=obj;data=struct.pack('<iiiiHHI',0,w,h,((w*b+31)//32)*4,1,b,p);u.mem_write(a[2],data[:a[1]]);return min(a[1],len(data)),3
  if n=='LoadBitmapA':return 0,2
  if n=='CreateSolidBrush':return self.handle(('brush',a[0])),1
  if n=='FillRect':
   # Solid fill of a RECT into the DC's surface or DIB; pixel encoding matches SetPixel.
   brush=self.objects.get(a[2],('brush',0))
   if a[0] in self.dd.gl_dcs and brush[0]=='brush':
    self.dd.gl_fill(a[0],*struct.unpack('<iiii',bytes(u.mem_read(a[1],16))),brush[1]);return 1,3
   target=self.target(a[0])
   if target and brush[0]=='brush':
    w,h,b,p=target;l,t,rr,bb=struct.unpack('<iiii',bytes(u.mem_read(a[1],16)));c=brush[1]
    l,t,rr,bb=max(0,l),max(0,t),min(w,rr),min(h,bb)
    px=struct.pack('<H',((c&255)>>3)<<11|(((c>>8)&255)>>2)<<5|((c>>16)&255)>>3) if b==16 else bytes([(c>>16)&255,(c>>8)&255,c&255,0])
    pitch=w*b//8 if a[0] in self.dd.surfaces else ((w*b+31)//32)*4
    for y in range(t,bb):u.mem_write(p+y*pitch+l*(b//8),px*(rr-l))
   return 1,3
  if n=='GetGlyphOutlineA':
   c=a[1];s=bytes([c]) if c<256 else c.to_bytes(2,'big');text=s.decode('gbk',errors='replace');f=self.font(self.dc(a[0]));box=f.getbbox(text);w,h=max(1,box[2]-box[0]),max(1,box[3]-box[1]);stride=((w+31)//32)*4
   u.mem_write(a[3],struct.pack('<IIiihh',w,h,box[0],h,int(f.getlength(text)),0))
   im=Image.new('1',(stride*8,h));ImageDraw.Draw(im).text((-box[0],-box[1]),text,font=f,fill=1);data=im.tobytes()
   if a[4] and a[5]:u.mem_write(a[5],data[:a[4]])
   return len(data),7
  if n in ['SetPixel','GetPixel']:
   target=self.target(a[0]);value=0
   if target:
    w,h,b,p=target;x,y=a[1:3]
    if x<w and y<h:
     p+=(y*w+x)*(b//8)
     if n=='SetPixel':
      c=a[3];value=c;rgb=((c&255)>>3)<<11|(((c>>8)&255)>>2)<<5|((c>>16)&255)>>3
      u.mem_write(p,struct.pack('<H',rgb) if b==16 else bytes([(c>>16)&255,(c>>8)&255,c&255,0]))
     else:
      c=int.from_bytes(u.mem_read(p,b//8),'little');value=(((c>>11)*255//31)|(((c>>5)&63)*255//63)<<8|((c&31)*255//31)<<16) if b==16 else c
   return value,4 if n=='SetPixel' else 3
  if n=='TextOutA':
   dc=self.dc(a[0]);txt=bytes(u.mem_read(a[3],a[4])).decode('gbk',errors='replace');c=dc['fg']
   if a[0] in self.dd.gl_dcs:
    # On the GPU render target, rasterize at display scale so CJK text stays sharp on Retina.
    k=self.dd.scale;mask,mw,mh=self.mask(txt,dc,k);s=self.dd.gl_dcs[a[0]]
    px=((c&255)>>3)<<11|(((c>>8)&255)>>2)<<5|((c>>16)&255)>>3 if s.bpp==2 else (c&255)<<16|(c&0xff00)|(c>>16)&255
    self.dd.gl_text(a[0],a[1],a[2],mask,mw,mh,px,round(mw/k),round(mh/k));return 1,5
   m=self.mask(txt,dc,1)
   target=self.target(a[0])
   if target:
    w,h,b,p=target
    px=((c&255)>>3)<<11|(((c>>8)&255)>>2)<<5|((c>>16)&255)>>3 if b==16 else (c&255)<<16|(c&0xff00)|(c>>16)&255
    pitch=w*b//8 if a[0] in self.dd.surfaces else ((w*b+31)//32)*4
    self.dd.gl_or_none().sw_text(r.host(p),pitch,w,h,b//8,*m,a[1],a[2],px)
   return 1,5
  if n=='BitBlt':
   dst=self.target(a[0]);src=self.target(a[5])
   if not dst or not src:return 0,9
   import ctypes as C
   if not hasattr(self,'pixels2'):self.pixels2=C.CDLL(__import__('paths').lib('libpixels.dylib'))
   dw,dh,db,dp=dst;sw,sh,sb,sp=src;pd=a[0] in self.dd.surfaces;ps=a[5] in self.dd.surfaces
   ds=dw*db//8 if pd else ((dw*db+31)//32)*4;ss=sw*sb//8 if ps else ((sw*sb+31)//32)*4
   d=C.create_string_buffer(bytes(u.mem_read(dp,ds*dh)));b=C.create_string_buffer(bytes(u.mem_read(sp,ss*sh)))
   flip=getattr(self,'bottomup',{}).get(sp,False)
   self.pixels2.pixels_copy(d,dw,dh,db,a[1],a[2],b,sw,sh,sb,a[6],a[7],a[3],a[4],int(flip),int(pd),int(ps))
   u.mem_write(dp,d.raw[:-1]);return 1,9
  raise NotImplementedError(n)
