"""Build-time only: obtain pinned document renderers and verify every shipped byte."""
import hashlib,io,json,sys,tarfile,urllib.request
from pathlib import Path
root=Path(sys.argv[1]).resolve() if len(sys.argv)>1 else Path(__file__).resolve().parents[1]/'web/vendor/documents';manifest=json.loads((root/'manifest.json').read_text())
for archive in manifest['archives']:
 names={n:digest for n,digest in manifest['files'].items() if n.startswith(archive['folder']+'/')}
 if all((root/n).is_file() and hashlib.sha256((root/n).read_bytes()).hexdigest()==digest for n,digest in names.items()):continue
 request=urllib.request.Request(archive['url'],headers={'User-Agent':'Mozilla/5.0'})
 data=urllib.request.urlopen(request,timeout=60).read()
 if hashlib.sha256(data).hexdigest()!=archive['sha256']:raise ValueError('Vendor archive checksum mismatch: '+archive['package'])
 with tarfile.open(fileobj=io.BytesIO(data),mode='r:gz') as tar:
  for name,digest in names.items():
   rel=name.split('/',1)[1]
   if archive['folder']=='xlsx' and rel=='xlsx.full.min.js':rel='dist/'+rel
   member=tar.getmember('package/'+rel)
   if not member.isfile():raise ValueError('Unexpected vendor member: '+name)
   content=tar.extractfile(member).read()
   if hashlib.sha256(content).hexdigest()!=digest:raise ValueError('Vendor file checksum mismatch: '+name)
   target=root/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(content)
print('Offline document renderers verified:',len(manifest['files']),'files')
