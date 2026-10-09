"""Restore project files at repository root, preserving existing Git history."""
from pathlib import Path
import hashlib,json,tarfile,tempfile,shutil,subprocess
root=Path(__file__).resolve().parent
def canonical_bytes(path):
 data=path.read_bytes()
 return data if b'\0' in data else data.replace(b'\r\n',b'\n')
def file_digest(path):
 return hashlib.sha256(canonical_bytes(path)).hexdigest()
# Checked-in source overlays take priority over the historical archive. Only
# clean regular files in the Git index qualify; uncommitted edits still fail.
tracked={}
result=subprocess.run(['git','ls-files','--stage','-z'],cwd=root,capture_output=True,check=True)
for entry in result.stdout.decode('utf-8').split('\0'):
 if not entry:continue
 metadata,name=entry.split('\t',1)
 mode,oid,stage=metadata.split()
 if stage=='0' and mode in {'100644','100755'}:tracked[name]=oid
def clean_tracked(name):
 path=root/name
 if name not in tracked or not path.is_file() or path.is_symlink():return False
 data=canonical_bytes(path)
 header=('blob '+str(len(data))+'\0').encode()
 return hashlib.sha1(header+data).hexdigest()==tracked[name]
m=json.loads((root/'WORKSPACE.json').read_text())
update_groups=[]
updated={}
previous={}
allowed_update_roots={'app','ai_worker','src','tests','infra','scripts','envs','docs'}
allowed_update_files={'.env.example','docker-compose.yml','README.md','requirements-demo.lock.txt'}
for name in ('RUNTIME_FIXES','CORE_FEATURE_FIXES'):
 updates_path=root/(name+'.json')
 if not updates_path.exists():continue
 updates=json.loads(updates_path.read_text())
 patch=root/(name+'.patch')
 for f in updates['files']:
  p=Path(f['path'])
  if p.is_absolute() or '..' in p.parts or not p.parts or (p.parts[0] not in allowed_update_roots and str(p) not in allowed_update_files and not (p.parts[:2]==('models','registry') and p.suffix=='.json')):raise SystemExit('Unsafe update path')
  if f['path'] in updated:raise SystemExit('Overlapping runtime update path: '+f['path'])
  updated[f['path']]=f['after']
  previous[f['path']]=f.get('previous')
 if updates['files'] and file_digest(patch)!=updates['patch_sha256']:raise SystemExit('Runtime patch checksum mismatch: '+name)
 if updates['files']:patch.write_bytes(canonical_bytes(patch))
 update_groups.append((name,updates,patch))
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
   if target.exists() and file_digest(target) not in {digest,updated.get(member.name),previous.get(member.name)} and not clean_tracked(member.name) and member.name not in {'README.md','DAILY.md','PREWORK.md','DAY_OF_WORK.md'}:raise SystemExit('Existing local changes; refusing overwrite: '+member.name)
  for member in members:
   target=root/member.name;target.parent.mkdir(parents=True,exist_ok=True)
   if target.exists():
    if clean_tracked(member.name):continue
    actual=file_digest(target)
    if actual != previous.get(member.name) or actual == updated.get(member.name):continue
   with t.extractfile(member) as src,target.open('wb') as dst:shutil.copyfileobj(src,dst)
print('Verified workspace:',len(members),'files at repository root. Git history preserved.')

for name,updates,patch in update_groups:
 if not updates['files']:continue
 import subprocess
 baseline=[]
 for f in updates['files']:
  target=root/f['path']
  if clean_tracked(f['path']):continue
  actual=file_digest(target) if target.exists() else None
  if actual==f['after']:continue
  elif actual==f['before']:baseline.append(f['path'])
  else:raise SystemExit('Local changes; refusing runtime update: '+f['path'])
 if baseline:
  includes=['--include='+path for path in baseline]
  subprocess.run(['git','-c','core.autocrlf=false','apply','--check',*includes,str(patch)],cwd=root,check=True)
  subprocess.run(['git','-c','core.autocrlf=false','apply',*includes,str(patch)],cwd=root,check=True)
 for f in updates['files']:
  if not clean_tracked(f['path']) and file_digest(root/f['path'])!=f['after']:raise SystemExit('Updated file checksum mismatch: '+f['path'])
 print('Verified runtime fixes:',name,len(updates['files']),'files.')
