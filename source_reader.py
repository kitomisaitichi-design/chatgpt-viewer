"""Bounded, fingerprinted source cache with concurrent read coalescing."""
import json, threading
from collections import OrderedDict
from concurrent.futures import Future
from pathlib import Path

def native_conversation(text,path):
    records=[json.loads(line) for line in text.splitlines() if line.strip()]
    session=next((r.get('payload') or {} for r in records if isinstance(r,dict) and r.get('type')=='session_meta'),{})
    conv={'id':session.get('id'),'title':session.get('title') or Path(path).stem,'product':'codex','create_time':session.get('timestamp'),'messages':[]}
    for r in records:
        if not isinstance(r,dict) or r.get('type')!='response_item':continue
        payload=r.get('payload') or {};role=payload.get('role')
        if role:conv['messages'].append({'role':role,'channel':payload.get('channel',''),'text':'\n'.join(x.get('text','') for x in payload.get('content',[]) if isinstance(x,dict)),'create_time':r.get('timestamp')})
    return conv

class SourceReader:
    def __init__(self,parse_json,parse_md,max_bytes=192*1024*1024,max_entries=4):
        self.parse_json=parse_json;self.parse_md=parse_md
        self.max_bytes=max_bytes;self.max_entries=max_entries
        self.lock=threading.RLock();self.entries=OrderedDict();self.pending={}
        self.reads=0;self.hits=0
    def entry(self,cid,path):
        path=Path(path);st=path.stat();key=(str(path.resolve()),st.st_mtime_ns,st.st_size,cid)
        if st.st_size>512*1024*1024:raise ValueError('File over 512 MiB; split the export first.')
        with self.lock:
            if key in self.entries:
                self.hits+=1;self.entries.move_to_end(key);return self.entries[key]
            owner=key not in self.pending
            if owner:self.pending[key]=Future()
            future=self.pending[key]
        if not owner:return future.result(timeout=60)
        try:
            text=path.read_text(encoding='utf-8-sig',errors='replace' if path.suffix.lower()=='.md' else 'strict')
            raw=native_conversation(text,path) if path.suffix.lower()=='.jsonl' else json.loads(text) if path.suffix.lower()!='.md' else None
            if isinstance(raw,list):raw=next((x for x in raw if isinstance(x,dict) and str(x.get('conversation_id') or x.get('id'))==cid),{})
            if isinstance(raw,dict) and isinstance(raw.get('conversation'),dict):raw=raw['conversation']
            item={'raw':raw,'md':text if raw is None else None,'rows':OrderedDict(),'lock':threading.RLock(),'weight':st.st_size*3,'path':path,'key':key}
            with self.lock:
                self.reads+=1
                # Invalidate all older fingerprints for this path and ID.
                for old in list(self.entries):
                    if old[0]==key[0] and old[3]==cid:del self.entries[old]
                self.entries[key]=item
                while len(self.entries)>1 and (len(self.entries)>self.max_entries or sum(e['weight'] for e in self.entries.values())>self.max_bytes):self.entries.popitem(last=False)
                future.set_result(item)
            return item
        except BaseException as error:
            future.set_exception(error);raise
        finally:
            with self.lock:self.pending.pop(key,None)
    def rows(self,cid,path,leaf=None):
        e=self.entry(cid,path)
        with e['lock']:
            if leaf in e['rows']:
                e['rows'].move_to_end(leaf);return e['rows'][leaf]
            raw=e['raw']
            if leaf and (not isinstance(raw,dict) or leaf not in (raw.get('mapping') or {})):raise ValueError('Saved JSON branch was not found.')
            parsed=self.parse_md(e['md'],e['path']) if raw is None else self.parse_json(raw,e['path'],leaf)
            if not parsed:raise ValueError('This export does not contain readable chat messages.')
            rows=[dict(m,seq=i,cid=cid) for i,m in enumerate(parsed['messages'])]
            e['rows'][leaf]=rows
            while len(e['rows'])>2:e['rows'].popitem(last=False)
            return rows
    def raw(self,cid,path):return self.entry(cid,path)['raw'] or {}
    def clear(self):
        with self.lock:self.entries.clear()

def page_rows(allrows,before=None,around=None,limit=100,details=False,after=None):
    allrows=[m for m in allrows if details or m['visible']];limit=max(1,min(int(limit),200))
    if around is not None:rows=[m for m in allrows if m['seq']>=max(0,int(around)-8)][:limit]
    elif after is not None:rows=[m for m in allrows if m['seq']>int(after)][:limit]
    else:rows=[m for m in allrows if before is None or m['seq']<int(before)][-limit:]
    first=rows[0]['seq'] if rows else 0;last=rows[-1]['seq'] if rows else -1
    return dict(messages=rows,total=len(allrows),older=sum(m['seq']<first for m in allrows),newer=sum(m['seq']>last for m in allrows),first=first)
