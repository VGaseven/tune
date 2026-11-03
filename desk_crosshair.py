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
COLORS={'0':'#FFFFFF','1':'#00FF00','2':'#ADFF2F','3':'#CCFF00','4':'#FFFF00','5':'#00FFFF','6':'#FF00C8','7':'#FF0000'}

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
