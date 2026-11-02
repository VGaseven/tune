"""Geometry and topmost state for this application's own standard desktop window."""
import ctypes
from ctypes import wintypes as w
import json
import os
from pathlib import Path

DEFAULT={'version':1,'mode':'mini','pinned':False,'mini':[450,390,60,60],'full':[1120,850,60,60]}

def validate_state(data):
    if not isinstance(data,dict) or set(data)!=set(DEFAULT) or type(data['version']) is not int or data['version']!=1 or data['mode'] not in ('mini','full') or type(data['pinned']) is not bool:raise ValueError('Invalid window preferences.')
    for mode in ('mini','full'):
        values=data[mode]
        if not isinstance(values,list) or len(values)!=4 or any(type(v) is not int for v in values):raise ValueError('Invalid window geometry.')
        if not 100<=values[0]<=16000 or not 100<=values[1]<=16000 or any(abs(v)>100000 for v in values[2:]):raise ValueError('Window geometry out of bounds.')
    return data

def load_state(path):
    try:
        with Path(path).open('rb') as f:raw=f.read(4097)
        if len(raw)>4096:raise ValueError('Preferences too large.')
        return validate_state(json.loads(raw.decode('utf-8')))
    except (OSError,ValueError,UnicodeError):return {k:list(v) if isinstance(v,list) else v for k,v in DEFAULT.items()}

def clamp_geometry(geometry,areas,minimum=(400,320)):
    width,height,x,y=geometry
    if not areas:areas=[(0,0,1920,1080)]
    def overlap(r):
        l,t,rr,b=r
        return max(0,min(x+width,rr)-max(x,l))*max(0,min(y+height,b)-max(y,t))
    chosen=max(areas,key=overlap)
    if overlap(chosen)==0:
        chosen=min(areas,key=lambda r:(x-(r[0]+r[2])/2)**2+(y-(r[1]+r[3])/2)**2)
    l,t,r,b=chosen
    available_w=max(100,r-l-16);available_h=max(100,b-t-56)
    width=min(max(width,minimum[0]),available_w);height=min(max(height,minimum[1]),available_h)
    x=max(l+8,min(x,r-width-8));y=max(t+32,min(y,b-height-24))
    return [int(width),int(height),int(x),int(y)]

def work_areas(root):
    if os.name=='nt':
        try:
            class MonitorInfo(ctypes.Structure):
                _fields_=[('size',w.DWORD),('monitor',w.RECT),('work',w.RECT),('flags',w.DWORD)]
            user=ctypes.WinDLL('user32',use_last_error=True);areas=[]
            callback=ctypes.WINFUNCTYPE(w.BOOL,w.HANDLE,w.HDC,ctypes.POINTER(w.RECT),w.LPARAM)
            user.GetMonitorInfoW.argtypes=[w.HANDLE,ctypes.POINTER(MonitorInfo)]
            user.EnumDisplayMonitors.argtypes=[w.HDC,ctypes.POINTER(w.RECT),callback,w.LPARAM]
            def collect(handle,dc,rect,param):
                info=MonitorInfo();info.size=ctypes.sizeof(info)
                if user.GetMonitorInfoW(handle,ctypes.byref(info)):
                    r=info.work;areas.append((r.left,r.top,r.right,r.bottom))
                return True
            if user.EnumDisplayMonitors(None,None,callback(collect),0) and areas:return areas
        except (OSError,AttributeError):pass
    return [(0,0,root.winfo_screenwidth(),root.winfo_screenheight())]

class DesktopMode:
    def __init__(self,app,full,mini,save_json,areas=None):
        self.app=app;self.root=app.root;self.full=full;self.mini=mini;self.writer=save_json
        self.path=app.store.base/'window-state.json';self.state=load_state(self.path)
        self.areas=areas or (lambda:work_areas(self.root));self.mode=None;self.pending=None;self.closed=False;self.switching=False
        self.root.resizable(True,True)
        self.root.protocol('WM_DELETE_WINDOW',self.close)
        self.root.bind('<Configure>',self.on_configure,add='+')
        self.root.bind('<Control-m>',lambda e:self.shortcut(self.toggle),add='+')
        self.root.bind('<Control-p>',lambda e:self.shortcut(self.toggle_pin),add='+')
        self.root.bind('<Control-Return>',lambda e:self.shortcut(lambda:self.app.run(self.app.capture)),add='+')
        self.root.bind('<Control-minus>',lambda e:self.shortcut(self.minimize),add='+')
        self.set_mode(self.state['mode'],remember=False)
        self.apply_pin(self.state['pinned'],persist=False)

    def shortcut(self,action):action();return 'break'
    def dimensions(self,mode):
        if mode=='full':return (720,520)
        self.mini.update_idletasks()
        return (max(410,self.mini.winfo_reqwidth()+28),max(330,self.mini.winfo_reqheight()+28))
    def remember(self):
        if self.mode and self.root.state()=='normal' and self.root.winfo_width()>100:
            self.state[self.mode]=clamp_geometry([self.root.winfo_width(),self.root.winfo_height(),self.root.winfo_x(),self.root.winfo_y()],self.areas(),self.dimensions(self.mode))
    def geometry(self,values):
        width,height,x,y=values
        # + followed by a signed integer is an absolute virtual-desktop coordinate in Tk.
        self.root.geometry(f'{width}x{height}+{x}+{y}')
    def set_mode(self,mode,remember=True):
        if mode not in ('mini','full'):raise ValueError('Unknown window mode.')
        if remember:self.remember()
        self.switching=True
        self.full.pack_forget();self.mini.pack_forget();self.root.minsize(1,1)
        self.mode=mode;self.state['mode']=mode
        if mode=='mini':self.mini.pack(fill='both',expand=True,padx=14,pady=14)
        else:self.full.pack(fill='both',expand=True)
        minimum=self.dimensions(mode);values=clamp_geometry(self.state[mode],self.areas(),minimum)
        self.root.minsize(min(minimum[0],values[0]),min(minimum[1],values[1]))
        self.geometry(values);self.state[mode]=values
        self.root.title('Preset Desk 3.1 — '+('Mini' if mode=='mini' else 'Full profiles'))
        self.root.update_idletasks();self.switching=False
        self.app.sync_mini()
        if remember:self.persist()
    def toggle(self):self.set_mode('full' if self.mode=='mini' else 'mini')
    def apply_pin(self,pinned,persist=True):
        self.root.attributes('-topmost',bool(pinned))
        self.state['pinned']=bool(pinned)
        self.app.pin_text.set('◆ Unpin' if pinned else '◇ Pin')
        if persist:self.persist()
    def toggle_pin(self):self.apply_pin(not self.state['pinned'])
    def minimize(self):self.remember();self.persist();self.root.iconify()
    def on_configure(self,event):
        if event.widget is not self.root or self.switching or self.closed:return
        if self.pending:self.root.after_cancel(self.pending)
        self.pending=self.root.after(500,self.after_resize)
    def after_resize(self):
        self.pending=None
        if self.closed:return
        self.remember();self.persist()
    def persist(self):
        try:
            validate_state(self.state);self.path.parent.mkdir(parents=True,exist_ok=True);self.writer(self.path,self.state)
        except (OSError,ValueError):
            self.app.status.set('Window preferences could not be saved. Profiles are unaffected; this window still works.')
    def drag_start(self,event):self.drag=(event.x_root,event.y_root,self.root.winfo_x(),self.root.winfo_y())
    def drag_move(self,event):
        if not hasattr(self,'drag'):return
        sx,sy,x,y=self.drag
        values=clamp_geometry([self.root.winfo_width(),self.root.winfo_height(),x+event.x_root-sx,y+event.y_root-sy],self.areas(),self.dimensions(self.mode))
        self.geometry(values)
    def close(self):
        if self.closed:return
        self.remember();self.persist();self.closed=True
        if self.pending:self.root.after_cancel(self.pending);self.pending=None
        self.root.destroy()
