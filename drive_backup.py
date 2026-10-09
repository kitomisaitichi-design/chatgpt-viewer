"""Direct Google OAuth and resumable Drive transfers, using the standard library."""
import base64,ctypes,hashlib,json,os,re,secrets,threading,time,urllib.error,urllib.parse,urllib.request,webbrowser
from pathlib import Path
from http.server import BaseHTTPRequestHandler,HTTPServer
from atomic_files import atomic_bytes

TOKEN_URL='https://oauth2.googleapis.com/token'
API='https://www.googleapis.com/drive/v3/'

def uploaded_offset(headers):
    value=headers.get('Range') or headers.get('range') or ''
    match=re.fullmatch(r'bytes=0-(\d+)',value)
    if value and not match:raise ValueError('Google returned an invalid upload range.')
    return int(match[1])+1 if match else 0

def protect(data,decrypt=False):
    if os.name!='nt':return data
    class Blob(ctypes.Structure):_fields_=[('size',ctypes.c_ulong),('data',ctypes.POINTER(ctypes.c_ubyte))]
    buf=ctypes.create_string_buffer(data);source=Blob(len(data),ctypes.cast(buf,ctypes.POINTER(ctypes.c_ubyte)));dest=Blob()
    function=ctypes.windll.crypt32.CryptUnprotectData if decrypt else ctypes.windll.crypt32.CryptProtectData
    if not function(ctypes.byref(source),None,None,None,None,1,ctypes.byref(dest)):raise OSError('Windows could not protect the Google connection.')
    try:return ctypes.string_at(dest.data,dest.size)
    finally:ctypes.windll.kernel32.LocalFree(dest.data)

def save_private(path,value):
    atomic_bytes(path,protect(json.dumps(value).encode()),private=True)

def read_private(path):
    return json.loads(protect(Path(path).read_bytes(),True)) if Path(path).exists() else {}

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None

class Drive:
    def __init__(self,data_dir):
        self.path=Path(data_dir)/'google-connection.secure';self.lock=threading.RLock();self.login={'phase':'disconnected'};self.listener=None
    def status(self):
        data=read_private(self.path)
        return dict(self.login,connected=bool(data.get('refresh_token')),client_ready=bool(data.get('client_id')),account=data.get('account',''))
    def configure(self,document):
        installed=document.get('installed') if isinstance(document,dict) else None
        if not isinstance(installed,dict) or not re.fullmatch(r'[a-zA-Z0-9.-]+\.apps\.googleusercontent\.com',str(installed.get('client_id',''))):raise ValueError('Choose the JSON for a Google OAuth Desktop app, not a service account or web app.')
        with self.lock:
            old=read_private(self.path)
            if old.get('client_id')!=installed['client_id']:old={}
            old.update(client_id=installed['client_id'],client_secret=str(installed.get('client_secret','')))
            save_private(self.path,old)
        return self.status()
    def disconnect(self):
        # Forget local credentials; no remote files are deleted.
        with self.lock:
            data=read_private(self.path);save_private(self.path,{k:data[k] for k in ('client_id','client_secret') if k in data});self.login={'phase':'disconnected'}
        if self.listener:threading.Thread(target=self.listener.shutdown,daemon=True).start()
    def connect(self):
        with self.lock:
            data=read_private(self.path)
            if not data.get('client_id'):raise ValueError('Import your Google Desktop app connection JSON first. The setup guide explains the one-time registration.')
            if self.login.get('phase')=='waiting':return self.status()
            verifier=secrets.token_urlsafe(48);state=secrets.token_urlsafe(32);drive=self
            class Callback(BaseHTTPRequestHandler):
                def log_message(self,*args):pass
                def do_GET(self):
                    q=urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
                    if not secrets.compare_digest(q.get('state',[''])[0],state):self.send_error(400,'This connection request has expired.');return
                    try:
                        if q.get('error'):raise ValueError('Google connection was declined. You can try again.')
                        code=q.get('code',[''])[0]
                        if not code:raise ValueError('Google did not return a connection code.')
                        token=drive._token(dict(client_id=data['client_id'],client_secret=data.get('client_secret',''),code=code,code_verifier=verifier,redirect_uri=redirect,grant_type='authorization_code'))
                        if not token.get('refresh_token'):raise ValueError('Google did not grant offline access. Remove the old app permission in your Google account and connect again.')
                        data.update(token);data['expires_at']=time.time()+token.get('expires_in',3600)
                        save_private(drive.path,data)
                        try:
                            account=drive.request('GET',API+'about?fields=user(emailAddress,displayName)')['user'];data['account']=account.get('emailAddress') or account.get('displayName','Connected account');save_private(drive.path,data)
                        except Exception:data['account']='Connected Google account';save_private(drive.path,data)
                        drive.login={'phase':'connected'};message='Google Drive is connected. Return to the viewer and choose your backup folder.'
                    except Exception as error:drive.login={'phase':'error','error':str(error)};message='Connection was not completed. Return to the viewer for details.'
                    body=('<!doctype html><meta charset="utf-8"><title>Offline Chat Viewer</title><p>'+message+'</p>').encode();self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Content-Length',str(len(body)));self.send_header('Content-Security-Policy',"default-src 'none'");self.end_headers();self.wfile.write(body);threading.Thread(target=drive.listener.shutdown,daemon=True).start()
            self.listener=HTTPServer(('127.0.0.1',0),Callback);redirect='http://127.0.0.1:'+str(self.listener.server_port)+'/'
            # Metadata is read-only; file writes are restricted to files created by this OAuth app.
            query=dict(client_id=data['client_id'],redirect_uri=redirect,response_type='code',scope='https://www.googleapis.com/auth/drive.file https://www.googleapis.com/auth/drive.metadata.readonly',state=state,code_challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('='),code_challenge_method='S256',access_type='offline',prompt='consent select_account')
            self.login={'phase':'waiting'}
            def listen():
                timer=threading.Timer(300,self.listener.shutdown);timer.daemon=True;timer.start()
                try:self.listener.serve_forever()
                finally:
                    timer.cancel();self.listener.server_close()
                    if self.login.get('phase')=='waiting':self.login={'phase':'error','error':'Google sign-in timed out. Select Connect again.'}
            threading.Thread(target=listen,daemon=True).start();webbrowser.open('https://accounts.google.com/o/oauth2/v2/auth?'+urllib.parse.urlencode(query))
        return self.status()
    def _token(self,values):
        try:
            with urllib.request.urlopen(urllib.request.Request(TOKEN_URL,data=urllib.parse.urlencode(values).encode(),headers={'Content-Type':'application/x-www-form-urlencoded'}),timeout=30) as response:return json.load(response)
        except urllib.error.HTTPError as e:raise ValueError('Google connection needs attention ('+str(e.code)+'). Reconnect the account.') from None
    def access_token(self):
        with self.lock:
            data=read_private(self.path)
            if not data.get('refresh_token'):raise ValueError('Connect Google Drive before uploading backups.')
            if time.time()>data.get('expires_at',0)-90:
                token=self._token(dict(client_id=data['client_id'],client_secret=data.get('client_secret',''),refresh_token=data['refresh_token'],grant_type='refresh_token'));data.update(token);data['expires_at']=time.time()+token.get('expires_in',3600);save_private(self.path,data)
            return data['access_token']
    def request(self,method,url,body=None,headers=None,raw=False):
        if not url.startswith(('https://www.googleapis.com/drive/','https://www.googleapis.com/upload/drive/')):raise ValueError('Unexpected Google upload endpoint.')
        content=json.dumps(body).encode() if isinstance(body,dict) else body
        h={'Authorization':'Bearer '+self.access_token(),**(headers or {})}
        if isinstance(body,dict):h['Content-Type']='application/json'
        req=urllib.request.Request(url,data=content,headers=h,method=method)
        try:response=urllib.request.build_opener(NoRedirect).open(req,timeout=60)
        except urllib.error.HTTPError as e:
            if e.code==308:return dict(status=308,headers=dict(e.headers),body={})
            raise ValueError('Google Drive request failed ('+str(e.code)+'). Check the connection, folder permission, or available storage.') from None
        with response:
            payload=response.read();result=dict(status=response.status,headers=dict(response.headers),body=json.loads(payload) if payload else {})
        return result if raw else result['body']
    def folders(self,parent='root'):
        if not re.fullmatch(r'[a-zA-Z0-9_-]+',parent):raise ValueError('Invalid folder ID.')
        q="mimeType='application/vnd.google-apps.folder' and trashed=false and '"+parent+"' in parents"
        items=[];page=''
        while True:
            result=self.request('GET',API+'files?'+urllib.parse.urlencode(dict(q=q,fields='nextPageToken,files(id,name,webViewLink)',pageSize=100,orderBy='name',**({'pageToken':page} if page else {}))));items.extend(result.get('files',[]));page=result.get('nextPageToken')
            if not page:return items
    def create_folder(self,name,parent='root'):
        name=str(name).strip()[:120]
        if not name or not re.fullmatch(r'[a-zA-Z0-9_-]+',parent):raise ValueError('Choose a folder name and valid parent folder.')
        return self.request('POST',API+'files?fields=id,name,webViewLink',dict(name=name,mimeType='application/vnd.google-apps.folder',parents=[parent]))
    def folder(self,folder_id):
        if not re.fullmatch(r'[a-zA-Z0-9_-]+',folder_id):raise ValueError('Invalid Google Drive folder ID.')
        value=self.request('GET',API+'files/'+folder_id+'?fields=id,name,mimeType,webViewLink')
        if value.get('mimeType')!='application/vnd.google-apps.folder':raise ValueError('Choose a Google Drive folder, not a file.')
        return value
    def upload(self,path,folder,slot,checkpoint,progress,cancel):
        path=Path(path);size=path.stat().st_size
        if not re.fullmatch(r'[a-zA-Z0-9_-]+',folder):raise ValueError('Choose the backup folder first.')
        def status(session):return self.request('PUT',session,b'',{'Content-Range':'bytes */'+str(size)},True)
        session=slot.get('session');offset=0
        if session:
            try:
                result=status(session)
                if result['status'] in (200,201):return result['body']
                offset=uploaded_offset(result['headers'])
            except ValueError:session=None
        if not session:
            file_id=slot.get('id');url='https://www.googleapis.com/upload/drive/v3/files'+('/'+file_id if file_id else '')+'?uploadType=resumable&fields=id,name,webViewLink,md5Checksum,size'
            body={'name':path.name}
            if not file_id:body['parents']=[folder]
            result=self.request('PATCH' if file_id else 'POST',url,body,{'X-Upload-Content-Type':'application/zip','X-Upload-Content-Length':str(size)},True);session=result['headers'].get('Location') or result['headers'].get('location')
            if not session or not session.startswith('https://www.googleapis.com/'):raise ValueError('Google did not return a safe resumable upload session.')
            slot['session']=session;checkpoint()
        with path.open('rb') as stream:
            retries=0
            while offset<size:
                if cancel.is_set():raise InterruptedError('Backup cancelled. The previous uploaded file is kept.')
                stream.seek(offset);chunk=stream.read(4*1024*1024)
                try:
                    result=self.request('PUT',session,chunk,{'Content-Type':'application/zip','Content-Range':f'bytes {offset}-{offset+len(chunk)-1}/{size}'},True)
                    if result['status'] in (200,201):progress(size,size);return result['body']
                    next_offset=uploaded_offset(result['headers'])
                    if next_offset<=offset or next_offset>size:raise ValueError('Google upload did not advance.')
                    offset=next_offset;progress(offset,size);retries=0
                except (ValueError,OSError):
                    retries+=1
                    if retries>5:raise ValueError('Upload interrupted. Run the backup again to resume it.') from None
                    if cancel.wait(min(2**retries,20)):raise InterruptedError('Backup cancelled.')
                    result=status(session)
                    if result['status'] in (200,201):return result['body']
                    offset=uploaded_offset(result['headers'])
        raise ValueError('Google did not confirm the completed upload.')
