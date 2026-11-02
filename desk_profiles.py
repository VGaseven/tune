"""Preset Desk 4 profile management, friend sharing, undo lookup and window preferences.
All game-file reads/writes stay in capture_model; this module only touches the app's own folder."""
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import uuid
import capture_model as model

SHARE_FORMAT='presetdesk-share';SHARE_MAX=16_384
# Short names for the 12 allowlisted keys. Engine scalability groups do not map 1:1 to every
# in-game menu label, so the raw key is always shown next to the short name where values change.
NAMES={'sg.ViewDistanceQuality':'View distance','sg.AntiAliasingQuality':'Anti-aliasing','sg.ShadowQuality':'Shadows',
       'sg.PostProcessQuality':'Post-processing','sg.TextureQuality':'Textures','sg.EffectsQuality':'Effects',
       'sg.FoliageQuality':'Foliage','sg.ShadingQuality':'Shading','sg.GlobalIlluminationQuality':'Global illumination',
       'sg.ReflectionQuality':'Reflections','bUseVSync':'VSync','FrameRateLimit':'Frame-rate limit'}
ORDER=list(NAMES)

UUID=rb'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}'
LOGIN=re.compile(rb'LogShooterGameUserSettings: Logged in user changed: ('+UUID+rb')')
def signed_in(config_root,limit=64_000_000):
    """Account ID that VALORANT itself logged as its active settings user in its latest log
    (Saved\\Logs\\ShooterGame.log next to Saved\\Config). Only this one line pattern is used;
    nothing else from the log is read into the app or stored. None when unknown."""
    log=Path(config_root).parent/'Logs'/'ShooterGame.log'
    try:
        with log.open('rb') as f:
            f.seek(0,2);size=f.tell();f.seek(max(0,size-limit));data=f.read()
    except OSError:return None
    found=LOGIN.findall(data)
    return found[-1].decode() if found else None

def account_of(path,config_root):
    """Account folder name for a settings file, or None for VALORANT's shared top-level folders."""
    folder=Path(path).parent.parent
    try:
        if folder.resolve()==Path(config_root).resolve():return None
    except OSError:return None
    return folder.name

def account_paths(paths,config_root):
    """One settings file per account folder: 'Windows' (the game's own platform folder) is
    preferred over the older 'WindowsClient' copy; shared non-account folders are skipped."""
    best={}
    for p in paths:
        acc=account_of(p,config_root)
        if acc is not None and (acc not in best or p.parent.name=='Windows'):best[acc]=p
    return sorted(best.values(),key=lambda p:str(p).lower())

def riot_client():
    """Path to RiotClientServices.exe from Riot's own install manifest
    (%ProgramData%\\Riot Games\\RiotClientInstalls.json - plain file paths, no secrets), or None.
    Used only to let the user open Riot Client themselves; Tune never signs in or reads tokens."""
    base=os.environ.get('PROGRAMDATA') or r'C:\ProgramData'
    try:data=json.loads((Path(base)/'Riot Games'/'RiotClientInstalls.json').read_text(encoding='utf-8-sig'))
    except (OSError,ValueError,UnicodeError):return None
    if not isinstance(data,dict):return None
    for key in ('rc_live','rc_default'):
        p=data.get(key)
        if isinstance(p,str) and Path(p).name.lower()=='riotclientservices.exe':
            path=Path(p)
            if path.is_file():return path
    return None

def shown(key,value):
    """Display form only ('240.000000' -> '240'); stored and written values are unchanged."""
    if key=='FrameRateLimit' and '.' in value:value=value.rstrip('0').rstrip('.') or '0'
    return value

def captured(data):
    return datetime.fromisoformat(data['provenance']['captured_utc']).astimezone()
def when(data):
    t=captured(data);return t.strftime('%b ')+str(t.day)+t.strftime(', %H:%M')
def is_shared(data):return data['provenance']['label_source']=='imported-share'
def captured_names(data):return [NAMES[k] for k in ORDER if k in data['settings']]

def entries(store):
    """Valid saved profiles, newest capture first. Invalid files are skipped, never rewritten."""
    return sorted(store.list(),key=lambda item:item[1]['provenance']['captured_utc'],reverse=True)

def display_names(items):
    """Duplicate labels get a numeric suffix for display only; stored labels are unchanged."""
    seen={};out=[]
    totals={}
    for _,d in items:totals[d['label'].casefold()]=totals.get(d['label'].casefold(),0)+1
    for _,d in reversed(items):
        key=d['label'].casefold();seen[key]=seen.get(key,0)+1
        out.append(d['label']+(f' ({seen[key]})' if totals[key]>1 else ''))
    return list(reversed(out))

def owned(store,path):
    path=Path(path).resolve();folder=(store.base/'profiles').resolve()
    if path.parent!=folder or path.suffix.lower()!='.json' or not path.is_file():raise ValueError('That profile is no longer in the app folder.')
    return path

def save_capture(store,data):
    """One profile per source+label: a new save atomically replaces that profile's file, so a
    failed save leaves the previous profile untouched. Returns (path, replaced)."""
    model.validate_profile(data);ref=data['provenance']['source_ref']
    for path,old in store.list():
        if not is_shared(old) and old['provenance']['source_ref']==ref and old['label']==data['label']:
            model.write_json(path,data);return path,True
    return store.save(data),False

def remembered(store):
    """(source_ref, your label) for the source you last chose, or None. Reads app files only."""
    try:
        ref=store.last_source();labels=store.bindings()
    except (OSError,ValueError,UnicodeError):return None
    return (ref,labels[ref]) if ref and ref in labels else None

def rebind(store,ref,label):
    data=store.bindings();data[ref]=model.clean_label(label)
    store.base.mkdir(parents=True,exist_ok=True);model.write_json(store.base/'source-labels.json',data)

def rename(store,path,label):
    path=owned(store,path);data=model.import_profile(path);old=data['label']
    data['label']=model.clean_label(label);model.validate_profile(data);model.write_json(path,data)
    ref=data['provenance']['source_ref']
    if not is_shared(data) and store.bindings().get(ref)==old:rebind(store,ref,data['label'])
    return data

def duplicate(store,path):
    data=model.import_profile(owned(store,path))
    data['label']=model.clean_label((data['label'][:75]+' copy'))
    return store.save(data)

def delete(store,path):
    """Moves the profile into the app's own 'deleted' folder (recoverable by hand)."""
    path=owned(store,path);trash=store.base/'deleted';trash.mkdir(parents=True,exist_ok=True)
    dest=trash/path.name
    if dest.exists():dest=trash/(uuid.uuid4().hex+'.json')
    shutil.move(str(path),str(dest));return dest

def share_payload(data,label=''):
    """Only supported video values plus an optional display label. No fingerprints, paths,
    account labels you did not choose, sensitivity values or timestamps."""
    payload={'format':SHARE_FORMAT,'version':1,'settings':{k:data['settings'][k] for k in ORDER if k in data['settings']}}
    if label.strip():payload['label']=model.clean_label(label)
    model.valid_settings(payload['settings']);return payload

def export_share(selected,payload):
    if not selected:return None
    p=Path(selected)
    if p.is_dir() or p.suffix.lower()!='.json' or not p.parent.is_dir():raise ValueError('Choose a .json filename in an existing folder.')
    model.write_json(p,payload);return p

def read_import(selected):
    """Accepts a Preset Desk share file or an older full v3 profile. Strict schema, size, types
    and value ranges; content never chooses any file path."""
    if not selected or str(selected).strip() in ('.','..') or Path(selected).is_dir() or Path(selected).suffix.lower()!='.json':raise ValueError('Choose a .json profile file.')
    raw=model.read_bytes(selected)
    try:data=json.loads(raw.decode('utf-8-sig'),object_pairs_hook=model.duplicates)
    except (UnicodeError,json.JSONDecodeError):raise ValueError('That file is not valid JSON.')
    if isinstance(data,dict) and data.get('format')==SHARE_FORMAT:
        if len(raw)>SHARE_MAX:raise ValueError('Shared profile is too large.')
        if set(data)-{'format','version','settings','label'} or set(data)<{'format','version','settings'} or type(data['version']) is not int or data['version']!=1:raise ValueError('Unsupported shared-profile layout.')
        model.valid_settings(data['settings'])
        label=model.clean_label(data['label']) if 'label' in data else 'Shared profile'
        return {'format':model.FORMAT,'version':3,'label':label,'settings':dict(data['settings']),
                'provenance':{'source_ref':hashlib.sha256(b'shared:'+uuid.uuid4().bytes).hexdigest(),'source_sha256':hashlib.sha256(raw).hexdigest(),
                              'captured_utc':model.now(),'file_name':'shared-profile.json','layout':'Imported','label_source':'imported-share'},
                'availability':{'account_name':'Imported from a shared file; not linked to any account.','sensitivity':'Not included in shared profiles.'}}
    return model.validate_profile(data)

def backups_for(store,target):
    """Undo records for this exact target, newest first. Malformed records are skipped."""
    ref=model.source_id(target);found=[]
    for p in (store.base/'backups').glob('*.json'):
        try:
            r=model.read_json(p)
            if isinstance(r,dict) and r.get('format')=='presetdesk-undo' and r.get('version')==3 and r.get('target_ref')==ref and isinstance(r.get('created_utc'),str):found.append((r['created_utc'],p))
        except (OSError,ValueError,UnicodeError):continue
    return [p for _,p in sorted(found,reverse=True)]

PREFS={'version':1,'view':'full','tab':'save','pin_full':False,'pin_mini':True,'full':[430,820,80,40],'mini':[420,200,120,120]}
def load_prefs(path):
    try:
        with Path(path).open('rb') as f:raw=f.read(4097)
        if len(raw)>4096:raise ValueError()
        d=json.loads(raw.decode('utf-8'))
        if not isinstance(d,dict) or set(d)!=set(PREFS) or type(d['version']) is not int or d['version']!=1:raise ValueError()
        if d['view'] not in ('full','mini') or d['tab'] not in ('save','accounts') or type(d['pin_full']) is not bool or type(d['pin_mini']) is not bool:raise ValueError()
        for k in ('full','mini'):
            v=d[k]
            if not isinstance(v,list) or len(v)!=4 or any(type(n) is not int for n in v) or not (100<=v[0]<=16000 and 60<=v[1]<=16000) or any(abs(n)>100000 for n in v[2:]):raise ValueError()
        return d
    except (OSError,ValueError,TypeError,UnicodeError):return json.loads(json.dumps(PREFS))
