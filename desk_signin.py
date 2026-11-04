"""One-click account switching, the way TcNo Account Switcher does it - opt-in, per account.

Riot Client keeps "Stay signed in" in its Data folder (RiotGamesPrivateSettings.yaml, its cookie
store and Sessions) plus Config\\RiotClientSettings.yaml - the same set TcNo swaps. Remembering an
account copies those files (or imports TcNo's saved copy of them). Switching closes Riot Client
(never VALORANT), puts the chosen account's copy back and starts Riot Client again, which signs
straight in. After VALORANT starts, its log says which account it really is, so a copy saved
under the wrong name is caught.

The copies are a sign-in for the account, so they are encrypted with Windows DPAPI (tied to this
Windows user on this PC - useless if copied elsewhere), never shown, logged or sent anywhere, and
can be deleted at any time. Tune never sees or asks for a password."""
from __future__ import annotations
import ctypes
import json
import os
import subprocess
import time
from datetime import datetime,timezone
from pathlib import Path

CONFIG_FILES=('Config/RiotClientSettings.yaml',)               # relative to the Riot Client folder; everything in Data/ is saved too
SIGNIN_FILE='Data/RiotGamesPrivateSettings.yaml'
MAX_BYTES=20_000_000
RIOT_PROCS=('riotclientservices.exe','riot client.exe','riotclientux.exe','riotclientuxrender.exe','riotclientcrashhandler.exe')
FORMAT='tune-signin'


def riot_root():
    return Path(os.environ.get('LOCALAPPDATA',''))/'Riot Games'/'Riot Client'

def tcno_cache():
    return Path(os.environ.get('APPDATA',''))/'TcNo Account Switcher'/'LoginCache'/'Riot Games'


# ---------- Windows DPAPI (current user) ----------
class _Blob(ctypes.Structure):
    _fields_=[('cbData',ctypes.c_uint32),('pbData',ctypes.POINTER(ctypes.c_char))]

def _blob(data):
    buf=ctypes.create_string_buffer(data,len(data));return _Blob(len(data),ctypes.cast(buf,ctypes.POINTER(ctypes.c_char))),buf

def protect(data:bytes)->bytes:
    crypt=ctypes.windll.crypt32;inp,_keep=_blob(data);out=_Blob()
    if not crypt.CryptProtectData(ctypes.byref(inp),'Tune sign-in',None,None,None,0x1,ctypes.byref(out)):
        raise RuntimeError('Windows could not encrypt the saved sign-in.')
    try:return ctypes.string_at(out.pbData,out.cbData)
    finally:ctypes.windll.kernel32.LocalFree(out.pbData)

def unprotect(data:bytes)->bytes:
    crypt=ctypes.windll.crypt32;inp,_keep=_blob(data);out=_Blob()
    if not crypt.CryptUnprotectData(ctypes.byref(inp),None,None,None,None,0x1,ctypes.byref(out)):
        raise RuntimeError('This saved sign-in was made on another PC or Windows user. Remember it again here.')
    try:return ctypes.string_at(out.pbData,out.cbData)
    finally:ctypes.windll.kernel32.LocalFree(out.pbData)


# ---------- processes ----------
def process_names():
    import capture_model
    return [n.lower() for n in capture_model.process_names()]

def kill_riot_client():
    """Close Riot Client's own processes. VALORANT itself is never touched."""
    flags=getattr(subprocess,'CREATE_NO_WINDOW',0)
    for name in RIOT_PROCS:
        subprocess.run(['taskkill','/F','/IM',name],capture_output=True,creationflags=flags)


class SignIns:
    """Saved sign-ins under <store>/signins, one encrypted file per account ref."""
    def __init__(self,store,root=None,procs=process_names,kill=kill_riot_client,
                 seal=protect,unseal=unprotect,sleep=time.sleep,tcno=None):
        self.dir=Path(store)/'signins';self.root=Path(root) if root else riot_root()
        self.tcno=Path(tcno) if tcno else tcno_cache()
        self.procs,self.kill,self.seal,self.unseal,self.sleep=procs,kill,seal,unseal,sleep

    def _file(self,ref):
        if not ref or not all(c in '0123456789abcdef' for c in ref):raise ValueError('Unknown account.')
        return self.dir/f'{ref}.bin'

    def saved(self):
        """{ref: saved_at} for every remembered account (no secrets)."""
        out={}
        for p in sorted(self.dir.glob('*.bin')) if self.dir.exists() else []:
            out[p.stem]=datetime.fromtimestamp(p.stat().st_mtime,timezone.utc).isoformat()
        return out

    @staticmethod
    def _collect(folder,prefix,out):
        """Add every file under folder to out as prefix/relative/path -> hex."""
        if not folder.is_dir():return
        for f in sorted(folder.rglob('*')):
            if f.is_file() and not f.name.endswith('.tune-tmp'):
                out[prefix+'/'+f.relative_to(folder).as_posix()]=f.read_bytes().hex()

    @staticmethod
    def _check(files):
        if SIGNIN_FILE not in files:
            raise RuntimeError('Riot Client has no saved sign-in on this PC. Tick "Stay signed in" when you sign in, then try again.')
        if sum(len(v)//2 for v in files.values())>MAX_BYTES:raise RuntimeError('Riot Client\'s sign-in files are unexpectedly large, so they were not saved.')
        return files

    def _snapshot(self):
        files={};self._collect(self.root/'Data','Data',files)
        for rel in CONFIG_FILES:
            f=self.root/rel
            if f.is_file():files[rel]=f.read_bytes().hex()
        return self._check(files)

    def _store(self,ref,files,source):
        path=self._file(ref);payload=json.dumps({'format':FORMAT,'v':2,'source':source,'files':files}).encode()
        self.dir.mkdir(parents=True,exist_ok=True);tmp=path.with_suffix('.tmp')
        tmp.write_bytes(self.seal(payload));tmp.replace(path)
        return {'ref':ref,'saved_at':self.saved()[ref]}

    def remember(self,ref):
        """Save Riot Client's current sign-in as `ref` (the caller makes sure ref is the right account)."""
        self._file(ref);return self._store(ref,self._snapshot(),'riot')

    # ---------- TcNo Account Switcher's saved Riot accounts ----------
    def tcno_accounts(self):
        """Names of the Riot accounts TcNo has saved on this PC (no file contents are read)."""
        if not self.tcno.is_dir():return []
        out=[]
        for d in sorted(self.tcno.iterdir(),key=lambda d:d.name.lower()):
            if d.is_dir() and ((d/'RiotClientPrivateSettings.yaml'/'RiotGamesPrivateSettings.yaml').is_file()
                               or (d/'RiotGamesPrivateSettings.yaml').is_file()):
                out.append(d.name)
        return out

    def _tcno_files(self,name):
        if name not in self.tcno_accounts():raise ValueError('That TcNo account is not on this PC.')
        d=self.tcno/name;files={}
        data=d/'RiotClientPrivateSettings.yaml'        # TcNo keeps a copy of Riot Client's whole Data folder under this name
        if data.is_dir():self._collect(data,'Data',files)
        else:
            if (d/'RiotGamesPrivateSettings.yaml').is_file():files[SIGNIN_FILE]=(d/'RiotGamesPrivateSettings.yaml').read_bytes().hex()
            self._collect(d/'Cookies','Data/Cookies',files);self._collect(d/'Sessions','Data/Sessions',files)
        cfg=d/'RiotClientSettings.yaml'/'RiotClientSettings.yaml'
        if cfg.is_file():files['Config/RiotClientSettings.yaml']=cfg.read_bytes().hex()
        return self._check(files)

    def import_tcno(self,name,ref):
        """Copy TcNo's saved sign-in for `name` into Tune, encrypted, as account `ref`."""
        self._file(ref);return self._store(ref,self._tcno_files(name),'tcno')

    def _load(self,ref):
        d=json.loads(self.unseal(self._file(ref).read_bytes()))
        files=d['files']
        if d.get('v',1)<2:                         # v7.3 copies: paths were relative to Data
            files={('Data/'+k if not k.startswith(('Data/','Config/')) else k):v for k,v in files.items()}
        return files

    def keep_fresh(self,ref):
        """Riot rotates its sign-in now and then; while ref is in game, refresh its copy if it changed."""
        path=self._file(ref)
        if not path.exists():return False
        try:old=self._load(ref)
        except Exception:old=None
        try:now=self._snapshot()
        except RuntimeError:return False
        if now==old:return False
        self.remember(ref);return True

    PREVIOUS='previous'

    def _keep_previous(self,files):
        self.dir.mkdir(parents=True,exist_ok=True);path=self.dir/f'{self.PREVIOUS}.last';tmp=path.with_suffix('.tmp')
        tmp.write_bytes(self.seal(json.dumps({'format':FORMAT,'v':2,'source':'before-switch','files':files}).encode()));tmp.replace(path)

    def has_previous(self):return (self.dir/f'{self.PREVIOUS}.last').exists()

    def undo_switch(self,launch):
        """Put back the sign-in Riot Client had before the last switch."""
        path=self.dir/f'{self.PREVIOUS}.last'
        if not path.exists():raise ValueError('There is no earlier sign-in to go back to.')
        files=json.loads(self.unseal(path.read_bytes()))['files']
        return self._restore(files,launch,keep=False)

    def forget(self,ref=None):
        targets=[self._file(ref)] if ref else (list(self.dir.glob('*.bin'))+list(self.dir.glob('*.last')) if self.dir.exists() else [])
        n=0
        for p in targets:
            try:p.unlink();n+=p.suffix=='.bin'      # count accounts, not the switch-back copy
            except FileNotFoundError:pass
        return {'forgotten':n}

    def switch(self,ref,launch):
        """Close Riot Client, restore ref's sign-in, then call launch() to start Riot Client again."""
        path=self._file(ref)
        if not path.exists():raise ValueError('This account has no saved sign-in yet.')
        return self._restore(self._load(ref),launch,ref=ref)

    def _restore(self,files,launch,ref=None,keep=True):
        if any(n.startswith('valorant') for n in self.procs()):
            raise RuntimeError('Quit VALORANT first - Tune never closes the game for you.')
        if any(n in RIOT_PROCS for n in self.procs()):
            self.kill()
            for _ in range(40):
                if not any(n in RIOT_PROCS for n in self.procs()):break
                self.sleep(0.25)
            else:raise RuntimeError('Riot Client did not close. Close it from the system tray, then try again.')
            self.sleep(0.5)            # let it finish releasing its files
        # Keep whatever Riot Client is signed in to right now, so switching can always be undone
        # (otherwise an account that was never saved would need its password typed again).
        if keep:
            try:self._keep_previous(self._snapshot())
            except RuntimeError:pass
        # Like TcNo: clear Riot Client's Data folder, then put this account's copy in place, so
        # nothing from the previous account is left behind.
        data=self.root/'Data'
        if data.is_dir():
            for f in sorted(data.rglob('*'),reverse=True):
                try:f.unlink() if f.is_file() else f.rmdir()
                except OSError:pass
        for rel,hexdata in files.items():
            dest=self.root/rel;dest.parent.mkdir(parents=True,exist_ok=True)
            tmp=dest.with_name(dest.name+'.tune-tmp');tmp.write_bytes(bytes.fromhex(hexdata));tmp.replace(dest)
        launch()
        return {'switched':ref}
