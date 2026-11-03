"""Tune backend - GUI-free orchestration for the web front-end.

Wraps capture_model (all game-file reads/writes), desk_profiles (the app's own store) and desk_rank
(optional online rank). Imports no tkinter and no pywebview, so it is fully unit-testable and runs
on CI. Listing and saving use a no-op guard - they only READ, so they work while VALORANT is open;
applying uses the real game-closed guard. Security model is unchanged: only the 12 video keys are
ever transferred, and no credentials, tokens or login files are read."""
from __future__ import annotations
import json
import re
from pathlib import Path
import capture_model as model
import desk_profiles as dp
import desk_rank
import desk_crosshair

READING=lambda:None   # read-only operations never require the game to be closed
RES_X=re.compile(rb'(?mi)^ResolutionSizeX=(\d{2,5})')
RES_Y=re.compile(rb'(?mi)^ResolutionSizeY=(\d{2,5})')

class Backend:
    def __init__(self,config_root=None,store_base=None,rank_cache=None,guard=None):
        self.config_root=Path(config_root) if config_root is not None else model.config_directory()
        self.store=model.Store(store_base)
        self.crosshairs=desk_crosshair.Library(self.store.base)
        self.rank_cache=Path(rank_cache) if rank_cache is not None else self.store.base/'rank-cache'
        self.guard=guard or model.ensure_closed   # game-closed guard, used only for writes (Apply/Undo)

    # ---------- reads (safe while the game is open) ----------
    def signed_in(self):
        return dp.signed_in(self.config_root)

    def _paths(self):
        return dp.account_paths(model.discover(self.config_root,READING),self.config_root)

    def _saved_index(self):
        """source_ref -> (label, captured_utc) for your own saved profiles (newest capture wins)."""
        index={}
        for _,data in dp.entries(self.store):
            if dp.is_shared(data):continue
            index.setdefault(data['provenance']['source_ref'],(data['label'],data['provenance']['captured_utc']))
        return index

    def _path_for_ref(self,ref):
        """Resolve a short account ref (source_id) to its real file path on THIS machine. The UI
        only ever sends refs/ids across the bridge, never raw Windows paths (which mangle in transit)."""
        for p in self._paths():
            if model.source_id(p)==ref:return p
        raise ValueError('That account is no longer available on this PC.')

    def _profile_for_id(self,pid):
        for p,_ in dp.entries(self.store):
            if p.name==pid:return p
        raise ValueError('That saved profile is no longer in the library.')

    def accounts(self):
        """One entry per VALORANT account folder on this PC, with the signed-in flag, saved label,
        region/puuid (for the optional rank lookup) and a few readable setting hints for the card."""
        signed=self.signed_in();saved=self._saved_index();out=[]
        for path in self._paths():
            ref=model.source_id(path);folder=dp.account_of(path,self.config_root) or ''
            puuid=folder.rsplit('-',1)[0] if '-' in folder else folder
            label,captured=saved.get(ref,(None,None))
            out.append({'ref':ref,'path':str(path),'account':folder,'puuid':puuid,
                        'region':desk_rank.region_from_folder(folder),
                        'signed_in':bool(signed and folder.startswith(signed)),
                        'saved':label,'last_saved':captured,'hints':self._hints(path)})
        return out

    def _hints(self,path):
        """Display-only peek at a card's settings: resolution, FPS cap, VSync. Never transferred,
        best-effort, and never raises - a card still renders if the file is unusual."""
        try:raw=model.read_bytes(path)
        except OSError:return {}
        hints={}
        try:
            values=model.parse(raw)[2]
            if 'FrameRateLimit' in values:hints['fps']=dp.shown('FrameRateLimit',values['FrameRateLimit'])
            if 'bUseVSync' in values:hints['vsync']='On' if values['bUseVSync']=='True' else 'Off'
        except ValueError:pass
        x=RES_X.search(raw);y=RES_Y.search(raw)
        if x and y:hints['resolution']=f'{int(x[1])}×{int(y[1])}'
        elif x:hints['resolution']=x[1].decode()
        return hints

    def profiles(self):
        """Your saved profiles, newest capture first."""
        return [{'id':path.name,'path':str(path),'label':data['label'],
                 'ref':data['provenance']['source_ref'],'captured':data['provenance']['captured_utc'],
                 'n':len(data['settings']),'shared':dp.is_shared(data)}
                for path,data in dp.entries(self.store)]

    def account_settings(self,ref):
        """The full video settings (the 12 keys) on an account's game file, display-ready and
        read-only. VSync is shown as On/Off; everything else keeps its exact value."""
        values=model.parse(model.read_bytes(self._path_for_ref(ref)))[2];out=[]
        for k in dp.ORDER:
            if k not in values:continue
            v='On' if (k=='bUseVSync' and values[k]=='True') else 'Off' if k=='bUseVSync' else dp.shown(k,values[k])
            out.append({'key':k,'name':dp.NAMES[k],'value':v})
        return out

    def rank(self,puuid,region=None):
        """Optional public rank/card lookup. Network-bound - the caller runs it off the UI thread."""
        return desk_rank.lookup(puuid,region,app_dir=self.store.base,cache_dir=self.rank_cache)

    def rank_key_status(self):
        """Whether a rank API key is configured. Never returns the key itself."""
        return {'set':bool(desk_rank.resolve_key(self.store.base))}

    def set_rank_key(self,key):
        """Store a free rank API key in the app folder only, and clear cached 'offline' results so
        rank refetches right away. The key never leaves this PC except as the stats API's own header."""
        key=(key or '').strip()
        if not re.fullmatch(r'[A-Za-z0-9._-]{8,200}',key):raise ValueError('That does not look like a valid key.')
        self.store.base.mkdir(parents=True,exist_ok=True)
        (self.store.base/'rankkey.txt').write_text(key,encoding='utf-8')
        try:
            for f in self.rank_cache.glob('*.json'):f.unlink()
        except OSError:pass
        return {'set':True}

    def clear_rank_key(self):
        try:(self.store.base/'rankkey.txt').unlink()
        except OSError:pass
        return {'set':False}

    def riot_client(self):
        exe=dp.riot_client();return str(exe) if exe else None

    # ---------- writes ----------
    def save(self,ref,label):
        """Capture the 12 video settings from an account's game file into a saved profile
        (works while the game is open - it only reads)."""
        path=self._path_for_ref(ref);data=model.capture(path,label,self.config_root,READING)
        saved,replaced=dp.save_capture(self.store,data)
        try:self.store.label(path,label);self.store.remember(path)
        except (OSError,ValueError):pass
        return {'path':str(saved),'label':label,'replaced':replaced,
                'captured':data['provenance']['captured_utc'],'n':len(data['settings'])}

    def apply(self,profile_id,target_ref):
        """Write a saved profile's video settings onto another account (requires the game closed).
        Always snapshots the target first, so every apply is undoable. Returns the applied delta."""
        profile=model.import_profile(self._profile_for_id(profile_id));target_path=self._path_for_ref(target_ref)
        self._check_closed()
        raw,delta=model.preview(target_path,profile,self.config_root,self.guard)
        if not delta:return {'applied':0,'delta':[],'backup':None}
        backup=model.apply(target_path,profile['settings'],raw,self.store.base/'backups',self.config_root,self.guard)
        return {'applied':len(delta),'backup':str(backup) if backup else None,
                'delta':[{'key':k,'from':a,'to':b} for k,a,b in delta]}

    def apply_to_all(self,profile_id):
        """Copy a saved profile's video settings onto every OTHER account (game must be closed).
        Each target is auto-backed-up first, so the whole sweep stays undoable per account."""
        profile=model.import_profile(self._profile_for_id(profile_id));self._check_closed()
        src=profile['provenance']['source_ref'];results=[]
        for path in self._paths():
            if model.source_id(path)==src:continue
            acc=dp.account_of(path,self.config_root)
            try:
                raw,delta=model.preview(path,profile,self.config_root,self.guard)
                if not delta:results.append({'account':acc,'applied':0});continue
                backup=model.apply(path,profile['settings'],raw,self.store.base/'backups',self.config_root,self.guard)
                results.append({'account':acc,'applied':len(delta),'backup':str(backup) if backup else None})
            except Exception as e:
                results.append({'account':acc,'error':str(e)})
        return {'targets':len(results),'changed':sum(1 for r in results if r.get('applied')),'results':results}

    def share_code(self,profile_id):
        """A shareable preset string: the video values plus your label only - no account names,
        file paths, IDs, sensitivity or timestamps."""
        data=model.import_profile(self._profile_for_id(profile_id))
        return json.dumps(dp.share_payload(data,data['label']))

    def share_import(self,text):
        """Import a shared preset string into your library. Strictly validated, then stored."""
        import os,tempfile
        with tempfile.NamedTemporaryFile('w',suffix='.json',delete=False,encoding='utf-8') as f:
            f.write(text or '');tmp=f.name
        try:data=dp.read_import(tmp);saved=self.store.save(data)
        finally:
            try:os.unlink(tmp)
            except OSError:pass
        return {'path':str(saved),'label':data['label'],'n':len(data['settings'])}

    def _check_closed(self):
        try:self.guard()
        except RuntimeError:
            raise RuntimeError('Close VALORANT and Riot Client first, then apply again. '
                               'While the game runs it rewrites its own settings on exit.') from None

    # ---------- crosshair code library (local, credential-free) ----------
    def crosshair_list(self):return self.crosshairs.list()
    def crosshair_add(self,name,code,tags=None,notes=''):return self.crosshairs.add(name,code,tags,notes)
    def crosshair_update(self,cid,name=None,code=None,tags=None,notes=None):return self.crosshairs.update(cid,name=name,code=code,tags=tags,notes=notes)
    def crosshair_delete(self,cid):return self.crosshairs.delete(cid)
    def crosshair_parse(self,code):return desk_crosshair.parse_code(code)
