"""Tune backend - GUI-free orchestration for the web front-end.

Wraps capture_model (all game-file reads/writes), desk_profiles (the app's own store) and desk_rank
(optional online rank). Imports no tkinter and no pywebview, so it is fully unit-testable and runs
on CI. Listing and saving use a no-op guard - they only READ, so they work while VALORANT is open;
applying uses the real game-closed guard. Only settings files are written (the 12 video keys in
GameUserSettings.ini and the game preferences in RiotUserSettings.ini, via desk_master). Passwords
are never read. Only if the user turns on one-click switching for an account does desk_signin keep
an encrypted copy of Riot Client's own "Stay signed in" files for it."""
from __future__ import annotations
import json
import re
from pathlib import Path
import capture_model as model
import desk_profiles as dp
import desk_rank
import desk_crosshair
import desk_master
import desk_signin

BLANK=bytes([0xef,0xbb,0xbf,0xff,0xfe,0x20,0x0d,0x0a,0x09,0x00])   # BOMs, whitespace, NULs: an empty video stub
READING=lambda:None   # read-only operations never require the game to be closed
RES_X=re.compile(rb'(?mi)^ResolutionSizeX=(\d{2,5})')
RES_Y=re.compile(rb'(?mi)^ResolutionSizeY=(\d{2,5})')

class Backend:
    def __init__(self,config_root=None,store_base=None,rank_cache=None,guard=None,game_running=None,signins=None):
        self.config_root=Path(config_root) if config_root is not None else model.config_directory()
        self.store=model.Store(store_base)
        self.crosshairs=desk_crosshair.Library(self.store.base)
        self.rank_cache=Path(rank_cache) if rank_cache is not None else self.store.base/'rank-cache'
        self.guard=guard or model.ensure_closed   # game-closed guard, used only for writes (Apply/Undo)
        self.game_running=game_running or model.valorant_running   # main-settings sync only blocks the signed-in account
        self.signins=signins or desk_signin.SignIns(self.store.base)   # opt-in one-click switching

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
        signed=self.signed_in();saved=self._saved_index();master=self.master_ref();out=[]
        for path in self._paths():
            ref=model.source_id(path);folder=dp.account_of(path,self.config_root) or ''
            puuid=folder.rsplit('-',1)[0] if '-' in folder else folder
            label,captured=saved.get(ref,(None,None))
            out.append({'ref':ref,'path':str(path),'account':folder,'puuid':puuid,
                        'region':desk_rank.region_from_folder(folder),
                        'signed_in':bool(signed and folder.startswith(signed)),
                        'saved':label,'last_saved':captured,'hints':self._hints(path),
                        'sens':desk_master.sensitivity(desk_master.values(desk_master.riot_file(path)))['sens'],
                        'is_master':ref==master})
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

    def rank(self,puuid,region=None,force=False):
        """Optional public rank/card lookup. Network-bound - the caller runs it off the UI thread."""
        return desk_rank.lookup(puuid,region,app_dir=self.store.base,cache_dir=self.rank_cache,force=bool(force))

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

    # ---------- main account (one shared configuration) ----------
    def _master_file(self):return self.store.base/'master.json'

    def master_ref(self):
        """The account whose settings every other account copies. Chosen once by the user; until
        then it defaults to the account currently signed in."""
        try:
            ref=model.read_json(self._master_file()).get('ref')
            if isinstance(ref,str) and any(model.source_id(p)==ref for p in self._paths()):return ref
        except (OSError,ValueError,AttributeError):pass
        signed=self.signed_in()
        for p in self._paths():
            if signed and (dp.account_of(p,self.config_root) or '').startswith(signed):return model.source_id(p)
        return None

    def set_master(self,ref):
        self._path_for_ref(ref);self.store.base.mkdir(parents=True,exist_ok=True)
        model.write_json(self._master_file(),{'ref':ref});return {'ref':ref}

    def master(self):
        """The shared configuration, read live from the main account's own files."""
        ref=self.master_ref()
        return self.account_view(ref) if ref else {'ref':None}

    def account_view(self,ref):
        """One account's own current configuration (sensitivity, crosshair, video), read live."""
        path=self._path_for_ref(ref);vals=desk_master.values(desk_master.riot_file(path))
        try:video=self.account_settings(ref)
        except (OSError,ValueError):video=[]   # VALORANT leaves empty stubs until that account changes a video option
        return {'ref':ref,'account':dp.account_of(path,self.config_root),'game_settings':len(desk_master.shared(vals)),
                **desk_master.sensitivity(vals),'crosshair':desk_master.crosshair(vals),'crosshair_code':desk_master.crosshair_code(vals),
                'video':video,'resolution':self._hints(path).get('resolution')}

    def status(self):
        """Is VALORANT running, and which account is it signed in to (by ref)? Read-only."""
        try:running=bool(self.game_running())
        except RuntimeError:running=None
        signed=self.signed_in();ref=None
        if signed:
            for path in self._paths():
                if path.parent.parent.name.startswith(signed):ref=model.source_id(path);break
        return {'game_running':running,'signed_in_ref':ref}

    def apply_all_from(self,source):
        """Copy one account's settings onto every other account that differs. Accounts that can't
        be written right now (VALORANT open on them) are skipped and reported, never forced."""
        self._path_for_ref(source);results=[]
        for path in self._paths():
            ref=model.source_id(path)
            if ref==source:continue
            acc=dp.account_of(path,self.config_root)
            try:
                if self.compare(source,ref)['in_sync']:results.append({'ref':ref,'account':acc,'status':'same'});continue
                out=self.apply_from(source,ref);results.append({'ref':ref,'account':acc,'status':'applied','changed':out['changed'],'video_note':out['video_note']})
            except Exception as e:
                results.append({'ref':ref,'account':acc,'status':'skipped','error':str(e)})
        return {'results':results,'applied':sum(r['status']=='applied' for r in results),
                'same':sum(r['status']=='same' for r in results),'skipped':sum(r['status']=='skipped' for r in results)}

    def apply_master_all(self):
        mref=self.master_ref()
        if not mref:raise ValueError('Pick the account to copy settings from.')
        return self.apply_all_from(mref)

    def _applied(self):
        """{target_ref: {'at': iso, 'from': source_ref}} - older files stored just the time."""
        try:d=model.read_json(self.store.base/'applied.json')
        except (OSError,ValueError):return {}
        if not isinstance(d,dict):return {}
        mref=self.master_ref() if self._master_file().exists() else None
        return {k:(v if isinstance(v,dict) else {'at':v,'from':mref}) for k,v in d.items()}

    def compare(self,source,target):
        """How many shared settings differ between two accounts right now (re-read from disk)."""
        spath=self._path_for_ref(source);tpath=self._path_for_ref(target)
        svals=desk_master.values(desk_master.riot_file(spath));tvals=desk_master.values(desk_master.riot_file(tpath))
        differ=desk_master.diff(svals,tvals)
        try:sv=model.parse(model.read_bytes(spath))[2]
        except (OSError,ValueError):sv={}
        try:tv=model.parse(model.read_bytes(tpath))[2]
        except (OSError,ValueError):tv={}
        vdiffer=[k for k,v in sv.items() if tv.get(k)!=v]
        return {'in_sync':not differ and not vdiffer,'differ':len(differ)+len(vdiffer),'total':len(desk_master.shared(svals))+len(sv)}

    def sync_report(self,ref):
        """Compared with the account whose settings were last applied here. After you play, a
        mismatch means Riot restored its online copy of those settings."""
        self._path_for_ref(ref);rec=self._applied().get(ref) or {}
        out={'source':None,'in_sync':None,'differ':None,'applied_at':rec.get('at'),
             'has_backup':bool(desk_master.latest_backup(self.store.base/'backups'/'master',ref))}
        src=rec.get('from')
        if src and src!=ref:
            try:out.update(self.compare(src,ref),source=src)
            except ValueError:pass            # that account is no longer on this PC
        return out

    def apply_from(self,source,ref):
        """Copy one account's whole configuration (video + game preferences such as sensitivity
        and crosshair) onto another, then verify it by reading the files back. Works while
        VALORANT is open, except on the account it is signed in to (the game would overwrite it on
        exit). The target is backed up first; the source account is only ever read."""
        if not source:raise ValueError('Pick the account to copy settings from.')
        if ref==source:raise ValueError('Pick a different account to copy from.')
        mpath=self._path_for_ref(source);tpath=self._path_for_ref(ref)
        self._check_target(tpath)
        mvals=desk_master.shared(desk_master.values(desk_master.riot_file(mpath)))
        if not mvals:raise ValueError('That account has no saved game settings on this PC yet. Play one match on it, then try again.')
        before=desk_master.values(desk_master.riot_file(tpath));changed=desk_master.diff(mvals,before)
        dest=desk_master.backup([tpath,desk_master.riot_file(tpath)],self.store.base/'backups'/'master',ref)
        failed=desk_master.write(desk_master.riot_file(tpath),mvals)
        vchanged=0;vfail=[];note=None;nvideo=0
        try:profile=model.capture(mpath,'Source account',self.config_root,READING)
        except ValueError:profile=None;note="the account you copied from has no video settings saved yet, so graphics were left as they are"
        if profile:
            nvideo=len(profile['settings'])
            try:
                raw,delta=model.preview(tpath,profile,self.config_root,READING)
                if delta:model.apply(tpath,profile['settings'],raw,self.store.base/'backups',self.config_root,READING)
                vchanged=len(delta);now=model.parse(model.read_bytes(tpath))[2]
                vfail=[k for k,v in profile['settings'].items() if now.get(k)!=v]
            except ValueError as e:
                # An empty/placeholder video file (VALORANT leaves 2-byte stubs) means "no settings yet":
                # give it the source account's whole video file, then verify. Anything else is left alone.
                try:blank=len(model.read_bytes(tpath).strip(BLANK))<16
                except OSError:blank=True
                if blank:
                    model.atomic(tpath,model.read_bytes(mpath));now=model.parse(model.read_bytes(tpath))[2]
                    vchanged=nvideo;vfail=[k for k,v in profile['settings'].items() if now.get(k)!=v]
                else:note=str(e);nvideo=0
        if failed or vfail:
            raise RuntimeError(f'Could not verify {len(failed)+len(vfail)} settings after writing. Your backup is in {dest}.')
        at=model.now();rec=self._applied();rec[ref]={'at':at,'from':source}
        try:model.write_json(self.store.base/'applied.json',rec)
        except OSError:pass
        return {'verified':True,'at':at,'game':len(mvals),'video':nvideo,
                'changed':len(changed)+vchanged,'video_note':note,'backup':str(dest),'from':source}

    def apply_master(self,ref):
        """Older name: copy from the remembered main account."""
        return self.apply_from(self.master_ref(),ref)

    def restore_backup(self,ref):
        """Put an account's files back exactly as they were before the last Apply."""
        self._check_target(self._path_for_ref(ref))
        dest=desk_master.latest_backup(self.store.base/'backups'/'master',ref)
        if not dest:raise ValueError('No backup for this account yet.')
        n=desk_master.restore(dest,ref)
        rec=self._applied();rec.pop(ref,None)
        try:model.write_json(self.store.base/'applied.json',rec)
        except OSError:pass
        return {'restored':n}

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

    def _check_target(self,path):
        """Writing another account's files is safe while VALORANT runs - the game only rewrites the
        account it is signed in to. Refuse just that one (or any, if we can't tell which it is)."""
        try:running=self.game_running()
        except RuntimeError:running=True
        if not running:return
        signed=self.signed_in()
        if not signed or Path(path).parent.parent.name.startswith(signed):
            raise RuntimeError('VALORANT is open on this account, so it would undo the change when it closes. '
                               'Quit VALORANT first, or apply to a different account.')

    def _check_closed(self):
        try:self.guard()
        except RuntimeError:
            raise RuntimeError('Close VALORANT and Riot Client first, then apply again. '
                               'While the game runs it rewrites its own settings on exit.') from None

    # ---------- one-click switching (opt-in, per account) ----------
    def signin_saved(self):
        known={model.source_id(p) for p in self._paths()}
        return {ref:at for ref,at in self.signins.saved().items() if ref in known}

    def remember_signin(self,ref,confirmed=False):
        """Save Riot Client's current sign-in for ref. Automatic while VALORANT is open on ref;
        otherwise only when the user confirms Riot Client is signed in to ref (checked again the
        next time VALORANT starts)."""
        self._path_for_ref(ref);st=self.status()
        if st['game_running'] and st['signed_in_ref'] and st['signed_in_ref']!=ref:
            raise RuntimeError("VALORANT is open on a different account, so Riot Client is signed in to that one, not this one.")
        if not (st['game_running'] and st['signed_in_ref']==ref) and not confirmed:
            raise RuntimeError('Sign in to this account in Riot Client first (with "Stay signed in" ticked), then save it.')
        return self.signins.remember(ref)

    def tcno_accounts(self):
        return {'accounts':self.signins.tcno_accounts()}

    def import_tcno(self,pairs):
        """pairs: [{'name': TcNo account name, 'ref': Tune account}] - copy each into Tune."""
        done=[];failed=[]
        for p in pairs or []:
            try:self._path_for_ref(p['ref']);self.signins.import_tcno(p['name'],p['ref']);done.append(p['ref'])
            except Exception as e:failed.append({'name':p.get('name'),'error':str(e)})
        return {'imported':len(done),'failed':failed}

    def keep_signin_fresh(self):
        st=self.status();ref=st['signed_in_ref']
        if st['game_running'] and ref and ref in self.signins.saved():return {'refreshed':self.signins.keep_fresh(ref)}
        return {'refreshed':False}

    def switch_to(self,ref,launch):
        self._path_for_ref(ref)
        return self.signins.switch(ref,launch)

    def undo_switch(self,launch):return self.signins.undo_switch(launch)
    def can_undo_switch(self):return self.signins.has_previous()

    def forget_signins(self,ref=None):
        return self.signins.forget(ref or None)

    # ---------- crosshair code library (local, credential-free) ----------
    def crosshair_list(self):return self.crosshairs.list()
    def crosshair_add(self,name,code,tags=None,notes=''):return self.crosshairs.add(name,code,tags,notes)
    def crosshair_update(self,cid,name=None,code=None,tags=None,notes=None):return self.crosshairs.update(cid,name=name,code=code,tags=tags,notes=notes)
    def crosshair_delete(self,cid):return self.crosshairs.delete(cid)
    def crosshair_parse(self,code):return desk_crosshair.parse_code(code)
    def crosshair_gallery(self):return desk_crosshair.gallery(self.crosshairs)
    def crosshair_preview(self,code):return desk_crosshair.preview(code)
