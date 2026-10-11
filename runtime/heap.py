# input: guest HeapAlloc/HeapFree sizes; output: reusable guest addresses; pos: Win32 heap backing.
class Heap:
 # Power-of-two size classes keep free/reuse O(1); the original game allocates and frees per level.
 def __init__(self,start,end):self.top=start;self.end=end;self.sizes={};self.free={};self.live=0
 def cls(self,n):
  c=16
  while c<n:c<<=1
  return c
 def alloc(self,n):
  c=self.cls(max(n,1));lst=self.free.get(c)
  if lst:p=lst.pop()
  else:
   p=self.top;self.top+=c
   if self.top>self.end:raise MemoryError('guest heap exhausted')
  self.sizes[p]=(n,c);self.live+=c;return p
 def release(self,p):
  e=self.sizes.pop(p,None)
  if not e:return False
  self.free.setdefault(e[1],[]).append(p);self.live-=e[1];return True
 def size(self,p):return self.sizes.get(p,(0,0))[0]
 def capacity(self,p):return self.sizes.get(p,(0,0))[1]
 def resize(self,p,n):
  e=self.sizes.get(p)
  if e and n<=e[1]:self.sizes[p]=(n,e[1]);return p
  return None
 def stats(self):return {'top':hex(self.top),'live_mb':round(self.live/1048576,1)}
