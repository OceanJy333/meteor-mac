# input: Win32 messages; output: translated Mac window events; pos: message pump adapter.
import ctypes as C,struct
class Window:
 def __init__(self,r):self.r=r;self.initial=[(6,1,0),(28,1,0),(5,0,640|(480<<16))]
 def call(self,n,a,api):
  r=self.r;u=r.u;host=api.host
  if n in ['PeekMessageA','GetMessageA']:
   remove=a[4]&1 if n=='PeekMessageA' else True
   if self.initial:
    event=self.initial[0]
    if remove:self.initial.pop(0)
   else:
    values=(C.c_uint*3)()
    if not host.host_message(values,int(remove)):return 0,5 if n=='PeekMessageA' else 4
    event=list(values)
   u.mem_write(a[0],struct.pack('<7I',20,*event,int((__import__('time').monotonic()-r.started)*1000),host.host_mouse(0)&0xffffffff,host.host_mouse(1)&0xffffffff));return 1,5 if n=='PeekMessageA' else 4
  if n=='TranslateMessage':return 1,1
  if n=='DispatchMessageA':
   hwnd,msg,wp,lp=struct.unpack('<4I',bytes(u.mem_read(a[0],16)))
   r.queue_callbacks([(api.wndproc,[hwnd,msg,wp,lp])]);return 0,1
  if n=='DefWindowProcA':return 0,4
  if n in ['GetForegroundWindow','SetCapture']:return 20,0 if n=='GetForegroundWindow' else 1
  if n=='ReleaseCapture':return 1,0
  if n=='SetCursor':return 10,1
  if n in ['GetKeyState','GetAsyncKeyState']:return host.host_key(a[0]),1
  if n=='GetCursorPos':u.mem_write(a[0],struct.pack('<ii',host.host_mouse(0),host.host_mouse(1)));return 1,1
  if n in ['GetWindowRect','GetClientRect']:u.mem_write(a[1],struct.pack('<4i',0,0,api.dd.w,api.dd.h));return 1,2
  if n in ['ClientToScreen','ScreenToClient']:return 1,2
  if n=='SetRect':
   u.mem_write(a[0],struct.pack('<4I',*a[1:5]));return 1,5
  if n=='SetRectEmpty':u.mem_write(a[0],b'\0'*16);return 1,1
  if n=='SetWindowPos':return 1,7
  if n=='ChangeDisplaySettingsA':return 0,2
  if n=='SetCursorPos':return 1,2
  if n=='BeginPaint':u.mem_write(a[1],b'\0'*64);return 501,2
  if n=='EndPaint':return 1,2
  if n=='RegisterWindowMessageA':return 0xc001,1
  if n=='DestroyWindow':return 1,1
  raise NotImplementedError(n)
NAMES=['PeekMessageA','GetMessageA','TranslateMessage','DispatchMessageA','DefWindowProcA','GetForegroundWindow','SetCapture','ReleaseCapture','SetCursor','GetKeyState','GetAsyncKeyState','GetCursorPos','GetWindowRect','GetClientRect','ClientToScreen','ScreenToClient','SetRect','SetRectEmpty','SetWindowPos','ChangeDisplaySettingsA','SetCursorPos','BeginPaint','EndPaint','RegisterWindowMessageA','DestroyWindow']
