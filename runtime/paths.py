# input: bundled game, METEOR_GAME / METEOR_DATA env or first-run dialogs; output: game dir, writable data dir, runtime dir; pos: the one place that knows where files live.
# Full builds carry game resources beside runtime; saves and settings live in the user data dir.
import os,pathlib,subprocess,json,shutil
RUNTIME=pathlib.Path(__file__).resolve().parent
DATA=pathlib.Path(os.environ.get('METEOR_DATA') or pathlib.Path.home()/'Library/Application Support/MeteorMac')
CONFIG=DATA/'config.json'
SERIAL=DATA/'serial.txt'
LOGS=DATA/'logs'
def lib(name):return str(RUNTIME/name)
def ask(script):
 r=subprocess.run(['osascript','-e',script],capture_output=True,text=True)
 if r.returncode:raise SystemExit('setup cancelled')
 return r.stdout.strip()
def alert(text):subprocess.run(['osascript','-e',f'display alert "流星蝴蝶剑 Mac" message {json.dumps(text)}'])
def find_exe(folder):
 hits=[p for p in folder.rglob('*') if p.name.lower()=='meteor.exe']
 return hits[0].parent if hits else None
def extract(folder):
 # Original CD / installer folder (data1.cab): unpack with unshield into the data dir.
 cab=next((p for p in folder.iterdir() if p.name.lower()=='data1.cab'),None)
 tool=shutil.which('unshield') or next((t for t in ('/opt/homebrew/bin/unshield','/usr/local/bin/unshield') if os.path.exists(t)),None)
 if not cab:return None
 if not tool:alert('这是安装盘目录。请先在终端运行 brew install unshield，再重新打开。');raise SystemExit(1)
 out=DATA/'game';subprocess.run([tool,'-d',str(out),'x',str(cab)],check=True,capture_output=True)
 return find_exe(out)
def game():
 if os.environ.get('METEOR_GAME'):return pathlib.Path(os.environ['METEOR_GAME'])
 bundled=RUNTIME.parent/'game'
 if (bundled/'Meteor.exe').is_file():return bundled
 DATA.mkdir(parents=True,exist_ok=True)
 cfg=json.loads(CONFIG.read_text()) if CONFIG.exists() else {}
 if cfg.get('game') and (pathlib.Path(cfg['game'])/'Meteor.exe').exists():return pathlib.Path(cfg['game'])
 folder=pathlib.Path(ask('POSIX path of (choose folder with prompt "选择你的流星蝴蝶剑目录：装好的游戏目录（含 Meteor.exe）或安装盘目录（含 data1.cab）")'))
 found=find_exe(folder) or extract(folder)
 if not found:alert('没有找到 Meteor.exe 或 data1.cab。');raise SystemExit(1)
 cfg['game']=str(found);CONFIG.write_text(json.dumps(cfg,ensure_ascii=False,indent=1))
 return found
# Without config.ini the original launches config.exe (its Windows settings tool) and quits; the Mac build writes the settings that tool would.
CONFIG_INI='DisplayColor 16\nWidth 640\nHeight 480\nTexQuality 0\nModelQuality 0\nSound 0\n'
# singlerec.ini is the original's single-player record: one 'level N' line per cleared mission. Seeding it opens all nine missions.
SINGLEREC=''.join(f'level {i}\n' for i in range(21))
def settings():
 DATA.mkdir(parents=True,exist_ok=True)
 for name,text in (('config.ini',CONFIG_INI),('singlerec.ini',SINGLEREC)):
  if not (DATA/name).exists():(DATA/name).write_text(text)
# A build may carry a preset key (build.sh SERIAL=...); the source tree never does.
PRESET=RUNTIME/'serial.txt'
def serial():
 if not SERIAL.exists() and PRESET.exists():DATA.mkdir(parents=True,exist_ok=True);SERIAL.write_text(PRESET.read_text().strip())
 if not SERIAL.exists():
  DATA.mkdir(parents=True,exist_ok=True)
  key=ask('text returned of (display dialog "输入你自己的流星蝴蝶剑 CD Key（只保存在本机）" default answer "")')
  SERIAL.write_text(key.strip())
 return SERIAL
