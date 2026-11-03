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

    def launch_riot(self):
        def go():
            exe=self.be.riot_client()
            if not exe:raise RuntimeError('Riot Client was not found. Open it yourself, sign in, then switch back - Tune will recognise the account.')
            subprocess.Popen([exe,'--launch-product=valorant','--launch-patchline=live'],cwd=str(Path(exe).parent))
            return {'launched':True}
        return self._call(go)


def main():
    import webview   # lazy: only needed to actually open the window
    api=Api(tune_backend.Backend())
    webview.create_window('Tune',url=str(resource('webui','index.html')),js_api=api,
                          width=1000,height=720,min_size=(820,620),background_color='#07070c')
    webview.start()


if __name__=='__main__':
    main()
