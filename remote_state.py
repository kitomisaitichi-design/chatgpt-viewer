"""Remote availability is metadata, never a transcript hash or a filename change."""
import time
from pathlib import Path

STATES={'available','deleted','unavailable'}
def ensure(archive):
    with archive.connect() as db:
        db.execute('CREATE TABLE IF NOT EXISTS remote_chat_state(root TEXT,cid TEXT,scope TEXT,state TEXT,checked REAL,source TEXT,detail TEXT,PRIMARY KEY(root,cid))')

def values(row):
    return dict(remote_state=row['state'],remote_checked=row['checked'],remote_detail=row['detail'],remote_source=row['source'])

def record(archive,root,cid,scope,state,source,detail='',checked=None):
    if state not in STATES or not scope:raise ValueError('Verified remote state and account scope are required')
    root=Path(root).resolve();checked=checked or time.time()
    with archive.lock,archive.connect() as db:
        old=db.execute('SELECT state,checked FROM remote_chat_state WHERE root=? AND cid=?',(str(root),cid)).fetchone()
        if old and old['checked']>checked:return
        db.execute('INSERT OR REPLACE INTO remote_chat_state VALUES(?,?,?,?,?,?,?)',(str(root),cid,scope,state,checked,source,detail))
    archive.revision+=1
    if archive.ui_cache is not None:
        with archive.ui_cache_lock:
            chat=archive.ui_cache['chats'].get(cid)
            if chat and Path(chat['path']).resolve().is_relative_to(root):
                chat.update(remote_state=state,remote_checked=checked,remote_detail=detail,remote_source=source)
                archive.ui_row_revisions[cid]=archive.ui_cache['revision']+1;archive.ui_cache['revision']+=1

def enrich(archive,chats):
    with archive.connect() as db:rows=[dict(r) for r in db.execute('SELECT * FROM remote_chat_state')]
    by_id={}
    for row in rows:by_id.setdefault(row['cid'],[]).append(row)
    for chat in chats:
        matches=[r for r in by_id.get(chat['id'],[]) if Path(chat['path']).resolve().is_relative_to(Path(r['root']))]
        if len({r['scope'] for r in matches})==1:chat.update(values(max(matches,key=lambda r:r['checked'])))
    return chats
