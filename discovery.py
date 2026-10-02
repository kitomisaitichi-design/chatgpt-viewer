"""Shared reader and backup folder scope, traversal, exclusions and limits."""
import os,time
from pathlib import Path
SKIP = {'.git','.svn','node_modules','__pycache__','.viewer-data','.venv','venv',
        'Windows','Program Files','Program Files (x86)','$Recycle.Bin','System Volume Information',
        'AppData','.cache','.npm','.local','exporter-source',
        '.semantic-env','.semantic-packages','.semantic-staging','.semantic-cache','.semantic-old'}
SKIP_LOWER={s.lower() for s in SKIP}|{'attachments','attachment-errors','files','images','assets','html'}
def scan_boundary(start,up=0):
    start=Path(start).expanduser().resolve()
    if not start.is_dir():raise ValueError('Choose an existing folder.')
    root=start
    for _ in range(max(0,min(int(up),4))):
        if root.parent==root or root.parent.parent==root.parent:break
        root=root.parent
    return start,root

def iter_documents(start,root,event,status,app,exclude=()):
    """Near folders first; yield each candidate without collecting the whole tree."""
    stages=[start];current=start
    while current!=root:
        current=current.parent;stages.append(current)
    visited=set();candidates=0;directories=0
    def note(error):
        if len(status['errors'])<40:status['errors'].append(str(error))
    for stage in stages:
        for base,dirs,files in os.walk(stage,followlinks=False,onerror=note):
            if event.is_set():return
            basepath=Path(base);key=str(basepath.resolve())
            if any(basepath.resolve().is_relative_to(x) for x in exclude):dirs.clear();continue
            if key in visited:dirs.clear();continue
            visited.add(key);directories+=1
            status['directories']=directories;status['current_folder']=str(basepath)
            if directories>25000:
                note('Directory limit reached. Choose a narrower export folder.');return
            depth=len(basepath.relative_to(root).parts)
            dirs[:]=[d for d in dirs if d.lower() not in SKIP_LOWER and not d.startswith('.') and
                     not (basepath/d).is_symlink() and str((basepath/d).resolve()) not in visited and
                     (basepath/d).resolve() not in (app/'web',app/'tests',app/'runtime',app/'models')]
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
                candidates+=1;status['files']=candidates
                if candidates>100000:
                    note('File limit reached. Choose a narrower export folder.');return
                yield f
            # Give foreground HTTP handlers a turn even in directories with no chats.
            time.sleep(.002)
