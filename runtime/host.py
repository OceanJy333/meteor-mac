# input: native host calls and optional METEOR_SCRIPT test input; output: window services with a responsive AppKit run loop; pos: event adapter.
import ctypes as C,os,json,time
class Host:
 def __init__(self,lib):
  self.lib=lib;self.cf=C.CDLL('/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation')
  self.mode=C.c_void_p.in_dll(self.cf,'kCFRunLoopDefaultMode')
  self.cf.CFRunLoopRunInMode.argtypes=[C.c_void_p,C.c_double,C.c_bool]
  # Scripted input replays [[seconds,'move',x,y],[s,'down'],[s,'up'],[s,'key',vk,0|1]] for unattended verification.
  path=os.environ.get('METEOR_SCRIPT');self.script=json.load(open(path)) if path else None
  self.t0=time.monotonic();self.mouse=[320,240,0];self.keys={};self.queue=[]
 def __getattr__(self,name):return getattr(self.lib,name)
 def advance(self):
  if not self.script:return
  now=time.monotonic()-self.t0
  while self.script and self.script[0][0]<=now:
   e=self.script.pop(0);kind=e[1];print('SCRIPT',e,flush=True)
   if kind=='move':self.mouse[0],self.mouse[1]=e[2],e[3];self.queue.append((0x200,self.mouse[2],e[2]|e[3]<<16))
   elif kind in('down','up'):self.mouse[2]=1 if kind=='down' else 0;self.queue.append((0x201 if kind=='down' else 0x202,self.mouse[2],self.mouse[0]|self.mouse[1]<<16))
   elif kind=='key':self.keys[e[2]]=e[3];self.queue.append((0x100 if e[3] else 0x101,e[2],0))
 def host_pump(self):
  self.lib.host_pump();self.cf.CFRunLoopRunInMode(self.mode,.001,True);self.advance()
 def host_mouse(self,axis):
  if self.script is not None:self.advance();return self.mouse[axis] if axis<3 else self.mouse[axis-3]+self.lib.host_mouse(axis)
  return self.lib.host_mouse(axis)
 def host_key(self,vk):
  if self.script is not None and self.keys.get(vk):return 0x8000
  return self.lib.host_key(vk)
 def host_message(self,values,remove):
  self.advance()
  if self.queue:
   e=self.queue[0]
   for i in range(3):values[i]=e[i]
   if remove:self.queue.pop(0)
   return 1
  return self.lib.host_message(values,remove)
