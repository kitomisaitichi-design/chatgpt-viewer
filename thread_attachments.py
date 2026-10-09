"""Thread document occurrences share the image resolver's bounded provenance cache."""
import json,mimetypes,re,zipfile,urllib.parse
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
    if suffix in ('.html','.htm'):return 'html'
    if suffix in ('.mp3','.ogg','.oga','.wav','.m4a','.ma4','.aac','.flac'):return 'audio'
    if suffix in ('.mp4','.m4v','.webm','.ogv'):return 'video'
    if suffix in ('.mid','.midi'):return 'midi'
    if suffix=='.pdf':return 'pdf'
    if suffix=='.docx':return 'word'
    if suffix in ('.xlsx','.xls','.csv','.tsv'):return 'sheet'
    if suffix in ('.md','.markdown'):return 'markdown'
    if suffix in ('.txt','.json','.jsonl','.ndjson','.log','.py','.js','.mjs','.cjs','.jsx','.ts','.tsx','.css','.html','.xml','.yaml','.yml','.toml','.sh','.ps1','.svg'):return 'text'
    return 'unsupported'

class ThreadAttachments(ThreadImages):
    extensions=None
    references=staticmethod(message_files)
    markdown_pattern=re.compile(r'!?\[([^\]\n]*)\]\(\s*(<[^>\n]+>|(?:[^\s()]|\([^()\n]*\))+)(?:\s+["\'][^\n]*?["\'])?\s*\)')
    raster_only=False
    def catalog(self,cid,leaf=None):
        base=super().catalog(cid,leaf);links=self.archive.settings().get('attachmentLinks',{})
        result=dict(base,images=[dict(item) for item in base['images']])
        with self.files.lock:
            for item in result['images']:
                selected=links.get(cid+'/'+item['id'])
                file=self.files.entries.get(selected.get('key')) if isinstance(selected,dict) else None
                if file and not file['historical']:
                    item.update(file_key=file['key'],target=file['target'],root=file['root'],expected=selected['size'],local_link=selected,source='Selected local copy')
        return result
    def candidates(self,item):
        names=set()
        for value in [item['name'],*item.get('names',[]),*item['references']]:
            name=Path(urllib.parse.unquote(value).replace('\\','/')).name.strip()
            if name:names.add(name.casefold())
        suffix=Path(item['references'][0]).suffix if item['references'] else ''
        if suffix:
            for label in [item['name'],*item.get('names',[])]:
                if not Path(label).suffix:names.add((label+suffix).casefold())
        rows=[];seen=set()
        with self.files.lock:
            for file in self.files.entries.values():
                aliases={str(file['name']).casefold(),Path(file['relative'] or file['name']).name.casefold()}
                if file['historical'] or not aliases&names:continue
                target=self.files.available_path(file)
                if not target or str(target) in seen:continue
                seen.add(str(target));rows.append(dict(key=file['key'],name=file['name'],size=target.stat().st_size,source=target.parent.name))
                if len(rows)>=12:break
        return rows
    def link(self,cid,attachment,key,leaf=None):
        with self.lock:
            item=next((i for i in self.catalog(cid,leaf)['images'] if i['id']==attachment),None)
            if not item or key not in {f['key'] for f in self.candidates(item)}:raise ValueError('Choose a downloaded copy listed for this attachment.')
            with self.files.lock:
                file=self.files.entries.get(key);path=self.files.available_path(file)
                if not path:raise FileNotFoundError('This local copy is no longer available.')
                stat=path.stat()
            links=dict(self.archive.settings().get('attachmentLinks',{}));links[cid+'/'+attachment]=dict(key=key,size=stat.st_size,modified=stat.st_mtime_ns)
            if len(links)>5000:raise ValueError('Too many saved attachment selections.')
            self.archive.save_settings({'attachmentLinks':links});self.cache.clear()
            return {'linked':True}
    def original(self,cid,attachment,leaf=None):
        selected=self.archive.settings().get('attachmentLinks',{}).get(cid+'/'+attachment)
        if isinstance(selected,dict):
            with self.files.lock:file=self.files.entries.get(selected.get('key'))
            if not file or file['historical']:raise FileNotFoundError('The selected local copy is unavailable. Choose another downloaded copy.')
            path=self.files.available_path(dict(target=file['target'],root=file['root'],size=selected['size']))
            if not path:raise FileNotFoundError('The selected local copy is unavailable. Choose another downloaded copy.')
            if path.stat().st_mtime_ns!=selected['modified']:raise ValueError('The selected local copy changed. Choose it again to review the current version.')
            return path
        return super().file(cid,attachment,leaf)
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
                except (OSError,ValueError) as error:public['available']=False;public['error']=str(error)
            public['local_copy']=bool(item.get('local_link'))
            if not public['available']:public['candidates']=self.candidates(item)
            filename=str(target or item['path'] or public['name'])
            public['kind']=kind(filename);public['size']=stat.st_size if stat else item['expected'];public['modified']=stat.st_mtime_ns if stat else None;public['mime']=mimetypes.guess_type(filename)[0] or 'application/octet-stream'
        result['attachments']=result.pop('images');return result
    def file(self,cid,image_id,leaf=None):
        path=self.original(cid,image_id,leaf)
        if kind(path.name) not in ('audio','video') and path.stat().st_size>64*1024*1024:raise ValueError('Preview limit is 64 MiB. Open the original file instead.')
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
