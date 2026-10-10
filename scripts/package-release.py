"""Build a portable release from tracked runtime/source files; exclude user data."""
import hashlib,json,re,subprocess,sys,zipfile
from pathlib import Path
root=Path(__file__).resolve().parents[1];version=re.search(r"VERSION = '([^']+)'",(root/'viewer.py').read_text()).group(1)
out=Path(sys.argv[1]).resolve() if len(sys.argv)>1 else root/'dist';out.mkdir(parents=True,exist_ok=True)
paths=subprocess.check_output(['git','ls-files','-z'],cwd=root).decode().split('\0')
# Newly authored source files can be packaged before the local release commit.
paths+=subprocess.check_output(['git','ls-files','--others','--exclude-standard','-z'],cwd=root).decode().split('\0')
vendors=json.loads((root/'web/vendor/documents/manifest.json').read_text())
for name,digest in vendors['files'].items():
 relative='web/vendor/documents/'+name
 if hashlib.sha256((root/relative).read_bytes()).hexdigest()!=digest:raise ValueError('Missing/changed offline renderer: '+name)
 paths.append(relative)
native=json.loads((root/'integration/native-connection/vendor.json').read_text())
for name,digest in native['files'].items():
 relative='runtime/native/'+name
 if hashlib.sha256((root/relative).read_bytes()).hexdigest()!=digest:raise ValueError('Missing/changed native runtime: '+name)
 paths.append(relative)
helper=json.loads((root/'integration/native-connection/helper.json').read_text())
if hashlib.sha256((root/'runtime/native/NativeConnect.exe').read_bytes()).hexdigest()!=helper['sha256']:raise ValueError('Native helper differs from its manifest')
if hashlib.sha256((root/'integration/native-connection/NativeConnect.cs').read_bytes().replace(b'\r\n',b'\n')).hexdigest()!=helper['source_sha256']:raise ValueError('Native helper source changed without rebuilding')
paths=sorted({p for p in paths if p and p!='.gitignore' and not p.startswith(('.github/','tests/','scripts/','release-notes/'))})
name=f'Offline-Chat-Viewer-v{version}-Windows.zip';target=out/name
for required in ['viewer.py','native_connection.py','runtime/native/NativeConnect.exe','thread_images.py','web/thread-images.js','web/document-cards.js','web/media.css','library_files.py','START-VIEWER.bat','runtime/python.exe','runtime/python313.zip','web/files.js','web/files.css','web/structured-content.js','web/structured-content.css','web/vendor/dagre.min.js','web/vendor/dagre-LICENSE.txt']:
 if required not in paths:raise ValueError('Missing portable file: '+required)
with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
 for relative in paths:
  if any(p.startswith('.') for p in Path(relative).parts) or '__pycache__' in relative or relative.endswith('.pyc'):raise ValueError('Unexpected private/generated file: '+relative)
  info=zipfile.ZipInfo('offline-chat-viewer/'+relative,(2000,1,1,0,0,0));info.create_system=3;info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o644<<16;z.writestr(info,(root/relative).read_bytes())
with zipfile.ZipFile(target) as z:
 if z.testzip():raise ValueError('CRC validation failed')
sha=hashlib.sha256(target.read_bytes()).hexdigest();(out/(name+'.sha256.txt')).write_text(sha+'  '+name+'\n',encoding='ascii')
print(f'{name}: {target.stat().st_size} bytes; SHA256 {sha}')
