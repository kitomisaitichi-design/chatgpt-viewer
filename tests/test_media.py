import http.client,json,threading,unittest
from thread_attachments import kind
from viewer import Server
import test_thread_attachments as fixtures

class Media(unittest.TestCase):
 setUp=fixtures.Attachments.setUp
 tearDown=fixtures.Attachments.tearDown
 save=fixtures.Attachments.save
 documents=fixtures.Attachments.documents
 def test_media_types_and_authenticated_stream_ranges(self):
  folder=self.documents();p=folder/'sound.mp3';p.write_bytes(b'0123456789');self.data['mapping']['n4']['message']['content']['parts']=['[Sound](attachments/sound.mp3)'];self.save()
  for name,expected in [('x.htm','html'),('x.html','html'),('x.mp3','audio'),('x.ogg','audio'),('x.wav','audio'),('x.ma4','audio'),('x.m4a','audio'),('x.mp4','video'),('x.midi','midi'),('x.mid','midi')]:self.assertEqual(kind(name),expected)
  server=Server(('127.0.0.1',0),self.a);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();c=http.client.HTTPConnection('127.0.0.1',server.server_port)
  try:
   cookie={'Cookie':server.cookie_name+'='+server.token};c.request('GET','/attachment-frame.html?format=html',headers=cookie);response=c.getresponse();frame=response.read().decode();self.assertEqual(frame.count('<script nonce='),2);self.assertNotIn('docx.renderAsync(safe',frame.split('const zip=')[0]);self.assertIn("connect-src 'none'",response.getheader('Content-Security-Policy'));item=server.attachments.public(self.cid)['attachments'][0];url='/api/thread-attachments/content?id='+self.cid+'&attachment='+item['id']+'&play=1'
   c.request('GET',url);response=c.getresponse();self.assertEqual(response.status,403);response.read()
   for byte_range,status,expected in [('bytes=2-5',206,b'2345'),('bytes=-3',206,b'789'),('bytes=7-',206,b'789'),('bytes=100-',416,b''),('bytes=0-1,4-5',416,b'')]:
    c.request('GET',url,headers={**cookie,'Range':byte_range});response=c.getresponse();self.assertEqual(response.status,status);self.assertEqual(response.read(),expected)
    if status==206:self.assertEqual(response.getheader('Content-Type'),'audio/mpeg');self.assertIsNone(response.getheader('Content-Disposition'));self.assertIn('/10',response.getheader('Content-Range'))
   c.request('GET',url.replace('&play=1',''),headers=cookie);response=c.getresponse();self.assertEqual(response.getheader('Content-Type'),'application/octet-stream');self.assertIn('attachment',response.getheader('Content-Disposition'));response.read()
  finally:c.close();server.shutdown();server.server_close();thread.join()
