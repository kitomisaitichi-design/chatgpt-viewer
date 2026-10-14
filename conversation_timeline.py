"""Bounded, read-only positions for navigating an archived conversation."""
import re


def build_timeline(rows, max_points=480):
    """Return equally spaced positions across all visible messages."""
    total = len(rows)
    if not total:
        return {'total': 0, 'items': []}
    limit = max(2, min(600, int(max_points)))
    indices = range(total) if total <= limit else sorted({round(i * (total - 1) / (limit - 1)) for i in range(limit)})
    items = []
    for index in indices:
        row = rows[index]
        excerpt = re.sub(r'\s+', ' ', str(row['text'] or '')[:440]).strip()
        excerpt = re.sub(r'\ue200[^\ue201]{0,100}\ue201', ' ', excerpt).strip()
        items.append({
            'index': index,
            'seq': int(row['seq']),
            'role': str(row['role'] or 'assistant'),
            'channel': str(row['channel'] or ''),
            'time': row['time'],
            'preview': excerpt[:200] or ('User message' if row['role'] == 'user' else 'Saved message'),
        })
    return {'total': total, 'items': items}
