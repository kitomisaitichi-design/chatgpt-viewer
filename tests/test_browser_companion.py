import copy, json, tempfile, time, unittest
from pathlib import Path
from unittest.mock import patch
from viewer import Archive, Server
from deletion_queue import DeletionQueue, read
from library_files import FileCatalog
from browser_companion import graph_hash, scope_key


class BrowserQueue(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.a=Archive(self.root/'data',background_process=False)
        self.cid='12345678-1234-1234-1234-123456789abc'
        self.body=dict(id=self.cid,title='Saved',mapping={
            'u':dict(parent=None,children=['a'],message=dict(id='u',author=dict(role='user'),content=dict(content_type='text',parts=['Hello']))),
            'a':dict(parent='u',children=[],message=dict(id='a',author=dict(role='assistant'),content=dict(content_type='text',parts=['Hi'])))},current_node='a')
        self.path=self.root/'chat.json';self.path.write_text(json.dumps(self.body))
        self.a.store(next(self.a.read_items(self.path)),self.path,'fp',self.root,{})
        self.q=DeletionQueue(self.a,FileCatalog(self.a));self.q.browser.endpoint='http://127.0.0.1:23456'
        self.start=patch.object(self.q,'start');self.start.start()
        self.client=dict(client='one',kind='companion',scope=dict(user='test-user',account=None),connected=True)

    def tearDown(self):
        self.start.stop();self.q.close();self.a.close();self.temp.cleanup()

    def clear_wait(self):
        with self.a.connect() as db:db.execute('UPDATE browser_requests SET next_at=0')

    def run_job(self,mode='preserve'):
        self.q.enqueue([self.cid],mode);self.q.browser.poll(dict(self.client,heartbeat=True))
        self.q.action('run',[r['id'] for r in self.q.rows()]);self.q.tick()
        return self.q.rows()[0]

    def request(self,client=None):
        self.clear_wait();return self.q.browser.poll(client or self.client).get('request')

    def result(self,req,result):
        return self.q.browser.result(dict(client='one',**req,result=result))

    def test_markdown_primary_uses_verified_linked_json_backup(self):
        from deletion_queue import write,digest
        row=self.run_job();base=self.a.data_dir/'deletion-recovery'/row['id']
        original=base/'source.json';linked=base/'sources'/'linked.json';linked.parent.mkdir(exist_ok=True);original.rename(linked)
        index=read(base/'index.json');index['sources']=[dict(copy=str(linked),sha256=digest(linked))];write(base/'index.json',index)
        req=self.request();self.result(req,dict(ok=True,status=200,data=self.body))
        self.assertEqual(self.request()['phase'],'delete')

    def test_no_exporter_required_and_one_lease(self):
        row=self.run_job();self.assertEqual(row['scope'],scope_key(self.client['scope']))
        command=read(Path(row['root'])/'.viewer-queue/commands'/(row['id']+'.json'))
        self.assertEqual(command['schema'],'offline-viewer/native-delete-v1')
        req=self.request();self.assertEqual(req['phase'],'preflight')
        self.assertIsNone(self.q.browser.poll(self.client).get('request'))
        self.assertFalse(self.q.browser.permit(dict(req,client='wrong'))['allowed'])
        self.assertTrue(self.q.browser.permit(dict(req,client='one'))['allowed'])
        self.result(req,dict(ok=True,status=200,data=self.body));self.q.tick()
        self.assertTrue((self.a.data_dir/'deletion-recovery'/row['id']/'remote.json').exists())
        req=self.request();self.assertEqual(req['phase'],'delete')
        self.result(req,dict(ok=True,status=200));req=self.request();self.assertEqual(req['phase'],'verify')
        self.result(req,dict(ok=False,status=404));self.q.tick()
        self.assertEqual(self.q.rows()[0]['state'],'confirmed')
        self.assertEqual(self.a.catalog(),[])
        self.assertIn(row['cid'],self.a.removed_ids())
        self.assertTrue(self.path.exists())
        with self.assertRaises(ValueError):self.result(req,dict(ok=False,status=404))

    def test_old_remote_chat_missing_twice_cleans_local_source_without_patch(self):
        row=self.run_job('library')
        self.assertTrue(self.path.is_file())
        req=self.request();self.assertEqual(req['op'],'get')
        self.result(req,dict(ok=False,status=404));self.q.tick()
        self.assertEqual(self.q.rows()[0]['state'],'retrying')
        self.assertTrue(self.path.is_file())
        self.assertNotIn(self.cid,self.a.removed_ids())
        req=self.request()
        self.assertEqual((req['phase'],req['op']),('absence-confirm','get'))
        self.result(req,dict(ok=False,status=410));self.q.tick()
        self.assertEqual(self.q.rows()[0]['state'],'confirmed')
        self.assertFalse(self.path.exists())
        self.assertIn(self.cid,self.a.removed_ids())
        with self.a.connect() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM browser_absence').fetchone()[0],0)
        proof=json.loads(self.q.rows()[0]['receipt'])
        self.assertEqual(proof['absence_checks'],2)
        self.assertEqual(proof['absence_statuses'],[404,410])
        self.assertEqual(proof['remote_state'],'deleted')

    def test_first_absence_is_not_deletion_proof_and_preserve_keeps_source(self):
        row=self.run_job()
        req=self.request();self.result(req,dict(ok=False,status=404));self.q.tick()
        self.assertTrue(self.path.is_file())
        self.assertNotIn(self.cid,self.a.removed_ids())
        req=self.request();self.assertEqual(req['phase'],'absence-confirm')
        self.result(req,dict(ok=True,status=200,data={**self.body,'is_visible':False}));self.q.tick()
        self.assertEqual(self.q.rows()[0]['state'],'confirmed')
        self.assertTrue(self.path.is_file())
        self.assertIn(self.cid,self.a.removed_ids())

    def test_network_failure_and_429_never_count_as_second_absence(self):
        self.run_job('library')
        req=self.request();self.result(req,dict(ok=False,status=404))
        req=self.request();self.assertEqual(req['phase'],'absence-confirm')
        self.result(req,dict(ok=False,status=0,error='Network disconnected'))
        self.q.tick()
        self.assertEqual(self.q.rows()[0]['state'],'retrying')
        with self.a.connect() as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM browser_absence').fetchone()[0],0)
        req=self.request();self.assertEqual(req['phase'],'preflight')
        self.result(req,dict(ok=False,status=404))
        req=self.request();self.assertEqual(req['phase'],'absence-confirm')
        self.result(req,dict(ok=False,status=429,retryAfter='40'))
        with self.a.connect() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM browser_absence').fetchone()[0],0)
            self.assertGreater(db.execute("SELECT until FROM browser_throttle WHERE key='rate-limit'").fetchone()[0],time.time()+35)
        self.assertTrue(self.path.is_file())
        self.assertNotIn(self.cid,self.a.removed_ids())
        with self.a.connect() as db:db.execute("UPDATE browser_throttle SET until=0")
        req=self.request();self.assertEqual(req['phase'],'preflight')
        self.result(req,dict(ok=False,status=404))
        req=self.request();self.assertEqual(req['phase'],'absence-confirm')
        self.result(req,dict(ok=False,status=404));self.q.tick()
        self.assertEqual(self.q.rows()[0]['state'],'confirmed')
        self.assertFalse(self.path.exists())

    def test_unauthorized_does_not_count_as_absence(self):
        self.run_job('library')
        req=self.request();self.result(req,dict(ok=False,status=410))
        req=self.request();self.result(req,dict(ok=False,status=401,error='Session expired'))
        self.q.tick()
        self.assertTrue(self.path.is_file())
        self.assertEqual(self.q.rows()[0]['state'],'paused')
        with self.a.connect() as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM browser_absence').fetchone()[0],0)

    def test_transient_404_followed_by_live_chat_cannot_delete_anything(self):
        self.run_job('library')
        req=self.request();self.result(req,dict(ok=False,status=404))
        req=self.request();self.assertEqual(req['phase'],'absence-confirm')
        self.result(req,dict(ok=True,status=200,data=self.body));self.q.tick()
        self.assertEqual(self.q.rows()[0]['state'],'failed')
        self.assertIn('inconsistent availability',self.q.rows()[0]['error'])
        self.assertTrue(self.path.is_file())
        self.assertNotIn(self.cid,self.a.removed_ids())
        self.assertIsNone(self.request())

    def test_malformed_success_body_never_counts_as_online_absence(self):
        self.run_job('library')
        req=self.request()
        self.result(req,dict(ok=True,status=200,data=['not a conversation']))
        self.q.tick()
        self.assertEqual(self.q.rows()[0]['state'],'failed')
        self.assertIn('Unrecognized conversation response',self.q.rows()[0]['error'])
        self.assertTrue(self.path.is_file())
        self.assertNotIn(self.cid,self.a.removed_ids())

    def test_malformed_second_check_fails_without_local_cleanup(self):
        self.run_job('library')
        req=self.request();self.result(req,dict(ok=False,status=404))
        req=self.request();self.assertEqual(req['phase'],'absence-confirm')
        self.result(req,dict(ok=True,status=200,data={'items':['unrelated']}))
        self.q.tick()
        self.assertEqual(self.q.rows()[0]['state'],'failed')
        self.assertTrue(self.path.is_file())
        self.assertNotIn(self.cid,self.a.removed_ids())

    def test_native_owner_precedes_extension_but_matching_exporter_can_handoff(self):
        self.run_job();native=dict(self.client,client='native-owner',kind='native',heartbeat=True)
        self.q.browser.poll(native)
        self.assertIsNone(self.request())
        native['heartbeat']=False;req=self.request(native);self.assertIsNotNone(req)
        self.q.browser.result(dict(client='native-owner',**req,result=dict(ok=True,status=200,data=self.body)))
        exporter=dict(self.client,client='exporter-owner',kind='exporter',heartbeat=True)
        self.q.browser.poll(exporter);self.assertIsNone(self.request(native))
        exporter['heartbeat']=False;self.assertIsNotNone(self.request(exporter))

    def test_revision_change_stops_before_delete(self):
        row=self.run_job();req=self.request();changed=copy.deepcopy(self.body);changed['mapping']['a']['message']['content']['parts']=['New reply']
        self.result(req,dict(ok=True,status=200,data=changed));self.q.tick()
        self.assertEqual(self.q.rows()[0]['state'],'failed');self.assertIn('different revision',self.q.rows()[0]['error']);self.assertIsNone(self.request())
        self.assertNotEqual(graph_hash(changed),graph_hash(self.body))

    def test_pause_and_uncertain_mutation_verify_before_retry(self):
        self.run_job();req=self.request();self.result(req,dict(ok=True,status=200,data=self.body));req=self.request();self.assertEqual(req['phase'],'delete')
        self.q.action('pause');self.assertFalse(self.q.browser.permit(dict(req,client='one'))['allowed'])
        self.result(req,dict(ok=False,status=0,error='Connection interrupted'));self.q.tick()
        self.assertEqual(self.q.rows()[0]['state'],'paused')
        self.q.action('run',[r['id'] for r in self.q.rows()]);self.q.tick();req=self.request();self.assertEqual(req['phase'],'verify')

    def test_scope_handoff_and_persisted_cooldown(self):
        self.run_job();foreign=dict(self.client,client='foreign',scope=dict(user='other',account=None));self.assertIsNone(self.q.browser.poll(foreign).get('request'))
        exporter=dict(self.client,client='exporter-owner',kind='exporter',heartbeat=True);self.q.browser.poll(exporter)
        self.assertIsNone(self.request());exporter['heartbeat']=False;req=self.request(exporter);self.assertIsNotNone(req)
        self.q.browser.result(dict(client='exporter-owner',**req,result=dict(ok=False,status=429,retryAfter='900')))
        self.assertIsNone(self.q.browser.poll(exporter).get('request'))
        with self.a.connect() as db:self.assertGreater(db.execute('SELECT next_at FROM browser_requests').fetchone()[0],time.time()+800)

    def test_old_completed_check_cannot_stall_new_deletion(self):
        self.run_job()
        with self.a.connect() as db:
            db.execute('INSERT INTO browser_requests VALUES(?,?,?,?,?,?,?,?)',
                       ('completed-old-check','done','','',0,time.time()+3600,0,time.time()-7200))
        req=self.q.browser.poll(self.client).get('request')
        self.assertIsNotNone(req)
        self.assertEqual(req['phase'],'preflight')

    def test_429_cooldown_survives_old_request_cleanup(self):
        self.run_job()
        req=self.request()
        self.result(req,dict(ok=False,status=429,retryAfter='900'))
        with self.a.connect() as db:
            db.execute('DELETE FROM browser_requests')
        self.assertIsNone(self.q.browser.poll(self.client).get('request'))
        with self.a.connect() as db:
            self.assertGreater(db.execute("SELECT until FROM browser_throttle WHERE key='rate-limit'").fetchone()[0],time.time()+800)

    def test_local_browser_pacing_is_short_per_request_not_global_rate_limit(self):
        row=self.run_job()
        req=self.request()
        before=time.time()
        self.result(req,dict(ok=False,status=0,localPacing=True,retryAfter='8',
                             error='Waiting for active ChatGPT traffic'))
        with self.a.connect() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM browser_throttle").fetchone()[0],0)
            stored=db.execute("SELECT * FROM browser_requests WHERE job=?",(row['id'],)).fetchone()
            self.assertEqual(stored['phase'],'preflight')
            self.assertEqual(stored['attempts'],0)
            self.assertGreaterEqual(stored['next_at'],before+7)
            self.assertLess(stored['next_at'],before+11)
            # Another ready authenticated read is not blocked by this job.
            db.execute('INSERT INTO browser_checks VALUES(?,?,?,?,?,0)',
                       ('another-check','other-chat',str(self.root),scope_key(self.client['scope']),time.time()))
            db.execute('UPDATE browser_requests SET updated=? WHERE job=?',(time.time()-120,req['job']))
        self.assertEqual(self.q.browser.poll(self.client)['request']['job'],'another-check')
        receipt=read(self.root/'.viewer-queue/receipts'/(row['id']+'.json'))
        self.assertEqual(receipt['message'],'Waiting for active ChatGPT traffic (local pacing)')
        self.assertEqual(receipt['state'],'retrying')

    def test_local_pacing_does_not_complete_remote_status_check(self):
        self.q.browser.poll(dict(self.client,heartbeat=True))
        self.q.check_remote(self.cid)
        req=self.request()
        self.assertEqual(req['phase'],'check')
        self.result(req,dict(ok=False,status=0,localPacing=True,retryAfter='5'))
        with self.a.connect() as db:
            self.assertEqual(db.execute("SELECT done FROM browser_checks WHERE id=?",(req['job'],)).fetchone()[0],0)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM browser_throttle").fetchone()[0],0)

    def test_per_job_retry_does_not_block_another_ready_job(self):
        self.run_job()
        req=self.request()
        self.result(req,dict(ok=False,status=0,error='Temporary connection failure'))
        with self.a.connect() as db:
            db.execute('INSERT INTO browser_checks VALUES(?,?,?,?,?,0)',
                       ('check-ready','other-chat',str(self.root),scope_key(self.client['scope']),time.time()))
            db.execute('UPDATE browser_requests SET updated=? WHERE job=?',(time.time()-120,req['job']))
        followup=self.q.browser.poll(self.client).get('request')
        self.assertIsNotNone(followup)
        self.assertEqual(followup['job'],'check-ready')

    def test_authenticated_availability_without_index_or_deletion(self):
        self.q.browser.poll(dict(self.client,heartbeat=True));self.q.check_remote(self.cid)
        req=self.request();self.assertEqual(req['phase'],'check');self.result(req,dict(ok=False,status=404))
        self.assertEqual(self.a.catalog()[0]['remote_state'],'unavailable');self.assertFalse(self.a.catalog()[0]['trashed']);self.assertTrue(self.path.exists())

    def test_expired_mutation_lease_is_verified(self):
        self.run_job();req=self.request();self.result(req,dict(ok=True,status=200,data=self.body));req=self.request()
        with self.a.connect() as db:db.execute('UPDATE browser_requests SET expires=0,next_at=0')
        replacement=self.request();self.assertEqual(replacement['phase'],'verify')
        with self.assertRaises(ValueError):self.result(req,dict(ok=True,status=200))


if __name__=='__main__':unittest.main()
