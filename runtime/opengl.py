# input: original OpenGL calls in x86 ABI; output: Mac legacy OpenGL; pos: rendering API adapter.
import ctypes as C,struct
I=C.c_uint;F=C.c_float;D=C.c_double;P=C.c_void_p
class OpenGL:
 def __init__(self,r):
  self.r=r;self.lib=C.CDLL('/System/Library/Frameworks/OpenGL.framework/OpenGL');self.arrays={};self.keep=[];self.frames=0
  self.signatures={
   'glEnable':'i','glDisable':'i','glShadeModel':'i','glEnableClientState':'i','glDisableClientState':'i',
   'glBlendFunc':'ii','glDepthFunc':'i','glAlphaFunc':'if','glTexParameterf':'iif','glTexParameteri':'iii','glPolygonMode':'ii','glDepthMask':'i',
   'glBindTexture':'ii','glMatrixMode':'i','glLoadIdentity':'','glViewport':'iiii','glScissor':'iiii','glClear':'i','glClearColor':'ffff','glClearDepth':'d',
   'glCullFace':'i','glFrontFace':'i','glHint':'ii','glDepthRange':'dd','glPixelStorei':'ii','glTexEnvi':'iii','glTexEnvf':'iif',
   'glPushMatrix':'','glPopMatrix':'','glRotatef':'ffff','glScalef':'fff','glTranslatef':'fff','glOrtho':'dddddd','glFrustum':'dddddd',
   'glBegin':'i','glEnd':'','glVertex3f':'fff','glColor4f':'ffff','glTexCoord2f':'ff','glNormal3f':'fff','glColor3f':'fff',
   'glActiveTextureARB':'i','glClientActiveTextureARB':'i','glMultiTexCoord2fARB':'iff','glPolygonOffset':'ff','glLineWidth':'f','glPointSize':'f',
   'glStencilFunc':'iii','glStencilOp':'iii','glStencilMask':'i','glColorMask':'iiii','glClearStencil':'i','glFogf':'if','glFogi':'ii',
   'glFlush':'','glFinish':'','glDrawBuffer':'i','glReadBuffer':'i','glPushAttrib':'i','glPopAttrib':'','glListBase':'i','glCallList':'i','glNewList':'ii','glEndList':'',
  }
 def has(self,n):return n in self.signatures or n in ['glLockArraysEXT','glUnlockArraysEXT'] or (n.startswith('gl') and hasattr(self.lib,n))
 def function(self,n,args,restype=None):
  fn=getattr(self.lib,n);fn.argtypes=args;fn.restype=restype;return fn
 def ptr(self,p,size):
  if not p:return None
  b=C.create_string_buffer(bytes(self.r.u.mem_read(p,size)));self.keep.append(b);return C.cast(b,P)
 def setup_arrays(self,count):
  sizes={0x1400:1,0x1401:1,0x1402:2,0x1403:2,0x1404:4,0x1405:4,0x1406:4,0x140a:8}
  for n,a in self.arrays.items():
   components,typ,stride,p=a;length=(max(0,count-1)*(stride or components*sizes[typ]))+components*sizes[typ]
   ptr=self.ptr(p,length)
   if n=='glNormalPointer':self.function(n,[I,I,P])(typ,stride,ptr)
   else:self.function(n,[I,I,I,P])(components,typ,stride,ptr)
 def call(self,n,a,host):
  r=self.r;u=r.u;self.keep=[]
  if n=='wglCreateContext':host.host_gl_open();return 1,1
  if n=='wglMakeCurrent':return 1,2
  if n=='wglUseFontBitmapsA':return 0,4
  if n=='wglGetProcAddress':
   name=r.string(a[0]);print('GL extension',name)
   return (r.stub(name) if self.has(name) else 0),1
  if n in ['SwapBuffers','wglSwapLayerBuffers']:
   host.host_gl_swap();self.frames+=1
   if self.frames%30==0:print('ORIGINAL GL FRAMES',self.frames,flush=True)
   return 1,1 if n=='SwapBuffers' else 2
  if n=='glLockArraysEXT':return 0,2
  if n=='glUnlockArraysEXT':return 0,0
  if n in ['glVertexPointer','glTexCoordPointer','glColorPointer','glNormalPointer']:
   self.arrays[n]=([3]+a[:3]) if n=='glNormalPointer' else a[:4];return 0,3 if n=='glNormalPointer' else 4
  if n=='glDrawElements':
   size={0x1401:1,0x1403:2,0x1405:4}[a[2]];b=bytes(u.mem_read(a[3],a[1]*size));mx=max(struct.unpack('<'+{1:'B',2:'H',4:'I'}[size]*a[1],b),default=0)
   self.setup_arrays(mx+1);ptr=self.ptr(a[3],len(b));self.function(n,[I,I,I,P])(a[0],a[1],a[2],ptr);return 0,4
  if n=='glDrawArrays':self.setup_arrays(a[1]+a[2]);self.function(n,[I,I,I])(*a[:3]);return 0,3
  if n in ['glGetIntegerv','glGetFloatv']:
   buf=(C.c_ubyte*256)();self.function(n,[I,P])(a[0],buf);length=64 if a[0] in [0xba6,0xba7,0xba8] else 16 if a[0]==0xba2 else 4;u.mem_write(a[1],bytes(buf)[:length]);return 0,2
  if n=='glGetString':
   b=self.function(n,[I],C.c_char_p)(a[0]);return r.blob((b or b'')+b'\0'),1
  if n=='glGetError':return self.function(n,[],I)(),0
  if n in ['glGenTextures','glDeleteTextures']:
   buf=(I*a[0])()
   if n=='glDeleteTextures':C.memmove(buf,bytes(u.mem_read(a[1],4*a[0])),4*a[0])
   self.function(n,[I,P])(a[0],buf)
   if n=='glGenTextures':u.mem_write(a[1],bytes(buf))
   return 0,2
  if n=='glGenLists':return self.function(n,[I],I)(a[0]),1
  if n in ['glLoadMatrixf','glMultMatrixf','glColor4ubv']:
   self.function(n,[P])(self.ptr(a[0],4 if n=='glColor4ubv' else 64));return 0,1
  if n=='glGetTexParameteriv':
   buf=I();self.function(n,[I,I,P])(a[0],a[1],C.byref(buf));r.w32(a[2],buf.value);return 0,3
  if n in ['glTexImage2D','gluBuild2DMipmaps']:
   if n=='glTexImage2D':w,h,fmt,typ,p=a[3],a[4],a[6],a[7],a[8];argc=9
   else:w,h,fmt,typ,p=a[2],a[3],a[4],a[5],a[6];argc=7
   channels={0x1906:1,0x1909:1,0x190a:2,0x1907:3,0x1908:4,0x80e0:3,0x80e1:4}.get(fmt,4)
   row=((w*channels+3)//4)*4 if typ==0x1401 else w*2
   self.function(n,[I]*(argc-1)+[P],I if n.startswith('glu') else None)(*a[:argc-1],self.ptr(p,row*h));return 0,argc
  if n in self.signatures:
   sig=self.signatures[n];args=[];types=[];off=0
   for t in sig:
    types.append({'i':I,'f':F,'d':D}[t]);slots=2 if t=='d' else 1
    raw=struct.pack('<'+'I'*slots,*a[off:off+slots]);args.append(a[off] if t=='i' else struct.unpack('<'+t,raw)[0]);off+=slots
   self.function(n,types)(*args);return 0,off
  raise NotImplementedError(n)
