# input: guest WSOCK32 calls; output: real host BSD sockets; pos: network layer (single-player also runs a local server through it).
import socket, select, struct, errno
WOULDBLOCK=10035;FIONBIO=0x8004667e;FIONREAD=0x4004667f
ARGS={'WSAStartup':2,'WSACleanup':0,'WSAGetLastError':0,'socket':3,'closesocket':1,'bind':3,'connect':3,
 'sendto':6,'recvfrom':6,'send':4,'recv':4,'select':5,'ioctlsocket':3,'setsockopt':5,'getsockname':3,
 'gethostname':2,'gethostbyname':1,'inet_addr':1,'inet_ntoa':1,'htons':1,'ntohs':1,'htonl':1,'ntohl':1}
# Windows option levels/names → BSD ones.
OPTS={(0xffff,4):(socket.SOL_SOCKET,socket.SO_REUSEADDR),(0xffff,0x20):(socket.SOL_SOCKET,socket.SO_BROADCAST),
 (0xffff,0x1001):(socket.SOL_SOCKET,socket.SO_SNDBUF),(0xffff,0x1002):(socket.SOL_SOCKET,socket.SO_RCVBUF),
 (6,1):(socket.IPPROTO_TCP,socket.TCP_NODELAY)}
class Winsock:
 def __init__(self,r):self.r=r;self.socks={};self.next=0x100;self.err=0;self.ntoa=0;self.hostent=0
 def addr(self,p):
  fam,port=struct.unpack('<HH',self.r.u.mem_read(p,4));ip=bytes(self.r.u.mem_read(p+4,4))
  port=socket.ntohs(port);host=socket.inet_ntoa(ip)
  return (host,port)
 def put_addr(self,p,lenp,a):
  if not p:return
  self.r.u.mem_write(p,struct.pack('<H',2)+struct.pack('>H',a[1])+socket.inet_aton(a[0])+bytes(8))
  if lenp:self.r.w32(lenp,16)
 def fail(self,e):
  self.err=WOULDBLOCK if isinstance(e,BlockingIOError) else 10000+(getattr(e,'errno',0) or 0)
  return 0xffffffff
 def fds(self,p):
  if not p:return []
  n=self.r.r32(p);return [self.r.r32(p+4+4*i) for i in range(n)]
 def put_fds(self,p,hs):
  if not p:return
  self.r.w32(p,len(hs))
  for i,h in enumerate(hs):self.r.w32(p+4+4*i,h)
 def call(self,n,a):
  r=self.r;u=r.u;argc=ARGS[n]
  if n=='WSAStartup':
   if a[1]:u.mem_write(a[1],struct.pack('<HH',0x101,0x202)+b'Mac Winsock'.ljust(257,b'\0')+b'\0'*129+struct.pack('<HHI',64,512,0))
   return 0,argc
  if n=='WSACleanup':return 0,argc
  if n=='WSAGetLastError':return self.err,argc
  if n in ('htons','ntohs'):return socket.htons(a[0]&0xffff),argc
  if n in ('htonl','ntohl'):return socket.htonl(a[0]),argc
  if n=='inet_addr':
   try:return struct.unpack('<I',socket.inet_aton(r.string(a[0])))[0],argc
   except OSError:return 0xffffffff,argc
  if n=='inet_ntoa':
   self.ntoa=self.ntoa or r.alloc(16);u.mem_write(self.ntoa,socket.inet_ntoa(struct.pack('<I',a[0])).encode()+b'\0');return self.ntoa,argc
  if n=='gethostname':u.mem_write(a[0],b'localhost\0');return 0,argc
  if n=='gethostbyname':
   # hostent{name,aliases,addrtype:short,length:short,addr_list} with 127.0.0.1 only.
   if not self.hostent:
    b=r.alloc(64);name=b+32;ip=b+44;lst=b+48
    u.mem_write(name,b'localhost\0');u.mem_write(ip,socket.inet_aton('127.0.0.1'));r.w32(lst,ip);r.w32(lst+4,0)
    r.w32(b,name);r.w32(b+4,lst+4);u.mem_write(b+8,struct.pack('<HH',2,4));r.w32(b+12,lst);self.hostent=b
   return self.hostent,argc
  if n=='socket':
   s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM if a[1]==2 else socket.SOCK_STREAM)
   h=self.next;self.next+=4;self.socks[h]=s;print('SOCKET',h,'udp' if a[1]==2 else 'tcp',flush=True);return h,argc
  s=self.socks.get(a[0])
  if n=='closesocket':
   if s:s.close();del self.socks[a[0]]
   return 0,argc
  if s is None and n!='select':self.err=10038;return 0xffffffff,argc
  try:
   if n=='bind':s.bind(self.addr(a[1]));print('BIND',a[0],s.getsockname(),flush=True);return 0,argc
   if n=='connect':
    try:s.connect(self.addr(a[1]))
    except BlockingIOError as e:return self.fail(e),argc
    return 0,argc
   if n=='getsockname':self.put_addr(a[1],a[2],s.getsockname());return 0,argc
   if n=='setsockopt':
    o=OPTS.get((a[1],a[2]))
    if o:s.setsockopt(*o,r.r32(a[3]))
    return 0,argc
   if n=='ioctlsocket':
    if a[1]==FIONBIO:s.setblocking(r.r32(a[2])==0)
    elif a[1]==FIONREAD:
     try:r.w32(a[2],len(s.recv(65536,socket.MSG_PEEK|socket.MSG_DONTWAIT)))
     except OSError:r.w32(a[2],0)
    return 0,argc
   if n in ('sendto','send'):
    b=bytes(u.mem_read(a[1],a[2]))
    return (s.sendto(b,self.addr(a[4])) if n=='sendto' and a[4] else s.send(b)),argc
   if n=='recv':
    b=s.recv(a[2]);u.mem_write(a[1],b);return len(b),argc
   if n=='recvfrom':
    b,src=s.recvfrom(a[2]);u.mem_write(a[1],b);self.put_addr(a[4],a[5],src);return len(b),argc
   if n=='select':
    rs,ws,xs=self.fds(a[1]),self.fds(a[2]),self.fds(a[3])
    t=0 if not a[4] else r.r32(a[4])+r.r32(a[4]+4)/1e6
    m={self.socks[h]:h for h in rs+ws+xs if h in self.socks}
    rr,ww,xx=select.select([k for k,h in m.items() if h in rs],[k for k,h in m.items() if h in ws],[k for k,h in m.items() if h in xs],min(t,0.01))
    self.put_fds(a[1],[m[k] for k in rr]);self.put_fds(a[2],[m[k] for k in ww]);self.put_fds(a[3],[m[k] for k in xx])
    return len(rr)+len(ww)+len(xx),argc
  except OSError as e:return self.fail(e),argc
  raise NotImplementedError(n)
