"""Restore project files at repository root, preserving existing Git history."""
from pathlib import Path
import hashlib,json,tarfile,tempfile,shutil
root=Path(__file__).resolve().parent
m=json.loads((root/'WORKSPACE.json').read_text())
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
   if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest()!=digest and member.name not in {'README.md','DAILY.md','PREWORK.md','DAY_OF_WORK.md'}:raise SystemExit('Existing local changes; refusing overwrite: '+member.name)
  for member in members:
   target=root/member.name;target.parent.mkdir(parents=True,exist_ok=True)
   if target.exists():continue
   with t.extractfile(member) as src,target.open('wb') as dst:shutil.copyfileobj(src,dst)
print('Verified workspace:',len(members),'files at repository root. Git history preserved.')
