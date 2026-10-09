"""Background local retention choices, completely separate from ChatGPT requests."""
import hashlib
import json
import shutil
import threading
import time
import uuid
from itertools import islice
from pathlib import Path


def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for part in iter(lambda:f.read(1024*1024),b''):h.update(part)
    return h.hexdigest()


class LocalChoiceQueue:
    def __init__(self,archive):
        self.archive=archive
        self.lock=threading.RLock()
        self.wakeup=threading.Event()
        self.stop_event=threading.Event()
        self.worker=None
        self.recovery=archive.data_dir/'local-choice-recovery'
        with archive.connect() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS local_choice_jobs(
                id TEXT PRIMARY KEY,cid TEXT NOT NULL, title TEXT NOT NULL,
                mode TEXT NOT NULL, source TEXT NOT NULL,state TEXT NOT NULL,
                error TEXT NOT NULL DEFAULT '',updated REAL NOT NULL)''')
            db.execute("UPDATE local_choice_jobs SET state='queued' WHERE state='running'")
        self.start()

    def rows(self):
        with self.archive.connect() as db:
            return [dict(row) for row in db.execute(
                "SELECT id,cid,title,mode,state,error,updated FROM local_choice_jobs "
                "WHERE state!='confirmed' OR updated>? ORDER BY updated DESC LIMIT 1000",
                (time.time()-25,))]

    def _source(self,cid,name):
        f=Path(name)
        if not f.is_file() or f.is_symlink() or f.suffix.lower() not in ('.json','.md'):
            raise ValueError('Only an individual regular JSON/Markdown source can be deleted locally')
        original=f.resolve(strict=True)
        if original.is_relative_to(self.archive.data_dir.resolve()) or original.is_relative_to(Path(__file__).parent.resolve()):
            raise ValueError('Viewer internal files cannot be selected for local deletion')
        if any(parent.is_symlink() for parent in f.parents):
            raise ValueError('Source has a symbolic-link parent')
        with self.archive.connect() as db:
            others=db.execute('''SELECT 1 FROM chats WHERE id!=? AND path=?
                UNION SELECT 1 FROM manifest_entries WHERE cid!=? AND path=? LIMIT 1''',
                (cid,str(f),cid,str(f))).fetchone()
        if others:raise ValueError('The source file is shared by another conversation')
        if f.stat().st_size>128*1024*1024:raise ValueError('Source is too large for exclusive-file verification')
        items=list(islice(self.archive.read_items(f),2))
        if len(items)!=1 or items[0]['id']!=cid:raise ValueError('Source contains more than the selected conversation')
        return original

    def enqueue(self,selected,mode):
        if mode not in ('preserve','delete'):raise ValueError('Unknown local retention choice')
        if mode=='delete':
            for cid,_,name in selected:self._source(cid,name)
        now=time.time()
        ids=[]
        with self.lock,self.archive.connect() as db:
            for cid,title,name in selected:
                ident='local-choice-'+uuid.uuid4().hex
                db.execute('INSERT INTO local_choice_jobs VALUES(?,?,?,?,?,?,?,?)',
                           (ident,cid,title,mode,name,'queued','',now))
                ids.append(ident)
        self.start();self.wakeup.set()
        return {'accepted':[c for c,_,_ in selected], 'jobs':ids, 'async':True, 'mode':mode}

    def start(self):
        with self.lock:
            if self.worker and self.worker.is_alive():return
            self.worker=threading.Thread(target=self._loop,name='ViewerLocalRetention',daemon=True)
            self.worker.start()

    def _delete_one(self,row):
        if not Path(row['source']).exists() and row['cid'] in self.archive.removed_ids():
            target=self.recovery/(row['id']+Path(row['source']).suffix)
            if target.is_file() and not target.is_symlink():return
        f=self._source(row['cid'],row['source'])
        before=f.stat()
        digest=sha(f)
        if self.recovery.is_symlink():raise ValueError('Private recovery directory is a symlink')
        self.recovery.mkdir(parents=True,exist_ok=True)
        target=self.recovery/(row['id']+f.suffix)
        if target.is_symlink():raise ValueError('Private recovery file is a symlink')
        if target.exists():
            if sha(target)!=digest:raise ValueError('Recovery source mismatch')
        else:
            tmp=target.with_suffix('.part-'+uuid.uuid4().hex)
            try:
                shutil.copy2(f,tmp)
                if sha(tmp)!=digest:raise ValueError('Recovery file hash mismatch')
                tmp.replace(target)
            finally:
                tmp.unlink(missing_ok=True)
        current=f.stat()
        if (current.st_size,current.st_mtime_ns,current.st_ino)!=(before.st_size,before.st_mtime_ns,before.st_ino) or sha(f)!=digest:
            raise ValueError('Source changed during local deletion, original kept')
        self.archive.remove_local_chat(row['cid'])
        if f.is_symlink() or not f.exists():raise ValueError('Source changed after index removal, retry')
        current=f.stat()
        if (current.st_size,current.st_mtime_ns,current.st_ino)!=(before.st_size,before.st_mtime_ns,before.st_ino) or sha(f)!=digest:
            raise ValueError('Source changed after index removal, original kept')
        f.unlink()

    def _loop(self):
        while not self.stop_event.is_set() and not self.archive.cache_stop.is_set():
            with self.lock,self.archive.connect() as db:
                r=db.execute("SELECT * FROM local_choice_jobs WHERE state='queued' ORDER BY updated LIMIT 1").fetchone()
                row=dict(r) if r else None
                if row:db.execute("UPDATE local_choice_jobs SET state='running',updated=? WHERE id=?",(time.time(),row['id']))
            if not row:
                self.wakeup.wait(.5);self.wakeup.clear();continue
            try:
                if row['mode']=='preserve':self.archive.remove_local_chat(row['cid'])
                else:self._delete_one(row)
            except Exception as exc:
                with self.lock,self.archive.connect() as db:
                    db.execute("UPDATE local_choice_jobs SET state='failed',error=?,updated=? WHERE id=?",(str(exc)[:1200],time.time(),row['id']))
            else:
                with self.lock,self.archive.connect() as db:
                    db.execute("UPDATE local_choice_jobs SET state='confirmed',error='',updated=? WHERE id=?",(time.time(),row['id']))

    def close(self):
        self.stop_event.set();self.wakeup.set()
        if self.worker and self.worker is not threading.current_thread():self.worker.join(timeout=5)
