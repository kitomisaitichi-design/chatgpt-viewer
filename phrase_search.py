"""Indexed phrase search with conservative spelling and final-word completion.

Candidate terms come from FTS; the verifier preserves word order and checks
original text. No embeddings or archive-wide text scan are needed.
"""
import math,re,sqlite3,unicodedata

WORD=re.compile(r'[^\W_]+',re.U)
def normal(text):return unicodedata.normalize('NFKC',text).casefold()
def edit_distance(a,b,limit=2):
    if a==b:return 0
    if abs(len(a)-len(b))>limit:return limit+1
    previous=list(range(len(b)+1));before=None
    for i,x in enumerate(a,1):
        row=[i]
        for j,y in enumerate(b,1):
            value=min(row[-1]+1,previous[j]+1,previous[j-1]+(x!=y))
            if before is not None and i>1 and j>1 and x==b[j-2] and a[i-2]==y:value=min(value,before[j-2]+1)
            row.append(value)
        if min(row)>limit:return limit+1
        before,previous=previous,row
    return previous[-1]

def spelling_variants(word):
    variants={word}
    if len(word)<3 or len(word)>32:return variants
    alphabet='abcdefghijklmnopqrstuvwxyz'+''.join(set(word))
    for i in range(len(word)):
        variants.add(word[:i]+word[i+1:])
        if i+1<len(word):variants.add(word[:i]+word[i+1]+word[i]+word[i+2:])
        for c in alphabet:variants.add(word[:i]+c+word[i+1:])
    for i in range(len(word)+1):
        for c in alphabet:variants.add(word[:i]+c+word[i:])
    return variants

def stems(words):
    # Use exactly the tokenizer already employed by the saved index. A tiny
    # in-memory database avoids writing to or rebuilding the archive.
    with sqlite3.connect(':memory:') as db:
        db.execute("CREATE VIRTUAL TABLE probe USING fts5(text,tokenize='porter unicode61')")
        db.execute("CREATE VIRTUAL TABLE terms USING fts5vocab(probe,'row')")
        db.executemany('INSERT INTO probe VALUES(?)',((w,) for w in words))
        return {r[0] for r in db.execute('SELECT term FROM terms')}

def near_phrase(text,query,typos=True):
    q=' '.join(normal(query).split());collapsed=' '.join(normal(text).split())
    at=collapsed.find(q)
    while at>=0:
        end=at+len(q)
        if not(at and q[0].isalnum() and collapsed[at-1].isalnum()) and not(end<len(collapsed) and q[-1].isalnum() and collapsed[end].isalnum()):
            return 0,'Exact phrase',max(0,normal(text).find(q.split()[0]))
        at=collapsed.find(q,at+1)
    if not typos:return None
    wanted=[normal(m.group()) for m in WORD.finditer(query)][:48]
    tokens=[(normal(m.group()),m.start()) for m in WORD.finditer(text)]
    if not wanted:return None
    budget=min(4,max(2,math.ceil(len(wanted)/4)))
    best=None
    for start,(token,pos) in enumerate(tokens):
        if edit_distance(wanted[0],token,2)>2 and not(len(wanted)==1 and len(wanted[0])>=3 and token.startswith(wanted[0])):continue
        # Ordered alignment allows one word inserted in the saved phrase.
        paths={(0,0):(0,False)}
        for i in range(len(wanted)):
            for j in range(i,min(i+2,len(tokens)-start)):
                old=paths.get((i,j))
                if old is None:continue
                score,completion=old;word=tokens[start+j][0];term=wanted[i]
                allowed=2 if len(term)>=4 else 1
                d=edit_distance(term,word,allowed)
                complete=i==len(wanted)-1 and len(term)>=3 and word.startswith(term) and word!=term
                if complete:d=.25
                if (complete or d<=allowed) and score+d<=budget:
                    key=(i+1,j+1);candidate=(score+d,completion or complete)
                    if key not in paths or candidate<paths[key]:paths[key]=candidate
                if j==i and start+j+1<len(tokens) and score+2<=budget:
                    paths[(i,j+1)]=(score+2,completion)
        for (i,j),(score,completion) in paths.items():
            if i==len(wanted) and (best is None or score<best[0]):best=(score,'Prefix completion' if completion else 'Close phrase',pos)
    return best

def phrase_search(archive,q,typos=False,cid=None):
    q=q.strip()[:800];words=[normal(m.group()) for m in WORD.finditer(q)][:48]
    if not q:return {'results':[],'mode':'exact + typos' if typos else 'exact phrase'}
    results=[]
    def add(chat,seq,text,matched):
        if not matched:return
        score,label,pos=matched
        results.append(dict(cid=chat['id'],seq=seq,title=chat['title'],snippet=text[max(0,pos-70):pos+330],score=score,match=label))
    for c in archive.catalog():
        if cid and c['id']!=cid:continue
        hit=near_phrase(c['title'] or '',q,typos)
        if ' '.join(normal(q).split()) in normal(c['id']):hit=(0,'Exact phrase',0)
        add(c,-1,c['title'] or c['id'],hit)
    condition=' AND cid=?' if cid else ''
    rows=[]
    if words:
        with archive.connect() as db:
            def fetch(query,limit=360):
                params=['text : ('+query+')']+([cid] if cid else [])
                return [dict(r) for r in db.execute('SELECT cid,seq,title,text FROM chunks WHERE chunks MATCH ?'+condition+' ORDER BY bm25(chunks,0,0,0,1) LIMIT '+str(limit),params)]
            rows=fetch('"'+q.replace('"','""')+'"')
            if typos:
                groups=[]
                for word in words:
                    known=set();possible=sorted(stems(spelling_variants(word)))
                    for offset in range(0,len(possible),400):
                        part=possible[offset:offset+400]
                        known.update(r[0] for r in db.execute('SELECT term FROM phrase_vocabulary WHERE term IN ('+','.join('?' for _ in part)+')',part))
                    original=next(iter(stems([word])),word)
                    if len(word)>=4:
                        prefix=original[:2]
                        for row in db.execute('SELECT term FROM phrase_vocabulary WHERE term>=? AND term<? AND length(term) BETWEEN ? AND ? LIMIT 400',(prefix,prefix+'\uffff',max(1,len(original)-2),len(original)+2)):
                            if edit_distance(original,row[0],2)<=2:known.add(row[0])
                    # Last-word completion is explicit and verified in the text.
                    options=['"'+t.replace('"','""')+'"' for t in sorted(known)[:80]]
                    if word==words[-1] and len(word)>=3:options.append('"'+word+'"*')
                    if not options:options=['"'+word+'"']
                    groups.append('('+' OR '.join(options)+')')
                rows+=fetch(' AND '.join(groups))
                if len(rows)<30:rows+=fetch(' OR '.join(groups),180)
    seen=set()
    for r in rows:
        key=(r['cid'],r['seq'],r['text'])
        if key in seen:continue
        seen.add(key);matched=near_phrase(r['text'],q,typos)
        if matched:add({'id':r['cid'],'title':r['title']},r['seq'],r['text'],matched)
    results.sort(key=lambda r:(r['score'],r['seq']<0,r['title']))
    unique={}
    for r in results:unique.setdefault((r['cid'],r['seq']),r)
    out={'results':list(unique.values())[:60],'mode':'exact + typos' if typos else 'exact phrase'}
    coverage=archive.coverage()
    if coverage['available']>coverage['indexed']:out['notice']=f"Content search covers {coverage['indexed']} indexed of {coverage['available']} available chats."
    return out
