"use strict";
/* Tune front-end - one page. Left: your registered accounts. Right: the selected account's rank,
   stats, the shared settings from your MAIN account, and its crosshair. Talks to Python through
   window.pywebview.api. Nothing is ever invented: missing data shows "Unavailable". The tiny PREVIEW
   mock exists only for ?preview=1 design checks in a plain browser - the real app never uses it. */

const hasApi=()=>!!(window.pywebview&&window.pywebview.api);
const PREVIEW=/[?&]preview=1/.test(location.search);
const PMOCK={accounts:[{ref:"a",account:"p1-eu",puuid:"p1",region:"eu",signed_in:true,sens:0.4,is_master:true},
                       {ref:"b",account:"p2-eu",puuid:"p2",region:"eu",signed_in:false,sens:0.5,is_master:false}],
  master:{ref:"a",sens:0.4,ads:1,game_settings:60,resolution:"1920×1080",video:[{key:"sg.TextureQuality",name:"Textures",value:"3"}],
          crosshair:{name:"Preview",color:"#00ffff",outline:true,outline_thickness:1,outline_opacity:.5,dot:false,dot_size:2,dot_opacity:1,
                     inner:{show:true,thickness:2,length:4,vlength:4,offset:2,opacity:1},outer:{show:false}}}};
async function call(name,...args){
  if(hasApi()) return await window.pywebview.api[name](...args);
  if(!PREVIEW) return {ok:false,error:"Tune engine not connected yet."};
  if(name==="accounts")return {ok:true,data:PMOCK.accounts};
  if(name==="master")return {ok:true,data:PMOCK.master};
  if(name==="account_view")return {ok:true,data:args[0]==="a"?PMOCK.master:{...PMOCK.master,ref:"b",sens:0.5,video:[{key:"sg.TextureQuality",name:"Textures",value:"0"}]}};
  if(name==="sync_report")return {ok:true,data:args[0]==="a"?{master:true,in_sync:true}:{master:false,in_sync:false,differ:12,total:72}};
  if(name==="rank_key_status")return {ok:true,data:{set:false}};
  if(name==="status")return {ok:true,data:{game_running:true,signed_in_ref:"a"}};
  if(name==="apply_master_all")return {ok:true,data:{applied:1,same:0,skipped:0,results:[]}};
  return {ok:true,data:{source:"offline"}};
}

const $=s=>document.querySelector(s);
const esc=s=>String(s==null?"":s).replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const fmtSens=v=>v==null?null:String(Math.round(v*1000)/1000);
function ago(iso){ if(!iso) return ""; const s=(Date.now()-new Date(iso))/1000;
  if(s<90)return"just now"; if(s<5400)return Math.round(s/60)+"m ago";
  if(s<86400)return Math.round(s/3600)+"h ago"; return Math.round(s/86400)+"d ago"; }
let toastTimer;
function toast(msg,bad){ const t=$("#toast"); t.textContent=msg; t.className="toast show"+(bad?" bad":"");
  clearTimeout(toastTimer); toastTimer=setTimeout(()=>t.className="toast",3600); }

let ACCOUNTS=[], MASTER=null, RANK={}, SYNC={}, VIEW={}, STATUS={}, SEL=null, KEY=false, RETRIED={};
const store={get(k){try{return localStorage.getItem(k)}catch(e){return null}},set(k,v){try{localStorage.setItem(k,v)}catch(e){}}};
const acc=ref=>ACCOUNTS.find(a=>a.ref===ref);
const masterAcc=()=>ACCOUNTS.find(a=>a.is_master);
function riotId(a){const r=RANK[a.puuid];return r&&r.name?{name:r.name,tag:r.tag?"#"+r.tag:""}:{name:"Account "+a.puuid.slice(0,4),tag:""};}
const wide=u=>u?u.replace("largeart.png","wideart.png"):null;
const inGame=a=>!!(a&&STATUS.game_running&&STATUS.signed_in_ref===a.ref);
const lastUsed=a=>!!(a&&STATUS.signed_in_ref===a.ref);
const fullId=a=>{const i=riotId(a);return i.name+i.tag;};

/* ---------------- account list ---------------- */
function renderList(){
  const list=$("#list"); list.innerHTML="";
  $("#sub").textContent=ACCOUNTS.length?`${ACCOUNTS.length} account${ACCOUNTS.length>1?"s":""} on this PC`:"Your accounts";
  if(!ACCOUNTS.length){
    list.innerHTML='<div class="empty">No VALORANT accounts on this PC yet.<br>Sign in once in VALORANT and the account appears here.<br><button class="btn primary" id="e-signin">Open Riot Client</button></div>';
    $("#e-signin").onclick=signIn; $("#detail").classList.add("hidden"); return;
  }
  ACCOUNTS.forEach((a,i)=>{const el=document.createElement("div");el.className="acc";el.dataset.ref=a.ref;
    el.style.animationDelay=(i*0.04)+"s";el.onclick=()=>select(a.ref);list.appendChild(el);paintRow(a);});
}
function paintRow(a){
  const el=document.querySelector(`.acc[data-ref="${a.ref}"]`); if(!el) return;
  const r=RANK[a.puuid], id=riotId(a), s=SYNC[a.ref];
  const msens=MASTER&&MASTER.sens, same=a.is_master||(a.sens!=null&&msens!=null&&Math.abs(a.sens-msens)<1e-4);
  const dot=a.is_master?"ok":s?(s.in_sync?"ok":"warn"):"";
  el.classList.toggle("sel",a.ref===SEL);
  el.style.setProperty("--art",r&&r.card_url?`url("${wide(r.card_url)}")`:"none");
  const loading=KEY&&!r;
  el.innerHTML=`<div class="who"><div class="nm">${esc(id.name)}<b>${esc(id.tag)}</b>${a.is_master?'<span class="pill main">MAIN</span>':""}${inGame(a)?'<span class="pill live">IN GAME</span>':lastUsed(a)?'<span class="pill last">LAST USED</span>':""}</div>
      <div class="mini"><span title="${same?"Matches your main":"Differs from your main"}"><span class="sdot ${dot}" style="display:inline-block;margin-right:5px"></span>Sens <b>${esc(fmtSens(a.sens)??"—")}</b></span>
      <span>HS <b>${r&&r.hs!=null?r.hs+"%":loading?"…":"—"}</b></span><span>WR <b>${r&&r.wr!=null?r.wr+"%":loading?"…":"—"}</b></span></div></div>
    <div class="rkbox"><div class="rkn">${r&&r.rank?esc(r.rank):loading?"…":"Unavailable"}</div>${r&&r.rank_icon?`<img class="emblem" src="${esc(r.rank_icon)}" alt="">`:""}</div>`;
}

/* ---------------- detail ---------------- */
function select(ref){
  if(!acc(ref)) return; const changed=SEL!==ref; SEL=ref; store.set("tune.sel",ref);
  document.querySelectorAll(".acc").forEach(e=>e.classList.toggle("sel",e.dataset.ref===ref));
  const d=$("#detail"); d.classList.remove("hidden");
  if(changed){d.classList.remove("swap");void d.offsetWidth;d.classList.add("swap");$("#signin").classList.remove("ready");}
  paintDetail(); loadSync(ref); loadView(ref);
}
function stat(id,value,note){const v=$("#"+id);v.textContent=value??"Unavailable";v.classList.toggle("na",value==null);$("#"+id+"-n").textContent=note||"";}
function paintDetail(){
  const a=acc(SEL); if(!a) return; const r=RANK[a.puuid]||{}, id=riotId(a);
  $("#d-name").textContent=id.name; $("#d-tag").textContent=id.tag; $("#d-main").classList.toggle("hidden",!a.is_master);
  $("#hero-art").style.backgroundImage=r.card_url?`url("${wide(r.card_url)}")`:"none";
  $("#d-rank").textContent=r.rank||(KEY&&!RANK[a.puuid]?"Loading…":"Unavailable");
  const sub=[r.rr!=null&&r.rank&&r.rank!=="Unrated"?r.rr+" RR":null,r.peak?"Peak "+r.peak:null].filter(Boolean).join(" · ");
  $("#d-rksub").textContent=sub||(!KEY?"Connect the free key to see rank":"");
  const em=$("#d-emblem"); if(r.rank_icon){em.src=r.rank_icon;em.classList.remove("hidden");}else em.classList.add("hidden");
  const v=VIEW[a.ref], ms=MASTER&&MASTER.sens, mine=v?v.sens:a.sens;
  const diff=!a.is_master&&mine!=null&&ms!=null&&Math.abs(mine-ms)>1e-4;
  stat("d-sens",fmtSens(mine),mine==null?"No saved sensitivity on this PC":diff?`main uses ${fmtSens(ms)}`:(v&&v.ads!=null?`ADS ${fmtSens(v.ads)}`:""));
  stat("d-hs",r.hs!=null?r.hs+"%":null,r.hs!=null?`last ${r.hs_matches} competitive match${r.hs_matches===1?"":"es"}`:"");
  stat("d-wr",r.wr!=null?r.wr+"%":null,r.wr!=null?`${r.wins}W · ${r.games} games this act`:"");
  paintMaster(a); paintSync(a);
}
function paintMaster(a){
  const m=MASTER, v=VIEW[a.ref], rows=$("#m-rows"), ma=masterAcc(), main=ma?riotId(ma).name+riotId(ma).tag:null;
  $("#m-from").textContent=a.is_master?"Your main account — every other account copies these"
    :main?`Apply copies ${main}'s settings onto this account`:"Pick a main account";
  $("#set-main").classList.toggle("hidden",!!a.is_master);
  if(!v){rows.innerHTML='<div class="row"><span>Reading this account…</span><b>—</b></div>';drawX(null);$("#x-name").textContent="—";return;}
  const mv={}; (m&&m.video||[]).forEach(x=>mv[x.key]=x.value);
  const keep=(v.video||[]).filter(x=>x.key!=="bUseVSync"&&x.key!=="FrameRateLimit");
  const cmp=!a.is_master&&m&&m.ref;
  rows.innerHTML=[["Sensitivity",fmtSens(v.sens),1,cmp&&fmtSens(m.sens)],["Scoped / ADS",fmtSens(v.ads),1,cmp&&fmtSens(m.ads)],
    ["Resolution",v.resolution,0,cmp&&m.resolution],...keep.map(x=>[x.name,x.value,0,cmp&&mv[x.key]]),...(keep.length?[]:[["Video settings","Not saved yet"]]),["Game settings",`${v.game_settings} saved`]]
    .map(([k,val,key,main])=>{const d=main!=null&&main!==false&&String(main)!==String(val??"");
      return `<div class="row${key?" key":""}${d?" diff":""}"><span>${esc(k)}</span><b>${esc(val??"Not saved")}${d?`<i>main ${esc(main)}</i>`:""}</b></div>`;}).join("");
  $("#x-name").textContent=v.crosshair?v.crosshair.name:"No crosshair saved on this PC"; drawX(v.crosshair);
}
async function loadView(ref){
  const r=await call("account_view",ref); if(r.ok){VIEW[ref]=r.data; if(ref===SEL)paintDetail();}
}
function paintSteps(a){
  const el=$("#steps"), s=SYNC[a.ref]; el.classList.toggle("hidden",!!a.is_master); if(a.is_master) return;
  const done1=!!(s&&s.in_sync), done2=done1&&lastUsed(a)&&!!s.applied_at;
  const st=[["Apply settings",done1],[`Sign in as ${fullId(a)}`,done2],["Play",false]];
  const cur=st.findIndex(x=>!x[1]);
  el.innerHTML=st.map(([t,d],i)=>`<div class="step${d?" done":""}${i===cur?" now":""}"><span>${d?"✓":i+1}</span>${esc(t)}</div>`).join("");
}
function paintSync(a){
  const s=SYNC[a.ref], box=$("#sync"), t=$("#sync-t"), ap=$("#apply"), rs=$("#restore"), blocked=inGame(a)&&!a.is_master;
  box.className="sync"; ap.disabled=!!a.is_master||!MASTER||!MASTER.ref||blocked; rs.classList.toggle("hidden",!(s&&s.has_backup));
  $("#apply-t").textContent=a.is_master?"Main account":blocked?"Quit VALORANT to apply":s&&s.in_sync?"Apply again":"Apply settings";
  paintSteps(a);
  if(a.is_master){box.classList.add("ok");t.textContent="This is your main account — every other account copies these settings.";return;}
  if(blocked){box.classList.add("warn");t.textContent="VALORANT is open on this account right now, so it would undo any change when it closes. Quit VALORANT first.";return;}
  if(!s){t.textContent="Checking…";return;}
  if(s.in_sync){box.classList.add("ok");t.textContent="Matches your main"+(s.applied_at?` · applied & verified ${ago(s.applied_at)}`:"");return;}
  box.classList.add("warn");
  t.textContent=s.applied_at?`${s.differ} setting${s.differ===1?"":"s"} changed since you applied (${ago(s.applied_at)}) — Riot may have restored its cloud copy. Apply again.`
                            :`${s.differ} of ${s.total} settings differ from your main.`;
}
async function loadSync(ref){
  const r=await call("sync_report",ref); if(r.ok){SYNC[ref]=r.data; const a=acc(ref); if(a){paintRow(a); if(ref===SEL)paintSync(a);}}
}

/* ---------------- crosshair preview (from the main account's active profile) ---------------- */
function drawX(x){
  const cv=$("#xcanvas"),ctx=cv.getContext("2d"),W=cv.width,H=cv.height,cx=Math.round(W/2),cy=Math.round(H/2),u=4;
  const g=ctx.createLinearGradient(0,0,0,H);g.addColorStop(0,"#5b6470");g.addColorStop(1,"#2a2f36");
  ctx.fillStyle=g;ctx.fillRect(0,0,W,H); if(!x) return;
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

/* ---------------- actions ---------------- */
let onOk=null;
function confirmBox(title,sub,ok,fn){$("#c-title").textContent=title;$("#c-sub").textContent=sub;$("#c-ok").textContent=ok;onOk=fn;$("#modal").classList.add("show");}
const closeBox=()=>$("#modal").classList.remove("show");
function applyClick(){
  const a=acc(SEL), ma=masterAcc(); if(!a||!ma||a.is_master) return;
  confirmBox(`Apply settings to ${riotId(a).name}?`,
    `Copies ${riotId(ma).name}'s sensitivity, crosshair, video and game settings onto this account, then reads the files back to verify.\nVALORANT can stay open, as long as it isn't signed in to this account. This account is backed up first, so you can undo.`,
    "Apply settings",async()=>{
      const b=$("#apply");b.classList.add("busy");
      const r=await call("apply_master",a.ref);b.classList.remove("busy");
      if(!r.ok){toast(r.error||"Apply failed.",true);return;}
      toast(r.data.video_note?`Game settings applied & verified ✓ — video settings skipped: ${r.data.video_note}`
        :`Applied & verified ✓ ${r.data.changed} setting${r.data.changed===1?"":"s"} updated. Now sign in.`,!!r.data.video_note);
      await refreshAccounts(); $("#signin").classList.add("ready"); loadSync(a.ref); loadView(a.ref);
    });
}
async function signIn(){const a=acc(SEL), n=a?fullId(a):"the account";
  if(inGame(a)){toast(`You're already in VALORANT on ${n}.`);return;}
  const r=await call("launch_riot");
  toast(r.ok?`Riot Client is opening. If it's on another account, sign out there and sign in as ${n}.`:(r.error||"Couldn't open Riot Client."),!r.ok);}
function restoreClick(){const a=acc(SEL);if(!a)return;
  confirmBox("Undo last apply?",`Puts ${riotId(a).name}'s settings files back exactly as they were before the last Apply. VALORANT can stay open unless it's signed in to this account.`,"Undo",async()=>{
    const r=await call("restore_backup",a.ref); if(!r.ok){toast(r.error||"Undo failed.",true);return;}
    toast("Restored."); await refreshAccounts(); loadSync(a.ref); loadView(a.ref);});}
function setMainClick(){const a=acc(SEL);if(!a)return;
  confirmBox(`Make ${riotId(a).name} your main?`,"Every other account will copy this account's settings when you press Apply. Nothing is changed until you apply.","Make main",async()=>{
    const r=await call("set_master",a.ref); if(!r.ok){toast(r.error||"Couldn't change main.",true);return;}
    toast(`${riotId(a).name} is now your main.`); SYNC={}; VIEW={}; await refresh();});}

function applyAllClick(){
  const ma=masterAcc(); if(!ma){toast("Pick a main account first.",true);return;}
  const others=ACCOUNTS.filter(a=>!a.is_master).length;
  confirmBox(`Apply ${fullId(ma)}'s settings to all ${others} other accounts?`,
    "Each account is backed up first and verified after. Accounts that already match are left alone, and the one VALORANT is open on (if any) is skipped.",
    "Apply to all",async()=>{
      const b=$("#apply-all");b.disabled=true;b.textContent="Applying…";
      const r=await call("apply_master_all");b.disabled=false;b.textContent="Apply to all";
      if(!r.ok){toast(r.error||"Apply failed.",true);return;}
      const d=r.data, parts=[`${d.applied} applied & verified ✓`]; if(d.same)parts.push(`${d.same} already matched`); if(d.skipped)parts.push(`${d.skipped} skipped`);
      const why=(d.results||[]).find(x=>x.status==="skipped");
      toast(parts.join(" · ")+(why?` — ${why.error}`:""),!!d.skipped);
      SYNC={}; VIEW={}; await refreshAccounts(); ACCOUNTS.forEach(x=>loadSync(x.ref)); if(SEL)loadView(SEL);
    });
}
async function loadStatus(){
  const r=await call("status"); if(!r.ok) return; const old=JSON.stringify(STATUS); STATUS=r.data||{};
  if(JSON.stringify(STATUS)!==old){ACCOUNTS.forEach(paintRow); const a=acc(SEL); if(a){paintSync(a); loadSync(a.ref);}}
}

/* ---------------- rank key ---------------- */
function openKey(){$("#kf-code").value="";$("#kf-err").textContent="";$("#kmodal").classList.add("show");$("#kf-code").focus();}
async function saveKey(){
  const key=$("#kf-code").value.trim(); if(key.length<8){$("#kf-err").textContent="Paste your key first.";return;}
  const r=await call("set_rank_key",key); if(!r.ok){$("#kf-err").textContent=r.error||"That key wasn't accepted.";return;}
  $("#kmodal").classList.remove("show"); toast("Key saved — loading ranks and stats…"); RANK={}; refresh();
}

/* ---------------- data ---------------- */
async function loadRanks(){
  if(!KEY) return;
  await Promise.all(ACCOUNTS.map(async a=>{ if(RANK[a.puuid]) return;
    const r=await call("rank",a.puuid,a.region); const d=r.ok&&r.data&&r.data.source!=="offline"?r.data:{};
    RANK[a.puuid]=d; paintRow(a); if(a.ref===SEL) paintDetail();
    if((!d.rank||d.hs==null)&&!RETRIED[a.puuid]){RETRIED[a.puuid]=1;   // the free API sometimes times out: one quiet retry
      setTimeout(async()=>{const q=await call("rank",a.puuid,a.region);if(q.ok&&q.data&&q.data.source!=="offline"){RANK[a.puuid]=q.data;paintRow(a);if(a.ref===SEL)paintDetail();}},25000);} }));
}
async function refreshAccounts(){
  const [a,m]=await Promise.all([call("accounts"),call("master")]);
  if(a.ok)ACCOUNTS=a.data; if(m.ok)MASTER=m.data; ACCOUNTS.forEach(paintRow); if(SEL)paintDetail();
}
async function refresh(){
  const [a,m,k]=await Promise.all([call("accounts"),call("master"),call("rank_key_status")]);
  if(!a.ok){$("#list").innerHTML=`<div class="empty">${esc(a.error||"Couldn't read your accounts.")}</div>`;return;}
  ACCOUNTS=a.data; MASTER=m.ok?m.data:null; KEY=!!(k.ok&&k.data&&k.data.set);
  $("#rankbar").classList.toggle("hidden",KEY);
  renderList(); if(!ACCOUNTS.length) return;
  const keep=store.get("tune.sel"); const first=acc(SEL)||acc(keep)||masterAcc()||ACCOUNTS[0]; SEL=null; select(first.ref);
  ACCOUNTS.forEach(x=>loadSync(x.ref)); loadRanks(); loadStatus();
}

function boot(){
  if(window.__booted)return; window.__booted=1;
  $("#apply").onclick=applyClick; $("#signin").onclick=signIn; $("#restore").onclick=restoreClick; $("#set-main").onclick=setMainClick; $("#apply-all").onclick=applyAllClick;
  $("#c-cancel").onclick=closeBox; $("#c-ok").onclick=()=>{closeBox(); if(onOk)onOk();};
  $("#modal").onclick=e=>{if(e.target.id==="modal")closeBox();};
  $("#rank-connect").onclick=openKey; $("#btn-key").onclick=openKey; $("#k-get").onclick=()=>call("open_rank_help");
  $("#kf-cancel").onclick=()=>$("#kmodal").classList.remove("show"); $("#kf-save").onclick=saveKey;
  $("#kmodal").onclick=e=>{if(e.target.id==="kmodal")$("#kmodal").classList.remove("show");};
  $("#btn-refresh").onclick=()=>{RANK={};SYNC={};RETRIED={};refresh();toast("Refreshing…");};
  addEventListener("keydown",e=>{ if(e.key==="Escape"){closeBox();$("#kmodal").classList.remove("show");}
    if((e.key==="ArrowDown"||e.key==="ArrowUp")&&SEL&&!document.querySelector(".modal-bg.show")){
      const i=ACCOUNTS.findIndex(a=>a.ref===SEL),n=ACCOUNTS[(i+(e.key==="ArrowDown"?1:-1)+ACCOUNTS.length)%ACCOUNTS.length];select(n.ref);e.preventDefault();}});
  addEventListener("pointermove",e=>{const s=$(".spot");s.style.setProperty("--x",e.clientX+"px");s.style.setProperty("--y",e.clientY+"px");});
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
