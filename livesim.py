r"""
volare_thermal.livesim
======================

Writes a self-contained HTML file that runs the ACTUAL physics in the browser:
the same electro-thermal pack model, the same hull resistance, the same
propeller, the same 25 kW cap.  Not a replay -- you drive it.

Verified in webexport.verify_scheme() to within 0.10 K RMS of the implicit
reference solver.

CONTROLS
  throttle       manual power demand, hard-limited to 25 kW
  autopilot      speed-following pilot with corner speed caps
  time           1x to 100x compression
  live sliders   coolant flow, sea temperature, ambient -- change mid-run and
                 watch the pack respond
"""

from __future__ import annotations
import json
import os

_HTML = r"""<!DOCTYPE html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Volare — Live Race Simulator</title><style>
:root{--bg:#0b0f14;--panel:#131a22;--line:#243040;--fg:#e6edf3;--dim:#7d8da1;
--acc:#4d9fff;--warn:#e3a008;--bad:#f2545b;--ok:#3ddc84;--water:#0a2540}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);
font:12.5px/1.5 ui-monospace,"SF Mono",Menlo,Consolas,monospace;overflow-x:hidden}
header{padding:10px 16px;border-bottom:1px solid var(--line);display:flex;
gap:14px;align-items:center;flex-wrap:wrap;background:var(--panel)}
h1{font-size:14px;margin:0;font-weight:600;letter-spacing:.4px}
.sub{color:var(--dim);font-size:10.5px}
button,select{background:#1b242f;color:var(--fg);border:1px solid var(--line);
border-radius:5px;padding:5px 11px;font:inherit;cursor:pointer}
button:hover,select:hover{border-color:var(--acc)}
button.on{background:var(--acc);color:#04121f;border-color:var(--acc);font-weight:600}
main{display:grid;grid-template-columns:minmax(430px,1.15fr) minmax(400px,1fr);
gap:10px;padding:10px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:7px;
padding:10px;margin-bottom:10px}
.card h2{font-size:10px;margin:0 0 8px;color:var(--dim);font-weight:600;
text-transform:uppercase;letter-spacing:.9px}
canvas{display:block;width:100%;border-radius:4px}
#boat{height:210px;background:linear-gradient(#0d1b2a 0%,#12293f 58%,#071a2b 58%,#04101c 100%)}
#plan{height:150px;background:#0a1219}
#pack{image-rendering:pixelated;background:#000}
.kv{display:grid;grid-template-columns:repeat(auto-fit,minmax(88px,1fr));gap:6px}
.kv div{background:#0d141c;border:1px solid var(--line);border-radius:5px;padding:6px 8px}
.kv b{display:block;font-size:16px;font-weight:600}
.kv span{color:var(--dim);font-size:9.5px;text-transform:uppercase;letter-spacing:.5px}
.row{display:flex;gap:10px;align-items:center;margin:7px 0;flex-wrap:wrap}
.row label{color:var(--dim);font-size:10.5px;min-width:96px}
input[type=range]{flex:1;min-width:110px;accent-color:var(--acc);height:20px}
#thr{accent-color:var(--ok);height:26px}
.val{min-width:74px;text-align:right;font-weight:600}
.legend{display:flex;gap:11px;font-size:9.5px;color:var(--dim);margin-top:5px;flex-wrap:wrap}
.sw{display:inline-block;width:9px;height:9px;border-radius:2px;margin-right:3px}
.warn{color:var(--warn)}.bad{color:var(--bad)}.ok{color:var(--ok)}
.bar{height:7px;background:#0d141c;border-radius:4px;overflow:hidden;margin-top:4px}
.bar i{display:block;height:100%;background:var(--acc)}
.note{color:var(--dim);font-size:10px;margin-top:6px;line-height:1.5}
</style></head><body>
<header><h1>VOLARE — LIVE RACE SIMULATOR</h1>
<span class="sub" id="cfg"></span><span style="flex:1"></span>
<button id="run" class="on">❚❚ pause</button>
<button id="rst">↺ reset</button>
<label class="sub">time</label>
<select id="rate"><option>1</option><option>2</option><option selected>5</option>
<option>10</option><option>25</option><option>50</option><option>100</option></select>
<span class="sub">×</span></header>
<main>
<div>
 <div class="card"><h2>Boat — hull in water, cockpit in air</h2>
  <canvas id="boat"></canvas>
  <div class="legend">
   <span><i class="sw" style="background:#4d9fff"></i>airflow over cockpit</span>
   <span><i class="sw" style="background:#3ddc84"></i>wake &amp; spray</span>
   <span><i class="sw" style="background:#7d8da1"></i>waterline</span>
   <span id="hyd"></span></div></div>
 <div class="card"><h2>Course</h2><canvas id="plan"></canvas></div>
 <div class="card"><h2>Controls</h2>
  <div class="row"><label>THROTTLE</label>
   <input type="range" id="thr" min="0" max="100" value="0">
   <span class="val" id="thrv">0 %</span></div>
  <div class="row"><label></label>
   <button id="ap">autopilot OFF</button>
   <label style="min-width:auto">target</label>
   <input type="range" id="tgt" min="20" max="70" value="55" style="max-width:120px">
   <span class="val" id="tgtv">55 km/h</span></div>
  <hr style="border:0;border-top:1px solid var(--line);margin:9px 0">
  <div class="row"><label>coolant flow</label>
   <input type="range" id="flow" min="10" max="160" value="80">
   <span class="val" id="flowv">8.0 L/min</span></div>
  <div class="row"><label>sea / inlet</label>
   <input type="range" id="tin" min="150" max="380" value="290">
   <span class="val" id="tinv">29.0 °C</span></div>
  <div class="row"><label>air ambient</label>
   <input type="range" id="tamb" min="150" max="450" value="300">
   <span class="val" id="tambv">30.0 °C</span></div>
  <div class="row"><label>headwind</label>
   <input type="range" id="wind" min="0" max="120" value="0">
   <span class="val" id="windv">0.0 m/s</span></div>
  <div class="note">Change any of these mid-run. The pack responds in real
   time — that is the point of running the physics rather than a replay.</div>
 </div>
</div>
<div>
 <div class="card"><h2>State</h2><div class="kv" id="kv"></div>
  <div class="note">energy budget (REQ_7, 9.828 kWh)</div>
  <div class="bar"><i id="ebar" style="width:0%"></i></div></div>
 <div class="card"><h2>Pack — cell core temperature</h2>
  <canvas id="pack"></canvas>
  <div class="legend" id="scale"></div>
  <div class="note" id="hot"></div></div>
 <div class="card"><h2>History — last 5 minutes</h2>
  <canvas id="tr" style="height:290px"></canvas>
  <div class="legend">
   <span><i class="sw" style="background:#4d9fff"></i>shaft power / 25 kW</span>
   <span><i class="sw" style="background:#3ddc84"></i>speed</span>
   <span><i class="sw" style="background:#f2545b"></i>T max</span>
   <span><i class="sw" style="background:#e3a008"></i>SOC</span></div></div>
</div></main>
<script>
const M = __MODEL__;
const $ = i => document.getElementById(i);
const NC = M.meta.nCells, NS = M.meta.nSeries, NP = M.meta.nParallel;
const TH = M.thermal, CL = M.cell, BT = M.boat, CO = M.course;

// ---------- flatten network into typed arrays (fast) ----------
const nbI = new Int32Array(TH.neighbours.length), nbJ = new Int32Array(TH.neighbours.length),
      nbG = new Float64Array(TH.neighbours.length);
TH.neighbours.forEach((p,k)=>{nbI[k]=p[0];nbJ[k]=p[1];nbG[k]=p[2]});
const cpI = new Int32Array(TH.coolPairs.length), cpS = new Int32Array(TH.coolPairs.length),
      cpG = new Float64Array(TH.coolPairs.length);
TH.coolPairs.forEach((p,k)=>{cpI[k]=p[0];cpS[k]=p[1];cpG[k]=p[2]});
const gAir = Float64Array.from(TH.gAir);
const capAh = Float64Array.from(CL.capMult, v=>v*CL.capAh);
const resM  = Float64Array.from(CL.resMult);
const serIdx= Int32Array.from(M.display.series);
const R0map = CL.R0map.map(r=>Float64Array.from(r));
const socG  = Float64Array.from(CL.socGrid), Tg = Float64Array.from(CL.Tgrid);

function interp(x,xs,ys){ if(x<=xs[0])return ys[0];
  const n=xs.length; if(x>=xs[n-1])return ys[n-1];
  let lo=0,hi=n-1; while(hi-lo>1){const m=(lo+hi)>>1; if(xs[m]<=x)lo=m;else hi=m}
  const f=(x-xs[lo])/(xs[hi]-xs[lo]); return ys[lo]+(ys[hi]-ys[lo])*f}

function R0of(T,z,i){
  const Tc=Math.min(Math.max(T,Tg[0]),Tg[Tg.length-1]);
  if(Tg.length===1) return interp(z,socG,R0map[0])*resM[i];
  let k=0; while(k<Tg.length-2 && Tg[k+1]<Tc) k++;
  const w=(Tc-Tg[k])/(Tg[k+1]-Tg[k]);
  return (interp(z,socG,R0map[k])*(1-w)+interp(z,socG,R0map[k+1])*w)*resM[i]}

// ---------- engine ----------
class Engine{
 constructor(){ this.reset() }
 reset(){
  this.Tcore=new Float64Array(NC).fill(28); this.Tcan=new Float64Array(NC).fill(28);
  this.Tseg=new Float64Array(Math.max(TH.nSeg,1)).fill(M.env.TinC);
  this.Tbus=new Float64Array(Math.max(TH.nBus,1)).fill(28);
  this.Tair=M.env.TambC;
  this.z=new Float64Array(NC).fill(1); this.v1=new Float64Array(NC); this.v2=new Float64Array(NC);
  this.I=new Float64Array(NC);
  this.t=0; this.v=0; this.s=0; this.Wh=0; this.Ip=0; this.Vp=NS*4.2;
  this.n=0; this.eff=0; this.q=0; this.thrust=0; this.drag=0; this.capped=false;
  this.num=new Float64Array(Math.max(TH.nSeg,1)); this.den=new Float64Array(Math.max(TH.nSeg,1));
  this.fc=new Float64Array(NC); this.fa=new Float64Array(NC);
 }
 // -- propeller
 KT(J){return Math.max(0,0.36*BT.propPD-0.32*J-0.06*J*J)}
 KQ(J){return Math.max(1e-4,0.055*BT.propPD-0.036*J-0.008*J*J)}
 Jof(v,n){return v*(1-BT.wake)/Math.max(n*BT.propD,1e-6)}
 shaftP(v,n){const J=this.Jof(v,n);return 2*Math.PI*n*this.KQ(J)*1025*n*n*Math.pow(BT.propD,5)}
 rpsFor(v,P){ if(P<=0)return 0; let lo=0.5,hi=200;
   for(let k=0;k<38;k++){const m=(lo+hi)/2; if(this.shaftP(v,m)<P)lo=m;else hi=m} return (lo+hi)/2}
 // -- one step
 step(dt,Pcmd,env){
  const Pmax=M.meta.PmaxW;
  this.capped = Pcmd>Pmax+1e-6;
  let P=Math.min(Math.max(Pcmd,0),Pmax);
  // ---- boat
  const n=this.rpsFor(this.v,P*BT.drivelineEff);
  const J=this.Jof(this.v,n);
  const T=this.KT(J)*1025*n*n*Math.pow(BT.propD,4);
  const Rv=interp(this.v,BT.vGrid,BT.Rgrid);
  const va=this.v+env.wind;
  const Rair=0.5*1.2*va*va*(0.55*BT.dryAreaM2*0.22+1.2*2*BT.beamD*BT.beamSpan)
             - 0.5*1.2*this.v*this.v*(0.55*BT.dryAreaM2*0.22+1.2*2*BT.beamD*BT.beamSpan);
  const Rt=Rv+Math.max(0,Rair);
  const a=(T*(1-BT.thrustDed)-Rt)/(BT.massKg*(1+BT.addedMass));
  this.v=Math.max(0,this.v+a*dt); this.s+=this.v*dt;
  this.n=n; this.thrust=T; this.drag=Rt;
  this.eff = this.KQ(J)>0 ? Math.min(0.85,Math.max(0,J*this.KT(J)/(2*Math.PI*this.KQ(J)))) : 0;
  // ---- pack electrical (closed form per parallel group)
  const a_=new Float64Array(NC), b_=new Float64Array(NC), U_=new Float64Array(NC);
  const A=new Float64Array(NS), B=new Float64Array(NS);
  for(let i=0;i<NC;i++){
    const R0=R0of(this.Tcore[i],this.z[i],i);
    const U=interp(this.z[i],CL.ocvSoc,CL.ocvV);
    U_[i]=U; a_[i]=(U-this.v1[i]-this.v2[i])/R0; b_[i]=1/R0;
    A[serIdx[i]]+=a_[i]; B[serIdx[i]]+=b_[i]}
  let Voc=0,Reff=0; for(let g=0;g<NS;g++){Voc+=A[g]/B[g];Reff+=1/B[g]}
  const Pbus=P/M.meta.inverterEff;
  const disc=Voc*Voc-4*Reff*Pbus;
  const Ip = disc<=0 ? Voc/(2*Reff) : (Voc-Math.sqrt(disc))/(2*Reff);
  const Vg=new Float64Array(NS); let Vp=0;
  for(let g=0;g<NS;g++){Vg[g]=(A[g]-Ip)/B[g]; Vp+=Vg[g]}
  this.Ip=Ip; this.Vp=Vp;
  // ---- heat
  let qtot=0;
  for(let i=0;i<NC;i++){
    const I=a_[i]-Vg[serIdx[i]]*b_[i]; this.I[i]=I;
    const dudt=interp(this.z[i],CL.dudtSoc,CL.dudtV);
    this.fc[i]=I*(U_[i]-Vg[serIdx[i]])-I*(this.Tcore[i]+273.15)*dudt;
    qtot+=this.fc[i]}
  this.q=qtot;
  const qbus=Ip*Ip*TH.busR;
  // ---- coolant: quasi-static forward sweep in flow order
  const mcp=TH.mdotCpPerCircuit*(env.flow/M.env.flowLmin);
  if(TH.nSeg){
    this.num.fill(0); this.den.fill(0);
    for(let k=0;k<cpI.length;k++){this.num[cpS[k]]+=cpG[k]*this.Tcan[cpI[k]]; this.den[cpS[k]]+=cpG[k]}
    for(let c=0;c<TH.coolChain.length;c++){
      const seg=TH.coolChain[c][0], up=TH.coolChain[c][1];
      const Tup = up<0 ? env.tin : this.Tseg[up];
      this.Tseg[seg]=(mcp*Tup+this.num[seg])/(mcp+this.den[seg])}}
  // ---- explicit Euler
  const gcc=TH.gCoreCan;
  this.fa.fill(0);
  for(let i=0;i<NC;i++){const fl=gcc*(this.Tcore[i]-this.Tcan[i]);
    this.fc[i]-=fl; this.fa[i]+=fl-gAir[i]*(this.Tcan[i]-this.Tair)}
  for(let k=0;k<nbI.length;k++){const fl=nbG[k]*(this.Tcan[nbI[k]]-this.Tcan[nbJ[k]]);
    this.fa[nbI[k]]-=fl; this.fa[nbJ[k]]+=fl}
  for(let k=0;k<cpI.length;k++){this.fa[cpI[k]]-=cpG[k]*(this.Tcan[cpI[k]]-this.Tseg[cpS[k]])}
  let fair=-TH.UAair*(this.Tair-env.tamb);
  for(let i=0;i<NC;i++) fair+=gAir[i]*(this.Tcan[i]-this.Tair);
  const fbus=new Float64Array(Math.max(TH.nBus,1));
  for(let i=0;i<NC;i++){const g=serIdx[i];
    if(g<TH.nBus){const f=TH.gCanBus*(this.Tcan[i]-this.Tbus[g]); this.fa[i]-=f; fbus[g]+=f}
    if(g-1>=0){const f=TH.gCanBus*(this.Tcan[i]-this.Tbus[g-1]); this.fa[i]-=f; fbus[g-1]+=f}}
  for(let i=0;i<NC;i++){this.Tcore[i]+=dt*this.fc[i]/TH.Ccore; this.Tcan[i]+=dt*this.fa[i]/TH.Ccan}
  for(let g=0;g<TH.nBus;g++) this.Tbus[g]+=dt*(fbus[g]+qbus-0.5*(this.Tbus[g]-this.Tair))/TH.Cbus;
  this.Tair+=dt*fair/TH.Cair;
  // ---- electrical state
  const e1=Math.exp(-dt/CL.tau1), e2=Math.exp(-dt/CL.tau2);
  for(let i=0;i<NC;i++){
    const R0=R0of(this.Tcore[i],this.z[i],i);
    this.v1[i]=this.v1[i]*e1+this.I[i]*R0*CL.f1*(1-e1);
    this.v2[i]=this.v2[i]*e2+this.I[i]*R0*CL.f2*(1-e2);
    this.z[i]=Math.max(0,this.z[i]-this.I[i]*dt/(3600*capAh[i]))}
  this.Wh+=Vp*Ip*dt/3600; this.t+=dt;
  return P}
 stats(){let mx=-1e9,mn=1e9,sm=0,hi=0,zs=0;
  for(let i=0;i<NC;i++){const T=this.Tcore[i]; sm+=T; zs+=this.z[i];
    if(T>mx){mx=T;hi=i} if(T<mn)mn=T}
  return {Tmax:mx,Tmin:mn,Tmean:sm/NC,hot:hi,soc:zs/NC,
          coolOut:TH.nSeg?Math.max(...this.Tseg):M.env.TinC}}
}

// ---------- course helpers ----------
function speedCap(s){let x=s%CO.lapLength,acc=0;
  for(const l of CO.legs){ if(x<acc+l.length) return l.radius>0?Math.sqrt(CO.latG*9.80665*l.radius):1e6; acc+=l.length}
  return 1e6}
function legName(s){let x=s%CO.lapLength,acc=0;
  for(const l of CO.legs){ if(x<acc+l.length) return l.name; acc+=l.length} return CO.legs[0].name}

// ---------- UI ----------
const E=new Engine(); let running=true, autopilot=false, last=performance.now();
const hist={t:[],P:[],v:[],T:[],z:[]}, HMAX=600;
const env={flow:M.env.flowLmin,tin:M.env.TinC,tamb:M.env.TambC,wind:0};
$('cfg').textContent=`${NC} cells ${NS}S${NP}P · ${M.meta.nTubes} tubes / `
 +`${M.meta.nCircuits} circuits · Re ${M.meta.ReCoolant.toFixed(0)} `
 +`(${M.meta.regime}) · ΔP ${M.meta.dPbar.toFixed(2)} bar`;
$('hyd').textContent=`Lwl ${BT.LwlM.toFixed(2)} m · wetted ${BT.wettedM2.toFixed(2)} m² · `
 +`prop ⌀${(BT.propD*1000).toFixed(0)} mm P/D ${BT.propPD.toFixed(2)}`;

function bind(id,vid,fmt,set){const e=$(id);
  const up=()=>{const v=+e.value; $(vid).textContent=fmt(v); set(v)}; e.oninput=up; up()}
bind('thr','thrv',v=>v.toFixed(0)+' %',()=>{});
bind('tgt','tgtv',v=>v.toFixed(0)+' km/h',()=>{});
bind('flow','flowv',v=>(v/10).toFixed(1)+' L/min',v=>env.flow=v/10);
bind('tin','tinv',v=>(v/10).toFixed(1)+' °C',v=>env.tin=v/10);
bind('tamb','tambv',v=>(v/10).toFixed(1)+' °C',v=>env.tamb=v/10);
bind('wind','windv',v=>(v/10).toFixed(1)+' m/s',v=>env.wind=v/10);
$('run').onclick=()=>{running=!running;$('run').textContent=running?'❚❚ pause':'▶ run';
  $('run').className=running?'on':''; last=performance.now()};
$('rst').onclick=()=>{E.reset();hist.t.length=0;hist.P.length=0;hist.v.length=0;
  hist.T.length=0;hist.z.length=0};
$('ap').onclick=()=>{autopilot=!autopilot;$('ap').textContent='autopilot '+(autopilot?'ON':'OFF');
  $('ap').className=autopilot?'on':''};

function col(u){u=Math.max(0,Math.min(1,u));
 const st=[[10,15,22],[26,74,124],[42,148,142],[227,160,8],[242,84,91],[255,232,180]];
 const x=u*(st.length-1),k=Math.min(st.length-2,Math.floor(x)),f=x-k,a=st[k],b=st[k+1];
 return `rgb(${a[0]+(b[0]-a[0])*f|0},${a[1]+(b[1]-a[1])*f|0},${a[2]+(b[2]-a[2])*f|0})`}

function fit(c){const r=c.getBoundingClientRect();
  if(c.width!==r.width*2||c.height!==r.height*2){c.width=r.width*2;c.height=r.height*2}
  return c.getContext('2d')}

// ---------- boat view: hull in water, cockpit in air ----------
let phase=0;
function drawBoat(st){
 const c=$('boat'),g=fit(c),W=c.width,H=c.height,WL=H*0.58;
 g.clearRect(0,0,W,H);
 const v=E.v, vk=v*3.6, spd=Math.min(1,vk/70);
 phase+=v*0.09+0.4;
 // --- airflow streamlines above the waterline
 g.lineCap='round';
 for(let k=0;k<16;k++){
  const y=8+k*(WL-16)/16, amp=(1-y/WL)*5;
  g.strokeStyle=`rgba(77,159,255,${0.10+0.42*spd})`;
  g.lineWidth=1.3+1.7*spd;
  const seg=26+150*spd, gap=30;
  for(let x=-((phase*(2+9*spd))%(seg+gap));x<W;x+=seg+gap){
   g.beginPath();
   for(let d=0;d<seg;d+=6){const xx=x+d;
    const dy=(xx>W*0.30&&xx<W*0.62)?-amp*Math.exp(-Math.pow((xx-W*0.46)/(W*0.13),2))*2.4:0;
    d?g.lineTo(xx,y+dy):g.moveTo(xx,y+dy)}
   g.stroke()}}
 // --- water surface
 g.strokeStyle='rgba(125,141,161,.85)';g.lineWidth=2;g.beginPath();
 for(let x=0;x<=W;x+=5){g.lineTo(x,WL+Math.sin(x*0.022+phase*0.05)*(1.5+3.5*spd))}
 g.stroke();
 // --- hull (below waterline darker) + cockpit (above)
 const cx=W*0.46, L=W*0.40, dr=H*0.10*(1-0.55*spd);   // rises as it planes
 g.fillStyle='#1b2a3a';
 g.beginPath();
 g.moveTo(cx-L/2,WL-dr*0.15); g.lineTo(cx+L/2*0.86,WL-dr*0.15);
 g.quadraticCurveTo(cx+L/2,WL-dr*0.15,cx+L/2,WL+dr*0.15);
 g.lineTo(cx+L/2,WL+dr); g.lineTo(cx-L/2*0.78,WL+dr*0.86);
 g.quadraticCurveTo(cx-L/2,WL+dr*0.3,cx-L/2,WL-dr*0.15);
 g.closePath(); g.fill();
 g.save(); g.beginPath(); g.rect(0,WL,W,H-WL); g.clip();
 g.fillStyle='#0d3b5c'; g.beginPath();
 g.moveTo(cx-L/2,WL); g.lineTo(cx+L/2,WL); g.lineTo(cx+L/2,WL+dr);
 g.lineTo(cx-L/2*0.78,WL+dr*0.86); g.closePath(); g.fill(); g.restore();
 // cockpit pod in air
 g.fillStyle='#24384d';
 g.beginPath(); g.moveTo(cx-L*0.20,WL-dr*0.15);
 g.lineTo(cx+L*0.16,WL-dr*0.15); g.lineTo(cx+L*0.10,WL-dr*0.15-H*0.15);
 g.lineTo(cx-L*0.13,WL-dr*0.15-H*0.15); g.closePath(); g.fill();
 g.fillStyle='rgba(77,159,255,.35)';
 g.fillRect(cx-L*0.09,WL-dr*0.15-H*0.125,L*0.15,H*0.055);
 // crossbeams
 g.strokeStyle='#3a4d63';g.lineWidth=4;
 g.beginPath();g.moveTo(cx-L*0.30,WL-dr*0.6);g.lineTo(cx+L*0.28,WL-dr*0.6);g.stroke();
 // --- spray at the bow and wake behind
 g.fillStyle=`rgba(61,220,132,${0.18+0.55*spd})`;
 for(let k=0;k<Math.round(4+40*spd);k++){
  const r=(k*61.7+phase*3)%1, x=cx+L/2-r*W*0.30, y=WL-r*H*0.16*spd+Math.sin(k*3.1)*3;
  g.beginPath();g.arc(x,y,1.2+3.2*spd*(1-r),0,6.283);g.fill()}
 g.fillStyle=`rgba(200,230,255,${0.10+0.35*spd})`;
 for(let k=0;k<Math.round(6+55*spd);k++){
  const r=(k*37.3+phase*2)%1, x=cx-L/2-r*W*0.42, y=WL+2+Math.sin(k*2.3+phase*0.1)*(2+7*spd);
  g.beginPath();g.arc(x,y,1+3.5*spd*(1-r*0.7),0,6.283);g.fill()}
 // --- labels
 g.font='19px ui-monospace';g.fillStyle='#7d8da1';
 g.fillText('AIR',12,26); g.fillText('WATER',12,WL+30);
 g.fillStyle='#e6edf3';g.font='bold 30px ui-monospace';
 g.fillText(vk.toFixed(1)+' km/h',W-250,42);
 g.font='17px ui-monospace';g.fillStyle=E.capped?'#f2545b':'#4d9fff';
 g.fillText((st.P/1000).toFixed(2)+' kW'+(E.capped?'  ← CAPPED':''),W-250,68);
 g.fillStyle='#7d8da1';
 g.fillText('drag '+E.drag.toFixed(0)+' N  ·  thrust '+E.thrust.toFixed(0)+' N',W-250,92);
}

// ---------- plan view ----------
function drawPlan(){
 const c=$('plan'),g=fit(c),W=c.width,H=c.height;
 g.clearRect(0,0,W,H);
 const pts=[],legs=CO.legs; let ang=0,x=0,y=0;
 const N=420;
 for(let k=0;k<N;k++){
  const s=k/N*CO.lapLength; let acc=0,cur=legs[0];
  for(const l of legs){ if(s<acc+l.length){cur=l;break} acc+=l.length}
  const ds=CO.lapLength/N;
  if(cur.radius>0) ang+=ds/cur.radius;
  x+=Math.cos(ang)*ds; y+=Math.sin(ang)*ds; pts.push([x,y])}
 const xs=pts.map(p=>p[0]),ys=pts.map(p=>p[1]);
 const x0=Math.min(...xs),x1=Math.max(...xs),y0=Math.min(...ys),y1=Math.max(...ys);
 const sc=Math.min((W-70)/(x1-x0+1e-6),(H-50)/(y1-y0+1e-6));
 const P=p=>[35+(p[0]-x0)*sc,25+(p[1]-y0)*sc];
 g.strokeStyle='#243040';g.lineWidth=16;g.lineJoin='round';g.beginPath();
 pts.forEach((p,k)=>{const q=P(p);k?g.lineTo(q[0],q[1]):g.moveTo(q[0],q[1])});
 g.closePath();g.stroke();
 const idx=Math.floor((E.s%CO.lapLength)/CO.lapLength*N)%N, b=P(pts[idx]);
 g.fillStyle='#3ddc84';g.beginPath();g.arc(b[0],b[1],9,0,6.283);g.fill();
 g.font='19px ui-monospace';g.fillStyle='#7d8da1';
 g.fillText(`lap ${(E.s/CO.lapLength).toFixed(2)}  ·  ${legName(E.s)}  ·  `
  +`${CO.lapLength.toFixed(0)} m/lap`,35,H-12);
}

// ---------- pack heatmap ----------
const nxP=NP, nyP=NS/Math.max(1,M.meta.nLayers), nL=M.meta.nLayers;
function drawPack(st){
 const c=$('pack'); const px=Math.max(6,Math.floor(560/nxP));
 if(c.width!==nxP*px){c.width=nxP*px;c.height=nyP*nL*px}
 const g=c.getContext('2d');
 let lo=1e9,hi=-1e9; for(let i=0;i<NC;i++){const T=E.Tcore[i];if(T<lo)lo=T;if(T>hi)hi=T}
 lo=Math.floor(lo*2)/2; hi=Math.max(lo+1,Math.ceil(hi*2)/2);
 for(let i=0;i<NC;i++){
  const s=M.display.series[i], p=M.display.par[i], L=M.display.layer[i];
  const row=(s%nyP)+L*nyP;
  g.fillStyle=col((E.Tcore[i]-lo)/(hi-lo));
  g.fillRect(p*px,row*px,px-1,px-1)}
 const hs=st.hot, hr=(M.display.series[hs]%nyP)+M.display.layer[hs]*nyP;
 g.strokeStyle='#fff';g.lineWidth=2;g.beginPath();
 g.arc((M.display.par[hs]+0.5)*px,(hr+0.5)*px,px*0.55,0,6.283);g.stroke();
 $('scale').innerHTML=`<span>${lo.toFixed(1)}°C</span>`+
  Array.from({length:20},(_,k)=>`<i class="sw" style="background:${col(k/19)}"></i>`).join('')+
  `<span>${hi.toFixed(1)}°C</span>`;
 $('hot').textContent=`hotspot: group ${M.display.series[hs]}, position ${M.display.par[hs]}`
  +`  ·  spread ${(st.Tmax-st.Tmin).toFixed(2)} K  ·  coolant out ${st.coolOut.toFixed(1)} °C`;
}

// ---------- traces ----------
function drawTr(){
 const c=$('tr'),g=fit(c),W=c.width,H=c.height;
 g.clearRect(0,0,W,H);
 const n=hist.t.length; if(n<2)return;
 g.strokeStyle='#243040';g.lineWidth=1;
 for(let k=0;k<=4;k++){const y=H*k/4;g.beginPath();g.moveTo(0,y);g.lineTo(W,y);g.stroke()}
 const Tlo=Math.min(...hist.T)-1,Thi=Math.max(...hist.T)+1;
 const plot=(d,c2,lo,hi,lw)=>{g.strokeStyle=c2;g.lineWidth=lw||2.4;g.beginPath();
  for(let k=0;k<n;k++){const x=W*k/(n-1),y=H*(1-(d[k]-lo)/(hi-lo));
   k?g.lineTo(x,y):g.moveTo(x,y)}g.stroke()};
 plot(hist.P,'#4d9fff',0,1); plot(hist.v,'#3ddc84',0,Math.max(...hist.v)*1.2+1);
 plot(hist.T,'#f2545b',Tlo,Thi); plot(hist.z,'#e3a008',0,1,1.8);
 g.setLineDash([6,5]);g.strokeStyle='rgba(242,84,91,.55)';g.lineWidth=1.5;
 const yw=H*(1-(CL.TwarnC-Tlo)/(Thi-Tlo));
 if(yw>0&&yw<H){g.beginPath();g.moveTo(0,yw);g.lineTo(W,yw);g.stroke();
  g.fillStyle='rgba(242,84,91,.8)';g.font='17px ui-monospace';
  g.fillText(`${CL.TwarnC}°C warn`,6,yw-6)}
 g.setLineDash([]);
 g.fillStyle='#7d8da1';g.font='17px ui-monospace';
 g.fillText(`T ${Tlo.toFixed(0)}–${Thi.toFixed(0)}°C`,6,H-8);
}

// ---------- readouts ----------
function draw(st,P){
 drawBoat({P}); drawPlan(); drawPack(st); drawTr();
 const eFrac=E.Wh/1000/M.meta.energyCapKWh;
 $('ebar').style.width=Math.min(100,eFrac*100)+'%';
 $('ebar').style.background=eFrac>0.97?'#f2545b':(eFrac>0.85?'#e3a008':'#4d9fff');
 $('kv').innerHTML=[
  ['speed',(E.v*3.6).toFixed(1),'km/h',''],
  ['shaft',(P/1000).toFixed(2),'kW',E.capped?'bad':''],
  ['prop rpm',(E.n*60*BT.gearRatio).toFixed(0),'',''],
  ['prop eff',(E.eff*100).toFixed(1),'%',''],
  ['bus',E.Ip.toFixed(0),'A',''],
  ['pack V',E.Vp.toFixed(1),'V',''],
  ['SOC',(st.soc*100).toFixed(1),'%',st.soc<0.1?'warn':''],
  ['energy',(E.Wh/1000).toFixed(3),'kWh',eFrac>0.97?'bad':''],
  ['pack heat',E.q.toFixed(0),'W',''],
  ['T max',st.Tmax.toFixed(1),'°C',st.Tmax>CL.TmaxC?'bad':(st.Tmax>CL.TwarnC?'warn':'')],
  ['T spread',(st.Tmax-st.Tmin).toFixed(2),'K',''],
  ['time',(E.t/60).toFixed(2),'min','']
 ].map(([k,v,u,cls])=>`<div><span>${k}</span><b class="${cls}">${v}`+
  `<small style="font-size:10px;color:#7d8da1"> ${u}</small></b></div>`).join('');
}

// ---------- main loop ----------
const DT=0.5;
function frame(ts){
 const rate=+$('rate').value, wall=Math.min(0.25,(ts-last)/1000); last=ts;
 if(running){
  let acc=wall*rate, guard=0;
  while(acc>0 && guard++<400){
   let Pcmd;
   if(autopilot){
    const vt=Math.min(+$('tgt').value/3.6, speedCap(E.s));
    Pcmd=Math.max(0,Math.min(M.meta.PmaxW,9000*(vt-E.v)));
    $('thr').value=Math.round(Pcmd/M.meta.PmaxW*100);
    $('thrv').textContent=(Pcmd/M.meta.PmaxW*100).toFixed(0)+' %';
   } else Pcmd=(+$('thr').value)/100*M.meta.PmaxW;
   if(E.z.reduce((a,b)=>Math.min(a,b),1)<=0.02) Pcmd=0;
   E.step(DT,Pcmd,env); acc-=DT;
   const st0=E.stats();
   hist.t.push(E.t); hist.P.push(Pcmd/M.meta.PmaxW); hist.v.push(E.v*3.6);
   hist.T.push(st0.Tmax); hist.z.push(st0.soc);
   if(hist.t.length>HMAX){for(const k in hist) hist[k].shift()}}}
 const st=E.stats();
 draw(st,(autopilot?+$('thr').value:+$('thr').value)/100*M.meta.PmaxW);
 requestAnimationFrame(frame);
}
requestAnimationFrame(frame);
</script></body></html>"""


def write_live_sim(model: dict, out="figures/live_simulator.html"):
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write(_HTML.replace("__MODEL__",
                              json.dumps(model, separators=(",", ":"))))
    return out, os.path.getsize(out)
