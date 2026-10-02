"""Build a portable release from tracked runtime/source files; exclude user data."""
import hashlib,re,subprocess,sys,zipfile
from pathlib import Path
root=Path(__file__).resolve().parents[1];version=re.search(r"VERSION = '([^']+)'",(root/'viewer.py').read_text()).group(1)
out=Path(sys.argv[1]).resolve() if len(sys.argv)>1 else root/'dist';out.mkdir(parents=True,exist_ok=True)
paths=subprocess.check_output(['git','ls-files','-z'],cwd=root).decode().split('\0')
# Newly authored source files can be packaged before the local release commit.
paths+=subprocess.check_output(['git','ls-files','--others','--exclude-standard','-z'],cwd=root).decode().split('\0')
paths=sorted({p for p in paths if p and p!='.gitignore' and not p.startswith(('.github/','tests/','scripts/','release-notes/'))})
name=f'Offline-Chat-Viewer-v{version}-Windows.zip';target=out/name
for required in ['viewer.py','library_files.py','START-VIEWER.bat','runtime/python.exe','runtime/python313.zip','web/files.js','web/files.css']:
 if required not in paths:raise ValueError('Missing portable file: '+required)
with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
 for relative in paths:
  if any(p.startswith('.') for p in Path(relative).parts) or '__pycache__' in relative or relative.endswith('.pyc'):raise ValueError('Unexpected private/generated file: '+relative)
  info=zipfile.ZipInfo('offline-chat-viewer/'+relative,(2000,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o644<<16;z.writestr(info,(root/relative).read_bytes())
with zipfile.ZipFile(target) as z:
 if z.testzip():raise ValueError('CRC validation failed')
sha=hashlib.sha256(target.read_bytes()).hexdigest();(out/(name+'.sha256.txt')).write_text(sha+'  '+name+'\n',encoding='ascii')
print(f'{name}: {target.stat().st_size} bytes; SHA256 {sha}')
