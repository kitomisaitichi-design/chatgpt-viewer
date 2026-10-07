"""Fingerprint-cached image occurrences; never scan directories or read image bytes here."""
import hashlib,re,threading,urllib.parse
from collections import OrderedDict
from pathlib import Path
from library_files import IMAGE_EXT

CODE_SPANS=re.compile(r'(?ms)^ {0,3}(`{3,}|~{3,})[^\n]*\n.*?^ {0,3}\1[ \t]*(?:\n|$)|`[^`\n]+`')
HTML_IMAGE=re.compile(r'<img\b[^>]*\bsrc\s*=\s*([\"\'])(.*?)\1[^>]*>',re.I)

MARKDOWN_IMAGE=re.compile(r'!\[([^\]\n]*)\]\(\s*(<[^>\n]+>|[^\s)]+)(?:\s+["\'][^\n]*?["\'])?\s*\)')

def message_images(message):
    out=[]
    def visit(value,depth=0):
        if depth>8:return
        if isinstance(value,list):
            for child in value:visit(child,depth+1)
        elif isinstance(value,dict):
            kind=str(value.get('content_type') or value.get('type') or '')
            mime=str(value.get('mime_type') or value.get('mime') or '')
            ref=value.get('asset_pointer') or value.get('path') or value.get('url') or value.get('file_id') or value.get('id')
            name=value.get('name') or value.get('filename') or ''
            if ref and ('image' in kind or mime.startswith('image/') or Path(str(name or ref)).suffix.lower() in IMAGE_EXT):out.append((str(ref),str(name or 'Saved image')))
            for key in ('parts','image','image_url','images','attachments','content'):
                if key in value:visit(value[key],depth+1)
    visit(message.get('content'));visit((message.get('metadata') or {}).get('attachments'))
    return out

def raster_type(path):
    # Extension alone must not allow an exported HTML/error response inline.
    with path.open('rb') as stream:head=stream.read(32)
    if head.startswith(b'\x89PNG\r\n\x1a\n'):return 'image/png'
    if head.startswith(b'\xff\xd8\xff'):return 'image/jpeg'
    if head[:6] in (b'GIF87a',b'GIF89a'):return 'image/gif'
    if head.startswith(b'RIFF') and head[8:12]==b'WEBP':return 'image/webp'
    if head.startswith(b'BM'):return 'image/bmp'
    if head[4:8]==b'ftyp' and any(x in head[8:] for x in (b'avif',b'avis')):return 'image/avif'
    raise ValueError('This saved file is not a supported raster image. Download it from Files & Library to inspect it.')

class ThreadImages:
    def __init__(self,archive,files):
        self.archive=archive;self.files=files;self.lock=threading.RLock();self.cache=OrderedDict();self.builds=0
    def catalog(self,cid,leaf=None):
        a=self.archive
        with a.connect() as db:r=db.execute('SELECT path FROM chats WHERE id=? UNION ALL SELECT path FROM manifest_entries WHERE cid=? AND available=1 LIMIT 1',(cid,cid)).fetchone()
        if not r:raise FileNotFoundError('Unknown conversation')
        path=Path(r['path']);entry=a.source_reader.entry(cid,path)
        with self.files.lock:
            self.files.refresh();signature=tuple(self.files.signature or []);files=[dict(f) for f in self.files.entries.values() if cid in f['conversations'] and not f['historical']]
        key=(entry['key'],leaf,signature)
        with self.lock:
            if key in self.cache:self.cache.move_to_end(key);return self.cache[key]
            rows=a.source_reader.rows(cid,path,leaf);raw=entry['raw'] or {};mapping=raw.get('mapping') or {};messages=raw.get('messages') or [];items=[];by_target={}
            aliases={}
            for f in files:
                if Path(f['relative'] or f['name']).suffix.lower() not in IMAGE_EXT:continue
                for alias in {f['id'],f['name'],f['relative'],Path(f['relative'] or f['name']).name}:
                    if alias:aliases.setdefault(str(alias),[]).append(f)
            def add(ref,name,seq,node_id='',file=None):
                ref=urllib.parse.unquote(str(ref)).strip('<>');target=None
                if not file:
                    opaque=re.sub(r'^(?:sediment|file-service)://','',ref)
                    candidates=aliases.get(ref) or aliases.get(opaque) or aliases.get(opaque.rsplit('/',1)[-1]) or []
                    if len(candidates)==1:file=candidates[0]
                if file:target=file['target']
                elif not re.match(r'^(?:[a-z][\w+.-]*:|//)',ref,re.I):
                    try:target=a.asset(cid,ref,indexed=False)
                    except (ValueError,OSError):pass
                if target and target.suffix.lower() not in IMAGE_EXT:return
                identity=str(target) if target else ref
                if identity in by_target:
                    item=by_target[identity]
                    if seq is not None and seq not in item['sequences']:item['sequences'].append(seq)
                    if ref not in item['references']:item['references'].append(ref)
                    return
                ident=hashlib.sha256((cid+'\0'+identity).encode()).hexdigest()[:24]
                item=dict(id=ident,name=(file['name'] if file else name or Path(ref).name),seq=seq,node_id=node_id,sequences=[] if seq is None else [seq],references=[ref],file_key=file['key'] if file else None,path=ref if not file else None,target=target,root=file['root'] if file else None,expected=file.get('size') if file else None,source='Library' if file and 'library' in file['sources'] else 'Chat')
                items.append(item);by_target[identity]=item
            for row in rows:
                if not row['visible']:continue
                node_id=(row.get('extras') or {}).get('node_id','');message=(mapping.get(node_id) or {}).get('message') or (messages[row['seq']] if row['seq']<len(messages) else {})
                for ref,name in (row.get('extras') or {}).get('image_refs',message_images(message)):add(ref,name,row['seq'],node_id)
                text=CODE_SPANS.sub('',row['text'])
                for m in MARKDOWN_IMAGE.finditer(text):add(m[2],m[1],row['seq'],node_id)
                for m in HTML_IMAGE.finditer(text):add(m[2],Path(m[2]).name,row['seq'],node_id)
            # Library entries without a prompt reference are explicitly placed last.
            for f in files:
                if Path(f['relative'] or f['name']).suffix.lower() in IMAGE_EXT:add(f['id'],f['name'],None,file=f)
            result=dict(images=items,last_seq=rows.visible[-1]['seq'] if rows.visible else None,revision=hashlib.sha256(repr(key).encode()).hexdigest()[:20]);self.builds+=1;self.cache[key]=result
            while len(self.cache)>8:self.cache.popitem(last=False)
            return result
    def public(self,cid,leaf=None):
        catalog=self.catalog(cid,leaf);images=[]
        for item in catalog['images']:
            target=item['target']
            if target is None and item['path']:
                try:target=self.archive.asset(cid,item['path'],indexed=False)
                except (ValueError,OSError):pass
            try:available=bool(self.files.available_path(dict(target=target,root=item['root'],size=item['expected']))) if item['root'] else bool(target and target.is_file() and (item['expected'] is None or target.stat().st_size==item['expected']))
            except OSError:available=False
            images.append({k:v for k,v in item.items() if k not in ('target','expected','root')} | {'available':available})
        return dict(images=images,last_seq=catalog['last_seq'],revision=catalog['revision'])
    def file(self,cid,image_id,leaf=None):
        # A thumbnail URL names an already-authorized occurrence. Reuse that
        # bounded snapshot while checking just its bytes/path; exporter writes
        # must not trigger two complete Library rebuilds for every thumbnail.
        with self.lock:
            item=next((i for (source,branch,_),catalog in reversed(self.cache.items()) if source[-1]==cid and branch==leaf for i in catalog['images'] if i['id']==image_id),None)
        if not item:item=next((i for i in self.catalog(cid,leaf)['images'] if i['id']==image_id),None)
        if not item:raise FileNotFoundError('This image has not been saved locally yet.')
        if item['file_key']:
            path=self.files.available_path(dict(target=item['target'],root=item['root'],size=item['expected']))
            if not path:raise FileNotFoundError('This image has not been completely saved locally yet. Retry after the exporter finishes downloading it.')
        else:path=self.archive.asset(cid,item['path'],indexed=False)
        raster_type(path);return path
