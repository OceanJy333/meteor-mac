# input: original Meteor.exe; output: original x86 execution with Mac-backed Win32/DirectX; pos: emulator entry.
import struct, time, json, sys, os, pathlib, collections, mmap, ctypes
import pefile
from unicorn import *
from unicorn.x86_const import *
from heap import Heap
from win32 import Win32
REGS=[UC_X86_REG_EAX,UC_X86_REG_EBX,UC_X86_REG_ECX,UC_X86_REG_EDX,UC_X86_REG_ESI,UC_X86_REG_EDI,UC_X86_REG_EBP,UC_X86_REG_ESP,UC_X86_REG_EFLAGS]
import paths
LOGS=paths.LOGS
GUEST_SPAN=0x60000000
STUB_BASE=0x70000000
NATIVE_BASE=0x70080000
FAST_DEV3=(21,22,25,26,28,29,37,38,39,40)
class Runtime:
 def __init__(self):
  LOGS.mkdir(parents=True,exist_ok=True);(LOGS/'runtime.pid').write_text(str(os.getpid()))
  self.game=paths.game();paths.serial();paths.settings();self.u=Uc(UC_ARCH_X86,UC_MODE_32);self.pe=pefile.PE(str(next(p for p in self.game.iterdir() if p.name.lower()=='meteor.exe')))
  # Guest memory is one host mapping, so native helpers read guest pointers as base+address.
  self.mem=mmap.mmap(-1,GUEST_SPAN,flags=mmap.MAP_PRIVATE|mmap.MAP_ANON)
  self.base=ctypes.addressof(ctypes.c_char.from_buffer(self.mem))
  for start,size in [(0,0x10000),(0x400000,0x400000),(0x1000000,0x1000000),(0x10000000,0x50000000)]:
   self.u.mem_map_ptr(start,size,UC_PROT_ALL,self.base+start)
  self.u.mem_write(0x400000,self.pe.get_memory_mapped_image())
  self.u.mem_map(STUB_BASE,0x100000);self.u.mem_write(STUB_BASE,b'\xc3'*0x100000)
  self.heap=Heap(0x10000000,0x60000000)
  self.stubs={};self.names={};self.counts=collections.Counter();self.events=collections.deque(maxlen=200)
  self.callbacks=[];self.pending=None
  self.started=time.monotonic();self.error=None;self.done=False
  self.api=Win32(self)
  for d in self.pe.DIRECTORY_ENTRY_IMPORT:
   for i in d.imports:
    n=i.name.decode() if i.name else d.dll.decode().split('.')[0]+'#'+str(i.ordinal)
    self.w32(i.address,self.stub(n))
  # Minimal TIB at fs:0 for SEH-based CRT code.
  self.w32(0,0xffffffff);self.w32(4,0x2000000);self.w32(8,0x1000000);self.w32(0x18,0)
  self.u.reg_write(UC_X86_REG_ESP,0x1ffff00);self.w32(0x1ffff00,self.stub('ExitProcess'))
  self.u.hook_add(UC_HOOK_CODE,self.hook,begin=STUB_BASE,end=NATIVE_BASE-1)
  from ddraw import load_gl
  self.fast=load_gl();self.natives=0;import unicorn.unicorn_py3.unicorn as ucmod;lib=ucmod.uclib;fn=lambda n:ctypes.cast(getattr(lib,n),ctypes.c_void_p)
  self.fast.fast_install(self.u._uch,self.base,NATIVE_BASE,STUB_BASE+0xfffff,fn('uc_hook_add'),fn('uc_reg_read'),fn('uc_reg_write'))
  self.u.hook_add(UC_HOOK_MEM_INVALID,self.invalid)
  self.verbose='--verbose' in sys.argv
  if os.environ.get('METEOR_BLOCKS'):
   # Debug: which pages run guest code (spots runtime-generated code that defeats Unicorn's TB cache).
   self.fast.fast_blocks.argtypes=[ctypes.c_void_p];self.fast.fast_block_hits.restype=ctypes.c_uint;self.fast.fast_blocks(self.u._uch);self.block_pages=True
  # METEOR_TRACE=0x519400,0x51f7d0 prints each hit with its first stack args (runtime evidence next to REA's static view).
  for t in filter(None,os.environ.get('METEOR_TRACE','').split(',')):
   a=int(t,16);self.u.hook_add(UC_HOOK_CODE,lambda u,addr,size,d:print('TRACE',hex(addr),[hex(x) for x in struct.unpack_from('<5I',self.mem,u.reg_read(UC_X86_REG_ESP))],'eax',hex(u.reg_read(UC_X86_REG_EAX)),flush=True),begin=a,end=a)
 # guest memory helpers
 # Guest RAM below the stub area is the host mmap itself, so plain struct access skips Unicorn's binding layer.
 def w32(self,p,v):
  if p<GUEST_SPAN:struct.pack_into('<I',self.mem,p,v&0xffffffff)
  else:self.u.mem_write(p,struct.pack('<I',v&0xffffffff))
 def r32(self,p):return struct.unpack_from('<I',self.mem,p)[0] if p<GUEST_SPAN else struct.unpack('<I',self.u.mem_read(p,4))[0]
 def host(self,p):return self.base+p
 def string(self,p,enc='gbk'):
  if not p:return ''
  b=bytearray()
  while len(b)<32768:
   c=self.u.mem_read(p+len(b),64);i=c.find(0)
   if i>=0:b+=c[:i];break
   b+=c
  return b.decode(enc,errors='replace')
 def alloc(self,n):return self.heap.alloc(n)
 def blob(self,b):
  p=self.alloc(len(b));self.u.mem_write(p,b);return p
 def stub(self,n):
  if n not in self.names:
   a=STUB_BASE+len(self.names)*16;self.names[n]=a;self.stubs[a]=n
  return self.names[n]
 def native_stub(self,kind,i):
  # Hot Dev3 methods enter fast.c; it jumps to the Python stub of the same name when it cannot finish natively.
  if kind!='Dev3' or i not in FAST_DEV3:return 0
  slot=self.natives;self.natives+=1;self.fast.fast_stub(slot,i,self.stub(f'{kind}:{i}'));return NATIVE_BASE+16*slot
 def update_gate(self):
  d3d=getattr(self,'api',None) and self.api.d3d;rt=self.api.dd.rt if d3d else None
  self.fast.fast_gate(int(not rt or rt.loc!='gl' or d3d.lights_dirty or (d3d.material_dirty and d3d.material is not None)))
 def queue_callbacks(self,calls,final=None):
  # Guest callbacks run after the API returns; a zero return stops enumeration (DDENUMRET_CANCEL).
  self.pending=(list(calls),final)
 def invalid(self,u,access,addr,size,val,data):
  self.error=f'memory fault access={access} addr={addr:#x} eip={u.reg_read(UC_X86_REG_EIP):#x}';return False
 def start_next_callback(self,u):
  ctx,pc,queue,final=self.callbacks[-1]
  fn,args=queue.pop(0);csp=ctx[UC_X86_REG_ESP]-0x400
  self.w32(csp,self.stub('CallbackDone'))
  for i,a in enumerate(args):self.w32(csp+4+4*i,a)
  u.reg_write(UC_X86_REG_ESP,csp);u.reg_write(UC_X86_REG_EIP,fn)
 def hook(self,u,address,size,data):
  n=self.stubs.get(address)
  if n=='CallbackDone':
   ctx,pc,queue,final=self.callbacks[-1]
   if queue and u.reg_read(UC_X86_REG_EAX)!=0:return self.start_next_callback(u)
   self.callbacks.pop()
   for reg,value in ctx.items():u.reg_write(reg,value)
   if final is not None:u.reg_write(UC_X86_REG_EAX,final)
   u.reg_write(UC_X86_REG_EIP,pc);return
  sp=u.reg_read(UC_X86_REG_ESP);ret,*a=struct.unpack_from('<17I',self.mem,sp)
  self.counts[n]+=1
  try:
   result,argc=self.api.call(n,a)
  except Exception as e:
   import traceback;traceback.print_exc()
   self.error=f'{n} at {ret:#x}: {type(e).__name__}: {e}; args={[hex(x) for x in a[:8]]}';u.emu_stop();return
  if self.verbose or self.counts[n]<=2:print(n,[hex(x) for x in a[:argc]],'=>',hex(result&0xffffffff),flush=True)
  self.events.append((n,ret,a[:argc],result))
  u.reg_write(UC_X86_REG_EAX,result&0xffffffff);u.reg_write(UC_X86_REG_ESP,sp+4+argc*4);u.reg_write(UC_X86_REG_EIP,ret)
  if self.pending:
   calls,final=self.pending;self.pending=None
   if calls:
    self.callbacks.append(({reg:u.reg_read(reg) for reg in REGS},ret,calls,final));self.start_next_callback(u)
 def status(self):
  if getattr(self,'block_pages',None):
   hits=collections.Counter({p:self.fast.fast_block_hits(p) for p in range(0x60000)});(LOGS/'blocks.json').write_text(json.dumps([(hex(k<<12),v) for k,v in hits.most_common(60) if v]))
  (LOGS/'live.json').write_text(json.dumps({'seconds':round(time.monotonic()-self.started,1),'counts':self.counts,'heap':self.heap.stats(),'error':self.error},indent=1))
 def run(self):
  pc=0x400000+self.pe.OPTIONAL_HEADER.AddressOfEntryPoint;last=0
  try:
   while not (self.error or self.done):
    self.u.emu_start(pc,0xffffffff);pc=self.u.reg_read(UC_X86_REG_EIP)
    self.api.pump()
    if time.monotonic()-last>2:last=time.monotonic();self.status()
  except UcError as e:self.error=self.error or f'{e} eip={self.u.reg_read(UC_X86_REG_EIP):#x}'
  self.status()
  result={'eip':hex(self.u.reg_read(UC_X86_REG_EIP)),'error':self.error,'done':self.done,'recent':[(n,hex(t),[hex(x) for x in a],hex(v&0xffffffff)) for n,t,a,v in list(self.events)[-40:]]}
  (LOGS/'original-execution.json').write_text(json.dumps(result,indent=1))
  print(json.dumps({k:v for k,v in result.items() if k!='recent'},indent=1),flush=True)
  if self.error:
   for e in result['recent'][-15:]:print('  ',e)
   print('REGISTERS',[hex(self.u.reg_read(r)) for r in REGS])
   sp=self.u.reg_read(UC_X86_REG_ESP);print('STACK',[hex(self.r32(sp+4*k)) for k in range(16)])
   for v in [self.u.reg_read(r) for r in REGS[:7]]:
    o=self.api.dd.com.objs.get(v);print('  reg',hex(v),'com' ,type(o).__name__ if o else None,'heap',self.heap.sizes.get(v))
   import capstone
   pc=self.u.reg_read(UC_X86_REG_EIP)
   try:
    for i in capstone.Cs(capstone.CS_ARCH_X86,capstone.CS_MODE_32).disasm(bytes(self.u.mem_read(pc,24)),pc):print(hex(i.address),i.mnemonic,i.op_str)
   except UcError:pass
if __name__=='__main__':
 import gc
 rt=Runtime();gc.collect();gc.freeze();gc.set_threshold(50000,50,100)  # long-lived boot objects stay out of frame-time GC pauses
 rt.run()
