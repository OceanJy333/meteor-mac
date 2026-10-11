#!/usr/bin/env python3
# input: REA_BINARY env + a JSON list of [tool, args] REA calls; output: printed results and an appended evidence jsonl; pos: one-shot REA MCP client for porting work.
# Runs its own stdio MCP session so a wedged shared REA/Hopper session does not block analysis.
# Env: REA_BINARY (required), REA_CMD (default "npx -y rea-agents mcp"), REA_EVIDENCE (default rea-evidence.jsonl),
#      HOPPER_LAUNCHER_PATH if Hopper is not in the default location.
import json,os,shlex,subprocess,sys
cmd=shlex.split(os.environ.get('REA_CMD','npx -y rea-agents mcp'))
p=subprocess.Popen(cmd,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True)
seq=0
def request(method,params):
 global seq
 seq+=1;p.stdin.write(json.dumps({'jsonrpc':'2.0','id':seq,'method':method,'params':params})+'\n');p.stdin.flush()
 while True:
  line=p.stdout.readline()
  if not line:raise RuntimeError('REA MCP closed')
  try:r=json.loads(line)
  except ValueError:continue
  if r.get('id')==seq:return r
def call(name,args):
 res=request('tools/call',{'name':name,'arguments':args}).get('result',{})
 d=res.get('structuredContent')
 if d is None:
  t=next((c['text'] for c in res.get('content',[]) if c.get('type')=='text'),'{}')
  try:d=json.loads(t)
  except ValueError:d={'text':t}
 return d
request('initialize',{'protocolVersion':'2024-11-05','capabilities':{},'clientInfo':{'name':'rea-batch','version':'1'}})
p.stdin.write(json.dumps({'jsonrpc':'2.0','method':'notifications/initialized'})+'\n');p.stdin.flush()
print(json.dumps(call('open_binary',{'path':os.environ['REA_BINARY']}))[:200])
log=open(os.environ.get('REA_EVIDENCE','rea-evidence.jsonl'),'a')
try:
 for name,args in json.loads(sys.argv[1]):
  d=call(name,args);log.write(json.dumps({'tool':name,'args':args,'result':d},ensure_ascii=False)+'\n')
  r=d.get('normalized_result',d)
  if isinstance(r,dict) and 'items' in r:
   for it in r['items']:print('=====',it.get('address'));print(it.get('pseudocode') or it.get('error'))
  else:print('=====',name,args);print(r if isinstance(r,str) else json.dumps(r,ensure_ascii=False)[:20000])
finally:
 call('close_binary',{});p.terminate()
