"""VALORANT file-only profiles. No credentials, game memory, client APIs or input automation."""
import ctypes
from ctypes import wintypes as w
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import uuid
import sensitivity_reference

GAME_SECTION='/Script/ShooterGame.ShooterGameUserSettings'
QUALITY={'sg.'+k+'Quality' for k in ('ViewDistance','AntiAliasing','Shadow','PostProcess','Texture','Effects','Foliage','Shading','GlobalIllumination','Reflection')}
SECTIONS={**{k:'ScalabilityGroups' for k in QUALITY},'bUseVSync':GAME_SECTION,'FrameRateLimit':GAME_SECTION}
MAX_BYTES=2_000_000
FORMAT='valorant-file-profile'

def process_names():
    if os.name!='nt': raise RuntimeError('This utility requires Windows.')
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    advapi=ctypes.WinDLL('advapi32',use_last_error=True)
    kernel.GetCurrentProcess.restype=w.HANDLE
    advapi.OpenProcessToken.argtypes=[w.HANDLE,w.DWORD,ctypes.POINTER(w.HANDLE)]
    advapi.GetTokenInformation.argtypes=[w.HANDLE,ctypes.c_int,ctypes.c_void_p,w.DWORD,ctypes.POINTER(w.DWORD)]
    kernel.CloseHandle.argtypes=[w.HANDLE]
    token=w.HANDLE()
    if not advapi.OpenProcessToken(kernel.GetCurrentProcess(),8,ctypes.byref(token)):
        raise RuntimeError('Unable to verify process-list visibility. No game files accessed.')
    try:
        isolated=w.DWORD();size=w.DWORD()
        if not advapi.GetTokenInformation(token,29,ctypes.byref(isolated),ctypes.sizeof(isolated),ctypes.byref(size)):
            raise RuntimeError('Unable to verify process-list visibility.')
        if isolated.value:
            raise RuntimeError('This sandbox hides running applications. Run the EXE normally as a standard user, not as administrator.')
    finally: kernel.CloseHandle(token)
    class Entry(ctypes.Structure):
        _fields_=[('size',w.DWORD),('usage',w.DWORD),('pid',w.DWORD),('heap',ctypes.c_size_t),('module',w.DWORD),('threads',w.DWORD),('parent',w.DWORD),('priority',w.LONG),('flags',w.DWORD),('exe',w.WCHAR*260)]
    kernel.CreateToolhelp32Snapshot.argtypes=[w.DWORD,w.DWORD];kernel.CreateToolhelp32Snapshot.restype=w.HANDLE
    kernel.Process32FirstW.argtypes=[w.HANDLE,ctypes.POINTER(Entry)];kernel.Process32FirstW.restype=w.BOOL
    kernel.Process32NextW.argtypes=[w.HANDLE,ctypes.POINTER(Entry)];kernel.Process32NextW.restype=w.BOOL
    handle=kernel.CreateToolhelp32Snapshot(2,0)
    if handle==ctypes.c_void_p(-1).value: raise RuntimeError('Cannot check whether the game is closed.')
    names=[]
    try:
        entry=Entry();entry.size=ctypes.sizeof(entry)
        if not kernel.Process32FirstW(handle,ctypes.byref(entry)):raise RuntimeError('Cannot read the process list.')
        while True:
            names.append(entry.exe)
            if not kernel.Process32NextW(handle,ctypes.byref(entry)):
                if ctypes.get_last_error()!=18:raise RuntimeError('Incomplete process list. No game files accessed.')
                break
    finally: kernel.CloseHandle(handle)
    if len(names)<10:raise RuntimeError('The process list appears restricted. No game files accessed.')
    return names

def ensure_closed():
    names=process_names()
    if any(n.lower().startswith(('valorant','riotclient','riot client')) for n in names):
        raise RuntimeError('Close VALORANT and Riot Client normally, then try again. This app will not close them for you.')

def app_directory():
    base=os.environ.get('LOCALAPPDATA')
    if not base or not Path(base).is_absolute():base=str(Path.home()/'AppData'/'Local')
    return Path(base)/'PresetDesk'

def config_directory():
    return app_directory().parent/'VALORANT'/'Saved'/'Config'

def read_bytes(path):
    with Path(path).open('rb') as f:raw=f.read(MAX_BYTES+1)
    if len(raw)>MAX_BYTES:raise ValueError('File exceeds the supported size.')
    return raw

def valid_settings(values):
    if not isinstance(values,dict) or not values or set(values)-set(SECTIONS):raise ValueError('Empty or unsupported settings profile.')
    for key,value in values.items():
        if not isinstance(value,str):raise ValueError('Setting values must be strings.')
        if key in QUALITY and not re.fullmatch('[0-3]',value):raise ValueError(f'{key}: unsupported quality value.')
        if key=='bUseVSync' and value not in ('True','False'):raise ValueError('Invalid VSync value.')
        if key=='FrameRateLimit' and (not re.fullmatch(r'\d{1,4}(\.\d{1,6})?',value) or not 0<=float(value)<=1000):raise ValueError('Invalid frame-rate value.')
    return values

def parse(raw):
    if len(raw)>MAX_BYTES:raise ValueError('Configuration is too large.')
    encoding='utf-16-le' if raw.startswith(b'\xff\xfe') else 'utf-16-be' if raw.startswith(b'\xfe\xff') else 'utf-8-sig' if raw.startswith(b'\xef\xbb\xbf') else 'utf-8'
    text=raw.decode(encoding)
    if '\x00' in text:raise ValueError('Unsupported configuration encoding.')
    lines=text.splitlines(keepends=True); section='';seen_sections=set();values={};locations={}
    sensitivity_keys=[]
    for i,line in enumerate(lines):
        stripped=line.strip().lstrip('\ufeff')
        if not stripped or stripped.startswith((';','#')):continue
        if stripped.startswith('[') and stripped.endswith(']'):
            section=stripped[1:-1]
            if section in set(SECTIONS.values()):
                if section in seen_sections:raise ValueError('Duplicate settings section; capture cancelled.')
                seen_sections.add(section)
            continue
        if '=' not in line:continue
        key,value=line.split('=',1);key=key.strip()
        if 'sensitiv' in key.lower():sensitivity_keys.append(key)
        if SECTIONS.get(key)==section:
            if key in values:raise ValueError('Duplicate supported setting: '+key)
            values[key]=value.strip();locations[key]=i
    if GAME_SECTION not in seen_sections:raise ValueError('Not a recognized VALORANT GameUserSettings.ini layout.')
    valid_settings(values)
    return lines,encoding,values,locations,bool(sensitivity_keys)

def validate_target(selected, root=None):
    if not selected or str(selected).strip() in ('','.','..'):raise ValueError('Select a settings file first.')
    path=Path(selected)
    if path.name!='GameUserSettings.ini' or not path.is_file():raise ValueError('Choose an existing GameUserSettings.ini file, not a folder.')
    if any(p.is_symlink() or (hasattr(p,'is_junction') and p.is_junction()) for p in (path,*path.parents)):raise ValueError('Linked configuration paths are not supported.')
    path=path.resolve();root=(Path(root) if root is not None else config_directory()).resolve()
    if not path.is_relative_to(root):raise ValueError('Choose a file inside VALORANT/Saved/Config. External paths are not allowed.')
    if path.parent.name not in ('Windows','WindowsClient'):raise ValueError('Unrecognized configuration folder layout.')
    return path

def discover(root=None,guard=None):
    (guard or ensure_closed)()
    root=Path(root) if root is not None else config_directory()
    if not root.is_dir():return []
    # Deterministic path order. No claim that newest or first is the active account.
    result=sorted((p for p in root.rglob('GameUserSettings.ini') if p.parent.name in ('Windows','WindowsClient')),key=lambda p:str(p).lower())
    return [validate_target(p,root) for p in result]

def source_id(path):return hashlib.sha256(str(Path(path).resolve()).casefold().encode()).hexdigest()
def sha(raw):return hashlib.sha256(raw).hexdigest()
def now():return datetime.now(timezone.utc).isoformat()

def capture(selected,label,root=None,guard=None):
    guard=guard or ensure_closed;guard()
    label=clean_label(label)
    path=validate_target(selected,root);raw=read_bytes(path);parsed=parse(raw)
    reference,reference_path,reference_raw=sensitivity_reference.read_sibling(path,read_bytes)
    guard()
    if read_bytes(path)!=raw:raise ValueError('Source changed while capturing. Try again with the game closed.')
    if reference_path is not None and read_bytes(reference_path)!=reference_raw:raise ValueError('Sensitivity source changed while capturing. Try again.')
    profile={'format':FORMAT,'version':3,'label':label,'settings':parsed[2],
            'provenance':{'source_ref':source_id(path),'source_sha256':sha(raw),'captured_utc':now(),'file_name':'GameUserSettings.ini','layout':path.parent.name,'label_source':'user-assigned'},
            'availability':{'account_name':'Not verified from a safe local source; label supplied by you.',
                            'sensitivity':'A sensitivity-like key is present but unsupported; not copied.' if parsed[4] else 'Not present in this captured file; not copied. Other local/server storage is unverified.'}}
    if reference:
        profile['reference']=reference
        profile['availability']['sensitivity']=f'{len(reference["values"])} actual values captured from sibling RiotUserSettings.ini. Reference/copy only; NOT applied to another account.'
    elif not parsed[4]:profile['availability']['sensitivity']='Not present in supported form in this source folder. Not copied; no default substituted.'
    return profile

def clean_label(label):
    if not isinstance(label,str) or not 1<=len(label.strip())<=80 or any(ord(c)<32 for c in label):raise ValueError('Enter a one-line label (1–80 characters) for this source. It is not an automatically verified Riot name.')
    return label.strip()

def validate_profile(data):
    required={'format','version','label','settings','provenance','availability'}
    if not isinstance(data,dict) or set(data) not in (required,required|{'reference'}) or data.get('format')!=FORMAT or type(data.get('version')) is not int or data['version']!=3:raise ValueError('Choose a Preset Desk capture v3 JSON profile.')
    if 'reference' in data:sensitivity_reference.validate(data['reference'])
    clean_label(data['label']);valid_settings(data['settings'])
    p=data['provenance']
    if not isinstance(p,dict) or set(p)!={'source_ref','source_sha256','captured_utc','file_name','layout','label_source'}:raise ValueError('Invalid provenance.')
    if any(not isinstance(p[k],str) or not re.fullmatch('[a-f0-9]{64}',p[k]) for k in ('source_ref','source_sha256')):raise ValueError('Invalid source fingerprint.')
    # 4.0: a friend's shared file is stored as 'imported-share' with no claimed game folder layout.
    if (p['file_name'],p['label_source'])==('shared-profile.json','imported-share'):
        if p['layout']!='Imported' or 'reference' in data:raise ValueError('Unsupported shared-profile metadata.')
    elif p['file_name']!='GameUserSettings.ini' or p['layout'] not in ('Windows','WindowsClient') or p['label_source']!='user-assigned':raise ValueError('Unsupported source metadata.')
    if not isinstance(p['captured_utc'],str) or len(p['captured_utc'])>40:raise ValueError('Invalid capture time.')
    datetime.fromisoformat(p['captured_utc'])
    a=data['availability']
    if not isinstance(a,dict) or set(a)!={'account_name','sensitivity'} or any(not isinstance(v,str) or len(v)>250 or any(ord(c)<32 for c in v) for v in a.values()):raise ValueError('Invalid availability metadata.')
    return data

def duplicates(pairs):
    out={}
    for k,v in pairs:
        if k in out:raise ValueError('Duplicate JSON field: '+k)
        out[k]=v
    return out

def read_json(path):return json.loads(read_bytes(path).decode('utf-8-sig'),object_pairs_hook=duplicates)
def import_profile(selected):
    if not selected or str(selected) in ('.','..') or Path(selected).is_dir() or Path(selected).suffix.lower()!='.json':raise ValueError('Choose a JSON profile filename.')
    return validate_profile(read_json(selected))

def atomic(path,raw):
    path=Path(path)
    fd,temp=tempfile.mkstemp(prefix='.presetdesk-',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
        os.replace(temp,path)
    finally:
        if os.path.exists(temp):os.unlink(temp)

def write_json(path,data):atomic(path,json.dumps(data,ensure_ascii=False,indent=2).encode('utf-8'))

class Store:
    def __init__(self,base=None):self.base=Path(base) if base is not None else app_directory()
    def save(self,data):
        validate_profile(data);folder=self.base/'profiles';folder.mkdir(parents=True,exist_ok=True)
        path=folder/(uuid.uuid4().hex+'.json');write_json(path,data);return path
    def list(self):
        result=[]
        for p in sorted((self.base/'profiles').glob('*.json'),key=lambda p:p.stat().st_mtime,reverse=True):
            try:result.append((p,import_profile(p)))
            except (ValueError,OSError,UnicodeError):continue
        return result
    def bindings(self):
        p=self.base/'source-labels.json'
        if not p.exists():return {}
        data=read_json(p)
        if not isinstance(data,dict):raise ValueError('Invalid local source labels.')
        for k,v in data.items():
            if not re.fullmatch('[a-f0-9]{64}',k):raise ValueError('Invalid source-label reference.')
            clean_label(v)
        return data
    def label(self,path,label):
        data=self.bindings();data[source_id(path)]=clean_label(label)
        self.base.mkdir(parents=True,exist_ok=True);write_json(self.base/'source-labels.json',data)
    def remember(self,path):
        self.base.mkdir(parents=True,exist_ok=True)
        write_json(self.base/'selection.json',{'source_ref':source_id(path)})
    def last_source(self):
        path=self.base/'selection.json'
        if not path.exists():return None
        data=read_json(path)
        if not isinstance(data,dict) or set(data)!={'source_ref'} or not isinstance(data['source_ref'],str) or not re.fullmatch('[a-f0-9]{64}',data['source_ref']):raise ValueError('Invalid remembered source selection.')
        return data['source_ref']

def merge(raw,values):
    valid_settings(values);lines,encoding,current,locations,_=parse(raw)
    if set(values)-set(current):raise ValueError('Target lacks these settings: '+', '.join(sorted(set(values)-set(current))))
    for key,value in values.items():
        if current[key]==value:continue
        i=locations[key];m=re.fullmatch(r'(.*?=)([ \t]*)([^\r\n]*?)([ \t]*)(\r?\n)?',lines[i])
        lines[i]=m[1]+m[2]+value+m[4]+(m[5] or '')
    return ''.join(lines).encode(encoding)

def diff(raw,values):
    merge(raw,values);current=parse(raw)[2]
    return [(k,current[k],v) for k,v in sorted(values.items()) if current[k]!=v]

def preview(selected,profile,root=None,guard=None):
    (guard or ensure_closed)();validate_profile(profile)
    path=validate_target(selected,root);raw=read_bytes(path)
    return raw,diff(raw,profile['settings'])

def apply(selected,values,expected,backup_dir,root=None,guard=None):
    guard=guard or ensure_closed;guard();path=validate_target(selected,root)
    folder=Path(backup_dir);folder.mkdir(parents=True,exist_ok=True)
    lock=folder/'write.lock'
    try:fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY)
    except FileExistsError:raise RuntimeError('Another write is active. Close other copies. If a prior crash left write.lock, remove it only after all copies are closed.')
    try:
        os.close(fd);raw=read_bytes(path)
        if raw!=expected:raise ValueError('Target changed since preview. Preview again.')
        updated=merge(raw,values);delta=diff(raw,values)
        if not delta:return None
        backup=folder/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')+'-'+uuid.uuid4().hex+'.json')
        record={'format':'presetdesk-undo','version':3,'target_ref':source_id(path),'created_utc':now(),'before':{k:a for k,a,b in delta},'after':{k:b for k,a,b in delta}}
        write_json(backup,record)
        guard()
        if read_bytes(path)!=raw:raise ValueError('Target changed during write preparation. No settings applied.')
        atomic(path,updated);return backup
    finally:lock.unlink()

def undo_preview(selected,backup,root=None,guard=None):
    (guard or ensure_closed)();path=validate_target(selected,root);record=read_json(backup)
    if not isinstance(record,dict) or set(record)!={'format','version','target_ref','created_utc','before','after'} or record.get('format')!='presetdesk-undo' or record.get('version')!=3 or record.get('target_ref')!=source_id(path):raise ValueError('Undo file does not match this target.')
    valid_settings(record['before']);valid_settings(record['after'])
    if set(record['before'])!=set(record['after']):raise ValueError('Invalid undo keys.')
    raw=read_bytes(path);current=parse(raw)[2]
    if any(current.get(k)!=v for k,v in record['after'].items()):raise ValueError('These settings changed after that backup. Undo cancelled to preserve newer edits.')
    return raw,record['before'],diff(raw,record['before'])
