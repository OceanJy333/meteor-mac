# input: guest COM interface pointers; output: Python implementations per interface kind; pos: DirectX object model.
E_NOINTERFACE=0x80004002
# Data1 of the IIDs the original game asks for → our interface kind.
IIDS={
 0x6c14db80:'DD',0xb3a6f3e0:'DD',0x9c59509a:'DD4',
 0x6c14db81:'Surf',0x57805885:'Surf',0xda044e00:'Surf',0x0b2b8630:'Surf4',
 0x3bba0080:'D3D3',0x6aae1ec1:'D3D3',0xbb223240:'D3D3',
 0x2cdcd9e0:'Tex2',0x93281502:'Tex2',
 0x56a868a9:'FG',0x56a868b1:'MC',0x36b73880:'MS',0x56a868c0:'ME',0x56a868b6:'ME',0x56a868b3:'BA',
 0x279afa85:'DSB',0x279afa84:'DS3DL',0x279afa86:'DS3DB',
}
class Com:
 def __init__(self,r):self.r=r;self.objs={};self.vtables={};self.ptrs={};self.kinds={}
 def vtable(self,kind):
  if kind not in self.vtables:
   r=self.r;v=r.alloc(4*64)
   for i in range(64):r.w32(v+4*i,r.native_stub(kind,i) or r.stub(f'{kind}:{i}'))
   self.vtables[kind]=v
  return self.vtables[kind]
 def wrap(self,obj,kind):
  # One guest pointer per (object, interface) so QueryInterface round-trips are stable.
  key=(id(obj),kind)
  if key not in self.ptrs:
   p=self.r.alloc(16);self.r.w32(p,self.vtable(kind));self.objs[p]=obj;self.kinds[p]=kind;self.ptrs[key]=p
   obj.refs=getattr(obj,'refs',0)
  obj.refs+=1
  return self.ptrs[key]
 def ptr(self,obj,kind):return self.ptrs.get((id(obj),kind)) or self.wrap(obj,kind)
 def get(self,p):return self.objs.get(p)
 def query(self,obj,iid_ptr,out):
  guid=bytes(self.r.u.mem_read(iid_ptr,16));d1=int.from_bytes(guid[:4],'little')
  kind=IIDS.get(d1)
  if not kind or not obj.supports(kind):
   print('QI unsupported',type(obj).__name__,guid.hex(),flush=True);self.r.w32(out,0);return E_NOINTERFACE
  self.r.w32(out,self.wrap(obj,kind));return 0
 def call(self,kind,i,a):
  obj=self.objs.get(a[0])
  if obj is None:raise RuntimeError(f'{kind}:{i} on unknown object {a[0]:#x}')
  if i==0:return self.query(obj,a[1],a[2]),3
  if i==1:obj.refs+=1;return obj.refs,1
  if i==2:
   obj.refs=max(0,obj.refs-1)
   if not obj.refs and hasattr(obj,'on_release'):obj.on_release()
   return obj.refs,1
  return obj.method(kind,i,a)
class Obj:
 kinds=()
 def supports(self,kind):return kind in self.kinds
 def method(self,kind,i,a):raise NotImplementedError(f'{kind}:{i} args={[hex(x) for x in a[:8]]}')
