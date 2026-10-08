"""Viewer-owned browser transport. Browser credentials never leave ChatGPT.

Only one request lease is issued at a time. Expired mutations are verified before
retrying; recovery snapshots and queue intent survive browser/server restarts.
"""
import hashlib, json, secrets, shutil, threading, time, uuid
from pathlib import Path
from atomic_files import atomic_bytes


def graph_hash(data):
    """Hash saved messages/branches, excluding mutable service bookkeeping."""
    mapping = data.get('mapping') if isinstance(data, dict) else None
    if not isinstance(mapping, dict) or not mapping:
        return None
    nodes = []
    for key, node in sorted(mapping.items()):
        if not isinstance(node, dict):
            return None
        message = node.get('message') or {}
        if not message:
            continue
        metadata = message.get('metadata') or {}
        nodes.append([key, node.get('parent'), sorted(node.get('children') or []),
                      message.get('id'), message.get('author'), message.get('content'),
                      metadata.get('attachments'), message.get('recipient'), message.get('channel')])
    return hashlib.sha256(json.dumps(nodes, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest() if nodes else None


def scope_key(scope):
    if not isinstance(scope, dict) or not isinstance(scope.get('user'), str) or not scope['user']:
        raise ValueError('An authenticated ChatGPT account is required')
    return hashlib.sha256(json.dumps([scope['user'], scope.get('account') or None], separators=(',', ':')).encode()).hexdigest()


def retry_delay(value):
    try:
        delay = float(value)
    except (TypeError, ValueError):
        try:
            from email.utils import parsedate_to_datetime
            delay = parsedate_to_datetime(value).timestamp() - time.time()
        except (TypeError, ValueError, OverflowError):
            delay = 60
    return max(8, min(delay, 86400))


class BrowserCompanion:
    def __init__(self, queue):
        self.queue = queue
        self.archive = queue.archive
        self.lock = threading.RLock()
        self.clients = {}
        self.endpoint = ''
        self.nonce = uuid.uuid4().hex
        self.secret_file = self.archive.data_dir / 'browser-connection.json'
        try:
            saved = json.loads(self.secret_file.read_text())
            self.secret = saved['secret']
            self.nonce = saved.get('nonce') or self.nonce
        except FileNotFoundError:
            self.secret = secrets.token_urlsafe(32)
        self.save_connection()
        with self.archive.connect() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS browser_requests(
                job TEXT PRIMARY KEY, phase TEXT, lease TEXT, owner TEXT, expires REAL,
                next_at REAL, attempts INTEGER, updated REAL)''')
            db.execute('CREATE TABLE IF NOT EXISTS browser_checks(id TEXT PRIMARY KEY,cid TEXT,root TEXT,scope TEXT,created REAL,done INTEGER)')
            # Never resend an uncertain PATCH. A read decides its outcome first.
            db.execute("UPDATE browser_requests SET phase=CASE WHEN phase='delete' THEN 'verify' ELSE phase END,lease='',owner='',expires=0")

    def setup(self):
        return dict(endpoint=self.endpoint, key=self.secret, folder=str(self.archive.data_dir / 'browser-connection-extension'))

    def save_connection(self):
        atomic_bytes(self.secret_file,json.dumps(dict(secret=self.secret,nonce=self.nonce)).encode(),private=True)

    def prepare_extension(self):
        """Stable private install folder; pairing follows the viewer's dynamic port."""
        target = Path(self.setup()['folder'])
        target.mkdir(parents=True,exist_ok=True)
        for source in (Path(__file__).parent/'integration/browser-companion').iterdir():
            if source.is_file():shutil.copy2(source,target/source.name)
        atomic_bytes(target/'pairing.json',json.dumps(dict(endpoint=self.endpoint,key=self.secret)).encode(),private=True)

    def configured(self, root):
        from deletion_queue import write
        write(Path(root) / '.viewer-queue/companion.json', dict(endpoint=self.endpoint,key=self.secret,nonce=self.nonce))

    def reset(self):
        with self.lock:
            self.nonce = uuid.uuid4().hex
            self.save_connection()
            self.clients.clear()
            for root in self.queue.roots():
                self.configured(root)

    def statuses(self):
        with self.lock:
            return [dict(root='', scope=c.get('key', ''), connected=c['connected'] and time.time()-c['updated'] < 45,
                         fresh=time.time()-c['updated'] < 45, version=c['kind'], independent=True,
                         connection=c.get('connection', {}), owner=c['kind']) for c in self.clients.values()]

    def connected_scopes(self):
        return {c['scope'] for c in self.statuses() if c['connected']}

    def check(self,cid):
        root,scope=self.queue.chat_account(cid)
        if scope=='unbound':return dict(queued=False,message='Connect a signed-in ChatGPT tab first')
        with self.archive.connect() as db:
            old=db.execute('SELECT id FROM browser_checks WHERE cid=? AND scope=? AND created>?',(cid,scope,time.time()-900)).fetchone()
            if old:return dict(queued=True,id=old['id'])
            ident=uuid.uuid4().hex
            db.execute('DELETE FROM browser_checks WHERE created<?',(time.time()-1800,))
            db.execute('INSERT INTO browser_checks VALUES(?,?,?,?,?,0)',(ident,cid,str(root),scope,time.time()))
        return dict(queued=True,id=ident)

    def enabled(self, row):
        from deletion_queue import read
        control = read(Path(row['root']) / '.viewer-queue/control.json')
        return control.get('enabled') is True and control.get('run') == row['run'] and time.time()-control.get('updated', 0) < 45

    def preferred(self, client, key):
        now = time.time()
        exporters = [c for c in self.clients.values() if c['kind'] == 'exporter' and c.get('key') == key and c['connected'] and now-c['updated'] < 20]
        if exporters:
            return client == min(exporters, key=lambda c: c['id'])['id']
        # Native intents use a separate schema which old adapters cannot execute.
        # Keep the compatibility guard only for the older extension companion.
        from deletion_queue import read
        for root, scope in self.queue.roots().items():
            bridge = read(root / '.viewer-queue/bridge.json')
            if self.clients.get(client,{}).get('kind')!='native' and scope == key and not bridge.get('transport') and bridge.get('connected') and now-bridge.get('updated', 0) < 20:
                return False
        companions = [c for c in self.clients.values() if c['kind'] in ('native','companion') and c.get('key') == key and c['connected'] and now-c['updated'] < 45]
        native = [c for c in companions if c['kind']=='native']
        if native:companions=native
        return bool(companions) and client == min(companions, key=lambda c: c['id'])['id']

    def poll(self, data):
        with self.lock:
            ident = str(data.get('client', ''))
            if not ident or len(ident) > 100 or data.get('kind') not in ('native', 'companion', 'exporter'):
                raise ValueError('Invalid browser client')
            scope = data.get('scope')
            key = scope_key(scope) if data.get('connected') is True else ''
            self.clients[ident] = dict(id=ident, kind=data['kind'], scope=scope, key=key,
                                      connected=bool(key), updated=time.time(), connection=data.get('connection') or {})
            if len(self.clients) > 20:
                oldest = min(self.clients, key=lambda c: self.clients[c]['updated'])
                self.clients.pop(oldest)
            response = dict(nonce=self.nonce, wait=15, pending=any(r['scope']==key and r['state'] in ('waiting','running','retrying') for r in self.queue.rows()),owner='exporter' if any(c['kind']=='exporter' and c.get('key')==key and time.time()-c['updated']<20 for c in self.clients.values()) else 'companion')
            if key:
                with self.archive.connect() as db:
                    response['pending'] |= bool(db.execute('SELECT 1 FROM browser_checks WHERE scope=? AND done=0 AND created>? LIMIT 1',(key,time.time()-1800)).fetchone())
            if not key or data.get('heartbeat') or not self.preferred(ident, key):
                return response
            now = time.time()
            with self.archive.connect() as db:
                db.execute('BEGIN IMMEDIATE')
                leased = db.execute('SELECT * FROM browser_requests WHERE lease<>\'\' AND expires>?', (now,)).fetchone()
                if leased:
                    return dict(response, wait=2)
                # Persist a shared cooldown across clients, tabs and process restarts.
                next_at = db.execute('SELECT MAX(next_at) FROM browser_requests').fetchone()[0] or 0
                cooldown = max(0, float(data.get('cooldown', 0) or 0))
                if cooldown > now:
                    next_at = max(next_at, min(cooldown, now+86400))
                    db.execute('UPDATE browser_requests SET next_at=MAX(next_at,?)', (next_at,))
                if next_at > now:
                    return dict(response, wait=min(15, next_at-now), until=next_at)
                rows = [r for r in self.queue.rows() if r['scope'] == key and r['state'] in ('waiting','running','retrying') and self.enabled(r)]
                rows += [dict(r,run='',is_check=True) for r in db.execute('SELECT * FROM browser_checks WHERE scope=? AND done=0 AND created>? ORDER BY created LIMIT 100',(key,now-1800))]
                for row in rows:
                    command = __import__('deletion_queue').read(Path(row['root']) / '.viewer-queue/commands' / (row['id']+'.json'))
                    if not row.get('is_check') and command.get('executor') != 'browser-v1':
                        continue
                    req = db.execute('SELECT * FROM browser_requests WHERE job=?', (row['id'],)).fetchone()
                    phase = req['phase'] if req else 'check' if row.get('is_check') else 'preflight'
                    if phase == 'done':
                        continue
                    if req and req['lease'] and req['expires'] <= now and phase == 'delete':
                        phase = 'verify'
                    lease = uuid.uuid4().hex
                    db.execute('INSERT OR REPLACE INTO browser_requests VALUES(?,?,?,?,?,?,?,?)',
                               (row['id'], phase, lease, ident, now+90, now+8, req['attempts'] if req else 0, now))
                    if not row.get('is_check'):self.receipt(row, 'running', message='Checking saved revision' if phase=='preflight' else 'Verifying deletion' if phase=='verify' else 'Deleting on ChatGPT')
                    return dict(response, wait=2, request=dict(job=row['id'], lease=lease, phase=phase, cid=row['cid'], scope=scope,
                                      op='viewerDelete' if phase=='delete' else 'get', path='/backend-api/conversation/'+row['cid']))
            return response

    def permit(self, data):
        with self.lock, self.archive.connect() as db:
            req = db.execute('SELECT * FROM browser_requests WHERE job=?', (data.get('job'),)).fetchone()
            row = next((r for r in self.queue.rows() if r['id']==data.get('job')), None)
            if not row:
                check=db.execute('SELECT * FROM browser_checks WHERE id=? AND done=0',(data.get('job'),)).fetchone()
                if check:row=dict(check,is_check=True)
            return dict(allowed=bool(req and row and secrets.compare_digest(req['lease'], str(data.get('lease',''))) and req['owner']==data.get('client') and req['expires']>time.time() and (row.get('is_check') or self.enabled(row))))

    def receipt(self, row, state, **extra):
        from deletion_queue import write, SCHEMA
        write(Path(row['root']) / '.viewer-queue/receipts' / (row['id']+'.json'),
              dict(schema=SCHEMA, **{k:row[k] for k in ('id','cid','scope','run','mode')}, state=state, updated=time.time(), **extra))

    def result(self, data):
        with self.lock, self.archive.connect() as db:
            req = db.execute('SELECT * FROM browser_requests WHERE job=?', (data.get('job'),)).fetchone()
            row = next((r for r in self.queue.rows() if r['id']==data.get('job')), None)
            if not row:
                check=db.execute('SELECT * FROM browser_checks WHERE id=? AND done=0',(data.get('job'),)).fetchone()
                if check:row=dict(check,is_check=True)
            if not req or not row or not req['lease'] or not secrets.compare_digest(req['lease'], str(data.get('lease',''))) or req['owner']!=data.get('client'):
                raise ValueError('Expired or duplicate browser result')
            result = data.get('result') or {}
            status = int(result.get('status') or 0)
            phase = req['phase']; next_phase = phase; attempts = req['attempts']; until = time.time()+8
            error = None
            if row.get('is_check'):
                body=result.get('data') or {}
                valid=result.get('ok') is True and (graph_hash(body) or isinstance(body.get('is_visible'),bool))
                if valid or status in (404,410):
                    from remote_state import record
                    state='unavailable' if status in (404,410) else 'deleted' if body.get('is_visible') is False else 'available'
                    db.commit()
                    record(self.archive,row['root'],row['cid'],row['scope'],state,'authenticated browser lookup')
                    db.execute('UPDATE browser_checks SET done=1 WHERE id=?',(row['id'],))
                elif status!=429:
                    db.execute('UPDATE browser_checks SET done=1 WHERE id=?',(row['id'],))
                db.execute("UPDATE browser_requests SET lease='',owner='',expires=0,next_at=? WHERE job=?",(time.time()+retry_delay(result.get('retryAfter')) if status==429 else time.time()+8,row['id']))
                return dict(accepted=True)
            if status == 429:
                until = time.time()+retry_delay(result.get('retryAfter'))
                self.receipt(row,'retrying',until=until,message='ChatGPT asked to wait; resumes automatically')
            elif status in (401,403,409):
                if phase=='delete':next_phase='verify'
                self.receipt(row,'paused',error=result.get('error') or 'Reconnect to the original ChatGPT account')
            elif result.get('ok') is not True and status not in (404,410):
                attempts += 1
                # An uncertain PATCH must be checked before any possible retry.
                if phase=='delete':next_phase='verify'
                if attempts <= 2:
                    until = time.time()+15*2**attempts
                    self.receipt(row,'retrying',until=until,error=result.get('error') or 'Connection interrupted; checking outcome')
                else:error = result.get('error') or 'Request failed twice; review and reconnect'
            elif phase == 'delete':
                next_phase = 'verify'
            else:
                body = result.get('data') or {}
                missing = status in (404,410)
                deleted = body.get('is_visible') is False
                if missing or deleted:
                    state = 'deleted' if phase=='verify' or deleted else 'unavailable'
                    self.receipt(row,'confirmed',verified=True,remote_state=state)
                    next_phase = 'done'
                elif not graph_hash(body) or (body.get('conversation_id') or body.get('id') or row['cid']) != row['cid']:
                    error = 'Unrecognized conversation response; no deletion was sent'
                elif phase == 'verify':
                    error = 'ChatGPT has not confirmed deletion. Review before retrying.'
                else:
                    recovery = self.archive.data_dir/'deletion-recovery'/row['id']
                    atomic_bytes(recovery/'remote.json',json.dumps(body,ensure_ascii=False).encode(),private=True)
                    # Compare the exact saved branch graph, not volatile index timestamps.
                    from deletion_queue import read,digest
                    sources = list(recovery.glob('source.json'))
                    index=read(recovery/'index.json')
                    if index.get('cid')==row['cid'] and index.get('scope')==row['scope']:
                        for source in index.get('sources',[]):
                            candidate=Path(source['copy'])
                            if (candidate.suffix.lower()=='.json' and not candidate.is_symlink()
                                and candidate.resolve().is_relative_to(recovery.resolve()) and candidate.is_file()
                                and digest(candidate)==source.get('sha256')):sources.append(candidate)
                    baselines={graph_hash(self.archive.source_reader.raw(row['cid'],source)) for source in sources}
                    baselines.discard(None)
                    if not baselines:
                        error = 'This local copy has no JSON graph to compare. Save its current JSON before remote deletion.'
                    elif graph_hash(body) not in baselines:
                        error = 'ChatGPT has a different revision. New remote JSON was backed up; update and review this chat first.'
                    elif not self.enabled(row):
                        self.receipt(row,'paused')
                    else:
                        next_phase = 'delete'
                        # Optional exporter owner also stores the preflight recovery/hash.
            if error:
                self.receipt(row,'failed',error=error);next_phase='done'
            db.execute('UPDATE browser_requests SET phase=?,lease=\'\',owner=\'\',expires=0,next_at=?,attempts=?,updated=? WHERE job=?',
                       (next_phase,until,attempts,time.time(),row['id']))
        self.queue.start()
        return dict(accepted=True)
