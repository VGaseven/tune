"""Tune master-settings sync (one shared configuration for every account).

VALORANT keeps an account's game settings - sensitivity, crosshair profiles, minimap, audio and
so on - in <config>/<puuid>-<region>/Windows/RiotUserSettings.ini, next to GameUserSettings.ini
(video). This module copies the MAIN account's game settings onto another account's file, then
reads the file back and verifies every value. It touches nothing else: no login files, tokens,
keybind caches or game memory, and per-account state flags (tutorials seen, popups, code of conduct)
are left exactly as they are.

Riot also keeps a cloud ('roaming') copy of these settings. sync_report() lets the app check, after
you have played, whether the account still matches the main one - so the UI never claims more than
it can verify."""
from __future__ import annotations
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
import capture_model as model

FILE='RiotUserSettings.ini'
SECTION='[Settings]'
LINE=re.compile(r'^(EAres(?:Float|Int|Bool|String)SettingName::([A-Za-z0-9_]+))=(.*)$')
# Account-state flags, not preferences: never copied, so each account keeps its own history.
STATE=re.compile(r'^(Has|LastSeen|LastAccepted|ContextAware|Collection|PreferredGamePods|ShootingRange)')
MAX_BYTES=4_000_000

def riot_file(game_file):
    """RiotUserSettings.ini that sits beside an account's GameUserSettings.ini."""
    return Path(game_file).with_name(FILE)

def _read(path):
    raw=Path(path).read_bytes()
    if len(raw)>MAX_BYTES:raise ValueError('Settings file exceeds the supported size.')
    return raw.decode('utf-8-sig')

def values(path):
    """{full_key: raw value} for every game setting line in the file ({} if the file is missing)."""
    try:text=_read(path)
    except FileNotFoundError:return {}
    out={}
    for line in text.splitlines():
        m=LINE.match(line.strip())
        if m:out[m[1]]=m[3]
    return out

def shared(vals):
    """The subset that is a real preference (what gets synced)."""
    return {k:v for k,v in vals.items() if not STATE.match(k.split('::',1)[1])}

def merge(text,updates):
    """Return text with updates applied: existing lines rewritten in place, missing keys appended
    to the [Settings] section. Line endings are preserved."""
    nl='\r\n' if '\r\n' in text or not text else '\n'
    lines=text.splitlines() if text else []
    if not any(l.strip()==SECTION for l in lines):lines=[SECTION]+lines
    pending=dict(updates)
    for i,line in enumerate(lines):
        m=LINE.match(line.strip())
        if m and m[1] in pending:lines[i]=f'{m[1]}={pending.pop(m[1])}'
    if pending:
        start=next(i for i,l in enumerate(lines) if l.strip()==SECTION)
        end=start+1
        while end<len(lines) and not lines[end].strip().startswith('['):end+=1
        while end>start+1 and not lines[end-1].strip():end-=1
        lines[end:end]=[f'{k}={v}' for k,v in pending.items()]
    return nl.join(lines)+nl

def diff(master_vals,target_vals):
    """Preference keys where the target differs from the main account."""
    m=shared(master_vals)
    return sorted(k for k,v in m.items() if target_vals.get(k)!=v)

def backup(paths,folder,ref):
    """Copy the target's files (as they are now) into a timestamped backup folder."""
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')
    dest=Path(folder)/f'{stamp}-{ref[:12]}';dest.mkdir(parents=True,exist_ok=True)
    kept={}
    for p in paths:
        p=Path(p)
        if p.exists():shutil.copy2(p,dest/p.name);kept[p.name]=str(p)
    model.write_json(dest/'restore.json',{'format':'tune-master-backup','version':1,'target_ref':ref,'files':kept})
    return dest

def latest_backup(folder,ref):
    found=sorted((d for d in Path(folder).glob(f'*-{ref[:12]}') if (d/'restore.json').exists()),reverse=True)
    return found[0] if found else None

def restore(dest,ref):
    rec=model.read_json(Path(dest)/'restore.json')
    if not isinstance(rec,dict) or rec.get('format')!='tune-master-backup' or rec.get('target_ref')!=ref:
        raise ValueError('That backup does not belong to this account.')
    for name,target in rec['files'].items():
        model.atomic(target,(Path(dest)/name).read_bytes())
    return len(rec['files'])

def write(path,updates):
    """Merge updates into the file atomically, then read it back and return any key that did not stick."""
    path=Path(path)
    try:text=_read(path)
    except FileNotFoundError:text=''
    path.parent.mkdir(parents=True,exist_ok=True)
    model.atomic(path,merge(text,updates).encode('utf-8'))
    now=values(path)
    return sorted(k for k,v in updates.items() if now.get(k)!=v)

# ---------- display helpers ----------
def _f(vals,name):
    v=vals.get(f'EAresFloatSettingName::{name}')
    try:return round(float(v),3) if v is not None else None
    except ValueError:return None

def sensitivity(vals):
    return {'sens':_f(vals,'MouseSensitivity'),'ads':_f(vals,'MouseSensitivityADS'),
            'scoped':_f(vals,'MouseSensitivityZoomed')}

def crosshair(vals):
    """The active crosshair profile, simplified for the preview, or None."""
    raw=vals.get('EAresStringSettingName::SavedCrosshairProfileData')
    if not raw:return None
    try:
        data=json.loads(json.loads(raw)) if raw.startswith('"') else json.loads(raw)
        prof=data['profiles'][int(data.get('currentProfile',0))];p=prof['primary']
    except (ValueError,KeyError,IndexError,TypeError):return None
    col=p.get('colorCustom') if p.get('bUseCustomColor') else p.get('color')
    col=col or {'r':255,'g':255,'b':255,'a':255}
    def lines(l):
        l=l or {}
        return {'show':bool(l.get('bShowLines')),'thickness':l.get('lineThickness',2),'length':l.get('lineLength',4),
                'vlength':l.get('lineLengthVertical',l.get('lineLength',4)) if l.get('bAllowVertScaling') else l.get('lineLength',4),
                'offset':l.get('lineOffset',2),'opacity':l.get('opacity',1)}
    return {'name':prof.get('profileName') or vals.get('EAresStringSettingName::CrosshairProfileName','').strip('"') or 'Crosshair',
            'color':'#%02x%02x%02x'%(col.get('r',255),col.get('g',255),col.get('b',255)),
            'outline':bool(p.get('bHasOutline')),'outline_thickness':p.get('outlineThickness',1),'outline_opacity':p.get('outlineOpacity',.5),
            'dot':bool(p.get('bDisplayCenterDot')),'dot_size':p.get('centerDotSize',2),'dot_opacity':p.get('centerDotOpacity',1),
            'inner':lines(p.get('innerLines')),'outer':lines(p.get('outerLines'))}
