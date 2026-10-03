"""Quick local suggestions and native Windows folder controls. Never scans Drive files."""
import ctypes,os,subprocess,time,uuid
from pathlib import Path

_drive_cache=None
def drive_suggestion(roots=None,refresh=False):
    global _drive_cache
    system_roots=roots is None
    if roots is None and not refresh and _drive_cache and time.monotonic()-_drive_cache[0]<30:return dict(_drive_cache[1])
    if roots is None:
        letters=ctypes.windll.kernel32.GetLogicalDrives() if os.name=='nt' else 0
        roots=[Path(letter+':/') for letter in 'GABCDEFGHIJKLMNOPQRSTUVWX YZ'.replace(' ','') if letters & (1<<(ord(letter)-65))]
        roots=list(dict.fromkeys(roots))
        home=Path.home()
        roots.extend([home/'Google Drive',home/'GoogleDrive',home/'My Drive'])
    found=[]
    for root in roots:
        root=Path(root)
        try:
            candidate=root/'My Drive' if (root/'My Drive').is_dir() else root if root.name in ('My Drive','Google Drive','GoogleDrive') else root/'My Drive'
            if candidate.is_dir() and candidate not in found:found.append(candidate)
        except OSError:continue
    result={'available':bool(found),'root':str(found[0]) if found else '', 'roots':[str(p) for p in found],
            'sync_folder':str(found[0]/'Offline Chat Viewer Backups') if found else '',
            'message':'Drive for desktop found. Completed ZIPs can be copied to a dedicated backup folder.' if found else 'Drive for desktop was not found. Mount your Drive, then scan again, or choose your synced folder.'}
    if system_roots:_drive_cache=(time.monotonic(),dict(result))
    return result

def quick_setup(settings,app,refresh=False,downloads=None):
    """Respect the loader; inspect only shallow export-folder markers for suggestions."""
    start=str(settings.get('scan_start') or '')
    selected=Path(start).expanduser() if start else None
    candidates=[]
    if selected and selected.is_dir():candidates.append(selected)
    home=Path(downloads) if downloads is not None else Path.home()/'Downloads'
    bases=[Path(app).parent,home/'CHATGPT',home]
    for base in bases:
        if len(candidates)>=12:break
        try:
            from itertools import islice
            children=list(islice(base.iterdir(),80)) if base.is_dir() else []
        except OSError:continue
        for candidate in [base]+children:
            try:
                if not candidate.is_dir() or candidate.is_symlink():continue
                if any((candidate/name).is_file() for name in ('conversation-index.json','viewer-handoff.json','portable-state.json')) or ((candidate/'markdown').is_dir() and (candidate/'json').is_dir()):
                    if candidate not in candidates:candidates.append(candidate)
            except OSError:continue
    source=str(candidates[0]) if candidates else ''
    return {'source':source,'up':int(settings.get('scan_up',0)) if selected and source==str(selected) else 0,
            'source_candidates':[str(p) for p in candidates], 'drive':drive_suggestion(refresh=refresh)}

def open_folder(path,create=False):
    if not str(path).strip():raise ValueError('Choose a local ZIP folder first.')
    folder=Path(path).expanduser().resolve()
    if create:folder.mkdir(parents=True,exist_ok=True)
    if not folder.is_dir():raise ValueError('That folder does not exist.')
    if os.name=='nt':os.startfile(str(folder),'open')
    else:subprocess.Popen(['open' if __import__('sys').platform=='darwin' else 'xdg-open',str(folder)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    return {'path':str(folder),'opened':True}

class GUID(ctypes.Structure):
    _fields_=[('data1',ctypes.c_uint32),('data2',ctypes.c_uint16),('data3',ctypes.c_uint16),('data4',ctypes.c_ubyte*8)]
    @classmethod
    def of(cls,value):return cls.from_buffer_copy(uuid.UUID(value).bytes_le)

def _call(obj,index,result,args,*values):
    address=ctypes.cast(obj,ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents[index]
    return ctypes.WINFUNCTYPE(result,ctypes.c_void_p,*args)(address)(obj,*values)

def pick_folder(initial='',title='Choose a folder',show=True):
    """IFileOpenDialog: address bar, search, Quick Access and folder creation."""
    ole=ctypes.OleDLL('ole32');shell=ctypes.WinDLL('shell32')
    ole.CoInitializeEx.argtypes=[ctypes.c_void_p,ctypes.c_uint32];ole.CoInitializeEx.restype=ctypes.c_int32
    initialized=ole.CoInitializeEx(None,2)
    if initialized<0:raise OSError('The Windows folder picker could not initialize. Paste the folder path instead.')
    dialog=ctypes.c_void_p();item=ctypes.c_void_p();selected=ctypes.c_void_p();display=ctypes.c_void_p()
    hresult=ctypes.c_int32;pointer=ctypes.POINTER(ctypes.c_void_p)
    try:
        cls=GUID.of('DC1C5A9C-E88A-4DDE-A5A1-60F82A20AEF7');iid=GUID.of('D57C7288-D4AD-4768-BE02-9D969532D960')
        ole.CoCreateInstance.argtypes=[ctypes.POINTER(GUID),ctypes.c_void_p,ctypes.c_uint32,ctypes.POINTER(GUID),pointer]
        ole.CoCreateInstance.restype=hresult
        if ole.CoCreateInstance(ctypes.byref(cls),None,1,ctypes.byref(iid),ctypes.byref(dialog))<0:raise OSError('Windows folder picker is unavailable. Paste the folder path instead.')
        def checked(index,args,*values):
            code=_call(dialog,index,hresult,args,*values)
            if code<0:raise OSError('Windows folder picker failed: '+hex(code&0xffffffff))
        checked(9,[ctypes.c_uint32],0x20|0x40|0x800|0x8)
        checked(17,[ctypes.c_wchar_p],title)
        checked(18,[ctypes.c_wchar_p],'Use this folder')
        folder=Path(initial).expanduser() if initial else None
        if folder:
            while not folder.is_dir() and folder.parent!=folder:folder=folder.parent
            if folder.is_dir():
                shell.SHCreateItemFromParsingName.argtypes=[ctypes.c_wchar_p,ctypes.c_void_p,ctypes.POINTER(GUID),pointer]
                shell.SHCreateItemFromParsingName.restype=hresult
                shelliid=GUID.of('43826D1E-E718-42EE-BC55-A1E261C37BFE')
                if shell.SHCreateItemFromParsingName(str(folder),None,ctypes.byref(shelliid),ctypes.byref(item))>=0:checked(12,[ctypes.c_void_p],item)
        if not show:return {'initialized':True,'initial':str(folder) if folder else ''}
        ctypes.windll.user32.GetForegroundWindow.restype=ctypes.c_void_p
        code=_call(dialog,3,hresult,[ctypes.c_void_p],ctypes.windll.user32.GetForegroundWindow())
        if code&0xffffffff==0x800704c7:return ''
        if code<0:raise OSError('Windows could not open the folder picker. Paste the path instead.')
        checked(20,[pointer],ctypes.byref(selected))
        code=_call(selected,5,hresult,[ctypes.c_uint32,pointer],0x80058000,ctypes.byref(display))
        if code<0:raise OSError('Choose a folder on your computer.')
        return ctypes.wstring_at(display)
    finally:
        if display:ole.CoTaskMemFree.argtypes=[ctypes.c_void_p];ole.CoTaskMemFree(display)
        for obj in (selected,item,dialog):
            if obj:_call(obj,2,ctypes.c_uint32,[])
        ole.CoUninitialize()
