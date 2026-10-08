"""Verified staging of public Windows releases. Installation happens before launch."""
import hashlib,json,os,re,shutil,urllib.request,zipfile
from contextlib import nullcontext
from pathlib import Path,PurePosixPath
from atomic_files import atomic_bytes
HOST='https://github.com/kitomisaitichi-design/chatgpt-viewer/releases/download/'
LIMIT=512*1024*1024

def download(url,path,limit):
    if not url.startswith(HOST):raise ValueError('Unexpected update asset source')
    request=urllib.request.Request(url,headers={'User-Agent':'Offline-Chat-Viewer-Updater'})
    with urllib.request.urlopen(request,timeout=30) as response,path.open('wb') as output:
        size=0
        while True:
            chunk=response.read(1024*1024)
            if not chunk:break
            size+=len(chunk)
            if size>limit:raise ValueError('Update download exceeds size limit')
            output.write(chunk)
    return path

def stage_release(archive,release,fetch=download,lock=None):
    tag=release['tag_name']
    if not re.fullmatch(r'v\d+\.\d+\.\d+',tag):raise ValueError('Invalid update tag')
    name=f'Offline-Chat-Viewer-{tag}-Windows.zip';assets={a.get('name'):a for a in release.get('assets',[]) if isinstance(a,dict)}
    for n in (name,name+'.sha256.txt'):
        if n not in assets or assets[n].get('browser_download_url')!=HOST+tag+'/'+n:raise ValueError('Verified Windows update assets are missing')
    root=archive.data_dir/'updates'/tag;root.mkdir(parents=True,exist_ok=True)
    fetch(HOST+tag+'/'+name,root/'release.zip.part',LIMIT);fetch(HOST+tag+'/'+name+'.sha256.txt',root/'checksum.txt',4096)
    expected=(root/'checksum.txt').read_text().split()[0].lower()
    digest=hashlib.sha256((root/'release.zip.part').read_bytes()).hexdigest()
    if not re.fullmatch('[0-9a-f]{64}',expected) or digest!=expected:raise ValueError('Update checksum mismatch')
    entries=[];seen=set();total=0;payload=root/'payload';payload.mkdir(exist_ok=True)
    with zipfile.ZipFile(root/'release.zip.part') as z:
        for info in z.infolist():
            parts=PurePosixPath(info.filename).parts
            if not parts or parts[0]!='offline-chat-viewer' or len(parts)<2:raise ValueError('Unexpected update archive layout')
            relative=PurePosixPath(*parts[1:]).as_posix()
            if '\\' in relative or ':' in relative or any(p in ('..','.') or p.startswith('.') for p in parts[1:]) or parts[1].lower() in ('backups','models') or (info.external_attr>>16)&0o170000==0o120000:raise ValueError('Unsafe update archive path')
            if info.is_dir():continue
            if relative.lower() in seen:raise ValueError('Duplicate update path')
            seen.add(relative.lower());total+=info.file_size
            if total>LIMIT or len(seen)>12000:raise ValueError('Update archive exceeds size limit')
            target=payload/relative;target.parent.mkdir(parents=True,exist_ok=True);data=z.read(info);target.write_bytes(data);entries.append(dict(path=relative,sha256=hashlib.sha256(data).hexdigest()))
    for required in ('viewer.py','START-VIEWER.bat','runtime/python.exe','runtime/python313.zip','web/index.html'):
        if required.lower() not in seen:raise ValueError('Incomplete Windows update')
    if not re.search(r"VERSION = '"+re.escape(tag[1:])+"'",(payload/'viewer.py').read_text(encoding='utf8')):raise ValueError('Update version does not match release')
    with lock if lock is not None else nullcontext():
        if not archive.settings().get('silentUpdates',False):return False
        marker=dict(version=tag[1:],payload=str(payload.resolve()),files=entries,sha256=digest)
        atomic_bytes(archive.data_dir/'pending-update.json',json.dumps(marker).encode(),private=True)
    return True
