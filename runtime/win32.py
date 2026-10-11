# input: guest Win32 calls; output: host-backed API results; pos: original executable runtime.
import struct,time,pathlib,datetime,paths
class Win32:
 def __init__(self,r):
  self.r=r; self.com_names={}; self.handles={}; self.next_file=100; self.last_error=0; self.cursor_count=0; self.modules={}; self.root=r.game
  from ddraw import DirectDraw
  self.dd=DirectDraw(r)
  from d3d import D3D
  self.d3d=D3D(r)
  from input import Input
  self.input=Input(r);self.host=None;self.sound=None;self.timers={};self.timer_id=0
  from gdi import GDI
  self.gdi=GDI(r,self.dd)
  from opengl import OpenGL
  self.gl=OpenGL(r)
  from window import Window
  self.window_api=Window(r)
  from winsock import Winsock,ARGS as WSOCK
  self.net=Winsock(r);self.wsock=WSOCK
  self.cmd=r.blob(b'"C:\\Meteor\\Meteor.exe"\0'); self.env=r.blob(b'PATH=C:\\Meteor\0TEMP=C:\\Meteor\0\0')
 def resolve(self,s,write=False):
  # Game paths → install dir, with a writable data-dir overlay and Windows-style case-insensitive names.
  rel=s.replace('\\','/').removeprefix('C:/Meteor/');p=self.root/rel
  overlay=paths.DATA/rel
  if overlay.exists() or write:p=overlay
  if write:p.parent.mkdir(parents=True,exist_ok=True)
  if not p.exists():
   matches=[x for x in p.parent.iterdir() if x.name.lower()==p.name.lower()] if p.parent.exists() else []
   if matches:p=matches[0]
  return p
 def audio(self):
  if not self.sound:
   from dsound import DirectSound,WaveOut
   self.sound=DirectSound(self.r,self.dd.com);self.wave=WaveOut(self.r,self.sound)
 def fire_timers(self):
  # winmm timer callbacks run on the main thread at message-pump points; one per pump keeps the callback chain simple.
  now=time.monotonic()
  for tid,t in list(self.timers.items()):
   if now>=t[0] and not self.r.pending:
    t[0]=now+t[1] if t[4] else float('inf')
    if not t[4]:del self.timers[tid]
    self.r.queue_callbacks([(t[2],[tid,0,t[3],0,0])]);return
 def pump(self):
  if self.host:self.host.host_pump()
 def call(self,n,a):
  # Hot path: COM methods dominate (~15k/s in a level), so resolve "Kind:index" once and skip the name chain.
  com=self.com_names.get(n)
  if com:return self.dd.com.call(com[0],com[1],a)
  if com is None and ':' in n:
   kind,_,i=n.partition(':')
   if kind in ('DD','DD4','D3D3','Surf','Surf4','Tex2','Clipper','VP3','Dev3','VB','Light','Mat3','DS','DSB','DS3DL','DS3DB','FG','MC','MS','ME','BA'):
    self.com_names[n]=(kind,int(i));return self.dd.com.call(kind,int(i),a)
  self.com_names[n]=False
  r=self.r;u=r.u
  if n=='PeekMessageA':
   if time.monotonic()-getattr(self,'status_tick',0)>2:self.status_tick=time.monotonic();r.status()
   self.fire_timers()
   # The game's own message loop is where macOS events get serviced; without it the window never reaches the screen.
   if self.host and time.monotonic()-getattr(self,'pump_tick',0)>0.008:self.pump_tick=time.monotonic();self.host.host_pump()
  if n=='lstrcpyA':
   b=bytearray();i=0
   while True:
    c=u.mem_read(a[1]+i,1);b.extend(c);i+=1
    if c==b'\0':break
   u.mem_write(a[0],bytes(b));return a[0],2
  if n in self.wsock:return self.net.call(n,a)
  from window import NAMES
  if n in NAMES:return self.window_api.call(n,a,self)
  if n.startswith(("gl","wgl")) or n=="SwapBuffers":
   # Without a current WGL context (D3D renderer), opengl32 entry points are no-ops on Windows.
   if not getattr(self,'wgl_current',False) and n not in ('wglCreateContext','wglMakeCurrent'):
    from opengl_noop import noop
    return noop(n,a)
   if n=='wglMakeCurrent':self.wgl_current=bool(a[1])
  if n=="ChoosePixelFormat":return 1,2
  if n=="SetPixelFormat":return 1,3
  if n in ['GetDC', 'ReleaseDC', 'CreateDCA', 'CreateCompatibleDC', 'DeleteDC', 'CreateFontA', 'CreateFontIndirectA', 'SelectObject', 'SetTextColor', 'SetBkColor', 'SetBkMode', 'TextOutA', 'DeleteObject', 'LoadBitmapA', 'CreateCompatibleBitmap', 'CreateDIBSection', 'GetObjectA', 'GetGlyphOutlineA', 'SetPixel', 'GetPixel', 'BitBlt', 'CreateSolidBrush', 'FillRect']:return self.gdi.call(n,a)
  if n.startswith(('DirectInputCreate','Input:','Device:')):return self.input.call(n,a,self.host)
  if n in ('DirectDrawCreate','DirectDrawEnumerateA') or n.split(':')[0] in ('DD','DD4','D3D3','Surf','Surf4','Tex2','Clipper','VP3','Dev3','VB','Light','Mat3'):return self.dd.call(n,a)
  if n in ['FindFirstFileA','FindNextFileA','FindClose']:
   from file_search import find
   return find(self,n,a)
  if n=='GetSystemMetrics':return {0:800,1:600,4:24,32:0,33:0}.get(a[0],0),1
  if n=='CreateWindowExA':
   import ctypes
   from host import Host
   if not self.host:
    self.host=Host(ctypes.CDLL(paths.lib('libmeteorhost.dylib')));self.host.host_open(self.dd.w,self.dd.h);self.dd.host=self.host
   print('WINDOW',r.string(a[2]),a[6],a[7],flush=True);self.window=20;return 20,12
  if n in ['ShowWindow','UpdateWindow']:return 1,2 if n=='ShowWindow' else 1
  if n=='CreateFontA':return 500,14
  if n=='CreateFontIndirectA':return 500,1
  if n=='SelectObject':return 500,2
  if n=='SetTextColor':return a[1],2
  if n=='SetBkColor':return a[1],2
  if n=='SetBkMode':return 1,2
  if n=='TextOutA':return 1,5
  if n=='DeleteObject':return 1,1
  if n=='CreateCompatibleDC':return 501,1
  if n=='DeleteDC':return 1,1
  if n=='GetDC':return 501,1
  if n=='ReleaseDC':return 1,2
  if n=='CreateDCA':return 501,4
  if n=='GetGlyphOutlineA':
   u.mem_write(a[3],struct.pack('<IIIIhh',16,16,0,16,16,0))
   if a[4]:u.mem_write(a[5],b'\0'*min(a[4],64))
   return 64,7
  if n=='mciSendCommandA':return 277,4
  if n=='CoInitialize':return 0,1
  if n=='CoUninitialize':return 0,0
  if n=='mciGetErrorStringA':u.mem_write(a[1],b'No CD audio device\0');return 1,3
  if n=='DSOUND#1':
   self.audio()
   r.w32(a[1],self.dd.com.wrap(self.sound,'DS'));return 0,3
  if n=='EnumDisplaySettingsA':
   u.mem_write(a[2]+36,struct.pack('<H',148));r.w32(a[2]+104,16);r.w32(a[2]+108,1600);r.w32(a[2]+112,1200);r.w32(a[2]+120,60);return 1,3
  if n=='CoCreateInstance':
   # CLSID_DirectSound: the music engine streams through a looping DirectSound buffer when this succeeds.
   if r.r32(a[0])==0x47d4d946:
    from dsound import DirectSound
    r.w32(a[4],self.dd.com.wrap(DirectSound(r,self.dd.com),'DS'));return 0,5
   if r.r32(a[0])==0xe436ebb3:
    # CLSID_FilterGraph for mp3 music; answer with the interface asked for (IGraphBuilder).
    from dshow import Graph
    r.w32(a[4],self.dd.com.wrap(Graph(r,self),'FG'));return 0,5
   return 0x80040154,5
  if n=='timeSetEvent':
   self.timer_id+=1;self.timers[self.timer_id]=[time.monotonic()+a[0]/1000,a[0]/1000,a[2],a[3],a[4]&1];return self.timer_id,5
  if n=='timeKillEvent':self.timers.pop(a[0],None);return 0,1
  if n.startswith('waveOut'):
   self.audio()
   return self.wave.call(n,a)
  if n in ['auxGetNumDevs','mixerGetNumDevs']:return 0,0
  if n in ['timeBeginPeriod','timeEndPeriod']:return 0,1
  if n=='timeGetDevCaps':u.mem_write(a[0],struct.pack('<II',1,1000));return 0,2
  if n=='AVIFileInit':return 0,0
  if n=='LoadBitmapA':return 0,2
  if n=='ShowCursor':self.cursor_count+=1 if a[0] else -1;return self.cursor_count,1
  if n=='SetPixel':return a[3],4
  if n=='GetPixel':return 0,3
  if n=='ProbeReturn':r.done=True;u.emu_stop();return 0,0
  if n=='IsProcessorFeaturePresent':return 0,1
  if n=='RegOpenKeyExA':r.w32(a[4],900);return 0,5
  if n=='RegCloseKey':return 0,1
  if n=='RegQueryValueExA':
   key_path=paths.SERIAL
   if r.string(a[1])!='Serial' or not key_path.exists():return 2,6
   from registry import installed_serial
   b=installed_serial(key_path.read_bytes().strip())+b'\0'
   if a[3]:r.w32(a[3],1)
   if a[4]:
    if r.r32(a[5])<len(b):r.w32(a[5],len(b));return 234,6
    u.mem_write(a[4],b)
   r.w32(a[5],len(b));return 0,6
  if n=='GetSystemDefaultLangID':return 0x804,0
  if n=='GetVersion':return 0x0a280105,0
  if n=='GetVersionExA':u.mem_write(a[0]+4,struct.pack('<IIII',5,1,2600,2));return 1,1
  if n=='GetCommandLineA':return self.cmd,0
  if n=='GetModuleHandleA':return 0x400000,1
  if n=='GetStartupInfoA':u.mem_write(a[0],struct.pack('<I',68)+b'\0'*64);return 0,1
  if n in ['GetEnvironmentStrings','GetEnvironmentStringsA']:return self.env,0
  if n=='GetEnvironmentStringsW':return 0,0
  if n in ['FreeEnvironmentStringsW','FreeEnvironmentStringsA']:return 1,1
  if n=='HeapCreate':return 0x1234,3
  if n=='HeapAlloc':
   p=r.alloc(a[2])
   if a[1]&8:u.mem_write(p,b'\0'*a[2])
   return p,3
  if n=='HeapSize':return r.heap.size(a[2]),3
  if n=='HeapReAlloc':
   old=r.heap.size(a[2]);p=r.heap.resize(a[2],a[3])
   if p is None:
    p=r.alloc(a[3]);u.mem_write(p,bytes(u.mem_read(a[2],min(a[3],old))));r.heap.release(a[2])
   if a[1]&8 and a[3]>old:u.mem_write(p+old,b'\0'*(a[3]-old))
   return p,4
  if n=='HeapFree':r.heap.release(a[2]);return 1,3
  if n=='HeapDestroy':return 1,1
  if n=='VirtualAlloc':
   if a[0]:return a[0],4
   p=r.alloc(a[1]);u.mem_write(p,b'\0'*a[1]);return p,4
  if n=='VirtualFree':
   if a[2]&0x8000:r.heap.release(a[0])
   return 1,3
  if n in ['InitializeCriticalSection','DeleteCriticalSection','EnterCriticalSection','LeaveCriticalSection']:return 0,1
  if n in ['GetACP','GetOEMCP']:return 936,0
  if n=='GetCPInfo':u.mem_write(a[1],struct.pack('<I',2)+b'?\0'+b'\x81\xfe'+b'\0'*12);return 1,2
  if n=='GetStdHandle':return a[0],1
  if n=='GetFileType':return (1 if a[0] in self.handles else 2),1
  if n=='SetHandleCount':return a[0],1
  if n=='GetLastError':return self.last_error,0
  if n=='GetEnvironmentVariableA':return 0,3
  if n=='GetModuleFileNameA':
   b=b'C:\\Meteor\\Meteor.exe\0';u.mem_write(a[1],b[:a[2]]);return len(b)-1,3
  if n in ['GetStringTypeW','GetStringTypeA']:
   wide=n.endswith('W');ptr=a[1] if wide else a[2];size=a[2] if wide else a[3];dst=a[3] if wide else a[4]
   if size==0xffffffff:size=1
   text=bytes(u.mem_read(ptr,size*(2 if wide else 1))).decode('utf-16le' if wide else 'gbk',errors='replace')
   def ct(c):
    return (1 if c.isupper() else 0)|(2 if c.islower() else 0)|(4 if c.isdigit() else 0)|(8 if c.isspace() else 0)|(16 if not c.isalnum() and not c.isspace() and ord(c)>31 else 0)|(32 if ord(c)<32 or ord(c)==127 else 0)|(64 if c in ' \t' else 0)|(128 if c in '0123456789abcdefABCDEF' else 0)|(256 if c.isalpha() else 0)
   u.mem_write(dst,b''.join(struct.pack('<H',ct(c)) for c in text));return 1,4 if wide else 5
  if n in ['LCMapStringW','LCMapStringA']:
   wide=n.endswith('W');size=a[3];enc='utf-16le' if wide else 'gbk'
   if size==0xffffffff:size=len(r.string(a[2]))+1
   text=bytes(u.mem_read(a[2],size*(2 if wide else 1))).decode(enc,errors='replace')
   out=(text.upper() if a[1]&0x200 else text.lower() if a[1]&0x100 else text).encode(enc,errors='replace')
   if a[4]:u.mem_write(a[4],out[:a[5]*(2 if wide else 1)])
   return len(out)//(2 if wide else 1),6
  if n=='MultiByteToWideChar':
   b=(r.string(a[2]).encode('gbk',errors='replace')+b'\0') if a[3]==0xffffffff else bytes(u.mem_read(a[2],a[3]))
   out=b.decode('gbk',errors='replace').encode('utf-16le')
   if a[4]:u.mem_write(a[4],out[:a[5]*2])
   return len(out)//2,6
  if n=='WideCharToMultiByte':
   length=a[3]
   if length==0xffffffff:
    length=0
    while bytes(u.mem_read(a[2]+length*2,2))!=b'\0\0':length+=1
    length+=1
   out=bytes(u.mem_read(a[2],length*2)).decode('utf-16le').encode('gbk',errors='replace')
   if a[4]:u.mem_write(a[4],out[:a[5]])
   return len(out),8
  if n in ['GetTickCount','timeGetTime']:return int((time.monotonic()-r.started)*1000),0
  if n in ['QueryPerformanceCounter','QueryPerformanceFrequency']:
   u.mem_write(a[0],struct.pack('<Q',int(time.monotonic()*1e6) if n.endswith('Counter') else 1000000));return 1,1
  if n in ['GetSystemTimeAsFileTime']:u.mem_write(a[0],struct.pack('<Q',int((time.time()+11644473600)*1e7)));return 0,1
  if n=='GetTimeZoneInformation':u.mem_write(a[0],b'\0'*172);return 0,1
  if n in ['GetSystemTime','GetLocalTime']:
   d=datetime.datetime.now();u.mem_write(a[0],struct.pack('<8H',d.year,d.month,d.isoweekday()%7,d.day,d.hour,d.minute,d.second,0));return 0,1
  if n=='GetCurrentProcess':return 0xffffffff,0
  if n in ['ExitProcess','TerminateProcess']:
   r.done=True;u.emu_stop();return 0,1 if n=='ExitProcess' else 2
  if n=='SetUnhandledExceptionFilter':return 0,1
  if n=='Sleep':time.sleep(min(a[0]/1000,0.01));return 0,1
  if n=='OutputDebugStringA':print('GAME:',r.string(a[0]),flush=True);return 0,1
  if n in ['LoadCursorA','LoadIconA']:return 10,2
  if n=='RegisterClassExA':self.wndproc=r.r32(a[0]+8);return 1,1
  if n=='UnregisterClassA':return 1,2
  if n in ['LoadLibraryA','GetProcAddress']:
   if n=='LoadLibraryA':
    s=r.string(a[0]);print('LIBRARY',s);self.modules[0x60000000+len(self.modules)*0x10000]=s;return list(self.modules)[-1],1
   s=r.string(a[1]) if a[1]>0xffff else '#'+str(a[1]);print('DYNAMIC',s);return r.stub(s),2
  if n=='FreeLibrary':return 1,1
  if n=='MessageBoxA':print('MESSAGE:',r.string(a[1]),r.string(a[2]),flush=True);return 1,4
  if n=='CreateFileA':
   s=r.string(a[0]).replace('\\','/');print('FILE:',s,flush=True)
   if s.lower()=='user.cfg' and '--trace' in __import__('sys').argv:
    from unicorn import UC_HOOK_BLOCK
    u.hook_add(UC_HOOK_BLOCK,lambda u,a,s,d:r.blocks.append((a,s)) if a>=0x400000 else None)
   p=self.resolve(s,bool(a[1]&0x40000000))
   try:
    mode='rb' if not a[1]&0x40000000 else ('w+b' if a[4]==2 else 'r+b')
    f=p.open(mode);h=self.next_file;self.next_file+=1;self.handles[h]=f;return h,7
   except OSError:self.last_error=2;return 0xffffffff,7
  if n=='ReadFile':
   b=self.handles[a[0]].read(a[2]);u.mem_write(a[1],b);r.w32(a[3],len(b));return 1,5
  if n=='WriteFile':
   b=bytes(u.mem_read(a[1],a[2]));f=self.handles.get(a[0]);
   if f:f.write(b)
   else:print('STDOUT',b[:500])
   if a[3]:r.w32(a[3],len(b))
   return 1,5
  if n=='SetFilePointer':
   f=self.handles[a[0]];off=a[1] if a[1]<0x80000000 else a[1]-0x100000000
   try:f.seek(off,a[3])
   except OSError:self.last_error=131;return 0xffffffff,4
   return f.tell(),4
  if n=='GetFileSize':return pathlib.Path(self.handles[a[0]].name).stat().st_size,2
  if n=='CloseHandle':
   f=self.handles.pop(a[0],None)
   if f:f.close()
   return 1,1
  if n=='FlushFileBuffers':return 1,1
  if n in ['IsBadReadPtr','IsBadWritePtr']:return 0,2
  raise NotImplementedError(n)
