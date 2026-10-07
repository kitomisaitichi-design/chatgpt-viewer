"""Thread document occurrences share the image resolver's bounded provenance cache."""
import json,mimetypes,re,zipfile
from pathlib import Path
from thread_images import ThreadImages
from library_files import IMAGE_EXT
from exporter_bridge import saved_path

def message_files(message):
    out=[]
    def visit(value,depth=0):
        if depth>8:return
        if isinstance(value,list):
            for child in value:visit(child,depth+1)
        elif isinstance(value,dict):
            ref=value.get('asset_pointer') or value.get('file_id') or value.get('path') or value.get('url') or value.get('id')
            name=value.get('name') or value.get('filename') or ''
            if ref and (name or value.get('file_id') or value.get('asset_pointer') or value.get('path')):out.append((str(ref),str(name)))
            for key in ('parts','content','attachments','files','image','image_url','images'):
                if key in value:visit(value[key],depth+1)
    visit(message.get('content'));visit((message.get('metadata') or {}).get('attachments'));visit(message.get('attachments'))
    return out

def kind(name):
    suffix=Path(name).suffix.lower()
    if suffix in IMAGE_EXT:return 'image'
    if suffix=='.pdf':return 'pdf'
    if suffix=='.docx':return 'word'
    if suffix in ('.xlsx','.xls','.csv','.tsv'):return 'sheet'
    if suffix in ('.md','.markdown'):return 'markdown'
    if suffix in ('.txt','.json','.log','.py','.js','.ts','.css','.html','.xml','.yaml','.yml','.toml','.sh','.ps1','.svg'):return 'text'
    return 'unsupported'

class ThreadAttachments(ThreadImages):
    extensions=None
    references=staticmethod(message_files)
    markdown_pattern=re.compile(r'!?\[([^\]\n]*)\]\(\s*(<[^>\n]+>|[^\s)]+)(?:\s+["\'][^\n]*?["\'])?\s*\)')
    raster_only=False
    def original(self,cid,attachment,leaf=None):return super().file(cid,attachment,leaf)
    def relative(self,cid,attachment,relative,leaf=None):
        base=self.original(cid,attachment,leaf);target=(base.parent/relative).resolve()
        catalog=self.catalog(cid,leaf)
        linked=next((i for i in catalog['images'] if i['target'] and i['target'].resolve()==target),None)
        # A shared export folder is not ownership proof. Only thread-linked
        # assets and the document's own conventional asset directory qualify.
        owned=[base.parent/(base.stem+suffix) for suffix in ('_files','.assets')]
        if linked:self.original(cid,linked['id'],leaf) # recheck root/symlink/size
        owned_asset=target.is_relative_to(base.parent.resolve()) and any(target.is_relative_to(p.resolve()) for p in owned)
        if not target.is_file() or (not linked and not owned_asset):raise FileNotFoundError('Linked image is unavailable or not associated with this thread.')
        if target.suffix.lower() not in IMAGE_EXT:raise ValueError('Only saved raster images can render inside documents.')
        from thread_images import raster_type
        raster_type(target);return target
    def public(self,cid,leaf=None):
        result=super().public(cid,leaf);catalog=self.catalog(cid,leaf)
        for public,item in zip(result['images'],catalog['images']):
            target=item['target'];stat=None
            if public['available']:
                try:target=self.original(cid,item['id'],leaf);stat=target.stat()
                except (OSError,ValueError):public['available']=False
            filename=str(target or item['path'] or public['name'])
            public['kind']=kind(filename);public['size']=stat.st_size if stat else item['expected'];public['modified']=stat.st_mtime_ns if stat else None;public['mime']=mimetypes.guess_type(filename)[0] or 'application/octet-stream'
        result['attachments']=result.pop('images');return result
    def file(self,cid,image_id,leaf=None):
        path=super().file(cid,image_id,leaf)
        if path.stat().st_size>64*1024*1024:raise ValueError('Preview limit is 64 MiB. Open the original file instead.')
        if path.suffix.lower() in ('.docx','.xlsx'):
            with zipfile.ZipFile(path) as z:
                info=z.infolist()
                if len(info)>20000 or sum(i.file_size for i in info)>256*1024*1024:raise ValueError('Document expands beyond the safe preview limit. Open the original instead.')
        return path

def thread_markdown(archive,cid,leaf=None):
    with archive.connect() as db:
        source=db.execute("SELECT path,title FROM chats WHERE id=? UNION ALL SELECT path,json_extract(metadata,'$.title') AS title FROM manifest_entries WHERE cid=? AND available=1 LIMIT 1",(cid,cid)).fetchone()
        manifests=db.execute('SELECT path,manifest,metadata FROM manifest_entries WHERE cid=?',(cid,)).fetchall()
    if not source:raise FileNotFoundError('Unknown conversation')
    path=Path(source['path']);candidate=path if path.suffix.lower()=='.md' else None
    if not leaf and candidate is None:
        candidates=set()
        for row in manifests:
            if Path(row['path']).resolve()!=path.resolve():continue
            entry=json.loads(row['metadata']);found=saved_path(Path(row['manifest']).parent,entry.get('markdown'))
            if found and found.suffix.lower()=='.md':candidates.add(found.resolve())
        if len(candidates)==1:candidate=candidates.pop()
    if candidate and not leaf:
        if candidate.stat().st_size>64*1024*1024:raise ValueError('Markdown exceeds the 64 MiB clipboard limit.')
        return candidate.read_text(encoding='utf-8-sig'),'original'
    rows=archive.source_reader.rows(cid,path,leaf)
    text='# '+(source['title'] or 'Saved conversation')+'\n\n'+'\n\n'.join('## '+('You' if r['role']=='user' else 'ChatGPT' if r['role']=='assistant' else r['role'].title())+'\n\n'+r['text'] for r in rows if r['visible'])+'\n'
    if len(text.encode())>64*1024*1024:raise ValueError('Markdown exceeds the 64 MiB clipboard limit.')
    return text,'generated'
