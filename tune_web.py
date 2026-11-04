"""Tune desktop window (pywebview host).

Loads the glass web UI (webui/) in a native window and exposes a tiny JSON bridge to the GUI-free
tune_backend. Every call returns a {'ok':bool, ...} envelope so the front-end can show friendly
errors (e.g. 'game is open') instead of a raw rejection. pywebview itself is imported lazily inside
main(), so this module stays importable (and testable) without it installed."""
from __future__ import annotations
import subprocess
import sys
from pathlib import Path
import tune_backend
import desk_update

VERSION='7.5'
REPO='https://github.com/VGaseven/tune'
LATEST_API='https://api.github.com/repos/VGaseven/tune/releases/latest'


def newer(latest,current):
    """True when a release tag like 'v7.2' is newer than the running version '7.0'."""
    def parts(v):
        try:return tuple(int(x) for x in str(v).lstrip('vV').split('.'))
        except ValueError:return ()
    a,b=parts(latest),parts(current)
    return bool(a) and bool(b) and a>b


def resource(*parts):
    """Path to a bundled asset, in dev and inside a PyInstaller onefile build."""
    base=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parent))
    return base.joinpath(*parts)


class Api:
    """The object the web UI calls as window.pywebview.api.* - a thin, defensive wrapper."""
    def __init__(self,backend):
        self.be=backend
        self._upd={'stage':'idle'}

    def _call(self,fn,*a):
        try:return {'ok':True,'data':fn(*a)}
        except Exception as e:return {'ok':False,'error':str(e)}

    def accounts(self):return self._call(self.be.accounts)
    def profiles(self):return self._call(self.be.profiles)
    def rank(self,puuid,region=None,force=False):return self._call(self.be.rank,puuid,region,force)
    def save(self,path,label):return self._call(self.be.save,path,label)
    def apply(self,profile_path,target_path):return self._call(self.be.apply,profile_path,target_path)
    def crosshairs(self):return self._call(self.be.crosshair_list)
    def crosshair_add(self,name,code,tags=None,notes=''):return self._call(self.be.crosshair_add,name,code,tags,notes)
    def crosshair_delete(self,cid):return self._call(self.be.crosshair_delete,cid)
    def crosshair_update(self,cid,name=None):return self._call(self.be.crosshair_update,cid,name)
    def crosshair_parse(self,code):return self._call(self.be.crosshair_parse,code)
    def crosshair_gallery(self):return self._call(self.be.crosshair_gallery)
    def crosshair_preview(self,code):return self._call(self.be.crosshair_preview,code)
    def open_site(self,url):
        import webbrowser,desk_crosshair
        def go():
            if url not in {u for _,u in desk_crosshair.SITES}:raise ValueError('Unknown site.')
            return {'opened':webbrowser.open(url)}
        return self._call(go)
    def settings(self,path):return self._call(self.be.account_settings,path)
    def apply_to_all(self,profile_path):return self._call(self.be.apply_to_all,profile_path)
    def share_code(self,profile_path):return self._call(self.be.share_code,profile_path)
    def share_import(self,text):return self._call(self.be.share_import,text)
    def master(self):return self._call(self.be.master)
    def set_master(self,ref):return self._call(self.be.set_master,ref)
    def account_view(self,ref):return self._call(self.be.account_view,ref)
    def status(self):return self._call(self.be.status)
    def apply_master_all(self):return self._call(self.be.apply_master_all)
    def sync_report(self,ref):return self._call(self.be.sync_report,ref)
    def apply_master(self,ref):return self._call(self.be.apply_master,ref)
    def apply_from(self,source,ref):return self._call(self.be.apply_from,source,ref)
    def apply_all_from(self,source):return self._call(self.be.apply_all_from,source)
    def restore_backup(self,ref):return self._call(self.be.restore_backup,ref)
    def rank_key_status(self):return self._call(self.be.rank_key_status)
    def set_rank_key(self,key):return self._call(self.be.set_rank_key,key)
    def open_rank_help(self):
        import webbrowser
        def go():webbrowser.open('https://api.henrikdev.xyz/dashboard/');return {'opened':True}
        return self._call(go)

    def about(self):
        return self._call(lambda:{'version':VERSION,'repo':REPO,'backups':str(self.be.store.base/'backups')})

    def check_update(self,fetch=None):
        """Ask GitHub (public, no account data sent) whether a newer Tune release exists."""
        def go():
            import json,urllib.request
            def get():
                req=urllib.request.Request(LATEST_API,headers={'User-Agent':f'Tune/{VERSION}','Accept':'application/vnd.github+json'})
                with urllib.request.urlopen(req,timeout=8) as r:return json.loads(r.read().decode('utf-8'))
            d=(fetch or get)();tag=d.get('tag_name','')
            return {'current':VERSION,'latest':tag.lstrip('vV') or None,'newer':newer(tag,VERSION),'url':d.get('html_url') or REPO+'/releases'}
        return self._call(go)

    def update_now(self):
        """Start downloading + installing the latest release in the background; poll update_status."""
        import threading
        if self._upd.get('stage') in ('downloading','installing','restarting'):return {'ok':True,'data':self._upd}
        self._upd={'stage':'downloading','got':0,'total':0}
        def prog(got,total):self._upd.update(got=got,total=total)
        def run():
            try:
                path=desk_update.update(f'Tune/{VERSION}',progress=prog,newer=lambda tag:newer(tag,VERSION))
                self._upd={'stage':'restarting'}
                desk_update.restart(path)
                # The new Tune is starting: close this window properly (so its files can be cleaned
                # up), with a hard exit as a fallback if the window doesn't go away.
                import os
                def close():
                    try:
                        import webview
                        for w in list(webview.windows):w.destroy()
                    except Exception:pass
                threading.Timer(1.0,close).start();threading.Timer(6.0,os._exit,(0,)).start()
            except Exception as e:
                self._upd={'stage':'error','error':str(e)}
        threading.Thread(target=run,daemon=True).start()
        return {'ok':True,'data':self._upd}

    def update_status(self):return {'ok':True,'data':dict(self._upd)}
    def can_self_update(self):return {'ok':True,'data':bool(getattr(sys,'frozen',False))}

    def open_releases(self):
        import webbrowser
        return self._call(lambda:{'opened':webbrowser.open(REPO+'/releases/latest')})

    def open_backups(self):
        def go():
            import os
            p=self.be.store.base/'backups';p.mkdir(parents=True,exist_ok=True);os.startfile(str(p));return {'opened':True}
        return self._call(go)

    def _launch(self):
        exe=self.be.riot_client()
        if not exe:raise RuntimeError('Riot Client was not found. Open it yourself, sign in, then switch back - Tune will recognise the account.')
        subprocess.Popen([exe,'--launch-product=valorant','--launch-patchline=live'],cwd=str(Path(exe).parent))

    def launch_riot(self):
        def go():self._launch();return {'launched':True}
        return self._call(go)

    def signin_saved(self):return self._call(self.be.signin_saved)
    def remember_signin(self,ref):return self._call(self.be.remember_signin,ref)
    def keep_signin_fresh(self):return self._call(self.be.keep_signin_fresh)
    def forget_signins(self,ref=None):return self._call(self.be.forget_signins,ref)
    def switch_to(self,ref):
        def go():
            if not self.be.riot_client():raise RuntimeError('Riot Client was not found on this PC.')
            return self.be.switch_to(ref,self._launch)
        return self._call(go)


_FIX=(b'; synthetic only\r\n[/Script/ShooterGame.ShooterGameUserSettings]\r\n'
      b'bUseVSync=False\r\nFrameRateLimit=0.000000\r\nResolutionSizeX=1920\r\nResolutionSizeY=1080\r\n'
      b'[ScalabilityGroups]\r\nsg.TextureQuality=3\r\nsg.ShadowQuality=2\r\n')

def _selftest():
    """Headless packaged-EXE check: exercise the backend end-to-end on throwaway synthetic files -
    no window, no network - and write the PASS/FAIL report CI looks for. Never touches real data."""
    import json,os,tempfile
    report=os.environ.get('NOTEBOOK_TEST_REPORT')
    try:
        with tempfile.TemporaryDirectory() as d:
            base=Path(d);config=base/'Config'
            a='0aec6e15-90a1-4b2c-8d3e-111111111111';b='21c9f7c6-a7b2-4c3d-9e4f-222222222222'
            for uid,tex in ((a,3),(b,0)):
                p=config/f'{uid}-eu'/'Windows'/'GameUserSettings.ini';p.parent.mkdir(parents=True)
                p.write_bytes(_FIX.replace(b'sg.TextureQuality=3',b'sg.TextureQuality='+str(tex).encode()))
            (base/'Logs').mkdir()
            (base/'Logs'/'ShooterGame.log').write_text(f'LogShooterGameUserSettings: Logged in user changed: {a}\n',encoding='utf-8')
            import capture_model as m
            be=tune_backend.Backend(config,store_base=base/'app',guard=lambda:None)
            assert len(be.accounts())==2,'account scan'
            aref=m.source_id(config/f'{a}-eu'/'Windows'/'GameUserSettings.ini')
            bref=m.source_id(config/f'{b}-eu'/'Windows'/'GameUserSettings.ini')
            saved=be.save(aref,'SELFTEST')
            out=be.apply(Path(saved['path']).name,bref)
            assert out['applied']==1,'apply video key'
            assert Api(be).accounts()['ok'],'bridge envelope'
        result,detail='PASS','accounts + save + apply + bridge ok'
    except Exception as e:
        result,detail='FAIL',repr(e)
    payload={'result':result,'detail':detail,'version':VERSION}
    if report:
        try:Path(report).write_text(json.dumps(payload),encoding='utf-8')
        except OSError:pass
    print(json.dumps(payload));sys.exit(0 if result=='PASS' else 1)


def main():
    if '--self-test' in sys.argv or '--selftest' in sys.argv:return _selftest()
    import webview   # lazy: only needed to actually open the window
    if getattr(sys,'frozen',False):desk_update.cleanup(sys.executable)   # remove the old version after an update
    import desk_window,time
    api=Api(tune_backend.Backend());title=f'Tune {VERSION}'
    win=webview.create_window(title,url=str(resource('webui','index.html')),js_api=api,
                              width=1140,height=800,min_size=(380,500),resizable=True,background_color='#07070c')
    def dark_titlebar():
        for _ in range(15):                  # the native window can take a moment to get its title
            if desk_window.darken(title):return
            time.sleep(0.2)
    win.events.shown+=dark_titlebar
    webview.start()


if __name__=='__main__':
    main()
