#!/usr/bin/env python3
"""Offline Chat Viewer. Python 3.10+, no dependencies for standard operation."""
import argparse, ast, gzip, hashlib, http.cookies, json, mimetypes, os, re, secrets, socket, sqlite3
import sys, threading, time, urllib.parse, webbrowser, subprocess, queue, multiprocessing
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from chat_types import surface_signal, source_surface_hint, source_header, canonical_kind, prefer_signal, free_account
from source_reader import SourceReader, page_rows, native_conversation

APP = Path(__file__).resolve().parent
# Embedded Windows Python ignores PYTHONPATH; activate the app-local packages explicitly.
from setup_semantic import activate as activate_semantic
activate_semantic()
VERSION = '1.0.13'
UUID = re.compile(r'[a-zA-Z0-9_-]{8,160}')
SKIP = {'.git','.svn','node_modules','__pycache__','.viewer-data','.venv','venv',
        'Windows','Program Files','Program Files (x86)','$Recycle.Bin','System Volume Information',
        'AppData','.cache','.npm','.local','exporter-source',
        '.semantic-env','.semantic-packages','.semantic-staging','.semantic-cache','.semantic-old'}
SKIP_LOWER={s.lower() for s in SKIP}|{'attachments','attachment-errors'}
ROLE = re.compile(r'^## (You|User|Assistant|ChatGPT|Tool|System)(?: \(([^)]+)\))?\s*$')
MODEL = 'sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2'
STATIC_MIME = {'.html':'text/html; charset=utf-8','.js':'text/javascript; charset=utf-8',
 '.mjs':'text/javascript; charset=utf-8','.css':'text/css; charset=utf-8','.json':'application/json',
 '.woff2':'font/woff2','.woff':'font/woff','.ttf':'font/ttf','.svg':'image/svg+xml',
 '.png':'image/png','.jpg':'image/jpeg','.jpeg':'image/jpeg','.gif':'image/gif','.webp':'image/webp','.ico':'image/x-icon'}

def static_mime(path):
    # Do not consult Windows file associations for application assets.
    suffix=Path(path).suffix.lower()
    if suffix in STATIC_MIME:return STATIC_MIME[suffix]
    return 'application/octet-stream'


def epoch(x):
    try:
        n=float(x or 0); return n/1000 if n>1e12 else n
    except (ValueError,TypeError):
        try:
            import datetime
            return datetime.datetime.fromisoformat(str(x).replace('Z','+00:00')).timestamp()
        except (ValueError,TypeError): return 0

def content_text(content):
    if isinstance(content,str): return content
    if not isinstance(content,dict): return json.dumps(content,ensure_ascii=False) if content else ''
    parts=content.get('parts')
    if isinstance(parts,list):
        return '\n\n'.join(p if isinstance(p,str) else p.get('text') or
                           ('[Media reference: '+str(p['asset_pointer'])+']' if p.get('asset_pointer') else
                            '```json\n'+json.dumps(p,ensure_ascii=False,indent=2)+'\n```') for p in parts if isinstance(p,(str,dict)))
    return content.get('text') or json.dumps(content,ensure_ascii=False,indent=2)

def active_nodes(data,leaf=None):
    mapping=data.get('mapping') or {}; current=leaf or data.get('current_node')
    if current not in mapping:
        leaves=[k for k,v in mapping.items() if not v.get('children')]
        current=max(leaves,key=lambda k:epoch((mapping[k].get('message') or {}).get('create_time')),default=None)
    seen=set(); nodes=[]
    while current in mapping and current not in seen:
        seen.add(current); node=mapping[current];nodes.append(node);current=node.get('parent')
    return nodes[::-1]

def visible_role(node):
    m=node.get('message') or {};role=(m.get('author') or {}).get('role');c=m.get('content') or {}
    if (m.get('metadata') or {}).get('is_visually_hidden_from_conversation'):return None
    if role=='user':return role
    if role=='assistant' and m.get('channel') in (None,'final') and isinstance(c,dict) and c.get('content_type','text') in ('text','multimodal_text') and content_text(c).strip():return role
    return None

def graph_context(data):
    from collections import defaultdict,deque
    mp=data.get('mapping') or {};children=defaultdict(list)
    for k,n in mp.items():
        if n.get('parent') in mp:children[n['parent']].append(k)
    cache={}
    def versions(mid):
        node=mp[mid];role=visible_role(node)
        if role not in ('user','assistant'):return []
        anchor=node.get('parent');seen={mid};highest=anchor
        while anchor in mp and anchor not in seen:
            seen.add(anchor);v=visible_role(mp[anchor])
            if role=='assistant':
                if v=='user':break
                if v=='assistant':return []
            elif v:break
            highest=anchor;anchor=mp[anchor].get('parent')
        if role=='user' and anchor not in mp:anchor=highest
        if anchor not in mp:return []
        key=(anchor,role)
        if key not in cache:
            queue=deque(children[anchor]);visited={anchor};found=[]
            while queue:
                cur=queue.popleft()
                if cur in visited:continue
                visited.add(cur);v=visible_role(mp[cur])
                if v:
                    if v==role:found.append(cur)
                else:queue.extend(children[cur])
            cache[key]=sorted(found,key=lambda k:epoch((mp[k].get('message') or {}).get('create_time')) or float('inf'))
        return cache[key] if mid in cache[key] and len(cache[key])>1 else []
    return mp,children,versions

def receipt(metadata):
    meta={k:v for k,v in metadata.items() if any(w in k.lower() for w in ('model_slug','effort','reasoning_start_time','reasoning_end_time'))}
    served=meta.get('resolved_model_slug') or meta.get('model_slug')
    picked=meta.get('default_model_slug')
    # Conversation-wide default is not a historical per-turn selection receipt.
    rerouted=bool(served and picked and not re.search(r'(^|[-_])auto($|[-_])',str(picked)) and served!=picked)
    effort=next((v for k,v in meta.items() if 'effort' in k.lower()),None)
    return dict(served=served,picked=picked,rerouted=rerouted,effort=effort,raw=meta)

def source_identity(item):
    return item.get('url') or item.get('file_id') or item.get('title') or ''

def source_links(metadata):
    """Keep saved URL and filename associations; never infer URLs from IDs."""
    found={}
    def refs(value):
        if isinstance(value,str):return [value]
        if isinstance(value,list):return [s for x in value for s in refs(x)]
        if isinstance(value,dict):
            out=[]
            for key in ('ref','ref_id','reference_id','id','citation_id'):out+=refs(value.get(key))
            # ChatGPT web-source pointers identify a turn plus a result slot.
            if isinstance(value.get('turn_index'),int) and isinstance(value.get('ref_index'),int):
                out.append('turn'+str(value['turn_index'])+str(value.get('ref_type') or ('file' if 'file' in str(value.get('type','')) else 'search'))+str(value['ref_index']))
            return out
        return []
    def visit(value,inherited=(),depth=0):
        if depth>12:return
        if isinstance(value,list):
            for item in value:visit(item,inherited,depth+1)
        elif isinstance(value,dict):
            own=[]
            for key in ('ref','ref_id','reference_id','citation_id','citation_uuid','id','refs','citations','reference_ids'):own+=refs(value.get(key))
            own=list(dict.fromkeys(own+list(inherited)+refs(value) if ('turn_index' in value or 'ref_index' in value) else own+list(inherited)))
            url=next((value.get(k) for k in ('url','safe_url','source_url','href','link','cloud_doc_url') if isinstance(value.get(k),str) and value[k].startswith(('https://','http://'))),'')
            is_file='file' in str(value.get('type') or value.get('ref_type') or '').lower() or value.get('category')=='files'
            title=value.get('title') or value.get('name') or value.get('filename') or value.get('file_name')
            if url or is_file and title:
                item=dict(title=str(title or value.get('attribution') or urllib.parse.urlsplit(url).hostname or 'Source'))
                if url:item['url']=url
                if is_file:
                    item['kind']='file'
                    fid=value.get('file_id') or value.get('id')
                    if isinstance(fid,str) and fid.startswith('file_'):item['file_id']=fid
                icon=value.get('favicon_path') or value.get('icon_path')
                if isinstance(icon,str) and not urllib.parse.urlsplit(icon).scheme:item['icon']=icon
                for ref in own:
                    bucket=found.setdefault(ref,[])
                    if not any(source_identity(x)==source_identity(item) for x in bucket):bucket.append(item)
            for key in ('items','sources','citations','references','content_references','source','data','source_links','webpages','grouped_webpages','conversation_context_citation_metadata','citation'):
                if key in value:visit(value[key],own,depth+1)
    visit(metadata)
    return found

def block_presentation(text,role='',content=None,message=None):
    content=content if isinstance(content,dict) else {};message=message or {}
    kind=content.get('content_type');language=content.get('language') or (message.get('metadata') or {}).get('language') or ''
    recipient=message.get('recipient') or '';author=(message.get('author') or {}).get('name') or ''
    if kind=='code':
        if str(language).lower() in ('unknown','text','plain','plaintext','none'):language=''
        return dict(kind='code',language=language or ('python' if 'python' in recipient else block_presentation(text,'assistant').get('language','plaintext')),origin='saved')
    if kind=='execution_output' or role=='tool':
        return dict(kind='output',language='plaintext',label='STDOUT/STDERR' if kind=='execution_output' or 'python' in author else 'Tool output',origin='saved')
    # MD and older indexed rows may have lost the original code content type.
    # Classify valid Python or explicit unfinished function/class declarations.
    # Fence characters can occur inside Python string literals. Let the Python
    # parser distinguish those from actual Markdown code fences; rejecting any
    # occurrence loses code presentation for scripts that generate Markdown.
    if role!='assistant' or len(text)>2000000:return {}
    # Shell tool calls need not contain a heredoc (pipelines are common).
    if re.match(r"^(?:bash|sh|zsh)\s+-(?:lc|c)\s+\S",text.lstrip()):
        return dict(kind='code',language='bash',origin='inferred')
    if text.lstrip().startswith(('{','[')):
        try:
            value=json.loads(text)
            if isinstance(value,(dict,list)):
                return dict(kind='code',language='json',origin='inferred')
        except (ValueError,MemoryError,RecursionError):pass
    candidate=re.sub(r'^python(?:3)?\s+-c\s+', '', text.lstrip(),count=1)
    if not re.search(r'(?m)^(?:import |from |(?:async )?def |class |for |while |with |if |try:|print\(|[a-zA-Z_]\w*\s*=)',candidate):return {}
    try:
        tree=ast.parse(candidate)
    except SyntaxError:
        if re.match(r'^#{1,6}\s+[^\n]+\n\s*\n',candidate):return {}
        # Exported code can end mid-expression. An explicit function/class
        # declaration still identifies it; retain exactly the saved text.
        first=next((line.strip() for line in candidate.splitlines() if line.strip() and not line.lstrip().startswith('#')),'')
        if re.match(r'^(?:async\s+)?def\s+[A-Za-z_]\w*\s*\(|^class\s+[A-Za-z_]\w*(?:\s*\(|\s*:)',first):
            return dict(kind='code',language='python',origin='inferred')
        return {}
    except (ValueError,MemoryError,RecursionError):return {}
    structured=(ast.Import,ast.ImportFrom,ast.Assign,ast.AnnAssign,ast.AugAssign,ast.For,ast.While,ast.With,ast.FunctionDef,ast.ClassDef,ast.If,ast.Try)
    if any(isinstance(n,structured) or isinstance(n,ast.Expr) and isinstance(n.value,ast.Call) for n in tree.body):
        return dict(kind='code',language='python',origin='inferred')
    return {}

def presented_message(message):
    extras=dict(message.get('extras') or {})
    existing=extras.get('presentation') or {}
    if existing.get('kind')=='code' and str(existing.get('language','')).lower() in ('unknown','text','plaintext','none',''):
        inferred=block_presentation(message['text'],'assistant')
        if inferred.get('language'):extras['presentation']={**existing,'language':inferred['language']}
    if not extras.get('presentation'):
        presentation=block_presentation(message['text'],message.get('role',''))
        if presentation:extras['presentation']=presentation
    return dict(message,extras=extras)

def surface_signal(data,models=True):
    from chat_types import surface_signal as classify
    return classify(data,models)

def source_surface_hint(path):
    return surface_signal(source_header(path))

def canonical_kind(value):
    from chat_types import canonical_kind as normalize
    return normalize(value)

def parse_json(data,path,leaf=None):
    if not isinstance(data,dict): return None
    if isinstance(data.get('conversation'),dict): data=data['conversation']
    messages=[]
    if isinstance(data.get('mapping'),dict):
        mp,children,versions=graph_context(data);node_ids={id(n):k for k,n in mp.items()}
        for node in active_nodes(data,leaf):
            m=node.get('message') or {}; role=(m.get('author') or {}).get('role','')
            if not role or (m.get('metadata') or {}).get('is_visually_hidden_from_conversation'): continue
            c=m.get('content') or {}; channel=m.get('channel') or ''
            text=content_text(c); attachments=(m.get('metadata') or {}).get('attachments') or []
            if attachments: text+='\n\n'+'\n'.join('Attachment reference: '+str(a.get('name') or a.get('filename') or a.get('id') or a.get('file_id')) for a in attachments)
            visible=role in ('user','assistant') and channel not in ('analysis','justify','confidence') and c.get('content_type') not in ('thoughts','reasoning_recap','execution_output')
            if role=='assistant' and m.get('recipient') not in (None,'','all'):visible=False
            if not text.strip(): continue
            mid=node.get('id') or node_ids.get(id(node),'')
            extra={'node_id':mid,'receipt':receipt(m.get('metadata') or {}),'versions':versions(mid) if mid else [],'sources':source_links(m.get('metadata') or {}),'presentation':block_presentation(text,role,c,m),'account_free':free_account(data) or free_account(m)}
            messages.append(dict(role=role,channel=channel,text=text,time=epoch(m.get('create_time')),visible=int(visible),extras=extra))
    elif isinstance(data.get('messages'),list):
        for m in data['messages']:
            if not isinstance(m,dict): continue
            role=m.get('role') or (m.get('author') or {}).get('role','assistant')
            text=content_text(m.get('content') or m.get('text') or '')
            if text.strip(): messages.append(dict(role=role,channel=m.get('channel',''),text=text,time=epoch(m.get('create_time')),visible=int(role in ('user','assistant') and m.get('channel') not in ('analysis','justify','confidence')),extras={'receipt':receipt(m.get('metadata') or m),'sources':source_links(m.get('metadata') or m),'presentation':block_presentation(text,role,m.get('content'),m),'account_free':free_account(data) or free_account(m)}))
    else: return None
    cid=str(data.get('conversation_id') or data.get('id') or infer_id(path))
    signal=surface_signal(data)
    # Inspect saved metadata across all branches. A changed default model and
    # inactive Work turns must not silently put a Work chat back into Chat.
    raw_messages=[n.get('message') or {} for n in (data.get('mapping') or {}).values()] if isinstance(data.get('mapping'),dict) else data.get('messages') or []
    for m in raw_messages:
        if isinstance(m,dict):
            turn=dict(m)
            if free_account(data):turn['is_free_account']=True
            signal=prefer_signal(signal,surface_signal(turn))
    kind,evidence=signal or ('chat','No saved Work/Codex product marker')
    return dict(id=cid,title=data.get('title') or path.stem,created=epoch(data.get('create_time')),updated=epoch(data.get('update_time')),kind=kind,kind_evidence=evidence,project=data.get('project') or '',url=data.get('url') or ('' if cid.startswith('local-') else 'https://chatgpt.com/c/'+urllib.parse.quote(cid)),messages=messages)

def infer_id(path):
    m=re.search(r'([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})',path.stem,re.I)
    return m.group(1) if m else 'local-'+hashlib.sha256(str(path.resolve()).encode()).hexdigest()[:24]

def parse_md(text,path):
    lines=text.splitlines(); messages=[]; body=[]; current=None; fence=None
    for line in lines:
        fm=re.match(r'^\s*(`{3,}|~{3,})',line)
        if fm:
            char=fm.group(1)[0]; length=len(fm.group(1))
            if fence is None: fence=(char,length)
            elif char==fence[0] and length>=fence[1]: fence=None
        m=ROLE.match(line) if fence is None else None
        if m:
            if current: current['text']='\n'.join(body).strip(); messages.append(current)
            role={'You':'user','User':'user','Assistant':'assistant','ChatGPT':'assistant','Tool':'tool','System':'system'}[m[1]]
            channel=m[2] or '';current=dict(role=role,channel=channel,time=0,visible=int(role in ('user','assistant') and channel!='analysis'));body=[]
        elif current: body.append(line)
    if current: current['text']='\n'.join(body).strip();messages.append(current)
    if not messages: return None
    for m in messages:
        presentation=block_presentation(m['text'],m['role'])
        if presentation:m.setdefault('extras',{})['presentation']=presentation
        if m['text'].startswith('{"content_type":"thoughts"'): m['visible']=0
    heading=next((l[2:] for l in lines[:15] if l.startswith('# ')),path.stem)
    link=re.search(r'^Conversation:\s*(https?://\S+)',text[:4000],re.M)
    url=link[1] if link else '';
    if not url and not infer_id(path).startswith('local-'):url='https://chatgpt.com/c/'+infer_id(path)
    match=re.search(r'/c/([\w-]+)',url)
    return dict(id=match[1] if match else infer_id(path),title=heading,created=0,updated=path.stat().st_mtime,kind='chat',project='',url=url,messages=messages)

class Archive:
    def __init__(self,data_dir,background_process=True,initialize=True):
        self.data_dir=Path(data_dir);self.data_dir.mkdir(parents=True,exist_ok=True)
        self.dbpath=self.data_dir/'archive.sqlite3';self.lock=threading.RLock(); self.scan_lock=threading.Lock()
        self.branch_cache={};self.revision=0;self.cancel_event=threading.Event();self.request_lock=threading.Lock()
        self.background_process=background_process;self.worker=None;self.reader_pool=None;self.reader_future=None;self.source_link_cache={}
        self.source_reader=SourceReader(parse_json,parse_md)
        self.mp=multiprocessing.get_context('spawn');self.foreground=self.mp.Event();self.foreground_count=0;self.foreground_lock=threading.Lock()
        self.status=dict(scanning=False,phase='Ready',files=0,indexed=0,errors=[],roots=[])
        self.ui_cache=None;self.ui_cache_lock=threading.Lock();self.live_sources={};self.cache_stop=threading.Event();self.cache_thread=None
        self.semantic_lock=threading.Lock(); self.semantic_model=None; self.semantic_state={'ready':False,'building':False,'count':0,'error':''}
        if not initialize:return
        with self.connect() as db:
            db.execute('PRAGMA journal_mode=WAL')
            db.executescript('''
            CREATE TABLE IF NOT EXISTS chats(id TEXT PRIMARY KEY,title TEXT,url TEXT,created REAL,updated REAL,kind TEXT,project TEXT,path TEXT,fingerprint TEXT,count INTEGER,folder TEXT);
            CREATE TABLE IF NOT EXISTS messages(cid TEXT,seq INTEGER,role TEXT,channel TEXT,text TEXT,time REAL,visible INTEGER,PRIMARY KEY(cid,seq));
            CREATE INDEX IF NOT EXISTS msg_visible ON messages(cid,visible,seq);
            CREATE VIRTUAL TABLE IF NOT EXISTS chunks USING fts5(cid UNINDEXED,seq UNINDEXED,title,text,tokenize='porter unicode61',prefix='2 3 4');
            CREATE VIRTUAL TABLE IF NOT EXISTS titles USING fts5(cid UNINDEXED,title,tokenize='porter unicode61',prefix='2 3 4');
            CREATE VIRTUAL TABLE IF NOT EXISTS phrase_vocabulary USING fts5vocab(chunks,'row');
            CREATE TABLE IF NOT EXISTS organization(cid TEXT PRIMARY KEY,category TEXT DEFAULT '',pinned INTEGER DEFAULT 0,position REAL DEFAULT 0,alias TEXT DEFAULT '');
            CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT);
            CREATE TABLE IF NOT EXISTS chunk_rows(cid TEXT,rowid INTEGER,PRIMARY KEY(cid,rowid));
            CREATE TABLE IF NOT EXISTS title_rows(cid TEXT PRIMARY KEY,rowid INTEGER);
            CREATE TABLE IF NOT EXISTS manifest_entries(cid TEXT,manifest TEXT,metadata TEXT,path TEXT,available INTEGER,PRIMARY KEY(cid,manifest));
            CREATE TABLE IF NOT EXISTS scanned_files(path TEXT PRIMARY KEY,fingerprint TEXT,status TEXT);
            CREATE TABLE IF NOT EXISTS vectors(cid TEXT,seq INTEGER,part INTEGER,hash TEXT,vector BLOB,PRIMARY KEY(cid,seq,part));
            ''')
            columns={r['name'] for r in db.execute('PRAGMA table_info(messages)')}
            if 'extras' not in columns:db.execute("ALTER TABLE messages ADD COLUMN extras TEXT DEFAULT '{}'")
            if 'kind_evidence' not in {r['name'] for r in db.execute('PRAGMA table_info(chats)')}:
                db.execute("ALTER TABLE chats ADD COLUMN kind_evidence TEXT DEFAULT ''")
            db.execute("UPDATE chats SET kind='chat' WHERE kind NOT IN ('chat','work','codex') AND lower(kind) NOT LIKE '%work%' AND lower(kind) NOT LIKE '%codex%'")
            db.execute("UPDATE chats SET kind='work' WHERE lower(kind) LIKE '%work%'")
            db.execute("UPDATE chats SET kind='codex' WHERE lower(kind) LIKE '%codex%'")
    @contextmanager
    def connect(self):
        # WAL is configured once at initialization. Reader connections never try to
        # change journal mode while the indexing worker owns a write transaction.
        db=sqlite3.connect(self.dbpath,timeout=5);db.row_factory=sqlite3.Row
        try:
            with db:yield db
        finally:db.close()
    def enable_ui_cache(self):
        # The HTTP status path must never wait on filesystem/database activity.
        self.ui_cache={'chats':{},'settings':self.settings(),'coverage':dict(expected=0,indexed=0,available=0,missing=0,examples=[]),'revision':0,'loading':True}
        def load_existing():
            try:
                chats=self.catalog();coverage=self.coverage()
                with self.ui_cache_lock:
                    for c in chats:
                        if c['id'] not in self.ui_cache['chats']:self.ui_cache['chats'][c['id']]=c
                    self.ui_cache['coverage']=coverage;self.ui_cache['loading']=False;self.ui_cache['revision']+=1
                self.repair_cached_types()
            except Exception as e:
                self.status.setdefault('errors',[]).append('Cached archive read: '+str(e))
                self.ui_cache['loading']=False
        self.cache_thread=threading.Thread(target=load_existing,daemon=True);self.cache_thread.start()
    def repair_cached_types(self):
        # Read saved receipt metadata only, never reparse all conversation bodies.
        signals={}
        with self.connect() as db:
            marker=db.execute("SELECT value FROM settings WHERE key='typeRepairVersion'").fetchone()
            if marker and json.loads(marker['value'])==VERSION:return
            cached=[dict(row) for row in db.execute("SELECT id,kind,path FROM chats WHERE kind!='codex'")]
            free_ids={row['id'] for row in cached if free_account(source_header(row['path']))}
            for row in db.execute("SELECT cid,extras FROM messages WHERE role='assistant' AND (extras LIKE '%-wm%' OR extras LIKE '%luna%' OR extras LIKE '%terra%' OR extras LIKE '%astra%' OR extras LIKE '%sol%')"):
                if self.cache_stop.is_set():return
                extras=json.loads(row['extras']) or {};receipt=extras.get('receipt') or {}
                signal=surface_signal({'model_slug':receipt.get('served'),'default_model_slug':receipt.get('picked'),'is_free_account':extras.get('account_free') or row['cid'] in free_ids})
                if signal:signals[row['cid']]=prefer_signal(signals.get(row['cid']),signal)
            for row in db.execute('SELECT cid,metadata FROM manifest_entries'):
                signal=surface_signal(json.loads(row['metadata']),models=False)
                if signal:signals[row['cid']]=prefer_signal(signals.get(row['cid']),signal)
        for row in cached:
            if self.cache_stop.is_set():return
            signal=source_surface_hint(row['path'])
            if signal:signals[row['id']]=prefer_signal(signals.get(row['id']),signal)
            self.yield_background()
        changed=False
        with self.lock,self.connect() as db:
            for cid,(kind,evidence) in signals.items():
                before=db.total_changes
                db.execute("UPDATE chats SET kind=?,kind_evidence=? WHERE id=? AND kind!='codex' AND (kind!=? OR kind_evidence!=?)",(kind,evidence,cid,kind,evidence))
                changed|=db.total_changes>before
            db.execute("INSERT OR REPLACE INTO settings VALUES('typeRepairVersion',?)",(json.dumps(VERSION),))
        if changed:self.revision+=1
        if self.ui_cache is not None:
            with self.ui_cache_lock:
                for cid,(kind,evidence) in signals.items():
                    c=self.ui_cache['chats'].get(cid)
                    if c and c['kind']!='codex' and (c['kind']!=kind or c.get('kind_evidence')!=evidence):
                        c.update(kind=kind,kind_evidence=evidence);self.ui_cache['revision']+=1

    def announce_source(self,f,root):
        if f.suffix.lower()=='.json':
            header=source_header(f)
            cid=header.get('conversation_id') or header.get('id') or infer_id(f)
            if not header or str(cid).startswith('local-'):return
            old=self.live_sources.get(cid,{})
            signal=prefer_signal(surface_signal(header),(old.get('kind','chat'),old.get('kind_evidence','')) if old.get('kind')!='chat' else None)
            kind,evidence=signal or ('chat','No saved Work/Codex product marker')
            parsed=dict(old,id=cid,title=header.get('title') or old.get('title') or f.stem,url=header.get('url') or old.get('url') or 'https://chatgpt.com/c/'+cid,created=epoch(header.get('create_time')) or old.get('created',0),updated=epoch(header.get('update_time')) or old.get('updated',0),kind=kind,kind_evidence=evidence,project=header.get('project') if isinstance(header.get('project'),str) else old.get('project',''))
        elif f.suffix.lower()=='.md':
            with f.open(encoding='utf-8-sig',errors='replace') as file:head=file.read(8192)
            parsed=parse_md(head,f)
            if parsed and self.live_sources.get(parsed['id'],{}).get('path','').lower().endswith('.json'):return
        else:return
        if not parsed:return
        c={k:v for k,v in parsed.items() if k!='messages'}
        stat=f.stat();c.update(path=str(f),fingerprint=str(stat.st_mtime_ns)+':'+str(stat.st_size),count=0,folder=str(f.parent.relative_to(root)),loaded=False)
        self.live_sources[c['id']]=c
    def publish_sources(self,sources,coverage=None):
        if self.ui_cache is None:return
        with self.ui_cache_lock:
            changed=False
            for c in sources:
                old=self.ui_cache['chats'].get(c['id'],{})
                if old.get('path','').lower().endswith('.json') and c.get('path','').lower().endswith('.md') and Path(old['path']).is_file():continue
                merged={**dict(category='',pinned=0,position=0,alias=''),**old,**c}
                if old.get('loaded') and not c.get('loaded') and old.get('path')==c.get('path') and (not c.get('fingerprint') or old.get('fingerprint')==c.get('fingerprint')):
                    merged.update(loaded=True,count=old.get('count',0),fingerprint=old.get('fingerprint',''))
                if merged!=old:self.ui_cache['chats'][c['id']]=merged;changed=True
            if coverage is not None and coverage!=self.ui_cache['coverage']:self.ui_cache['coverage']=coverage;changed=True
            if changed:self.ui_cache['revision']+=1
    def save_settings_later(self,values):
        if self.ui_cache is not None:
            with self.ui_cache_lock:self.ui_cache['settings'].update(values)
        def persist():
            try:self.save_settings(values)
            except Exception as e:self.status.setdefault('errors',[]).append('Saving settings: '+str(e))
        threading.Thread(target=persist,daemon=True).start()
    def foreground_page(self,cid,*args):
        if self.ui_cache is not None:
            with self.ui_cache_lock:c=self.ui_cache['chats'].get(cid)
            if c and Path(c['path']).is_file() and Path(c['path']).suffix.lower() in ('.md','.json'):
                stat=Path(c['path']).stat()
                if c.get('loaded') and c.get('fingerprint')==str(stat.st_mtime_ns)+':'+str(stat.st_size):return self.page(cid,*args)
                return self.read_source_page(cid,c['path'],*args)
        return self.page(cid,*args)
    def read_source_page(self,cid,path,*args):
        if self.reader_pool is None:
            with self.foreground_lock:
                if self.reader_pool is None:self.reader_pool=ThreadPoolExecutor(max_workers=2,thread_name_prefix='SelectedChatReader')
        with self.foreground_lock:
            future=self.reader_pool.submit(source_page,cid,path,*args,cache=self.source_reader)
        return future.result(timeout=60)
    def linked_sources(self,cid,requested,seq=None,node_id=None):
        d,path=self.source_data(cid)
        if not path:return {}
        exact={}
        if node_id and node_id in (d.get('mapping') or {}):exact=source_links(((d['mapping'][node_id].get('message') or {}).get('metadata') or {}))
        elif seq is not None and isinstance(d.get('messages'),list) and 0<=int(seq)<len(d['messages']):
            message=d['messages'][int(seq)];exact=source_links(message.get('metadata') or message)
        if requested and all(ref in exact for ref in requested[:100]):
            return {ref:exact[ref] for ref in requested[:100]}
        key=(cid,str(path),path.stat().st_mtime_ns)
        if key not in self.source_link_cache:
            links={}
            for node in (d.get('mapping') or {}).values():
                for ref,items in source_links((node.get('message') or {}).get('metadata') or {}).items():
                    bucket=links.setdefault(ref,[])
                    for item in items:
                        if not any(source_identity(x)==source_identity(item) for x in bucket):bucket.append(item)
            for message in d.get('messages') or []:
                for ref,items in source_links(message.get('metadata') or message).items():
                    bucket=links.setdefault(ref,[])
                    for item in items:
                        if not any(source_identity(x)==source_identity(item) for x in bucket):bucket.append(item)
            self.source_link_cache={key:links}
        links=self.source_link_cache[key]
        return {ref:exact.get(ref) or links[ref] for ref in requested[:100] if ref in exact or ref in links and len(links[ref])==1}
    def message_fragment(self,cid,seq,offset=0,leaf=None,budget=24576):
        seq=int(seq);offset=max(0,int(offset))
        budget=max(4096,min(int(budget),131072))
        if leaf:
            d,path=self.source_data(cid)
            rows=self.source_reader.rows(cid,path,leaf) if path else []
            row=next((m for m in rows if m['seq']==seq),None)
        else:
            c=None
            if self.ui_cache is not None:
                with self.ui_cache_lock:c=self.ui_cache['chats'].get(cid)
            fresh=False
            if c and Path(c['path']).is_file():
                st=Path(c['path']).stat();fresh=not c.get('loaded') or c.get('fingerprint')!=f'{st.st_mtime_ns}:{st.st_size}'
            if fresh:
                rows=self.source_reader.rows(cid,c['path']);row=next((m for m in rows if m['seq']==seq),None)
            else:
                with self.connect() as db:row=db.execute('SELECT text FROM messages WHERE cid=? AND seq=?',(cid,seq)).fetchone()
                if row is None:
                    page=self.foreground_page(cid,None,seq,1,True);row=next((m for m in page['messages'] if m['seq']==seq),None)
        if not row:raise ValueError('Saved message not found.')
        text=row['text'];part=bounded_text(text[offset:offset+budget],budget);end=offset+len(part)
        return dict(text=part,next_offset=end,complete=end>=len(text),length=len(text))
    def catalog_batch(self,offset=0,limit=25,priority=''):
        offset=max(0,int(offset));limit=max(1,min(int(limit),25))
        if self.ui_cache is not None:
            with self.ui_cache_lock:
                rows=list(self.ui_cache['chats'].values());revision=self.ui_cache['revision']
        else:rows=self.catalog();revision=self.revision
        # Cache insertion order only grows. Updates keep their original slots,
        # so discovery can continue while offset-based batches are downloaded.
        if priority:
            chosen=next((c for c in rows if c['id']==priority),None)
            if chosen:rows=[chosen]+[c for c in rows if c['id']!=priority]
            else:priority=''
        batch=[];size=0
        for c in rows[offset:offset+limit]:
            n=len(json.dumps(c,ensure_ascii=False,separators=(',',':')).encode())
            if batch and size+n>16*1024:break
            batch.append(c);size+=n
        next_offset=offset+len(batch)
        return dict(chats=batch,revision=revision,offset=offset,nextOffset=next_offset if next_offset<len(rows) else None,total=len(rows),priority=priority)
    def state(self,since=None,limit=None,priority=''):
        if self.ui_cache is not None:
            with self.ui_cache_lock:
                cache=self.ui_cache;revision=cache['revision'];chats=list(cache['chats'].values()) if since is None or str(revision)!=str(since) else None
                coverage=dict(cache['coverage']);coverage['available']=max(coverage['available'],len(cache['chats']));coverage['indexed']=sum(bool(c.get('loaded')) for c in cache['chats'].values())
                result=dict(chats=chats,revision=revision,coverage=coverage,settings=dict(cache['settings']),scan=dict(self.status),semantic=dict(self.semantic_state),cacheLoading=cache['loading'])
        else:
            revision=self.revision
            result=dict(chats=self.catalog() if since is None or str(revision)!=str(since) else None,
                        revision=revision,coverage=self.coverage(),settings=self.settings(),scan=dict(self.status),semantic=dict(self.semantic_state))
        if limit is not None and result['chats'] is not None:
            page=self.catalog_batch(0,limit,priority or result['settings'].get('lastChat',''))
            result['chats']=page.pop('chats');result['catalog']=page;result['revision']=page['revision']
        if limit is not None and since is not None:
            # Reading positions/organization can be large. Polls only need scan settings.
            result['settings']={k:result['settings'][k] for k in ('scan_start','scan_up','scanPaused') if k in result['settings']}
        return result
    def request_scan(self,start,up=2):
        # A new request cancels the old producer and queued work, rather than being dropped.
        with self.request_lock:
            self.cancel_event.set();event=threading.Event();self.cancel_event=event
            self.save_settings_later({'scan_start':str(Path(start).expanduser().resolve()),'scan_up':int(up),'scanPaused':False}) if self.ui_cache is not None else self.save_settings({'scan_start':str(Path(start).expanduser().resolve()),'scan_up':int(up),'scanPaused':False})
            self.status.update(scanning=True,phase='Starting background discovery')
            threading.Thread(target=self.process_scan if self.background_process else self.scan,args=(start,up,event),daemon=True).start()
    def process_scan(self,start,up,event):
        with self.scan_lock:
            if event.is_set():return
            updates=self.mp.Queue(maxsize=4);cancel=self.mp.Event()
            worker=self.mp.Process(target=scan_worker,args=(str(self.data_dir),str(start),up,updates,cancel,self.foreground),daemon=True)
            self.worker=worker;last_revision=0
            try:
                worker.start()
                while worker.is_alive():
                    if event.is_set():
                        cancel.set();worker.join(timeout=.3)
                        if worker.is_alive():worker.terminate()
                        worker.join(timeout=2);break
                    try:
                        status,revision,sources,coverage=updates.get(timeout=.1)
                        self.publish_sources(sources,coverage)
                        self.status=status
                        if revision!=last_revision:self.revision+=1;last_revision=revision;self.semantic_state['ready']=False
                    except queue.Empty:pass
                if not event.is_set():
                    while True:
                        try:
                            status,revision,sources,coverage=updates.get_nowait();self.status=status;self.publish_sources(sources,coverage)
                            if revision!=last_revision:self.revision+=1;last_revision=revision;self.semantic_state['ready']=False
                        except queue.Empty:break
                    if worker.exitcode not in (None,0):self.status.update(phase='Background scan failed · see console',scanning=False)
                else:self.status.update(phase='Scan stopped · cached chats remain available',scanning=False)
            except Exception as e:self.status.update(phase='Background scan failed',scanning=False,errors=[str(e)])
            finally:
                self.status['scanning']=False;self.worker=None;updates.close()
    @contextmanager
    def foreground_read(self):
        with self.foreground_lock:self.foreground_count+=1;self.foreground.set()
        try:yield
        finally:
            with self.foreground_lock:
                self.foreground_count-=1
                if not self.foreground_count:self.foreground.clear()
    def yield_background(self):
        while self.foreground.is_set() and not self.cancel_event.is_set():time.sleep(.01)
    def close(self):
        self.cancel_event.set();self.cache_stop.set()
        if self.worker and self.worker.is_alive():self.worker.terminate();self.worker.join(timeout=2)
        if self.reader_pool:self.reader_pool.shutdown(wait=False,cancel_futures=True)
        self.source_reader.clear()
        if self.cache_thread and self.cache_thread.is_alive():self.cache_thread.join(timeout=5)
    def stop_scan(self):
        self.cancel_event.set();self.save_settings_later({'scanPaused':True}) if self.ui_cache is not None else self.save_settings({'scanPaused':True})
        if self.status.get('scanning'):self.status['phase']='Stopping background scan'
    def settings(self):
        with self.connect() as db:return {r['key']:json.loads(r['value']) for r in db.execute('SELECT * FROM settings')}
    def save_settings(self,values):
        if self.ui_cache is not None:
            with self.ui_cache_lock:self.ui_cache['settings'].update(values)
        with self.lock,self.connect() as db:
            for k,v in values.items():db.execute('INSERT OR REPLACE INTO settings VALUES(?,?)',(k,json.dumps(v)))
    def catalog(self):
        with self.connect() as db:
            ready=[dict(dict(r),loaded=True) for r in db.execute("SELECT c.*,COALESCE(o.category,'') category,COALESCE(o.pinned,0) pinned,COALESCE(o.position,0) position,COALESCE(o.alias,'') alias FROM chats c LEFT JOIN organization o ON c.id=o.cid")]
            ids={r['id'] for r in ready};organization={r['cid']:dict(r) for r in db.execute('SELECT * FROM organization')}
            for r in db.execute('SELECT * FROM manifest_entries WHERE available=1'):
                if r['cid'] in ids:continue
                m=json.loads(r['metadata']);ids.add(r['cid'])
                ready.append(dict(id=r['cid'],title=m.get('title') or Path(r['path']).stem,url=m.get('url') or 'https://chatgpt.com/c/'+r['cid'],
                    created=epoch(m.get('create_time')),updated=epoch(m.get('update_time')),kind=(surface_signal(m) or (canonical_kind(m.get('chat_kind') or m.get('chatKind')),))[0],kind_evidence=m.get('kind_evidence') or (surface_signal(m) or ('','No saved Work/Codex product marker'))[1],
                    project=m.get('project') if isinstance(m.get('project'),str) else '',path=r['path'],fingerprint='',count=0,folder=str(Path(r['path']).parent),
                    category='',pinned=0,position=0,alias='',loaded=False))
                ready[-1].update({k:organization.get(r['cid'],{}).get(k,ready[-1][k]) for k in ('category','pinned','position','alias')})
            return ready
    def coverage(self):
        with self.connect() as db:
            expected={r[0] for r in db.execute('SELECT DISTINCT cid FROM manifest_entries')}
            ready={r[0] for r in db.execute('SELECT id FROM chats')}
            available={r[0] for r in db.execute('SELECT DISTINCT cid FROM manifest_entries WHERE available=1')}
            missing=expected-ready-available
            examples=[dict(id=r['cid'],title=json.loads(r['metadata']).get('title') or r['cid']) for r in db.execute('SELECT cid,metadata FROM manifest_entries') if r['cid'] in missing][:8]
            return dict(expected=len(expected),indexed=len(ready),available=len(ready|available),missing=len(missing),examples=examples)
    def register_manifest(self,entry,manifest,root):
        cid=entry['id'];path='';available=False
        for key in ('json','markdown'):
            value=entry.get(key)
            if isinstance(value,str) and value:
                candidate=(manifest.parent/value).resolve()
                if candidate.is_relative_to(root) and candidate.is_file():path=str(candidate);available=True;break
        signal=prefer_signal(surface_signal(entry),source_surface_hint(path) if available else None)
        if signal:entry={**entry,'chat_kind':signal[0],'kind_evidence':signal[1]}
        metadata=json.dumps(entry,ensure_ascii=False)
        with self.lock,self.connect() as db:
            old=db.execute('SELECT metadata,path,available FROM manifest_entries WHERE cid=? AND manifest=?',(cid,str(manifest))).fetchone()
            if old and tuple(old)==(metadata,path,int(available)):return
            db.execute('INSERT OR REPLACE INTO manifest_entries VALUES(?,?,?,?,?)',(cid,str(manifest),metadata,path,int(available)))
        self.revision+=1
        if available:
            self.live_sources[cid]=dict(id=cid,title=entry.get('title') or Path(path).stem,url=entry.get('url') or 'https://chatgpt.com/c/'+cid,created=epoch(entry.get('create_time')),updated=epoch(entry.get('update_time')),kind=signal[0] if signal else 'chat',kind_evidence=signal[1] if signal else 'No saved Work/Codex product marker',project=entry.get('project') if isinstance(entry.get('project'),str) else '',path=path,fingerprint='',count=0,folder=str(Path(path).parent.relative_to(root)),loaded=False)

    def organize(self,cid,values):
        with self.lock,self.connect() as db:
            db.execute('INSERT OR IGNORE INTO organization(cid) VALUES(?)',(cid,))
            for k in ('category','pinned','position','alias'):
                if k in values:db.execute('UPDATE organization SET '+k+'=? WHERE cid=?',(values[k],cid))
        self.revision+=1
        if self.ui_cache is not None:
            with self.ui_cache_lock:
                if cid in self.ui_cache['chats']:self.ui_cache['chats'][cid].update(values)
                self.ui_cache['revision']+=1
    def organize_many(self,changes):
        if not isinstance(changes,list) or len(changes)>5000:raise ValueError('Invalid organization batch.')
        rows=[(str(r['id']),{k:r[k] for k in ('category','pinned','position','alias') if k in r}) for r in changes]
        with self.lock,self.connect() as db:
            for cid,values in rows:
                db.execute('INSERT OR IGNORE INTO organization(cid) VALUES(?)',(cid,))
                for key,value in values.items():db.execute('UPDATE organization SET '+key+'=? WHERE cid=?',(value,cid))
        self.revision+=1
        if self.ui_cache is not None:
            with self.ui_cache_lock:
                for cid,values in rows:
                    if cid in self.ui_cache['chats']:self.ui_cache['chats'][cid].update(values)
                self.ui_cache['revision']+=1
    def discover_paths(self,start,root,event):
        """Near folders first; yield each candidate without collecting the whole tree."""
        stages=[start];current=start
        while current!=root:
            current=current.parent;stages.append(current)
        visited=set();candidates=0;directories=0
        def note(error):
            if len(self.status['errors'])<40:self.status['errors'].append(str(error))
        for stage in stages:
            for base,dirs,files in os.walk(stage,followlinks=False,onerror=note):
                if event.is_set():return
                basepath=Path(base);key=str(basepath.resolve())
                if key in visited:dirs.clear();continue
                visited.add(key);directories+=1
                self.status['directories']=directories;self.status['current_folder']=str(basepath)
                if directories>25000:
                    note('Directory limit reached. Choose a narrower export folder.');return
                depth=len(basepath.relative_to(root).parts)
                dirs[:]=[d for d in dirs if d.lower() not in SKIP_LOWER and not d.startswith('.') and
                         not (basepath/d).is_symlink() and str((basepath/d).resolve()) not in visited and
                         (basepath/d).resolve() not in (APP/'web',APP/'tests',APP/'runtime',APP/'models')]
                dirs.sort(key=lambda d:(not any(w in d.lower() for w in ('export','backup','chat','markdown','json')),d.lower()))
                if depth>=24:
                    dirs.clear();note('Depth limit reached at '+str(basepath))
                def priority(name):
                    lower=name.lower()
                    return (0 if lower=='conversation-index.json' or 'portable-state' in lower else 1 if lower.endswith('.json') else 2,lower)
                for name in sorted(files,key=priority):
                    if event.is_set():return
                    f=basepath/name
                    if f.suffix.lower() not in ('.md','.json','.jsonl') or f.is_symlink():continue
                    if name.lower().endswith('.error-response.json'):continue
                    candidates+=1;self.status['files']=candidates
                    if candidates>100000:
                        note('File limit reached. Choose a narrower export folder.');return
                    yield f
                # Give foreground HTTP handlers a turn even in directories with no chats.
                time.sleep(.002)
    def read_items(self,f):
        if f.suffix.lower()=='.md':
            parsed=parse_md(f.read_text(encoding='utf-8-sig',errors='replace'),f)
            if parsed:yield parsed
            return
        if f.suffix.lower()=='.jsonl':
            conv=native_conversation(f.read_text(encoding='utf-8-sig'),f)
            conv['id']=conv['id'] or infer_id(f)
            raw=[conv] if conv['messages'] else []
        else:
            d=json.loads(f.read_text(encoding='utf-8-sig'));raw=d if isinstance(d,list) else [d]
        for d in raw:
            self.yield_background()
            x=parse_json(d,f)
            if x:yield x
    def scan(self,start,up=2,event=None):
        if event is None:
            self.cancel_event.set();self.cancel_event=threading.Event();event=self.cancel_event
        with self.scan_lock:
            if event.is_set():return
            producer=None
            try:
                p=Path(start).expanduser().resolve()
                if not p.is_dir():raise ValueError('Choose an existing folder.')
                root=p
                for _ in range(max(0,min(int(up),4))):
                    if root.parent==root or root.parent.parent==root.parent:break
                    root=root.parent
                self.status=dict(scanning=True,phase='Discovering and indexing',files=0,indexed=0,processed=0,cached=0,
                                 directories=0,current_folder=str(p),current_file='',errors=[],roots=[str(root)],started=time.time())
                self.save_settings({'scan_start':str(p),'scan_up':int(up)})
                jobs=queue.Queue(maxsize=100000);finished=object();metadata={};seen={}
                def produce():
                    try:
                        for f in self.discover_paths(p,root,event):
                            try:self.announce_source(f,root)
                            except Exception as e:
                                if len(self.status['errors'])<40:self.status['errors'].append(f.name+': header read: '+str(e))
                            while not event.is_set():
                                try:jobs.put(f,timeout=.1);break
                                except queue.Full:pass
                            if event.is_set():return
                    except Exception as e:
                        if len(self.status['errors'])<40:self.status['errors'].append(str(e))
                    finally:
                        while not event.is_set():
                            try:jobs.put(finished,timeout=.1);break
                            except queue.Full:pass
                producer=threading.Thread(target=produce,daemon=True);producer.start()
                while not event.is_set():
                    self.yield_background()
                    try:f=jobs.get(timeout=.1)
                    except queue.Empty:continue
                    if f is finished:break
                    self.status['current_file']=str(f);self.status['phase']='Discovering / indexing '+f.name
                    try:
                        stat=f.stat()
                        if stat.st_size>512*1024*1024:raise ValueError('File over 512 MiB; split the export first.')
                        fp=str(stat.st_mtime_ns)+':'+str(stat.st_size);rank=(int(f.suffix.lower()=='.json'),stat.st_mtime_ns)
                        ismeta=f.name.lower()=='conversation-index.json' or ('portable-state' in f.name.lower() and f.suffix.lower()=='.json')
                        with self.connect() as db:
                            cached=list(db.execute('SELECT id,fingerprint FROM chats WHERE path=?',(str(f),)))
                            record=db.execute('SELECT fingerprint,status FROM scanned_files WHERE path=?',(str(f),)).fetchone()
                        # A manifest already points at the preferred JSON. Do
                        # not parse its potentially huge duplicate Markdown.
                        if f.suffix.lower()=='.md':
                            cid=infer_id(f)
                            with self.connect() as db:preferred=db.execute('SELECT path FROM chats WHERE id=? UNION ALL SELECT path FROM manifest_entries WHERE cid=? AND available=1 LIMIT 1',(cid,cid)).fetchone()
                            if preferred and Path(preferred['path']).suffix.lower()=='.json' and Path(preferred['path']).is_file():
                                self.status['processed']+=1;self.status['cached']+=1;continue
                        if not ismeta and record and record['fingerprint']==fp and record['status']=='indexed' and cached and all(r['fingerprint']==fp for r in cached):
                            for r in cached:
                                if r['id'] not in seen or rank>=seen[r['id']]:seen[r['id']]=rank;self.enrich(r['id'],metadata.get(r['id'],{}))
                            self.status['cached']+=1
                        elif not ismeta and record and record['fingerprint']==fp and record['status']=='ignored':
                            self.status['cached']+=1
                        elif ismeta:
                            d=json.loads(f.read_text(encoding='utf-8-sig'));entries=d.get('entries') or (d.get('job') or {}).get('entries') or []
                            if isinstance(entries,dict):entries=entries.values()
                            for e in entries:
                                if event.is_set():break
                                if isinstance(e,dict) and e.get('id'):
                                    self.yield_background();metadata[e['id']]=e;self.register_manifest(e,f,root);self.enrich(e['id'],e)
                        else:
                            items=self.read_items(f);had_items=False;cached_ids={r['id'] for r in cached if r['fingerprint']==fp};reused=False
                            for item in items:
                                had_items=True
                                if event.is_set():break
                                cid=item['id']
                                if cid in seen and seen[cid]>=rank:continue
                                if cid in cached_ids:
                                    seen[cid]=rank;self.enrich(cid,metadata.get(cid,{}));reused=True;continue
                                # A cached JSON remains preferred if an MD copy is discovered first.
                                with self.connect() as db:old=db.execute('SELECT path FROM chats WHERE id=? UNION ALL SELECT path FROM manifest_entries WHERE cid=? AND available=1 LIMIT 1',(cid,cid)).fetchone()
                                if f.suffix.lower()=='.md' and old and Path(old['path']).suffix.lower()=='.json' and Path(old['path']).is_file():
                                    seen[cid]=(1,Path(old['path']).stat().st_mtime_ns);continue
                                self.store(item,f,fp,root,metadata.get(cid,{}));seen[cid]=rank;self.status['indexed']+=1
                            if reused:self.status['cached']+=1
                            if not event.is_set():
                                with self.lock,self.connect() as db:db.execute('INSERT OR REPLACE INTO scanned_files VALUES(?,?,?)',(str(f),fp,'indexed' if had_items else 'ignored'))
                        self.status['processed']+=1
                    except Exception as e:
                        if len(self.status['errors'])<40:self.status['errors'].append(f.name+': '+str(e))
                    time.sleep(.005)
                self.status['phase']='Scan stopped · cached chats remain available' if event.is_set() else f'Ready · {len(self.catalog()):,} conversations'
            except Exception as e:
                self.status['errors'].append(str(e));self.status['phase']='Scan failed'
            finally:
                if producer and producer.is_alive():
                    event.set();producer.join(timeout=1)
                self.status['scanning']=False;self.status['current_file']=''
    def enrich(self,cid,meta):
        if not meta:return
        signal=surface_signal(meta)
        kind,evidence=signal or (None,'')
        project=meta.get('project') or '';project=project.get('title') or project.get('name') or '' if isinstance(project,dict) else project
        with self.lock,self.connect() as db:
            existing=db.execute('SELECT kind,kind_evidence FROM chats WHERE id=?',(cid,)).fetchone()
            if existing and kind:
                kind,evidence=prefer_signal((existing['kind'],existing['kind_evidence']),signal)
            if kind:db.execute('UPDATE chats SET kind=?,kind_evidence=? WHERE id=? AND (kind IS NOT ? OR kind_evidence IS NOT ?)',(kind,evidence,cid,kind,evidence))
            if project:db.execute('UPDATE chats SET project=? WHERE id=? AND project IS NOT ?',(project,cid,project))
            for k,mk in [('created','create_time'),('updated','update_time')]:
                if meta.get(mk):db.execute('UPDATE chats SET '+k+'=? WHERE id=? AND '+k+' IS NOT ?',(epoch(meta[mk]),cid,epoch(meta[mk])))
            if meta.get('url'):db.execute('UPDATE chats SET url=? WHERE id=? AND url IS NOT ?',(meta['url'],cid,meta['url']))
            changed=db.total_changes
        if changed:self.revision+=1
        if cid in self.live_sources:
            c=self.live_sources[cid]
            if kind:c.update(kind=kind,kind_evidence=evidence)
            if project:c['project']=project
            for k in ('create_time','update_time'):
                if meta.get(k):c['created' if k=='create_time' else 'updated']=epoch(meta[k])
            if meta.get('url'):c['url']=meta['url']
    def store(self,item,path,fp,root,meta):
        cid=item['id'];msgs=item['messages'];project=item.get('project')
        self.semantic_state['ready']=False
        if not isinstance(project,str):project=str(project or '')
        created=item['created'] or min((m['time'] for m in msgs if m['time']),default=path.stat().st_mtime)
        updated=item['updated'] or max((m['time'] for m in msgs if m['time']),default=created)
        with self.lock,self.connect() as db:
            if not db.execute("SELECT 1 FROM settings WHERE key='ftsRowMapV1'").fetchone():
                db.execute('INSERT OR IGNORE INTO chunk_rows SELECT cid,rowid FROM chunks')
                db.execute('INSERT OR REPLACE INTO title_rows SELECT cid,rowid FROM titles')
                db.execute("INSERT INTO settings VALUES('ftsRowMapV1','true')")
            db.execute('DELETE FROM titles WHERE rowid IN (SELECT rowid FROM title_rows WHERE cid=?)',(cid,))
            title=db.execute('INSERT INTO titles VALUES(?,?)',(cid,item['title']))
            db.execute('INSERT OR REPLACE INTO title_rows VALUES(?,?)',(cid,title.lastrowid))
            db.execute('DELETE FROM messages WHERE cid=?',(cid,));db.execute('DELETE FROM chunks WHERE rowid IN (SELECT rowid FROM chunk_rows WHERE cid=?)',(cid,));db.execute('DELETE FROM chunk_rows WHERE cid=?',(cid,));db.execute('DELETE FROM vectors WHERE cid=?',(cid,))
            db.execute('INSERT OR REPLACE INTO chats(id,title,url,created,updated,kind,project,path,fingerprint,count,folder,kind_evidence) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',(cid,item['title'],item['url'],created,updated,canonical_kind(item['kind']),project,str(path),fp,len(msgs),str(path.parent.relative_to(root)),item.get('kind_evidence','')))
            for seq,m in enumerate(msgs):
                if seq%20==0:self.yield_background()
                db.execute('INSERT INTO messages VALUES(?,?,?,?,?,?,?,?)',(cid,seq,m['role'],m['channel'],m['text'],m['time'],m['visible'],json.dumps(m.get('extras') or {},ensure_ascii=False)))
                if m['visible']:
                    for chunk in chunks(m['text']):
                        inserted=db.execute('INSERT INTO chunks(cid,seq,title,text) VALUES(?,?,?,?)',(cid,seq,item['title'],chunk))
                        db.execute('INSERT INTO chunk_rows VALUES(?,?)',(cid,inserted.lastrowid))
        self.revision+=1
        self.live_sources[cid]=dict(id=cid,title=item['title'],url=item['url'],created=created,updated=updated,kind=canonical_kind(item['kind']),kind_evidence=item.get('kind_evidence',''),project=project,path=str(path),fingerprint=fp,count=len(msgs),folder=str(path.parent.relative_to(root)),loaded=True)
        self.enrich(cid,meta)
    def page(self,cid,before=None,around=None,limit=100,details=False,after=None):
        limit=max(1,min(int(limit),200));predicate='' if details else ' AND visible=1'
        with self.connect() as db:
            known=db.execute('SELECT id FROM chats WHERE id=?',(cid,)).fetchone()
            if not known:
                source=db.execute('SELECT path FROM manifest_entries WHERE cid=? AND available=1',(cid,)).fetchone()
                if not source:raise ValueError('The saved conversation file was not found in this scan boundary.')
                return self.read_source_page(cid,source['path'],before,around,limit,details,after)
            total=db.execute('SELECT count(*) FROM messages WHERE cid=?'+predicate,(cid,)).fetchone()[0]
            if after is not None:
                rows=db.execute('SELECT * FROM messages WHERE cid=?'+predicate+' AND seq>? ORDER BY seq LIMIT ?',(cid,int(after),limit)).fetchall()
            elif around is not None:
                rows=db.execute('SELECT * FROM messages WHERE cid=?'+predicate+' AND seq>=? ORDER BY seq LIMIT ?',(cid,max(0,int(around)-8),limit)).fetchall()
            else:
                rows=db.execute('SELECT * FROM messages WHERE cid=?'+predicate+' AND seq<? ORDER BY seq DESC LIMIT ?',(cid,int(before) if before is not None else 2**31,limit)).fetchall()[::-1]
            first=rows[0]['seq'] if rows else 0
            older=db.execute('SELECT count(*) FROM messages WHERE cid=?'+predicate+' AND seq<?',(cid,first)).fetchone()[0]
            last=rows[-1]['seq'] if rows else -1
            newer=db.execute('SELECT count(*) FROM messages WHERE cid=?'+predicate+' AND seq>?',(cid,last)).fetchone()[0]
            return {'messages':[presented_message(dict(dict(r),extras=json.loads(r['extras'] or '{}'))) for r in rows],'total':total,'older':older,'newer':newer,'first':first}
    def source_data(self,cid):
        if self.ui_cache is not None and cid in self.ui_cache['chats']:r={'path':self.ui_cache['chats'][cid]['path']}
        else:
            with self.connect() as db:r=db.execute('SELECT path FROM chats WHERE id=? UNION ALL SELECT path FROM manifest_entries WHERE cid=? AND available=1 LIMIT 1',(cid,cid)).fetchone()
        if not r or Path(r['path']).suffix.lower()!='.json':return {},None
        path=Path(r['path']);return self.source_reader.raw(cid,path),path
    def choose_version(self,cid,target):
        d,path=self.source_data(cid);mp,children,_=graph_context(d)
        if target not in mp:raise ValueError('This version was not saved in the JSON export.')
        selected=d.get('current_node');descendants=set();todo=[target]
        while todo:
            k=todo.pop()
            if k in descendants:continue
            descendants.add(k);todo.extend(children[k])
        if selected in descendants:return selected
        leaves=[k for k in descendants if not children[k]]
        return max(leaves,key=lambda k:epoch((mp[k].get('message') or {}).get('create_time')),default=target)
    def branch_page(self,cid,leaf,before=None,around=None,limit=100,details=False,after=None):
        d,path=self.source_data(cid)
        if not path:raise ValueError('Saved JSON branch was not found.')
        return dict(page_rows(self.source_reader.rows(cid,path,leaf),before,around,limit,details,after),leaf=leaf)
    def search(self,q,mode='smart',cid=None,cids=None):
        if cids is not None and (not cids or cid and cid not in cids):return {'results':[],'mode':mode}
        if mode in ('exact','exact_typo'):
            from phrase_search import phrase_search
            return phrase_search(self,q,mode=='exact_typo',cid,cids)
        terms=re.findall(r'[^\W_]+',q,flags=re.U)[:24]
        if not terms:return {'results':[],'mode':'keyword'}
        groups=[]
        for term in terms:
            alts={term.lower()}
            if mode!='keyword':
                for family in CONCEPTS:
                    if term.lower() in family:alts.update(family)
            groups.append('('+' OR '.join('"'+t+'"*' for t in sorted(alts))+')')
        query=' AND '.join(groups)
        scope_params=[cid] if cid else sorted(cids) if cids is not None else []
        condition=' AND cid=?' if cid else ' AND cid IN ('+','.join('?' for _ in scope_params)+')' if cids is not None else ''
        def fetch(query):
            with self.connect() as db:
                return [dict(r) for r in db.execute("SELECT cid,seq,title,snippet(chunks,3,'','',' … ',42) snippet,bm25(chunks,0,0,5,1) score FROM chunks WHERE chunks MATCH ?"+condition+" ORDER BY score LIMIT 180",['text : ('+query+')']+scope_params)]
        rows=fetch(query)
        if len(rows)<8:rows+=fetch(' OR '.join(groups))
        exact=[]
        with self.connect() as db:
            exact=[dict(r) for r in db.execute('SELECT id cid,-1 seq,title,title snippet,-100 score FROM chats WHERE (id LIKE ? OR title LIKE ?)'+condition.replace('cid','id')+' LIMIT 20',['%'+q+'%','%'+q+'%']+scope_params)]
        with self.connect() as db:
            title_hits=[dict(r) for r in db.execute("SELECT cid,-1 seq,title,title snippet,bm25(titles) score FROM titles WHERE titles MATCH ?"+condition+" ORDER BY score LIMIT 30",[query]+scope_params)]
        catalog_hits=[]
        for c in (list(self.ui_cache['chats'].values()) if self.ui_cache is not None else self.catalog()):
            if c['loaded'] or (cid and cid!=c['id']) or (cids is not None and c['id'] not in cids):continue
            title=c['title'] or '';words=re.findall(r'[^\W_]+',title.lower(),flags=re.U)
            if q.lower() in c['id'].lower() or q.lower() in title.lower() or all(any(word.startswith(term.lower()) for word in words) for term in terms):
                catalog_hits.append(dict(cid=c['id'],seq=-1,title=title,snippet=title,score=-100))
        rows=exact+catalog_hits+title_hits+rows
        if cid:rows=[r for r in rows if r['cid']==cid]
        used=set();clean=[]
        for r in rows:
            key=(r['cid'],r['seq'])
            if key not in used:used.add(key);clean.append(r)
        used_mode='keyword' if mode=='keyword' else 'smart (text + related words)'
        if mode in ('semantic','hybrid'):
            if not self.semantic_state['ready']:
                self.request_semantic()
                return {'results':clean[:60],'mode':used_mode,'notice':self.semantic_state.get('phase') or 'Semantic setup/indexing started in the background. Progress is shown in Settings; text results remain available.'}
            semantic=self.semantic_search(q,cids) if cids is not None else self.semantic_search(q)
            if cid:semantic=[r for r in semantic if r['cid']==cid]
            if mode=='semantic':clean=semantic
            else:
                ranks={}; lookup={}
                for stream in (clean,semantic):
                    for i,r in enumerate(stream):
                        key=(r['cid'],r['seq']);lookup[key]=r;ranks[key]=ranks.get(key,0)+1/(60+i)
                clean=[lookup[k] for k in sorted(ranks,key=ranks.get,reverse=True)]
            used_mode=mode
        result={'results':clean[:180],'mode':used_mode,'more':len(clean)>180}
        coverage=self.coverage()
        if coverage['available']>coverage['indexed']:result['notice']=f"Content search covers {coverage['indexed']} indexed of {coverage['available']} available chats; titles and IDs are searchable now. See discovery notes for pending or skipped files."
        return result
    def request_semantic(self):
        if not self.semantic_state['building']:
            threading.Thread(target=self.build_semantic,daemon=True).start()
    def build_semantic(self,allow_setup=True):
        if not self.semantic_lock.acquire(False):return
        self.semantic_state.update(building=True,error='',count=0,phase='Preparing local semantic search…')
        try:
            modelpath=APP/'models'/'semantic'
            if allow_setup and (not (APP/'.semantic-packages'/'.ready').is_file() or not (modelpath/'.ready').is_file()):
                self.semantic_state['phase']='Setting up local semantic search…'
                log=self.data_dir/'semantic-setup.log'
                with log.open('w',encoding='utf-8') as output:
                    proc=subprocess.Popen([sys.executable,str(APP/'setup_semantic.py')],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace',bufsize=1)
                    for line in proc.stdout:
                        output.write(line);output.flush()
                        if line.startswith('VIEWER_SETUP:'):self.semantic_state['phase']=line[len('VIEWER_SETUP:'):].strip()
                    if proc.wait():raise RuntimeError('Semantic setup was interrupted. Select semantic again to retry. Details: '+str(log))
            activate_semantic()
            import numpy as np
            import torch
            torch.set_num_threads(1)
            from sentence_transformers import SentenceTransformer
            self.semantic_state['phase']='Loading the local meaning model…'
            self.semantic_model=SentenceTransformer(str(modelpath),local_files_only=True,device='cpu')
            with self.connect() as db: rows=list(db.execute('SELECT cid,seq,title,text FROM chunks'))
            self.semantic_state['phase']='Indexing saved messages'
            counts={};batch=[]
            with self.lock,self.connect() as db:db.execute('DELETE FROM vectors')
            for r in rows:
                key=(r['cid'],r['seq']);part=counts.get(key,0);counts[key]=part+1
                batch.append((r,part))
                if len(batch)>=32:
                    self._embed_batch(batch,np);batch=[]
            if batch:self._embed_batch(batch,np)
            self.semantic_state.update(ready=True,count=len(rows),phase='')
        except Exception as e:self.semantic_state.update(ready=False,error=str(e),phase='')
        finally:self.semantic_state['building']=False;self.semantic_lock.release()
    def _embed_batch(self,batch,np):
        texts=[r['title']+'\n'+r['text'] for r,_ in batch]
        vecs=self.semantic_model.encode(texts,normalize_embeddings=True,show_progress_bar=False)
        with self.lock,self.connect() as db:
            for (r,part),text,v in zip(batch,texts,vecs):db.execute('INSERT INTO vectors VALUES(?,?,?,?,?)',(r['cid'],r['seq'],part,hashlib.sha256(text.encode()).hexdigest(),np.asarray(v,dtype='float32').tobytes()))
        self.semantic_state['count']+=len(batch)
    def semantic_search(self,q,cids=None):
        import numpy as np
        query=self.semantic_model.encode([q],normalize_embeddings=True,show_progress_bar=False)[0]
        with self.connect() as db:rows=list(db.execute('SELECT cid,seq,part,vector FROM vectors'))
        ranked=[];seen=set()
        for r in rows:
            if cids is None or r['cid'] in cids:ranked.append((float(np.dot(query,np.frombuffer(r['vector'],dtype='float32'))),r))
        ranked.sort(key=lambda x:x[0],reverse=True);out=[]
        with self.connect() as db:
            for score,r in ranked:
                key=(r['cid'],r['seq'])