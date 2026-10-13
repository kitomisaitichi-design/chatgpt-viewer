"""Open recorded conversation folders and explicitly linked local directories."""
from pathlib import Path
from native_codex import conversation_metadata, local_references, reference_path, session_header

def resolve_folder(archive,cid,target='workspace',reference=''):
    if archive.ui_cache is not None:
        with archive.ui_cache_lock:chat=dict(archive.ui_cache['chats'].get(cid) or {})
    else:chat=next((c for c in archive.catalog() if c['id']==cid),{})
    if not chat:raise ValueError('This conversation is no longer available.')
    source=Path(chat['path'])
    if target=='source':folder=source.parent
    elif target=='workspace':
        value=chat.get('workspace')
        if not value and source.suffix.lower()=='.jsonl':value=conversation_metadata(session_header(source))['workspace']
        if not value:raise ValueError('This conversation has no recorded home folder. Use Source folder instead.')
        folder=reference_path(value)
        if not folder.is_absolute():raise ValueError('The recorded home folder is not an absolute local path.')
    elif target=='reference':
        raw,_=archive.source_data(cid)
        if reference not in local_references(raw):raise ValueError('This folder is not explicitly linked by this conversation.')
        folder=reference_path(reference)
        if not folder.is_absolute():folder=source.parent/folder
    else:raise ValueError('Choose Home folder, Source folder or a linked folder.')
    folder=folder.resolve()
    if not folder.is_dir():raise FileNotFoundError('This folder is missing or unavailable: '+str(folder))
    return folder

def open_conversation_folder(archive,cid,target='workspace',reference=''):
    from folder_tools import open_folder
    return open_folder(resolve_folder(archive,cid,target,reference))
