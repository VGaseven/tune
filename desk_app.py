"""Tune 4.0 (formerly Preset Desk): save VALORANT video presets per account and apply them to another account.
Local files only: no credentials, game memory, client APIs, injection, overlays or automation.
Every game-file read/write goes through capture_model (allowlist, process guard, backups,
atomic writes, change detection)."""
import ctypes
import json
import os
from pathlib import Path
import sys
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk,filedialog
import capture_model as model
import desk_profiles as dp
from desktop_mode import clamp_geometry,work_areas
from desk_theme import VERSION,NAME,PALETTES,FONT,SEMIBOLD,GRADIENT,icon_font,reduced_motion,mix,title_bar
from desk_icon import photo
from desk_skin import Images,UI,RoundButton,PillButton,Toggle,Hotspot,Button,draw_matrix,matrix_width,draw_sphere,dot_field,fit,LIME,TEXT,SEMI

def _launch_riot(exe):
    """Starts Riot Client (user-initiated). Opens VALORANT's login so the user can switch account."""
    import subprocess
    subprocess.Popen([str(exe),'--launch-product=valorant','--launch-patchline=live'],cwd=str(exe.parent))

def load_theme(path):
    try:
        raw=Path(path).read_bytes()
        if len(raw)>1024:raise ValueError()
        data=json.loads(raw)
        if not isinstance(data,dict) or set(data)!={'version','theme'} or type(data['version']) is not int or data['version']!=1 or data['theme'] not in PALETTES:raise ValueError()
        return data['theme']
    except (OSError,ValueError,TypeError,UnicodeError):return 'dark'

class Look:
    """Palette + DPI-aware pixel scaling shared by every widget."""
    def __init__(self,root,name):self.root=root;self.name=name;self.icons=icon_font(root)
    @property
    def c(self):return PALETTES[self.name]
    def scale(self):return float(self.root.tk.call('tk','scaling'))/(96/72)
    def px(self,n):return max(1,round(n*self.scale()))

class App:
    def __init__(self,root,store=None,config_root=None,guard=None,motion=None,launcher=None):
        self.root=root;self.store=store or model.Store()
        self.config_root=Path(config_root) if config_root is not None else model.config_directory();self.guard=guard
        self.launcher=launcher or _launch_riot
        self.busy=False;self.items=[];self.names=[];self.selected=None;self.last_saved=None;self.cards=[];self.closed=False;self.pending=None
        self.prefs_path=self.store.base/'desk-window.json';self.prefs=dp.load_prefs(self.prefs_path);self.view='full'
        self.look=Look(root,load_theme(self.store.base/'theme.json'))
        self.motion=(not reduced_motion()) if motion is None else motion
        self.status=tk.StringVar(root,value='');self.pin_var=tk.BooleanVar(root,value=self.prefs['pin_full']);self.theme_var=tk.StringVar(root,value=self.look.name)
        self.content=None;self.mini=None
        root.title(NAME)
        try:self.icon=photo(root);root.iconphoto(True,self.icon)
        except tk.TclError:self.icon=None
        self.screen=self.prefs['tab'];self.load_items();self.acct=self.account_view();self.build();self.mini=MiniView(self)
        self.minimum=(self.look.px(400),self.look.px(680))
        root.minsize(*self.minimum)
        self.place(root,self.prefs['full'],self.minimum);root.attributes('-topmost',self.prefs['pin_full']);self.dark_bar(root)
        root.protocol('WM_DELETE_WINDOW',self.close);root.bind('<Configure>',self.moved,add='+')
        for seq,fn in [('<Control-s>',self.save_settings),('<Control-i>',self.import_profile),('<Control-m>',self.toggle_view),('<Control-l>',self.launch_riot)]:
            root.bind(seq,lambda e,fn=fn:(self.run(fn),'break')[1])
        root.bind('<Control-Key-1>',lambda e:self.show_screen('save'));root.bind('<Control-Key-2>',lambda e:self.show_screen('accounts'))
        if self.prefs['view']=='mini':self.show_mini(initial=True)

    # ---------- layout: one canvas per view, styled after the reference ----------
    def build(self):
        c=self.look.c;self.root.configure(bg=c['bg'])
        if self.content is not None:self.cancel_redraw();self.content.destroy()
        if not hasattr(self,'images'):self.images=Images(self.root)
        self.content=tk.Canvas(self.root,bg=c['bg'],highlightthickness=0,bd=0)
        if self.view=='full':self.content.pack(fill='both',expand=True)
        self.ui=UI(self.content,self.look);self.drawn=None
        cv=self.content;cv.bind('<Configure>',self.resized)
        cv.bind('<Left>',lambda e:self.step_profile(-1));cv.bind('<Right>',lambda e:self.step_profile(1))
        cv.bind('<MouseWheel>',lambda e:self.step_profile(-1 if e.delta>0 else 1) if self.screen=='accounts' else None)
        for seq,fn in [('<F2>',self.rename_profile),('<Delete>',self.delete_profile)]:
            cv.bind(seq,lambda e,fn=fn:self.run(lambda:fn(self.selected)) if self.screen=='accounts' and self.selected else None)
        cv.bind('<Shift-F10>',lambda e:self.popup(self.menu_anchor()));cv.bind('<App>',lambda e:self.popup(self.menu_anchor()))
        self.root.bind('<Button-3>',lambda e:self.popup(None,e))
        self.redraw()
    def dark_bar(self,win):title_bar(win,self.look.name=='dark')
    def size(self,cv,default):
        cv.update_idletasks();w,h=cv.winfo_width(),cv.winfo_height()
        # an unmapped window reports placeholder sizes; lay out for the remembered window size
        return (w,h) if cv.winfo_ismapped() and w>50 and h>50 else tuple(self.look.px(n) for n in default)
    def resized(self,e):
        if self.drawn!=(e.width,e.height) and e.width>50:
            self.cancel_redraw();self.redraw_job=self.root.after(40,self.redraw)
    def cancel_redraw(self):
        if getattr(self,'redraw_job',None):self.root.after_cancel(self.redraw_job);self.redraw_job=None
    def redraw(self):
        self.redraw_job=None
        if self.content is None or not self.content.winfo_exists():return
        cv=self.content;c=self.look.c;px=self.look.px;cv.delete('all');self.ui.reset()
        W,H=self.size(cv,tuple(self.prefs['full'][:2]));self.drawn=(W,H)
        dot_field(cv,W,H,px(14),c['dots'])
        if self.screen=='save':self.draw_header(W,'people','Accounts',lambda:self.show_screen('accounts'),NAME);self.draw_save(W,H)
        else:self.draw_header(W,'back','Back to Save',lambda:self.show_screen('save'),'Accounts');self.draw_accounts(W,H)
    def draw_header(self,W,icon,name,command,title):
        cv=self.content;c=self.look.c;px=self.look.px;d=px(48);y=px(20)+d/2
        RoundButton(self.ui,name,px(20)+d/2,y,d,icon,command,c['chip'],c['text'],c['chiphover'])
        self.more=RoundButton(self.ui,'Menu',W-px(20)-d/2,y,d,'menu',lambda:self.popup(self.menu_anchor()),c['chip'],c['text'],c['chiphover'])
        cv.create_text(W/2,y,text=title,font=(SEMI,19),fill=c['text'])
        self.header_bottom=y+d/2
    def menu_anchor(self):
        b=self.ui.find('Menu');cv=self.content
        if b is None:return None
        x0,y0,x1,y1=cv.bbox(b.bg);return (cv.winfo_rootx()+int(x0),cv.winfo_rooty()+int(y1)+self.look.px(6))
    def show_screen(self,key):
        if key not in ('save','accounts'):raise ValueError('Unknown screen.')
        self.screen=key;self.prefs['tab']=key;self.persist();self.redraw()
        self.content.focus_set()

    def account_view(self):
        """Display data for the Save screen: which account, your name for it, and its current
        video values (read-only). Computed on refresh, not on every redraw."""
        info={'path':None,'label':None,'signed':False,'values':{}}
        try:
            cur=self.current_account()
            if cur:info.update(path=cur[0],label=cur[1],signed=True)
            else:
                rem=dp.remembered(self.store)
                if rem:
                    match=[p for p in dp.account_paths(model.discover(self.config_root,lambda:None),self.config_root) if model.source_id(p)==rem[0]]
                    if match:info.update(path=match[0],label=rem[1])
            if info['path']:info['values']=model.parse(model.read_bytes(info['path']))[2]
        except (OSError,ValueError,UnicodeError):pass
        return info
    def draw_save(self,W,H):
        cv=self.content;c=self.look.c;px=self.look.px;a=self.acct;v=a['values']
        sheet_h=px(262);sx,sw=px(14),W-px(28);sy=H-px(14)-sheet_h
        top=self.header_bottom+px(18);room=sy-top-px(12)
        R=max(px(46),min(W*0.30,room*0.27));cy=top+R
        draw_sphere(cv,W/2,cy,R,px(14),px(1.5),c['bg'])
        fps=dp.shown('FrameRateLimit',v['FrameRateLimit']) if 'FrameRateLimit' in v else '--'
        ny=cy+R+px(50);dot=px(2.3) if len(fps)<4 else px(1.9)
        draw_matrix(cv,fps,W/2,ny,dot,'#FFFFFF')
        cv.create_text(W/2,ny+px(40),text='FPS limit' if fps not in ('--','0') else ('FPS limit (unlimited)' if fps=='0' else 'No account read yet'),font=(TEXT,10),fill=c['muted'])
        msg=self.save_message();mt=cv.create_text(W/2,sy-px(14),text=msg,font=(TEXT,9),fill=c['muted'],width=W-px(56),justify='center',anchor='s')
        msg_top=cv.bbox(mt)[1]
        for k,row in enumerate((5,3,2)):          # tapering dot trail under the label (reference)
            yy=ny+px(66)+k*px(12)
            if yy>msg_top-px(10):break
            for i in range(row):xx=W/2+(i-(row-1)/2)*px(12);cv.create_oval(xx-px(1.2),yy-px(1.2),xx+px(1.2),yy+px(1.2),fill=mix(c['bg'],'#FFFFFF',0.55-k*0.15),outline='')
        cv.create_image(sx,sy,image=self.images.card(sw,sheet_h,px(52),'navy',c['bg']),anchor='nw')
        # top row: Textures | account | VSync
        tex=v.get('sg.TextureQuality','--');vs={'True':'On','False':'Off'}.get(v.get('bUseVSync'),'--');ty=sy+px(44)
        cv.create_text(sx+px(34),ty,text=tex,font=(TEXT,12),fill='#FFFFFF',anchor='w');cv.create_text(sx+px(34),ty+px(20),text='Textures',font=(TEXT,8),fill='#7C83C8',anchor='w')
        cv.create_text(sx+sw-px(34),ty,text=vs,font=(TEXT,12),fill='#FFFFFF',anchor='e');cv.create_text(sx+sw-px(34),ty+px(20),text='VSync',font=(TEXT,8),fill='#7C83C8',anchor='e')
        for i,(dx,dy) in enumerate([(0,0),(-1,1),(1,1),(-2,2),(0,2),(2,2)]):   # small dot pyramid icon
            xx=sx+sw/2+dx*px(4);yy=sy+px(26)+dy*px(4);cv.create_oval(xx-px(1.3),yy-px(1.3),xx+px(1.3),yy+px(1.3),fill=LIME if a['signed'] else '#C9CCF5',outline='')
        name=a['label'] or ('New account' if a['path'] else 'Choose account')
        cv.create_text(sx+sw/2,sy+px(52),text=fit(cv,name,(TEXT,12),sw-px(170)),font=(TEXT,12),fill='#FFFFFF')
        cv.create_text(sx+sw/2,sy+px(72),text='signed in' if a['signed'] else ('your saved choice' if a['path'] else ''),font=(TEXT,8),fill='#7C83C8')
        # quality track: lime length = average quality level of the 10 groups (0-3)
        qs=[int(v[k]) for k in model.QUALITY if k in v];frac=(sum(qs)/len(qs)/3) if qs else 0
        ty=sy+px(128);x0=sx+px(70);x1=sx+sw-px(40)
        for xx in range(int(sx+px(28)),int(sx+sw-px(24)),px(7)):cv.create_oval(xx-1,ty-1,xx+1,ty+1,fill='#2B3170',outline='')
        cv.create_line(x0,ty,x0+(x1-x0)*frac,ty,fill=LIME,width=px(2))
        cv.create_oval(x0+(x1-x0)*frac-px(3.5),ty-px(3.5),x0+(x1-x0)*frac+px(3.5),ty+px(3.5),fill=LIME,outline='')
        r=px(17);cv.create_oval(x0-r-px(5),ty-r-px(5),x0+r+px(5),ty+r+px(5),outline='#5A62B8',dash=(1,3))
        cv.create_oval(x0-r,ty-r,x0+r,ty+r,fill='#E9E9F2',outline='');cv.create_arc(x0-r,ty-r,x0+r,ty+r,start=90,extent=180,fill='#20244F',outline='')
        rr=px(24);cv.create_oval(sx+sw-px(118)-rr,ty-rr,sx+sw-px(118)+rr,ty+rr,outline='#2B3170',dash=(1,4))
        cv.create_text(x1,ty-px(16),text='Overall quality',font=(TEXT,8),fill='#7C83C8',anchor='e')
        # bottom row: change account | Save settings (white end circle)
        bh=px(54);by=sy+sheet_h-px(26)-bh;rd=bh
        RoundButton(self.ui,'Switch account (open Riot Client)',sx+px(26)+rd/2,by+bh/2,rd,'refresh',lambda:self.run(self.launch_riot),'#1B2059','#FFFFFF','#262C70')
        text='Save settings' if a['label'] else ('Name & save' if a['path'] else 'Set up & save')
        self.save_btn=PillButton(self.ui,'Save',sx+px(26)+rd+px(12),by,sw-px(52)-rd-px(12),bh,text,lambda:self.run(self.save_settings),'#1E2357','#FFFFFF','#283071','check')
        if self.busy:self.save_btn.set_state('disabled')
    def save_message(self):
        s=self.last_saved;msg=self.status.get()
        if s:
            what='all 12 video settings' if s['n']==12 else f'{s["n"]} video settings ('+', '.join(s['names'])+')'
            line=f'✓ Saved “{s["label"]}” at {s["time"].split(", ")[-1]}  ·  {what}'
            if s['ref']:line+='\nSensitivity kept for reference only'
            if s.get('open'):line+='\nVALORANT was open - if a new change is missing, save again after closing it'
            return line if not msg or msg.startswith(('Saved','Updated')) else msg
        return msg or 'Save works while VALORANT is open. Apply needs it closed.'

    def draw_accounts(self,W,H):
        cv=self.content;c=self.look.c;px=self.look.px;items=self.items
        top=self.header_bottom+px(22);cw=min(W*0.66,px(300));ch=min(cw*1.16,(H-top)*0.46);r=px(56);cx=W/2;gap=px(16)
        i=[p for p,_ in items].index(self.selected) if self.selected in [p for p,_ in items] else (0 if items else None)
        if i is not None and self.selected is None:self.selected=items[0][0]
        for d,look in ((-1,'blue'),(1,'gold')):          # neighbours peek in from the sides
            if i is not None and 0<=i+d<len(items):
                x=cx-cw/2+d*(cw+gap);cv.create_image(x,top+px(26),image=self.images.card(cw,ch-px(52),r,look,c['bg']),anchor='nw')
                Hotspot(self.ui,'Show '+self.names[i+d],max(0,x),top+px(26),min(W,x+cw)-max(0,x),ch-px(52),r,lambda j=i+d:self.pick(j),'#FFFFFF')
        x0=cx-cw/2;cv.create_image(x0,top,image=self.images.card(cw,ch,r,'magenta' if items else 'slate',c['bg']),anchor='nw')
        if i is None:
            draw_matrix(cv,'0',cx,top+ch*0.40,px(2.3),'#FFFFFF')
            cv.create_text(cx,top+px(30),text='No profiles yet',font=(TEXT,11),fill='#FFFFFF')
            cv.create_text(cx,top+ch*0.66,text='Save one on the Save screen,\nor import a friend’s file (≡ menu).',font=(TEXT,9),fill='#B9B9C4',justify='center')
            caption='Accounts'
        else:
            path,data=items[i];s=data['settings']
            cv.create_text(x0+px(30),top+px(38),text=('Shared  ·  ' if dp.is_shared(data) else 'Saved  ·  ')+dp.when(data),font=(TEXT,10),fill='#F3D9EC',anchor='w')
            RoundButton(self.ui,'Details',x0+cw-px(38),top+px(38),px(30),'info',lambda p=path:self.run(lambda:self.details(p)),'#8A3F7C','#FFFFFF','#A04E90')
            fps=dp.shown('FrameRateLimit',s['FrameRateLimit']) if 'FrameRateLimit' in s else '--'
            draw_matrix(cv,fps,cx,top+ch*0.34,px(2.3) if len(fps)<4 else px(1.9),'#FFFFFF')
            cv.create_text(cx,top+ch*0.34+px(44),text='FPS limit',font=(TEXT,10),fill='#E9D3E4')
            ar=min(cw*0.24,ch*0.17);ay=top+ch-px(26)-2*ar   # dotted orbits kept inside the card
            for k,ox in enumerate((-0.55,0,0.55)):cv.create_oval(cx+ox*ar-ar,ay,cx+ox*ar+ar,ay+2*ar,outline='#7D3A70',dash=(1,4))
            cv.create_line(x0+px(24),ay+ar*1.15,x0+cw-px(24),ay+ar*1.15,fill='#6A2E5E',dash=(1,4))
            for fx,fy in ((-0.45,0.05),(0.1,0.35),(-0.6,0.6),(0.7,0.75)):
                xx=cx+fx*cw*0.5;yy=ay+fy*ar*1.4;cv.create_oval(xx-px(3),yy-px(3),xx+px(3),yy+px(3),fill='#FFFFFF',outline='')
            caption=self.names[i]
        cy=top+ch+px(30);cv.create_text(cx,cy,text=fit(cv,caption,(SEMI,12),W-px(48)),font=(SEMI,12),fill=c['text'])
        n=len(items);shown=min(n,7)
        for k in range(shown):
            on=i is not None and (k==i if n<=7 else k==round(i*(shown-1)/max(1,n-1)));rr=px(3) if on else px(2)
            xx=cx+(k-(shown-1)/2)*px(12);cv.create_oval(xx-rr,cy+px(24)-rr,xx+rr,cy+px(24)+rr,fill=c['text'] if on else c['faint'],outline='')
        # tiles
        ty=cy+px(48);th=max(px(150),min(px(250),H-ty-px(40)));lx=px(16);tw=(W-px(40))/2;rx=lx+tw+px(8)
        cv.create_image(lx,ty,image=self.images.card(tw,th,px(30),'slate',c['bg']),anchor='nw')
        cv.create_text(lx+px(22),ty+px(32),text='Video settings',font=(TEXT,11),fill='#FFFFFF',anchor='w')
        cnt=len(items[i][1]['settings']) if i is not None else 0
        mw=matrix_width(str(cnt),px(1.8));draw_matrix(cv,str(cnt),lx+px(22)+mw/2,ty+th-px(62),px(1.8),'#E8E8EE')
        cv.create_text(lx+px(30)+mw,ty+th-px(72),text='of 12',font=(TEXT,8),fill='#8A8A94',anchor='w')
        dy=ty+th-px(26);steps=int((tw-px(36))/px(8))
        for k in range(steps):
            xx=lx+px(18)+k*px(8);lit=k<steps*cnt/12
            cv.create_oval(xx-px(1.4),dy-px(1.4),xx+px(1.4),dy+px(1.4),fill='#FFFFFF' if lit else '#3A3A42',outline='')
        mk=lx+px(18)+steps*cnt/12*px(8);cv.create_rectangle(mk-px(1.5),dy-px(8),mk+px(1.5),dy+px(8),fill=LIME,outline='')
        cv.create_image(rx,ty,image=self.images.card(tw,px(62),px(26),'indigo',c['bg']),anchor='nw')
        cv.create_text(rx+px(22),ty+px(31),text='Keep on top',font=(TEXT,11),fill='#FFFFFF',anchor='w')
        Toggle(self.ui,'Keep on top',rx+tw-px(66),ty+px(18),px(44),px(26),self.prefs['pin_full'],self.set_pin_full)
        ay=ty+px(70);ah=th-px(70)
        cv.create_image(rx,ay,image=self.images.card(tw,ah,px(30),'ember',c['bg']),anchor='nw')
        cv.create_text(rx+px(22),ay+px(32),text='Apply',font=(TEXT,11),fill='#FFFFFF',anchor='w')
        cv.create_text(rx+px(22),ay+px(54),text='to another account',font=(TEXT,8),fill='#D9A08F',anchor='w')
        base=ay+ah-px(30)
        cv.create_line(rx+px(14),base,rx+tw-px(14),base,fill='#7A2A1A',dash=(1,4))
        cv.create_arc(rx+tw*0.38,base-tw*0.34,rx+tw*0.92,base+tw*0.2,start=0,extent=180,style='arc',outline='#F3C2B0',width=1)
        cv.create_arc(rx+tw*0.22,base-tw*0.12,rx+tw*0.5,base+tw*0.1,start=0,extent=180,style='arc',outline='#F3C2B0',width=1)
        for fx in (0.22,0.38,0.5,0.92):xx=rx+tw*fx;cv.create_oval(xx-px(3),base-px(3),xx+px(3),base+px(3),fill=LIME,outline='')
        self.apply_tile=Hotspot(self.ui,'Apply',rx,ay,tw,ah,px(30),lambda:self.run(self.apply_profile),'#FFB199')
        if i is None:self.apply_tile.set_state('disabled')
        cv.create_text(W/2,H-px(14),text=self.status.get(),font=(TEXT,9),fill=c['muted'],width=W-px(40),anchor='s',justify='center')
    def pick(self,j):
        if 0<=j<len(self.items):self.selected=self.items[j][0];self.redraw();self.update_mini()
    def step_profile(self,d):
        if not self.items:return 'break'
        i=[p for p,_ in self.items].index(self.selected) if self.selected in [p for p,_ in self.items] else 0
        self.pick(max(0,min(len(self.items)-1,i+d)));return 'break'
    def build_menu(self):
        """The round menu button's contents: the selected profile's actions first, then app items."""
        c=self.look.c;opts=dict(tearoff=False,background=c['surface'],foreground=c['text'],activebackground=c['hover'],activeforeground=c['text'],disabledforeground=c['disabledtext'],selectcolor=c['text'],font=(TEXT,10))
        m=tk.Menu(self.root,**opts);path=self.selected if self.items else None
        if path:
            name=next((n for (p,_),n in zip(self.items,self.names) if p==path),'profile')
            m.add_command(label=f'“{name}”',state='disabled')
            for label,fn in [('Apply to an account...',self.apply_profile),('Rename...    F2',self.rename_profile),('Duplicate',self.duplicate_profile),('Export for a friend...',self.export_profile),('Copy values',self.copy_values),('Details',self.details)]:
                m.add_command(label='   '+label,command=lambda fn=fn:self.run(lambda:fn(path)))
            m.add_command(label='   Delete...    Del',foreground=c['danger'],command=lambda:self.run(lambda:self.delete_profile(path)));m.add_separator()
        m.add_command(label='Accounts' if self.screen=='save' else 'Save screen',command=lambda:self.show_screen('accounts' if self.screen=='save' else 'save'))
        m.add_command(label='Switch account (open Riot Client)    Ctrl+L',command=lambda:self.run(self.launch_riot))
        m.add_command(label='Compact view    Ctrl+M',command=lambda:self.run(self.show_mini))
        m.add_command(label='Import profile...    Ctrl+I',command=lambda:self.run(self.import_profile))
        m.add_command(label='Undo last apply...',command=lambda:self.run(self.undo_last))
        m.add_command(label='Change save account...',command=lambda:self.run(lambda:self.save_settings(True)))
        m.add_checkbutton(label='Keep this window on top',variable=self.pin_var,command=self.pin_full)
        theme=tk.Menu(m,**opts)
        for name in ('dark','light'):theme.add_radiobutton(label=name.title(),value=name,variable=self.theme_var,command=lambda n=name:self.choose_theme(n))
        m.add_cascade(label='Theme',menu=theme);m.add_separator()
        m.add_command(label='About, safety & limits',command=self.about)
        self.menu=m;return m
    def popup(self,anchor=None,event=None):
        menu=self.build_menu()
        if event:x,y=event.x_root,event.y_root
        elif anchor:x,y=anchor
        else:x,y=self.root.winfo_rootx()+self.look.px(40),self.root.winfo_rooty()+self.look.px(80)
        try:menu.tk_popup(x,y)
        finally:menu.grab_release()
    def set_pin_full(self,value):self.pin_var.set(value);self.pin_full()

    # ---------- state ----------
    def load_items(self):
        self.items=dp.entries(self.store);self.names=dp.display_names(self.items)
        if self.selected not in [p for p,_ in self.items]:self.selected=None
    def refresh(self):
        self.load_items();self.acct=self.account_view();self.redraw();self.update_mini()
    def set_status(self,text):
        self.status.set(text)
        if getattr(self,'content',None) is not None and self.view=='full' and not self.closed:self.redraw()
        if self.mini and self.view=='mini' and not self.closed:self.mini.update()
    def set_busy(self,busy):
        for b in (getattr(self,'save_btn',None),getattr(self.mini,'save',None) if self.mini else None,getattr(self.mini,'apply',None) if self.mini else None):
            if b is not None and b.cv.winfo_exists():b.set_state('disabled' if busy else 'normal')
    def run(self,action):
        """Single entry point for user actions: blocks re-entry (double clicks, held keys) and
        turns expected failures into a message without losing data."""
        if self.busy:self.set_status('Still finishing the previous action.');return
        self.busy=True;self.set_busy(True)
        try:return action()
        except (OSError,ValueError,RuntimeError,UnicodeError) as e:
            self.set_status('Stopped. Nothing was changed by the step that failed.')
            self.notice('Action stopped',str(e))
        finally:
            self.busy=False
            if not self.closed:self.set_busy(False)
    def scan(self):return dp.account_paths(model.discover(self.config_root,self.guard),self.config_root)
    def current_account(self,paths=None):
        """(settings file, your name or None) for the account VALORANT's log reports as signed in."""
        uid=dp.signed_in(self.config_root)
        if not uid:return None
        if paths is None:paths=dp.account_paths(model.discover(self.config_root,lambda:None),self.config_root)
        match=[p for p in paths if (dp.account_of(p,self.config_root) or '').startswith(uid)]
        if len(match)!=1:return None
        try:return match[0],self.store.bindings().get(model.source_id(match[0]))
        except (OSError,ValueError,UnicodeError):return match[0],None
    def check_closed(self):
        try:(self.guard or model.ensure_closed)()
        except RuntimeError as e:
            raise RuntimeError('Close VALORANT and Riot Client first, then press Apply again - your profile is ready.\n\n'
                               'Why: while VALORANT runs it keeps its settings in memory and writes them back when it closes, '
                               'which would undo the change. Tune never closes the game for you.\n\n('+str(e)+')') from None
    def profile(self,path):return model.import_profile(dp.owned(self.store,path))
    def label_for(self,target):
        try:return self.store.bindings().get(model.source_id(target))
        except (OSError,ValueError,UnicodeError):return None
    def describe(self,target):
        try:rel=Path(target).resolve().relative_to(self.config_root.resolve())
        except ValueError:rel=Path(target).name
        return str(Path('VALORANT','Saved','Config')/rel)

    # ---------- dialogs (patched in tests) ----------
    def owner(self):return self.root
    def dialog(self,title):
        c=self.look.c;px=self.look.px;owner=self.owner()
        win=tk.Toplevel(owner);win.title(title);win.configure(bg=c['bg']);win.transient(owner);win.resizable(False,False)
        frame=tk.Frame(win,bg=c['bg']);frame.pack(fill='both',expand=True,padx=px(24),pady=px(20))
        return win,frame
    def wait(self,win,focus=None):
        win.bind('<Escape>',lambda e:win.destroy());win.protocol('WM_DELETE_WINDOW',win.destroy)
        win.update_idletasks();owner=self.owner()
        g=clamp_geometry([win.winfo_reqwidth(),win.winfo_reqheight(),owner.winfo_rootx()+self.look.px(24),owner.winfo_rooty()+self.look.px(40)],work_areas(win),(self.look.px(200),self.look.px(120)))
        win.geometry(f'+{g[2]}+{g[3]}');self.dark_bar(win);self.fade(win)
        (focus or win).focus_set();win.grab_set();self.root.wait_window(win)
    def heading(self,frame,text,sub=None,width=420):
        c=self.look.c;px=self.look.px
        tk.Label(frame,text=text,bg=c['bg'],fg=c['text'],font=(SEMIBOLD,15),anchor='w',justify='left',wraplength=px(width)).pack(fill='x')
        if sub:tk.Label(frame,text=sub,bg=c['bg'],fg=c['muted'],font=(FONT,10),anchor='w',justify='left',wraplength=px(width)).pack(fill='x',pady=(px(6),px(12)))
    def buttons(self,frame,cancel,ok_text,ok,kind='primary'):
        px=self.look.px;row=tk.Frame(frame,bg=self.look.c['bg']);row.pack(fill='x',pady=(px(16),0))
        ok_button=Button(row,self.look,ok_text,ok,kind);ok_button.pack(side='right')
        Button(row,self.look,'Cancel',cancel).pack(side='right',padx=(0,px(8)));return ok_button
    def notice(self,title,body):
        win,frame=self.dialog(title);self.heading(frame,title,body)
        row=tk.Frame(frame,bg=self.look.c['bg']);row.pack(fill='x');ok=Button(row,self.look,'OK',win.destroy,'primary');ok.pack(side='right')
        self.wait(win,ok)
    def ask_yes(self,title,body,ok_text,danger=False):
        win,frame=self.dialog(title);answer=[];self.heading(frame,title,body)
        def ok():answer.append(True);win.destroy()
        self.buttons(frame,win.destroy,ok_text,ok,'danger' if danger else 'primary');self.wait(win)
        return bool(answer)
    def entry(self,frame,value=''):
        c=self.look.c;var=tk.StringVar(frame,value=value)
        e=tk.Entry(frame,textvariable=var,bg=c['surface'],fg=c['text'],insertbackground=c['text'],relief='flat',font=(FONT,11),highlightthickness=self.look.px(2),highlightbackground=c['stroke'],highlightcolor=c['focus'],selectbackground=c['accent'],selectforeground='#FFFFFF')
        e.pack(fill='x',ipady=self.look.px(7));return e,var
    def ask_text(self,title,prompt,initial=''):
        win,frame=self.dialog(title);answer=[];self.heading(frame,title,prompt)
        e,var=self.entry(frame,initial);e.select_range(0,'end')
        def ok():answer.append(var.get());win.destroy()
        e.bind('<Return>',lambda ev:ok());self.buttons(frame,win.destroy,'OK',ok);self.wait(win,e)
        return answer[0] if answer else None
    def choose_source(self,paths,purpose,profile=None):
        """Explicit folder choice. Nothing is preselected; labels are yours, never inferred."""
        if not paths:raise ValueError('No VALORANT settings files were found in %LOCALAPPDATA%\\VALORANT\\Saved\\Config. Sign in to that account in VALORANT once, close the game and Riot Client, then try again.')
        c=self.look.c;px=self.look.px
        titles={'save':('Name this account','Each line is one Riot account that has played on this PC. The one marked "signed in" is the account VALORANT is using now (from its own log). Tune can\'t see Riot names, so type a name you\'ll recognise - you only do this once per account.'),
                'apply':('Apply to which account?',f'Applying “{profile["label"] if profile else ""}”. Choose the destination folder yourself; nothing is preselected. Only supported video values will change.'),
                'undo':('Undo on which account?','Choose the folder whose last Tune apply you want to undo.')}
        win,frame=self.dialog(titles[purpose][0]);result=[];self.heading(frame,*titles[purpose])
        labels=self.store.bindings();rows=[];uid=dp.signed_in(self.config_root);signed=None
        for i,p in enumerate(paths):
            ref=model.source_id(p);folder=dp.account_of(p,self.config_root) or p.parent.parent.name;short=folder if len(folder)<=14 else folder[:12]+'…'
            text=(labels.get(ref) or 'Unnamed account')+'   ·   '+short
            if uid and folder.startswith(uid):text+='   ·   signed in';signed=i
            if profile and ref==profile['provenance']['source_ref']:text+='   ·   saved from here'
            rows.append(text)
        box=tk.Listbox(frame,width=60,height=min(6,max(3,len(rows))),bg=c['surface'],fg=c['text'],selectbackground=c['accent'],selectforeground='#FFFFFF',activestyle='none',relief='flat',font=(FONT,10),highlightthickness=px(2),highlightbackground=c['stroke'],highlightcolor=c['focus'],exportselection=False,bd=0)
        for r in rows:box.insert('end','  '+r)
        box.pack(fill='x');box.selection_clear(0,'end')
        detail=tk.StringVar(frame,value='No folder selected yet.')
        tk.Label(frame,textvariable=detail,bg=c['bg'],fg=c['muted'],font=(FONT,9),anchor='w',justify='left',wraplength=px(420)).pack(fill='x',pady=(px(8),px(4)))
        var=None
        if purpose=='save':
            tk.Label(frame,text='Your label for this folder (shown as “your label”, not a Riot ID)',bg=c['bg'],fg=c['text'],font=(FONT,10),anchor='w').pack(fill='x',pady=(px(8),px(6)))
            entry,var=self.entry(frame)
        def changed(e=None):
            sel=box.curselection()
            if not sel:return
            p=paths[sel[0]];ref=model.source_id(p);note='Folder: '+self.describe(p)
            if profile and ref==profile['provenance']['source_ref']:note+='\nThis is the folder this profile was saved from.'
            elif labels.get(ref):note+='\nLabel: '+labels[ref]+' (entered by you)'
            if sel[0]==signed:note+='\nVALORANT\'s own log says this account is signed in.'
            detail.set(note)
            if var is not None and not var.get().strip():var.set(labels.get(ref,''))
        box.bind('<<ListboxSelect>>',changed)
        # Saving: start on the account VALORANT reports as signed in (shown, and you still press
        # Save). Apply/Undo never preselect a destination.
        if purpose=='save' and signed is not None:box.selection_set(signed);box.see(signed);changed()
        def finish():
            try:
                sel=box.curselection()
                if not sel:raise ValueError('Choose a folder from the list first.')
                name=model.clean_label(var.get()) if var is not None else ''
                result.append((paths[sel[0]],name));win.destroy()
            except ValueError as e:detail.set(str(e))
        self.ok_button=self.buttons(frame,win.destroy,{'save':'Save settings','apply':'Review changes','undo':'Review undo'}[purpose],finish)
        self.wait(win,box)
        return result[0] if result else None
    def confirm_changes(self,target,delta,action,dest):
        c=self.look.c;px=self.look.px;win,frame=self.dialog(action+': review changes');answer=[]
        self.heading(frame,f'{action} {len(delta)} video setting'+('s' if len(delta)!=1 else ''),f'Destination: {dest}\n{self.describe(target)}')
        table=tk.Frame(frame,bg=c['surface'],highlightthickness=1,highlightbackground=c['stroke']);table.pack(fill='x')
        table.columnconfigure(0,weight=1)
        for i,(key,before,after) in enumerate(delta):
            bg=c['surface'] if i%2==0 else c['surface2']
            cell=tk.Frame(table,bg=bg);cell.grid(row=i,column=0,sticky='ew');cell.columnconfigure(1,weight=1)
            tk.Label(cell,text=dp.NAMES.get(key,key),bg=bg,fg=c['text'],font=(SEMIBOLD,10),anchor='w').grid(row=0,column=0,sticky='w',padx=(px(12),px(6)),pady=px(5))
            tk.Label(cell,text=key,bg=bg,fg=c['faint'],font=(FONT,8),anchor='w').grid(row=0,column=1,sticky='w')
            tk.Label(cell,text=f'{dp.shown(key,before)}  →  {dp.shown(key,after)}',bg=bg,fg=c['text'],font=(SEMIBOLD,10)).grid(row=0,column=2,sticky='e',padx=px(12))
        tk.Label(frame,text='A backup of these values is saved first. Everything else in the file is kept as it is: sensitivity, resolution, keybinds and account data are not touched. Keep VALORANT and Riot Client closed.',bg=c['bg'],fg=c['muted'],font=(FONT,9),justify='left',anchor='w',wraplength=px(420)).pack(fill='x',pady=(px(12),0))
        def ok():answer.append(True);win.destroy()
        self.buttons(frame,win.destroy,action+' now',ok);self.wait(win)
        return bool(answer)

    # ---------- workflows ----------
    def game_open(self):
        """True when the process guard would block (game/client running or list unreadable)."""
        try:self.check_closed();return False
        except RuntimeError:return True
    def launch_riot(self):
        """Opens Riot Client so YOU can sign in / switch account there. Tune launches the app
        the user already has and never signs in, reads tokens or automates anything."""
        exe=dp.riot_client()
        if exe is None:raise RuntimeError('Tune could not find Riot Client automatically. Open it yourself from the Start menu, sign in to the account you want, then switch back to Tune - it will recognise the account.')
        self.launcher(exe)
        self.set_status('Opening Riot Client. Sign in to the account you want, then switch back here. Tune will recognise it.')
    def save_settings(self,force_setup=False):
        # Save only READS game files, so it works while VALORANT is open. capture() still reads
        # twice and refuses if the file changes mid-read. Writing (Apply/Undo) stays guarded.
        reading=lambda:None;self.saved_while_open=self.game_open()
        paths=dp.account_paths(model.discover(self.config_root,reading),self.config_root);chosen=None;rem=dp.remembered(self.store)
        cur=None if force_setup else self.current_account(paths)
        if cur and cur[1]:chosen=cur            # signed-in account already has your name: one click
        elif rem and not cur and not force_setup:
            match=[p for p in paths if model.source_id(p)==rem[0]]
            if len(match)==1:chosen=(match[0],rem[1])
        if chosen is None:chosen=self.choose_source(paths,'save')
        if chosen is None:self.set_status('Save cancelled. Nothing changed.');return
        path,label=chosen;data=model.capture(path,label,self.config_root,reading)
        saved,replaced=dp.save_capture(self.store,data);warning=''
        try:self.store.label(path,label);self.store.remember(path)
        except (OSError,ValueError):warning=' The folder choice could not be remembered; you will be asked again next time.'
        self.selected=saved
        self.last_saved={'label':label,'time':dp.when(data),'n':len(data['settings']),'names':dp.captured_names(data),'ref':len(data.get('reference',{}).get('values',{})),'open':self.saved_while_open}
        self.refresh();self.set_status(('Updated' if replaced else 'Saved')+f' “{label}”. Find it under Accounts.'+warning)
        return saved
    def apply_profile(self,path=None):
        path=path or self.selected
        if not path:raise ValueError('Select a profile under Accounts first.')
        profile=self.profile(path);self.check_closed()
        chosen=self.choose_source(self.scan(),'apply',profile)
        if chosen is None:self.set_status('Apply cancelled. Nothing changed.');return
        target=chosen[0];raw,delta=model.preview(target,profile,self.config_root,self.guard)
        dest=self.label_for(target) or 'unlabelled folder'
        if not delta:self.set_status(f'{dest} already matches “{profile["label"]}”. Nothing was written.');return
        if not self.confirm_changes(target,delta,'Apply',dest):self.set_status('Apply cancelled. Nothing changed.');return
        backup=model.apply(target,profile['settings'],raw,self.store.base/'backups',self.config_root,self.guard)
        if backup is None:self.set_status('Already matched. Nothing was written.');return
        self.set_status(f'Applied {len(delta)} video setting(s) to {dest}. Undo is in the ⋯ menu.')
        self.notice('Applied',f'{len(delta)} video setting(s) from “{profile["label"]}” were written to {dest}.\n\nNext: open VALORANT on that account and check Settings › Video. VALORANT may keep or replace local values after launch; Tune cannot verify that from here.\n\nChanged your mind? ⋯ › Undo last apply.')
        return backup
    def undo_last(self):
        self.check_closed();chosen=self.choose_source(self.scan(),'undo')
        if chosen is None:self.set_status('Undo cancelled. Nothing changed.');return
        target=chosen[0];records=dp.backups_for(self.store,target)
        if not records:raise ValueError('There is no Tune apply to undo for that folder.')
        raw,values,delta=model.undo_preview(target,records[0],self.config_root,self.guard)
        if not delta:self.set_status('Nothing to undo; the values already match.');return
        if not self.confirm_changes(target,delta,'Undo',self.label_for(target) or 'unlabelled folder'):self.set_status('Undo cancelled. Nothing changed.');return
        model.apply(target,values,raw,self.store.base/'backups',self.config_root,self.guard)
        self.set_status('Previous video values restored. That undo can itself be undone the same way.')
    def import_profile(self):
        selected=filedialog.askopenfilename(title='Import a Tune profile',filetypes=[('Tune profile','*.json')],parent=self.owner())
        if not selected:self.set_status('Import cancelled.');return
        data=dp.read_import(selected);saved=self.store.save(data);self.selected=saved
        self.refresh();self.show_screen('accounts');self.set_status(f'Imported “{data["label"]}”. You choose the destination when you apply it.')
        return saved
    def export_profile(self,path):
        data=self.profile(path)
        label=self.ask_text('Export for a friend','Only the supported video values are exported. No account labels, folder IDs, paths or sensitivity. Optional display name for the file:',data['label'])
        if label is None:self.set_status('Export cancelled.');return
        payload=dp.share_payload(data,label)
        selected=filedialog.asksaveasfilename(title='Export profile',initialfile='tune-profile.json',defaultextension='.json',filetypes=[('Tune profile','*.json')],parent=self.owner())
        if not selected:self.set_status('Export cancelled.');return
        dp.export_share(selected,payload);self.set_status('Exported video values only.')
    def rename_profile(self,path):
        data=self.profile(path);new=self.ask_text('Rename profile','New name (1–80 characters). This is your label, not a Riot ID.',data['label'])
        if new is None or new.strip()==data['label']:return
        dp.rename(self.store,path,new);self.refresh();self.set_status('Renamed.')
    def duplicate_profile(self,path):
        saved=dp.duplicate(self.store,path);self.selected=saved;self.refresh();self.set_status('Duplicated.')
    def delete_profile(self,path):
        data=self.profile(path)
        if not self.ask_yes('Delete this profile?',f'“{data["label"]}” will disappear from Accounts. The file is moved to the app’s “deleted” folder, so it can be recovered by hand. Your VALORANT settings are not changed.','Delete',True):return
        dp.delete(self.store,path);self.refresh();self.set_status('Profile deleted.')
    def readable(self,path):
        d=self.profile(path);lines=[d['label']+('  (shared file)' if dp.is_shared(d) else '  (your label, not a verified Riot ID)'),'Saved '+dp.when(d),'','Video values (applied by Tune):']
        lines+=[f'  {dp.NAMES[k]}: {d["settings"][k]}    [{k}]' for k in dp.ORDER if k in d['settings']]
        missing=[dp.NAMES[k] for k in dp.ORDER if k not in d['settings']]
        if missing:lines+=['','Not in this profile (manual): '+', '.join(missing)]
        ref=d.get('reference',{}).get('values',{})
        lines+=['','Sensitivity (reference only, never applied):']+([f'  {k.split("::")[-1]}: {v}' for k,v in sorted(ref.items())] or ['  not available'])
        lines+=['','Everything else (keybinds, crosshair, audio, resolution, display mode): manual.']
        return '\n'.join(lines)
    def copy_values(self,path):
        text=self.readable(path);self.root.clipboard_clear();self.root.clipboard_append(text);self.set_status('Copied readable values.')
    def details(self,path):self.notice('Profile details',self.readable(path))
    def about(self):
        self.notice(f'About {NAME} {VERSION}','Applies only 12 allowlisted video values (10 scalability groups, VSync, frame-rate limit) between local VALORANT config files. Everything else is manual.\n\nAccount names are labels you type; Riot IDs are never read. No passwords, tokens, game memory, injection, overlays, automation or network access. VALORANT and Riot Client must be closed for every save, apply and undo.\n\nCompact view shrinks this window; with keep-on-top it stays above borderless/windowed games, not exclusive fullscreen.\n\nFormerly "Preset Desk"; profiles stay in %LOCALAPPDATA%\\PresetDesk.\n\nNot affiliated with or approved by Riot Games. Use at your own discretion.')

    # ---------- windows ----------
    def place(self,win,geometry,minimum):
        g=clamp_geometry(list(geometry),work_areas(win),minimum);win.geometry(f'{g[0]}x{g[1]}+{g[2]}+{g[3]}');return g
    def fade(self,win):
        if not self.motion:return
        try:
            win.attributes('-alpha',0.0)
            for i,a in enumerate((0.35,0.7,1.0)):win.after(30*(i+1),lambda a=a:win.winfo_exists() and win.attributes('-alpha',a))
        except tk.TclError:pass
    def moved(self,event):
        if event.widget is not self.root or self.closed:return
        if self.pending:self.root.after_cancel(self.pending)
        self.pending=self.root.after(400,self.remember_full if self.view=='full' else self.remember_mini)
    def remember_mini(self):self.pending=None;self.mini.remember();self.persist()
    def remember_full(self):
        self.pending=None
        if self.view=='full' and self.root.state()=='normal' and self.root.winfo_width()>100:
            self.prefs['full']=clamp_geometry([self.root.winfo_width(),self.root.winfo_height(),self.root.winfo_x(),self.root.winfo_y()],work_areas(self.root),self.minimum);self.persist()
    def persist(self):
        try:self.store.base.mkdir(parents=True,exist_ok=True);model.write_json(self.prefs_path,self.prefs)
        except OSError:self.set_status('Window preferences could not be saved. Profiles are unaffected.')
    def pin_full(self):
        self.prefs['pin_full']=bool(self.pin_var.get());self.root.attributes('-topmost',self.prefs['pin_full']);self.persist()
    def choose_theme(self,name):
        if name not in PALETTES:raise ValueError('Unknown theme.')
        self.look.name=name;self.theme_var.set(name)
        try:self.store.base.mkdir(parents=True,exist_ok=True);model.write_json(self.store.base/'theme.json',{'version':1,'theme':name})
        except OSError:pass
        self.build();self.mini.build();self.dark_bar(self.root)
    def show_mini(self,initial=False):
        """Shrinks this same window to the compact layout (no second window)."""
        if self.view=='mini':return
        if not initial:self.remember_full()
        self.view='mini';self.content.pack_forget();self.mini.show()
        self.root.attributes('-topmost',self.prefs['pin_mini']);self.prefs['view']='mini';self.persist()
    def show_full(self):
        if self.view=='full':return
        self.mini.remember();self.mini.frame.pack_forget();self.view='full'
        self.content.pack(fill='both',expand=True)
        self.root.resizable(True,True);self.root.minsize(*self.minimum);self.place(self.root,self.prefs['full'],self.minimum)
        self.root.attributes('-topmost',self.prefs['pin_full']);self.dark_bar(self.root);self.fade(self.root);self.prefs['view']='full';self.persist()
    def toggle_view(self):(self.show_full if self.view=='mini' else self.show_mini)()
    def update_mini(self):
        if self.mini:self.mini.update()
    def close(self):
        if self.closed:return
        if self.view=='full':self.remember_full()
        else:self.mini.remember()
        self.persist();self.closed=True
        if self.pending:self.root.after_cancel(self.pending);self.pending=None
        self.cancel_redraw();self.root.destroy()

class MiniView:
    """Compact mode of the main window, Spotify-miniplayer style: the selected profile with
    Save, Apply, previous/next, keep-on-top and expand. Same window, same safeguards."""
    W,H=420,212
    def __init__(self,app):
        self.app=app;self.win=app.root;self.frame=None;self.build()
    def build(self):
        look=self.app.look;c=look.c;px=look.px;shown=self.frame is not None and self.frame.winfo_manager()
        if self.frame is not None:self.frame.destroy()
        self.frame=tk.Canvas(self.win,bg=c['bg'],highlightthickness=0,bd=0,width=px(self.W),height=px(self.H))
        self.ui=UI(self.frame,look)
        self.frame.bind('<ButtonPress-1>',self.drag_start);self.frame.bind('<B1-Motion>',self.drag_move)
        self.frame.bind('<Left>',lambda e:self.cycle(-1));self.frame.bind('<Right>',lambda e:self.cycle(1))
        if shown:self.frame.pack(fill='both',expand=True)
        self.update()
    def current(self):
        items=self.app.items
        if not items:return None,None
        if self.app.selected is None:self.app.selected=items[0][0]
        i=[p for p,_ in items].index(self.app.selected);return i,items[i]
    def update(self):
        """Redraws the compact card: name, FPS, prev/next, Save, Apply, pin, expand."""
        look=self.app.look;c=look.c;px=look.px;cv=self.frame;cv.delete('all');self.ui.reset()
        W,H=px(self.W),px(self.H);x,y,w,h=px(8),px(8),W-px(16),H-px(16)
        cv.create_image(x,y,image=self.app.images.card(w,h,px(44),'navy',c['bg']),anchor='nw')
        i,item=self.current()
        if item is None:name,meta='No profiles yet','Save one to get started'
        else:
            path,data=item;name=self.app.names[i];s=data['settings']
            fps=dp.shown('FrameRateLimit',s['FrameRateLimit']) if 'FrameRateLimit' in s else '--'
            meta=f'{fps} FPS  ·  {len(s)} video  ·  {dp.when(data)}'
        font=tkfont.Font(cv,family=SEMI,size=12);limit=w-px(150)
        if font.measure(name)>limit:
            while name and font.measure(name+'…')>limit:name=name[:-1]
            name+='…'
        self.name_text=name
        for k,(dx,dy) in enumerate([(0,0),(-1,1),(1,1),(-2,2),(0,2),(2,2)]):
            xx=x+px(30)+dx*px(4);yy=y+px(28)+dy*px(4);cv.create_oval(xx-px(1.3),yy-px(1.3),xx+px(1.3),yy+px(1.3),fill=LIME,outline='')
        self.name=cv.create_text(x+px(52),y+px(34),text=name,font=(SEMI,12),fill='#FFFFFF',anchor='w')
        cv.create_text(x+px(52),y+px(56),text=meta,font=(TEXT,8),fill='#7C83C8',anchor='w')
        d=px(38);pinned=self.app.prefs['pin_mini']
        self.expand=RoundButton(self.ui,'Full view',x+w-px(22)-d/2,y+px(40),d,'expand',lambda:self.app.run(self.app.show_full),'#1B2059','#FFFFFF','#262C70')
        self.pin=RoundButton(self.ui,'Keep on top: '+('on' if pinned else 'off'),x+w-px(30)-d*1.5,y+px(40),d,'pinned' if pinned else 'pin',self.toggle_pin,'#1B2059',LIME if pinned else '#FFFFFF','#262C70')
        bh=px(48);by=y+h-px(22)-bh;rd=px(44)
        self.prev=RoundButton(self.ui,'Previous profile',x+px(22)+rd/2,by+bh/2,rd,'prev',lambda:self.cycle(-1),'#1B2059','#FFFFFF','#262C70')
        self.next=RoundButton(self.ui,'Next profile',x+w-px(22)-rd/2,by+bh/2,rd,'next',lambda:self.cycle(1),'#1B2059','#FFFFFF','#262C70')
        pw=(w-px(44)-2*rd-px(28))/2;px0=x+px(22)+rd+px(10)
        self.save=PillButton(self.ui,'Save',px0,by,pw,bh,'Save',lambda:self.app.run(self.app.save_settings),'#1E2357','#FFFFFF','#283071','check')
        self.apply=PillButton(self.ui,'Apply',px0+pw+px(8),by,pw,bh,'Apply',lambda:self.app.run(self.app.apply_profile),'#C9472A','#FFFFFF','#DD5636','arrow')
        if item is None:
            for b in (self.prev,self.apply,self.next):b.set_state('disabled')
        elif len(self.app.items)<2:
            for b in (self.prev,self.next):b.set_state('disabled')
        if self.app.busy:self.save.set_state('disabled');self.apply.set_state('disabled')
    def cycle(self,d):
        i,item=self.current()
        if item is None:return 'break'
        self.app.selected=self.app.items[(i+d)%len(self.app.items)][0];self.update();return 'break'
    def toggle_pin(self):
        self.app.prefs['pin_mini']=not self.app.prefs['pin_mini']
        if self.app.view=='mini':self.win.attributes('-topmost',self.app.prefs['pin_mini'])
        self.app.persist();self.update()
    def show(self):
        px=self.app.look.px;self.frame.pack(fill='both',expand=True);self.update()
        need=(px(self.W),px(self.H));g=list(self.app.prefs['mini']);g[0],g[1]=need
        self.win.minsize(*need);self.app.place(self.win,g,need);self.win.resizable(False,False)
        self.app.dark_bar(self.win);self.app.fade(self.win)  # style change resets the dark title bar
    def drag_start(self,e):self.drag=(e.x_root,e.y_root,self.win.winfo_x(),self.win.winfo_y())
    def drag_move(self,e):
        if not hasattr(self,'drag') or self.app.view!='mini':return
        a,b,x,y=self.drag;w,h=self.win.winfo_width(),self.win.winfo_height()
        g=clamp_geometry([w,h,x+e.x_root-a,y+e.y_root-b],work_areas(self.win),(w,h));self.win.geometry(f'+{g[2]}+{g[3]}')
    def remember(self):
        if self.app.view=='mini' and self.win.state()=='normal' and self.win.winfo_width()>60:
            self.app.prefs['mini']=[self.win.winfo_width(),self.win.winfo_height(),self.win.winfo_x(),self.win.winfo_y()]

def watchdog(root,folder):
    """If the UI thread stalls for 8 s, write where it is stuck to <app folder>\\hang.log
    (local only, code locations only). Re-armed every 2 s while the UI is responsive."""
    import faulthandler
    try:folder.mkdir(parents=True,exist_ok=True);log=open(folder/'hang.log','w',encoding='utf-8')
    except OSError:return
    def beat():
        faulthandler.dump_traceback_later(8,repeat=False,file=log,exit=False);root.after(2000,beat)
    beat()
    return log

def main():
    if os.name=='nt':
        try:ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except (OSError,AttributeError):pass
    root=tk.Tk();app=App(root);log=watchdog(root,app.store.base);root.mainloop()

if __name__=='__main__':
    if '--self-test' in sys.argv:
        import desk_selftest;desk_selftest.run()
    else:main()
