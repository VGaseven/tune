"""Tune online rank & player-card lookup (optional, best-effort).

Given the account id VALORANT itself logged (a puuid), fetch the PUBLIC profile - Riot name#tag,
current rank, equipped player-card art - from a public stats API so the account cards can show
them. No passwords, session tokens or login files are ever read; only the puuid and region leave
the PC, and only to request the public profile. Every failure degrades to 'offline' so the UI
always has something to show. This module imports no tkinter and makes no network call unless
lookup() is asked to (and even then only when a key is available)."""
from __future__ import annotations
import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

# Public providers. Henrik serves the live profile/rank; valorant-api serves static card art (no key).
ACCOUNT_URL='https://api.henrikdev.xyz/valorant/v2/by-puuid/account/{puuid}'
MMR_URL='https://api.henrikdev.xyz/valorant/v3/by-puuid/mmr/{region}/{platform}/{puuid}'
CARD_ART='https://media.valorant-api.com/playercards/{card}/largeart.png'
REGIONS=('eu','na','ap','kr','latam','br')
PLATFORM='pc'
DEFAULT_KEY=''   # deliberately empty in the public repo; a real key is supplied at runtime (resolve_key).
PUUID=re.compile(r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$')
CARD_ID=re.compile(r'^[0-9a-fA-F-]{10,40}$')

class RankError(Exception):
    """Any lookup failure (network, bad response). Always caught inside lookup()."""

def region_from_folder(name):
    """VALORANT names account folders '<puuid>-<region>' (e.g. ...-eu). Returns the region or None."""
    if not name:return None
    tail=str(name).rsplit('-',1)[-1].lower()
    return tail if tail in REGIONS else None

def resolve_key(app_dir=None):
    """Runtime API key, never committed: env TUNE_RANK_KEY, then <app_dir>/rankkey.txt, then the
    (empty) bundled default. Whitespace-stripped; returns '' when none is set."""
    env=os.environ.get('TUNE_RANK_KEY','').strip()
    if env:return env
    if app_dir:
        try:
            text=(Path(app_dir)/'rankkey.txt').read_text(encoding='utf-8').strip()
            if text:return text
        except OSError:pass
    return DEFAULT_KEY.strip()

def card_image_url(card_id):
    return CARD_ART.format(card=card_id) if card_id and CARD_ID.match(str(card_id)) else None

def _offline():
    return {'name':None,'tag':None,'rank':None,'rr':None,'card_id':None,'card_url':None,
            'rank_icon':None,'source':'offline'}

def _http_json(url,headers,timeout=6,max_bytes=1_000_000):
    req=urllib.request.Request(url,headers=headers or {})
    try:
        with urllib.request.urlopen(req,timeout=timeout) as r:raw=r.read(max_bytes+1)
    except (urllib.error.URLError,OSError,ValueError) as e:raise RankError('network') from e
    if len(raw)>max_bytes:raise RankError('too large')
    try:return json.loads(raw.decode('utf-8'))
    except (UnicodeError,json.JSONDecodeError) as e:raise RankError('bad json') from e

def _norm(account,mmr):
    """Flatten the two public responses into the small dict the UI uses. Tolerant of missing keys."""
    a=(account or {}).get('data') or {}
    card=a.get('card') or {}
    card_id=card.get('id') if isinstance(card,dict) else card
    cur=((mmr or {}).get('data') or {}).get('current_data') or {}
    images=cur.get('images') or {}
    return {'name':a.get('name'),'tag':a.get('tag'),
            'rank':cur.get('currenttierpatched'),'rr':cur.get('ranking_in_tier'),
            'card_id':card_id,'card_url':card_image_url(card_id),
            'rank_icon':images.get('small') or images.get('large'),'source':'online'}

def _cache_file(cache_dir,puuid):return Path(cache_dir)/f'{puuid}.json'

def _read_cache(cache_dir,puuid,max_age):
    try:rec=json.loads(_cache_file(cache_dir,puuid).read_text(encoding='utf-8'))
    except (OSError,ValueError):return None
    if not isinstance(rec,dict) or not isinstance(rec.get('at'),(int,float)):return None
    if time.time()-rec['at']>max_age or not isinstance(rec.get('data'),dict):return None
    out=dict(rec['data']);out['source']='cache';return out

def _write_cache(cache_dir,puuid,data):
    try:
        Path(cache_dir).mkdir(parents=True,exist_ok=True)
        # only the normalized public profile is stored - never the key or any raw response
        _cache_file(cache_dir,puuid).write_text(json.dumps({'at':time.time(),'data':data}),encoding='utf-8')
    except OSError:pass

def lookup(puuid,region,*,key=None,app_dir=None,cache_dir=None,max_age=21600,fetch=None,platform=PLATFORM):
    """Best-effort public profile for a puuid. Returns a dict with name/tag/rank/rr/card_url/source,
    where source is 'online' (fresh), 'cache' (recent copy) or 'offline' (nothing fetched).
    Never raises and never blocks the UI thread's state - callers run it in a worker thread."""
    if not PUUID.match(str(puuid or '')):return _offline()
    if cache_dir:
        hit=_read_cache(cache_dir,puuid,max_age)
        if hit:return hit
    key=key if key is not None else resolve_key(app_dir)
    if not key:return _offline()
    region=(region or '').lower()
    get=fetch or (lambda url:_http_json(url,{'Authorization':key}))
    try:account=get(ACCOUNT_URL.format(puuid=puuid))
    except RankError:return _offline()
    mmr=None
    if region in REGIONS:
        try:mmr=get(MMR_URL.format(region=region,platform=platform,puuid=puuid))
        except RankError:mmr=None
    data=_norm(account,mmr)
    if cache_dir:_write_cache(cache_dir,puuid,data)
    return data

def display(data):
    """'name#tag' when known, else ''. Safe for the UI."""
    if data and data.get('name') and data.get('tag'):return f"{data['name']}#{data['tag']}"
    return ''

def rank_label(data):
    """Rank text for a card: the rank when online/cached, 'Unranked' when known but no rank, '' offline."""
    if not data or data.get('source')=='offline':return ''
    return data.get('rank') or 'Unranked'
