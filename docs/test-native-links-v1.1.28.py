#!/usr/bin/env python3
"""Isolated native source-link resolution and authorization checks."""
import http.cookiejar
import json
import pathlib
import sys
import tempfile
import threading
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent.parent))
from linked_sources import parsed_file_links
from viewer import Archive,Server

with tempfile.TemporaryDirectory(prefix='viewer-linked-sources-') as directory:
    root=pathlib.Path(directory)
    exports=root/'export';exports.mkdir()
    (exports/'conversation.md').write_text('# Example\n## User\nHello\n',encoding='utf-8')
    filename='rollout-2026-10-09T03-32-20-01a11f93-c427-7ad1-9786-203789fdae4c.jsonl'
    session=exports/filename
    session.write_text(
        json.dumps({'type':'session_meta','payload':{'id':'native-session','originator':'codex_cli','timestamp':'2026-10-09'}})
        +'\n'+json.dumps({'type':'response_item','payload':{'role':'assistant','content':[{'type':'output_text','text':'Saved assistant text'}]}})+'\n',
        encoding='utf-8')
    a=Archive(root/'db',background_process=False)
    server=None
    try:
        a.scan(exports,0)
        matches=parsed_file_links(a,filename)
        assert len(matches)==1 and matches[0]['id']=='native-session',matches
        assert len(parsed_file_links(a,'conversation.md'))==1
        assert parsed_file_links(a,'not-indexed.txt')==[]
        assert parsed_file_links(a,'hidden.jsonl')==[]
        assert parsed_file_links(a,'../secret/other.jsonl')==[]
        # An indexed path should identify its own source, not a similarly
        # named arbitrary path outside the scanned and parsed sources.
        assert len(parsed_file_links(a,str(session)))==1
        server=Server(('127.0.0.1',0),a)
        worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
        base='http://127.0.0.1:'+str(server.server_port)
        endpoint=base+'/api/linked-source?'+urllib.parse.urlencode({'name':filename})
        try:
            urllib.request.urlopen(endpoint,timeout=3)
            raise AssertionError('Unauthenticated source resolution permitted')
        except urllib.error.HTTPError as e:assert e.code==403
        opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        with opener.open(base+'/?token='+server.token,timeout=3) as response:response.read()
        with opener.open(endpoint,timeout=3) as response:
            data=json.load(response)
        assert data['matches'][0]['id']=='native-session'
        assert 'path' not in data['matches'][0]
        print('native indexed source resolution: pass; arbitrary paths: rejected; cookie boundary: pass')
    finally:
        if server:server.shutdown();server.server_close()
        a.close()
print('native link fixtures removed')
