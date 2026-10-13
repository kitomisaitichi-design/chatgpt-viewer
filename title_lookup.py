"""Metadata-only title matching; never loads or searches message bodies."""
import re, unicodedata
from functools import lru_cache

@lru_cache(maxsize=16384)
def normalized(text):
    return ''.join(c for c in unicodedata.normalize('NFKD',text) if not unicodedata.combining(c)).casefold()

def distance(a,b,limit):
    if abs(len(a)-len(b))>limit:return limit+1
    previous=list(range(len(b)+1))
    for i,letter in enumerate(a,1):
        row=[i]
        for j,other in enumerate(b,1):row.append(min(row[-1]+1,previous[j]+1,previous[j-1]+(letter!=other)))
        if min(row)>limit:return limit+1
        previous=row
    return previous[-1]

def lookup(chats,query,cid=None,cids=None,limit=240):
    q=' '.join(normalized(str(query or '')).split())
    if not q:return {'results':[],'mode':'Conversation titles','more':False}
    words=re.findall(r'[^\W_]+',q,re.U);hits=[];possible=[];similar={}
    def hit(c,score,match='Title match'):
        title=c.get('alias') or c.get('title') or c['id']
        return dict(cid=c['id'],seq=-1,title=title,snippet=title,score=score,match=match,updated=c.get('updated') or c.get('created') or 0)
    for c in chats:
        if c.get('trashed') or cid and c['id']!=cid or cids is not None and c['id'] not in cids:continue
        names=[normalized(str(c.get('alias') or c.get('title') or '')),normalized(str(c.get('title') or ''))]
        tokens=set(re.findall(r'[^\W_]+',' '.join(names),re.U));score=0 if normalized(c['id'])==q else 99
        for i,name in enumerate(names):
            if name==q:score=min(score,i)
            elif name.startswith(q):score=min(score,2+i)
            elif q in name:score=min(score,4+i)
        if words and all(any(t.startswith(w) for t in tokens) for w in words):score=min(score,6)
        if words and all(any(w in t for t in tokens) for w in words):score=min(score,8)
        if score<99:hits.append(hit(c,score))
        elif len(q)>=4 and 0<len(words)<=5 and len(possible)<400 and all(any(t[:1]==w[:1] and abs(len(t)-len(w))<=2 for t in tokens) for w in words):possible.append((c,tokens))
    if not hits:
        for c,tokens in possible:
            cost=0
            for word in words:
                threshold=2 if len(word)>7 else 1;best=3
                for token in tokens:
                    if len(word)<4 or len(token)>64 or token[:1]!=word[:1]:continue
                    key=(word,token)
                    if key not in similar:similar[key]=distance(word,token,threshold)
                    best=min(best,similar[key])
                if best>threshold:break
                cost+=best
            else:hits.append(hit(c,20+cost,'Similar title'))
    hits.sort(key=lambda h:(h['score'],-float(h['updated']),h['cid']))
    return dict(results=hits[:limit],mode='Conversation titles',more=len(hits)>limit)
