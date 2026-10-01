"""Read saved HTML widgets for an isolated local preview."""
import json,re

def saved_widgets(text):
    values=[]
    for hit in re.finditer('\ue200genui\ue202(.*?)\ue201',text,re.S):
        fence=''
        for line in text[:hit.start()].splitlines():
            marker=re.match(r'^\s*(`{3,}|~{3,})',line)
            if marker:
                char=marker[1][0]
                if not fence:fence=char
                elif fence==char:fence=''
        if fence:continue
        try:value=json.loads(hit[1])
        except ValueError:value={}
        if not isinstance(value,dict) or 'citation' not in value:values.append(value)
    return values

def application_frame(text,index,css,colors,nonce=''):
    values=saved_widgets(text);index=int(index)
    if index<0 or index>=len(values):raise ValueError('Saved app was not found in this message.')
    spec=values[index].get('app_block') or {}
    if str(spec.get('language','')).lower()!='html':raise ValueError('This saved widget is not an HTML app.')
    variables=''
    for key,value in colors.items():
        if key in ('bg','text','muted','border','card','accent') and re.fullmatch(r'#[0-9a-fA-F]{3,8}',value or ''):
            variables+='--viz-'+key+':'+value+';'
    bridge=''
    if re.fullmatch(r'[a-zA-Z0-9-]{20,64}',nonce):
        bridge='<script>(()=>{let t;const report=()=>{clearTimeout(t);t=setTimeout(()=>parent.postMessage({viewerFrame:'+json.dumps(nonce)+',height:document.body.scrollHeight},"*"),30);};new ResizeObserver(report).observe(document.body);report();})()</script>'
    return ('<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            '<style>'+css+'\n:root{'+variables+'}</style></head><body>'+str(spec.get('content') or '')+bridge+'</body></html>').encode('utf-8')
