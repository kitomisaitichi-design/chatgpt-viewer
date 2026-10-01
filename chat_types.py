"""Classify saved products without inspecting prompts, titles or code."""
import json, re
from functools import lru_cache
from pathlib import Path

PRODUCT_FIELDS=('chat_kind','chatKind','surface','product','conversation_mode','conversation_origin','client','source')
MODELS=('resolved_model_slug','model_slug','default_model_slug')

def work_model(value):
    if not isinstance(value,str):return False
    value=value.lower()
    # Saved Work model families also appear without a product suffix.
    return bool(re.search(r'(?:[-_])wm(?:$|[-_])|(?:^|[-_.])(?:luna|terra|astra)(?:$|[-_.])|(?:^|[-_])6(?:[.-]1)?[-_.]sol(?:$|[-_.])',value))

def free_account(data):
    if not isinstance(data,dict):return False
    candidates=[data]
    for key in ('metadata','account','subscription','owner'):
        if isinstance(data.get(key),dict):candidates.append(data[key])
    for source in candidates:
        if source.get('is_free_user') is True or source.get('is_free_account') is True or source.get('is_paid_user') is False or source.get('is_paid_account') is False:return True
        for key in ('account_plan','account_type','plan_type','subscription_plan','subscription_tier','plan','tier'):
            value=source.get(key)
            if isinstance(value,str) and value.strip().lower() in ('free','chatgpt-free','chatgpt free'):return True
    return False

def canonical_kind(value):
    value=re.sub(r'[ _]+','-',str(value or '').strip().lower())
    if value in ('codex','codex-chat','codex-cli','codex-cli-rs','codex-desktop','openai-codex'):return 'codex'
    if value in ('work','work-chat','chatgpt-work','workmode','work-mode'):return 'work'
    return 'chat'

def surface_signal(data,models=True):
    if not isinstance(data,dict):return None
    meta=data.get('metadata') if isinstance(data.get('metadata'),dict) else {}
    explicit=[]
    for source in (data,meta):
        for key in PRODUCT_FIELDS:
            value=source.get(key)
            if isinstance(value,dict):value=value.get('kind') or value.get('type') or value.get('name')
            if not isinstance(value,str):continue
            kind=canonical_kind(value)
            if kind!='chat':explicit.append((kind,'Saved '+key+': '+value))
        # Native Codex sessions identify their producer. Work may contain Codex
        # subagent activity; those message payloads are not a product marker.
        if source.get('originator') in ('codex_cli_rs','codex_cli','codex_desktop'):
            explicit.append(('codex','Saved native Codex originator: '+source['originator']))
    if explicit:return next((s for s in explicit if s[0]=='codex'),explicit[0])
    if models:
        for source in (data,meta):
            for key in MODELS:
                value=source.get(key)
                if work_model(value):
                    if re.search(r'(?:^|[-_.])luna(?:$|[-_.])',value.lower()) and free_account(data):continue
                    return 'work','Inferred from saved Work model marker: '+value
    for source in (data,meta):
        if isinstance(source.get('work_activity'),dict) and source['work_activity'].get('groups'):
            return 'work','Saved Work activity metadata'
    return None

def prefer_signal(first,second):
    if not first:return second
    if not second:return first
    def strength(s):return (s[1].startswith('Saved '),s[0]=='codex')
    return second if strength(second)>strength(first) else first

@lru_cache(maxsize=1024)
def _header(path,mtime,size):
    try:
        with Path(path).open(encoding='utf-8-sig',errors='replace') as stream:head=stream.read(131072)
    except OSError:return {}
    if not head.lstrip().startswith('{'):return {}
    # Only complete top-level values before the conversation body count. Using
    # a JSON decoder prevents quoted message text from becoming type evidence.
    decoder=json.JSONDecoder();result={};pos=head.index('{')+1
    while pos<len(head):
        pos+=len(head[pos:])-len(head[pos:].lstrip(' \t\r\n,'))
        if pos>=len(head) or head[pos]=='}':break
        try:
            key,end=decoder.raw_decode(head,pos);pos=end
            pos+=len(head[pos:])-len(head[pos:].lstrip())
            if head[pos]!=':':break
            pos+=1;pos+=len(head[pos:])-len(head[pos:].lstrip())
            if key in ('mapping','messages','chatlog'):break
            if key=='conversation':
                # Nested exporter envelopes are supported after full parsing.
                break
            value,pos=decoder.raw_decode(head,pos)
            if key in (*PRODUCT_FIELDS,*MODELS,'metadata','originator','id','conversation_id','title','create_time','update_time','url','project','account','subscription','owner','account_plan','plan_type','account_type','subscription_plan','subscription_tier','is_free_user','is_free_account','is_paid_user','is_paid_account'):result[key]=value
        except (ValueError,IndexError):break
    return result

def source_header(path):
    path=Path(path)
    if path.suffix.lower()!='.json':return {}
    try:st=path.stat();return dict(_header(str(path),st.st_mtime_ns,st.st_size))
    except OSError:return {}

def source_surface_hint(path):return surface_signal(source_header(path))
