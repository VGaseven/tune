"use strict";
/* Tune front-end. Two views: Accounts (tiles; click one for its side panel) and Crosshairs (a
   library of codes with previews). Talks to Python through window.pywebview.api. Nothing is ever
   invented: missing data shows "Unavailable". The tiny PREVIEW mock exists only for ?preview=1
   design checks in a plain browser - the real app never uses it. */

const hasApi=()=>!!(window.pywebview&&window.pywebview.api);
const PREVIEW=/[?&]preview=1/.test(location.search);
const PX={name:"Preview",color:"#00ffff",outline:true,outline_thickness:1,outline_opacity:.5,dot:false,dot_size:2,dot_opacity:1,
          inner:{show:true,thickness:2,length:4,vlength:4,offset:2,opacity:1},outer:{show:false}};
const PMOCK={accounts:[{ref:"a",account:"p1-eu",puuid:"p1",region:"eu",sens:0.4},{ref:"b",account:"p2-eu",puuid:"p2",region:"eu",sens:0.5}],
  view:{sens:0.4,ads:1,game_settings:60,resolution:"1920×1080",video:[{key:"sg.TextureQuality",name:"Textures",value:"3"}],crosshair:PX,crosshair_code:"0;P;c;5;h;0;0l;4;0o;2;0a;1;0f;0;1b;0"}};
async function call(name,...args){
  if(hasApi()) return await window.pywebview.api[name](...args);
  if(!PREVIEW) return {ok:false,error:"Tune engine not connected yet."};
  const M={accounts:PMOCK.accounts,account_view:{...PMOCK.view,ref:args[0]},sync_report:{source:null},rank_key_status:{set:false},
    status:{game_running:true,signed_in_ref:"a"},signin_saved:{a:"2026-11-04T16:00:00Z"},
    crosshair_gallery:{mine:[],presets:[{id:"preset-0",name:"Classic Cyan",code:PMOCK.view.crosshair_code,kind:"preset",preview:PX}],sites:[]},
    crosshair_preview:PX};
  return name in M?{ok:true,data:M[name]}:{ok:true,data:{source:"offline"}};
}

const $=s=>document.querySelector(s);
const esc=s=>String(s==null?"":s).replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const fmtSens=v=>v==null?null:String(Math.round(v*1000)/1000);
function ago(iso){ if(!iso) return ""; const s=(Date.now()-new Date(iso))/1000;
  if(s<90)return"just now"; if(s<5400)return Math.round(s/60)+"m ago";
  if(s<86400)return Math.round(s/3600)+"h ago"; return Math.round(s/86400)+"d ago"; }
let toastTimer;
function toast(msg,bad){ const t=$("#toast"); t.textContent=msg; t.className="toast show"+(bad?" bad":"");
  clearTimeout(toastTimer); toastTimer=setTimeout(()=>t.className="toast",3800); }
async function copyText(text,what){ try{await navigator.clipboard.writeText(text);toast(`Copied ${what}`);}catch(e){toast("Couldn't copy.",true);} }

let ACCOUNTS=[], RANK={}, SYNC={}, VIEW={}, STATUS={}, SAVED={}, GALLERY=null, EXPECT=null, SEL=null, KEY=false, RETRIED={}, FORCE=false, VIEWNAME="accounts";
const store={get(k){try{return localStorage.getItem(k)}catch(e){return null}},set(k,v){try{localStorage.setItem(k,v)}catch(e){}}};
const acc=ref=>ACCOUNTS.find(a=>a.ref===ref);
function riotId(a){const r=RANK[a.puuid];return r&&r.name?{name:r.name,tag:r.tag?"#"+r.tag:""}:{name:"Account "+a.puuid.slice(0,4),tag:""};}
const fullId=a=>{const i=riotId(a);return i.name+i.tag;};
const wide=u=>u?u.replace("largeart.png","wideart.png"):null;
const RK={iron:"#8d8f94",bronze:"#c08552",silver:"#cfd6de",gold:"#f0c75e",platinum:"#4fd1d9",diamond:"#c99af5",ascendant:"#41d69b",immortal:"#f0577a",radiant:"#ffe8a3"};
const rankColor=n=>RK[String(n||"").split(" ")[0].toLowerCase()]||"#8a8f99";
const inGame=a=>!!(a&&STATUS.game_running&&STATUS.signed_in_ref===a.ref);
const lastUsed=a=>!!(a&&STATUS.signed_in_ref===a.ref);
const isWide=()=>matchMedia("(min-width:900px)").matches;   // details sit next to the list; smaller windows slide them over it
const drawerOpen=()=>isWide()||$("#detail").classList.contains("open");
function countUp(el,text){ // animate the numeric part of a stat; plain text if not numeric
  const m=/^(-?[0-9.]+)(.*)$/.exec(text||""); if(!m||el.dataset.v===text){el.textContent=text;el.dataset.v=text;return;}
  const to=parseFloat(m[1]),dp=(m[1].split(".")[1]||"").length,from=parseFloat(el.dataset.v)||0,t0=performance.now();el.dataset.v=text;
  const step=t=>{const k=Math.min(1,(t-t0)/550),e=1-Math.pow(1-k,3);el.textContent=(from+(to-from)*e).toFixed(dp)+m[2];if(k<1&&el.dataset.v===text)requestAnimationFrame(step);else if(el.dataset.v===text)el.textContent=text;};
  requestAnimationFrame(step); setTimeout(()=>{if(el.dataset.v===text)el.textContent=text;},650);   // land on the value even if frames are paused (hidden window)
}
const meter=(id,pct,good)=>{const el=$("#"+id);if(!el)return;el.style.width=(pct==null?0:Math.max(2,Math.min(100,pct)))+"%";el.className=good==null?"":good?"good":"low";};

/* ---------------- views ---------------- */
function showView(name){
  VIEWNAME=name; store.set("tune.view",name);
  document.querySelectorAll(".tab").forEach(t=>t.classList.toggle("on",t.dataset.view===name));
  $("#v-accounts").classList.toggle("hidden",name!=="accounts"); $("#v-crosshairs").classList.toggle("hidden",name!=="crosshairs");
  $("#search").placeholder=name==="accounts"?"Search accounts  ( / )":"Search crosshairs  ( / )";
  if(name==="crosshairs"){if(!isWide())closeDrawer(); loadGallery();}
  applyFilter();
}

/* ---------------- account tiles ---------------- */
function renderList(){
  const list=$("#list"); list.innerHTML="";
  $("#sub").textContent=ACCOUNTS.length?`${ACCOUNTS.length} account${ACCOUNTS.length>1?"s":""} on this PC`:"Your accounts";
  $("#copy-all").classList.toggle("hidden",ACCOUNTS.length<3);
  if(!ACCOUNTS.length){
    list.innerHTML='<div class="empty">No VALORANT accounts on this PC yet.<br>Sign in once in VALORANT and the account appears here.<br><button class="btn primary" id="e-signin">Open Riot Client</button></div>';
    $("#e-signin").onclick=()=>call("launch_riot"); return;
  }
  ACCOUNTS.forEach((a,i)=>{const el=document.createElement("div");el.className="acc";el.dataset.ref=a.ref;el.tabIndex=0;el.setAttribute("role","button");
    el.style.animationDelay=(i*0.035)+"s";el.onclick=()=>openAccount(a.ref);el.onkeydown=e=>{if(e.key==="Enter"){e.stopPropagation();openAccount(a.ref);}};list.appendChild(el);paintRow(a);});
  applyFilter();
}
function paintRow(a){
  const el=document.querySelector(`.acc[data-ref="${a.ref}"]`); if(!el) return;
  const r=RANK[a.puuid], id=riotId(a), s=SYNC[a.ref], loading=KEY&&!r;
  el.classList.toggle("sel",a.ref===SEL);
  el.style.setProperty("--art",r&&r.card_url?`url("${wide(r.card_url)}")`:"none"); el.style.setProperty("--rk",rankColor(r&&r.rank));
  const src=s&&s.source?acc(s.source):null;
  const foot=s&&s.source?(s.in_sync?`<div class="a-foot ok"><i class="sdot"></i>Matches ${esc(src?riotId(src).name:"source")}</div>`
                                    :`<div class="a-foot warn"><i class="sdot"></i>${s.differ} changed since apply</div>`):"";
  el.innerHTML=`<div class="who"><div class="nm"><span class="id">${esc(id.name)}<b>${esc(id.tag)}</b></span>${SAVED[a.ref]?'<span class="pill key" title="One-click sign-in remembered">🔑</span>':""}${inGame(a)?'<span class="pill live">IN GAME</span>':lastUsed(a)?'<span class="pill last">LAST USED</span>':""}</div>
      <div class="mini"><span>Sens <b>${esc(fmtSens(a.sens)??"—")}</b></span><span>HS <b>${r&&r.hs!=null?r.hs+"%":loading?"…":"—"}</b></span><span>WR <b>${r&&r.wr!=null?r.wr+"%":loading?"…":"—"}</b></span></div>${foot}</div>
    <div class="rkbox"><div class="rkn">${r&&r.rank?esc(r.rank)+(r.rr!=null&&r.rank!=="Unrated"?`<small>${r.rr} RR</small>`:""):loading?"…":"Unavailable"}</div>${r&&r.rank_icon?`<img class="emblem" src="${esc(r.rank_icon)}" alt="">`:""}</div>`;
}
function applyFilter(){
  const q=($("#search").value||"").trim().toLowerCase();
  if(VIEWNAME==="crosshairs"){ document.querySelectorAll(".xcard").forEach(c=>c.classList.toggle("hidden",!!q&&!c.dataset.name.toLowerCase().includes(q))); return; }
  let shown=0;
  ACCOUNTS.forEach(a=>{const el=document.querySelector(`.acc[data-ref="${a.ref}"]`); if(!el) return; const r=RANK[a.puuid]||{};
    const hit=!q||[fullId(a),r.rank,a.region].some(s=>String(s||"").toLowerCase().includes(q)); el.classList.toggle("hidden",!hit); shown+=hit;});
  let n=$("#nohit"); if(!shown&&q){ if(!n){n=document.createElement("div");n.id="nohit";n.className="empty";$("#list").appendChild(n);} n.textContent=`No account matches "${q}".`;} else if(n) n.remove();
}

/* ---------------- side panel ---------------- */
function openAccount(ref){
  if(!acc(ref)) return; const changed=SEL!==ref; SEL=ref; store.set("tune.sel",ref);
  document.querySelectorAll(".acc").forEach(e=>e.classList.toggle("sel",e.dataset.ref===ref));
  const d=$("#detail"); d.classList.add("open"); if(!isWide())$("#scrim").classList.add("show");
  if(changed){d.scrollTop=0;d.classList.remove("swap");void d.offsetWidth;d.classList.add("swap");$("#signin").classList.remove("ready");}
  paintDetail(); loadSync(ref); loadView(ref);
}
function closeDrawer(){ $("#detail").classList.remove("open"); $("#scrim").classList.remove("show"); }
function stat(id,value,note){const v=$("#"+id);if(value==null){v.textContent="Unavailable";v.dataset.v="";}else countUp(v,value);v.classList.toggle("na",value==null);$("#"+id+"-n").textContent=note||"";}
function paintDetail(){
  const a=acc(SEL); if(!a) return; const r=RANK[a.puuid]||{}, id=riotId(a), v=VIEW[a.ref];
  $("#d-name").textContent=id.name; $("#d-tag").textContent=id.tag;
  $("#hero-art").style.backgroundImage=r.card_url?`url("${wide(r.card_url)}")`:"none";
  $("#d-rank").textContent=r.rank||(KEY&&!RANK[a.puuid]?"Loading…":"Unavailable");
  const sub=[r.rr!=null&&r.rank&&r.rank!=="Unrated"?r.rr+" RR":null,r.peak?"Peak "+r.peak:null].filter(Boolean).join(" · ");
  $("#d-rksub").textContent=sub||(!KEY?"Connect the free key to see rank":"");
  const em=$("#d-emblem"); if(r.rank_icon){em.src=r.rank_icon;em.classList.remove("hidden");}else em.classList.add("hidden");
  $("#hero").style.setProperty("--rk",rankColor(r.rank));
  const hasRR=r.rr!=null&&r.rank&&r.rank!=="Unrated"; $("#d-rrbar").classList.toggle("hidden",!hasRR); if(hasRR)$("#d-rrfill").style.width=Math.min(100,Math.max(3,r.rr))+"%";
  const mine=v?v.sens:a.sens;
  stat("d-sens",fmtSens(mine),mine==null?"No saved sensitivity on this PC":(v&&v.ads!=null?`ADS ${fmtSens(v.ads)}`:""));
  stat("d-hs",r.hs!=null?r.hs+"%":null,r.hs!=null?`last ${r.hs_matches} competitive match${r.hs_matches===1?"":"es"}`:"");
  stat("d-wr",r.wr!=null?r.wr+"%":null,r.wr!=null?`${r.wins}W · ${r.games} games this act`:"");
  meter("d-hs-m",r.hs!=null?r.hs*2:null,r.hs!=null?r.hs>=25:null); meter("d-wr-m",r.wr,r.wr!=null?r.wr>=50:null);
  paintSettings(a); paintSync(a);
}
function paintSettings(a){
  const v=VIEW[a.ref], rows=$("#m-rows");
  if(!v){rows.innerHTML='<div class="row"><span>Reading this account…</span><b>—</b></div>';$("#m-sum").textContent="Reading…";drawX($("#xcanvas"),null);$("#x-name").textContent="—";return;}
  const keep=(v.video||[]).filter(x=>x.key!=="bUseVSync"&&x.key!=="FrameRateLimit");
  $("#m-sum").textContent=[v.sens!=null?`Sens ${fmtSens(v.sens)}`:null,v.resolution,keep.length?`${keep.length} graphics settings`:"No graphics saved yet",`${v.game_settings} game settings`].filter(Boolean).join(" · ");
  const G=t=>`<div class="grp">${t}</div>`, R=(k,val,key)=>`<div class="row${key?" key":""}"><span>${esc(k)}</span><b>${esc(val??"Not saved")}</b></div>`;
  rows.innerHTML=G("Aim")+R("Sensitivity",fmtSens(v.sens),1)+R("Scoped / ADS",fmtSens(v.ads),1)
    +G("Display &amp; graphics")+R("Resolution",v.resolution)+(keep.length?keep.map(x=>R(x.name,x.value)).join(""):R("Video settings","Not saved yet"))
    +G("Everything else")+R("Game settings",`${v.game_settings} saved`);
  $("#x-name").textContent=v.crosshair?v.crosshair.name:"No crosshair saved on this PC"; drawX($("#xcanvas"),v.crosshair);
  $("#x-copy").disabled=!v.crosshair_code; $("#x-save").disabled=!v.crosshair_code;
}
async function loadView(ref){
  const r=await call("account_view",ref); if(r.ok){VIEW[ref]=r.data; if(ref===SEL)paintDetail(); if(VIEWNAME==="crosshairs")renderGallery();}
}
function paintSteps(a){
  const el=$("#steps"), s=SYNC[a.ref];
  const done1=!!(s&&s.in_sync), done2=done1&&lastUsed(a)&&!!s.applied_at;
  const st=[["Apply settings",done1],[SAVED[a.ref]?`Sign in · one click`:`Sign in`,done2],["Play",false]];
  const cur=st.findIndex(x=>!x[1]);
  el.innerHTML=st.map(([t,d],i)=>`<div class="step${d?" done":""}${i===cur?" now":""}"><span>${d?"✓":i+1}</span>${esc(t)}</div>`).join("");
}
function paintSync(a){
  const s=SYNC[a.ref], box=$("#sync"), t=$("#sync-t"), ap=$("#apply"), rs=$("#restore"), blocked=inGame(a);
  box.className="sync"; ap.disabled=blocked||ACCOUNTS.length<2; rs.classList.toggle("hidden",!(s&&s.has_backup));
  $("#apply-t").textContent=blocked?"Quit VALORANT to apply":"Apply settings…";
  const rb=$("#remember"); rb.classList.toggle("hidden",!inGame(a)); rb.textContent=SAVED[a.ref]?"Sign-in remembered ✓":"Remember sign-in";
  $("#signin").title=SAVED[a.ref]?`Switch to ${fullId(a)} in one click`:"Sign in — opens Riot Client";
  $("#signin-t").textContent=SAVED[a.ref]?"Sign in 🔑":"Sign in"; $("#signin").classList.toggle("one",!!SAVED[a.ref]);
  paintSteps(a);
  if(blocked){box.classList.add("warn");t.textContent="VALORANT is open on this account right now, so it would undo any change when it closes. Quit VALORANT first.";return;}
  if(!s){t.textContent="Checking…";return;}
  const src=s.source?acc(s.source):null, sn=src?fullId(src):"the account you copied from";
  if(!s.source){t.textContent=s.applied_at?`Settings applied ${ago(s.applied_at)}.`:"Press Apply settings to copy another account's settings here.";return;}
  if(s.in_sync){box.classList.add("ok");t.textContent=`Matches ${sn} · applied & verified ${ago(s.applied_at)}`;return;}
  box.classList.add("warn");
  t.textContent=`${s.differ} setting${s.differ===1?"":"s"} changed since you copied from ${sn} (${ago(s.applied_at)}) — Riot may have restored its online copy. Apply again.`;
}
async function loadSync(ref){
  const r=await call("sync_report",ref); if(r.ok){SYNC[ref]=r.data; const a=acc(ref); if(a){paintRow(a); if(ref===SEL)paintSync(a);}}
}

/* ---------------- crosshair drawing ---------------- */
const XBG={range:[[0,"#6b7480"],[.55,"#4a525c"],[.56,"#3a3f46"],[1,"#2a2e34"]],sky:[[0,"#9fc7e8"],[.6,"#d9ecf7"],[.61,"#b9a98f"],[1,"#8c7c63"]],
  sand:[[0,"#e9d3a6"],[1,"#b88c55"]],dark:[[0,"#15171c"],[1,"#0b0c0f"]]};
let XB=store.get("tune.xbg")||"range";
function drawX(cv,x,bg){
  const ctx=cv.getContext("2d"),W=cv.width,H=cv.height,cx=Math.round(W/2),cy=Math.round(H/2);
  cv._x=x; const b=XBG[bg||XB]||XBG.range, g=ctx.createLinearGradient(0,0,0,H);
  b.forEach(([o,c])=>g.addColorStop(o,c)); ctx.globalAlpha=1; ctx.fillStyle=g; ctx.fillRect(0,0,W,H);
  if(!x){ctx.fillStyle="rgba(255,255,255,.4)";ctx.font=`600 ${Math.max(9,W/14)}px Inter,sans-serif`;ctx.textAlign="center";ctx.fillText("No crosshair",cx,cy+4);return;}
  // 4px per game pixel, zoomed out only if the crosshair wouldn't fit the box
  const reach=l=>l&&l.show&&l.thickness&&l.length?l.offset+Math.max(l.length,l.vlength||0)+l.thickness/2:0;
  const ext=Math.max(reach(x.inner),reach(x.outer),x.dot?x.dot_size/2:0,1)+(x.outline?x.outline_thickness:0);
  const u=Math.min(4,(Math.min(W,H)/2-4)/ext);
  const ot=x.outline?Math.max(1,x.outline_thickness)*u:0;
  // the outline has its own opacity: a line at 0% with a full outline is VALORANT's "black crosshair"
  const box=(x0,y0,w,h,alpha)=>{ if(ot){ctx.globalAlpha=x.outline_opacity;ctx.fillStyle="#000";ctx.fillRect(x0-ot,y0-ot,w+2*ot,h+2*ot);}
    ctx.globalAlpha=alpha;ctx.fillStyle=x.color;ctx.fillRect(x0,y0,w,h); };
  const arms=l=>{ if(!l||!l.show||!l.thickness||!l.length) return; const t=l.thickness*u,L=l.length*u,V=(l.vlength||l.length)*u,o=l.offset*u,h=t/2;
    box(cx+h+o,cy-h,L,t,l.opacity); box(cx-h-o-L,cy-h,L,t,l.opacity);
    box(cx-h,cy-h-o-V,t,V,l.opacity); box(cx-h,cy+h+o,t,V,l.opacity); };
  arms(x.inner); arms(x.outer);
  if(x.dot){const s=x.dot_size*u;box(cx-s/2,cy-s/2,s,s,x.dot_opacity);}
  ctx.globalAlpha=1;
}

/* ---------------- crosshair library ---------------- */
async function loadGallery(){ const r=await call("crosshair_gallery"); if(r.ok){GALLERY=r.data;renderGallery();}
  ACCOUNTS.forEach(a=>{if(!VIEW[a.ref])loadView(a.ref);}); }
function xcard(item){
  const el=document.createElement("div"); el.className="xcard"; el.dataset.name=item.name+" "+(item.sub||"");
  el.innerHTML=`<canvas width="84" height="84" class="xmini"></canvas><div class="xc-b"><div class="xc-n" title="${esc(item.name)}">${esc(item.name)}</div><div class="xc-s">${esc(item.sub||"")}</div>
    <div class="xc-a"><button class="btn sm primary">Copy</button><button class="btn sm more" aria-label="More options" title="More options">⋯</button></div></div>`;
  drawX(el.querySelector("canvas"),item.preview,"range");
  el.querySelector(".primary").onclick=()=>copyText(item.code,`"${item.name}" — paste it in VALORANT's crosshair import.`);
  el.querySelector(".more").onclick=e=>{e.stopPropagation();openMenu(e.currentTarget,item);};
  return el;
}
function renderGallery(){
  if(!GALLERY) return;
  const accs=ACCOUNTS.map(a=>({a,v:VIEW[a.ref]})).filter(x=>x.v&&x.v.crosshair_code)
    .map(({a,v})=>({id:"acc-"+a.ref,name:fullId(a),sub:v.crosshair?v.crosshair.name:"",code:v.crosshair_code,kind:"account",preview:v.crosshair}));
  const fill=(id,items,empty)=>{const g=$(id);g.innerHTML="";if(!items.length){g.innerHTML=`<div class="xempty">${empty}</div>`;return;}items.forEach(i=>g.appendChild(xcard(i)));};
  fill("#x-accounts",accs,ACCOUNTS.length?"Reading your accounts…":"No accounts on this PC yet.");
  fill("#x-mine",GALLERY.mine.map(m=>({...m,sub:"Saved by you"})),"Nothing saved yet — paste a code above, or press ⋯ → Save on any crosshair.");
  fill("#x-presets",GALLERY.presets.map(p=>({...p,sub:p.style==="dot"?"Dot":p.style==="outline"?"Outline":"Cross"})),"");
  applyFilter();
}
function openMenu(btn,item){
  const m=$("#xmenu"), opts=[["Copy code",()=>copyText(item.code,`"${item.name}"`)],["Show code",()=>confirmBox(item.name,item.code,"Copy",()=>copyText(item.code,`"${item.name}"`))]];
  if(item.kind!=="mine") opts.push(["Save to my crosshairs",()=>saveCrosshair(item.kind==="account"?`${item.name} crosshair`:item.name,item.code)]);
  if(item.kind==="mine") opts.push(["Rename",()=>renameCrosshair(item)],["Delete",()=>deleteCrosshair(item)]);
  m.innerHTML=opts.map(([t],i)=>`<button data-i="${i}"${t==="Delete"?' class="bad"':""}>${esc(t)}</button>`).join("");
  m.querySelectorAll("button").forEach(b=>b.onclick=()=>{closeMenu();opts[+b.dataset.i][1]();});
  const r=btn.getBoundingClientRect(); m.classList.remove("hidden");
  const w=m.offsetWidth,h=m.offsetHeight; m.style.left=Math.max(8,Math.min(innerWidth-w-8,r.right-w))+"px";
  m.style.top=(r.bottom+6+h>innerHeight?r.top-h-6:r.bottom+6)+"px";
}
const closeMenu=()=>$("#xmenu").classList.add("hidden");
async function saveCrosshair(name,code){
  const r=await call("crosshair_add",name,code,[],""); if(!r.ok){toast(r.error||"Couldn't save it.",true);return false;}
  toast(`Saved "${name}" to your crosshairs.`); loadGallery(); return true;
}
function renameCrosshair(item){
  confirmBox("Rename crosshair","","Rename",()=>{const n=$("#c-input").value.trim(); if(!n) return;
    call("crosshair_update",item.id,n).then(r=>{if(!r.ok)toast(r.error||"Couldn't rename.",true);else loadGallery();});},item.name);
}
function deleteCrosshair(item){
  confirmBox(`Delete "${item.name}"?`,"Removes it from your saved crosshairs. Your accounts aren't affected.","Delete",async()=>{
    const r=await call("crosshair_delete",item.id); if(!r.ok){toast(r.error||"Couldn't delete.",true);return;} toast("Deleted."); loadGallery();});
}
let pasteTimer=null;
function pasteChanged(){
  clearTimeout(pasteTimer); pasteTimer=setTimeout(async()=>{
    const code=$("#p-code").value.trim(), msg=$("#p-msg"); if(!code){drawX($("#p-canvas"),null);$("#p-save").disabled=true;msg.classList.remove("bad");return;}
    const r=await call("crosshair_preview",code), x=r.ok?r.data:null; drawX($("#p-canvas"),x);
    $("#p-save").disabled=!x; msg.classList.toggle("bad",!x);
    if(!x) msg.textContent="That doesn't look like a VALORANT crosshair code. It starts with 0;P; or 0;s;"; else msg.textContent="Looks good — name it and press Save.";
  },180);
}
async function pasteSave(){ const code=$("#p-code").value.trim(), name=$("#p-name").value.trim()||"My crosshair";
  if(await saveCrosshair(name,code)){ $("#p-code").value="";$("#p-name").value="";pasteChanged(); } }

/* ---------------- apply: choose where to copy from ---------------- */
let onOk=null;
function confirmBox(title,sub,ok,fn,input){$("#c-title").textContent=title;$("#c-sub").textContent=sub;$("#c-ok").textContent=ok;onOk=fn;
  const i=$("#c-input"); i.classList.toggle("hidden",input==null); if(input!=null){i.value=input;setTimeout(()=>{i.focus();i.select();},60);}
  $("#modal").classList.add("show");}
const closeBox=()=>$("#modal").classList.remove("show");
let PICK=null, PICKFN=null;
function chooseSource(title,sub,exclude,okText,fn){
  const list=$("#s-list"), others=ACCOUNTS.filter(a=>a.ref!==exclude);
  const last=store.get("tune.src"); PICK=others.some(a=>a.ref===last)?last:null; PICKFN=fn;
  $("#s-title").textContent=title; $("#s-sub").textContent=sub; $("#s-ok").textContent=okText;
  list.innerHTML=others.map(a=>{const r=RANK[a.puuid]||{};return `<button class="pk${a.ref===PICK?" on":""}" data-ref="${a.ref}" style="--rk:${rankColor(r.rank)}">
      ${r.rank_icon?`<img class="emblem" src="${esc(r.rank_icon)}" alt="">`:'<span class="emblem ph"></span>'}
      <span class="pk-n">${esc(riotId(a).name)}<b>${esc(riotId(a).tag)}</b><i>${esc(r.rank||"")}</i></span><span class="pk-s">Sens <b>${esc(fmtSens(a.sens)??"—")}</b></span><span class="pk-r"></span></button>`;}).join("");
  list.querySelectorAll(".pk").forEach(b=>b.onclick=()=>{PICK=b.dataset.ref;list.querySelectorAll(".pk").forEach(o=>o.classList.toggle("on",o===b));$("#s-ok").disabled=false;});
  $("#s-ok").disabled=!PICK; $("#smodal").classList.add("show");
}
const closePick=()=>$("#smodal").classList.remove("show");
function applyClick(){
  const a=acc(SEL); if(!a) return;
  if(inGame(a)){toast("Quit VALORANT first — it's open on this account.",true);return;}
  chooseSource(`Copy settings to ${fullId(a)}`,"Which account's settings should this account get?",a.ref,"Apply",async src=>{
    const b=$("#apply");b.classList.add("busy");
    const r=await call("apply_from",src,a.ref);b.classList.remove("busy");
    if(!r.ok){toast(r.error||"Apply failed.",true);return;}
    const from=acc(src)?riotId(acc(src)).name:"that account";
    toast(r.data.video_note?`Applied & verified ✓ (from ${from}) — but ${r.data.video_note}.`
      :`Applied & verified ✓ ${r.data.changed} setting${r.data.changed===1?"":"s"} copied from ${from}. Now sign in.`,!!r.data.video_note);
    await refreshAccounts(); $("#signin").classList.add("ready"); loadSync(a.ref); loadView(a.ref);
  });
}
function copyAllClick(){
  if(ACCOUNTS.length<2) return;
  chooseSource("Copy one account to all","Pick the account whose settings every other account should get.",null,"Copy to all",src=>{
    const n=ACCOUNTS.length-1, from=acc(src)?fullId(acc(src)):"that account";
    confirmBox(`Copy ${from}'s settings to all ${n} other accounts?`,"Each account is backed up first and verified after. Accounts that already match are left alone, and the one VALORANT is open on (if any) is skipped.","Copy to all",async()=>{
      const b=$("#copy-all");b.disabled=true;b.textContent="Copying…";
      const r=await call("apply_all_from",src);b.disabled=false;b.textContent="Copy to all…";
      if(!r.ok){toast(r.error||"Copy failed.",true);return;}
      const d=r.data, parts=[`${d.applied} applied & verified ✓`]; if(d.same)parts.push(`${d.same} already matched`); if(d.skipped)parts.push(`${d.skipped} skipped`);
      const why=(d.results||[]).find(x=>x.status==="skipped");
      toast(parts.join(" · ")+(why?` — ${why.error}`:""),!!d.skipped);
      SYNC={}; VIEW={}; await refreshAccounts(); ACCOUNTS.forEach(x=>loadSync(x.ref)); if(SEL)loadView(SEL);
    });
  });
}

/* ---------------- sign in / switch ---------------- */
async function signIn(){const a=acc(SEL), n=a?fullId(a):"the account";
  if(!a) return;
  if(inGame(a)){toast(`You're already in VALORANT on ${n}.`);return;}
  if(SAVED[a.ref]){
    if(STATUS.game_running){toast("Quit VALORANT first — Tune never closes the game for you.",true);return;}
    confirmBox(`Switch to ${n}?`,"Tune closes Riot Client, signs in to this account with its remembered sign-in, and starts VALORANT.","Switch",async()=>{
      const b=$("#signin");b.classList.add("busy");const r=await call("switch_to",a.ref);b.classList.remove("busy");
      if(!r.ok){toast(r.error||"Couldn't switch.",true);return;}
      EXPECT=a.ref; toast(`Switching to ${n}… VALORANT is starting.`);});
    return;
  }
  $("#g-name").textContent=n; $("#g-title").textContent=`Set up one-click sign-in for ${n}`; $("#gmodal").classList.add("show");}
const closeGuide=()=>$("#gmodal").classList.remove("show");
async function openRiotFromGuide(){ closeGuide(); const r=await call("launch_riot");
  toast(r.ok?"Riot Client is opening.":(r.error||"Couldn't open Riot Client."),!r.ok); }
function restoreClick(){const a=acc(SEL);if(!a)return;
  confirmBox("Undo last apply?",`Puts ${riotId(a).name}'s settings files back exactly as they were before the last Apply. VALORANT can stay open unless it's signed in to this account.`,"Undo",async()=>{
    const r=await call("restore_backup",a.ref); if(!r.ok){toast(r.error||"Undo failed.",true);return;}
    toast("Restored."); await refreshAccounts(); loadSync(a.ref); loadView(a.ref);});}
async function loadStatus(){
  const r=await call("status"); if(!r.ok) return; const was=STATUS, old=JSON.stringify(STATUS); STATUS=r.data||{};
  if(was.game_running&&STATUS.game_running===false){ const a=ACCOUNTS.find(x=>x.ref===was.signed_in_ref);
    if(a&&KEY) call("rank",a.puuid,a.region,true).then(q=>{ if(q.ok&&q.data&&q.data.source!=="offline"){RANK[a.puuid]=q.data;paintRow(a);if(a.ref===SEL)paintDetail();} });
    refreshAccounts(); VIEW={}; if(SEL)loadView(SEL); }
  if(STATUS.game_running&&SAVED[STATUS.signed_in_ref]) call("keep_signin_fresh");
  if(EXPECT&&STATUS.game_running&&STATUS.signed_in_ref){ const want=acc(EXPECT);
    if(STATUS.signed_in_ref!==EXPECT&&want) toast(`Riot signed in to a different account than ${fullId(want)}. Its saved sign-in may have expired: sign in to it once and press Remember sign-in again.`,true);
    EXPECT=null; }
  if(JSON.stringify(STATUS)!==old){ACCOUNTS.forEach(paintRow); const a=acc(SEL); if(a){paintSync(a); loadSync(a.ref);}}
}
async function loadSaved(){const r=await call("signin_saved"); SAVED=r.ok&&r.data?r.data:{}; ACCOUNTS.forEach(paintRow); const a=acc(SEL); if(a)paintSync(a);}
function rememberClick(){const a=acc(SEL); if(!a) return;
  confirmBox(`Remember ${fullId(a)}'s sign-in?`,"Tune saves Riot Client's \"Stay signed in\" file for this account, encrypted so only your Windows user on this PC can use it. Your password is never seen. Then you can switch here in one click.","Remember",async()=>{
    const r=await call("remember_signin",a.ref); if(!r.ok){toast(r.error||"Couldn't remember the sign-in.",true);return;}
    toast(`${fullId(a)} remembered 🔑 — switch to it in one click from now on.`); loadSaved();});}
function forgetClick(){ const n=Object.keys(SAVED).length; if(!n){toast("No saved sign-ins.");return;}
  $("#hmodal").classList.remove("show");
  confirmBox(`Forget ${n} saved sign-in${n>1?"s":""}?`,"Deletes every remembered sign-in from this PC. Your accounts aren't affected; you'll just sign in normally again.","Forget",async()=>{
    const r=await call("forget_signins"); if(!r.ok){toast(r.error||"Couldn't delete them.",true);return;} toast("Saved sign-ins deleted."); loadSaved();});}

/* ---------------- help, about, updates ---------------- */
function openHelp(welcome){
  $("#h-title").textContent=welcome?"Welcome to Tune 👋":"Help & about";
  $("#h-sub").textContent=welcome?"Copy settings between your VALORANT accounts in three steps.":"Copy settings between your VALORANT accounts, switch accounts and keep your crosshairs.";
  $("#hmodal").classList.add("show");
}
const closeHelp=()=>{$("#hmodal").classList.remove("show");store.set("tune.welcomed","1");};
let UPD=null, SELFUPD=false;
async function checkUpdate(quiet){
  const r=await call("check_update");
  if(!r.ok){ if(!quiet) toast("Couldn't check for updates. Are you online?",true); return; }
  const d=r.data||{}; UPD=d; paintUpdateBtn();
  if(d.newer&&(!quiet||store.get("tune.later")!==d.latest)){$("#upd-t").textContent=`Tune ${d.latest} is out — you have ${d.current}.`;$("#updbar").classList.remove("hidden");}
  if(!quiet){ if(d.newer){$("#hmodal").classList.remove("show");toast(`Tune ${d.latest} is available — press Update now.`);} else toast(`You're on the latest version (${d.current}).`); }
}
function paintUpdateBtn(){
  const b=$("#btn-update"), n=!!(UPD&&UPD.newer);
  b.classList.toggle("new",n); $("#upd-dot").classList.toggle("hidden",!n);
  $("#upd-label").textContent=n?`Update to ${UPD.latest}`:"Update"; b.title=n?`Tune ${UPD.latest} is ready to install`:"Check for updates";
}
async function updateBtnClick(){
  if(UPD&&UPD.newer){updateClick();return;}
  const b=$("#btn-update"); b.classList.add("busy"); $("#upd-label").textContent="Checking…";
  await checkUpdate(false); b.classList.remove("busy"); paintUpdateBtn();
}
function updateClick(){
  if(!UPD||!UPD.newer) return;
  if(!SELFUPD){call("open_releases");return;}
  confirmBox(`Update to Tune ${UPD.latest}?`,"Tune downloads the new version from its GitHub page, checks it isn't damaged, then restarts itself. It takes about a minute. Your accounts, settings and backups stay as they are.",
    "Update now",async()=>{
      const r=await call("update_now"); if(!r.ok){toast(r.error||"Couldn't start the update.",true);return;}
      $("#upd-go").disabled=true; $("#upd-go").textContent="Updating…"; $("#updbar").classList.remove("hidden"); $("#btn-update").classList.add("busy"); $("#upd-label").textContent="Updating…"; $("#upd-later").classList.add("hidden"); $("#upd-prog").classList.remove("hidden"); pollUpdate();
    });
}
async function pollUpdate(){
  const r=await call("update_status"), s=r.ok?r.data:{stage:"error",error:"Lost contact with the updater."};
  if(s.stage==="downloading"){const p=s.total?Math.round(s.got/s.total*100):0;
    $("#upd-t").textContent=`Downloading Tune ${UPD.latest}… ${p}%`;$("#upd-fill").style.width=Math.max(3,p)+"%";setTimeout(pollUpdate,400);return;}
  if(s.stage==="installing"){$("#upd-t").textContent="Installing…";setTimeout(pollUpdate,400);return;}
  if(s.stage==="restarting"){$("#upd-t").textContent=`Installed ✓ Restarting Tune ${UPD.latest}…`;$("#upd-fill").style.width="100%";return;}
  if(s.stage==="error"){toast(s.error||"The update failed. Nothing was changed.",true);
    $("#upd-t").textContent=`Tune ${UPD.latest} is out — the update didn't finish.`;$("#upd-go").disabled=false;$("#upd-go").textContent="Try again";
    $("#upd-later").classList.remove("hidden");$("#upd-prog").classList.add("hidden");$("#btn-update").classList.remove("busy");paintUpdateBtn();}
}

/* ---------------- rank key ---------------- */
function openKey(){$("#kf-code").value="";$("#kf-err").textContent="";$("#kmodal").classList.add("show");$("#kf-code").focus();}
async function saveKey(){
  const key=$("#kf-code").value.trim(); if(key.length<8){$("#kf-err").textContent="Paste your key first.";return;}
  const r=await call("set_rank_key",key); if(!r.ok){$("#kf-err").textContent=r.error||"That key wasn't accepted.";return;}
  $("#kmodal").classList.remove("show"); toast("Key saved — loading ranks and stats…"); RANK={}; refresh();
}

/* ---------------- data ---------------- */
async function loadRanks(force){
  if(!KEY) return;
  await Promise.all(ACCOUNTS.map(async a=>{ if(RANK[a.puuid]&&!force) return;
    const r=await call("rank",a.puuid,a.region,!!force); const d=r.ok&&r.data&&r.data.source!=="offline"?r.data:{};
    RANK[a.puuid]=d; paintRow(a); if(a.ref===SEL) paintDetail(); if(VIEWNAME==="crosshairs") renderGallery();
    if((!d.rank||d.hs==null)&&!RETRIED[a.puuid]){RETRIED[a.puuid]=1;   // the free API sometimes times out: one quiet retry
      setTimeout(async()=>{const q=await call("rank",a.puuid,a.region);if(q.ok&&q.data&&q.data.source!=="offline"){RANK[a.puuid]=q.data;paintRow(a);if(a.ref===SEL)paintDetail();}},25000);} }));
}
async function refreshAccounts(){
  const a=await call("accounts"); if(a.ok)ACCOUNTS=a.data; ACCOUNTS.forEach(paintRow); if(SEL&&drawerOpen())paintDetail();
}
async function refresh(){
  const [a,k]=await Promise.all([call("accounts"),call("rank_key_status")]);
  if(!a.ok){$("#list").innerHTML=`<div class="empty">${esc(a.error||"Couldn't read your accounts.")}</div>`;return;}
  ACCOUNTS=a.data; KEY=!!(k.ok&&k.data&&k.data.set);
  $("#rankbar").classList.toggle("hidden",KEY);
  renderList(); if(!ACCOUNTS.length) return;
  const keep=store.get("tune.sel"); SEL=acc(SEL)?SEL:acc(keep)?keep:null;
  if(isWide()){ const first=SEL||(acc(STATUS.signed_in_ref)?STATUS.signed_in_ref:ACCOUNTS[0].ref); SEL=null; openAccount(first); }
  else if(drawerOpen()&&SEL){ paintDetail(); loadView(SEL); }
  ACCOUNTS.forEach(x=>loadSync(x.ref)); loadRanks(FORCE); FORCE=false; loadStatus(); loadSaved();
  if(VIEWNAME==="crosshairs") loadGallery();
}

function boot(){
  if(window.__booted)return; window.__booted=1;
  document.querySelectorAll(".tab").forEach(t=>t.onclick=()=>showView(t.dataset.view));
  $("#apply").onclick=applyClick; $("#signin").onclick=signIn; $("#restore").onclick=restoreClick; $("#copy-all").onclick=copyAllClick;
  $("#remember").onclick=rememberClick; $("#h-forget").onclick=forgetClick; $("#d-close").onclick=closeDrawer; $("#scrim").onclick=closeDrawer;
  $("#x-copy").onclick=()=>{const v=VIEW[SEL];if(v&&v.crosshair_code)copyText(v.crosshair_code,"crosshair code — paste it in VALORANT's crosshair import.");};
  $("#x-save").onclick=()=>{const a=acc(SEL),v=VIEW[SEL];if(a&&v&&v.crosshair_code)saveCrosshair(`${fullId(a)} crosshair`,v.crosshair_code);};
  $("#p-code").oninput=pasteChanged; $("#p-save").onclick=pasteSave; $("#p-name").onkeydown=e=>{if(e.key==="Enter"&&!$("#p-save").disabled)pasteSave();};
  document.querySelectorAll("[data-site]").forEach(b=>b.onclick=()=>call("open_site",b.dataset.site));
  $("#s-cancel").onclick=closePick; $("#smodal").onclick=e=>{if(e.target.id==="smodal")closePick();};
  $("#s-ok").onclick=()=>{if(!PICK)return;store.set("tune.src",PICK);closePick();const f=PICKFN;PICKFN=null;if(f)f(PICK);};
  $("#btn-help").onclick=()=>openHelp(false); $("#h-close").onclick=closeHelp; $("#hmodal").onclick=e=>{if(e.target.id==="hmodal")closeHelp();};
  $("#h-update").onclick=()=>checkUpdate(false); $("#upd-go").onclick=updateClick; $("#btn-update").onclick=updateBtnClick;
  $("#g-close").onclick=closeGuide; $("#g-open").onclick=openRiotFromGuide; $("#gmodal").onclick=e=>{if(e.target.id==="gmodal")closeGuide();};
  addEventListener("resize",()=>{ if(isWide()){ $("#scrim").classList.remove("show"); if(!SEL&&ACCOUNTS.length) openAccount(ACCOUNTS[0].ref); } });
  $("#upd-later").onclick=()=>{if(UPD)store.set("tune.later",UPD.latest);$("#updbar").classList.add("hidden");};
  call("can_self_update").then(r=>{SELFUPD=!!(r.ok&&r.data); if(!SELFUPD)$("#upd-go").textContent="Download";});
  setInterval(()=>{if(!document.hidden)checkUpdate(true);},6*3600*1000);   // a long session still hears about new versions
  $("#h-backups").onclick=async()=>{const r=await call("open_backups"); if(!r.ok)toast(r.error||"Couldn't open the folder.",true);};
  $("#d-id").onclick=()=>{const a=acc(SEL); if(!a||!RANK[a.puuid]||!RANK[a.puuid].name){toast("Riot ID isn't loaded yet.",true);return;} copyText(fullId(a),fullId(a));};
  $("#search").oninput=applyFilter;
  $("#fold").open=store.get("tune.fold")==="1"; $("#fold").ontoggle=()=>store.set("tune.fold",$("#fold").open?"1":"0");
  call("about").then(r=>{if(r.ok)$("#h-ver").textContent=`Tune ${r.data.version}`;});
  if(!store.get("tune.welcomed")) setTimeout(()=>openHelp(true),600);
  setTimeout(()=>checkUpdate(true),3000);
  document.querySelectorAll("#xbgs button").forEach(b=>{b.classList.toggle("on",b.dataset.bg===XB);
    b.onclick=()=>{XB=b.dataset.bg;store.set("tune.xbg",XB);document.querySelectorAll("#xbgs button").forEach(o=>o.classList.toggle("on",o===b));drawX($("#xcanvas"),$("#xcanvas")._x);};});
  $("#c-cancel").onclick=closeBox; $("#c-ok").onclick=()=>{closeBox(); if(onOk)onOk();};
  $("#c-input").onkeydown=e=>{if(e.key==="Enter")$("#c-ok").click();};
  $("#modal").onclick=e=>{if(e.target.id==="modal")closeBox();};
  $("#rank-connect").onclick=openKey; $("#btn-key").onclick=openKey; $("#k-get").onclick=()=>call("open_rank_help");
  $("#kf-cancel").onclick=()=>$("#kmodal").classList.remove("show"); $("#kf-save").onclick=saveKey;
  $("#kmodal").onclick=e=>{if(e.target.id==="kmodal")$("#kmodal").classList.remove("show");};
  $("#btn-refresh").onclick=()=>{SYNC={};VIEW={};RETRIED={};FORCE=true;refresh();toast("Getting fresh ranks and player cards… this takes about a minute.");};
  addEventListener("click",e=>{if(!e.target.closest("#xmenu"))closeMenu();});
  addEventListener("resize",closeMenu);
  addEventListener("keydown",e=>{
    const typing=/INPUT|TEXTAREA/.test((document.activeElement||{}).tagName||""), modal=document.querySelector(".modal-bg.show");
    if(e.key==="Escape"){ closeMenu();
      if(modal){closeBox();closePick();closeGuide();$("#kmodal").classList.remove("show");if($("#hmodal").classList.contains("show"))closeHelp();return;}
      if(document.activeElement===$("#search")){$("#search").value="";applyFilter();$("#search").blur();return;}
      if(!isWide()&&drawerOpen()){closeDrawer();return;} }
    if(typing||modal) return;
    if(e.key==="/"){e.preventDefault();$("#search").focus();}
    else if(e.key==="h"||e.key==="H"||e.key==="?") openHelp(false);
    else if(VIEWNAME!=="accounts") return;
    else if((e.key==="s"||e.key==="S")&&drawerOpen()) signIn();
    else if((e.key==="a"||e.key==="A")&&drawerOpen()&&!$("#apply").disabled) applyClick();
    else if(e.key==="Enter"&&SEL&&!drawerOpen()) openAccount(SEL);
    else if(["ArrowRight","ArrowLeft","ArrowDown","ArrowUp"].includes(e.key)){
      const vis=ACCOUNTS.filter(a=>{const el=document.querySelector(`.acc[data-ref="${a.ref}"]`);return el&&!el.classList.contains("hidden");}); if(!vis.length) return;
      const step=e.key==="ArrowRight"||e.key==="ArrowDown"?1:-1, i=vis.findIndex(a=>a.ref===SEL), n=vis[(i+step+vis.length)%vis.length];
      if(drawerOpen()) openAccount(n.ref); else {SEL=n.ref; document.querySelectorAll(".acc").forEach(t=>t.classList.toggle("sel",t.dataset.ref===SEL));}
      const el=document.querySelector(`.acc[data-ref="${n.ref}"]`); if(el)el.scrollIntoView({block:"nearest"});
      e.preventDefault(); }
  });
  addEventListener("pointermove",e=>{const s=$(".spot");s.style.setProperty("--x",e.clientX+"px");s.style.setProperty("--y",e.clientY+"px");});
  drawX($("#p-canvas"),null);
  showView(store.get("tune.view")==="crosshairs"?"crosshairs":"accounts");
  refresh(); setInterval(()=>{if(!document.hidden)loadStatus();},15000);
}
// Boot the REAL backend as soon as pywebview binds its api; never fall back to invented accounts.
function connecting(msg){ const g=$("#list"); if(g) g.innerHTML='<div class="empty">'+esc(msg)+'</div>'; }
function startup(){
  if(hasApi()||PREVIEW){ boot(); return; }
  connecting("Connecting to Tune…");
  window.addEventListener("pywebviewready",()=>{ if(!window.__booted) boot(); },{once:true});
  let n=0;
  const t=setInterval(()=>{
    if(hasApi()){ clearInterval(t); boot(); return; }
    if(++n>80){ clearInterval(t); if(!window.__booted) connecting("Couldn't reach Tune's engine. Close Tune completely and reopen it."); }
  },100);
}
startup();
