"""Tune crosshair code library - fully local and credential-free.

A VALORANT crosshair code is just the share string you copy out of the game (e.g.
'0;P;c;1;h;0;0l;4;0o;2;0a;1'). This module stores a named, tagged library of those strings in
the app's own folder, and parses a best-effort subset for a rough on-screen preview. It never
reads or writes game files and never touches credentials - the user copies a code and pastes it
into VALORANT themselves (crosshairs are account-synced by Riot, so a code is the reliable way to
move one between accounts). Imports no tkinter."""
from __future__ import annotations
import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
import capture_model as model

MAX_CODE=512
CODE_OK=re.compile(r'^[0-9A-Za-z;._-]+$')
# VALORANT colour indices -> approximate hex for the preview (index 8 uses a custom 'u' hex).
COLORS={'0':'#FFFFFF','1':'#00FF00','2':'#ADFF2F','3':'#CCFF00','4':'#FFFF00','5':'#00FFFF','6':'#FF00FF','7':'#FF0000'}

def validate_code(code):
    """Accept a plausible VALORANT crosshair share string; reject anything that is not one.
    Content is never used to choose a file path - it is only ever stored as text."""
    if not isinstance(code,str):raise ValueError('Crosshair code must be text.')
    code=code.strip()
    if not 1<=len(code)<=MAX_CODE or ';' not in code or not CODE_OK.match(code):
        raise ValueError('That does not look like a VALORANT crosshair code.')
    return code

def _num(v,lo,hi,default):
    try:n=float(v)
    except (TypeError,ValueError):return default
    return max(lo,min(hi,n))

def parse_code(code):
    """Best-effort decode for a rough preview only (colour, centre dot, inner lines). Tolerant of
    unknown keys and malformed input; the stored code remains the source of truth."""
    try:code=validate_code(code)
    except ValueError:return None
    # Codes start with a version/profile token, so values are not pair-aligned from index 0:
    # scan for known keys and take the following token as the value.
    keys={'c','u','h','d','z','a','0b','0l','0t','0o','0a'}
    t=code.split(';');kv={};i=0
    while i<len(t)-1:
        if t[i] in keys:kv[t[i]]=t[i+1];i+=2
        else:i+=1
    color=COLORS.get(kv.get('c'),'#00FFFF')
    if kv.get('c')=='8' and re.fullmatch(r'[0-9A-Fa-f]{6,8}',kv.get('u','')):color='#'+kv['u'][:6]
    return {
        'color':color,
        'dot':kv.get('d')=='1','dot_size':_num(kv.get('z'),1,10,2),'dot_opacity':_num(kv.get('a'),0,1,1),
        'inner':kv.get('0b','1')!='0','inner_length':_num(kv.get('0l'),0,20,4),
        'inner_thickness':_num(kv.get('0t'),1,10,2),'inner_offset':_num(kv.get('0o'),0,20,2),
        'inner_opacity':_num(kv.get('0a'),0,1,1),'outlines':kv.get('h')=='1',
    }

# Ready-made crosshairs (Tune's own picks, written for this app - not copied from any site).
PRESETS=[
    ('Tiny Cyan Dot','0;P;c;5;h;0;d;1;z;2;a;1;0b;0;1b;0','dot'),
    ('Classic Cyan','0;P;c;5;h;0;0t;2;0l;4;0o;2;0a;1;0f;0;1b;0','cross'),
    ('Small Green Plus','0;P;c;1;h;0;0t;1;0l;3;0o;1;0a;1;0f;0;1b;0','cross'),
    ('Yellow Cross + Dot','0;P;c;4;h;0;d;1;z;1;0t;1;0l;3;0o;2;0a;1;0f;0;1b;0','cross'),
    ('Pink Outlined','0;P;c;6;h;1;t;1;o;1;0t;2;0l;4;0o;2;0a;1;0f;0;1b;0','cross'),
    ('Black Crosshair','0;P;c;0;h;1;t;1;o;1;0t;1;0l;2;0o;3;0a;0;0f;0;1b;0','outline'),
    ('Red Dot','0;P;c;7;h;1;o;1;d;1;z;3;0b;0;1b;0','dot'),
    ('White Thin','0;P;c;0;h;0;0t;1;0l;5;0o;3;0a;1;0f;0;1b;0','cross'),
    ('Wide Gap Cyan','0;P;c;5;h;0;0t;2;0l;4;0o;6;0a;1;0f;0;1b;0','cross'),
    ('Dot + Outer Lines','0;P;c;1;h;0;d;1;z;2;0b;0;1b;1;1t;2;1l;3;1o;6;1a;1;1m;0;1f;0','dot'),
    ('Tune Lime','0;P;c;8;u;D7F24BFF;h;0;0t;2;0l;4;0o;2;0a;1;0f;0;1b;0','cross'),
    ('Big Outlined Yellow','0;P;c;4;h;1;t;2;o;0.8;0t;3;0l;6;0o;3;0a;1;0f;0;1b;0','cross'),
]
SITES=[('VCRDB','https://www.vcrdb.net/'),('valorantcrosshair.com','https://valorantcrosshair.com/')]

def preview(code):
    """Decode the primary crosshair of a share code into what the preview canvas draws.
    Missing keys take VALORANT's defaults. None if it isn't a crosshair code."""
    try:code=validate_code(code)
    except ValueError:return None
    t=code.split(';');kv={}
    try:start=t.index('P')+1
    except ValueError:start=0
    i=start
    while i<len(t)-1:
        if t[i] in ('A','S'):break                      # ADS / sniper sections follow the primary one
        kv[t[i]]=t[i+1];i+=2
    color=COLORS.get(kv.get('c','0'),'#FFFFFF')
    if kv.get('c')=='8' and re.fullmatch(r'[0-9A-Fa-f]{6,8}',kv.get('u','')):color='#'+kv['u'][:6]
    def lines(p,show,th,ln,off,op):
        L=_num(kv.get(p+'l'),0,20,ln)
        return {'show':kv.get(p+'b',show)=='1','thickness':_num(kv.get(p+'t'),0,10,th),'length':L,
                'vlength':_num(kv.get(p+'v'),0,20,L) if kv.get(p+'g')=='1' else L,
                'offset':_num(kv.get(p+'o'),0,40,off),'opacity':_num(kv.get(p+'a'),0,1,op)}
    return {'color':color,'outline':kv.get('h','1')=='1','outline_thickness':_num(kv.get('t'),1,6,1),
            'outline_opacity':_num(kv.get('o'),0,1,.5),'dot':kv.get('d')=='1','dot_size':_num(kv.get('z'),1,6,2),
            'dot_opacity':_num(kv.get('a'),0,1,1),'inner':lines('0','1',2,6,3,.8),'outer':lines('1','1',2,2,10,.35)}

def gallery(lib):
    """Presets plus the user's own saved codes, each with a ready preview."""
    mine=[{'id':e['id'],'name':e['name'],'code':e['code'],'kind':'mine','preview':preview(e['code'])} for e in lib.list()]
    picks=[{'id':f'preset-{i}','name':n,'code':c,'kind':'preset','style':s,'preview':preview(c)} for i,(n,c,s) in enumerate(PRESETS)]
    return {'mine':mine,'presets':picks,'sites':[{'name':n,'url':u} for n,u in SITES]}

def _now():return datetime.now(timezone.utc).isoformat()

class Library:
    """CRUD over crosshairs.json in the app folder. Each entry: id, name, code, tags, notes, created."""
    def __init__(self,base):
        self.path=Path(base)/'crosshairs.json'

    def list(self):
        try:data=json.loads(self.path.read_text(encoding='utf-8'))
        except (OSError,ValueError):return []
        out=[]
        if isinstance(data,list):
            for e in data:
                if isinstance(e,dict) and {'id','name','code'}<=set(e):out.append(e)
        return out

    def _write(self,items):
        self.path.parent.mkdir(parents=True,exist_ok=True);model.write_json(self.path,items)

    def add(self,name,code,tags=None,notes=''):
        entry={'id':uuid.uuid4().hex,'name':model.clean_label(name),'code':validate_code(code),
               'tags':[model.clean_label(t) for t in (tags or []) if str(t).strip()][:8],
               'notes':(str(notes) or '')[:400],'created':_now()}
        items=self.list();items.insert(0,entry);self._write(items);return entry

    def delete(self,cid):
        items=[e for e in self.list() if e.get('id')!=cid];self._write(items);return True

    def update(self,cid,name=None,code=None,tags=None,notes=None):
        items=self.list();found=None
        for e in items:
            if e.get('id')==cid:
                if name is not None:e['name']=model.clean_label(name)
                if code is not None:e['code']=validate_code(code)
                if tags is not None:e['tags']=[model.clean_label(t) for t in tags if str(t).strip()][:8]
                if notes is not None:e['notes']=str(notes)[:400]
                found=e
        if found is None:raise ValueError('That crosshair is no longer in the library.')
        self._write(items);return found
