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
  profiles:[{ref:"a",path:"profA",label:"daisy#EU1"},{ref:"c",path:"profC",label:"kaya#EU2"}],
  rank:{p1:{name:"daisy",tag:"EU1",rank:"Immortal 2",rr:42,source:"online"},
        p3:{name:"kaya",tag:"EU2",rank:"Platinum 1",rr:12,source:"online"}}
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
       <div class="rr"><div class="num">—</div><div class="lab">RR</div></div>
       <div class="rank"><span class="dot"></span><span class="rank-t">Unranked</span></div>
       <div class="avatar">${esc(letter)}</div>
       ${a.signed_in?'<div class="me-dot"><i></i> signed in</div>':""}
     </div>
     <div class="body">
       <div class="name">${esc(a.saved||("Account "+a.puuid.slice(0,4)))}</div>
       <div class="hints">${chips||'<div class="chip">no settings read yet</div>'}</div>
       <div class="foot">
         <div class="saved">${a.last_saved?"Saved · "+ago(a.last_saved):"Not saved yet"}</div>
         <button class="apply${a.signed_in?"":" ghost"}" ${canApply?"":"disabled"}>Apply
           <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12h14M13 6l6 6-6 6"/></svg></button>
       </div>
     </div>`;
  el.querySelector(".apply").onclick=()=>openApply(a);
  if(a.puuid) loadRank(a,el);
  return el;
}

async function loadRank(a,el){
  const r=await call("rank",a.puuid,a.region); if(!r.ok||!r.data) return; const d=r.data;
  if(d.source==="offline") return;
  if(d.rr!=null) el.querySelector(".rr .num").textContent=d.rr;
  if(d.rank) el.querySelector(".rank-t").textContent=d.rank;
  if(d.name&&d.tag&&!a.saved) el.querySelector(".name").innerHTML=esc(d.name)+'<b>#'+esc(d.tag)+'</b>';
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
  const r=await call("apply",prof.path,target.path);
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
  const r=await call("save",me.path,label);
  if(!r.ok){toast(r.error||"Save failed.",true);return;}
  toast(`${r.data&&r.data.replaced?"Updated":"Saved"} ${esc(label)}.`);
  await refresh();
}

async function refresh(){
  const [a,p]=await Promise.all([call("accounts"),call("profiles")]);
  if(a.ok)ACCOUNTS=a.data; if(p.ok)PROFILES=p.data; render();
}

function boot(){
  if(window.__booted)return; window.__booted=1;
  $("#btn-add").onclick=addAccount;
  $("#btn-switch").onclick=async()=>{const r=await call("launch_riot");
    toast(r.ok?"Opening Riot Client. Sign in there, then switch back — Tune will see the account.":(r.error||"Couldn't open Riot Client."),!r.ok);};
  $("#m-cancel").onclick=closeModal; $("#modal").onclick=e=>{if(e.target.id==="modal")closeModal();};
  addEventListener("pointermove",e=>{const s=$(".spot");s.style.setProperty("--x",e.clientX+"px");s.style.setProperty("--y",e.clientY+"px");});
  refresh();
}
if(hasApi())boot(); else window.addEventListener("pywebviewready",boot,{once:true});
setTimeout(boot,300); // browser-preview fallback when pywebviewready never fires
