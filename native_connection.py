"""Own the viewer's native ChatGPT session; no exporter/extension setup."""
import json, os, subprocess, threading, time, uuid
from pathlib import Path
from atomic_files import atomic_bytes


class NativeConnection:
    def __init__(self, browser):
        self.browser=browser;self.archive=browser.archive;self.data=self.archive.data_dir
        self.app=Path(__file__).parent;self.process=None;self.lock=threading.RLock()
        self.enabled=self.data/'native-connection-enabled.json'
        self.state_file=self.data/'native-connection-state.json'
        if self.enabled.exists() and self.read_state().get('phase') not in ('blocked','error'):
            self._start(False)

    def read_state(self):
        try:
            value=json.loads(self.state_file.read_text(encoding='utf-8'))
            if not isinstance(value,dict):raise ValueError('Native connection state must be an object')
            return value
        except FileNotFoundError:return {}
        except (OSError,UnicodeError,ValueError):
            # Preserve the original state file for diagnosis. A corrupt helper
            # checkpoint must not prevent the viewer from starting.
            return dict(phase='error',error='Native connection state is unreadable; reconnect to recreate it.')

    def write(self,name,value):
        atomic_bytes(self.data/name,json.dumps(value).encode(),private=True)

    def alive(self):
        return self.process is not None and self.process.poll() is None

    def status(self):
        with self.lock:
            value=self.read_state();alive=self.alive()
            connected=alive and any(c.get('version')=='native' and c.get('connected') for c in self.browser.statuses())
            phase='connected' if connected else value.get('phase','disconnected')
            if not alive and phase not in ('error','blocked'):phase='disconnected'
            return dict(phase=phase,alive=alive,connected=connected,error=value.get('error',''),attempts=value.get('attempts',0))

    def _start(self,show):
        exe=self.app/'runtime/native/NativeConnect.exe'
        if os.name!='nt' or not exe.is_file():
            self.write('native-connection-state.json',dict(phase='error',error='The native connection requires the complete Windows release.',updated=time.time()));return
        # The profile survives version changes while cookies stay out of the archive.
        profile=Path(os.environ.get('LOCALAPPDATA',str(self.data)))/'OfflineChatViewer/ChatGPTConnection'
        profile.mkdir(parents=True,exist_ok=True)
        config=self.data/'native-connection-config.json'
        self.write(config.name,dict(endpoint=self.browser.endpoint,key=self.browser.secret,data=str(self.data),profile=str(profile),show=show,parent=os.getpid()))
        self.write('native-connection-state.json',dict(phase='starting',error='',updated=time.time()))
        self.write('native-connection-control.json',dict(id=uuid.uuid4().hex))
        try:
            with (self.data/'native-connection.log').open('ab') as log:
                self.process=subprocess.Popen([str(exe),str(config)],cwd=exe.parent,stdout=log,stderr=log,creationflags=subprocess.CREATE_NO_WINDOW)
        except OSError as error:
            self.write('native-connection-state.json',dict(phase='error',error=str(error),updated=time.time()))

    def connect(self):
        with self.lock:
            self.write(self.enabled.name,dict(enabled=True))
            if self.alive() and self.read_state().get('phase')=='error':self.close()
            if self.alive():
                reset=not self.status()['connected']
                if reset:self.browser.reset()
                self.write('native-connection-control.json',dict(id=uuid.uuid4().hex,show=True,reset=reset))
            else:
                self.browser.reset();self._start(True)
            return self.status()

    def close(self):
        with self.lock:
            if not self.alive():return
            self.write('native-connection-control.json',dict(id=uuid.uuid4().hex,stop=True))
            try:self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.terminate();self.process.wait(timeout=3)
