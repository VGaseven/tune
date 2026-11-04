"""In-app updater: download the latest Tune.exe from this project's own GitHub releases, check it
against the release's SHA-256 file, then swap it in and restart.

Only https://github.com/VGaseven/tune release downloads are accepted. Nothing about the user's
accounts is sent - it is a plain public download. Windows cannot overwrite a running .exe, but it
can rename it, so the running file becomes Tune.old.exe (removed on the next start) and the new
one takes its name. Any failure leaves the current Tune.exe in place."""
from __future__ import annotations
import hashlib
import json
import os
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

LATEST_API='https://api.github.com/repos/VGaseven/tune/releases/latest'
DOWNLOAD_PREFIX='https://github.com/VGaseven/tune/releases/download/'
EXE='Tune.exe'
SUM='Tune.exe.sha256.txt'
MIN_SIZE=1_000_000            # a real build is ~13 MB; anything tiny is an error page, not an app
HEX=re.compile(r'\b[0-9a-fA-F]{64}\b')


def get_json(url,agent,timeout=10):
    req=urllib.request.Request(url,headers={'User-Agent':agent,'Accept':'application/vnd.github+json'})
    with urllib.request.urlopen(req,timeout=timeout) as r:return json.loads(r.read().decode('utf-8'))


def pick_assets(release):
    """(exe_url, sum_url, size) from a GitHub release, or raise if it isn't a proper Tune release."""
    by={a.get('name'):a for a in release.get('assets') or []}
    exe,s=by.get(EXE),by.get(SUM)
    if not exe or not s:raise RuntimeError('This release has no Tune.exe to install. Download it from the releases page instead.')
    urls=(exe.get('browser_download_url',''),s.get('browser_download_url',''))
    if not all(u.startswith(DOWNLOAD_PREFIX) for u in urls):raise RuntimeError('The update link is not from Tune\'s own GitHub page, so it was not used.')
    return urls[0],urls[1],int(exe.get('size') or 0)


def expected_hash(raw):
    """The SHA-256 inside the release's checksum file (UTF-8 or UTF-16, any case)."""
    for enc in ('utf-8-sig','utf-16'):
        try:m=HEX.search(raw.decode(enc))
        except UnicodeDecodeError:continue
        if m:return m.group(0).lower()
    raise RuntimeError('The release checksum file is unreadable, so the update was not installed.')


def download(url,dest,agent,progress=None,timeout=30):
    """Stream url to dest; returns the SHA-256 of what was written."""
    h=hashlib.sha256();got=0
    req=urllib.request.Request(url,headers={'User-Agent':agent})
    with urllib.request.urlopen(req,timeout=timeout) as r,open(dest,'wb') as f:
        total=int(r.headers.get('Content-Length') or 0)
        while True:
            chunk=r.read(256*1024)
            if not chunk:break
            f.write(chunk);h.update(chunk);got+=len(chunk)
            if progress:progress(got,total)
    return h.hexdigest()


def install(new,exe):
    """Swap the verified file `new` into place of the running `exe`. Rolls back on any failure."""
    new,exe=Path(new),Path(exe);old=exe.with_name('Tune.old.exe')
    try:old.unlink()
    except FileNotFoundError:pass
    exe.replace(old)                       # renaming a running .exe is allowed on Windows
    try:new.replace(exe)
    except OSError:
        old.replace(exe);raise
    return exe


def cleanup(exe):
    """Remove the previous version left behind by an update (silently; it may still be closing)."""
    for p in (Path(exe).with_name('Tune.old.exe'),Path(exe).with_name('Tune.exe.download')):
        try:p.unlink()
        except OSError:pass


def update(agent,exe=None,progress=None,get=get_json,fetch=download,newer=None,read=None):
    """Download, verify and install the latest release over `exe`. Returns the installed path."""
    exe=Path(exe or sys.executable)
    if not getattr(sys,'frozen',False) and exe.name.lower()!=EXE.lower():
        raise RuntimeError('Updating from inside the app works in the downloaded Tune.exe only.')
    release=get(LATEST_API,agent)
    if newer and not newer(release.get('tag_name','')):raise RuntimeError("You're already on the latest version.")
    exe_url,sum_url,size=pick_assets(release)
    if not os.access(exe.parent,os.W_OK):
        raise RuntimeError(f'Tune can\'t write to {exe.parent}. Move Tune.exe to a normal folder (like Downloads or Desktop) and try again.')
    want=expected_hash((read or _read)(sum_url,agent))
    tmp=exe.with_name('Tune.exe.download')
    try:
        got=fetch(exe_url,tmp,agent,progress)
        if tmp.stat().st_size<MIN_SIZE or (size and tmp.stat().st_size!=size):
            raise RuntimeError('The download was incomplete. Nothing was changed - try again.')
        if got.lower()!=want:raise RuntimeError('The download did not match the release checksum, so it was not installed.')
        return install(tmp,exe)
    finally:
        try:tmp.unlink()
        except OSError:pass


def _read(url,agent,timeout=15):
    req=urllib.request.Request(url,headers={'User-Agent':agent})
    with urllib.request.urlopen(req,timeout=timeout) as r:return r.read(4096)


def restart(exe):
    """Start the freshly installed Tune and let the caller exit."""
    flags=getattr(subprocess,'DETACHED_PROCESS',0)|getattr(subprocess,'CREATE_NEW_PROCESS_GROUP',0)
    subprocess.Popen([str(exe)],cwd=str(Path(exe).parent),creationflags=flags,close_fds=True)
