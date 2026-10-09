"""Restore project files at repository root, preserving existing Git history."""
from pathlib import Path
import hashlib,json,tarfile,tempfile,shutil
root=Path(__file__).resolve().parent
m=json.loads((root/'WORKSPACE.json').read_text())
updates_path=root/'RUNTIME_FIXES.json'
updates=json.loads(updates_path.read_text()) if updates_path.exists() else {'files':[]}
updated={f['path']:f['after'] for f in updates['files']}
allowed_update_roots={'app','src','tests','infra','scripts','envs'}
allowed_update_files={'.env.example','docker-compose.yml','README.md'}
for f in updates['files']:
 p=Path(f['path'])
 if p.is_absolute() or '..' in p.parts or not p.parts or (p.parts[0] not in allowed_update_roots and str(p) not in allowed_update_files):raise SystemExit('Unsafe update path')
patch=root/'RUNTIME_FIXES.patch'
if updates['files'] and hashlib.sha256(patch.read_bytes()).hexdigest()!=updates['patch_sha256']:raise SystemExit('Runtime patch checksum mismatch')
expected={f['path']:f for f in m['files']}
with tempfile.TemporaryFile() as archive:
 for part in m['parts']:
  p=root/part['name']; data=p.read_bytes()
  if len(data)!=part['bytes'] or hashlib.sha256(data).hexdigest()!=part['sha256']:raise SystemExit('Checksum mismatch: '+part['name'])
  archive.write(data)
 archive.seek(0)
 with tarfile.open(fileobj=archive,mode='r:gz') as t:
  members=t.getmembers()
  if len(members)!=len(expected) or set(x.name for x in members)!=set(expected):raise SystemExit('Inventory mismatch')
  for member in members:
   target=(root/member.name).resolve()
   if not member.isfile() or not target.is_relative_to(root) or '.git' in Path(member.name).parts:raise SystemExit('Unsafe archive path')
   with t.extractfile(member) as src:
    h=hashlib.sha256()
    while b:=src.read(1048576):h.update(b)
   digest=expected[member.name]['sha256']
   if h.hexdigest()!=digest:raise SystemExit('File mismatch: '+member.name)
   if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest() not in {digest,updated.get(member.name)} and member.name not in {'README.md','DAILY.md','PREWORK.md','DAY_OF_WORK.md'}:raise SystemExit('Existing local changes; refusing overwrite: '+member.name)
  for member in members:
   target=root/member.name;target.parent.mkdir(parents=True,exist_ok=True)
   if target.exists():continue
   with t.extractfile(member) as src,target.open('wb') as dst:shutil.copyfileobj(src,dst)
print('Verified workspace:',len(members),'files at repository root. Git history preserved.')

if updates['files']:
 import subprocess
 baseline=[]
 for f in updates['files']:
  target=root/f['path']
  actual=hashlib.sha256(target.read_bytes()).hexdigest() if target.exists() else None
  if actual==f['after']:continue
  elif actual==f['before']:baseline.append(f['path'])
  else:raise SystemExit('Local changes; refusing runtime update: '+f['path'])
 if baseline:
  includes=['--include='+path for path in baseline]
  subprocess.run(['git','apply','--check',*includes,str(patch)],cwd=root,check=True)
  subprocess.run(['git','apply',*includes,str(patch)],cwd=root,check=True)
 for f in updates['files']:
  if hashlib.sha256((root/f['path']).read_bytes()).hexdigest()!=f['after']:raise SystemExit('Updated file checksum mismatch: '+f['path'])
 print('Verified runtime fixes:',len(updates['files']),'files.')
