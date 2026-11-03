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

VERSION='6.7'


def resource(*parts):
    """Path to a bundled asset, in dev and inside a PyInstaller onefile build."""
    base=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parent))
    return base.joinpath(*parts)


class Api:
    """The object the web UI calls as window.pywebview.api.* - a thin, defensive wrapper."""
    def __init__(self,backend):
        self.be=backend

    def _call(self,fn,*a):
        try:return {'ok':True,'data':fn(*a)}
        except Exception as e:return {'ok':False,'error':str(e)}

    def accounts(self):return self._call(self.be.accounts)
    def profiles(self):return self._call(self.be.profiles)
    def rank(self,puuid,region=None):return self._call(self.be.rank,puuid,region)
    def save(self,path,label):return self._call(self.be.save,path,label)
    def apply(self,profile_path,target_path):return self._call(self.be.apply,profile_path,target_path)
    def crosshairs(self):return self._call(self.be.crosshair_list)
    def crosshair_add(self,name,code,tags=None,notes=''):return self._call(self.be.crosshair_add,name,code,tags,notes)
    def crosshair_delete(self,cid):return self._call(self.be.crosshair_delete,cid)
    def crosshair_parse(self,code):return self._call(self.be.crosshair_parse,code)
    def settings(self,path):return self._call(self.be.account_settings,path)
    def apply_to_all(self,profile_path):return self._call(self.be.apply_to_all,profile_path)
    def share_code(self,profile_path):return self._call(self.be.share_code,profile_path)
    def share_import(self,text):return self._call(self.be.share_import,text)
    def rank_key_status(self):return self._call(self.be.rank_key_status)
    def set_rank_key(self,key):return self._call(self.be.set_rank_key,key)
    def open_rank_help(self):
        import webbrowser
        def go():webbrowser.open('https://docs.henrikdev.xyz/authentication-and-authorization/general');return {'opened':True}
        return self._call(go)

    def launch_riot(self):
        def go():
            exe=self.be.riot_client()
            if not exe:raise RuntimeError('Riot Client was not found. Open it yourself, sign in, then switch back - Tune will recognise the account.')
            subprocess.Popen([exe,'--launch-product=valorant','--launch-patchline=live'],cwd=str(Path(exe).parent))
            return {'launched':True}
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
    api=Api(tune_backend.Backend())
    webview.create_window(f'Tune {VERSION}',url=str(resource('webui','index.html')),js_api=api,
                          width=1000,height=720,min_size=(820,620),background_color='#07070c')
    webview.start()


if __name__=='__main__':
    main()
