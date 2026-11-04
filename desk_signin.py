"""One-click account switching, the way TcNo Account Switcher does it - opt-in, per account.

Riot Client keeps "Stay signed in" in its own files (Data\\RiotGamesPrivateSettings.yaml and its
cookie store). Remembering an account copies those files while VALORANT is open on that account,
so the copy is known to belong to it. Switching closes Riot Client (never VALORANT), puts the
chosen account's copy back and starts Riot Client again, which signs straight in.

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

FILES=('RiotGamesPrivateSettings.yaml','Cookies/Cookies')     # relative to Riot Client\Data
STALE=('Cookies/Cookies-journal',)                               # removed on switch so the cookie store stays consistent
RIOT_PROCS=('riotclientservices.exe','riot client.exe','riotclientux.exe','riotclientuxrender.exe','riotclientcrashhandler.exe')
FORMAT='tune-signin'


def riot_data_dir():
    return Path(os.environ.get('LOCALAPPDATA',''))/'Riot Games'/'Riot Client'/'Data'


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
    def __init__(self,store,data_dir=None,procs=process_names,kill=kill_riot_client,
                 seal=protect,unseal=unprotect,sleep=time.sleep):
        self.dir=Path(store)/'signins';self.data=Path(data_dir) if data_dir else riot_data_dir()
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

    def _snapshot(self):
        files={}
        for rel in FILES:
            p=self.data/rel
            if p.is_file():files[rel]=p.read_bytes().hex()
        if FILES[0] not in files:
            raise RuntimeError('Riot Client has no saved sign-in on this PC. Tick "Stay signed in" when you sign in, then try again.')
        return files

    def remember(self,ref):
        """Save Riot Client's current sign-in as `ref`. The caller guarantees VALORANT is open on ref."""
        path=self._file(ref);payload=json.dumps({'format':FORMAT,'v':1,'files':self._snapshot()}).encode()
        self.dir.mkdir(parents=True,exist_ok=True);tmp=path.with_suffix('.tmp')
        tmp.write_bytes(self.seal(payload));tmp.replace(path)
        return {'ref':ref,'saved_at':self.saved()[ref]}

    def keep_fresh(self,ref):
        """Riot rotates its sign-in now and then; while ref is in game, refresh its copy if it changed."""
        path=self._file(ref)
        if not path.exists():return False
        try:old=json.loads(self.unseal(path.read_bytes()))['files']
        except Exception:old=None
        try:now=self._snapshot()
        except RuntimeError:return False
        if now==old:return False
        self.remember(ref);return True

    def forget(self,ref=None):
        targets=[self._file(ref)] if ref else (list(self.dir.glob('*.bin')) if self.dir.exists() else [])
        n=0
        for p in targets:
            try:p.unlink();n+=1
            except FileNotFoundError:pass
        return {'forgotten':n}

    def switch(self,ref,launch):
        """Close Riot Client, restore ref's sign-in, then call launch() to start Riot Client again."""
        path=self._file(ref)
        if not path.exists():raise ValueError('This account has no saved sign-in yet.')
        files=json.loads(self.unseal(path.read_bytes()))['files']
        if any(n.startswith('valorant') for n in self.procs()):
            raise RuntimeError('Quit VALORANT first - Tune never closes the game for you.')
        if any(n in RIOT_PROCS for n in self.procs()):
            self.kill()
            for _ in range(40):
                if not any(n in RIOT_PROCS for n in self.procs()):break
                self.sleep(0.25)
            else:raise RuntimeError('Riot Client did not close. Close it from the system tray, then try again.')
            self.sleep(0.5)            # let it finish releasing its files
        for rel in STALE:
            try:(self.data/rel).unlink()
            except FileNotFoundError:pass
        for rel,hexdata in files.items():
            dest=self.data/rel;dest.parent.mkdir(parents=True,exist_ok=True)
            tmp=dest.with_name(dest.name+'.tune-tmp');tmp.write_bytes(bytes.fromhex(hexdata));tmp.replace(dest)
        for rel in FILES:              # files this account didn't have must not leak from the previous one
            if rel not in files:
                try:(self.data/rel).unlink()
                except FileNotFoundError:pass
        launch()
        return {'switched':ref}
