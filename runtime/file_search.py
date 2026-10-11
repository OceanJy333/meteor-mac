# input: Win32 wildcard searches; output: original directory entries; pos: file enumeration adapter.
import fnmatch,struct

def find(api,n,a):
 r=api.r
 if not hasattr(api,'searches'):api.searches={};api.next_search=90000
 if n=='FindClose':api.searches.pop(a[0],None);return 1,1
 if n=='FindFirstFileA':
  pattern=r.string(a[0]).replace('\\','/');parent,_,name=pattern.rpartition('/');folder=api.root/parent
  matches=sorted([p for p in folder.iterdir() if fnmatch.fnmatchcase(p.name.lower(),('*' if name=='*.*' else name).lower())]) if folder.is_dir() else []
  api.next_search+=1;h=api.next_search;api.searches[h]=iter(matches);dst=a[1]
 else:h=a[0];dst=a[1]
 p=next(api.searches.get(h,iter(())),None)
 if p is None:api.last_error=18;return (0xffffffff if n=='FindFirstFileA' else 0),2
 size=p.stat().st_size;data=bytearray(320);struct.pack_into('<I',data,0,16 if p.is_dir() else 32);struct.pack_into('<II',data,28,size>>32,size&0xffffffff);name=p.name.encode('gbk',errors='replace')[:259];data[44:44+len(name)]=name;r.u.mem_write(dst,bytes(data));return (h if n=='FindFirstFileA' else 1),2
