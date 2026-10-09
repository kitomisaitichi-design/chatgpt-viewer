"""Resolve source-file references to conversations already indexed in this viewer.

The lookup exposes only existing chat IDs/titles; it never opens an arbitrary
filesystem path supplied by message content or the browser.
"""
from pathlib import Path, PureWindowsPath

SOURCE_SUFFIXES = {'.jsonl', '.json', '.md'}


def parsed_file_links(archive, reference, limit=24):
    if not isinstance(reference, str) or not 1 <= len(reference) <= 1024:
        return []
    reference = reference.strip().strip('<>"\'')
    if not reference or '\x00' in reference:
        return []
    filename = PureWindowsPath(reference.replace('/', '\\')).name
    if not filename or Path(filename).suffix.lower() not in SOURCE_SUFFIXES:
        return []
    normalized = reference.replace('\\', '/').casefold()
    has_directories = '/' in normalized
    matched = []
    seen = set()
    with archive.connect() as db:
        rows = db.execute("""
            SELECT c.id,c.title,c.kind,c.path
              FROM chats c
              LEFT JOIN organization o ON o.cid=c.id
             WHERE COALESCE(o.trashed,0)=0
               AND NOT EXISTS (SELECT 1 FROM local_removals r WHERE r.cid=c.id)
            UNION ALL
            SELECT e.cid,
                   COALESCE(json_extract(e.metadata,'$.title'),e.cid),
                   'chat',e.path
              FROM manifest_entries e
             WHERE e.available=1
               AND NOT EXISTS (SELECT 1 FROM chats c WHERE c.id=e.cid)
               AND NOT EXISTS (SELECT 1 FROM local_removals r WHERE r.cid=e.cid)
        """).fetchall()
    for row in rows:
        path = Path(row['path'])
        if path.name.casefold() != filename.casefold() or not path.is_file():
            continue
        if has_directories:
            candidate = str(path).replace('\\', '/').casefold()
            # Absolute/relative references must match a suffix of the indexed
            # path. A basename-only reference deliberately finds every match.
            if candidate != normalized and not candidate.endswith('/' + normalized.lstrip('/')):
                continue
        if row['id'] in seen:
            continue
        matched.append(dict(id=row['id'], title=row['title'] or path.stem,
                            filename=path.name, kind=row['kind'] or 'chat'))
        seen.add(row['id'])
        if len(matched) >= limit:
            break
    return matched
