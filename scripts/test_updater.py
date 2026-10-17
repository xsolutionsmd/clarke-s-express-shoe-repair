"""Isolated Linux fault injection for the real updater. No host/network access."""
import json,os,subprocess,tempfile,sys
from pathlib import Path
BRANCH=sys.argv[sys.argv.index('--branch')+1] if '--branch' in sys.argv else None
PREVIEW=bool(BRANCH)
SLUG='clarke-s-express-shoe-repair'+('-'+BRANCH if BRANCH else '')
NEW='a'*40;OLD='b'*40;IMAGE='ghcr.io/xsolutionsmd/clarke-s-express-shoe-repair@sha256:'+'c'*64
STUB=r'''#!/usr/bin/env python3
import json,os,pathlib,shutil,signal,sys
p=pathlib.Path(os.environ['TEST_CASE']);mode=os.environ['TEST_MODE'];cmd=pathlib.Path(sys.argv[0]).name;a=sys.argv[1:];new='a'*40;old='b'*40;image='ghcr.io/xsolutionsmd/clarke-s-express-shoe-repair@sha256:'+'c'*64
def once(name):
 f=p/name
 if f.exists():return False
 f.touch();return True
if cmd=='git':print((old if mode=='stale' and not once('read') else new)+'\trefs/heads/main')
elif cmd in ('sleep','sync'):pass
elif cmd=='docker':
 if a[:2]==['image','inspect']:
  fmt=a[-1];print(('amd64' if mode=='architecture' else 'arm64') if 'Architecture' in fmt else 'linux' if '.Os' in fmt else new if 'revision' in fmt else 'https://github.com/xsolutionsmd/clarke-s-express-shoe-repair')
 elif a[0]=='inspect':print('unhealthy' if mode=='candidate' else 'healthy')
 elif a[0]=='exec' and 'version.json' in a[-1]:print(json.dumps({'revision':new}))
 elif a[0]=='exec':print('<html>Placeholder</html>')
 elif a[0]=='compose' and 'up' in a:
  env=pathlib.Path(a[a.index('--env-file')+1]);isnew=image in env.read_text();(p/'running').write_text(new if isnew else old)
  if isnew:
   (p/'root/data/record').write_text('new incompatible data')
   if mode in ('replacement','recovery'):sys.exit(1)
   if mode=='term':os.kill(os.getppid(),signal.SIGTERM)
  elif mode=='recovery':sys.exit(1)
 elif a[0]=='compose' and 'rm' in a:(p/'removed').touch()
elif cmd=='curl':
 url=next(x for x in a if x.startswith('http'))
 if 'releases/download' in url:
  body=json.dumps({'revision':new,'image':image if mode!='malformed' else 'wrong'});print('404' if mode=='absent' else '200',end='')
 elif 'version.json' in url:
  running=(p/'running').read_text() if (p/'running').exists() else new
  body=json.dumps({'revision':'bad' if mode=='https' and running==new else running})
 else:body='<html>Clarke placeholder</html>'
 if '-o' in a:pathlib.Path(a[a.index('-o')+1]).write_text(body)
 else:print(body,end='')
elif cmd=='tar':
 if mode=='snapshot' and a[0]=='-cpf':sys.exit(1)
 if mode=='restore' and a[0]=='-xpf':sys.exit(1)
 subprocess=__import__('subprocess');sys.exit(subprocess.run(['/usr/bin/tar']+a).returncode)
elif cmd in ('cp','mv'):
 if len(a)>2:sys.exit(__import__('subprocess').run(['/usr/bin/'+cmd]+a).returncode)
 src,dst=map(pathlib.Path,a)
 if cmd=='cp' and dst.name=='current.json.new' and src.name=='deployment.json' and mode in ('state','restore') and once('fail'):sys.exit(1)
 if cmd=='cp':shutil.copy(src,dst)
 else:shutil.move(src,dst)
 if cmd=='mv' and dst.name=='current.json' and mode=='term_state' and once('term'):os.kill(os.getppid(),signal.SIGTERM)
'''
if PREVIEW:
 IMAGE=IMAGE.replace('clarke-s-express-shoe-repair@','clarke-s-express-shoe-repair-'+BRANCH+'@')
 STUB=STUB.replace('clarke-s-express-shoe-repair@','clarke-s-express-shoe-repair-'+BRANCH+'@').replace('refs/heads/main','refs/heads/'+BRANCH)

def case(mode,first=False):
 with tempfile.TemporaryDirectory() as tmp:
  p=Path(tmp);root=p/'root';state=p/'state';bin=p/'bin'
  for d in (root,state,bin,root/'data'):d.mkdir(parents=True,exist_ok=True)
  (root/'data/record').write_text('original data');(root/'runtime.env').write_text('private config')
  if not first:
   (root/'compose.yaml').write_text('old compose');(root/'release.env').write_text('APP_IMAGE=old-image');(state/'current.json').write_text(json.dumps({'revision':OLD,'image':'old-image'}))
  if mode=='guard':(state/'transaction').write_text('prior failure')
  (p/'template').write_text('new compose');source=(Path(__file__).resolve().parents[1]/('server/'+BRANCH+'/update-release.sh' if PREVIEW else 'server/update-release.sh')).read_text();source=source.replace('root=/opt/'+SLUG,'root='+str(root)).replace('state=/var/lib/'+SLUG+'-deploy','state='+str(state)).replace('/usr/local/share/'+SLUG+'/compose.yaml',str(p/'template')).replace("[[ $EUID == 0 ]] || { echo 'Run the installed updater as root.' >&2; exit 1; }",':');(p/'update.sh').write_text(source)
  (bin/'stub').write_text(STUB);(bin/'stub').chmod(0o755)
  for name in ('git','docker','curl','sleep','sync','tar','cp','mv'):(bin/name).symlink_to(bin/'stub')
  env=dict(os.environ,TEST_CASE=tmp,TEST_MODE=mode,PATH=str(bin)+':'+os.environ['PATH']);r=subprocess.run(['bash',str(p/'update.sh')],env=env,capture_output=True,text=True,timeout=30)
  quiet=mode in ('absent','stale');success=mode=='success';assert (r.returncode==0)==(quiet or success),(mode,r.stdout,r.stderr)
  if success:
   assert json.loads((state/'current.json').read_text())['revision']==NEW
   assert (root/'data/record').read_text()=='new incompatible data'
  elif mode not in ('recovery','restore'):
   assert (root/'data/record').read_text()=='original data',mode
   if not first:assert json.loads((state/'current.json').read_text())['revision']==OLD
   else:assert not (state/'current.json').exists()
  assert (state/'transaction').exists()==(mode in ('guard','recovery','restore')),(mode,r.stderr)
  print('PASS',mode,'first' if first else 'subsequent')
if __name__=='__main__':
 for mode in ('success','absent','stale','malformed','architecture','candidate','replacement','https','snapshot','state','term','term_state','recovery','restore','guard'):case(mode)
 for mode in ('success','replacement','https'):case(mode,True)
