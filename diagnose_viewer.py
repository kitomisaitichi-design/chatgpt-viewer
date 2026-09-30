#!/usr/bin/env python3
"""Read-only local checks. Report counts/timings, never messages, paths or tokens."""
import argparse
import json
import platform
import re
import socket
import sqlite3
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def local_version(app):
    try:
        source = (app / 'viewer.py').read_text(encoding='utf-8')
        match = re.search(r"(?:version|VERSION)\s*=\s*['\"]([\d.]+)['\"]", source)
        return match.group(1) if match else None
    except OSError:
        return None


def session_target(session):
    parsed = urllib.parse.urlsplit(session['url'])
    # This checker never sends the local session secret to another host.
    if (parsed.scheme != 'http' or parsed.hostname not in ('127.0.0.1', 'localhost')
            or parsed.username or parsed.password or not parsed.port):
        raise ValueError('Invalid local session')
    token = urllib.parse.parse_qs(parsed.query).get('token', [''])[0]
    if not token or not re.fullmatch(r'[A-Za-z0-9_-]+', token):
        raise ValueError('Invalid session token')
    return 'http://127.0.0.1:' + str(parsed.port), token


def probe(base, token, endpoint, timeout=4):
    started = time.monotonic()
    result = {'endpoint': endpoint}
    # Bypass environment/system proxies for this strictly loopback request.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    request = urllib.request.Request(base + endpoint, headers={
        'Cookie': 'viewer_token=' + token, 'Connection': 'close'})
    try:
        with opener.open(request, timeout=timeout) as response:
            result['http_status'] = response.status
            result['content_length'] = response.headers.get('Content-Length')
            result['content_encoding'] = response.headers.get('Content-Encoding', 'identity')
            result['headers_ms'] = round((time.monotonic() - started) * 1000)
            body = bytearray();result['bytes_received'] = 0
            while len(body) <= 4 * 1024 * 1024:
                if time.monotonic() - started > timeout:
                    raise TimeoutError()
                chunk = response.read1(min(64 * 1024, 4 * 1024 * 1024 + 1 - len(body)))
                if not chunk:
                    break
                body.extend(chunk)
                result['bytes_received'] = len(body)
        result['bytes'] = len(body)
        if len(body) > 4 * 1024 * 1024:
            result['outcome'] = 'response_too_large'
        else:
            data = json.loads(body)
            result['outcome'] = 'ok'
            if endpoint == '/api/health':
                result.update(version=data.get('version'), pid=data.get('pid'),
                              scanning=bool(data.get('scanning')))
                if isinstance(data.get('transfers'), dict):
                    result['transfers']={group:[{key:row.get(key) for key in
                        ('endpoint','bytes','written','encoding','elapsed_ms')} for row in
                        data['transfers'].get(group, [])] for group in ('active','recent')}
            else:
                chats = data.get('chats')
                result['returned_chats'] = len(chats) if isinstance(chats, list) else None
                result['revision'] = data.get('revision')
                result['cache_loading'] = data.get('cacheLoading')
                scan = data.get('scan') or {}
                result['scan'] = {key: scan.get(key) for key in
                                  ('scanning', 'files', 'processed', 'indexed')}
                result['scan_error_count'] = len(scan.get('errors') or [])
                coverage = data.get('coverage') or {}
                result['coverage'] = {key: coverage.get(key) for key in
                                      ('expected', 'indexed', 'available', 'missing')}
    except urllib.error.HTTPError as error:
        result.update(outcome='http_error', http_status=error.code)
    except (TimeoutError, socket.timeout):
        result['outcome'] = 'timeout'
    except urllib.error.URLError as error:
        result['outcome'] = 'timeout' if isinstance(error.reason, TimeoutError) else 'connection_failed'
    except Exception as error:
        # Exception strings can contain URLs, tokens or private filenames.
        result.update(outcome='invalid_response', error_type=type(error).__name__)
    result['elapsed_ms'] = round((time.monotonic() - started) * 1000)
    return result


def database_report(data_dir):
    dbpath = data_dir / 'archive.sqlite3'
    result = {'exists': dbpath.is_file()}
    if not result['exists']:
        return result
    try:
        result['bytes'] = dbpath.stat().st_size
        wal = data_dir / 'archive.sqlite3-wal'
        result['wal_bytes'] = wal.stat().st_size if wal.is_file() else 0
        db = sqlite3.connect(dbpath.resolve().as_uri() + '?mode=ro', uri=True, timeout=1)
        try:
            for table in ('chats', 'manifest_entries', 'scanned_files'):
                try:
                    result[table + '_rows'] = db.execute('SELECT COUNT(*) FROM ' + table).fetchone()[0]
                except sqlite3.Error as error:
                    result[table + '_error'] = type(error).__name__
            settings = {key: json.loads(value) for key, value in db.execute(
                "SELECT key,value FROM settings WHERE key IN ('scan_start','scan_up','scanPaused')")}
            root = settings.get('scan_start')
            result['scan_folder_saved'] = bool(root)
            if root:
                result['scan_folder_exists'] = Path(root).is_dir()
            result['scan_up'] = settings.get('scan_up')
            result['scan_paused'] = settings.get('scanPaused')
        finally:
            db.close()
    except Exception as error:
        result['error_type'] = type(error).__name__
    return result


def diagnose(app, data_dir=None, timeout=4):
    data_dir = data_dir or app / '.viewer-data'
    report = {'checker_version': 2, 'platform': platform.system(),
              'python_version': platform.python_version(), 'local_app_version': local_version(app),
              'embedded_runtime_present': (app / 'runtime' / 'python.exe').is_file(),
              'semantic_environment_present': (app / '.semantic-env' / 'Scripts' / 'python.exe').is_file(),
              'session_found': (data_dir / 'session.json').is_file(), 'requests': []}
    try:
        session_file = data_dir / 'session.json'
        session = json.loads(session_file.read_text(encoding='utf-8-sig'))
        base, token = session_target(session)
        report['session_age_seconds'] = round(max(0, time.time() - session_file.stat().st_mtime))
        report['session_pid'] = session.get('pid')
        health = probe(base, token, '/api/health', timeout)
        report['requests'].append(health)
        state = probe(base, token, '/api/state', timeout)
        report['requests'].append(state)
        # Check whether the whole server stalls while a status request is stuck.
        report['requests'].append(probe(base, token, '/api/health', timeout))
        if health['outcome'] == 'ok' and health.get('version') != report['local_app_version']:
            report['finding'] = 'running_server_version_differs_from_files'
        elif health.get('http_status') == 403 or state.get('http_status') == 403:
            report['finding'] = 'session_rejected'
        elif health['outcome'] == 'ok' and state['outcome'] == 'timeout':
            report['finding'] = 'server_alive_but_status_request_stalls'
        elif state['outcome'] == 'ok':
            report['finding'] = 'status_responds_outside_browser'
        else:
            report['finding'] = 'server_or_endpoint_unavailable'
    except Exception as error:
        report.update(finding='session_unavailable', session_error_type=type(error).__name__)
    report['database'] = database_report(data_dir)
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--app', type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument('--data-dir', type=Path)
    parser.add_argument('--timeout', type=float, default=4)
    args = parser.parse_args()
    print('Checking the running viewer. Leave its console and browser open.', flush=True)
    report = diagnose(args.app, args.data_dir, max(0.1, min(args.timeout, 10)))
    output = args.app / 'VIEWER-DIAGNOSTICS.json'
    output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print('\nResult: ' + report['finding'])
    for item in report['requests']:
        print(item['endpoint'] + ': ' + item['outcome'] + ' (' + str(item['elapsed_ms']) + ' ms)')
    print('\nSaved VIEWER-DIAGNOSTICS.json beside START-VIEWER.bat.')
    print('Attach that JSON file in the conversation. It contains no chat text or session token.')


if __name__ == '__main__':
    main()
