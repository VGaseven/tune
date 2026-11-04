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
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

# Public providers. Henrik serves the live profile/rank; valorant-api serves static card art (no key).
ACCOUNT_URL='https://api.henrikdev.xyz/valorant/v2/by-puuid/account/{puuid}'
MMR_URL='https://api.henrikdev.xyz/valorant/v3/by-puuid/mmr/{region}/{platform}/{puuid}'
MATCHES_URL='https://api.henrikdev.xyz/valorant/v1/by-puuid/stored-matches/{region}/{puuid}?mode=competitive&size=20'
CARD_ART='https://media.valorant-api.com/playercards/{card}/largeart.png'
TIER_ICON='https://media.valorant-api.com/competitivetiers/03621f52-342b-cf4e-4f86-9350a49c6d04/{tier}/largeicon.png'
USER_AGENT='Tune/7.4 (+https://github.com/VGaseven/tune)'
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
    return {'name':None,'tag':None,'rank':None,'rr':None,'peak':None,'card_id':None,'card_url':None,
            'rank_icon':None,'wr':None,'wins':None,'games':None,'hs':None,'hs_matches':0,'source':'offline'}

_PACE=threading.Lock();_LAST=[0.0]
GAP=2.1   # seconds between calls: keeps a burst of 7 accounts under the free key's 30 requests/minute

def _http_json(url,headers,timeout=15,max_bytes=1_000_000):
    req=urllib.request.Request(url,headers={'User-Agent':USER_AGENT,'Accept':'application/json',**(headers or {})})
    for attempt in (0,1):
        with _PACE:
            wait=_LAST[0]+GAP-time.monotonic()
            if wait>0:time.sleep(wait)
            _LAST[0]=time.monotonic()
        try:
            with urllib.request.urlopen(req,timeout=timeout) as r:raw=r.read(max_bytes+1)
            break
        except urllib.error.HTTPError as e:
            if e.code==429 and attempt==0:
                try:time.sleep(min(30,float(e.headers.get('Retry-After') or 10)))
                except ValueError:time.sleep(10)
                continue
            raise RankError(f'http {e.code}') from e
        except (urllib.error.URLError,OSError,ValueError) as e:
            if attempt==0:continue   # the free API is sometimes slow: one quiet retry
            raise RankError('network') from e
    if len(raw)>max_bytes:raise RankError('too large')
    try:return json.loads(raw.decode('utf-8'))
    except (UnicodeError,json.JSONDecodeError) as e:raise RankError('bad json') from e

def _norm(account,mmr):
    """Flatten the two public responses into the small dict the UI uses. Tolerant of missing keys."""
    a=(account or {}).get('data') or {}
    card=a.get('card') or {}
    card_id=card.get('id') if isinstance(card,dict) else card
    m=(mmr or {}).get('data') or {}
    if isinstance(m.get('current'),dict):   # v3 shape: current.tier.{id,name}, current.rr
        cur=m['current'];tier=cur.get('tier') or {}
        rank,rr,tid,icon=tier.get('name'),cur.get('rr'),tier.get('id'),None
        peak=((m.get('peak') or {}).get('tier') or {}).get('name')
    else:                                   # legacy v2 shape: current_data.*
        cur=m.get('current_data') or {};images=cur.get('images') or {}
        rank,rr,tid=cur.get('currenttierpatched'),cur.get('ranking_in_tier'),cur.get('currenttier')
        icon=images.get('small') or images.get('large');peak=None
    if not icon and isinstance(tid,int) and (tid==0 or tid>2):icon=TIER_ICON.format(tier=tid)   # 0 = Unrated emblem
    return {'name':a.get('name'),'tag':a.get('tag'),
            'rank':rank,'rr':rr,'peak':peak,
            'card_id':card_id,'card_url':card_image_url(card_id),
            'rank_icon':icon,'source':'online'}

def stats(mmr,matches):
    """Real numbers only: win rate for the current act (from the rank history) and headshot rate
    over the last stored competitive matches. None when the data simply isn't there."""
    out={'wr':None,'wins':None,'games':None,'hs':None,'hs_matches':0}
    seasonal=((mmr or {}).get('data') or {}).get('seasonal') or []
    if seasonal and isinstance(seasonal[-1],dict):
        w,g=seasonal[-1].get('wins'),seasonal[-1].get('games')
        if isinstance(w,int) and isinstance(g,int) and g>0:out.update(wr=round(100*w/g),wins=w,games=g)
    head=total=n=0
    rows=(matches or {}).get('data') if isinstance(matches,dict) else None
    for m in rows if isinstance(rows,list) else []:
        if not isinstance(m,dict):continue
        s=(m.get('stats') or {}).get('shots') or {}
        try:h,b,l=int(s.get('head',0)),int(s.get('body',0)),int(s.get('leg',0))
        except (TypeError,ValueError):continue
        if h+b+l:head+=h;total+=h+b+l;n+=1
    if total:out.update(hs=round(100*head/total,1),hs_matches=n)
    return out

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

def lookup(puuid,region,*,key=None,app_dir=None,cache_dir=None,max_age=3600,fetch=None,platform=PLATFORM,force=False):
    """Best-effort public profile for a puuid. Returns a dict with name/tag/rank/rr/card_url/source,
    where source is 'online' (fresh), 'cache' (recent copy) or 'offline' (nothing fetched).
    force=True skips the local copy and asks the API to re-read the profile (new player card etc.).
    Never raises and never blocks the UI thread's state - callers run it in a worker thread."""
    if not PUUID.match(str(puuid or '')):return _offline()
    if cache_dir and not force:
        hit=_read_cache(cache_dir,puuid,max_age)
        if hit:return hit
    key=key if key is not None else resolve_key(app_dir)
    if not key:return _offline()
    region=(region or '').lower()
    get=fetch or (lambda url:_http_json(url,{'Authorization':key}))
    try:account=get(ACCOUNT_URL.format(puuid=puuid)+('?force=true' if force else ''))
    except RankError:return _offline()
    mmr=matches=None
    if region in REGIONS:
        try:mmr=get(MMR_URL.format(region=region,platform=platform,puuid=puuid))
        except RankError:mmr=None
        try:matches=get(MATCHES_URL.format(region=region,puuid=puuid))
        except RankError:matches=None
    data=_norm(account,mmr);data.update(stats(mmr,matches))
    complete=region not in REGIONS or (mmr is not None and matches is not None)
    if cache_dir and complete:_write_cache(cache_dir,puuid,data)   # partial results are retried next time
    return data

def display(data):
    """'name#tag' when known, else ''. Safe for the UI."""
    if data and data.get('name') and data.get('tag'):return f"{data['name']}#{data['tag']}"
    return ''

def rank_label(data):
    """Rank text for a card: the rank when online/cached, 'Unranked' when known but no rank, '' offline."""
    if not data or data.get('source')=='offline':return ''
    return data.get('rank') or 'Unranked'
