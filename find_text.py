"""Locate literal, whitespace-tolerant text in one saved branch."""
import re

def literal_matches(text, query, limit=1000):
    words=query.strip().split()
    if not words:return []
    pattern=re.compile(r'\s+'.join(re.escape(w) for w in words),re.I)
    from itertools import islice
    return [dict(start=m.start(),end=m.end(),text=m.group()) for m in islice(pattern.finditer(text),limit)]

def conversation_matches(archive,cid,query,leaf=None,details=False):
    query=query.strip()[:800]
    if not query:return dict(results=[],truncated=False)
    if leaf:
        _,path=archive.source_data(cid)
        rows=archive.source_reader.rows(cid,path,leaf)
    else:
        with archive.connect() as db:
            rows=[dict(r) for r in db.execute('SELECT seq,text,visible,role FROM messages WHERE cid=? ORDER BY seq',(cid,))]
            source=db.execute('SELECT path FROM manifest_entries WHERE cid=? AND available=1',(cid,)).fetchone() if not rows else None
        if source:rows=archive.source_reader.rows(cid,source['path'])
    results=[];truncated=False
    for row in rows:
        if not details and not row.get('visible',1):continue
        for hit in literal_matches(row['text'],query,1001):
            if len(results)>=1000:truncated=True;break
            results.append(dict(seq=row['seq'],role=row['role'],**hit))
        if truncated:break
    return dict(results=results,truncated=truncated)