"""Bundle the pinned Microsoft SDK DLLs; never package a user's browser profile."""
import hashlib,json,urllib.request,zipfile
from pathlib import Path
root=Path(__file__).resolve().parents[1]
manifest=json.loads((root/'integration/native-connection/vendor.json').read_text())
target=root/'runtime/native';target.mkdir(parents=True,exist_ok=True)
if not all((target/name).is_file() and hashlib.sha256((target/name).read_bytes()).hexdigest()==digest for name,digest in manifest['files'].items()):
    blob=urllib.request.urlopen(manifest['url'],timeout=60).read()
    assert hashlib.sha256(blob).hexdigest()==manifest['sha256'],'Microsoft SDK package checksum differs'
    import io
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        for source,name in manifest['extract'].items():(target/name).write_bytes(z.read(source))
for name,digest in manifest['files'].items():
    assert hashlib.sha256((target/name).read_bytes()).hexdigest()==digest,name
print('Pinned native WebView2 SDK files verified.')
