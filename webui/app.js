"use strict";
/* Tune front-end. Talks to the Python backend via window.pywebview.api when running in the app,
   and falls back to MOCK data so the same files render in a plain browser (preview / CI). */

const MOCK = {
  accounts: [
    {ref:"a",path:"A",account:"p1-eu",puuid:"p1",region:"eu",signed_in:true,saved:"daisy#EU1",
     last_saved:new Date(Date.now()-7200e3).toISOString(),hints:{resolution:"1920×1080",fps:"0",vsync:"Off"}},
    {ref:"b",path:"B",account:"p2-na",puuid:"p2",region:"na",signed_in:false,saved:null,
     last_saved:null,hints:{resolution:"2560×1440",fps:"240",vsync:"Off"}},
    {ref:"c",path:"C",account:"p3-eu",puuid:"p3",region:"eu",signed_in:false,saved:"kaya#EU2",
     last_saved:new Date(Date.now()-3*864e5).toISOString(),hints:{resolution:"1920×1080",fps:"0",vsync:"On"}}
  ],
  profiles:[{ref:"a",id:"profA",path:"profA",label:"daisy#EU1"},{ref:"c",id:"profC",path:"profC",label:"kaya#EU2"}],
  rank:{p1:{name:"daisy",tag:"EU1",rank:"Immortal 2",rr:42,source:"online"},
        p3:{name:"kaya",tag:"EU2",rank:"Platinum 1",rr:12,source:"online"}},
  crosshairs:[{id:"x1",name:"My main",code:"0;P;c;5;h;0;0l;4;0o;2;0a;1;d;1;z;2",tags:["Pros","clean"]},
              {id:"x2",name:"Fun dot",code:"0;P;c;6;d;1;z;3;a;1;0b;0",tags:["Fun"]}]
};
const BANNERS=["b0","b1","b2","b3"];
const hasApi=()=>!!(window.pywebview&&window.pywebview.api);

async function call(name,...args){
  if(hasApi()) return await window.pywebview.api[name](...args);
  if(name==="rank"){const d=MOCK.rank[args[0]]||{source:"offline"};return {ok:true,data:d};}
  if(name==="accounts")return {ok:true,data:MOCK.accounts};
  if(name==="profiles")return {ok:true,data:MOCK.profiles};
  if(name==="save")return {ok:true,data:{replaced:false,label:args[1]}};
  if(name==="apply")return {ok:true,data:{applied:3}};
  if(name==="launch_riot")return {ok:true,data:{launched:true}};
  if(name==="rank_key_status")return {ok:true,data:{set:false}};
  if(name==="set_rank_key")return {ok:true,data:{set:true}};
  if(name==="open_rank_help")return {ok:true,data:{opened:true}};
  if(name==="apply_to_all")return {ok:true,data:{targets:2,changed:2,results:[]}};
  if(name==="share_code")return {ok:true,data:'{"format":"presetdesk-share","version":1,"settings":{"sg.TextureQuality":"3"},"label":"daisy#EU1"}'};
  if(name==="share_import")return {ok:true,data:{label:"Shared preset",n:3}};
  if(name==="settings")return {ok:true,data:[{name:"View distance",value:"3"},{name:"Textures",value:"3"},{name:"Shadows",value:"2"},{name:"Anti-aliasing",value:"2"},{name:"VSync",value:"Off"},{name:"Frame-rate limit",value:"240"}]};
  if(name==="crosshairs")return {ok:true,data:MOCK.crosshairs};
  if(name==="crosshair_add"){const e={id:"x"+Date.now(),name:args[0],code:args[1],tags:args[2]||[]};MOCK.crosshairs.unshift(e);return {ok:true,data:e};}
  if(name==="crosshair_delete"){MOCK.crosshairs=MOCK.crosshairs.filter(c=>c.id!==args[0]);return {ok:true,data:true};}
  return {ok:false,error:"unavailable"};
}

const $=s=>document.querySelector(s);
const esc=s=>String(s==null?"":s).replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
function ago(iso){ if(!iso) return ""; const s=(Date.now()-new Date(iso))/1000;
  if(s<90)return"just now"; if(s<5400)return Math.round(s/60)+"m ago";
  if(s<86400)return Math.round(s/3600)+"h ago"; return Math.round(s/86400)+"d ago"; }

let toastTimer;
function toast(msg,bad){ const t=$("#toast"); t.textContent=msg; t.className="toast show"+(bad?" bad":"");
  clearTimeout(toastTimer); toastTimer=setTimeout(()=>t.className="toast",3200); }

let ACCOUNTS=[], PROFILES=[];
const profileFor=ref=>PROFILES.find(p=>p.ref===ref);

function render(){
  const grid=$("#grid"); grid.innerHTML="";
  const signed=ACCOUNTS.some(a=>a.signed_in);
  $("#sub").textContent=ACCOUNTS.length?`${ACCOUNTS.length} account${ACCOUNTS.length>1?"s":""} on this PC`:"Your accounts";
  if(!ACCOUNTS.length){grid.innerHTML='<div class="empty">No VALORANT accounts found yet. Sign in once, then add it.</div>';}
  ACCOUNTS.forEach((a,i)=>grid.appendChild(cardEl(a,i)));
  const add=document.createElement("div"); add.className="add"; add.innerHTML=
    '<div class="plus"><svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="M12 5v14M5 12h14"/></svg></div>'+
    '<div class="t">Add account</div><div class="s">'+(signed?"save the account you're signed into":"sign in to an account first")+'</div>';
  add.onclick=addAccount; grid.appendChild(add);
}

function cardEl(a,i){
  const el=document.createElement("div"); el.className="card"+(a.signed_in?" me":""); el.style.animationDelay=(i*0.05)+"s";
  const h=a.hints||{}, letter=(a.saved||a.account||"?").trim()[0].toUpperCase();
  const chips=[h.resolution&&`<div class="chip"><b>${esc(h.resolution)}</b></div>`,
               h.fps!=null&&`<div class="chip"><b>${esc(h.fps)}</b> fps</div>`,
               h.vsync&&`<div class="chip">VSync <b>${esc(h.vsync)}</b></div>`].filter(Boolean).join("");
  const canApply=!!profileFor(a.ref);
  el.innerHTML=
    `<div class="banner ${BANNERS[i%4]}">
       <div class="rr hidden"><div class="num">—</div><div class="lab">RR</div></div>
       <div class="rank hidden"><span class="dot"></span><span class="rank-t">Unranked</span></div>
       <div class="avatar">${esc(letter)}</div>
       ${a.signed_in?'<div class="me-dot"><i></i> signed in</div>':""}
     </div>
     <div class="body">
       <div class="name">${esc(a.saved||("Account "+a.puuid.slice(0,4)))}</div>
       <div class="hints">${chips||'<div class="chip">no settings read yet</div>'}</div>
       <div class="foot">
         <div class="saved">${a.last_saved?"Saved · "+ago(a.last_saved):"Not saved yet"}</div>
         <div class="acts">
           ${canApply?`<button class="mini-btn toall" title="Copy to all accounts"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3l9 5-9 5-9-5 9-5z"/><path d="M3 14l9 5 9-5"/></svg></button><button class="mini-btn share" title="Share preset"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><circle cx="6" cy="12" r="2.4"/><circle cx="18" cy="6" r="2.4"/><circle cx="18" cy="18" r="2.4"/><path d="M8 11l8-4M8 13l8 4"/></svg></button>`:""}
           <button class="apply${a.signed_in?"":" ghost"}" ${canApply?"":"disabled"}>Apply
             <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12h14M13 6l6 6-6 6"/></svg></button>
         </div>
       </div>
     </div>`;
  el.querySelector(".apply").onclick=()=>openApply(a);
  const toall=el.querySelector(".toall");if(toall)toall.onclick=()=>copyToAll(a);
  const sh=el.querySelector(".share");if(sh)sh.onclick=()=>sharePreset(a);
  if(a.puuid) loadRank(a,el);
  return el;
}

async function loadRank(a,el){
  const r=await call("rank",a.puuid,a.region); if(!r.ok||!r.data) return; const d=r.data;
  if(d.source==="offline") return;
  if(d.rr!=null){el.querySelector(".rr .num").textContent=d.rr;el.querySelector(".rr").classList.remove("hidden");}
  if(d.rank){el.querySelector(".rank-t").textContent=d.rank;el.querySelector(".rank").classList.remove("hidden");}
  if(d.card_url){const b=el.querySelector(".banner");b.style.backgroundImage=`linear-gradient(180deg,rgba(0,0,0,.12),rgba(0,0,0,.4)),url("${d.card_url}")`;b.style.backgroundSize="cover";b.style.backgroundPosition="center";}
  if(d.name&&d.tag&&!a.saved) el.querySelector(".name").innerHTML=esc(d.name)+'<b>#'+esc(d.tag)+'</b>';
}

function confirmModal(title,sub,okText,onOk){
  $("#m-title").textContent=title;$("#m-sub").textContent=sub;
  const list=$("#m-list");list.innerHTML="";
  const b=document.createElement("button");b.className="btn primary";b.textContent=okText;
  b.onclick=()=>{closeModal();onOk();};list.appendChild(b);
  $("#modal").classList.add("show");
}
function copyToAll(a){
  const prof=profileFor(a.ref);if(!prof){toast("Save this account first.",true);return;}
  const others=ACCOUNTS.filter(x=>x.ref!==a.ref).length;
  if(!others){toast("You need another account to copy onto.",true);return;}
  confirmModal("Copy to all accounts",`This copies ${prof.label}'s video settings onto every other account (${others}). The game must be closed; each account is backed up first.`,"Copy to all",async()=>{
    toast("Copying to all…");const r=await call("apply_to_all",prof.id);
    if(!r.ok){toast(r.error||"Couldn't copy.",true);return;}
    toast(`Copied to ${r.data.changed} account${r.data.changed===1?"":"s"} of ${r.data.targets}.`);refresh();
  });
}
async function sharePreset(a){
  const prof=profileFor(a.ref);if(!prof){toast("Save this account first.",true);return;}
  const r=await call("share_code",prof.id);
  if(!r.ok){toast(r.error||"Couldn't make a share code.",true);return;}
  copyText(r.data);toast("Preset code copied — send it to a friend. They open it with the Import button.");
}
async function checkRankKey(){
  const r=await call("rank_key_status");const set=r.ok&&r.data&&r.data.set;
  const bar=$("#rankbar");if(bar)bar.classList.toggle("hidden",!!set);
}
function openKey(){$("#kf-code").value="";$("#kf-err").textContent="";$("#kmodal").classList.add("show");$("#kf-code").focus();}
async function saveKey(){
  const key=$("#kf-code").value.trim();
  if(key.length<8){$("#kf-err").textContent="Paste your key first.";return;}
  const r=await call("set_rank_key",key);
  if(!r.ok){$("#kf-err").textContent=r.error||"That key wasn't accepted.";return;}
  $("#kmodal").classList.remove("show");$("#rankbar").classList.add("hidden");
  toast("Rank connected — loading your ranks…");refresh();
}
function openImport(){$("#if-code").value="";$("#if-err").textContent="";$("#imodal").classList.add("show");$("#if-code").focus();}
async function doImport(){
  const text=$("#if-code").value.trim();
  if(!text){$("#if-err").textContent="Paste a preset code first.";return;}
  const r=await call("share_import",text);
  if(!r.ok){$("#if-err").textContent=r.error||"That code is not valid.";return;}
  $("#imodal").classList.remove("show");toast(`Imported "${r.data.label}" (${r.data.n} settings) — find it under Accounts.`);refresh();
}
function openApply(source){
  const prof=profileFor(source.ref); if(!prof){toast("Save this account first, then you can copy its settings.",true);return;}
  const targets=ACCOUNTS.filter(a=>a.ref!==source.ref);
  if(!targets.length){toast("You need a second account to copy settings onto.",true);return;}
  $("#m-title").textContent=`Apply ${esc(prof.label)} →`;
  $("#m-sub").textContent="Pick the account to copy these video settings onto. The game must be closed.";
  const list=$("#m-list"); list.innerHTML="";
  targets.forEach(t=>{ const row=document.createElement("div"); row.className="m-row";
    row.innerHTML=`<div class="mini">${esc((t.saved||t.account||"?").trim()[0].toUpperCase())}</div>
      <div><div class="mn">${esc(t.saved||("Account "+t.puuid.slice(0,4)))}</div><div class="ms">${esc(t.account)}</div></div>`;
    row.onclick=()=>doApply(prof,t); list.appendChild(row); });
  $("#modal").classList.add("show");
}
const closeModal=()=>$("#modal").classList.remove("show");

async function doApply(prof,target){
  closeModal(); toast("Applying…");
  const r=await call("apply",prof.id,target.ref);
  if(!r.ok){toast(r.error||"Apply failed.",true);return;}
  const n=r.data&&r.data.applied;
  toast(n?`Applied ${n} video setting${n>1?"s":""} to ${target.saved||target.account}. Undo stays available.`:"Already matched — nothing changed.");
  await refresh();
}

async function addAccount(){
  const me=ACCOUNTS.find(a=>a.signed_in);
  if(!me){toast("Sign in to a VALORANT account first, then add it.",true);return;}
  let label=me.saved; // keep existing label on re-save
  if(!label){ const r=await call("rank",me.puuid,me.region); const d=r.ok&&r.data;
    label=(d&&d.name&&d.tag)?`${d.name}#${d.tag}`:("Account "+me.puuid.slice(0,4)); }
  toast("Saving…");
  const r=await call("save",me.ref,label);
  if(!r.ok){toast(r.error||"Save failed.",true);return;}
  toast(`${r.data&&r.data.replaced?"Updated":"Saved"} ${esc(label)}.`);
  await refresh();
}

async function refresh(){
  const [a,p]=await Promise.all([call("accounts"),call("profiles")]);
  if(a.ok)ACCOUNTS=a.data; if(p.ok)PROFILES=p.data; render(); checkRankKey();
}

/* ---------------- crosshair library ---------------- */
const XCOLORS={"0":"#FFFFFF","1":"#00FF00","2":"#ADFF2F","3":"#CCFF00","4":"#FFFF00","5":"#00FFFF","6":"#FF00C8","7":"#FF0000"};
function parseX(code){
  if(!code||code.indexOf(";")<0)return null;
  const keys={c:1,u:1,h:1,d:1,z:1,a:1,"0b":1,"0l":1,"0t":1,"0o":1,"0a":1};
  const t=code.trim().split(";"),kv={};
  for(let i=0;i<t.length-1;){ if(keys[t[i]]){kv[t[i]]=t[i+1];i+=2;} else i++; }
  const num=(v,lo,hi,d)=>{const n=parseFloat(v);return isNaN(n)?d:Math.max(lo,Math.min(hi,n));};
  let color=XCOLORS[kv.c]||"#00FFFF";
  if(kv.c==="8"&&/^[0-9A-Fa-f]{6,8}$/.test(kv.u||""))color="#"+kv.u.slice(0,6);
  return {color,dot:kv.d==="1",dotSize:num(kv.z,1,10,2),
    inner:(kv["0b"]||"1")!=="0",len:num(kv["0l"],0,20,4),th:num(kv["0t"],1,10,2),off:num(kv["0o"],0,20,2),op:num(kv["0a"],0,1,1)};
}
function drawX(cv,p){
  const ctx=cv.getContext("2d"),W=cv.width,H=cv.height,cx=W/2,cy=H/2;
  ctx.clearRect(0,0,W,H);ctx.fillStyle="#0b0b12";ctx.fillRect(0,0,W,H);
  if(!p)return;
  const s=W/26, th=Math.max(1,p.th*1.4), ln=p.len*s, off=p.off*s+th/2;
  ctx.fillStyle=p.color;ctx.globalAlpha=p.op;
  if(p.inner){
    ctx.fillRect(cx-th/2,cy-off-ln,th,ln);ctx.fillRect(cx-th/2,cy+off,th,ln);
    ctx.fillRect(cx-off-ln,cy-th/2,ln,th);ctx.fillRect(cx+off,cy-th/2,ln,th);
  }
  if(p.dot){ctx.beginPath();ctx.arc(cx,cy,Math.max(1,p.dotSize*1.3),0,7);ctx.fill();}
  ctx.globalAlpha=1;
}
function copyText(t){
  try{ if(navigator.clipboard&&navigator.clipboard.writeText){navigator.clipboard.writeText(t);return;} }catch(e){}
  const ta=document.createElement("textarea");ta.value=t;ta.style.position="fixed";ta.style.opacity="0";
  document.body.appendChild(ta);ta.select();try{document.execCommand("copy");}catch(e){}document.body.removeChild(ta);
}
function xcardEl(e){
  const el=document.createElement("div");el.className="card xcard";
  el.innerHTML=`<div class="xtop"><canvas width="92" height="92" class="xcanvas"></canvas>
    <div class="xmeta"><div class="xname">${esc(e.name)}</div>
      <div class="xtags">${(e.tags||[]).map(t=>`<span class="xtag">${esc(t)}</span>`).join("")}</div></div></div>
    <div class="xcode">${esc(e.code)}</div>
    <div class="foot"><button class="apply ghost xcopy">Copy code</button><button class="xdel" title="Delete">✕</button></div>`;
  drawX(el.querySelector(".xcanvas"),parseX(e.code));
  el.querySelector(".xcopy").onclick=()=>{copyText(e.code);toast("Crosshair code copied — paste it in VALORANT › Crosshair.");};
  el.querySelector(".xdel").onclick=async()=>{const r=await call("crosshair_delete",e.id);if(r.ok){toast("Crosshair deleted.");loadCrosshairs();}else toast(r.error||"Delete failed.",true);};
  return el;
}
async function loadCrosshairs(){
  const r=await call("crosshairs");const list=r.ok?r.data:[];
  const g=$("#xgrid");g.innerHTML="";
  list.forEach(e=>g.appendChild(xcardEl(e)));
  const add=document.createElement("div");add.className="add";add.style.minHeight="190px";
  add.innerHTML='<div class="plus"><svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="M12 5v14M5 12h14"/></svg></div><div class="t">Add crosshair</div><div class="s">paste a code from VALORANT</div>';
  add.onclick=openXAdd;g.appendChild(add);
}
function openXAdd(){
  $("#xf-name").value="";$("#xf-code").value="";$("#xf-tags").value="";$("#xf-err").textContent="";
  drawX($("#xprev"),null);$("#xmodal").classList.add("show");$("#xf-name").focus();
}
function xPreview(){drawX($("#xprev"),parseX($("#xf-code").value));}
async function xSave(){
  const name=$("#xf-name").value.trim(),code=$("#xf-code").value.trim();
  if(!name){$("#xf-err").textContent="Give it a name.";return;}
  if(!code||code.indexOf(";")<0){$("#xf-err").textContent="Paste a valid VALORANT crosshair code.";return;}
  const tags=$("#xf-tags").value.split(",").map(s=>s.trim()).filter(Boolean);
  const r=await call("crosshair_add",name,code,tags,"");
  if(!r.ok){$("#xf-err").textContent=r.error||"Could not save that code.";return;}
  $("#xmodal").classList.remove("show");toast("Crosshair saved.");loadCrosshairs();
}
async function loadSettings(){
  const g=$("#sgrid");g.innerHTML="";
  if(!ACCOUNTS.length){const r=await call("accounts");if(r.ok)ACCOUNTS=r.data;}
  const me=ACCOUNTS.find(a=>a.signed_in);
  if(!me){g.innerHTML='<div class="empty">Sign in to a VALORANT account to see its video settings.</div>';return;}
  const r=await call("settings",me.ref);const rows=r.ok?r.data:[];
  const card=document.createElement("div");card.className="scard";
  card.innerHTML=`<div class="shead"><div class="savatar">${esc((me.saved||me.account||"?").trim()[0].toUpperCase())}</div>
      <div><div class="sname">${esc(me.saved||("Account "+me.puuid.slice(0,4)))}</div><div class="ssub">current video settings · signed in</div></div></div>
    <div class="srows">${rows.map(x=>`<div class="srow"><span>${esc(x.name)}</span><b>${esc(x.value)}</b></div>`).join("")||'<div class="empty">No readable video settings in this file.</div>'}</div>
    <div class="sfoot"><button class="apply" id="s-save">Save these settings</button></div>`;
  g.appendChild(card);
  const b=card.querySelector("#s-save");if(b)b.onclick=addAccount;
}
function setView(v){
  document.querySelectorAll(".tab").forEach(t=>t.classList.toggle("active",t.dataset.view===v));
  ["accounts","settings","crosshairs"].forEach(k=>$("#view-"+k).classList.toggle("hidden",k!==v));
  if(v==="crosshairs")loadCrosshairs();
  if(v==="settings")loadSettings();
}

function boot(){
  if(window.__booted)return; window.__booted=1;
  document.querySelectorAll(".tab").forEach(t=>t.onclick=()=>setView(t.dataset.view));
  $("#xf-cancel").onclick=()=>$("#xmodal").classList.remove("show");
  $("#xmodal").onclick=e=>{if(e.target.id==="xmodal")$("#xmodal").classList.remove("show");};
  $("#xf-code").addEventListener("input",xPreview);
  $("#xf-save").onclick=xSave;
  $("#btn-import").onclick=openImport;
  $("#if-cancel").onclick=()=>$("#imodal").classList.remove("show");
  $("#imodal").onclick=e=>{if(e.target.id==="imodal")$("#imodal").classList.remove("show");};
  $("#if-save").onclick=doImport;
  $("#rank-connect").onclick=openKey;
  $("#k-get").onclick=()=>call("open_rank_help");
  $("#kf-cancel").onclick=()=>$("#kmodal").classList.remove("show");
  $("#kmodal").onclick=e=>{if(e.target.id==="kmodal")$("#kmodal").classList.remove("show");};
  $("#kf-save").onclick=saveKey;
  $("#btn-add").onclick=addAccount;
  $("#btn-switch").onclick=async()=>{const r=await call("launch_riot");
    toast(r.ok?"Opening Riot Client. Sign in there, then switch back — Tune will see the account.":(r.error||"Couldn't open Riot Client."),!r.ok);};
  $("#m-cancel").onclick=closeModal; $("#modal").onclick=e=>{if(e.target.id==="modal")closeModal();};
  addEventListener("pointermove",e=>{const s=$(".spot");s.style.setProperty("--x",e.clientX+"px");s.style.setProperty("--y",e.clientY+"px");});
  refresh();
}
// Boot the REAL backend as soon as pywebview binds its api. Never fall back to demo data while a
// pywebview bridge exists - the handshake can take a few seconds on a real PC, so we wait for it.
function tryBoot(){ if(window.__booted) return true; if(hasApi()){ boot(); return true; } return false; }
window.addEventListener("pywebviewready",tryBoot,{once:true});
if(!tryBoot()){
  let n=0;
  const t=setInterval(()=>{
    if(tryBoot()||++n>60){ clearInterval(t);
      if(!window.__booted && !window.pywebview) boot(); // only here: a plain browser with no bridge (preview)
    }
  },120);
}
