import json,threading,time,tempfile,unittest,zipfile,hashlib,shutil,subprocess,os
from pathlib import Path
from release_checks import ReleaseChecks,interval,version
from silent_update import stage_release,HOST
class Archive:
 def __init__(self,p):self.data_dir=Path(p);self.values={}
 def settings(self):return dict(self.values)
class ReleaseTests(unittest.TestCase):
 def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.a=Archive(self.tmp.name)
 def finish(self,c):c.worker.join(3);self.assertFalse(c.status()['checking'])
 def test_intervals(self):
  self.assertEqual(interval(None),24)
  for h in (0,12,24,168):self.assertEqual(interval(h),h)
  self.assertEqual(interval(True),24)
 def test_numeric_versions(self):self.assertGreater(version('v1.10.0'),version('1.9.9'))
 def test_persisted_check_and_off(self):
  self.a.values['releaseCheckHours']=0;c=ReleaseChecks(self.a,'1.1.28',lambda:dict(tag_name='v1.1.29'),lambda:100);c.check();self.finish(c)
  self.assertTrue(c.status()['available']);self.assertIsNone(c.status()['nextCheckAt']);self.assertEqual(ReleaseChecks(self.a,'1.1.28').status()['version'],'1.1.29')
 def test_failure_visible_retains_version(self):
  def fail():raise OSError('HTTP 403')
  c=ReleaseChecks(self.a,'1.1.28',fail);c.state={'version':'1.1.29'};c.check();self.finish(c);self.assertIn('403',c.status()['error']);self.assertTrue(c.status()['available'])
 def test_double_check(self):
  gate=threading.Event();calls=[]
  def fetch():calls.append(1);gate.wait(2);return dict(tag_name='v1.1.29')
  c=ReleaseChecks(self.a,'1.1.28',fetch);c.check();c.check();gate.set();self.finish(c);self.assertEqual(len(calls),1)
 def test_off_scheduler_does_not_fetch(self):
  self.a.values['releaseCheckHours']=0;calls=[];c=ReleaseChecks(self.a,'1.1.28',lambda:calls.append(1));c.start();time.sleep(.03);c.close();self.assertFalse(calls)
 def test_schedule_wakes_on_change(self):
  self.a.values['releaseCheckHours']=0;c=ReleaseChecks(self.a,'1.1.28',lambda:dict(tag_name='v1.1.28'));c.start();self.a.values['releaseCheckHours']=12;c.reschedule()
  for _ in range(100):
   if c.state.get('checkedAt'):break
   time.sleep(.01)
  c.close();self.assertTrue(c.state.get('checkedAt'));self.assertFalse(c.status()['available'])
 def test_corrupt_state_visible(self):
  (self.a.data_dir/'release-check.json').write_text('{');self.assertIn('previous release',ReleaseChecks(self.a,'1.1.28').status()['error'])
 def archive(self,unsafe=False):
  zpath=self.a.data_dir/'fixture.zip'
  with zipfile.ZipFile(zpath,'w') as z:
   for n in ('viewer.py','START-VIEWER.bat','runtime/python.exe','runtime/python313.zip','web/index.html'):z.writestr('offline-chat-viewer/'+n,"VERSION = '9.0.0'" if n=='viewer.py' else 'fixture')
   if unsafe:z.writestr('offline-chat-viewer/../escape','no')
  digest=hashlib.sha256(zpath.read_bytes()).hexdigest();name='Offline-Chat-Viewer-v9.0.0-Windows.zip'
  release=dict(tag_name='v9.0.0',assets=[dict(name=n,browser_download_url=HOST+'v9.0.0/'+n) for n in (name,name+'.sha256.txt')])
  def fetch(url,p,limit):
   if url.endswith('.txt'):p.write_text(digest+'  '+name)
   else:shutil.copy2(zpath,p)
  return release,fetch
 def test_staging_verified_and_disabled(self):
  release,fetch=self.archive();self.assertFalse(stage_release(self.a,release,fetch));self.assertFalse((self.a.data_dir/'pending-update.json').exists());self.a.values['silentUpdates']=True;self.assertTrue(stage_release(self.a,release,fetch));m=json.loads((self.a.data_dir/'pending-update.json').read_text());self.assertEqual(len(m['files']),5)
 def test_checksum_rejected(self):
  release,fetch=self.archive();self.a.values['silentUpdates']=True
  def bad(url,p,limit):fetch(url,p,limit);p.write_text('0'*64) if url.endswith('.txt') else None
  with self.assertRaisesRegex(ValueError,'checksum'):stage_release(self.a,release,bad)
 def test_path_escape_rejected(self):
  release,fetch=self.archive(True);self.a.values['silentUpdates']=True
  with self.assertRaisesRegex(ValueError,'Unsafe'):stage_release(self.a,release,fetch)
 def test_disable_cancels_pending(self):
  (self.a.data_dir/'pending-update.json').write_text('{}');ReleaseChecks(self.a,'1.1.28').reschedule();self.assertFalse((self.a.data_dir/'pending-update.json').exists())
 @unittest.skipUnless(os.name=='nt','Windows launcher integration')
 def test_installer_preserves_private_data_and_keeps_rollback(self):
  app=self.a.data_dir/'app';app.mkdir();shutil.copy2(Path(__file__).resolve().parents[1]/'apply-update.ps1',app/'apply-update.ps1');data=app/'.viewer-data';data.mkdir();(data/'archive.sqlite3').write_bytes(b'private');payload=data/'updates/v9.0.0/payload';payload.mkdir(parents=True);(payload/'viewer.py').write_text('new');(app/'viewer.py').write_text('old')
  marker=dict(version='9.0.0',payload=str(payload.resolve()),files=[dict(path='viewer.py',sha256=hashlib.sha256(b'new').hexdigest())]);(data/'pending-update.json').write_text(json.dumps(marker));subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',str(app/'apply-update.ps1')],check=True)
  self.assertEqual((app/'viewer.py').read_text(),'new');self.assertEqual((data/'archive.sqlite3').read_bytes(),b'private');self.assertEqual(next((data/'update-rollback').glob('*/viewer.py')).read_text(),'old');self.assertFalse((data/'pending-update.json').exists())
if __name__=='__main__':unittest.main()
