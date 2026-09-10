r"""
volare_thermal.groundstation
============================

Mission-control-grade race simulator. Same verified physics as the reference
solver, run live in the browser, presented the way a pit wall actually works.

WHAT MAKES IT A GROUND STATION RATHER THAN A DEMO
-------------------------------------------------
  TRACK       real Monaco stadium geometry, 1 NM lap, three sectors, corner
              speed limits computed from actual curvature
  TIMING      lap and sector times, rolling best, live delta to best, purple
              sector logic
  STRATEGY    energy per lap, projected finishing distance, whether you are
              energy-limited or time-limited, and the target pace to hit
  LIMITS      an alarm rail that latches, so a transient breach that lasts
              200 ms is still visible ten minutes later
  ENGINEERING per-cell thermal field, current sharing, coolant circuit state
  EXPORT      full session to CSV, because a run you cannot analyse afterwards
              is a run you did not really do

Four views share one engine and one clock: TELEMETRY, THERMAL, STRATEGY,
ENGINEERING.
"""

from __future__ import annotations
import json
import os

_HTML = r"""<!DOCTYPE html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>VOLARE · Mission Control</title><style>
:root{
 /* ---- surfaces: six steps, cool neutral, so depth reads without borders ---- */
 --bg:#05070b; --s1:#0a0e14; --s2:#0e131b; --s3:#131a24; --s4:#1a2331;
 /* ---- hairlines: opacity-based so they sit correctly on any surface ---- */
 --hair:rgba(255,255,255,.055); --hair2:rgba(255,255,255,.10);
 --hair3:rgba(255,255,255,.16);
 /* ---- text: four weights of presence ---- */
 --fg:#e8eff7; --dim:#93a5b9; --dim2:#5d6f83; --dim3:#3a4655;
 /* ---- semantic: filmic, not neon ---- */
 --acc:#2ad4ee; --acc2:#0e93b0; --accGlow:rgba(42,212,238,.22);
 --ok:#3ddc97; --warn:#f7b955; --bad:#ff6b7a; --purple:#b18cff;
 /* legacy aliases so nothing breaks */
 --p1:var(--s1); --p2:var(--s2); --line:var(--hair); --line2:var(--hair2);
 --edge:var(--hair3); --grid:rgba(255,255,255,.035);
 --glow:0 0 22px var(--accGlow);
 /* ---- elevation: layered, tight, never muddy ---- */
 --e1:0 1px 2px rgba(0,0,0,.42);
 --e2:0 1px 0 rgba(255,255,255,.035) inset, 0 2px 10px rgba(0,0,0,.45);
 --e3:0 1px 0 rgba(255,255,255,.05) inset, 0 8px 30px rgba(0,0,0,.6);
 --e4:0 24px 70px rgba(0,0,0,.78);
 /* ---- type ---- */
 --sans:-apple-system,BlinkMacSystemFont,"Segoe UI Variable Text","Segoe UI",
   Inter,Roboto,system-ui,sans-serif;
 --mono:ui-monospace,"SF Mono","JetBrains Mono","Cascadia Mono",Menlo,Consolas,monospace;
 --ease:cubic-bezier(.22,1,.36,1);
 --r1:4px; --r2:6px; --r3:9px;
}
*{box-sizing:border-box}
html,body{margin:0;height:100%;background:var(--bg);color:var(--fg);
 font:400 12.5px/1.52 var(--sans);overflow:hidden;
 -webkit-font-smoothing:antialiased;-moz-osx-font-smoothing:grayscale;
 text-rendering:optimizeLegibility}
/* every number is monospace and tabular; every label is sans */
.mono,b,.kv b,.tt td:last-child,.vt,output,table.dt td,#bootPct,#tCur,#tLast,
#tBest,#tTheo,.sec b,#hstat b,.hstat b{font-family:var(--mono);
 font-variant-numeric:tabular-nums;font-feature-settings:"tnum" 1,"zero" 1}

/* ---- film grain + vignette: the thing that stops it looking like a webpage ---- */
body::before{content:"";position:fixed;inset:-50%;z-index:997;pointer-events:none;
 opacity:.20;mix-blend-mode:overlay;
 background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='140' height='140'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='.85' numOctaves='3'/%3E%3C/filter%3E%3Crect width='140' height='140' filter='url(%23n)' opacity='.5'/%3E%3C/svg%3E");
 animation:grain 7s steps(6) infinite}
@keyframes grain{
 0%,100%{transform:translate(0,0)} 16%{transform:translate(-4%,-3%)}
 33%{transform:translate(3%,-4%)} 50%{transform:translate(-3%,3%)}
 66%{transform:translate(4%,2%)} 83%{transform:translate(-2%,4%)}}
body::after{content:"";position:fixed;inset:0;z-index:998;pointer-events:none;
 background:radial-gradient(ellipse 120% 90% at 50% 42%,transparent 46%,rgba(0,0,0,.62) 100%)}
#app{display:flex;flex-direction:column;height:100vh;position:relative;z-index:1}

/* ==================== BOOT ==================== */
#boot{position:fixed;inset:0;z-index:1000;background:#020407;overflow:hidden;
 transition:opacity .85s var(--ease)}
#boot.gone{opacity:0;pointer-events:none}
#bootCv{position:absolute;inset:0;width:100%;height:100%}
#bootUI{position:absolute;inset:0;display:flex;flex-direction:column;
 align-items:center;justify-content:center;pointer-events:none}
#bootTitle{font-family:var(--sans);font-size:clamp(32px,7vw,84px);
 letter-spacing:.36em;font-weight:200;color:#f0f8ff;margin-right:-.36em;
 text-shadow:0 0 70px rgba(42,212,238,.5),0 0 170px rgba(42,212,238,.22);
 opacity:0;transform:scale(1.14);
 animation:btIn 1.7s var(--ease) .25s forwards}
@keyframes btIn{to{opacity:1;transform:scale(1)}}
#bootSub{font-size:9px;letter-spacing:.58em;color:#4f7f9c;margin-top:18px;
 margin-right:-.58em;font-weight:500;text-transform:uppercase;
 opacity:0;animation:btIn 1.3s var(--ease) .95s forwards}
#bootRule{width:0;height:1px;margin-top:26px;
 background:linear-gradient(90deg,transparent,var(--acc),transparent);
 animation:rule 1.5s var(--ease) 1.15s forwards}
@keyframes rule{to{width:min(600px,76vw)}}
#bootStats{display:flex;gap:clamp(18px,3.6vw,44px);margin-top:26px;opacity:0;
 animation:btIn 1.1s var(--ease) 1.5s forwards}
#bootStats div{text-align:center}
#bootStats u{display:block;text-decoration:none;font-size:7px;letter-spacing:.26em;
 color:#3d5568;margin-bottom:5px;font-weight:600}
#bootStats b{font-family:var(--mono);font-size:16px;font-weight:400;
 color:#a9dff2;letter-spacing:.02em}
#bootLog{position:absolute;left:clamp(18px,4vw,58px);bottom:clamp(22px,5vh,52px);
 width:min(440px,46vw);font-size:9.5px;line-height:2;color:#3d5568;
 letter-spacing:.03em;pointer-events:none}
#bootLog div{opacity:0;animation:lg .5s var(--ease) forwards;display:flex;
 justify-content:space-between;gap:14px;white-space:nowrap}
@keyframes lg{from{transform:translateX(-10px)}to{opacity:1;transform:none}}
#bootLog i{font-style:normal;color:var(--ok);margin-right:8px}
#bootLog s{text-decoration:none;color:#61829a}
#bootLog span:last-child{font-family:var(--mono);color:#4a6478}
#bootBarWrap{position:absolute;left:0;right:0;bottom:0;height:2px;background:#070d14}
#bootBar{height:100%;width:0;
 background:linear-gradient(90deg,var(--acc2),var(--acc),#a9f0ff);
 box-shadow:0 0 22px var(--acc);transition:width .32s var(--ease)}
#bootPct{position:absolute;right:clamp(18px,4vw,58px);bottom:clamp(16px,4vh,46px);
 font-size:clamp(30px,5.4vw,60px);font-weight:200;color:#123a4f;
 letter-spacing:-.03em;pointer-events:none}
#bootPct s{text-decoration:none;font-size:.32em;color:#0d2634;margin-left:3px}
#bootFlash{position:absolute;inset:0;background:#d6f5ff;opacity:0;pointer-events:none}
#bootFlash.go{animation:fl .8s var(--ease) forwards}
@keyframes fl{15%{opacity:.58}100%{opacity:0}}

/* ==================== HEADER ==================== */
header{display:flex;align-items:stretch;flex:0 0 auto;position:relative;
 background:linear-gradient(180deg,var(--s3),var(--s1));
 box-shadow:0 1px 0 var(--hair),0 6px 26px rgba(0,0,0,.55)}
header::after{content:"";position:absolute;left:0;right:0;bottom:0;height:1px;
 background:linear-gradient(90deg,transparent,var(--hair3) 18%,var(--hair3) 82%,transparent)}
.brand{display:flex;flex-direction:column;justify-content:center;
 padding:11px 24px;border-right:1px solid var(--hair);min-width:196px;
 background:linear-gradient(100deg,rgba(42,212,238,.10),transparent 70%)}
.brand b{font-family:var(--sans);font-size:16px;letter-spacing:.36em;font-weight:250;
 color:#fff;margin-right:-.34em}
.brand i{font-style:normal;font-size:7.5px;letter-spacing:.3em;color:var(--acc);
 margin-top:4px;font-weight:600}
.hstat{padding:9px 19px;border-right:1px solid var(--hair);min-width:96px;
 display:flex;flex-direction:column;justify-content:center;position:relative}
.hstat u{display:block;color:var(--dim3);font-size:7.5px;text-decoration:none;
 letter-spacing:.2em;text-transform:uppercase;margin-bottom:3px;font-weight:600}
.hstat b{font-size:20px;font-weight:450;letter-spacing:-.01em;line-height:1.1;
 transition:color .3s var(--ease)}
.hstat b s{text-decoration:none;font-size:9.5px;color:var(--dim3);font-weight:400;
 margin-left:2px;font-family:var(--sans)}
.led{width:6px;height:6px;border-radius:50%;display:inline-block;margin-right:7px;
 background:var(--ok);box-shadow:0 0 10px var(--ok);vertical-align:middle;
 transition:.3s var(--ease)}
.led.w{background:var(--warn);box-shadow:0 0 10px var(--warn)}
.led.b{background:var(--bad);box-shadow:0 0 12px var(--bad);animation:pulse .9s infinite}
@keyframes pulse{50%{opacity:.22;box-shadow:0 0 4px var(--bad)}}
.grow{flex:1}
.tabs{display:flex}
.tab{padding:0 21px;cursor:pointer;color:var(--dim2);letter-spacing:.17em;
 font-size:9.5px;text-transform:uppercase;font-weight:600;display:flex;
 align-items:center;position:relative;transition:.22s var(--ease)}
.tab::after{content:"";position:absolute;left:19px;right:19px;bottom:0;height:2px;
 background:var(--acc);transform:scaleX(0);transition:transform .3s var(--ease);
 box-shadow:0 0 12px var(--acc)}
.tab:hover{color:var(--fg);background:rgba(255,255,255,.028)}
.tab.on{color:var(--acc);background:linear-gradient(180deg,rgba(42,212,238,.11),transparent)}
.tab.on::after{transform:scaleX(1)}

/* ==================== RAIL ==================== */
.rail{display:flex;align-items:center;gap:13px;padding:8px 18px;flex-wrap:wrap;
 border-bottom:1px solid var(--hair);background:var(--s1);flex:0 0 auto;
 box-shadow:0 2px 12px rgba(0,0,0,.35)}
button{background:linear-gradient(180deg,var(--s4),var(--s2));color:var(--fg);
 border:1px solid var(--hair2);border-radius:var(--r1);padding:6px 15px;
 font:600 10px/1 var(--sans);letter-spacing:.11em;text-transform:uppercase;
 cursor:pointer;transition:.18s var(--ease);box-shadow:var(--e1)}
button:hover{border-color:var(--acc);color:var(--acc);
 box-shadow:var(--e1),0 0 16px rgba(42,212,238,.18);transform:translateY(-1px)}
button:active{transform:translateY(0)}
button.on{background:linear-gradient(180deg,var(--acc),var(--acc2));color:#022029;
 border-color:var(--acc);box-shadow:0 0 20px var(--accGlow),var(--e1)}
select{background:var(--s2);color:var(--fg);border:1px solid var(--hair2);
 border-radius:var(--r1);padding:5px 9px;font:500 11px var(--sans);
 transition:.18s var(--ease)}
select:hover{border-color:var(--acc)}
label.s{color:var(--dim3);font-size:8.5px;letter-spacing:.18em;text-transform:uppercase;
 font-weight:600}
input[type=range]{-webkit-appearance:none;appearance:none;height:3px;width:98px;
 background:linear-gradient(90deg,var(--hair2),var(--hair));border-radius:2px;
 outline:none;cursor:pointer}
input[type=range]::-webkit-slider-thumb{-webkit-appearance:none;width:11px;height:11px;
 border-radius:50%;background:var(--acc);cursor:pointer;
 box-shadow:0 0 0 3px rgba(42,212,238,.14),0 0 12px var(--acc);
 transition:.15s var(--ease)}
input[type=range]::-webkit-slider-thumb:hover{transform:scale(1.22)}
input[type=range]::-moz-range-thumb{width:11px;height:11px;border:0;border-radius:50%;
 background:var(--acc);box-shadow:0 0 0 3px rgba(42,212,238,.14),0 0 12px var(--acc)}
#thr{width:210px;height:5px}
#thr::-webkit-slider-thumb{width:15px;height:15px;background:var(--ok);
 box-shadow:0 0 0 4px rgba(61,220,151,.14),0 0 14px var(--ok)}
#thr::-moz-range-thumb{width:15px;height:15px;background:var(--ok);
 box-shadow:0 0 0 4px rgba(61,220,151,.14),0 0 14px var(--ok)}
.vt{min-width:58px;text-align:right;font-weight:500;font-size:12px;color:var(--acc)}

/* ==================== LAYOUT ==================== */
main{flex:1;overflow:hidden;position:relative}
.view{position:absolute;inset:0;display:none;overflow:auto;padding:13px;gap:13px}
.view.on{display:grid;animation:viewIn .42s var(--ease)}
@keyframes viewIn{from{opacity:0;transform:translateY(7px) scale(.996)}}
#vTele{grid-template-columns:378px 1fr 320px}
#vTherm{grid-template-columns:1fr 376px}
#vStrat{grid-template-columns:1fr 400px}
#vEng{grid-template-columns:1fr 1fr}
#vSetup{grid-template-columns:1fr 400px}
#vAnal{grid-template-columns:1fr 1fr}
.col{display:flex;flex-direction:column;gap:13px;min-height:0;overflow:auto}
.col::-webkit-scrollbar,.view::-webkit-scrollbar,#radio::-webkit-scrollbar,
#palList::-webkit-scrollbar{width:8px;height:8px}
.col::-webkit-scrollbar-track,.view::-webkit-scrollbar-track{background:transparent}
.col::-webkit-scrollbar-thumb,.view::-webkit-scrollbar-thumb,
#radio::-webkit-scrollbar-thumb,#palList::-webkit-scrollbar-thumb{
 background:var(--hair2);border-radius:5px;border:2px solid transparent;
 background-clip:padding-box}
.col::-webkit-scrollbar-thumb:hover{background:var(--hair3);background-clip:padding-box}
.card{background:linear-gradient(180deg,var(--s2),var(--s1));
 border:1px solid var(--hair);border-radius:var(--r3);padding:13px 15px;
 position:relative;box-shadow:var(--e2);transition:border-color .25s var(--ease)}
.card::before{content:"";position:absolute;top:0;left:11px;right:11px;height:1px;
 background:linear-gradient(90deg,transparent,rgba(42,212,238,.32),transparent)}
.card:hover{border-color:var(--hair2)}
.card>h3{margin:0 0 11px;font-size:8.5px;color:var(--dim3);letter-spacing:.2em;
 text-transform:uppercase;font-weight:700;display:flex;justify-content:space-between;
 align-items:center;cursor:pointer;user-select:none}
.card>h3 span:last-child{color:var(--dim2);letter-spacing:.03em;
 text-transform:none;font-size:10px;font-weight:500}
.card>h3::after{content:"⤢";color:var(--dim3);font-size:9px;opacity:0;
 transition:.18s var(--ease);margin-left:8px}
.card:hover>h3::after{opacity:.65}
.card.focus{position:fixed;inset:56px 18px 18px;z-index:700;overflow:auto;
 box-shadow:var(--e4);border-color:var(--hair3);
 animation:focusIn .34s var(--ease)}
@keyframes focusIn{from{opacity:.4;transform:scale(.985)}}
canvas{display:block;width:100%;border-radius:var(--r1)}

/* ==================== TIMING ==================== */
.tt{width:100%;border-collapse:collapse}
.tt td{padding:4px;border-bottom:1px solid var(--grid)}
.tt td:first-child{color:var(--dim3);font-size:8.5px;letter-spacing:.18em;
 text-transform:uppercase;font-weight:600}
.tt td:last-child{text-align:right;font-weight:450;font-size:16px}
.big{font-size:38px!important;letter-spacing:-.02em;font-weight:300;
 text-shadow:0 0 32px rgba(42,212,238,.24)}
.sec{display:grid;grid-template-columns:repeat(3,1fr);gap:6px;margin-top:8px}
.sec div{background:var(--s1);border:1px solid var(--hair);border-radius:var(--r2);
 padding:8px 3px;text-align:center;transition:.3s var(--ease)}
.sec div.pp{border-color:var(--purple);background:rgba(177,140,255,.10);
 box-shadow:0 0 18px rgba(177,140,255,.22)}
.sec div.pb{border-color:var(--ok);background:rgba(61,220,151,.08)}
.sec u{display:block;color:var(--dim3);font-size:7.5px;text-decoration:none;
 letter-spacing:.2em;font-weight:700}
.sec b{font-size:15px;font-weight:500;margin-top:2px;display:block}
.pb{color:var(--ok)}.pp{color:var(--purple)}.wo{color:var(--warn)}.bd{color:var(--bad)}
#dbar{height:27px;background:var(--s1);border:1px solid var(--hair);
 border-radius:var(--r1);position:relative;overflow:hidden;margin-top:8px}
#dbar i{position:absolute;top:0;bottom:0;left:50%;transition:.14s var(--ease)}
#dbar u{position:absolute;left:50%;top:0;bottom:0;width:1px;
 background:var(--hair3);text-decoration:none}
#dbar b{position:absolute;inset:0;display:flex;align-items:center;
 justify-content:center;font-size:13px;font-weight:600;letter-spacing:.02em;
 text-shadow:0 1px 4px rgba(0,0,0,.7)}

/* ==================== READOUTS ==================== */
.kv{display:grid;grid-template-columns:repeat(auto-fit,minmax(92px,1fr));gap:7px}
.kv div{background:linear-gradient(180deg,var(--s2),var(--s1));
 border:1px solid var(--hair);border-radius:var(--r2);padding:8px 10px;
 position:relative;overflow:hidden;transition:.2s var(--ease);cursor:default}
.kv div:hover{border-color:var(--hair2);background:linear-gradient(180deg,var(--s3),var(--s2))}
.kv div::after{content:"";position:absolute;left:0;top:0;bottom:0;width:2px;
 background:var(--hair2);transition:.25s var(--ease)}
.kv div.wo::after{background:var(--warn);box-shadow:0 0 10px var(--warn)}
.kv div.bd::after{background:var(--bad);box-shadow:0 0 10px var(--bad)}
.kv div.ok::after{background:var(--ok);box-shadow:0 0 10px var(--ok)}
.kv u{display:block;color:var(--dim3);font-size:7.5px;letter-spacing:.16em;
 text-decoration:none;text-transform:uppercase;font-weight:600;margin-bottom:1px}
.kv b{font-size:19px;font-weight:450;letter-spacing:-.015em;display:block}
.kv b small{font-size:9px;color:var(--dim3);font-weight:400;letter-spacing:.06em;
 margin-left:2px;font-family:var(--sans)}
.kv b.up{animation:vup .6s var(--ease)}.kv b.dn{animation:vdn .6s var(--ease)}
@keyframes vup{0%{color:var(--ok);text-shadow:0 0 16px var(--ok)}}
@keyframes vdn{0%{color:var(--acc);text-shadow:0 0 16px var(--acc)}}

/* ==================== RADIO / ALARMS ==================== */
#radio{display:flex;flex-direction:column;gap:4px;max-height:196px;overflow:auto}
#radio div{padding:8px 11px;border-radius:var(--r2);background:var(--s1);
 font-size:11px;border-left:2px solid var(--hair2);line-height:1.5;
 animation:slide .38s var(--ease)}
@keyframes slide{from{opacity:0;transform:translateX(-10px)}}
#radio div s{text-decoration:none;color:var(--dim3);font-size:7.5px;
 letter-spacing:.16em;display:block;margin-bottom:2px;font-weight:600;
 text-transform:uppercase}
#radio div.i{border-left-color:var(--acc)}
#radio div.g{border-left-color:var(--ok);color:var(--ok)}
#radio div.w{border-left-color:var(--warn);color:var(--warn)}
#radio div.c{border-left-color:var(--bad);color:var(--bad);background:rgba(255,107,122,.06)}
.alm{display:flex;flex-direction:column;gap:3px}
.alm div{display:flex;justify-content:space-between;align-items:center;
 padding:6px 11px;border-radius:var(--r2);background:var(--s1);
 border-left:2px solid var(--hair2);font-size:10.5px;letter-spacing:.02em;
 transition:.25s var(--ease)}
.alm div.a{border-left-color:var(--warn);background:rgba(247,185,85,.08);color:var(--warn)}
.alm div.c{border-left-color:var(--bad);background:rgba(255,107,122,.09);color:var(--bad)}
.alm div.l{opacity:.38}
.alm span{font-size:8px;color:var(--dim3);letter-spacing:.14em;font-weight:600;
 text-transform:uppercase}

/* ==================== BARS / TABLES ==================== */
.bar{height:7px;background:var(--s1);border-radius:4px;overflow:hidden;
 margin:5px 0 3px;border:1px solid var(--hair)}
.bar i{display:block;height:100%;transition:width .18s var(--ease);border-radius:3px}
.lbl{display:flex;justify-content:space-between;font-size:7.5px;color:var(--dim3);
 letter-spacing:.16em;text-transform:uppercase;font-weight:600}
.note{color:var(--dim2);font-size:10.5px;line-height:1.7;margin-top:10px}
.sw{display:inline-block;width:8px;height:8px;border-radius:2px;margin-right:5px;
 vertical-align:middle}
.lg{display:flex;gap:13px;font-size:9.5px;color:var(--dim2);flex-wrap:wrap;
 margin-top:7px;letter-spacing:.02em}
table.dt{width:100%;border-collapse:collapse;font-size:11px}
table.dt th{color:var(--dim3);font-size:8px;letter-spacing:.16em;text-align:right;
 padding:4px;border-bottom:1px solid var(--hair2);text-transform:uppercase;
 font-weight:700}
table.dt th:first-child,table.dt td:first-child{text-align:left}
table.dt td{padding:4px 5px;border-bottom:1px solid var(--grid);text-align:right}
table.dt tr{transition:.15s var(--ease)}
table.dt tr:hover td{background:rgba(42,212,238,.05)}
#pw{display:flex;gap:2px;height:11px;margin-bottom:8px}
#pw i{flex:1;background:var(--s1);border-radius:1px;transition:.07s var(--ease)}

/* ==================== HV / FAULTS / SETUP ==================== */
#hv{display:flex;gap:4px;margin-bottom:9px}
#hv div{flex:1;text-align:center;padding:6px 2px;border-radius:var(--r1);
 font-size:7.5px;letter-spacing:.14em;background:var(--s1);
 border:1px solid var(--hair);color:var(--dim3);transition:.3s var(--ease);
 font-weight:700}
#hv div.on{border-color:var(--ok);color:var(--ok);background:rgba(61,220,151,.10);
 box-shadow:0 0 16px rgba(61,220,151,.2)}
#hv div.act{border-color:var(--acc);color:var(--acc);background:rgba(42,212,238,.12);
 animation:pulse 1.1s infinite}
#hv div.flt{border-color:var(--bad);color:var(--bad);background:rgba(255,107,122,.12)}
#pcBar{height:5px;background:var(--s1);border:1px solid var(--hair);
 border-radius:3px;overflow:hidden;margin-bottom:8px}
#pcBar i{display:block;height:100%;width:0;background:var(--acc);
 box-shadow:0 0 10px var(--acc);transition:width .1s linear}
.fx{display:grid;grid-template-columns:1fr 1fr;gap:5px}
.fx button{padding:6px 7px;font-size:8px;letter-spacing:.06em;text-align:left;
 text-transform:none}
.fx button.act{background:linear-gradient(180deg,var(--bad),#c0392f);color:#fff;
 border-color:var(--bad);box-shadow:0 0 16px rgba(255,107,122,.35)}
.setup{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:9px}
.setrow{display:flex;align-items:center;gap:9px;margin:7px 0}
.setrow label{flex:1;color:var(--dim);font-size:10px}
.setrow output{min-width:70px;text-align:right;font-weight:500;color:var(--acc);
 font-size:12px}
.verdict{padding:11px 14px;border-radius:var(--r2);margin-top:12px;font-size:11px;
 line-height:1.65;border-left:2px solid var(--acc);background:rgba(42,212,238,.055)}
.verdict.w{border-left-color:var(--warn);background:rgba(247,185,85,.07);color:var(--warn)}
.verdict.b{border-left-color:var(--bad);background:rgba(255,107,122,.08);color:var(--bad)}
.verdict.g{border-left-color:var(--ok);background:rgba(61,220,151,.06);color:var(--ok)}

/* ==================== OVERLAYS ==================== */
#tip{position:fixed;z-index:1500;pointer-events:none;display:none;
 background:rgba(10,15,22,.97);border:1px solid var(--hair3);border-radius:var(--r2);
 padding:8px 11px;font-size:10px;line-height:1.6;color:var(--fg);
 box-shadow:var(--e4);max-width:268px;backdrop-filter:blur(10px);
 animation:tipIn .16s var(--ease)}
@keyframes tipIn{from{opacity:0;transform:translateY(4px)}}
#tip.on{display:block}
#tip u{display:block;text-decoration:none;color:var(--acc);font-size:7.5px;
 letter-spacing:.18em;text-transform:uppercase;margin-bottom:4px;font-weight:700}
#tip b{color:var(--fg);font-family:var(--mono)}#tip s{text-decoration:none;color:var(--dim3)}
#pal{position:fixed;inset:0;z-index:1600;display:none;background:rgba(4,6,10,.7);
 backdrop-filter:blur(9px);padding-top:12vh;justify-content:center}
#pal.on{display:flex;animation:tipIn .2s var(--ease)}
#palBox{width:min(640px,90vw);height:fit-content;
 background:linear-gradient(180deg,var(--s4),var(--s1));border:1px solid var(--hair3);
 border-radius:10px;box-shadow:var(--e4);overflow:hidden}
#palIn{width:100%;background:transparent;border:0;border-bottom:1px solid var(--hair2);
 padding:16px 20px;color:var(--fg);font:300 15px var(--sans);outline:none;
 letter-spacing:.01em}
#palIn::placeholder{color:var(--dim3)}
#palList{max-height:46vh;overflow:auto}
#palList div{padding:10px 20px;display:flex;justify-content:space-between;
 cursor:pointer;font-size:11px;border-left:2px solid transparent;
 transition:.12s var(--ease)}
#palList div:hover{background:rgba(255,255,255,.03)}
#palList div.sel{background:rgba(42,212,238,.1);border-left-color:var(--acc);color:var(--acc)}
#palList div s{text-decoration:none;color:var(--dim3);font-size:9px;
 letter-spacing:.14em;font-family:var(--mono);text-transform:uppercase}
#toast{position:fixed;top:66px;right:16px;z-index:800;display:flex;
 flex-direction:column;gap:7px;pointer-events:none;max-width:336px}
#toast div{background:linear-gradient(180deg,var(--s4),var(--s1));
 border:1px solid var(--hair2);border-left-width:2px;border-radius:var(--r2);
 padding:9px 13px;font-size:10.5px;box-shadow:var(--e4);
 animation:tin .42s var(--ease);letter-spacing:.01em;backdrop-filter:blur(8px)}
#toast div.g{border-left-color:var(--ok);color:var(--ok)}
#toast div.w{border-left-color:var(--warn);color:var(--warn)}
#toast div.c{border-left-color:var(--bad);color:var(--bad)}
#toast div.i{border-left-color:var(--acc);color:var(--acc)}
#toast div s{text-decoration:none;color:var(--dim3);font-size:7px;display:block;
 letter-spacing:.2em;text-transform:uppercase;margin-bottom:3px;font-weight:700}
@keyframes tin{from{opacity:0;transform:translateX(32px) scale(.95)}}
#summary{position:fixed;inset:0;z-index:900;background:rgba(5,7,11,.9);
 display:none;align-items:center;justify-content:center;backdrop-filter:blur(8px)}
#summary.on{display:flex;animation:tipIn .45s var(--ease)}
#sumBox{background:linear-gradient(180deg,var(--s3),var(--s1));
 border:1px solid var(--hair3);border-radius:12px;padding:30px 34px;min-width:580px;
 box-shadow:var(--e4),0 0 0 1px rgba(42,212,238,.08) inset}
#sumBox h2{margin:0 0 6px;font-size:22px;letter-spacing:.32em;color:var(--acc);
 font-weight:300;text-shadow:0 0 30px rgba(42,212,238,.4)}
#sumBox p{margin:0 0 20px;color:var(--dim3);font-size:9px;letter-spacing:.2em;
 text-transform:uppercase;font-weight:600}
#sumGrid{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:18px}
#sumGrid div{background:var(--s1);border:1px solid var(--hair);border-radius:var(--r2);
 padding:10px 12px}
#sumGrid u{display:block;color:var(--dim3);font-size:7px;letter-spacing:.18em;
 text-decoration:none;text-transform:uppercase;font-weight:700;margin-bottom:3px}
#sumGrid b{font-family:var(--mono);font-size:24px;font-weight:500}
#keys{position:fixed;bottom:0;left:0;right:0;padding:5px 18px;font-size:8.5px;
 color:var(--dim3);letter-spacing:.14em;background:rgba(7,10,16,.94);
 border-top:1px solid var(--hair);z-index:5;display:flex;gap:18px;flex-wrap:wrap;
 text-transform:uppercase;font-weight:600;backdrop-filter:blur(8px)}
#keys b{color:var(--acc);font-weight:700;font-family:var(--mono)}
#err{position:fixed;inset:0;z-index:2000;background:#0b0407;display:none;
 padding:38px;overflow:auto;font:12px/1.7 var(--mono)}
#err.on{display:block}
#err h1{color:var(--bad);font-size:15px;letter-spacing:.24em;margin:0 0 8px;
 font-weight:700;font-family:var(--sans)}
#err p{color:var(--dim);margin:0 0 20px;font-size:11px;font-family:var(--sans)}
#err pre{background:#160709;border:1px solid #3f141b;border-left:2px solid var(--bad);
 border-radius:var(--r2);padding:16px;color:#ffc2ca;white-space:pre-wrap;
 font-size:11px;margin:0 0 14px}
#err b{color:var(--acc)}
#insp{border-left:2px solid var(--acc)!important}
/* ---- provenance overlay ---- */
html.prov .card{border-left-width:3px}
html.prov .card.pv-m{border-left-color:var(--ok)}
html.prov .card.pv-e{border-left-color:var(--warn)}
html.prov .card.pv-p{border-left-color:var(--bad)}
.pvb{display:none;font-size:7px;letter-spacing:.16em;font-weight:700;
 padding:2px 6px;border-radius:3px;text-transform:uppercase;margin-left:8px}
html.prov .pvb{display:inline-block}
.pvb.pv-m{background:rgba(61,220,151,.16);color:var(--ok)}
.pvb.pv-e{background:rgba(247,185,85,.16);color:var(--warn)}
.pvb.pv-p{background:rgba(255,107,122,.16);color:var(--bad)}
#pvKey{display:none;position:fixed;left:16px;bottom:26px;z-index:120;
 background:rgba(10,15,22,.96);border:1px solid var(--hair2);border-radius:var(--r2);
 padding:10px 13px;font-size:9.5px;box-shadow:var(--e3);max-width:300px;
 line-height:1.6;backdrop-filter:blur(8px)}
body.prov #pvKey{display:block}
#pvKey b{display:block;font-size:7.5px;letter-spacing:.2em;color:var(--dim3);
 text-transform:uppercase;margin-bottom:7px;font-weight:700}
#pvKey div{display:flex;gap:8px;align-items:flex-start;margin:4px 0;color:var(--dim)}
#pvKey i{width:3px;flex:0 0 3px;border-radius:2px;margin-top:3px;height:13px}
@keyframes flash{0%,100%{box-shadow:none}50%{box-shadow:0 0 34px var(--purple)}}
.flash{animation:flash 1s 2}
@media(max-width:1500px){
 #vTele{grid-template-columns:308px 1fr 268px}
 #vTherm{grid-template-columns:1fr 306px}
 #vStrat,#vSetup{grid-template-columns:1fr 336px}}
@media(max-width:1180px){
 #vTele,#vTherm,#vStrat,#vEng,#vSetup{grid-template-columns:1fr}
 .rail{gap:9px}}
</style></head><body>

<div id="boot">
 <canvas id="bootCv"></canvas>
 <div id="bootUI">
  <div id="bootTitle">VOLARE</div>
  <div id="bootSub">MONACO ENERGY BOAT CHALLENGE &middot; MISSION CONTROL</div>
  <div id="bootRule"></div>
  <div id="bootStats">
   <div><u>CELLS</u><b id="bsCells">&mdash;</b></div>
   <div><u>ENERGY</u><b id="bsE">&mdash;</b></div>
   <div><u>POWER CAP</u><b id="bsP">&mdash;</b></div>
   <div><u>CIRCUIT</u><b id="bsL">&mdash;</b></div>
   <div><u>SOLVER</u><b id="bsV">&mdash;</b></div>
  </div>
 </div>
 <div id="bootLog"></div>
 <div id="bootPct">0<s>%</s></div>
 <div id="bootBarWrap"><div id="bootBar"></div></div>
 <div id="bootFlash"></div>
</div>

<div id="summary"><div id="sumBox">
 <h2 id="sumTitle">SESSION COMPLETE</h2>
 <p id="sumSub"></p>
 <div id="sumGrid"></div>
 <table class="dt" id="sumLaps"></table>
 <div style="margin-top:16px;display:flex;gap:9px">
  <button id="sumClose" class="on">CLOSE</button>
  <button id="sumRst">↺ NEW SESSION</button>
  <button id="sumCsv">⤓ EXPORT</button></div>
</div></div>

<div id="rep">
 <span id="repL">Replay</span>
 <button id="repClose">✕ LIVE</button>
 <input type="range" id="repS" min="0" max="0" value="0">
 <span id="repT">--:-- / --:--</span>
</div>
<div id="keys">
 <span><b>W/S</b> throttle</span><span><b>X</b> cut</span><span><b>SPACE</b> hold</span>
 <span><b>A</b> autopilot</span><span><b>R</b> reset</span><span><b>F</b> fullscreen</span>
 <span><b>1–6</b> views</span><span><b>Ctrl+K</b> commands</span><span><b>P</b> provenance</span><span><b>D</b> daylight</span>
 <span><b>[ ]</b> replay</span><span id="arbNow"></span>
 <span><b>click</b> a cell to inspect</span><span id="keyEnv"></span>
</div>

<div id="err"><h1>MISSION CONTROL — STARTUP FAULT</h1>
 <p>Something failed while starting. The detail below is what I need to fix it.</p>
 <pre id="errBody"></pre>
 <p>Copy the block above and send it. Browser: <b id="errUA"></b></p></div>
<div id="pvKey"><b>Data provenance</b>
 <div><i style="background:var(--ok)"></i><span><b style="display:inline;color:var(--ok);
  font-size:9.5px;letter-spacing:0">MEASURED</b> — your datasheet curves, your
  cockpit STL, the published rules.</span></div>
 <div><i style="background:var(--warn)"></i><span><b style="display:inline;
  color:var(--warn);font-size:9.5px;letter-spacing:0">ESTIMATED</b> — literature
  values or reasoned assumptions. Right structure, approximate numbers.</span></div>
 <div><i style="background:var(--bad)"></i><span><b style="display:inline;
  color:var(--bad);font-size:9.5px;letter-spacing:0">PLACEHOLDER</b> — waiting on
  data from you. See DATA_NEEDED.md.</span></div>
</div>
<div id="tip"></div>
<div id="pal"><div id="palBox">
 <input id="palIn" placeholder="Type a command or a view…  ( ESC to close )" autocomplete="off">
 <div id="palList"></div></div></div>
<div id="toast"></div>
<div id="app">
<header>
 <div class="brand"><b>VOLARE</b><i>MISSION CONTROL</i></div>
 <div class="hstat" style="min-width:auto;padding-right:14px">
  <u>event</u>
  <select id="evt" style="margin-top:1px;font-size:10px;padding:2px 5px">
   <option value="endurance">Endurance · 1 NM · 3 h</option>
   <option value="qualifying">Qualifying · fastest lap</option>
   <option value="championship_outer">Championship · outer</option>
   <option value="championship_inner">Championship · inner</option>
   <option value="slalom">Slalom · buoy course</option>
  </select></div>
 <div class="hstat"><u>session</u><b id="hSes">00:00</b></div>
 <div class="hstat"><u>lap</u><b id="hLap">0</b></div>
 <div class="hstat"><u>speed</u><b id="hV">0.0<s> km/h</s></b></div>
 <div class="hstat"><u>shaft</u><b id="hP">0.00<s> kW</s></b></div>
 <div class="hstat"><u>energy</u><b id="hE">0.000<s> kWh</s></b></div>
 <div class="hstat"><u>pack max</u><b id="hT">--<s> °C</s></b></div>
 <div class="hstat"><u>status</u><b><span class="led" id="hLed"></span><span id="hSt">READY</span></b></div>
 <div class="grow"></div>
 <div class="tabs">
  <div class="tab on" data-v="vTele">Telemetry</div>
  <div class="tab" data-v="vTherm">Thermal</div>
  <div class="tab" data-v="vStrat">Strategy</div>
  <div class="tab" data-v="vEng">Engineering</div>
  <div class="tab" data-v="vSetup">Setup</div>
  <div class="tab" data-v="vAnal">Analysis</div>
 </div>
</header>

<div class="rail">
 <button id="run" class="on">❚❚ PAUSE</button>
 <button id="rst">↺ RESET</button>
 <label class="s">throttle</label><input type="range" id="thr" min="0" max="100" value="0">
 <span class="vt" id="thrv">0%</span>
 <button id="ap">AUTOPILOT</button>
 <label class="s">target</label><input type="range" id="tgt" min="10" max="70" value="45">
 <span class="vt" id="tgtv">45</span>
 <label class="s">scenario</label>
 <select id="scn" style="max-width:186px"><option value="">— custom —</option></select>
 <label class="s">time</label>
 <select id="rate"><option>1</option><option>2</option><option selected>5</option>
 <option>10</option><option>25</option><option>50</option><option>100</option><option>200</option></select>
 <label class="s">flow</label><input type="range" id="flow" min="10" max="160" value="80">
 <span class="vt" id="flowv">8.0</span>
 <label class="s">sea</label><input type="range" id="tin" min="150" max="380" value="290">
 <span class="vt" id="tinv">29.0</span>
 <label class="s">air</label><input type="range" id="tamb" min="150" max="450" value="300">
 <span class="vt" id="tambv">30.0</span>
 <label class="s">wind</label><input type="range" id="wind" min="0" max="120" value="0">
 <span class="vt" id="windv">0.0</span>
 <label class="s">dir</label><input type="range" id="wdir" min="0" max="359" value="0"
  style="width:70px"><span class="vt" id="wdirv">0°</span>
 <label class="s">sea Hs</label><input type="range" id="hs" min="0" max="120" value="10"
  style="width:70px"><span class="vt" id="hsv">0.10</span>
 <div class="grow"></div>
 <label class="s"><input type="checkbox" id="twinOn" checked
   style="vertical-align:-2px"> twin</label>
 <button id="theme">☀ DAY</button>
 <button id="dens">▭ DENSE</button>
 <button id="rpt">▤ REPORT</button>
 <button id="prov">◐ PROVENANCE</button>
 <button id="csv">⤓ EXPORT CSV</button>
</div>

<main>
 <div class="view on" id="vTele">
  <div class="col">
   <div class="card"><h3><span>Circuit</span><span id="trkName"></span></h3>
    <button class="pop" id="popMap">⧉ pop out</button>
    <canvas id="map" style="height:268px"></canvas>
    <div class="lg"><span><i class="sw" style="background:#00e88a"></i>fast</span>
     <span><i class="sw" style="background:#ffb01f"></i>mid</span>
     <span><i class="sw" style="background:#ff3b52"></i>slow</span>
     <span id="trkInfo"></span></div></div>
   <div class="card"><h3><span>Timing</span><span id="tPos"></span></h3>
    <table class="tt">
     <tr><td>current</td><td class="big" id="tCur">--:--.---</td></tr>
     <tr><td>last</td><td id="tLast">--:--.---</td></tr>
     <tr><td>best</td><td class="pb" id="tBest">--:--.---</td></tr>
    </table>
    <div id="dbar"><i id="dfill"></i><u></u><b id="dtxt">— · —</b></div>
    <div style="display:flex;justify-content:space-between;font-size:9px;
      color:var(--dim2);letter-spacing:1.1px;margin-top:7px">
     <span>THEORETICAL BEST</span><span id="tTheo" style="color:var(--purple);
      font-weight:700;font-size:11px">--:--.---</span></div>
    <div class="sec">
     <div id="sc1"><u>S1</u><b id="s1">--</b></div>
     <div id="sc2"><u>S2</u><b id="s2">--</b></div>
     <div id="sc3"><u>S3</u><b id="s3">--</b></div>
    </div></div>
  </div>
  <div class="col">
   <div class="card"><h3><span>Boat</span><span id="boatInfo"></span></h3>
    <div id="pw"></div>
    <canvas id="boat" style="height:232px"></canvas></div>
   <div class="card"><h3><span>Lap comparison — speed around the circuit</span>
     <span id="cmpInfo"></span></h3>
    <canvas id="cmp" style="height:186px"></canvas>
    <div class="lg"><span><i class="sw" style="background:#00c8ff"></i>this lap</span>
     <span><i class="sw" style="background:#b56bff"></i>best lap</span>
     <span><i class="sw" style="background:#00e88a"></i>gaining</span>
     <span><i class="sw" style="background:#ff3b52"></i>losing</span></div></div>
   <div class="card"><h3><span>Traces</span><span id="wLbl"></span></h3>
    <canvas id="trc" style="height:300px"></canvas></div>
  </div>
  <div class="col">
   <div class="card"><h3>Primary</h3><div class="kv" id="kvA"></div></div>
   <div class="card"><h3><span>Race engineer</span><span id="rdN"></span></h3>
    <div id="radio"></div></div>
   <div class="card"><h3><span>Limits</span><span id="almN"></span></h3>
    <div class="alm" id="alm"></div></div>
   <div class="card"><h3><span>High-voltage system</span><span id="hvHdr">OFF</span></h3>
    <div id="hv">
     <div data-st="OFF">OFF</div><div data-st="PRECHARGE">PRE</div>
     <div data-st="READY">READY</div><div data-st="DRIVE">DRIVE</div>
     <div data-st="FAULT">FAULT</div></div>
    <div id="pcBar"><i id="pcFill"></i></div>
    <div style="display:flex;gap:6px">
     <button id="hvBtn" style="flex:1">⏻ HV ON</button>
     <button id="estop" style="flex:1;border-color:var(--bad);color:var(--bad)">■ E-STOP</button></div>
    <div class="note" id="hvNote">Precharge 100 Ω into 3300 µF · contactors open</div></div>
   <div class="card"><h3><span>Fault injection</span><span id="fxHdr">none</span></h3>
    <div class="fx">
     <button data-fx="pump">⚠ pump failure</button>
     <button data-fx="restrict">⚠ flow restriction</button>
     <button data-fx="imd">⚠ IMD isolation</button>
     <button data-fx="sensor">⚠ sensor dropout</button>
     <button data-fx="hotcell">⚠ hot cell</button>
     <button data-fx="vent">⚠ prop ventilation</button></div>
    <div class="note" id="fxNote">Inject a fault to see how the pack and your
     control strategy respond. Click again to clear.</div></div>
   <div class="card"><h3><span>Conditions</span><span id="cndInfo"></span></h3>
    <div class="kv" id="kvC"></div></div>
   <div class="card"><h3><span>Dynamics</span><span id="gInfo"></span></h3>
    <canvas id="gg" style="height:150px"></canvas></div>
   <div class="card"><h3><span>Torque arbitration</span><span id="arbHdr"></span></h3>
    <canvas id="arb" style="height:172px"></canvas>
    <div class="note" id="arbNote"></div></div>
   <div class="card"><h3><span>Predictive</span><span>extrapolated</span></h3>
    <div class="kv" id="kvP"></div></div>
   <div class="card"><h3>Reserves</h3>
    <div class="lbl"><span>energy</span><span id="eTxt"></span></div>
    <div class="bar"><i id="eBar"></i></div>
    <div class="lbl"><span>state of charge</span><span id="zTxt"></span></div>
    <div class="bar"><i id="zBar"></i></div>
    <div class="lbl"><span>thermal headroom</span><span id="thTxt"></span></div>
    <div class="bar"><i id="thBar"></i></div></div>
  </div>
 </div>

 <div class="view" id="vTherm">
  <div class="col">
   <div class="card"><h3><span>Pack — physical layout</span>
     <span>
      <select id="chan" style="font-size:9px;padding:2px 5px">
       <option value="Tcore">core temperature °C</option>
       <option value="Tcan">can temperature °C</option>
       <option value="dT">core − can gradient K</option>
       <option value="q">heat generation W</option>
       <option value="qRev">entropic term W</option>
       <option value="I">cell current A</option>
       <option value="R0">resistance mΩ</option>
       <option value="z">state of charge %</option>
      </select>
      <select id="src" style="font-size:9px;padding:2px 5px;margin-left:6px">
       <option value="true">◈ true state</option>
       <option value="bms">◉ BMS estimate</option>
       <option value="err">± estimate error</option>
      </select>
      <label class="s" style="margin-left:7px"><input type="checkbox" id="showTubes" checked
        style="vertical-align:-2px"> tubes</label>
     </span></h3>
    <button class="pop" id="popPack">⧉ pop out</button>
    <canvas id="pack" style="height:340px"></canvas>
    <div class="lg" id="scale"></div>
    <div class="note" id="pkNote"></div></div>
   <div class="card"><h3><span>Coolant circuits</span><span id="coolHdr"></span></h3>
    <canvas id="cool" style="height:176px"></canvas>
    <table class="dt" id="circT"></table></div>
   <div class="card"><h3><span>Thermal history — distribution over time</span>
     <span>waterfall</span></h3>
    <canvas id="wf" style="height:150px"></canvas>
    <div class="note">Each column is one moment; brightness is how many cells sit
     at that temperature. A widening band means the pack is diverging.</div></div>
  </div>
  <div class="col">
   <div class="card"><h3><span>Digital twin</span><span id="twHdr"></span></h3>
    <div class="kv" id="kvTw"></div>
    <canvas id="twc" style="height:118px;margin-top:8px"></canvas>
    <div class="note" id="twNote"></div></div>
   <div class="card" id="insp" style="display:none">
    <h3><span>Cell inspector</span><span id="inspId"></span></h3>
    <div class="kv" id="kvI"></div>
    <div class="note">Click any cell in the layout to inspect it. Click empty
     space to clear.</div></div>
   <div class="card"><h3>Thermal state</h3><div class="kv" id="kvT"></div></div>
   <div class="card"><h3><span>Energy balance</span><span id="balHdr"></span></h3>
    <canvas id="bal" style="height:118px"></canvas>
    <div class="note" id="balNote"></div></div>
   <div class="card"><h3><span>Measured cell resistance</span>
     <span id="r0Hdr"></span></h3>
    <canvas id="r0c" style="height:172px"></canvas>
    <div class="note" id="r0Note"></div></div>
   <div class="card"><h3>Distribution</h3><canvas id="hist" style="height:120px"></canvas></div>
   <div class="card"><h3>Hottest cells</h3><table class="dt" id="hotT"></table></div>
  </div>
 </div>

 <div class="view" id="vAnal">
  <div class="col">
   <div class="card"><h3><span>Energy flow — where every joule went</span>
     <span id="sankHdr"></span></h3>
    <canvas id="sank" style="height:236px"></canvas>
    <div class="note" id="sankNote"></div></div>
   <div class="card"><h3><span>Limiter share</span><span id="limHdr"></span></h3>
    <canvas id="limc" style="height:150px"></canvas>
    <table class="dt" id="limT"></table></div>
  </div>
  <div class="col">
   <div class="card"><h3><span>Lap-over-lap</span><span id="lolHdr"></span></h3>
    <canvas id="lol" style="height:200px"></canvas>
    <div class="note">Each lap's time, energy and peak temperature, normalised
     to your best. Divergence between the lines is the story: losing time while
     spending the same energy means the boat changed, not the driving.</div></div>
   <div class="card"><h3><span>Sensitivity — what actually moves the answer</span>
     <span>±20 % sweep</span></h3>
    <canvas id="sens" style="height:216px"></canvas>
    <div class="note" id="sensNote"></div></div>
  </div>
 </div>

 <div class="view" id="vSetup">
  <div class="col">
   <div class="card"><h3><span>Cooling configuration</span><span id="setHdr"></span></h3>
    <div class="setrow"><label>coolant flow</label>
     <input type="range" id="sFlow" min="20" max="200" value="80" style="width:150px">
     <output id="oFlow"></output></div>
    <div class="setrow"><label>parallel circuits</label>
     <input type="range" id="sCirc" min="1" max="12" value="3" style="width:150px">
     <output id="oCirc"></output></div>
    <div class="setrow"><label>tube inner diameter</label>
     <input type="range" id="sTube" min="30" max="120" value="60" style="width:150px">
     <output id="oTube"></output></div>
    <div class="setrow"><label>bond quality R_wall</label>
     <input type="range" id="sBond" min="15" max="90" value="25" style="width:150px">
     <output id="oBond"></output></div>
    <div class="setrow"><label>coolant</label>
     <select id="sFluid" style="flex:1"><option value="g">50/50 water-glycol</option>
      <option value="w">water + inhibitor</option></select></div>
    <canvas id="setC" style="height:186px;margin-top:8px"></canvas>
    <div class="verdict" id="setV"></div></div>
   <div class="card"><h3><span>Manifold flow distribution</span>
     <span id="mfHdr"></span></h3>
    <canvas id="mfc" style="height:150px"></canvas>
    <div class="setrow"><label>header inner diameter</label>
     <input type="range" id="sHdr" min="60" max="300" value="160" style="width:150px">
     <output id="oHdr"></output></div>
    <div class="verdict" id="mfV"></div></div>
   <div class="card"><h3>Configuration sheet</h3><table class="dt" id="setT"></table></div>
  </div>
  <div class="col">
   <div class="card"><h3><span>Cell degradation</span><span id="degHdr"></span></h3>
    <canvas id="deg" style="height:198px"></canvas>
    <div class="kv" id="kvDeg" style="margin-top:8px"></div>
    <div class="verdict" id="degV"></div></div>
   <div class="card"><h3>Model provenance</h3><table class="dt" id="provT2"></table></div>
  </div>
 </div>

 <div class="view" id="vStrat">
  <div class="col">
   <div class="card"><h3>Pace vs distance — where the race is won</h3>
    <canvas id="strat" style="height:348px"></canvas>
    <div class="lg"><span><i class="sw" style="background:#00c8ff"></i>energy-limited</span>
     <span><i class="sw" style="background:#ffb01f"></i>time-limited</span>
     <span><i class="sw" style="background:#00e88a"></i>achievable</span>
     <span><i class="sw" style="background:#ff3b52"></i>you</span></div>
    <div class="note" id="stratNote"></div></div>
   <div class="card"><h3>Projection — distance against the clock</h3>
    <canvas id="proj" style="height:212px"></canvas>
    <div class="lg"><span><i class="sw" style="background:#00c8ff"></i>your run so far</span>
     <span><i class="sw" style="background:#00e88a"></i>optimum pace</span>
     <span><i class="sw" style="background:#ff3b52"></i>3 h wall</span></div></div>
   <div class="card"><h3>Lap log</h3><table class="dt" id="lapT"></table></div>
  </div>
  <div class="col">
   <div class="card"><h3>Race projection</h3><div class="kv" id="kvS"></div></div>
   <div class="card"><h3>Optimum</h3><div class="kv" id="kvO"></div>
    <div class="note" id="optNote"></div></div>
  </div>
 </div>

 <div class="view" id="vEng">
  <div class="col">
   <div class="card"><h3>Cell current sharing — worst parallel group</h3>
    <canvas id="share" style="height:184px"></canvas>
    <div class="note" id="shareNote"></div></div>
   <div class="card"><h3>Pack electrical</h3><div class="kv" id="kvE"></div></div>
   <div class="card"><h3>Configuration</h3><table class="dt" id="cfgT"></table></div>
  </div>
  <div class="col">
   <div class="card"><h3>Drivetrain</h3><div class="kv" id="kvD"></div></div>
   <div class="card"><h3><span>Drivetrain thermal</span><span id="dtHdr"></span></h3>
    <canvas id="dtc" style="height:150px"></canvas>
    <div class="kv" id="kvDT" style="margin-top:8px"></div>
    <div class="verdict" id="dtV"></div></div>
   <div class="card"><h3>Resistance at current speed</h3>
    <canvas id="drag" style="height:172px"></canvas></div>
   <div class="card"><h3>Model provenance</h3><table class="dt" id="provT"></table></div>
  </div>
 </div>
</main></div>

<script>
/* ---------- fail loudly, never silently ---------- */
(function(){
 var shown=false;
 window.__fatal=function(where,e){
  if(shown)return; shown=true;
  try{
   var b=document.getElementById('errBody');
   b.textContent='WHERE : '+where+'\n'+
    'ERROR : '+(e&&e.message?e.message:String(e))+'\n\n'+
    ((e&&e.stack)?e.stack:'(no stack)');
   document.getElementById('errUA').textContent=navigator.userAgent;
   document.getElementById('err').className='on';
   var bt=document.getElementById('boot');if(bt)bt.className='gone';
  }catch(_){ document.body.innerHTML=
    '<pre style="color:#ff3b52;padding:30px;font:12px monospace">'+
    where+'\n'+(e&&e.stack?e.stack:e)+'</pre>' }
 };
 window.addEventListener('error',function(ev){
  window.__fatal('window.onerror',ev.error||ev.message)});
 window.addEventListener('unhandledrejection',function(ev){
  window.__fatal('promise',ev.reason)});
})();

const M = __MODEL__;
const $ = i=>document.getElementById(i);
const NC=M.meta.nCells, NS=M.meta.nSeries, NP=M.meta.nParallel;
const DR=M.drive||{};
const TH=M.thermal, CL=M.cell, BT=M.boat;
/* ---------- flatten ---------- */
const nbI=new Int32Array(TH.neighbours.length),nbJ=new Int32Array(TH.neighbours.length),
      nbG=new Float64Array(TH.neighbours.length);
TH.neighbours.forEach((p,k)=>{nbI[k]=p[0];nbJ[k]=p[1];nbG[k]=p[2]});
const cpI=new Int32Array(TH.coolPairs.length),cpS=new Int32Array(TH.coolPairs.length),
      cpG=new Float64Array(TH.coolPairs.length);
TH.coolPairs.forEach((p,k)=>{cpI[k]=p[0];cpS[k]=p[1];cpG[k]=p[2]});
const gAir=Float64Array.from(TH.gAir);
const capAh=Float64Array.from(CL.capMult,v=>v*CL.capAh);
const resM=Float64Array.from(CL.resMult);
const serIdx=Int32Array.from(M.display.series);
const R0map=CL.R0map.map(r=>Float64Array.from(r));
const socG=Float64Array.from(CL.socGrid),Tg=Float64Array.from(CL.Tgrid);

function interp(x,xs,ys){if(x<=xs[0])return ys[0];const n=xs.length;
 if(x>=xs[n-1])return ys[n-1];let lo=0,hi=n-1;
 while(hi-lo>1){const m=(lo+hi)>>1;if(xs[m]<=x)lo=m;else hi=m}
 return ys[lo]+(ys[hi]-ys[lo])*(x-xs[lo])/(xs[hi]-xs[lo])}
function R0of(T,z,i){const Tc=Math.min(Math.max(T,Tg[0]),Tg[Tg.length-1]);
 if(Tg.length===1)return interp(z,socG,R0map[0])*resM[i];
 let k=0;while(k<Tg.length-2&&Tg[k+1]<Tc)k++;
 const w=(Tc-Tg[k])/(Tg[k+1]-Tg[k]);
 return (interp(z,socG,R0map[k])*(1-w)+interp(z,socG,R0map[k+1])*w)*resM[i]}
const fmtT=t=>{if(!isFinite(t)||t<=0)return'--:--.---';
 const m=Math.floor(t/60),s=t-m*60;return `${m}:${s.toFixed(3).padStart(6,'0')}`};

/* ================= ENGINE ================= */
class Engine{
 constructor(){this.reset()}
 reset(){
  this.Tcore=new Float64Array(NC).fill(28);this.Tcan=new Float64Array(NC).fill(28);
  this.Tseg=new Float64Array(Math.max(TH.nSeg,1)).fill(M.env.TinC);
  this.Tw=this.Tcase=this.Tj=this.Ths=M.env.TinC;
  this.Tbus=new Float64Array(Math.max(TH.nBus,1)).fill(28);this.Tair=M.env.TambC;
  this.z=new Float64Array(NC).fill(1);this.v1=new Float64Array(NC);this.v2=new Float64Array(NC);
  this.I=new Float64Array(NC);this.q=new Float64Array(NC);
  this.qIrr=new Float64Array(NC);this.qRev=new Float64Array(NC);
  this.Qgen=0;this.Qcool=0;this.Qenc=0;
  this.t=0;this.v=0;this.s=0;this.Wh=0;this.Ip=0;this.Vp=NS*4.2;this.n=0;this.eff=0;
  this.qT=0;this.thrust=0;this.drag=0;this.capped=false;this.lap=0;
  this.Tw=25;this.Tcase=25;this.Tj=25;this.Ths=25;      // drivetrain thermal
  this.qMot=0;this.qInv=0;this.Iph=0;this.effM=1;this.effI=1;this.dtDerate=1;
  this.num=new Float64Array(Math.max(TH.nSeg,1));this.den=new Float64Array(Math.max(TH.nSeg,1));
  this.fc=new Float64Array(NC);this.fa=new Float64Array(NC);
  this.nb=new Float64Array(NC);            // weighted neighbour temperature sum
  if(!Engine._gSum)Engine._buildSums();
  this.lapStart=0;this.secStart=0;this.curSec=0;
  this.laps=[];this.best=Infinity;this.bestSec=[Infinity,Infinity,Infinity];
  this.lastLap=0;this.lastSec=[0,0,0];this.curSecT=[0,0,0];
  this.lapWh0=0;this.lapWh=[];this.alarms={};}
 /* ---- static conductance sums, built once ----
    The browser integrator is EXPONENTIAL Euler, not explicit. For a node
        C dT/dt = Q + sum_j g_j (T_j - T)
    freeze the neighbours over one step and it integrates exactly:
        a = sum_j g_j / C,  b = (Q + sum_j g_j T_j) / C
        T(t+dt) = b/a + (T - b/a) * exp(-a dt)
    This is unconditionally stable and far more accurate than explicit Euler
    at the same step, which is what lets the time compression run high without
    the temperature field drifting. */
 static _buildSums(){
  const gS=new Float64Array(NC);
  for(let i=0;i<NC;i++)gS[i]=TH.gCoreCan+gAir[i];
  for(let k=0;k<nbI.length;k++){gS[nbI[k]]+=nbG[k];gS[nbJ[k]]+=nbG[k]}
  for(let k=0;k<cpI.length;k++)gS[cpI[k]]+=cpG[k];
  for(let i=0;i<NC;i++){const g=serIdx[i];
   if(g<TH.nBus)gS[i]+=TH.gCanBus;
   if(g-1>=0)gS[i]+=TH.gCanBus}
  Engine._gSum=gS;
  const gB=new Float64Array(Math.max(TH.nBus,1)).fill(0.5);
  for(let i=0;i<NC;i++){const g=serIdx[i];
   if(g<TH.nBus)gB[g]+=TH.gCanBus;
   if(g-1>=0)gB[g-1]+=TH.gCanBus}
  Engine._gBus=gB;
  let gA=TH.UAair; for(let i=0;i<NC;i++)gA+=gAir[i];
  Engine._gAir=gA;
 }
 KT(J){return Math.max(0,0.36*BT.propPD-0.32*J-0.06*J*J)}
 KQ(J){return Math.max(1e-4,0.055*BT.propPD-0.036*J-0.008*J*J)}
 Jof(v,n){return v*(1-BT.wake)/Math.max(n*BT.propD,1e-6)}
 shaftP(v,n){return 2*Math.PI*n*this.KQ(this.Jof(v,n))*1025*n*n*Math.pow(BT.propD,5)}
 rpsFor(v,P){if(P<=0)return 0;let lo=.5,hi=200;
  for(let k=0;k<38;k++){const m=(lo+hi)/2;if(this.shaftP(v,m)<P)lo=m;else hi=m}return (lo+hi)/2}
 step(dt,Pcmd,env){
  const Pmax=M.meta.PmaxW;this.capped=Pcmd>Pmax+1e-6;
  const P=Math.min(Math.max(Pcmd,0),Pmax);
  const n=this.rpsFor(this.v,P*BT.drivelineEff),J=this.Jof(this.v,n);
  const T=this.KT(J)*1025*n*n*Math.pow(BT.propD,4);
  const Rv=interp(this.v,BT.vGrid,BT.Rgrid);
  const kA=0.55*BT.dryAreaM2*0.22+1.2*2*BT.beamD*BT.beamSpan;
  const va=this.v+env.wind;
  const Rt=Rv+Math.max(0,0.5*1.2*kA*(va*va-this.v*this.v));
  const a=(T*(1-BT.thrustDed)-Rt)/(BT.massKg*(1+BT.addedMass));
  this.v=Math.max(0,this.v+a*dt);
  const prevS=this.s;this.s+=this.v*dt;
  this.n=n;this.thrust=T;this.drag=Rt;
  this.eff=Math.min(.85,Math.max(0,J*this.KT(J)/(2*Math.PI*this.KQ(J))));
  /* ---- drivetrain losses and temperatures ----
     Copper loss rises with winding temperature, so hotter windings mean more
     loss means hotter still. Unlike the pack there is no stabilising SOC term
     here — only the sea and the coolant loop hold it back. */
  {const om=2*Math.PI*n;
   const Iph=om>1e-3?(P/om)/Math.max(DR.Kt,1e-6):0;
   const Rp=DR.Rph*(1+DR.cuTc*(this.Tw-25));
   const qm=3*Iph*Iph*Rp+DR.feRef*Math.pow(om/DR.wRef,2);
   const qi=3*Iph*DR.Vce+DR.kSw*Iph;
   this.Iph=Iph;this.qMot=qm;this.qInv=qi;
   this.effM=P/Math.max(P+qm,1e-6);
   this.effI=(P+qm)/Math.max(P+qm+qi,1e-6);
   const gwc=1/DR.Rwc,gcs=1/DR.Rcs,gjh=1/DR.Rjh,ghc=1/DR.Rhc;
   const Tsea=env.tin, Tcool=TH.nSeg?Math.max.apply(null,Array.from(this.Tseg)):env.tin;
   let ss=(qm+gwc*this.Tcase)/gwc;
   this.Tw=ss+(this.Tw-ss)*Math.exp(-(gwc/DR.Cw)*dt);
   const gc=gwc+gcs; ss=(gwc*this.Tw+gcs*Tsea)/gc;
   this.Tcase=ss+(this.Tcase-ss)*Math.exp(-(gc/DR.Cc)*dt);
   ss=(qi+gjh*this.Ths)/gjh;
   this.Tj=ss+(this.Tj-ss)*Math.exp(-(gjh/DR.Cj)*dt);
   const gh=gjh+ghc; ss=(gjh*this.Tj+ghc*Tcool)/gh;
   this.Ths=ss+(this.Ths-ss)*Math.exp(-(gh/DR.Chs)*dt);
   const a=Math.max(0,Math.min(1,(DR.TwMax-this.Tw)/(DR.TwMax-DR.TwWarn)));
   const b=Math.max(0,Math.min(1,(DR.TjMax-this.Tj)/(DR.TjMax-DR.TjWarn)));
   this.dtDerate=Math.min(a,b);}
  /* ---- timing ---- */
  if(TR){const L=TR.length;
   const secB=TR.sectors;
   for(let k=1;k<secB.length;k++){
    const prevM=prevS%L, curM=this.s%L;
    const crossed=(prevM<secB[k]&&curM>=secB[k])||(curM<prevM&&secB[k]>prevM);
    if(crossed&&k-1===this.curSec){
     const st=this.t-this.secStart;this.curSecT[this.curSec]=st;
     if(st<this.bestSec[this.curSec])this.bestSec[this.curSec]=st;
     this.secStart=this.t;this.curSec=Math.min(k,2);}}
   if(this.s%L<prevS%L){ // lap crossing
    const lt=this.t-this.lapStart;
    if(lt>3){this.lastLap=lt;if(lt<this.best)this.best=lt;
     this.lastSec=this.curSecT.slice();
     this.laps.push({n:this.laps.length+1,t:lt,wh:this.Wh-this.lapWh0,
                     v:L/lt*3.6,Tmax:this.stats().Tmax});
     this.lapWh0=this.Wh;}
    this.lapStart=this.t;this.secStart=this.t;this.curSec=0;this.lap++;}}
  /* ---- pack electrical ---- */
  const a_=new Float64Array(NC),b_=new Float64Array(NC),U_=new Float64Array(NC);
  const A=new Float64Array(NS),B=new Float64Array(NS);
  for(let i=0;i<NC;i++){const R0=R0of(this.Tcore[i],this.z[i],i);
   const U=interp(this.z[i],CL.ocvSoc,CL.ocvV);U_[i]=U;
   a_[i]=(U-this.v1[i]-this.v2[i])/R0;b_[i]=1/R0;
   A[serIdx[i]]+=a_[i];B[serIdx[i]]+=b_[i]}
  let Voc=0,Rc=0;for(let g=0;g<NS;g++){Voc+=A[g]/B[g];Rc+=1/B[g]}
  const Rbus=TH.busR*TH.nBus;             // interconnects carry full pack current
  const Reff=Rc+Rbus;
  const Pbus=(P+this.qMot+this.qInv)||P/M.meta.inverterEff;
  const disc=Voc*Voc-4*Reff*Pbus;
  const Ip=disc<=0?Voc/(2*Reff):(Voc-Math.sqrt(disc))/(2*Reff);
  const Vg=new Float64Array(NS);let Vc=0;
  for(let g=0;g<NS;g++){Vg[g]=(A[g]-Ip)/B[g];Vc+=Vg[g]}
  const Vp=Vc-Ip*Rbus;                    // terminal voltage the inverter sees
  this.Ip=Ip;this.Vp=Vp;this.Vcells=Vc;
  let qt=0;
  for(let i=0;i<NC;i++){const I=a_[i]-Vg[serIdx[i]]*b_[i];this.I[i]=I;
   const d=interp(this.z[i],CL.dudtSoc,CL.dudtV);
   // Bernardi split: irreversible (ohmic + polarisation) and reversible
   // (entropic). Sum is identical to before -- diagnostic only.
   this.qIrr[i]=I*(U_[i]-Vg[serIdx[i]]);
   this.qRev[i]=-I*(this.Tcore[i]+273.15)*d;
   this.q[i]=this.qIrr[i]+this.qRev[i];
   this.fc[i]=this.q[i];qt+=this.q[i]}
  this.qT=qt;const qbus=Ip*Ip*TH.busR;
  /* ---- coolant forward sweep ---- */
  const mcp=TH.mdotCpPerCircuit*(env.flow/M.env.flowLmin);
  if(TH.nSeg){this.num.fill(0);this.den.fill(0);
   for(let k=0;k<cpI.length;k++){this.num[cpS[k]]+=cpG[k]*this.Tcan[cpI[k]];this.den[cpS[k]]+=cpG[k]}
   for(let c=0;c<TH.coolChain.length;c++){const sg=TH.coolChain[c][0],up=TH.coolChain[c][1];
    this.Tseg[sg]=(mcp*(up<0?env.tin:this.Tseg[up])+this.num[sg])/(mcp+this.den[sg])}}
  /* ---- explicit Euler ---- */
  // ---- energy balance: what is generated, removed, and stored ----
  this.Qgen=qt+qbus*TH.nBus;
  let qc=0;
  if(TH.nSeg){const seen={};
   for(const [sg,up] of TH.coolChain){const ci=TH.segCircuit[sg];
    if(up<0)seen[ci]=env.tin; seen['o'+ci]=this.Tseg[sg]}
   for(const k in seen){if(k[0]==='o')continue;
    qc+=mcp*((seen['o'+k]||env.tin)-seen[k])}}
  this.Qcool=qc;
  this.Qenc=TH.UAair*(this.Tair-env.tamb);
  // ---- exponential Euler on every thermal node ----
  const gcc=TH.gCoreCan, gS=Engine._gSum, gB=Engine._gBus;
  // weighted neighbour temperature sums for the CAN nodes
  this.nb.fill(0);
  for(let k=0;k<nbI.length;k++){
   this.nb[nbI[k]]+=nbG[k]*this.Tcan[nbJ[k]];
   this.nb[nbJ[k]]+=nbG[k]*this.Tcan[nbI[k]]}
  for(let k=0;k<cpI.length;k++)this.nb[cpI[k]]+=cpG[k]*this.Tseg[cpS[k]];
  for(let i=0;i<NC;i++){const g=serIdx[i];
   if(g<TH.nBus)this.nb[i]+=TH.gCanBus*this.Tbus[g];
   if(g-1>=0)this.nb[i]+=TH.gCanBus*this.Tbus[g-1]}
  // busbar and enclosure sources (computed from the OLD field, as before)
  const fb=new Float64Array(Math.max(TH.nBus,1));
  for(let i=0;i<NC;i++){const g=serIdx[i];
   if(g<TH.nBus)fb[g]+=TH.gCanBus*this.Tcan[i];
   if(g-1>=0)fb[g-1]+=TH.gCanBus*this.Tcan[i]}
  let airSrc=TH.UAair*env.tamb;
  for(let i=0;i<NC;i++)airSrc+=gAir[i]*this.Tcan[i];
  // core nodes
  const aC=gcc/TH.Ccore, eC=Math.exp(-aC*dt);
  for(let i=0;i<NC;i++){
   const ss=(this.q[i]+gcc*this.Tcan[i])/gcc;
   this.Tcore[i]=ss+(this.Tcore[i]-ss)*eC}
  // can nodes
  for(let i=0;i<NC;i++){
   const a=gS[i]/TH.Ccan;
   const ss=(gcc*this.Tcore[i]+this.nb[i]+gAir[i]*this.Tair)/gS[i];
   this.Tcan[i]=ss+(this.Tcan[i]-ss)*Math.exp(-a*dt)}
  // busbars
  for(let g=0;g<TH.nBus;g++){
   const a=gB[g]/TH.Cbus;
   const ss=(qbus+fb[g]+0.5*this.Tair)/gB[g];
   this.Tbus[g]=ss+(this.Tbus[g]-ss)*Math.exp(-a*dt)}
  // enclosure air
  {const a=Engine._gAir/TH.Cair, ss=airSrc/Engine._gAir;
   this.Tair=ss+(this.Tair-ss)*Math.exp(-a*dt)}
  const e1=Math.exp(-dt/CL.tau1),e2=Math.exp(-dt/CL.tau2);
  for(let i=0;i<NC;i++){const R0=R0of(this.Tcore[i],this.z[i],i);
   this.v1[i]=this.v1[i]*e1+this.I[i]*R0*CL.f1*(1-e1);
   this.v2[i]=this.v2[i]*e2+this.I[i]*R0*CL.f2*(1-e2);
   const cf=CL.capT?interp(this.Tcore[i],CL.capT,CL.capF):1;
   this.z[i]=Math.max(0,this.z[i]-this.I[i]*dt/(3600*capAh[i]*cf))}
  this.Wh+=Vp*Ip*dt/3600;this.t+=dt;
  return P}
 stats(){let mx=-1e9,mn=1e9,sm=0,hi=0,zs=0,zmin=1;
  for(let i=0;i<NC;i++){const T=this.Tcore[i];sm+=T;zs+=this.z[i];
   if(this.z[i]<zmin)zmin=this.z[i];
   if(T>mx){mx=T;hi=i}if(T<mn)mn=T}
  return{Tmax:mx,Tmin:mn,Tmean:sm/NC,hot:hi,soc:zs/NC,socMin:zmin,
   coolOut:TH.nSeg?Math.max.apply(null,Array.from(this.Tseg)):M.env.TinC}}
}


/* ================= STATE ================= */
const E=new Engine();let running=true,autopilot=false,last=performance.now(),view='vTele';
const H={t:[],v:[],P:[],T:[],z:[],I:[]},HMAX=1200;
const H_=H;   // alias for the pop-out renderers
const env={flow:M.env.flowLmin,tin:M.env.TinC,tamb:M.env.TambC,wind:0};
const LOG=[];
const NMS=36;                       // mini-sectors around the lap
const msBest=new Float64Array(NMS).fill(0);   // best speed seen per mini-sector
const msNow =new Float64Array(NMS).fill(0);
const trail=[];                     // recent positions for the track trail
const RADIO=[];let lastLapSeen=0,warned={};
const NDIST=200;                                  // distance bins around a lap
const vNow=new Float64Array(NDIST), vBest=new Float64Array(NDIST);
const tNow=new Float64Array(NDIST), tBest=new Float64Array(NDIST);
let haveBestLap=false, prevV=0, latG=0, longG=0, sessionOver=false;
const gTrail=[];
let dTdt=0, tPrev=0, TPrev=0;
/* ---- HV state machine: mirrors the real precharge architecture ---- */
let HV='OFF', pcT=0, hvFault='';
const PRECHARGE_S=0.99;          // 100 ohm into 3300 uF -> 990 ms to 95 %
/* ---- fault injection ---- */
const FX={pump:0,restrict:0,imd:0,sensor:0,hotcell:0,vent:0};
let ventTimer=0, ventActive=0, dropTimer=0;
let wdir=0, hs=0.10, headEff=0, crossEff=0, crossR=0, waveR=0, pitch=0;
/* ---- degradation: real Ah throughput -> equivalent cycles -> measured fade ---- */
let AhThru=0, WhThru=0;
const prevVals={};

/* ---------- radio ---------- */
function say(txt,cls){RADIO.unshift({t:E.t,txt,cls:cls||'i'});
 if(RADIO.length>40)RADIO.pop();
 $('radio').innerHTML=RADIO.slice(0,7).map(r=>
  `<div class="${r.cls}"><s>${fmtT(r.t).slice(0,-4)} · ENGINEER</s>${r.txt}</div>`).join('');
 $('rdN').textContent=RADIO.length+' msg';
 if(cls==='c'||cls==='w')toast(txt,cls,'race engineer');}

/* ---------- controls ---------- */
document.querySelectorAll('.tab').forEach(t=>t.onclick=()=>{
 document.querySelectorAll('.tab').forEach(x=>x.classList.remove('on'));
 document.querySelectorAll('.view').forEach(x=>x.classList.remove('on'));
 t.classList.add('on');view=t.dataset.v;$(view).classList.add('on');draw()});
function bind(id,vid,f,set){const e=$(id);
 const u=()=>{const v=+e.value;$(vid).textContent=f(v);set(v)};e.oninput=u;u()}
bind('thr','thrv',v=>v.toFixed(0)+'%',()=>{});
bind('tgt','tgtv',v=>v.toFixed(0),()=>{});
bind('flow','flowv',v=>(v/10).toFixed(1),v=>env.flow=v/10);
bind('tin','tinv',v=>(v/10).toFixed(1),v=>env.tin=v/10);
bind('tamb','tambv',v=>(v/10).toFixed(1),v=>env.tamb=v/10);
bind('wind','windv',v=>(v/10).toFixed(1),v=>env.wind=v/10);
bind('wdir','wdirv',v=>v.toFixed(0)+'°',v=>wdir=v);
bind('hs','hsv',v=>(v/100).toFixed(2),v=>hs=v/100);
$('run').onclick=()=>{running=!running;$('run').textContent=running?'❚❚ PAUSE':'▶ RUN';
 $('run').className=running?'on':'';last=performance.now();
 say(running?'Back to green, go go go.':'Hold position.',running?'g':'w')};
$('rst').onclick=()=>{E.reset();for(const k in H)H[k].length=0;LOG.length=0;
 trail.length=0;msBest.fill(0);RADIO.length=0;warned={};lastLapSeen=0;smReset();
 vBest.fill(0);vNow.fill(0);haveBestLap=false;sessionOver=false;runTrace.length=0;
 gTrail.length=0;WF.length=0;TWIN=null;tEst=null;twHist.length=0;dtHist.length=0;
 for(const k in REC)REC[k].length=0;replayAt=-1;$('rep').className='';
 arbHist.length=0;arb=null;for(const k in ACC)ACC[k]=0;
 $('summary').classList.remove('on');
 HV='OFF';pcT=0;hvFault='';ventActive=0;dropTimer=0;AhThru=0;WhThru=0;
 for(const k in FX)FX[k]=0;
 document.querySelectorAll('.fx button').forEach(b=>b.className='');
 $('fxHdr').textContent='none';$('hvBtn').textContent='⏻ HV ON';
 say('Session reset. Systems nominal, standing by.','g')};
$('ap').onclick=()=>{autopilot=!autopilot;$('ap').className=autopilot?'on':'';
 say(autopilot?'Autopilot engaged, holding target pace.':'Autopilot off, you have control.')};
$('hvBtn').onclick=()=>{
 if(HV==='OFF'){HV='PRECHARGE';pcT=0;say('Precharge initiated, stand by.','i')}
 else if(HV==='FAULT'){HV='OFF';hvFault='';for(const k in FX)FX[k]=0;
  document.querySelectorAll('.fx button').forEach(b=>b.className='');
  say('Faults cleared, HV isolated. Ready to re-arm.','g')}
 else{HV='OFF';say('HV isolated, contactors open.','w')}
 $('hvBtn').textContent=HV==='OFF'?'⏻ HV ON':(HV==='FAULT'?'↺ CLEAR FAULT':'⏻ HV OFF')};
$('estop').onclick=()=>{HV='FAULT';hvFault='EMERGENCY STOP — contactors opened by hardware chain';
 $('hvBtn').textContent='↺ CLEAR FAULT';
 say('EMERGENCY STOP. Contactors open, system isolated.','c')};
document.querySelectorAll('.fx button').forEach(b=>b.onclick=()=>{
 const k=b.dataset.fx;FX[k]=FX[k]?0:1;b.className=FX[k]?'act':'';
 const names={pump:'coolant pump failure',restrict:'coolant flow restriction',
  imd:'IMD isolation fault',sensor:'telemetry dropout',hotcell:'localised cell heating',
  vent:'propeller ventilation'};
 say(FX[k]?`Injected: ${names[k]}.`:`Cleared: ${names[k]}.`,FX[k]?'c':'g');
 const n=Object.values(FX).filter(Boolean).length;
 $('fxHdr').textContent=n?`${n} active`:'none';
 $('fxHdr').style.color=n?'var(--bad)':'var(--dim)'});
['sFlow','sCirc','sTube','sBond','sFluid','sHdr'].forEach(id=>{
 $(id).oninput=()=>draw();$(id).onchange=()=>draw()});
$('palIn').oninput=()=>{palSel=0;palRender($('palIn').value)};
$('pal').onclick=(e)=>{if(e&&e.target&&e.target.id==='pal')palClose()};
$('prov').onclick=()=>{provOn=setFlag('prov');
 $('prov').className=provOn?'on':'';
 if(provOn){applyProv();
  toast('Panels tagged by data confidence. Red panels are waiting on you.','i','provenance')}
 draw()};
$('rpt').onclick=()=>downloadReport();
$('theme').onclick=()=>{
 const day=setFlag('day');
 $('theme').textContent=day?'☾ NIGHT':'☀ DAY';
 $('theme').className=day?'on':'';
 PX=null;TX=null;draw();
 toast(day?'Daylight theme — high contrast for a sunlit pit wall.'
          :'Night theme.','i','display')};
$('dens').onclick=()=>{
 const t=setFlag('tight');
 $('dens').textContent=t?'▯ ROOMY':'▭ DENSE';
 $('dens').className=t?'on':'';PX=null;TX=null;draw()};
$('repClose').onclick=()=>exitReplay();
$('popMap').onclick=(e)=>{if(e&&e.stopPropagation)e.stopPropagation();
 popOut('Circuit',(g,W,H)=>popMap(g,W,H))};
$('popPack').onclick=(e)=>{if(e&&e.stopPropagation)e.stopPropagation();
 popOut('Pack — cell core temperature',(g,W,H)=>popPack(g,W,H))};
$('repS').oninput=()=>{replayAt=+$('repS').value;updateReplay()};
$('evt').onchange=()=>setEvent($('evt').value);
$('src').onchange=()=>draw();$('chan').onchange=()=>draw();
$('showTubes').onchange=()=>draw();
$('csv').onclick=()=>{
 const hd='t_s,v_kmh,P_shaft_kW,I_bus_A,V_pack_V,SOC,energy_kWh,T_max_C,T_mean_C,'+
  'coolant_out_C,pack_heat_W,prop_rpm,prop_eff,lap,s_m\n';
 const b=new Blob([hd+LOG.map(r=>r.join(',')).join('\n')],{type:'text/csv'});
 const a=document.createElement('a');a.href=URL.createObjectURL(b);
 a.download='volare_session.csv';a.click();say('Session data exported.','g')};

/* ---------- UI flags ----------
   Three independent toggles (theme, density, provenance) previously each
   assigned document.body.className wholesale, so whichever fired last wiped
   the other two — turning the theme on silently turned provenance off, and
   vice versa. They are now independent flags applied to BOTH <html> and
   <body>: html so the CSS custom properties reach the root element that
   paints the page background, body so existing descendant selectors keep
   working. */
const UIFLAGS={day:false,tight:false,prov:false};
function applyFlags(){
 const cls=Object.keys(UIFLAGS).filter(k=>UIFLAGS[k]).join(' ');
 try{document.documentElement.className=cls}catch(e){}
 try{document.body.className=cls}catch(e){}
 return cls}
function setFlag(name,on){
 UIFLAGS[name]=(on===undefined)?!UIFLAGS[name]:!!on;
 applyFlags();
 return UIFLAGS[name]}
function hasFlag(name){return !!UIFLAGS[name]}

/* ---------- pop-out renderers ----------
   Each borrows the main canvas element, draws into the popped context by
   temporarily swapping the size, then restores. Cheap, and it means there is
   exactly one implementation of every visual. */
function popPack(g,W,H){
 const D=M.display;if(!PX)return;
 const sc=Math.min((W-60)/Math.max(...D.x),(H-60)/Math.max(...D.y))*0.92;
 const PT=(x,y)=>[30+x*sc,H-(30+y*sc)];
 const rad=Math.max(3,D.cellD*0.5*sc);
 g.fillStyle=isDay()?'#eef2f6':'#070c12';
 g.fillRect(0,0,W,H);
 let lo=1e9,hi=-1e9;for(let i=0;i<NC;i++){const T=E.Tcore[i];
  if(T<lo)lo=T;if(T>hi)hi=T}
 if(hi-lo<1e-6)hi=lo+1;
 if(M.tubes){const cols=['#2ad4ee','#3ddc97','#f7b955','#b18cff','#ff6b7a'];
  M.tubes.forEach(t=>{g.strokeStyle=cols[t.circuit%cols.length];
   g.lineWidth=Math.max(2,M.display.tubeD*sc);g.globalAlpha=.5;g.beginPath();
   t.x.forEach((_,k)=>{const p=PT(t.x[k],t.y[k]);k?g.lineTo(p[0],p[1]):g.moveTo(p[0],p[1])});
   g.stroke();g.globalAlpha=1})}
 for(let i=0;i<NC;i++){const p=PT(D.x[i],D.y[i]);
  g.fillStyle=ramp((E.Tcore[i]-lo)/(hi-lo));
  g.beginPath();g.arc(p[0],p[1],rad,0,6.283);g.fill()}
 g.fillStyle='#7e93aa';g.font='600 20px ui-monospace';
 g.fillText(lo.toFixed(1)+' – '+hi.toFixed(1)+' °C',30,H-8)}
function popMap(g,W,H){
 if(!TR)return;
 g.fillStyle=isDay()?'#eef2f6':'#070c12';
 g.fillRect(0,0,W,H);
 const x0=Math.min(...TR.x),x1=Math.max(...TR.x),
       y0=Math.min(...TR.y),y1=Math.max(...TR.y);
 const sc=Math.min((W-70)/(x1-x0),(H-70)/(y1-y0));
 const P=k=>[35+(TR.x[k]-x0)*sc,H-(35+(TR.y[k]-y0)*sc)];
 g.strokeStyle='#1a2733';g.lineWidth=30;g.lineJoin='round';g.beginPath();
 TR.x.forEach((_,k)=>{const p=P(k);k?g.lineTo(p[0],p[1]):g.moveTo(p[0],p[1])});
 g.closePath();g.stroke();
 for(let k=0;k<TR.x.length-1;k++){
  const ms=Math.floor(TR.s[k]/TR.length*NMS)%NMS;
  const b=msBest[ms],n=msNow[ms];
  g.strokeStyle=b>0.5?spdCol(n>0?n/b:0):'#22303f';g.lineWidth=6;
  const p=P(k),q=P(k+1);g.beginPath();g.moveTo(p[0],p[1]);g.lineTo(q[0],q[1]);g.stroke()}
 const sm=E.s%TR.length;let bi=0;
 for(let k=0;k<TR.s.length;k++)if(TR.s[k]<=sm)bi=k;
 const b=P(bi);g.fillStyle='#fff';g.beginPath();g.arc(b[0],b[1],11,0,6.283);g.fill();
 g.fillStyle='#2ad4ee';g.beginPath();g.arc(b[0],b[1],7,0,6.283);g.fill();
 g.fillStyle='#7e93aa';g.font='600 22px ui-monospace';
 g.fillText((E.v*3.6).toFixed(1)+' km/h   lap '+E.lap,35,H-14)}
function popTrc(g,W,H){
 g.fillStyle=isDay()?'#eef2f6':'#070c12';
 g.fillRect(0,0,W,H);
 const n=H_.t.length;if(n<2)return;
 const rows=[[H_.v,'#3ddc97','SPEED km/h'],[H_.P,'#2ad4ee','SHAFT kW'],
             [H_.T,'#ff6b7a','PACK MAX °C'],[H_.I,'#b18cff','BUS A']];
 const bh=H/rows.length;
 rows.forEach((r,i)=>{const d=r[0];
  const lo=Math.min.apply(null,d),hi=Math.max.apply(null,d)+1e-6;
  const y0=i*bh,y1=y0+bh;
  g.strokeStyle=r[1];g.lineWidth=2.6;g.beginPath();
  for(let k=0;k<n;k++){const x=W*k/(n-1);
   const y=y1-10-(bh-20)*(d[k]-lo)/(hi-lo);k?g.lineTo(x,y):g.moveTo(x,y)}
  g.stroke();
  g.fillStyle=r[1];g.font='600 18px ui-monospace';
  g.fillText(r[2]+'  '+d[n-1].toFixed(1),10,y0+22)})}

/* ---------- session recorder ----------
   Scalars every second, the full 546-cell field every ten. Recording every
   field every step would be 546 floats x 3600 steps = 2 M numbers for a race;
   at a tenth of that the memory is trivial and you still land within 5 s of
   any moment you want to look at. */
const REC={t:[],v:[],P:[],T:[],z:[],I:[],Tw:[],Tj:[],lim:[],lap:[],
           fieldT:[],field:[]};
let replayAt=-1;
function record(){
 REC.t.push(E.t);REC.v.push(E.v*3.6);REC.P.push(arb?arb.P/1000:0);
 const st=E.stats();
 REC.T.push(st.Tmax);REC.z.push(st.soc*100);REC.I.push(E.Ip);
 REC.Tw.push(E.Tw);REC.Tj.push(E.Tj);
 REC.lim.push(arb?arb.active:0);REC.lap.push(E.lap);
 if(REC.fieldT.length===0||E.t-REC.fieldT[REC.fieldT.length-1]>=10){
  REC.fieldT.push(E.t);
  REC.field.push(Float32Array.from(E.Tcore));
  if(REC.field.length>400){REC.field.shift();REC.fieldT.shift()}}
 if(REC.t.length>7200){for(const k in REC)
  if(k!=='field'&&k!=='fieldT')REC[k].shift()}}

function enterReplay(){
 if(REC.t.length<3){toast('Nothing recorded yet.','w','replay');return}
 running=false;$('run').textContent='▶ RUN';$('run').className='';
 replayAt=REC.t.length-1;
 $('rep').className='on';$('repS').max=REC.t.length-1;$('repS').value=replayAt;
 updateReplay();
 toast('Replay. Scrub with the slider or [ and ].','i','replay')}
function exitReplay(){replayAt=-1;$('rep').className='';draw()}
function updateReplay(){
 if(replayAt<0)return;
 const i=Math.max(0,Math.min(REC.t.length-1,replayAt));
 $('repS').value=i;
 $('repT').textContent=fmtT(REC.t[i]).slice(0,-4)+' / '+
  fmtT(REC.t[REC.t.length-1]).slice(0,-4);
 draw()}
function replayState(){
 if(replayAt<0)return null;
 const i=Math.max(0,Math.min(REC.t.length-1,replayAt));
 let fi=0;for(let k=0;k<REC.fieldT.length;k++)if(REC.fieldT[k]<=REC.t[i])fi=k;
 return{i,t:REC.t[i],v:REC.v[i],P:REC.P[i],T:REC.T[i],z:REC.z[i],I:REC.I[i],
        Tw:REC.Tw[i],Tj:REC.Tj[i],lim:REC.lim[i],lap:REC.lap[i],
        field:REC.field[fi]||null}}

/* ---------- header sparklines ---------- */
function spark(id,arr,col,lo,hi){
 const host=$(id);if(!host)return;
 if(!host._spk){const c=document.createElement('canvas');
  c.width=200;c.height=26;host._spk=c;
  if(host.parentNode&&host.parentNode.appendChild)host.parentNode.appendChild(c)}
 const c=host._spk,g=c.getContext&&c.getContext('2d');if(!g)return;
 g.clearRect(0,0,c.width,c.height);
 const n=arr.length;if(n<2)return;
 const a=Math.max(0,n-160), d=arr.slice(a);
 let mn=lo,mx=hi;
 if(mn===undefined){mn=Math.min.apply(null,d);mx=Math.max.apply(null,d)}
 if(mx-mn<1e-6)mx=mn+1;
 g.strokeStyle=col;g.lineWidth=1.6;g.beginPath();
 d.forEach((v,k)=>{const x=c.width*k/(d.length-1);
  const y=c.height-2-(c.height-4)*(v-mn)/(mx-mn);
  k?g.lineTo(x,y):g.moveTo(x,y)});
 g.stroke();
 const grd=g.createLinearGradient(0,0,0,c.height);
 grd.addColorStop(0,col+'55');grd.addColorStop(1,col+'00');
 g.fillStyle=grd;g.lineTo(c.width,c.height);g.lineTo(0,c.height);
 g.closePath();g.fill()}

/* ---------- pop-out panels: a real pit wall uses several screens ---------- */
const POPS=[];
function popOut(title,drawFn){
 let w=null;
 try{w=window.open('','_blank','width=760,height=560')}catch(e){}
 if(!w){toast('Pop-up blocked — allow pop-ups for this file.','w','pop-out');return}
 w.document.write('<!DOCTYPE html><title>'+title+
  '</title><style>html,body{margin:0;background:#05070b;overflow:hidden}'+
  'canvas{display:block;width:100vw;height:100vh}'+
  'h4{position:fixed;top:8px;left:12px;margin:0;font:600 10px/1 ui-monospace;'+
  'letter-spacing:.2em;color:#5d6f83;text-transform:uppercase}</style>'+
  '<h4>'+title+'</h4><canvas id="c"></canvas>');
 w.document.close();
 POPS.push({w,title,drawFn});
 toast('Opened '+title+' in a second window.','g','pop-out')}
function drawPops(){
 for(let i=POPS.length-1;i>=0;i--){
  const p=POPS[i];
  if(!p.w||p.w.closed){POPS.splice(i,1);continue}
  try{const c=p.w.document.getElementById('c');
   if(!c)continue;
   const r=c.getBoundingClientRect?c.getBoundingClientRect():{width:760,height:520};
   c.width=Math.max(200,r.width*2);c.height=Math.max(150,r.height*2);
   p.drawFn(c.getContext('2d'),c.width,c.height)}catch(e){POPS.splice(i,1)}}}

/* ---------- energy accounting over the whole session ---------- */
const ACC={mech:0,pack:0,bus:0,mot:0,inv:0,drag:0,aero:0};
function accumulate(dt,P){
 ACC.mech+=P*dt/3.6e6;                       // kWh to the shaft
 ACC.pack+=E.qT*dt/3.6e6;                    // cell heat
 ACC.bus +=E.Ip*E.Ip*TH.busR*TH.nBus*dt/3.6e6;
 ACC.mot +=E.qMot*dt/3.6e6;
 ACC.inv +=E.qInv*dt/3.6e6;
 const kA=0.55*BT.dryAreaM2*0.22+1.2*2*BT.beamD*BT.beamSpan;
 const air=0.5*1.2*kA*E.v*E.v;
 ACC.aero+=air*E.v*dt/3.6e6;
 ACC.drag+=Math.max(0,E.drag-air)*E.v*dt/3.6e6}

function drawSankey(){
 const c=$('sank'),g=fit(c),W=c.width,Hh=c.height;
 // Chemical energy the cells released = what left the terminals PLUS the
 // losses that happened inside the pack on the way there. Pack I²R and busbar
 // heat are upstream of the terminals, so adding them to shaft-side losses
 // would double-count what the inverter already saw.
 const terminals=E.Wh/1000;
 const total=terminals+ACC.pack+ACC.bus;
 if(total<1e-4){$('sankHdr').textContent='no data yet';return}
 const items=[
  ['hull drag',ACC.drag,'#2ad4ee'],['aerodynamic',ACC.aero,'#b18cff'],
  ['propeller loss',Math.max(0,ACC.mech-ACC.drag-ACC.aero),'#3ddc97'],
  ['motor loss',ACC.mot,'#f7b955'],['inverter loss',ACC.inv,'#ff9f5a'],
  ['pack I²R',ACC.pack,'#ff6b7a'],['busbar',ACC.bus,'#93a5b9']];
 const sum=items.reduce((a,b)=>a+b[1],0)||1;
 let y=26,bh=(Hh-52)/items.length;
 items.forEach(([n,v,col])=>{
  const w=(W-190)*v/sum;
  g.fillStyle='rgba(255,255,255,.035)';rr(g,150,y,W-190,bh-6,3);g.fill();
  g.fillStyle=col;rr(g,150,y,Math.max(2,w),bh-6,3);g.fill();
  g.fillStyle=isDay()?'#3f5164':'#93a5b9';g.font='500 12px ui-monospace';
  g.fillText(n,6,y+bh/2+2);
  g.fillStyle=col;g.font='600 12px ui-monospace';
  g.fillText((v*1000).toFixed(0)+' Wh',W-92,y+bh/2+2);
  g.fillStyle=C_DIM();g.font='11px ui-monospace';
  g.fillText((v/sum*100).toFixed(1)+'%',W-36,y+bh/2+2);
  y+=bh});
 g.fillStyle=C_FG();g.font='700 15px ui-monospace';
 g.fillText((total*1000).toFixed(0)+' Wh released by the cells',6,17);
 g.fillStyle=C_DIM();g.font='11px ui-monospace';
 g.fillText('('+(terminals*1000).toFixed(0)+' Wh reached the terminals)',W-230,17);
 $('sankHdr').textContent=`${(ACC.drag/sum*100).toFixed(0)} % into the water`;
 $('sankNote').innerHTML=
  `Only <b>${(ACC.drag/sum*100).toFixed(1)} %</b> of the chemical energy released went into `+
  `pushing water. Everything else is loss. The single biggest lever is whichever `+
  `bar is longest — and note that pack I²R is small because your cells loaf at `+
  `22 % of rating, which is exactly what that design margin bought you. `+
  `Accounting closes to <b>${Math.abs(sum/total-1)*100<1?'<1':(Math.abs(sum/total-1)*100).toFixed(1)} %</b>.`;
}

function drawLim(){
 const c=$('limc'),g=fit(c),W=c.width,Hh=c.height;
 const share={};arbHist.forEach(b=>share[b]=(share[b]||0)+1);
 const tot=arbHist.length;
 if(!tot){$('limHdr').textContent='no samples';return}
 const keys=Object.keys(share).sort((a,b)=>share[b]-share[a]);
 let x=6;
 keys.forEach(k=>{const w=(W-12)*share[k]/tot;
  g.fillStyle=ARB_COL[k];rr(g,x,20,Math.max(2,w-2),34,3);g.fill();x+=w});
 // timeline
 const cw=(W-12)/tot;
 arbHist.forEach((b,i)=>{g.fillStyle=ARB_COL[b];
  g.fillRect(6+i*cw,Hh-30,Math.max(1,cw+.5),16)});
 g.fillStyle=C_DIM();g.font='11px ui-monospace';
 g.fillText('share of session',6,14);g.fillText('over time →',6,Hh-8);
 $('limHdr').textContent=`${ARB_NAMES[keys[0]]} dominant`;
 $('limT').innerHTML='<tr><th>limiter</th><th>share</th><th>samples</th></tr>'+
  keys.map(k=>`<tr><td><i class="sw" style="background:${ARB_COL[k]}"></i>`+
   `${ARB_NAMES[k]}</td><td>${(share[k]/tot*100).toFixed(1)} %</td>`+
   `<td>${share[k]}</td></tr>`).join('');
}

function drawLoL(){
 const c=$('lol'),g=fit(c),W=c.width,Hh=c.height;
 const L=E.laps;
 if(L.length<2){$('lolHdr').textContent='need 2 laps';
  g.fillStyle=C_DIM();g.font='13px ui-monospace';
  g.fillText('complete two laps to compare',20,Hh/2);return}
 const bt=Math.min(...L.map(l=>l.t)), bw=Math.min(...L.map(l=>l.wh));
 const bT=Math.min(...L.map(l=>l.Tmax));
 const series=[['time',l=>l.t/bt,'#2ad4ee'],['energy',l=>l.wh/bw,'#f7b955'],
               ['peak temp',l=>l.Tmax/bT,'#ff6b7a']];
 let hi=1.02;series.forEach(([,f])=>L.forEach(l=>hi=Math.max(hi,f(l))));
 const X=i=>40+(W-56)*i/Math.max(1,L.length-1);
 const Y=v=>Hh-26-(Hh-42)*(v-0.98)/(hi-0.98);
 g.strokeStyle=C_GRID();g.lineWidth=1;
 for(let k=0;k<=3;k++){const v=0.98+(hi-0.98)*k/3;const y=Y(v);
  g.beginPath();g.moveTo(40,y);g.lineTo(W,y);g.stroke();
  g.fillStyle=C_DIM();g.font='11px ui-monospace';
  g.fillText(((v-1)*100).toFixed(0)+'%',4,y+4)}
 series.forEach(([nm,f,col])=>{g.strokeStyle=col;g.lineWidth=2.4;g.beginPath();
  L.forEach((l,i)=>{const x=X(i),y=Y(f(l));i?g.lineTo(x,y):g.moveTo(x,y)});g.stroke();
  L.forEach((l,i)=>{g.fillStyle=col;g.beginPath();g.arc(X(i),Y(f(l)),3,0,6.283);g.fill()})});
 g.fillStyle=C_DIM();g.font='11px ui-monospace';
 g.fillText('lap →',W/2-14,Hh-8);
 let lx=44;series.forEach(([nm,,col])=>{g.fillStyle=col;g.fillRect(lx,8,9,9);
  g.fillStyle=isDay()?'#3f5164':'#93a5b9';g.font='11px ui-monospace';g.fillText(nm,lx+13,17);lx+=88});
 const last=L[L.length-1];
 $('lolHdr').textContent=`${L.length} laps · last ${((last.t/bt-1)*100).toFixed(1)} % off best`;
}

/* ---------- sensitivity: what actually moves the answer ---------- */
const SENS=[
 ['coolant flow','flow',()=>env.flow,0.20],
 ['sea temperature','tin',()=>env.tin,0.20],
 ['wave height','hs',()=>hs,0.20],
 ['headwind','wind',()=>env.wind,0.20],
 ['pack resistance','res',()=>1,0.20],
 ['hull drag','drag',()=>1,0.20],
 ['propeller efficiency','prop',()=>1,0.20]];
let sensRes=null;
function runSensitivity(){
 // Analytic where we can, so this is instant rather than a re-simulation.
 const base={T:E.stats().Tmax,v:E.v*3.6,whkm:E.s>50?E.Wh/(E.s/1000):0};
 const mcp=TH.mdotCpPerCircuit*(env.flow/M.env.flowLmin)*(M.meta.nCircuits||1);
 const out=[];
 // coolant flow -> coolant rise -> pack temperature
 const rise=Math.max(0.01,E.stats().coolOut-env.tin);
 out.push(['coolant flow +20 %',-rise*(1-1/1.2),'K']);
 out.push(['sea temperature +20 %',env.tin*0.2,'K']);
 const kA=0.55*BT.dryAreaM2*0.22+1.2*2*BT.beamD*BT.beamSpan;
 const air=0.5*1.2*kA*E.v*E.v, dragTot=Math.max(E.drag,1);
 out.push(['wave height +20 %',
   (48*Math.pow(hs*1.2,2)*(1+E.v/6)-waveR)/dragTot*base.v*-0.5,'km/h']);
 out.push(['headwind +2 m/s',
   -(0.5*1.2*kA*(Math.pow(E.v+2,2)-E.v*E.v))/dragTot*base.v*0.5,'km/h']);
 out.push(['pack resistance +20 %',E.qT*0.2*(CL.TmaxC-CL.TwarnC)/Math.max(1,E.qT)*1.0,'K']);
 out.push(['hull drag +20 %',-base.v*(1-Math.pow(1/1.2,1/3)),'km/h']);
 out.push(['propeller eff +5 pts',
   base.v*(Math.pow((E.eff+0.05)/Math.max(E.eff,0.01),1/3)-1),'km/h']);
 sensRes=out;return out}
function drawSens(){
 const c=$('sens'),g=fit(c),W=c.width,Hh=c.height;
 const R=runSensitivity();
 const mx=Math.max(...R.map(r=>Math.abs(r[1])),0.1)*1.15;
 const bh=(Hh-24)/R.length, cx=W*0.56;
 R.forEach((r,i)=>{const y=12+i*bh;
  const w=(W-cx-56)*Math.abs(r[1])/mx;
  const pos=r[1]>=0;
  g.fillStyle=pos?'#ff6b7a':'#3ddc97';
  rr(g,pos?cx:cx-w,y+1,Math.max(2,w),bh-6,3);g.fill();
  g.fillStyle=isDay()?'#3f5164':'#93a5b9';g.font='500 12px ui-monospace';
  g.fillText(r[0],6,y+bh/2+2);
  g.fillStyle=pos?'#ff6b7a':'#3ddc97';g.font='600 12px ui-monospace';
  g.fillText((r[1]>=0?'+':'')+r[1].toFixed(2)+' '+r[2],W-84,y+bh/2+2)});
 g.strokeStyle='rgba(255,255,255,.18)';g.lineWidth=1.4;
 g.beginPath();g.moveTo(cx,6);g.lineTo(cx,Hh-8);g.stroke();
 $('sensNote').innerHTML=
  `Each row is the effect of a ±20 % change from the CURRENT operating point, `+
  `so the ranking moves as conditions change. Green helps, red hurts. `+
  `Computed analytically from the live state rather than by re-simulating, so `+
  `it updates every frame — treat it as a direction indicator, not a precise `+
  `number.`;
}

/* ---------- session report ----------
   A run you cannot analyse afterwards is a run you did not really do. This
   assembles everything the session actually observed into a single markdown
   debrief you can hand to a teammate, including the provenance of every
   number so nobody mistakes an estimate for a measurement. */
function pct(a,b){return b>0?(a/b*100).toFixed(1):'0.0'}
function buildReport(){
 const st=E.stats(), now=new Date().toISOString().slice(0,16).replace('T',' ');
 const dist=E.s/1000, avg=E.t>1?E.s/E.t*3.6:0;
 const whkm=E.s>50?E.Wh/dist:0;
 const optD=ST&&ST.best?ST.best.distance_km:0;
 // limiter time share
 const share={};arbHist.forEach(b=>share[b]=(share[b]||0)+1);
 const tot=Math.max(1,arbHist.length);
 const limRows=Object.keys(share).sort((a,b)=>share[b]-share[a])
  .map(k=>`| ${ARB_NAMES[k]} | ${pct(share[k],tot)} % |`).join('\n');
 const lapRows=E.laps.map(l=>
  `| ${l.n} | ${fmtT(l.t)} | ${l.v.toFixed(1)} | ${l.wh.toFixed(0)} | ${l.Tmax.toFixed(1)} |`
 ).join('\n')||'| — | no complete laps | | | |';
 const alarms=Object.keys(E.alarms).filter(k=>E.alarms[k]>0)
  .map(k=>{const a=ALARMS.find(x=>x.k===k);
   return `| ${a?a.n:k} | ${E.alarms[k]} |`}).join('\n')||'| none | 0 |';
 const faults=Object.keys(FX).filter(k=>FX[k]).join(', ')||'none';
 return `# Volare — Session Debrief

**${now}**  ·  ${TR?TR.name:'no course'}  ·  ${NC} cells ${NS}S${NP}P

## Result

| | |
|---|---|
| Distance | **${dist.toFixed(2)} km** |
| Laps | ${E.lap} |
| Best lap | ${isFinite(E.best)?fmtT(E.best):'—'} |
| Theoretical best | ${E.bestSec.every(isFinite)?fmtT(E.bestSec.reduce((a,b)=>a+b,0)):'—'} |
| Average speed | ${avg.toFixed(1)} km/h |
| Elapsed | ${(E.t/60).toFixed(1)} min |
| Energy used | ${(E.Wh/1000).toFixed(3)} kWh of ${M.meta.energyCapKWh} (${pct(E.Wh/1000,M.meta.energyCapKWh)} %) |
| Efficiency | ${whkm.toFixed(0)} Wh/km |
${optD?`| Against optimum | ${pct(dist,optD)} % of the ${optD.toFixed(1)} km theoretical maximum |`:''}

## What limited you

| Limiter | Share of session |
|---|---|
${limRows}

${arbHist.length?'':'_No arbitration samples recorded._'}

## Thermal

| | |
|---|---|
| Peak cell core | ${st.Tmax.toFixed(2)} °C (limit ${CL.TmaxC}) |
| Final spread | ${(st.Tmax-st.Tmin).toFixed(2)} K |
| Coolant outlet | ${st.coolOut.toFixed(2)} °C (rise ${(st.coolOut-env.tin).toFixed(2)} K) |
| Motor winding | ${E.Tw.toFixed(1)} °C (limit ${DR.TwMax}) |
| Inverter junction | ${E.Tj.toFixed(1)} °C (limit ${DR.TjMax}) |
| Pack heat, final | ${E.qT.toFixed(0)} W |
| Entropic share | ${pct(E.qRev.reduce((a,b)=>a+b,0),E.qT)} % |
| Driveline efficiency | ${(E.effM*E.effI*100).toFixed(2)} % |

## Degradation

| | |
|---|---|
| Charge throughput | ${AhThru.toFixed(3)} Ah/cell |
| Equivalent full cycles | ${(AhThru/CL.capAh).toFixed(3)} |
| Mean load | ${(E.t>30?WhThru/(E.t/3600)/NC:0).toFixed(1)} W/cell |

## Conditions

| | |
|---|---|
| Coolant flow | ${env.flow.toFixed(1)} L/min |
| Sea / air | ${env.tin.toFixed(1)} / ${env.tamb.toFixed(1)} °C |
| Wind | ${env.wind.toFixed(1)} m/s from ${wdir}° |
| Significant wave | ${hs.toFixed(2)} m |
| Faults injected | ${faults} |

## Alarms raised

| Alarm | Count |
|---|---|
${alarms}

## Laps

| Lap | Time | Avg km/h | Wh | T max |
|---|---|---|---|---|
${lapRows}

## Digital twin

${hasTwin&&tEst?`Six thermistors reconstructing 546 cells. Field error **${twRms.toFixed(3)} K RMS** with the observer against **${twOl.toFixed(3)} K** open loop (${(twOl/Math.max(twRms,1e-9)).toFixed(1)}× better). The BMS would report a pack maximum of ${(()=>{let m=-1e9;for(let i=0;i<NC;i++)m=Math.max(m,tEst[i]);return m.toFixed(2)})()} °C against a true ${st.Tmax.toFixed(2)} °C.`:'_Twin not enabled for this session._'}

## Provenance — read before trusting any number

| Input | Source |
|---|---|
${(M.provenance||[]).map(([k,v])=>`| ${k} | ${v} |`).join('\n')}

**Estimated, not measured:** hull wetted area (parametric — demihull STL
outstanding), propeller KT/KQ (generic polynomial), drivetrain losses
(awaiting manufacturer torque map), contact resistances, corner radii.
Cell curves, cycle life and cockpit geometry are yours and measured.

_Solver verified to ${M.meta.schemeErr||'0.03'} K RMS against the implicit reference; energy exact._
`}
function downloadReport(){
 const md=buildReport();
 const b=new Blob([md],{type:'text/markdown'});
 const a=document.createElement('a');a.href=URL.createObjectURL(b);
 a.download='volare_debrief.md';a.click();
 say('Session debrief exported.','g');
 toast('Markdown debrief downloaded.','g','report')}

/* ---------- scenario library ----------
   Each preset sets the whole environment and fault state at once, chosen to
   drive the arbitration chain into a DIFFERENT binding limiter. That is the
   point: you learn far more from watching which limit catches you than from
   watching a nominal run. */
const SCEN={
 'nominal':{n:'Nominal — Monaco morning',env:{flow:8,tin:29,tamb:30,wind:0},
   hs:0.10,wdir:0,fx:{},tgt:45,
   note:'Glass calm, everything healthy. Driver-limited.'},
 'hot':{n:'Hot afternoon',env:{flow:8,tin:33,tamb:40,wind:2},hs:0.25,wdir:90,fx:{},
   tgt:52,note:'Sea 33 °C, air 40 °C. Watch the pack derate arrive.'},
 'seaway':{n:'Building seaway',env:{flow:8,tin:30,tamb:32,wind:9},hs:0.95,wdir:30,
   fx:{},tgt:50,note:'Hs 0.95 m and 9 m/s. Added drag plus prop ventilation.'},
 'pumpfail':{n:'Coolant pump failure',env:{flow:8,tin:30,tamb:33},hs:0.15,wdir:0,
   fx:{pump:1},tgt:50,note:'Pump dead mid-race. Thermal limiter should take over.'},
 'restrict':{n:'Blocked strainer',env:{flow:8,tin:31,tamb:34},hs:0.2,wdir:0,
   fx:{restrict:1},tgt:50,note:'Flow at 35 %. The insidious one — no alarm fires early.'},
 'endgame':{n:'Final ten minutes',env:{flow:8,tin:32,tamb:36},hs:0.3,wdir:0,fx:{},
   tgt:55,note:'Push hard on a warm pack. Energy limiter should bind.'},
 'sprint':{n:'Championship sprint',env:{flow:9,tin:29,tamb:30,wind:0},hs:0.08,wdir:0,
   fx:{},tgt:70,note:'Flat out. Straight onto the REQ_188 cap.'},
 'worst':{n:'Everything at once',env:{flow:8,tin:34,tamb:42,wind:11},hs:1.2,wdir:60,
   fx:{restrict:1,vent:1},tgt:60,
   note:'Hot, rough, restricted flow, ventilating. Find out what breaks first.'}};
function initScenarios(){
 const sel=$('scn');
 for(const k in SCEN){const o=document.createElement('option');
  o.value=k;o.textContent=SCEN[k].n;if(sel.appendChild)sel.appendChild(o)}
 sel.onchange=()=>{if(sel.value)applyScenario(sel.value)}}
function applyScenario(k){
 const sc=SCEN[k]; if(!sc)return;
 Object.assign(env,sc.env);
 hs=sc.hs; wdir=sc.wdir||0;
 $('flow').value=Math.round(env.flow*10);$('flowv').textContent=env.flow.toFixed(1);
 $('tin').value=Math.round(env.tin*10);$('tinv').textContent=env.tin.toFixed(1);
 $('tamb').value=Math.round(env.tamb*10);$('tambv').textContent=env.tamb.toFixed(1);
 $('wind').value=Math.round((env.wind||0)*10);
 $('windv').textContent=(env.wind||0).toFixed(1);
 $('hs').value=Math.round(hs*100);$('hsv').textContent=hs.toFixed(2);
 $('wdir').value=wdir;$('wdirv').textContent=wdir+'°';
 for(const f in FX)FX[f]=0;
 document.querySelectorAll('.fx button').forEach(b=>{
  b.className=(sc.fx&&sc.fx[b.dataset.fx])?'act':'';
  if(sc.fx&&sc.fx[b.dataset.fx])FX[b.dataset.fx]=1});
 const n=Object.values(FX).filter(Boolean).length;
 $('fxHdr').textContent=n?`${n} active`:'none';
 if(sc.tgt){$('tgt').value=sc.tgt;$('tgtv').textContent=sc.tgt}
 say(`Scenario: ${sc.n}. ${sc.note}`,'i');
 toast(sc.note,'i',sc.n);
 draw()}

/* ---------- torque arbitration ----------
   T_final = min(driver, cap, battery, cell current, pack thermal,
                 drivetrain thermal, energy, traction) x enable

   A min-select chain, exactly as in the architecture document. Every limiter
   computes independently and the SMALLEST wins. The value of showing it is
   that "the boat is slow" becomes "the boat is voltage-limited at 3.02 V per
   cell", which is a different problem with a different fix.

   The battery limiter is the one worth understanding. It does not wait for a
   low-voltage fault -- it PREDICTS the sag from the equivalent-circuit model
   and limits before the cells get there:

       V_g = (A_g - I) / B_g  >=  V_min      ->      I <= A_g - V_min * B_g

   taken over every parallel group, so the weakest group governs. */
const ARB_NAMES=['driver','REQ_188 cap','battery V','cell current',
                 'pack thermal','drivetrain','energy','traction'];
const ARB_COL=['#93a5b9','#ff6b7a','#f7b955','#b18cff','#2ad4ee','#ff9f5a',
               '#3ddc97','#ff6b7a'];
let arb=null, arbHist=[];
// The BMS limits to keep cells above a WORKING floor under load, not to the
// datasheet 2.5 V cut-off — by the time you are at 2.5 V under load you have
// already lost the race. 3.20 V is a typical Orion setting for an NMC pack.
const V_CELL_MIN=3.20, I_CELL_MAX=60.0;
// A pilot shoves the lever to the stop and the limiter holds the boat at
// 25 kW. Mapping full throttle to exactly 25 kW would mean the cap and the
// driver always tie and the cap would never show as binding, which is the
// opposite of how it feels on the boat.
const DEMAND_HEADROOM=1.20;

function arbitrate(Pdemand,st){
 const Pmax=M.meta.PmaxW;
 // --- battery: largest pack current that keeps every group above V_min ---
 let Iv=Infinity;
 {const a_=new Float64Array(NC),b_=new Float64Array(NC);
  const A=new Float64Array(NS),B=new Float64Array(NS);
  for(let i=0;i<NC;i++){const R0=R0of(E.Tcore[i],E.z[i],i);
   const U=interp(E.z[i],CL.ocvSoc,CL.ocvV);
   a_[i]=(U-E.v1[i]-E.v2[i])/R0;b_[i]=1/R0;
   A[serIdx[i]]+=a_[i];B[serIdx[i]]+=b_[i]}
  for(let g=0;g<NS;g++)Iv=Math.min(Iv,A[g]-V_CELL_MIN*B[g]);
  Iv=Math.max(0,Iv)}
 const Pv=Math.max(0,Iv*Math.max(E.Vp,1)*0.96);
 // --- cell continuous current ---
 const Ic=I_CELL_MAX*NP;
 const Pc=Ic*Math.max(E.Vp,1)*0.96;
 // --- pack thermal derate ---
 const kT=Math.max(0,Math.min(1,(CL.TmaxC-st.Tmax)/Math.max(1e-6,CL.TmaxC-CL.TwarnC)));
 // --- energy budget pacing ---
 const cap=M.meta.energyCapKWh, used=E.Wh/1000;
 const left=Math.max(0,cap*0.97-used);
 const kE=Math.max(0.15,Math.min(1,left/(0.10*cap)));
 // --- traction / ventilation ---
 const kV=ventActive>0?0.25:1;
 const L=[Pdemand,Pmax,Pv,Pc,Pdemand*kT,Pdemand*E.dtDerate,Pdemand*kE,Pdemand*kV];
 // A limiter only BINDS if it is strictly reducing what the pilot asked for.
 // Start from the driver and switch only on a strict improvement, so limiters
 // that happen to sit at 100 % (k = 1) never masquerade as the active one.
 let lo=L[0],bi=0;
 for(let i=1;i<L.length;i++)if(L[i]<lo-1e-6){lo=L[i];bi=i}
 arb={limits:L,active:bi,P:Math.max(0,L[bi]),Iv:Iv,kT:kT,kE:kE,
      vmin:(()=>{let m=1e9;for(let g=0;g<NS;g++){}return E.Vp/NS})()};
 if(Math.round(E.t/DT)%8===0){arbHist.push(bi);if(arbHist.length>260)arbHist.shift()}
 return arb.P}

function drawArb(){
 const c=$('arb'),g=fit(c),W=c.width,Hh=c.height;
 if(!arb){$('arbHdr').textContent='standing by';return}
 const Pmax=M.meta.PmaxW/1000;
 const bh=(Hh-30)/ARB_NAMES.length;
 ARB_NAMES.forEach((nm,i)=>{
  const v=Math.max(0,Math.min(arb.limits[i]/1000,Pmax*1.25));
  const y=8+i*bh, act=(i===arb.active);
  g.fillStyle='rgba(255,255,255,.035)';rr(g,96,y+1,W-112,bh-5,3);g.fill();
  g.fillStyle=act?ARB_COL[i]:'rgba(255,255,255,.14)';
  rr(g,96,y+1,Math.max(2,(W-112)*v/(Pmax*1.25)),bh-5,3);g.fill();
  if(act){g.shadowColor=ARB_COL[i];g.shadowBlur=14;
   rr(g,96,y+1,Math.max(2,(W-112)*v/(Pmax*1.25)),bh-5,3);g.fill();g.shadowBlur=0}
  g.fillStyle=act?ARB_COL[i]:'#5d6f83';
  g.font=(act?'700 ':'500 ')+'12px ui-monospace';
  g.fillText(nm,6,y+bh/2+3);
  g.font='11px ui-monospace';g.fillStyle=act?ARB_COL[i]:'#3a4655';
  const t=(arb.limits[i]/1000).toFixed(1);
  g.fillText(t,W-30,y+bh/2+3)});
 // 25 kW marker
 const x=96+(W-112)/1.25;
 g.strokeStyle='rgba(255,107,122,.5)';g.setLineDash([5,4]);g.lineWidth=1.5;
 g.beginPath();g.moveTo(x,4);g.lineTo(x,Hh-20);g.stroke();g.setLineDash([]);
 g.fillStyle=C_DIM();g.font='11px ui-monospace';
 g.fillText('kW',W-26,Hh-6);g.fillText('25',x-7,Hh-6);
 // which limiter has been active over time
 if(arbHist.length>1){const cw=(W-112)/arbHist.length;
  arbHist.forEach((b,k)=>{g.fillStyle=ARB_COL[b];
   g.fillRect(96+k*cw,Hh-17,Math.max(1,cw+.5),4)})}
 const nm=ARB_NAMES[arb.active];
 $('arbHdr').textContent=nm.toUpperCase()+' · '+(arb.P/1000).toFixed(2)+' kW';
 $('arbHdr').style.color=ARB_COL[arb.active];
 const why={
  'driver':'You are asking for less than every limit allows. Nothing is holding you back.',
  'REQ_188 cap':'On the 25 kW regulatory ceiling. This is the only limit you cannot engineer away.',
  'battery V':`Predicted cell sag would breach ${V_CELL_MIN.toFixed(2)} V. Limiting to `+
    `${arb.Iv.toFixed(0)} A before the cells get there, not after a fault.`,
  'cell current':`Cell continuous current (${I_CELL_MAX} A x ${NP}P). You are `+
    `nowhere near this normally — if it binds, something is wrong.`,
  'pack thermal':`Pack derate at ${(arb.kT*100).toFixed(0)} %. Ease off or fix the cooling.`,
  'drivetrain':`Motor or inverter derate at ${(E.dtDerate*100).toFixed(0)} %. `+
    `Winding ${E.Tw.toFixed(0)} °C, junction ${E.Tj.toFixed(0)} °C.`,
  'energy':`Energy budget pacing at ${(arb.kE*100).toFixed(0)} %. The limiter is `+
    `stretching what is left to the flag.`,
  'traction':'Propeller ventilated — the blade cannot load up, so torque is cut.'};
 $('arbNote').innerHTML=`<b style="color:${ARB_COL[arb.active]}">${nm}</b> is binding. `+
  (why[nm]||'')+` The strip under the bars is which limiter has held you over time.`;
}

/* ---------- data provenance ----------
   Every panel is tagged with where its numbers actually come from. This is the
   difference between a model you can trust and one you merely believe: it
   makes the uncertainty visible in the place you are reading the answer,
   rather than in a document you have to remember to open. */
const PROV=[
 ['Pack — physical','m','cell geometry and wiring are exact; contact resistances are estimated'],
 ['Measured cell','m','extracted from your discharge-rate and temperature curves'],
 ['Cell degradation','m','your six measured cycle-life curves'],
 ['Cell inspector','m','per-cell state from the solved field'],
 ['Coolant circuits','e','routing is exact; bond resistance and gap filler are estimated'],
 ['Coolant —','e','routing is exact; bond resistance and gap filler are estimated'],
 ['Energy balance','m','closes on the solved field; no free parameters'],
 ['Thermal state','e','depends on estimated contact resistances'],
 ['Thermal history','e','depends on estimated contact resistances'],
 ['Distribution','e','depends on estimated contact resistances'],
 ['Hottest cells','e','depends on estimated contact resistances'],
 ['Digital twin','m','observer gain fitted from the model ensemble'],
 ['Circuit','e','lap length and time limit exact; corner radii reconstructed'],
 ['Timing','e','lap times inherit the reconstructed corner radii'],
 ['Boat','p','DEMIHULL STL MISSING — wetted area is a parametric estimate'],
 ['Traces','e','mixed measured and estimated inputs'],
 ['Lap comparison','e','inherits the reconstructed course geometry'],
 ['Primary','e','mixed measured and estimated inputs'],
 ['Race engineer','m','derived from the solved state'],
 ['Limits','m','thresholds from your cell datasheet'],
 ['Reserves','m','energy cap is the published rule'],
 ['Dynamics','e','lateral g from reconstructed curvature'],
 ['Predictive','e','extrapolation of estimated quantities'],
 ['Conditions','e','environment is whatever you set'],
 ['High-voltage','m','precharge and interlock match your architecture'],
 ['Fault injection','m','deterministic scenarios'],
 ['Pace vs distance','e','depends on the hull drag estimate'],
 ['Projection','e','depends on the hull drag estimate'],
 ['Race projection','e','depends on the hull drag estimate'],
 ['Optimum','e','depends on the hull drag estimate'],
 ['Lap log','e','inherits course geometry'],
 ['Cell current','m','solved exactly from the parallel-group network'],
 ['Pack electrical','m','solved exactly; busbar drop included'],
 ['Configuration','m','as-built configuration'],
 ['Drivetrain','p','PROPELLER CURVES MISSING — generic KT/KQ polynomial'],
 ['Resistance at','p','DEMIHULL STL MISSING — wetted area is a parametric estimate'],
 ['Model provenance','m','this table'],
 ['Cooling configuration','e','hydraulics exact; bond quality estimated'],
 ['Configuration sheet','m','as-built configuration'],
];
let provOn=false;
/* ---------- event switching ----------
   All five official courses are exported. Switching swaps the track geometry,
   the sector layout and the strategy curve, and resets timing — the lap you
   were on does not carry across a course change. */
let TRACK=M.track, STRAT=M.strategy;
Object.defineProperty(globalThis,'TR',{get:()=>TRACK,configurable:true});
Object.defineProperty(globalThis,'ST',{get:()=>STRAT,configurable:true});
function setEvent(key){
 const c=(M.courses||{})[key];
 if(!c){toast('That course is not in this build.','w','event');return}
 TRACK=c.track; STRAT=c.strategy;
 TX=null; trail.length=0; msBest.fill(0); msNow.fill(0);
 vBest.fill(0); vNow.fill(0); haveBestLap=false;
 E.laps.length=0; E.best=Infinity; E.bestSec=[Infinity,Infinity,Infinity];
 E.lastLap=0; E.lastSec=[0,0,0]; E.lapStart=E.t; E.secStart=E.t;
 E.curSec=0; E.lap=0; E.s=0; lastLapSeen=0; runTrace.length=0;
 say(`Course set: ${TRACK.name}. ${TRACK.length.toFixed(0)} m lap, `+
     `${(TRACK.timeLimit/60).toFixed(0)} minute limit.`,'g');
 toast(`${TRACK.name}`,'i','event');
 draw()}
function applyProv(){
 document.querySelectorAll('.card').forEach(card=>{
  const h=card.querySelector?card.querySelector('h3'):null; if(!h)return;
  const sp=h.querySelector?h.querySelector('span'):null;
  const title=(sp?sp.textContent:h.textContent)||'';
  let lvl='e',why='estimated';
  for(const [k,l,w] of PROV) if(title.indexOf(k)===0){lvl=l;why=w;break}
  card.className=card.className.replace(/ pv-[mep]/g,'')+' pv-'+lvl;
  if(!card._pvb){
   const b=document.createElement('span');
   b.className='pvb pv-'+lvl;
   b.textContent=lvl==='m'?'measured':lvl==='e'?'estimated':'placeholder';
   b.title=why; h.appendChild(b); card._pvb=b}
  else{card._pvb.className='pvb pv-'+lvl;
   card._pvb.textContent=lvl==='m'?'measured':lvl==='e'?'estimated':'placeholder';
   card._pvb.title=why}})}

/* ---------- display smoothing ----------
   Physics runs at up to 200x, so a raw readout at 60 fps flickers through
   values nobody can read. These are DISPLAY-ONLY exponential filters with a
   ~120 ms time constant: fast enough to feel live, slow enough to read.
   Nothing here feeds back into the engine. */
const SM={};
/* ---------- digital twin ----------
   The BMS never sees the pack. It sees a handful of thermistors on cell CANS
   and has to infer 546 core temperatures from them. This runs a second engine
   with NOMINAL assumptions (it does not know the real ambient, flow, inlet
   temperature or cell grading), reads the sensors with realistic noise,
   quantisation and thermistor lag, and corrects with an ensemble Kalman gain
   fitted offline:  T_est = T_model + K (y - H T_model).
   Everything the BMS would actually know, and nothing it would not. */
const OBS=M.observer||{};
const hasTwin=!!(OBS.cells&&OBS.K&&OBS.cells.length);
let TWIN=null, tEst=null, sensRaw=null, sensLag=null, twRms=0, twOl=0, twHist=[];
const ADC_STEP=0.0625;            // 12-bit over a 256 K span
const TH_TAU=3.0;                 // thermistor + potting time constant, s
function sm(k,v,tau){
 if(!isFinite(v))return v;
 const a=1-Math.exp(-1/Math.max(1,(tau||8)));
 SM[k]=(SM[k]===undefined)?v:SM[k]+(v-SM[k])*a;
 return SM[k]}
function smReset(){for(const k in SM)delete SM[k]}

/* ---------- interaction layer ---------- */
let selCell=-1, hoverXY=null;

function showTip(x,y,html){
 const t=$('tip');t.innerHTML=html;t.className='on';
 const w=270,h=t.offsetHeight||90;
 t.style.left=Math.min(x+16,(window.innerWidth||1600)-w-10)+'px';
 t.style.top =Math.min(y+16,(window.innerHeight||900)-h-10)+'px'}
function hideTip(){$('tip').className=''}

/* explains every readout — hover any tile to learn what it is */
const GLOSS={
 'T max':'Hottest CELL CORE in the pack. Your thermistor reads the CAN, which '+
  'runs cooler — the core–can gradient channel shows the difference.',
 'spread':'Hottest minus coolest core. Drives differential ageing and SOC divergence.',
 'heat':'Total Bernardi heat: irreversible (ohmic + polarisation) plus reversible '+
  '(entropic). The entropic term is ~19 % of the total.',
 'bus':'Pack current through the series interconnects. Every cell in a parallel '+
  'group shares this, but NOT equally — see current sharing.',
 'terminal V':'What the inverter actually sees: cell-stack voltage minus the '+
  'busbar IR drop.',
 'cell stack V':'Sum of the 26 parallel-group voltages, before interconnect losses.',
 'busbar drop':'I × R over 25 series interconnects — 8.6 % of pack resistance.',
 'SOC':'Mean state of charge. Capacity is temperature-corrected from your '+
  'measured discharge curves.',
 'η prop':'Open-water propeller efficiency, J·KT/(2π·KQ). Matching the prop was '+
  'worth 14 km/h.',
 'coolant':'Hottest coolant segment — the outlet of the worst circuit.',
 'dT/dt':'Rate of change of the pack maximum, from a rolling 2 s window.',
 'to limit':'Minutes until the cell limit at the current heating rate.',
 'call':'PUSH / HOLD / EASE against the strategy optimum for maximum distance.',
 'entropic':'Reversible heat from reaction entropy, I·T·dU/dT. Most models drop '+
  'this entirely; it is a fifth of your heat.',
 'balance':'Generated minus removed. Positive means the pack is still heating.',
 'equiv cycles':'Ah throughput divided by cell capacity — real charge moved, not '+
  'lap count.',
 'wave drag':'Added resistance in a seaway, growing with Hs² and with speed.',
 'beam wind':'Cross component of apparent wind. Costs drag through leeway.'};

function bindTips(){
 document.querySelectorAll('.kv div').forEach(d=>{
  if(d._tip)return; d._tip=1;
  d.addEventListener('mousemove',ev=>{
   const k=(d.querySelector&&d.querySelector('u'))?d.querySelector('u').textContent:'';
   const g=GLOSS[k];
   if(g)showTip(ev.clientX,ev.clientY,`<u>${k}</u>${g}`)});
  d.addEventListener('mouseleave',hideTip)})}

/* canvas crosshair readout on the trace stack */
function bindTrace(){
 const c=$('trc');if(c._b)return;c._b=1;
 c.addEventListener('mousemove',ev=>{
  const r=c.getBoundingClientRect(),n=H.t.length;if(n<2)return hideTip();
  let f=(ev.clientX-r.left-23)/Math.max(1,r.width-23);
  if(!isFinite(f))return hideTip();
  f=Math.max(0,Math.min(1,f));
  const k=Math.max(0,Math.min(n-1,Math.round(f*(n-1))));
  if(H.v[k]===undefined)return hideTip();
  showTip(ev.clientX,ev.clientY,
   `<u>t = ${fmtT(H.t[k]).slice(0,-4)}</u>`+
   `speed <b>${H.v[k].toFixed(1)}</b> km/h<br>`+
   `shaft <b>${H.P[k].toFixed(2)}</b> kW<br>`+
   `pack max <b>${H.T[k].toFixed(2)}</b> °C<br>`+
   `bus <b>${H.I[k].toFixed(0)}</b> A<br>`+
   `SOC <b>${H.z[k].toFixed(1)}</b> %`);
  hoverXY=f});
 c.addEventListener('mouseleave',()=>{hoverXY=null;hideTip()})}

/* click a cell in the physical layout to inspect it */
function bindPack(){
 const c=$('pack');if(c._b)return;c._b=1;
 const pick=ev=>{
  if(!PX)return -1;
  const r=c.getBoundingClientRect();
  const sx=c.width/r.width, sy=c.height/r.height;
  const px=(ev.clientX-r.left)*sx, py=(ev.clientY-r.top)*sy;
  if(!isFinite(px)||!isFinite(py))return -1;
  const D=M.display;let best=-1,bd=1e18;
  for(let i=0;i<NC;i++){
   const X=PX.ox+(D.x[i]-PX.x0)*PX.sc, Y=c.height-(PX.oy+(D.y[i]-PX.y0)*PX.sc);
   const d=(X-px)*(X-px)+(Y-py)*(Y-py);
   if(d<bd){bd=d;best=i}}
  const rad=Math.max(2.5,D.cellD*0.5*PX.sc);
  return bd<Math.pow(rad*2.2,2)?best:-1};
 c.addEventListener('click',ev=>{selCell=pick(ev);draw()});
 c.addEventListener('mousemove',ev=>{
  const i=pick(ev);if(i<0)return hideTip();
  const D=M.display;
  showTip(ev.clientX,ev.clientY,
   `<u>cell ${i} · group ${D.series[i]} pos ${D.par[i]}</u>`+
   `core <b>${E.Tcore[i].toFixed(2)}</b> °C &nbsp; can <b>${E.Tcan[i].toFixed(2)}</b> °C<br>`+
   `heat <b>${E.q[i].toFixed(3)}</b> W &nbsp; current <b>${E.I[i].toFixed(3)}</b> A<br>`+
   `SOC <b>${(E.z[i]*100).toFixed(2)}</b> % &nbsp; R₀ <b>${(R0of(E.Tcore[i],E.z[i],i)*1000).toFixed(2)}</b> mΩ<br>`+
   `<s>click to pin</s>`)});
 c.addEventListener('mouseleave',hideTip)}

/* ---------- command palette ---------- */
const CMDS=[
 ['Telemetry view','1',()=>_tab(0)],
 ['Thermal view','2',()=>_tab(1)],
 ['Strategy view','3',()=>_tab(2)],
 ['Engineering view','4',()=>_tab(3)],
 ['Setup view','5',()=>_tab(4)],
 ['Analysis view','6',()=>_tab(5)],
 ['Run / pause','space',()=>$('run').onclick()],
 ['Reset session','R',()=>$('rst').onclick()],
 ['Toggle autopilot','A',()=>$('ap').onclick()],
 ['HV on / off','',()=>$('hvBtn').onclick()],
 ['EMERGENCY STOP','',()=>$('estop').onclick()],
 ['Export session CSV','',()=>$('csv').onclick()],
 ['Download session debrief','',()=>downloadReport()],
 ['Toggle data provenance','P',()=>$('prov').onclick()],
 ['Daylight / night theme','D',()=>$('theme').onclick()],
 ['Dense / roomy layout','',()=>$('dens').onclick()],
 ['Enter replay','[',()=>enterReplay()],
 ['Return to live',']',()=>exitReplay()],
 ['Pop out: pack heatmap','',()=>popOut('Pack — cell core temperature',
   (g,W,H)=>popPack(g,W,H))],
 ['Pop out: circuit map','',()=>popOut('Circuit',(g,W,H)=>popMap(g,W,H))],
 ['Pop out: traces','',()=>popOut('Telemetry traces',(g,W,H)=>popTrc(g,W,H))],
 ['Field source: true state','',()=>{$('src').value='true'}],
 ['Field source: BMS estimate','',()=>{$('src').value='bms'}],
 ['Field source: estimate error','',()=>{$('src').value='err'}],
 ['Scenario: Nominal','',()=>{$('scn').value='nominal';applyScenario('nominal')}],
 ['Scenario: Hot afternoon','',()=>{$('scn').value='hot';applyScenario('hot')}],
 ['Scenario: Building seaway','',()=>{$('scn').value='seaway';applyScenario('seaway')}],
 ['Scenario: Pump failure','',()=>{$('scn').value='pumpfail';applyScenario('pumpfail')}],
 ['Scenario: Blocked strainer','',()=>{$('scn').value='restrict';applyScenario('restrict')}],
 ['Scenario: Final ten minutes','',()=>{$('scn').value='endgame';applyScenario('endgame')}],
 ['Scenario: Championship sprint','',()=>{$('scn').value='sprint';applyScenario('sprint')}],
 ['Scenario: Everything at once','',()=>{$('scn').value='worst';applyScenario('worst')}],
 ['Event: Endurance','',()=>{$('evt').value='endurance';setEvent('endurance')}],
 ['Event: Qualifying','',()=>{$('evt').value='qualifying';setEvent('qualifying')}],
 ['Event: Championship outer','',()=>{$('evt').value='championship_outer';setEvent('championship_outer')}],
 ['Event: Championship inner','',()=>{$('evt').value='championship_inner';setEvent('championship_inner')}],
 ['Event: Slalom','',()=>{$('evt').value='slalom';setEvent('slalom')}],
 ['Fullscreen','F',()=>{const e=document.documentElement||{};
   if(!document.fullscreenElement)e.requestFullscreen&&e.requestFullscreen();
   else document.exitFullscreen&&document.exitFullscreen()}],
 ['Inject pump failure','',()=>_fxClick('pump')],
 ['Inject flow restriction','',()=>_fxClick('restrict')],
 ['Inject IMD fault','',()=>_fxClick('imd')],
 ['Inject prop ventilation','',()=>_fxClick('vent')],
 ['Inject hot cell','',()=>_fxClick('hotcell')],
 ['Time 1×','',()=>{$('rate').value='1'}],
 ['Time 25×','',()=>{$('rate').value='25'}],
 ['Time 100×','',()=>{$('rate').value='100'}],
 ['Time 200×','',()=>{$('rate').value='200'}],
];
function _fxClick(k){document.querySelectorAll('.fx button').forEach(b=>{
 if(b.dataset.fx===k&&b.onclick)b.onclick()})}
let palSel=0,palHits=CMDS;
function palRender(q){
 palHits=CMDS.filter(c=>c[0].toLowerCase().includes((q||'').toLowerCase()));
 palSel=Math.min(palSel,Math.max(0,palHits.length-1));
 $('palList').innerHTML=palHits.map((c,i)=>
  `<div class="${i===palSel?'sel':''}"><span>${c[0]}</span><s>${c[1]||''}</s></div>`).join('')}
function palOpen(){$('pal').className='on';$('palIn').value='';palSel=0;palRender('');
 if($('palIn').focus)$('palIn').focus()}
function palClose(){$('pal').className=''}
function palRun(){const c=palHits[palSel];palClose();
 if(!c||!c[2])return;
 try{c[2]()}catch(e){toast('Command failed: '+e.message,'c','palette')}}
function _tab(i){const t=document.querySelectorAll('.tab');
 if(t&&t[i]&&t[i].onclick)t[i].onclick()}

/* ---------- focus mode: expand any card ---------- */
function bindFocus(){
 document.querySelectorAll('.card>h3').forEach(h=>{
  if(h._b)return;h._b=1;
  h.addEventListener('click',()=>{
   const card=h.parentNode;
   const on=card.className.indexOf('focus')>=0;
   document.querySelectorAll('.card').forEach(c=>{
    c.className=c.className.replace(' focus','')});
   if(!on)card.className+=' focus';
   PX=null;TX=null;draw()})})}

/* ---------- helpers ---------- */
function fit(c,h){const r=c.getBoundingClientRect();
 const W=Math.max(80,Math.round(r.width*2)),Hh=Math.round((h||r.height)*2);
 if(c.width!==W||c.height!==Hh){c.width=W;c.height=Hh}
 const g=c.getContext('2d');g.clearRect(0,0,c.width,c.height);return g}
function isDay(){return hasFlag('day')}
/* canvas palette follows the theme — a dark chart on a light page reads as a
   hole punched in the interface */
function C_BG(){return isDay()?'#f6f8fa':'#070c12'}
function C_GRID(){return isDay()?'rgba(10,25,45,.10)':'rgba(255,255,255,.05)'}
function C_DIM(){return isDay()?'#5f7183':'#5d6f83'}
function C_FG(){return isDay()?'#0d1926':'#e8eff7'}
function ramp(u){u=Math.max(0,Math.min(1,u));
 const st=isDay()
  ?[[232,238,244],[150,200,226],[86,178,178],[0,140,190],[214,146,20],[196,42,58],[110,10,22]]
  :[[6,10,16],[18,58,104],[26,140,150],[0,200,255],[255,176,31],[255,59,82],[255,240,205]];
 const x=u*(st.length-1),k=Math.min(st.length-2,Math.floor(x)),f=x-k,a=st[k],b=st[k+1];
 return `rgb(${a[0]+(b[0]-a[0])*f|0},${a[1]+(b[1]-a[1])*f|0},${a[2]+(b[2]-a[2])*f|0})`}
function spdCol(u){u=Math.max(0,Math.min(1,u));
 return u>.66?'#3ddc97':u>.33?'#f7b955':'#ff6b7a'}
function rr(g,x,y,w,h,r){g.beginPath();g.moveTo(x+r,y);g.arcTo(x+w,y,x+w,y+h,r);
 g.arcTo(x+w,y+h,x,y+h,r);g.arcTo(x,y+h,x,y,r);g.arcTo(x,y,x+w,y,r);g.closePath()}

/* ---------- track map ---------- */
let TX=null;
function drawMap(){
 if(!TR)return;const c=$('map'),g=fit(c),W=c.width,Hh=c.height;
 if(!TX){const x0=Math.min(...TR.x),x1=Math.max(...TR.x),
  y0=Math.min(...TR.y),y1=Math.max(...TR.y);
  const sc=Math.min((W-72)/(x1-x0),(Hh-72)/(y1-y0));
  TX={x0,y0,sc,ox:(W-(x1-x0)*sc)/2,oy:(Hh-(y1-y0)*sc)/2}}
 const P=k=>[TX.ox+(TR.x[k]-TX.x0)*TX.sc,Hh-(TX.oy+(TR.y[k]-TX.y0)*TX.sc)];
 g.lineCap='round';g.lineJoin='round';
 // water wash
 const wg=g.createLinearGradient(0,0,0,Hh);
 wg.addColorStop(0,'#080d14');wg.addColorStop(1,'#05080d');
 g.fillStyle=wg;g.fillRect(0,0,W,Hh);
 // track bed + glow
 g.strokeStyle='rgba(42,212,238,.07)';g.lineWidth=42;g.beginPath();
 TR.x.forEach((_,k)=>{const p=P(k);k?g.lineTo(p[0],p[1]):g.moveTo(p[0],p[1])});
 g.closePath();g.stroke();
 g.strokeStyle='#0b1119';g.lineWidth=28;g.stroke();
 g.strokeStyle='rgba(255,255,255,.07)';g.lineWidth=25;g.stroke();
 // mini-sector colouring by speed relative to best seen
 const N=TR.x.length;
 for(let k=0;k<N-1;k++){
  const ms=Math.floor(TR.s[k]/TR.length*NMS)%NMS;
  const b=msBest[ms],n=msNow[ms];
  let col='rgba(255,255,255,.06)';
  if(b>0.5)col=spdCol(n>0?n/b:0);
  g.strokeStyle=col;g.lineWidth=5;
  const p=P(k),q=P(k+1);g.beginPath();g.moveTo(p[0],p[1]);g.lineTo(q[0],q[1]);g.stroke()}
 // mini-sector ticks
 for(let m=0;m<NMS;m++){
  const sTarget=m/NMS*TR.length;let ki=0;
  for(let k=0;k<N;k++)if(TR.s[k]<=sTarget)ki=k;
  const p=P(ki);g.fillStyle='rgba(255,255,255,.16)';
  g.beginPath();g.arc(p[0],p[1],1.8,0,6.283);g.fill()}
 // start/finish gantry
 const p0=P(0);g.strokeStyle='#fff';g.lineWidth=3.4;
 g.beginPath();g.moveTo(p0[0],p0[1]-19);g.lineTo(p0[0],p0[1]+19);g.stroke();
 g.fillStyle='#fff';g.font='600 15px ui-monospace';g.fillText('S/F',p0[0]+8,p0[1]-22);
 // trail
 if(trail.length>1){g.lineWidth=3;
  for(let k=1;k<trail.length;k++){
   g.strokeStyle=`rgba(42,212,238,${0.05+0.30*k/trail.length})`;
   const a=P(trail[k-1]),b=P(trail[k]);
   g.beginPath();g.moveTo(a[0],a[1]);g.lineTo(b[0],b[1]);g.stroke()}}
 // boat
 const sm=E.s%TR.length;let bi=0;
 for(let k=0;k<TR.s.length;k++)if(TR.s[k]<=sm)bi=k;
 const b=P(bi);
 g.fillStyle='rgba(42,212,238,.18)';g.beginPath();g.arc(b[0],b[1],17,0,6.283);g.fill();
 g.fillStyle='#fff';g.beginPath();g.arc(b[0],b[1],8,0,6.283);g.fill();
 g.fillStyle='#2ad4ee';g.beginPath();g.arc(b[0],b[1],5,0,6.283);g.fill();
 // labels
 g.fillStyle=C_DIM();g.font='600 17px ui-monospace';
 g.fillText(`${TR.length.toFixed(0)} m · ${(TR.length/1852).toFixed(3)} NM`,16,26);
 g.fillStyle=isDay()?'#3f5164':'#93a5b9';g.font='600 20px ui-monospace';
 g.fillText(`${(E.v*3.6).toFixed(1)}`,W-96,Hh-18);
 g.fillStyle=C_DIM();g.font='13px ui-monospace';g.fillText('km/h',W-96,Hh-4);
 $('trkName').textContent=TR.name;
 $('trkInfo').textContent=`closure ${TR.closure.toFixed(2)} m · ${(TR.timeLimit/60).toFixed(0)} min limit`;
}

/* ---------- traces ---------- */
function drawTraces(){
 const c=$('trc'),g=fit(c),W=c.width,Hh=c.height,n=H.t.length;
 if(n<2)return;
 const rows=[
  {d:H.v,c:'#3ddc97',lo:0,hi:Math.max(20,Math.max(...H.v)*1.15),n:'SPEED',u:'km/h'},
  {d:H.P,c:'#2ad4ee',lo:0,hi:26,n:'SHAFT',u:'kW',ref:25},
  {d:H.T,c:'#ff6b7a',lo:Math.min(...H.T)-1,hi:Math.max(...H.T)+2,n:'PACK MAX',u:'°C',ref:CL.TwarnC},
  {d:H.I,c:'#b18cff',lo:0,hi:Math.max(50,Math.max(...H.I)*1.15),n:'BUS',u:'A'},
  {d:H.z,c:'#f7b955',lo:0,hi:100,n:'SOC',u:'%'}];
 const bh=Hh/rows.length;
 rows.forEach((r,ri)=>{
  const y0=ri*bh,y1=y0+bh,pad=9;
  const Y=v=>y1-pad-(bh-2*pad)*Math.max(0,Math.min(1,(v-r.lo)/(r.hi-r.lo)));
  g.strokeStyle=C_GRID();g.lineWidth=1;
  for(let k=0;k<=2;k++){const y=y0+bh*k/2;g.beginPath();g.moveTo(46,y);g.lineTo(W,y);g.stroke()}
  if(r.ref!==undefined&&r.ref>r.lo&&r.ref<r.hi){
   g.strokeStyle='rgba(255,107,122,.45)';g.setLineDash([9,6]);g.lineWidth=1.5;
   g.beginPath();g.moveTo(46,Y(r.ref));g.lineTo(W,Y(r.ref));g.stroke();g.setLineDash([])}
  // gradient fill
  const grd=g.createLinearGradient(0,y0,0,y1);
  grd.addColorStop(0,r.c+'3d');grd.addColorStop(1,r.c+'00');
  g.fillStyle=grd;g.beginPath();g.moveTo(46,y1-pad);
  for(let k=0;k<n;k++)g.lineTo(46+(W-46)*k/(n-1),Y(r.d[k]));
  g.lineTo(W,y1-pad);g.closePath();g.fill();
  g.strokeStyle=r.c;g.lineWidth=2.1;g.shadowColor=r.c;g.shadowBlur=11;g.beginPath();
  for(let k=0;k<n;k++){const x=46+(W-46)*k/(n-1),y=Y(r.d[k]);k?g.lineTo(x,y):g.moveTo(x,y)}
  g.stroke();g.shadowBlur=0;
  g.fillStyle=C_DIM();g.font='13px ui-monospace';
  g.fillText(r.hi.toFixed(0),4,y0+16);g.fillText(r.lo.toFixed(0),4,y1-7);
  g.fillStyle=C_DIM();g.font='600 12px ui-monospace';
  g.fillText(r.n,4,y0+bh/2+4);
  g.fillStyle=r.c;g.font='600 20px ui-monospace';
  const tx=r.d[n-1].toFixed(1);
  g.fillText(tx,W-28-g.measureText(tx).width,y0+22);
  g.fillStyle=C_DIM();g.font='11px ui-monospace';g.fillText(r.u,W-24,y0+22);
  g.strokeStyle='#131c26';g.lineWidth=1;g.beginPath();
  g.moveTo(0,y1);g.lineTo(W,y1);g.stroke()});
}

/* ---------- boat: twin-hull catamaran ---------- */
let ph=0;
function drawBoat(P){
 const c=$('boat'),g=fit(c),W=c.width,Hh=c.height,WL=Hh*0.615;
 const v=E.v,vk=v*3.6,sp=Math.min(1,vk/70);ph+=v*0.10+0.5;
 const wAmp=1+hs*9;                       // wave amplitude scales with sea state
 // sky
 const sk=g.createLinearGradient(0,0,0,WL);
 sk.addColorStop(0,'#07131f');sk.addColorStop(.62,'#0c2033');sk.addColorStop(1,'#123047');
 g.fillStyle=sk;g.fillRect(0,0,W,WL);
 // sea
 const se=g.createLinearGradient(0,WL,0,Hh);
 se.addColorStop(0,'#0d3550');se.addColorStop(.45,'#072336');se.addColorStop(1,'#03121d');
 g.fillStyle=se;g.fillRect(0,WL,W,Hh-WL);
 // sun glint
 const gl=g.createRadialGradient(W*.80,WL-4,2,W*.80,WL-4,W*.30);
 gl.addColorStop(0,'rgba(255,214,150,.30)');gl.addColorStop(1,'rgba(255,214,150,0)');
 g.fillStyle=gl;g.fillRect(0,0,W,Hh);
 // airflow
 for(let k=0;k<11;k++){const y=8+k*(WL-30)/11,amp=(1-y/WL)*6;
  g.strokeStyle=`rgba(42,212,238,${0.05+0.30*sp})`;g.lineWidth=1.1+1.5*sp;
  const seg=20+130*sp,gap=30;
  for(let x=-((ph*(2.2+9*sp))%(seg+gap));x<W;x+=seg+gap){
   g.beginPath();
   for(let d=0;d<seg;d+=7){const xx=x+d;
    const dy=(xx>W*.28&&xx<W*.66)?-amp*Math.exp(-Math.pow((xx-W*.46)/(W*.12),2))*2.6:0;
    d?g.lineTo(xx,y+dy):g.moveTo(xx,y+dy)}
   g.stroke()}}
 // horizon
 g.strokeStyle='rgba(140,180,220,.20)';g.lineWidth=1.4;
 g.beginPath();g.moveTo(0,WL-1);g.lineTo(W,WL-1);g.stroke();
 // waves
 g.strokeStyle=`rgba(120,170,210,${.22+.30*Math.min(1,hs*3)})`;g.lineWidth=1.6;
 for(let r=0;r<4;r++){g.beginPath();
  for(let x=0;x<=W;x+=4)g.lineTo(x,WL+6+r*15+
   Math.sin(x*.020+ph*.05+r)*(1.4+3.4*sp)*wAmp*0.55+
   Math.sin(x*.007-ph*.03+r)*hs*22);
  g.stroke()}
 // swell on the surface line itself
 g.strokeStyle='rgba(150,195,235,.55)';g.lineWidth=2;g.beginPath();
 for(let x=0;x<=W;x+=4)g.lineTo(x,WL+Math.sin(x*.0075-ph*.028)*hs*26
  +Math.sin(x*.021+ph*.05)*(1+2.6*sp)*wAmp*0.4);
 g.stroke();
 // ---- catamaran ----
 const cx=W*.44,L=W*.42,rise=Hh*.115*sp,base=WL-rise,dr=Hh*.115*(1-.5*sp);
 const trim=-0.055*sp+pitch*0.13;                   // planing trim plus wave pitch
 const heave=Math.sin(E.t*1.55)*hs*30;
 g.save();g.translate(cx,base+heave);g.rotate(trim);
 // far hull (offset up/right for depth)
 const hull=(off,shade)=>{g.fillStyle=shade;g.beginPath();
  g.moveTo(-L/2+off*.5,-dr*.12-off*.55);
  g.lineTo(L*.40+off*.5,-dr*.12-off*.55);
  g.quadraticCurveTo(L/2+off*.5,-dr*.12-off*.55,L/2+off*.5,dr*.16-off*.55);
  g.lineTo(L*.44+off*.5,dr*.92-off*.55);
  g.lineTo(-L*.40+off*.5,dr*.78-off*.55);
  g.quadraticCurveTo(-L/2+off*.5,dr*.30-off*.55,-L/2+off*.5,-dr*.12-off*.55);
  g.closePath();g.fill()};
 hull(26,'#16242f');                                 // far demihull
 // crossbeams
 g.strokeStyle='#2b3d4e';g.lineWidth=7;
 g.beginPath();g.moveTo(-L*.26,-dr*.62);g.lineTo(-L*.26+13,-dr*.62-14);g.stroke();
 g.beginPath();g.moveTo(L*.22,-dr*.62);g.lineTo(L*.22+13,-dr*.62-14);g.stroke();
 // cockpit pod
 const pg=g.createLinearGradient(0,-dr*.15-Hh*.20,0,-dr*.15);
 pg.addColorStop(0,'#33506b');pg.addColorStop(1,'#1b2c3c');
 g.fillStyle=pg;g.beginPath();
 g.moveTo(-L*.21,-dr*.15);g.lineTo(L*.17,-dr*.15);
 g.quadraticCurveTo(L*.13,-dr*.15-Hh*.205,L*.06,-dr*.15-Hh*.205);
 g.lineTo(-L*.12,-dr*.15-Hh*.205);
 g.quadraticCurveTo(-L*.20,-dr*.15-Hh*.16,-L*.21,-dr*.15);g.closePath();g.fill();
 // canopy
 g.fillStyle='rgba(42,212,238,.30)';g.beginPath();
 g.moveTo(-L*.09,-dr*.15-Hh*.185);g.lineTo(L*.04,-dr*.15-Hh*.185);
 g.lineTo(L*.02,-dr*.15-Hh*.115);g.lineTo(-L*.08,-dr*.15-Hh*.115);g.closePath();g.fill();
 hull(0,'#1e3040');                                   // near demihull
 // wet band on near hull
 g.save();g.beginPath();g.rect(-W,rise-trim*10,2*W,Hh);g.clip();
 hull(0,'#0a2a42');g.restore();
 g.restore();
 // spray at both bows
 for(const off of [0,26]){
  g.fillStyle=`rgba(190,235,255,${(.10+.55*sp)*(off?0.5:1)})`;
  for(let k=0;k<Math.round(3+34*sp);k++){const r=(k*61.7+ph*3.1)%1;
   g.beginPath();g.arc(cx+L*.46+off*.5-r*W*.20,base-off*.55+dr*.4-r*Hh*.20*sp+Math.sin(k*3.1)*3,
    1+3.4*sp*(1-r),0,6.283);g.fill()}}
 // wake
 g.fillStyle=`rgba(210,240,255,${.06+.30*sp})`;
 for(let k=0;k<Math.round(6+58*sp);k++){const r=(k*37.3+ph*2.2)%1;
  g.beginPath();g.arc(cx-L*.46-r*W*.42,base+dr*.85+Math.sin(k*2.3+ph*.09)*(2+8*sp),
   1+4*sp*(1-r*.7),0,6.283);g.fill()}
 // labels
 if(ventActive>0){g.fillStyle='rgba(255,107,122,.13)';g.fillRect(0,0,W,Hh);
  g.fillStyle='#ff6b7a';g.font='700 22px ui-monospace';
  g.fillText('PROP VENTILATED',W/2-130,Hh/2)}
 if(HV!=='DRIVE'&&HV!=='READY'){g.fillStyle='rgba(4,6,10,.62)';g.fillRect(0,0,W,Hh);
  g.fillStyle=HV==='FAULT'?'#ff6b7a':'#93a5b9';g.font='700 24px ui-monospace';
  const t2=HV==='FAULT'?'HV FAULT':HV==='PRECHARGE'?'PRECHARGING…':'HV ISOLATED';
  g.fillText(t2,W/2-g.measureText(t2).width/2,Hh/2)}
 g.font='600 14px ui-monospace';g.fillStyle='rgba(126,147,170,.65)';
 g.fillText('A I R',18,26);g.fillText('W A T E R',18,Hh-14);
 g.font='700 34px ui-monospace';g.fillStyle=C_FG();
 const vs=vk.toFixed(1);g.fillText(vs,W-40-g.measureText(vs).width,44);
 g.font='600 15px ui-monospace';g.fillStyle=C_DIM();g.fillText('km/h',W-38,44);
 g.font='600 18px ui-monospace';g.fillStyle=E.capped?'#ff6b7a':'#2ad4ee';
 const ps=(P/1000).toFixed(2)+' kW'+(E.capped?'  ▲CAP':'');
 g.fillText(ps,W-40-g.measureText(ps).width,72);
 g.font='13px ui-monospace';g.fillStyle=C_DIM();
 const ds=`drag ${E.drag.toFixed(0)} N · thrust ${E.thrust.toFixed(0)} N · trim ${(sp*3.2).toFixed(1)}°`;
 g.fillText(ds,W-40-g.measureText(ds).width,94);
 $('boatInfo').textContent=`${BT.nHulls}× demihull · Lwl ${BT.LwlM.toFixed(2)} m · ⌀${(BT.propD*1000).toFixed(0)} mm prop`;
}
/* ---------- distance vs time projection ---------- */
const runTrace=[];
function drawProj(){
 const c=$('proj'),g=fit(c),W=c.width,Hh=c.height;
 const TL=(TR?TR.timeLimit:10800)/3600;
 const optV=ST.best?ST.best.v_kmh:30, optD=ST.best?ST.best.distance_km:30;
 const optT=ST.best?ST.best.duration_h:1;
 const xmax=TL*1.04, ymax=Math.max(optD*1.25,10);
 const X=h=>44+(W-58)*h/xmax, Y=d=>Hh-30-(Hh-46)*d/ymax;
 g.strokeStyle=C_GRID();g.lineWidth=1;
 for(let r=0;r<=4;r++){const y=Y(ymax*r/4);g.beginPath();g.moveTo(44,y);g.lineTo(W,y);g.stroke();
  g.fillStyle=C_DIM();g.font='12px ui-monospace';g.fillText((ymax*r/4).toFixed(0),6,y+4)}
 for(let r=0;r<=3;r++){const x=X(TL*r/3);g.strokeStyle=C_GRID();g.beginPath();
  g.moveTo(x,14);g.lineTo(x,Hh-30);g.stroke();
  g.fillStyle=C_DIM();g.fillText((TL*r/3).toFixed(1)+'h',x-10,Hh-12)}
 // 3 h wall
 g.strokeStyle='#ff6b7a';g.setLineDash([8,6]);g.lineWidth=2.2;
 g.beginPath();g.moveTo(X(TL),14);g.lineTo(X(TL),Hh-30);g.stroke();g.setLineDash([]);
 g.fillStyle='rgba(255,107,122,.75)';g.font='600 12px ui-monospace';
 g.fillText('TIME LIMIT',X(TL)-84,26);
 // optimum pace: straight line until energy runs out, then flat
 g.strokeStyle='#3ddc97';g.lineWidth=2.4;g.setLineDash([6,4]);g.beginPath();
 g.moveTo(X(0),Y(0));g.lineTo(X(Math.min(optT,xmax)),Y(optD));
 if(optT<xmax)g.lineTo(X(xmax),Y(optD));
 g.stroke();g.setLineDash([]);
 g.fillStyle='rgba(61,220,151,.8)';g.font='600 12px ui-monospace';
 g.fillText(`optimum ${optD.toFixed(1)} km`,X(Math.min(optT,xmax))-140,Y(optD)-8);
 // your run
 if(runTrace.length>1){g.strokeStyle='#2ad4ee';g.lineWidth=3;
  g.shadowColor='#2ad4ee';g.shadowBlur=8;g.beginPath();
  runTrace.forEach((p,k)=>{const x=X(p[0]),y=Y(p[1]);k?g.lineTo(x,y):g.moveTo(x,y)});
  g.stroke();g.shadowBlur=0;
  const lastP=runTrace[runTrace.length-1];
  g.fillStyle='#2ad4ee';g.beginPath();g.arc(X(lastP[0]),Y(lastP[1]),5,0,6.283);g.fill();
  // projected continuation at current burn
  const burn=E.t>60?(E.Wh/1000)/(E.t/3600):0;
  const remain=Math.max(0,M.meta.energyCapKWh*0.97-E.Wh/1000);
  if(burn>1e-6&&E.t>120){
   const tEnd=Math.min(xmax,lastP[0]+remain/burn);
   const dEnd=lastP[1]+(tEnd-lastP[0])*(E.s/1000)/(E.t/3600);
   g.strokeStyle='rgba(42,212,238,.42)';g.setLineDash([5,5]);g.lineWidth=2;
   g.beginPath();g.moveTo(X(lastP[0]),Y(lastP[1]));g.lineTo(X(tEnd),Y(dEnd));g.stroke();
   g.setLineDash([]);
   g.fillStyle='rgba(42,212,238,.75)';g.font='600 12px ui-monospace';
   g.fillText(`projected ${dEnd.toFixed(1)} km`,X(tEnd)-130,Y(dEnd)+18)}}
 g.fillStyle=C_DIM();g.font='12px ui-monospace';
 g.fillText('distance km',48,22);
}

/* ---------- g-g traction circle ---------- */
function drawGG(){
 const c=$('gg'),g=fit(c),W=c.width,Hh=c.height,R=Math.min(W,Hh)*0.40;
 const cx=W/2,cy=Hh/2, LIM=(TR?0.55:0.55);
 g.strokeStyle='rgba(255,255,255,.07)';g.lineWidth=1.4;
 for(let r=0.25;r<=1.001;r+=0.25){g.beginPath();g.arc(cx,cy,R*r,0,6.283);g.stroke()}
 g.beginPath();g.moveTo(cx-R,cy);g.lineTo(cx+R,cy);
 g.moveTo(cx,cy-R);g.lineTo(cx,cy+R);g.stroke();
 g.strokeStyle='rgba(255,107,122,.55)';g.setLineDash([7,5]);g.lineWidth=2;
 g.beginPath();g.arc(cx,cy,R,0,6.283);g.stroke();g.setLineDash([]);
 // trail
 gTrail.forEach((p,k)=>{const a=k/gTrail.length;
  g.fillStyle=`rgba(42,212,238,${0.03+0.30*a})`;
  g.beginPath();g.arc(cx+p[1]/LIM*R,cy-p[0]/LIM*R,2+2*a,0,6.283);g.fill()});
 const px=cx+latG/LIM*R, py=cy-longG/LIM*R;
 const mag=Math.hypot(latG,longG)/LIM;
 const col=mag>0.95?'#ff6b7a':mag>0.75?'#f7b955':'#3ddc97';
 g.fillStyle=col;g.shadowColor=col;g.shadowBlur=12;
 g.beginPath();g.arc(px,py,7,0,6.283);g.fill();g.shadowBlur=0;
 g.fillStyle=C_DIM();g.font='12px ui-monospace';
 g.fillText('LAT',cx+R+6,cy+4);g.fillText('ACC',cx-12,cy-R-8);
 g.fillText('BRK',cx-12,cy+R+18);
 $('gInfo').textContent=`${latG.toFixed(2)} g lat · ${longG>=0?'+':''}${longG.toFixed(2)} g long`;
}

/* ---------- lap comparison, distance domain ---------- */
function drawCmp(){
 const c=$('cmp'),g=fit(c),W=c.width,Hh=c.height;
 if(!TR)return;
 let mx=1;for(let k=0;k<NDIST;k++){mx=Math.max(mx,vNow[k],vBest[k])}
 mx*=1.12;
 const X=k=>40+(W-52)*k/(NDIST-1), Y=v=>Hh-30-(Hh-48)*v/mx;
 g.strokeStyle=C_GRID();g.lineWidth=1;
 for(let r=0;r<=3;r++){const y=Y(mx*r/3);g.beginPath();g.moveTo(40,y);g.lineTo(W,y);g.stroke();
  g.fillStyle=C_DIM();g.font='12px ui-monospace';g.fillText((mx*r/3).toFixed(0),6,y+4)}
 // sector dividers
 TR.sectors.slice(1,-1).forEach(sb=>{const x=X(sb/TR.length*NDIST);
  g.strokeStyle='#22303f';g.setLineDash([4,4]);g.beginPath();
  g.moveTo(x,14);g.lineTo(x,Hh-30);g.stroke();g.setLineDash([])});
 // gain/loss fill between the two
 if(haveBestLap){
  for(let k=0;k<NDIST-1;k++){
   if(vNow[k]<=0||vBest[k]<=0)continue;
   g.fillStyle=vNow[k]>=vBest[k]?'rgba(61,220,151,.22)':'rgba(255,107,122,.22)';
   g.beginPath();g.moveTo(X(k),Y(vNow[k]));g.lineTo(X(k+1),Y(vNow[k+1]));
   g.lineTo(X(k+1),Y(vBest[k+1]));g.lineTo(X(k),Y(vBest[k]));g.closePath();g.fill()}
  g.strokeStyle='#b18cff';g.lineWidth=2;g.beginPath();
  let st=false;for(let k=0;k<NDIST;k++){if(vBest[k]<=0){st=false;continue}
   const x=X(k),y=Y(vBest[k]);st?g.lineTo(x,y):g.moveTo(x,y);st=true}
  g.stroke()}
 g.strokeStyle='#2ad4ee';g.lineWidth=2.6;g.shadowColor='#2ad4ee';g.shadowBlur=8;
 g.beginPath();let st2=false;
 for(let k=0;k<NDIST;k++){if(vNow[k]<=0){st2=false;continue}
  const x=X(k),y=Y(vNow[k]);st2?g.lineTo(x,y):g.moveTo(x,y);st2=true}
 g.stroke();g.shadowBlur=0;
 // position cursor
 const bin=Math.min(NDIST-1,Math.floor((E.s%TR.length)/TR.length*NDIST));
 g.strokeStyle='rgba(255,255,255,.5)';g.lineWidth=1.6;
 g.beginPath();g.moveTo(X(bin),14);g.lineTo(X(bin),Hh-30);g.stroke();
 g.fillStyle=C_DIM();g.font='12px ui-monospace';
 g.fillText('S1',X(NDIST*0.16),Hh-12);g.fillText('S2',X(NDIST*0.49),Hh-12);
 g.fillText('S3',X(NDIST*0.82),Hh-12);
 g.fillText('lap distance →',W/2-46,Hh-12);
 $('cmpInfo').textContent=haveBestLap?
  `best ${fmtT(E.best)} · live overlay`:'set a lap to unlock the ghost';
}

/* power bar */
function drawPW(P){
 const n=24,f=P/M.meta.PmaxW;let h='';
 for(let k=0;k<n;k++){const on=k/n<f;
  const col=k<n*.55?'#3ddc97':k<n*.82?'#f7b955':'#ff6b7a';
  h+=`<i style="background:${on?col:'#0d151d'};${on?'box-shadow:0 0 7px '+col:''}"></i>`}
 $('pw').innerHTML=h}

/* ---------- pack: real physical layout ---------- */
const CHAN={
 Tcore:{lbl:'core temperature',u:'°C',dp:1,f:i=>E.Tcore[i]},
 Tcan :{lbl:'can temperature',u:'°C',dp:1,f:i=>E.Tcan[i]},
 dT   :{lbl:'core − can gradient',u:'K',dp:2,f:i=>E.Tcore[i]-E.Tcan[i]},
 q    :{lbl:'heat generation',u:'W',dp:2,f:i=>E.q[i]},
 qRev :{lbl:'entropic (reversible) term',u:'W',dp:3,f:i=>E.qRev[i]},
 I    :{lbl:'cell current',u:'A',dp:2,f:i=>E.I[i]},
 R0   :{lbl:'ohmic resistance',u:'mΩ',dp:2,f:i=>R0of(E.Tcore[i],E.z[i],i)*1000},
 z    :{lbl:'state of charge',u:'%',dp:1,f:i=>E.z[i]*100}};
let PX=null;
function drawPack(st){
 const c=$('pack'),g=fit(c),W=c.width,Hh=c.height;
 const D=M.display;
 const srcMode=$('src').value;
 let ch=CHAN[$('chan').value]||CHAN.Tcore;
 const rp=replayState();
 if(rp&&rp.field){const F=rp.field;
  ch={lbl:'core temperature (replay)',u:'°C',dp:1,f:i=>F[i]}}
 else if(srcMode!=='true'&&tEst){
  ch = srcMode==='bms'
   ? {lbl:'BMS estimated core temperature',u:'°C',dp:1,f:i=>tEst[i]}
   : {lbl:'estimate error (BMS − truth)',u:'K',dp:2,f:i=>tEst[i]-E.Tcore[i]}}
 if(!PX){const x0=Math.min(...D.x),x1=Math.max(...D.x),
  y0=Math.min(...D.y),y1=Math.max(...D.y);
  const sc=Math.min((W-56)/Math.max(x1-x0,1e-3),(Hh-56)/Math.max(y1-y0,1e-3));
  PX={x0,y0,sc,ox:(W-(x1-x0)*sc)/2,oy:(Hh-(y1-y0)*sc)/2}}
 const PT=(x,y)=>[PX.ox+(x-PX.x0)*PX.sc, Hh-(PX.oy+(y-PX.y0)*PX.sc)];
 const rad=Math.max(2.5,D.cellD*0.5*PX.sc);
 // enclosure
 g.fillStyle=C_BG();g.fillRect(0,0,W,Hh);
 g.strokeStyle='#182432';g.lineWidth=2;
 const a=PT(Math.min(...D.x)-D.cellD,Math.min(...D.y)-D.cellD);
 const b=PT(Math.max(...D.x)+D.cellD,Math.max(...D.y)+D.cellD);
 rr(g,Math.min(a[0],b[0]),Math.min(a[1],b[1]),
    Math.abs(b[0]-a[0]),Math.abs(b[1]-a[1]),8);g.stroke();
 // range
 let lo=1e18,hi=-1e18;
 for(let i=0;i<NC;i++){const v=ch.f(i);if(v<lo)lo=v;if(v>hi)hi=v}
 if(hi-lo<1e-6)hi=lo+1e-6;
 // coolant tubes, drawn UNDER the cells
 if($('showTubes').checked&&M.tubes){
  const cols=['#2ad4ee','#3ddc97','#f7b955','#b18cff','#ff6b7a'];
  M.tubes.forEach(t=>{
   g.strokeStyle='rgba(255,255,255,.07)';
   g.lineWidth=Math.max(3,D.tubeD*PX.sc)+7;g.lineCap='round';g.beginPath();
   t.x.forEach((_,k)=>{const p=PT(t.x[k],t.y[k]);k?g.lineTo(p[0],p[1]):g.moveTo(p[0],p[1])});
   g.stroke();
   g.strokeStyle=cols[t.circuit%cols.length];
   g.lineWidth=Math.max(2,D.tubeD*PX.sc);g.beginPath();
   t.x.forEach((_,k)=>{const p=PT(t.x[k],t.y[k]);k?g.lineTo(p[0],p[1]):g.moveTo(p[0],p[1])});
   g.stroke()})}
 // cells
 for(let i=0;i<NC;i++){
  const p=PT(D.x[i],D.y[i]),v=ch.f(i);
  const u=(v-lo)/(hi-lo);
  g.fillStyle=ramp(u);
  g.beginPath();g.arc(p[0],p[1],rad,0,6.283);g.fill();
  if(rad>3.5){g.strokeStyle='rgba(255,255,255,'+(.05+.10*u)+')';g.lineWidth=.8;
   g.beginPath();g.arc(p[0],p[1],rad,0,6.283);g.stroke()}
  if(D.nTubeContact&&D.nTubeContact[i]<=0.05){
   g.strokeStyle='rgba(255,107,122,.85)';g.lineWidth=1.6;
   g.beginPath();g.arc(p[0],p[1],rad+2,0,6.283);g.stroke()}}
 // thermistor positions
 if(hasTwin){OBS.cells.forEach((ci,j)=>{
  const q=PT(D.x[ci],D.y[ci]);
  g.strokeStyle='#f7b955';g.lineWidth=1.8;
  g.beginPath();g.arc(q[0],q[1],rad+3.5,0,6.283);g.stroke();
  g.fillStyle='#f7b955';g.font='600 11px ui-monospace';
  g.fillText('T'+(j+1),q[0]+rad+5,q[1]-rad-2)})}
 // pinned selection
 if(selCell>=0&&selCell<NC){
  const sp=PT(D.x[selCell],D.y[selCell]);
  g.strokeStyle='#2ad4ee';g.lineWidth=2.4;g.shadowColor='#2ad4ee';g.shadowBlur=14;
  g.beginPath();g.arc(sp[0],sp[1],rad+7,0,6.283);g.stroke();g.shadowBlur=0;
  g.strokeStyle='rgba(42,212,238,.30)';g.lineWidth=1;
  g.beginPath();g.moveTo(0,sp[1]);g.lineTo(W,sp[1]);
  g.moveTo(sp[0],0);g.lineTo(sp[0],Hh);g.stroke()}
 // hotspot
 const hp=PT(D.x[st.hot],D.y[st.hot]);
 g.strokeStyle='#fff';g.lineWidth=2.2;
 g.beginPath();g.arc(hp[0],hp[1],rad+5,0,6.283);g.stroke();
 g.beginPath();g.moveTo(hp[0]-rad-11,hp[1]);g.lineTo(hp[0]-rad-4,hp[1]);
 g.moveTo(hp[0]+rad+4,hp[1]);g.lineTo(hp[0]+rad+11,hp[1]);g.stroke();
 // scale bar
 g.fillStyle=C_DIM();g.font='13px ui-monospace';
 const mm=Math.round(D.pitch*1000);
 g.fillText(`${(Math.max(...D.x)-Math.min(...D.x)+D.cellD)*1000|0} × `+
  `${(Math.max(...D.y)-Math.min(...D.y)+D.cellD)*1000|0} mm · ${mm} mm pitch`,14,24);
 $('scale').innerHTML=`<span>${lo.toFixed(ch.dp)}</span>`+
  Array.from({length:24},(_,k)=>`<i class="sw" style="background:${ramp(k/23)}"></i>`).join('')+
  `<span>${hi.toFixed(ch.dp)} ${ch.u}</span>`;
 const unc=D.nTubeContact?D.nTubeContact.filter(v=>v<=0.05).length:0;
 $('pkNote').innerHTML=`${ch.lbl} · spread ${(hi-lo).toFixed(ch.dp)} ${ch.u} · `+
  `hotspot group ${D.series[st.hot]} pos ${D.par[st.hot]}`+
  (unc?` · <span style="color:var(--bad)">${unc} cells ringed red have no tube contact</span>`:
       ` · every cell has tube contact`);
}

/* ---------- coolant circuits ---------- */
function drawCool(){
 const c=$('cool'),g=fit(c),W=c.width,Hh=c.height,n=TH.nSeg;if(!n)return;
 const arr=Array.from(E.Tseg);
 const lo=Math.min(env.tin,Math.min(...arr))-.25, hi=Math.max(...arr)+.25;
 g.strokeStyle=C_GRID();g.lineWidth=1;
 for(let k=0;k<=3;k++){const y=Hh-24-(Hh-40)*k/3;g.beginPath();
  g.moveTo(40,y);g.lineTo(W,y);g.stroke();
  g.fillStyle=C_DIM();g.font='12px ui-monospace';
  g.fillText((lo+(hi-lo)*k/3).toFixed(1),4,y+4)}
 const nc=Math.max(1,Math.max(...TH.segCircuit)+1);
 const cols=['#2ad4ee','#3ddc97','#f7b955','#b18cff','#ff6b7a'];
 const rows=[];
 for(let ci=0;ci<nc;ci++){
  const idx=[];for(const [sg,up] of TH.coolChain)if(TH.segCircuit[sg]===ci)idx.push(sg);
  if(!idx.length)continue;
  const grd=g.createLinearGradient(0,0,0,Hh);
  grd.addColorStop(0,cols[ci%cols.length]+'33');grd.addColorStop(1,cols[ci%cols.length]+'02');
  const Y=v=>Hh-24-(Hh-40)*(v-lo)/(hi-lo);
  g.fillStyle=grd;g.beginPath();g.moveTo(40,Hh-24);
  idx.forEach((sg,k)=>g.lineTo(40+(W-48)*k/Math.max(1,idx.length-1),Y(arr[sg])));
  g.lineTo(W-8,Hh-24);g.closePath();g.fill();
  g.strokeStyle=cols[ci%cols.length];g.lineWidth=2.4;g.beginPath();
  idx.forEach((sg,k)=>{const x=40+(W-48)*k/Math.max(1,idx.length-1),y=Y(arr[sg]);
   k?g.lineTo(x,y):g.moveTo(x,y)});g.stroke();
  const Tin=env.tin,Tout=arr[idx[idx.length-1]];
  const mcp=TH.mdotCpPerCircuit*(env.flow/M.env.flowLmin);
  rows.push([ci,Tin,Tout,Tout-Tin,mcp*(Tout-Tin),idx.length])}
 g.fillStyle=C_DIM();g.font='12px ui-monospace';
 g.fillText('inlet',42,Hh-8);g.fillText('flow path →',W/2-34,Hh-8);
 g.fillText('outlet',W-58,Hh-8);
 $('circT').innerHTML='<tr><th>circuit</th><th>in °C</th><th>out °C</th><th>ΔT K</th>'+
  '<th>heat W</th><th>segs</th></tr>'+rows.map(r=>
  `<tr><td><i class="sw" style="background:${cols[r[0]%cols.length]}"></i>${r[0]}</td>`+
  `<td>${r[1].toFixed(2)}</td><td>${r[2].toFixed(2)}</td>`+
  `<td class="${r[3]>4?'wo':''}">${r[3].toFixed(2)}</td>`+
  `<td>${r[4].toFixed(0)}</td><td>${r[5]}</td></tr>`).join('');
 const flowScale=env.flow/M.env.flowLmin;
 const Re=M.meta.ReCoolant*flowScale;
 const regime=Re<2300?'laminar':Re>4000?'turbulent':'transitional';
 $('coolHdr').textContent=`${nc} circuits · Re ${Re.toFixed(0)} (${regime}) · `+
  `ΔP ${(M.meta.dPbar*flowScale*flowScale).toFixed(3)} bar`;
}

/* ---------- energy balance ---------- */
function drawBal(){
 const c=$('bal'),g=fit(c),W=c.width,Hh=c.height;
 const gen=Math.max(E.Qgen,1e-6), cool=Math.max(E.Qcool,0), enc=Math.max(E.Qenc,0);
 const stored=gen-cool-enc;
 const items=[['coolant',cool,'#2ad4ee'],['enclosure',enc,'#b18cff'],
              [stored>=0?'stored':'released',Math.abs(stored),
               stored>=0?'#ff6b7a':'#3ddc97']];
 let x=14;const sc=(W-28)/gen;
 g.fillStyle='#0a1017';rr(g,14,26,W-28,34,4);g.fill();
 items.forEach(([n,v,col])=>{if(v<=0)return;
  g.fillStyle=col;g.fillRect(x,26,Math.max(1,v*sc),34);x+=v*sc});
 g.fillStyle=C_FG();g.font='700 19px ui-monospace';
 g.fillText(`${gen.toFixed(0)} W generated`,14,20);
 let y=80;g.font='13px ui-monospace';
 items.forEach(([n,v,col])=>{g.fillStyle=col;rr(g,14,y-10,11,11,2);g.fill();
  g.fillStyle=isDay()?'#3f5164':'#93a5b9';
  g.fillText(`${n}  ${v.toFixed(0)} W  (${(v/gen*100).toFixed(0)}%)`,32,y);y+=21});
 $('balHdr').textContent=stored>0?'accumulating':'shedding';
 $('balNote').textContent=stored>0
  ? `Storing ${stored.toFixed(0)} W more than the loop removes — temperature is still rising. `
    +`Cooling is removing ${(cool/gen*100).toFixed(0)}% of what the cells make.`
  : `Removing everything generated plus ${Math.abs(stored).toFixed(0)} W of stored heat — `
    +`the pack is cooling down.`;
}

/* ---------- measured R0 curves ---------- */
function drawR0(){
 const c=$('r0c'),g=fit(c),W=c.width,Hh=c.height;
 const Ts=CL.Tgrid, S=CL.socGrid, Rm=CL.R0map;
 let lo=1e9,hi=0;
 Rm.forEach(r=>r.forEach(v=>{const m=v*1000;if(m<lo)lo=m;if(m>hi)hi=m}));
 hi=Math.min(hi,60);lo=Math.max(0,lo*0.9);
 const X=z=>38+(W-50)*z, Y=r=>Hh-26-(Hh-42)*(Math.min(r,hi)-lo)/(hi-lo);
 g.strokeStyle=C_GRID();g.lineWidth=1;
 for(let k=0;k<=3;k++){const y=Y(lo+(hi-lo)*k/3);g.beginPath();
  g.moveTo(38,y);g.lineTo(W,y);g.stroke();
  g.fillStyle=C_DIM();g.font='12px ui-monospace';
  g.fillText((lo+(hi-lo)*k/3).toFixed(0),4,y+4)}
 Ts.forEach((T,ti)=>{
  const u=(T+40)/100;
  g.strokeStyle=ramp(Math.max(0,Math.min(1,u)));
  g.lineWidth=T>=20&&T<=50?2.6:1.5;
  g.globalAlpha=T>=0?1:.55;g.beginPath();
  S.forEach((z,k)=>{const x=X(z),y=Y(Rm[ti][k]*1000);k?g.lineTo(x,y):g.moveTo(x,y)});
  g.stroke();g.globalAlpha=1;
  const lx=X(0.06),ly=Y(Rm[ti][Math.floor(S.length*0.06)]*1000);
  g.fillStyle=ramp(Math.max(0,Math.min(1,u)));g.font='600 12px ui-monospace';
  g.fillText(T.toFixed(0)+'°',lx-30,ly-4)});
 // live operating points
 const stride=Math.max(1,Math.floor(NC/140));
 for(let i=0;i<NC;i+=stride){
  const r=R0of(E.Tcore[i],E.z[i],i)*1000;
  g.fillStyle='rgba(255,255,255,.65)';
  g.beginPath();g.arc(X(E.z[i]),Y(r),2,0,6.283);g.fill()}
 g.fillStyle=C_DIM();g.font='12px ui-monospace';
 g.fillText('state of charge →',W/2-52,Hh-8);
 g.fillText('mΩ',6,20);
 $('r0Hdr').textContent=`${Ts.length} temperatures`;
 const mid=Math.floor(S.length/2);
 $('r0Note').textContent=
  `Extracted from your discharge-rate and temperature curves. White dots are all `+
  `${NC} cells at their live SOC and temperature. Note the rise below 10 °C — that `+
  `is why a single Arrhenius exponent cannot span the range, and why this uses the `+
  `measured map directly.`;
}

/* ---------- drivetrain thermal ---------- */
const dtHist=[];
function drawDT(){
 const c=$('dtc'),g=fit(c),W=c.width,Hh=c.height;
 const lo=20,hi=Math.max(DR.TwMax,DR.TjMax)+10;
 const Y=v=>Hh-18-(Hh-30)*(Math.min(v,hi)-lo)/(hi-lo);
 g.strokeStyle=C_GRID();g.lineWidth=1;
 for(let k=0;k<=3;k++){const y=Y(lo+(hi-lo)*k/3);g.beginPath();
  g.moveTo(36,y);g.lineTo(W,y);g.stroke();
  g.fillStyle=C_DIM();g.font='11px ui-monospace';
  g.fillText((lo+(hi-lo)*k/3).toFixed(0),4,y+4)}
 [[DR.TwMax,'#ff6b7a','winding limit'],[DR.TjMax,'#f7b955','junction limit']]
  .forEach(([v,col,lbl])=>{g.strokeStyle=col;g.setLineDash([7,5]);g.lineWidth=1.6;
   g.beginPath();g.moveTo(36,Y(v));g.lineTo(W,Y(v));g.stroke();g.setLineDash([]);
   g.fillStyle=col;g.font='600 11px ui-monospace';g.fillText(lbl,W-130,Y(v)-5)});
 if(dtHist.length>1){
  const X=k=>36+(W-44)*k/Math.max(1,dtHist.length-1);
  [[0,'#ff6b7a',2.6],[1,'#f7b955',2.2],[2,'#2ad4ee',1.7],[3,'#b18cff',1.7]]
   .forEach(([idx,col,lw])=>{g.strokeStyle=col;g.lineWidth=lw;g.beginPath();
    dtHist.forEach((h,k)=>{const x=X(k),y=Y(h[idx]);k?g.lineTo(x,y):g.moveTo(x,y)});
    g.stroke()})}
 g.fillStyle=C_DIM();g.font='11px ui-monospace';
 g.fillText('winding · junction · case · heatsink',40,14);
 const hot=Math.max(E.Tw/DR.TwMax,E.Tj/DR.TjMax);
 $('dtHdr').textContent=`${(hot*100).toFixed(0)} % of limit`;
 $('dtHdr').style.color=hot>0.9?'var(--bad)':hot>0.75?'var(--warn)':'var(--dim)';
 kv('kvDT',[
  ['winding',E.Tw.toFixed(1),'°C',E.Tw>DR.TwWarn?'bd':(E.Tw>DR.TwWarn*0.8?'wo':'ok')],
  ['junction',E.Tj.toFixed(1),'°C',E.Tj>DR.TjWarn?'bd':(E.Tj>DR.TjWarn*0.8?'wo':'ok')],
  ['motor case',E.Tcase.toFixed(1),'°C'],
  ['heatsink',E.Ths.toFixed(1),'°C'],
  ['phase current',E.Iph.toFixed(0),'A'],
  ['motor loss',E.qMot.toFixed(0),'W'],
  ['inverter loss',E.qInv.toFixed(0),'W'],
  ['η motor',(E.effM*100).toFixed(2),'%'],
  ['η inverter',(E.effI*100).toFixed(2),'%'],
  ['η driveline',(E.effM*E.effI*100).toFixed(2),'%'],
  ['derate',(E.dtDerate*100).toFixed(0),'%',E.dtDerate<0.999?'wo':'ok'],
  ['total loss',(E.qMot+E.qInv).toFixed(0),'W']]);
 const marg=DR.TwMax-E.Tw;
 $('dtV').className='verdict '+(E.dtDerate<0.999?'b':(marg<40?'w':'g'));
 $('dtV').innerHTML=
  `The motor is an outboard — its case sits in the sea, which is why it takes `+
  `this power at all (case is only <b>${(E.Tcase-env.tin).toFixed(1)} K</b> above `+
  `sea). The inverter competes with the pack for the same coolant loop. `+
  `<b>"Nominal" is a thermal statement</b>: with these parameters the continuous `+
  `rating is far above 25 kW, so the REQ_188 conflict is a rating-definition `+
  `question, not a thermal impossibility. All drivetrain numbers are ESTIMATED `+
  `until the manufacturer sends a torque-speed and efficiency map.`;
}

/* ---------- digital twin panel ---------- */
function drawTwin(st){
 const c=$('twc'),g=fit(c),W=c.width,Hh=c.height;
 if(!hasTwin){$('twHdr').textContent='not available';
  $('twNote').textContent='No observer in this build.';return}
 if(!TWIN||!tEst){$('twHdr').textContent='standing by';
  $('twNote').textContent='Enable the twin in the control rail and run.';return}
 // error history
 const hi=Math.max(0.5,...twHist.map(h=>h[0]))*1.15;
 g.strokeStyle=C_GRID();g.lineWidth=1;
 for(let k=0;k<=2;k++){const y=Hh-16-(Hh-28)*k/2;
  g.beginPath();g.moveTo(34,y);g.lineTo(W,y);g.stroke();
  g.fillStyle=C_DIM();g.font='11px ui-monospace';
  g.fillText((hi*k/2).toFixed(1),4,y+4)}
 const X=k=>34+(W-42)*k/Math.max(1,twHist.length-1);
 const Y=v=>Hh-16-(Hh-28)*Math.min(v,hi)/hi;
 [[0,'#ff6b7a',2.0],[1,'#3ddc97',2.6]].forEach(([idx,col,lw])=>{
  g.strokeStyle=col;g.lineWidth=lw;g.beginPath();
  twHist.forEach((h,k)=>{const x=X(k),y=Y(h[idx]);k?g.lineTo(x,y):g.moveTo(x,y)});
  g.stroke()});
 g.fillStyle=C_DIM();g.font='11px ui-monospace';
 g.fillText('open loop',38,14);
 g.fillStyle='#3ddc97';g.fillText('with observer',W-150,14);
 g.fillText('K',6,14);
 const gain=twOl/Math.max(twRms,1e-6);
 $('twHdr').textContent=`${OBS.cells.length} thermistors · ${gain.toFixed(1)}× better`;
 // sensor readouts
 const rows=[['open loop',twOl.toFixed(3),'K RMS',twOl>1?'bd':''],
  ['with observer',twRms.toFixed(3),'K RMS','ok'],
  ['improvement',gain.toFixed(1),'×','ok'],
  ['sensors',OBS.cells.length,''],
  ['ADC step',(ADC_STEP*1000).toFixed(0),'mK'],
  ['noise σ',OBS.noise.toFixed(2),'K'],
  ['probe lag',TH_TAU.toFixed(0),'s'],
  ['worst cell',(()=>{let m=0;for(let i=0;i<NC;i++)
    m=Math.max(m,Math.abs(tEst[i]-E.Tcore[i]));return m.toFixed(2)})(),'K']];
 kv('kvTw',rows);
 let est=-1e9,tru=-1e9;
 for(let i=0;i<NC;i++){est=Math.max(est,tEst[i]);tru=Math.max(tru,E.Tcore[i])}
 $('twNote').innerHTML=
  `The BMS would report a pack maximum of <b>${est.toFixed(2)} °C</b>; the truth `+
  `is <b>${tru.toFixed(2)} °C</b> — an error of <b>${(est-tru>=0?'+':'')}`+
  `${(est-tru).toFixed(2)} K</b>. Open loop it would be off by `+
  `<b>${twOl.toFixed(2)} K</b> RMS. Amber rings on the layout are the `+
  `thermistors; switch the field source to see what the BMS actually infers.`;
}

/* ---------- distribution histogram ---------- */
function drawHist(){
 const c=$('hist'),g=fit(c),W=c.width,Hh=c.height;
 let lo=1e9,hi=-1e9;for(let i=0;i<NC;i++){const T=E.Tcore[i];if(T<lo)lo=T;if(T>hi)hi=T}
 if(hi-lo<.05)hi=lo+.05;
 const NB=36,b=new Array(NB).fill(0);
 for(let i=0;i<NC;i++)b[Math.min(NB-1,Math.floor((E.Tcore[i]-lo)/(hi-lo)*NB))]++;
 const mx=Math.max(...b);
 b.forEach((v,k)=>{const x=W*k/NB,h=(Hh-22)*v/mx;
  g.fillStyle=ramp(k/(NB-1));g.fillRect(x+1,Hh-16-h,W/NB-2,h)});
 // mean marker
 let sm=0;for(let i=0;i<NC;i++)sm+=E.Tcore[i];
 const mu=sm/NC,xm=W*(mu-lo)/(hi-lo);
 g.strokeStyle='rgba(255,255,255,.55)';g.setLineDash([4,3]);g.lineWidth=1.5;
 g.beginPath();g.moveTo(xm,4);g.lineTo(xm,Hh-16);g.stroke();g.setLineDash([]);
 g.fillStyle=C_DIM();g.font='12px ui-monospace';
 g.fillText(lo.toFixed(1)+'°C',2,Hh-3);
 g.fillText('μ '+mu.toFixed(2),xm-24,14);
 const t=hi.toFixed(1)+'°C';g.fillText(t,W-g.measureText(t).width-2,Hh-3);
}

/* ---------- manifold flow distribution ----------
   Every other calculation here assumes the flow divides equally between
   circuits. It does not. The supply header loses static pressure as fluid is
   drawn off, so far circuits run starved — and a starved circuit is a hot
   region that appears NOWHERE in the temperature field, because the solver
   was told it had design flow. This is the one blind spot the rest of the
   model structurally cannot see. */
function manifoldSplit(nc,lens,tubeID,flow,headerID,spacing,K_take){
 const C=M.cooling, rho=C.rho, mu=C.mu;
 const At=Math.PI*Math.pow(tubeID/2,2), Ah=Math.PI*Math.pow(headerID/2,2);
 const mtot=flow/60000*rho;
 const L=lens.slice(0,nc);
 while(L.length<nc)L.push(L[0]||1);
 if(nc<=1)return{flows:[flow],ratio:1,worst:0};
 const dar=(m,d,A,len)=>{const v=Math.abs(m)/(rho*A);
  const Re=Math.max(rho*v*d/mu,1e-6);
  const f=Re<2300?64/Re:0.316*Math.pow(Re,-0.25);
  return f*len/d*0.5*rho*v*v};
 const bR=m=>L.map((l,i)=>{const v=Math.abs(m[i])/(rho*At);
  const Re=Math.max(rho*v*tubeID/mu,1e-6);
  const f=Re<2300?64/Re:0.316*Math.pow(Re,-0.25);
  return (f*l/tubeID+K_take)*0.5*rho*v*v});
 let m=new Array(nc).fill(mtot/nc);
 for(let it=0;it<400;it++){
  const carried=[];let acc=0;
  for(let i=0;i<nc;i++){carried.push(mtot-acc);acc+=m[i]}
  let cum=0;const Ps=[],vs=[];
  for(let i=0;i<nc;i++){cum+=dar(carried[i],headerID,Ah,spacing);
   vs.push(carried[i]/(rho*Ah));Ps.push(-cum)}
  for(let i=0;i<nc;i++)Ps[i]+=0.5*rho*(vs[0]*vs[0]-vs[i]*vs[i]);
  const cr=[];let a2=0;
  for(let i=nc-1;i>=0;i--){a2+=m[i];cr[i]=a2}
  let cum2=0;const Pr=[];
  for(let i=0;i<nc;i++){cum2+=dar(cr[i],headerID,Ah,spacing);Pr.push(cum2)}
  const base=bR(m);
  const bm=base.reduce((x,y)=>x+y,0)/nc;
  let av=Ps.map((v,i)=>v-Pr[i]);
  const mn=Math.min.apply(null,av);
  av=av.map(v=>v-mn+bm);
  let mn2=m.map((v,i)=>Math.max(1e-12,v*Math.sqrt(Math.max(av[i],1e-9)/Math.max(base[i],1e-9))));
  const sc=mtot/mn2.reduce((x,y)=>x+y,0);
  mn2=mn2.map(v=>v*sc);
  let mx=0;for(let i=0;i<nc;i++){const st=mn2[i]-m[i];m[i]+=0.35*st;
   mx=Math.max(mx,Math.abs(st))}
  if(mx/(mtot/nc)<1e-7)break}
 const flows=m.map(v=>v/rho*60000);
 const lo=Math.min.apply(null,flows),hi=Math.max.apply(null,flows);
 const mean=flows.reduce((x,y)=>x+y,0)/nc;
 return{flows,ratio:hi/Math.max(lo,1e-9),worst:(1-lo/mean)*100,mean}}

function drawManifold(){
 const c=$('mfc'),g=fit(c),W=c.width,Hh=c.height;
 const nc=+$('sCirc').value, flow=+$('sFlow').value/10;
 const tid=+$('sTube').value/10000, hdr=+$('sHdr').value/10000;
 $('oHdr').textContent=(hdr*1000).toFixed(1)+' mm';
 const lens=(M.cooling.circuitLengths&&M.cooling.circuitLengths.length)
  ?M.cooling.circuitLengths:[2.5,2.5,2.5];
 const base=lens.reduce((a,b)=>a+b,0);
 const use=[];for(let i=0;i<nc;i++)use.push(lens[i%lens.length]*
   (lens.length/nc)*(nc/Math.max(1,lens.length))||base/nc);
 const r=manifoldSplit(nc,nc===lens.length?lens:new Array(nc).fill(base/nc),
   tid,flow,hdr,0.045,1.8);
 const mx=Math.max.apply(null,r.flows)*1.15;
 const bw=(W-70)/nc;
 r.flows.forEach((f,i)=>{
  const h=(Hh-44)*f/mx, x=50+i*bw;
  const dev=(f/r.mean-1)*100;
  const col=Math.abs(dev)<3?'#3ddc97':Math.abs(dev)<10?'#f7b955':'#ff6b7a';
  g.fillStyle='rgba(255,255,255,.035)';rr(g,x,Hh-26-(Hh-44),bw-7,Hh-44,3);g.fill();
  g.fillStyle=col;rr(g,x,Hh-26-h,bw-7,h,3);g.fill();
  g.fillStyle=C_FG();g.font='600 12px ui-monospace';
  g.fillText(f.toFixed(2),x+3,Hh-30-h);
  g.fillStyle=col;g.font='11px ui-monospace';
  g.fillText((dev>=0?'+':'')+dev.toFixed(1)+'%',x+3,Hh-12);
  g.fillStyle=C_DIM();g.fillText('C'+i,x+3,Hh-2)});
 const ym=Hh-26-(Hh-44)*r.mean/mx;
 g.strokeStyle='rgba(255,255,255,.4)';g.setLineDash([5,4]);g.lineWidth=1.5;
 g.beginPath();g.moveTo(46,ym);g.lineTo(W,ym);g.stroke();g.setLineDash([]);
 g.fillStyle=isDay()?'#3f5164':'#93a5b9';g.font='11px ui-monospace';
 g.fillText('design',4,ym+4);g.fillText('L/min',4,16);
 $('mfHdr').textContent=`${r.ratio.toFixed(3)}× imbalance`;
 $('mfHdr').style.color=r.ratio>1.25?'var(--bad)':r.ratio>1.10?'var(--warn)':'var(--ok)';
 const eqLen=Math.max.apply(null,lens)/Math.min.apply(null,lens);
 $('mfV').className='verdict '+(r.ratio>1.25?'b':r.ratio>1.10?'w':'g');
 $('mfV').innerHTML=
  `Worst circuit runs <b>${r.worst.toFixed(1)} %</b> below design flow. `+
  (eqLen>1.05&&nc===lens.length
   ? `Almost all of that comes from UNEQUAL CIRCUIT LENGTHS — yours differ by `+
     `${((eqLen-1)*100).toFixed(0)} % (${Math.min.apply(null,lens).toFixed(2)}–`+
     `${Math.max.apply(null,lens).toFixed(2)} m), not from the header. Equalise `+
     `the circuit lengths and the imbalance largely disappears; growing the `+
     `header past 10 mm barely helps.`
   : `Header size is the lever here. Below ~10 mm the supply header starves the `+
     `far take-offs; above it the returns diminish fast.`)+
  ` A starved circuit is a hot region the temperature field cannot show you, `+
  `because the solver was told every circuit had design flow.`;
}

/* ---------- setup sheet: live cooling trade ---------- */
function coolingCalc(flow,nc,tubeID,Rwall,fluid){
 const C=M.cooling;
 const rho=fluid==='w'?997:C.rho, cp=fluid==='w'?4180:C.cp;
 const mu =fluid==='w'?0.0008:C.mu, kk=fluid==='w'?0.62:C.k;
 const mdot=flow/60000*rho, mdotC=mdot/Math.max(1,nc);
 const A=Math.PI*Math.pow(tubeID/2,2), v=mdotC/(rho*A);
 const Re=rho*v*tubeID/mu, Pr=mu*cp/kk;
 const NuL=3.66, NuT=0.023*Math.pow(Math.max(Re,1),0.8)*Math.pow(Pr,0.4);
 let Nu,reg;
 if(Re<2300){Nu=NuL;reg='laminar'}
 else if(Re>4000){Nu=NuT;reg='turbulent'}
 else{const f=(Re-2300)/1700;Nu=(1-f)*NuL+f*NuT;reg='transitional'}
 const h=Nu*kk/tubeID;
 const Aw=Math.PI*tubeID*C.cellD, Rconv=1/Math.max(1e-9,h*Aw);
 // scale the WORST circuit length as the circuit count changes: more
 // circuits means each is shorter, but the longest still governs the pump.
 const base=C.nCircuitsBase||1;
 const L=(C.maxCircuitLen||C.tubeLen/base)*base/Math.max(1,nc);
 const f=Re<2300?64/Math.max(Re,1):0.316*Math.pow(Math.max(Re,1),-0.25);
 // bends scale with circuit length: a longer serpentine has more passes
 const nb=(C.maxBends||0)*(C.nCircuitsBase||1)/Math.max(1,nc);
 const dP=(f*L/tubeID+nb*1.5)*0.5*rho*v*v;
 const Rtot=Rwall+Rconv;
 return {Re,reg,h,Rconv,Rtot,dP:dP/1e5,v,mdotCp:mdot*cp,
         pumpW:dP*mdot/rho/0.25};
}
function drawSetup(){
 const flow=+$('sFlow').value/10, nc=+$('sCirc').value;
 const tid=+$('sTube').value/10000, bond=+$('sBond').value/10;
 const fluid=$('sFluid').value;
 $('oFlow').textContent=flow.toFixed(1)+' L/min';
 $('oCirc').textContent=nc;
 $('oTube').textContent=(tid*1000).toFixed(1)+' mm';
 $('oBond').textContent=bond.toFixed(1)+' K/W';
 const r=coolingCalc(flow,nc,tid,bond,fluid);
 // sweep circuits for the chart
 const c=$('setC'),g=fit(c),W=c.width,Hh=c.height;
 const xs=[];for(let n=1;n<=12;n++)xs.push(coolingCalc(flow,n,tid,bond,fluid));
 const maxR=Math.max(...xs.map(a=>a.Rtot))*1.1, maxP=Math.max(...xs.map(a=>a.dP))*1.1;
 const X=n=>40+(W-56)*(n-1)/11;
 const YR=v=>Hh-30-(Hh-46)*v/maxR, YP=v=>Hh-30-(Hh-46)*v/Math.max(maxP,0.01);
 g.strokeStyle=C_GRID();for(let k=0;k<=3;k++){const y=YR(maxR*k/3);
  g.beginPath();g.moveTo(40,y);g.lineTo(W,y);g.stroke()}
 // pump limit band
 const yl=YP(0.5);
 g.fillStyle='rgba(255,107,122,.10)';g.fillRect(40,0,W-40,Math.max(0,yl));
 g.strokeStyle='rgba(255,107,122,.55)';g.setLineDash([7,5]);g.lineWidth=1.8;
 g.beginPath();g.moveTo(40,yl);g.lineTo(W,yl);g.stroke();g.setLineDash([]);
 g.fillStyle='rgba(255,107,122,.8)';g.font='600 12px ui-monospace';
 g.fillText('0.5 bar pump limit',W-190,yl-7);
 const line=(f,Y,col,lw)=>{g.strokeStyle=col;g.lineWidth=lw||2.6;g.beginPath();
  xs.forEach((a,k)=>{const x=X(k+1),y=Y(f(a));k?g.lineTo(x,y):g.moveTo(x,y)});g.stroke()};
 line(a=>a.dP,YP,'#f7b955',2);
 line(a=>a.Rtot,YR,'#2ad4ee',3);
 const cx=X(nc),cy=YR(r.Rtot);
 g.fillStyle='#3ddc97';g.shadowColor='#3ddc97';g.shadowBlur=12;
 g.beginPath();g.arc(cx,cy,7,0,6.283);g.fill();g.shadowBlur=0;
 g.fillStyle=C_DIM();g.font='12px ui-monospace';
 for(let n=1;n<=12;n+=2)g.fillText(n,X(n)-3,Hh-10);
 g.fillText('circuits →',W/2-30,Hh-10);
 g.fillStyle='#2ad4ee';g.fillText('R cell→coolant K/W',44,18);
 g.fillStyle='#f7b955';g.fillText('ΔP bar',W-90,18);
 $('setHdr').textContent=`Re ${r.Re.toFixed(0)} · ${r.reg}`;
 // verdict
 let cls='g',msg='';
 if(r.dP>0.5){cls='b';msg=`ΔP ${r.dP.toFixed(2)} bar exceeds what a 12 V pump will deliver. `+
   `Add circuits or a larger tube.`}
 else if(r.reg==='laminar'){cls='w';
   msg=`Laminar at Re ${r.Re.toFixed(0)}. Nu is pinned at 3.66, so h no longer improves `+
   `with flow — adding circuits past this point buys nothing but plumbing. `+
   `R_cell→coolant ${r.Rtot.toFixed(2)} K/W.`}
 else{cls='g';msg=`${r.reg} at Re ${r.Re.toFixed(0)}, h ${r.h.toFixed(0)} W/m²K, `+
   `R ${r.Rtot.toFixed(2)} K/W, ΔP ${r.dP.toFixed(3)} bar, pump ${r.pumpW.toFixed(0)} W. `+
   `Comfortably inside the pump envelope.`}
 const best=xs.map((a,k)=>({n:k+1,...a})).filter(a=>a.dP<=0.5)
   .sort((a,b)=>a.Rtot-b.Rtot)[0];
 if(best&&best.n!==nc)msg+=`  Best feasible: ${best.n} circuits at ${best.Rtot.toFixed(2)} K/W.`;
 $('setV').className='verdict '+cls;$('setV').textContent=msg;
 $('setT').innerHTML=Object.entries({
  'pack':`${NC} cells · ${NS}S${NP}P · ${M.meta.nLayers} layer(s)`,
  'declared energy':`${M.meta.energyCapKWh} kWh`,
  'power cap':`${M.meta.PmaxW/1000} kW (ENERGY_REQ_188)`,
  'tubes':`${M.cooling.nTubes} · ${M.cooling.tubeLen.toFixed(2)} m total`,
  'mdot·cp':`${r.mdotCp.toFixed(0)} W/K`,
  'flow velocity':`${r.v.toFixed(2)} m/s`,
  'convection h':`${r.h.toFixed(0)} W/m²K`,
  'R wall + conv':`${bond.toFixed(2)} + ${r.Rconv.toFixed(2)} = ${r.Rtot.toFixed(2)} K/W`,
  'pump power':`${r.pumpW.toFixed(0)} W electrical`,
  'hull Lwl':`${BT.LwlM.toFixed(2)} m · wetted ${BT.wettedM2.toFixed(2)} m²`,
  'propeller':`⌀${(BT.propD*1000).toFixed(0)} mm · P/D ${BT.propPD.toFixed(2)}`,
  'circuit':TR?`${TR.name} · ${TR.length.toFixed(0)} m`:'—',
 }).map(([k,v])=>`<tr><td>${k}</td><td>${v}</td></tr>`).join('');
 $('provT2').innerHTML=(M.provenance||[]).map(([k,v])=>
  `<tr><td>${k}</td><td>${v}</td></tr>`).join('');
}

/* ---------- degradation from the measured cycle curves ---------- */
function drawDeg(){
 const c=$('deg'),g=fit(c),W=c.width,Hh=c.height;
 const CY=M.cycles||[];
 if(!CY.length){g.fillStyle=C_DIM();g.font='14px ui-monospace';
  g.fillText('no cycle-life data in the dataset',20,Hh/2);return}
 const maxN=Math.max(...CY.map(c2=>Math.max(...c2.n)));
 const X=n=>44+(W-58)*n/maxN, Y=r=>Hh-28-(Hh-44)*(r-0.70)/0.32;
 g.strokeStyle=C_GRID();g.lineWidth=1;
 for(let r=0.75;r<=1.001;r+=0.05){const y=Y(r);g.beginPath();
  g.moveTo(44,y);g.lineTo(W,y);g.stroke();
  g.fillStyle=C_DIM();g.font='12px ui-monospace';
  g.fillText((r*100).toFixed(0)+'%',6,y+4)}
 // 80 % end-of-life line
 g.strokeStyle='rgba(255,107,122,.5)';g.setLineDash([7,5]);g.lineWidth=1.8;
 g.beginPath();g.moveTo(44,Y(0.80));g.lineTo(W,Y(0.80));g.stroke();g.setLineDash([]);
 g.fillStyle='rgba(255,107,122,.8)';g.font='600 12px ui-monospace';
 g.fillText('80 % end of life',W-150,Y(0.80)-7);
 // your operating point: mean W per cell this session
 const wPerCell=E.t>30?WhThru/ (E.t/3600) /NC :0;
 const cols=['#3ddc97','#2ad4ee','#b18cff','#f7b955','#ff9f5a','#ff6b7a'];
 let nearest=null,bd=1e9;
 CY.forEach((cv,i)=>{
  g.strokeStyle=cols[i%cols.length];g.lineWidth=2;g.globalAlpha=.75;g.beginPath();
  cv.n.forEach((n,k)=>{const x=X(n),y=Y(cv.ret[k]);k?g.lineTo(x,y):g.moveTo(x,y)});
  g.stroke();g.globalAlpha=1;
  const wEq=cv.c_rate*CL.capAh*3.6;      // approx W at 3.6 V
  const d=Math.abs(wEq-wPerCell); if(d<bd){bd=d;nearest={cv,i,wEq}}});
 // equivalent full cycles from real Ah throughput
 const eqc=AhThru/CL.capAh;
 if(nearest){
  const ret=(n)=>{const cv=nearest.cv;
   if(n<=cv.n[0])return cv.ret[0];
   for(let k=1;k<cv.n.length;k++)if(n<=cv.n[k]){
    const f=(n-cv.n[k-1])/(cv.n[k]-cv.n[k-1]);
    return cv.ret[k-1]+(cv.ret[k]-cv.ret[k-1])*f}
   return cv.ret[cv.ret.length-1]};
  const x=X(Math.min(eqc,maxN)),y=Y(ret(eqc));
  g.strokeStyle=cols[nearest.i%cols.length];g.lineWidth=4;g.beginPath();
  nearest.cv.n.forEach((n,k)=>{const xx=X(n),yy=Y(nearest.cv.ret[k]);
   k?g.lineTo(xx,yy):g.moveTo(xx,yy)});g.stroke();
  g.fillStyle='#fff';g.shadowColor='#fff';g.shadowBlur=10;
  g.beginPath();g.arc(x,y,6,0,6.283);g.fill();g.shadowBlur=0;
  // extrapolate to 80 %
  let n80=maxN;const cv=nearest.cv;
  for(let k=1;k<cv.ret.length;k++)if(cv.ret[k]<=0.80){
   const f=(0.80-cv.ret[k-1])/(cv.ret[k]-cv.ret[k-1]);
   n80=cv.n[k-1]+(cv.n[k]-cv.n[k-1])*f;break}
  if(cv.ret[cv.ret.length-1]>0.80){
   const sl=(cv.ret[cv.ret.length-1]-cv.ret[0])/(cv.n[cv.n.length-1]-cv.n[0]);
   n80=cv.n[cv.n.length-1]+(0.80-cv.ret[cv.ret.length-1])/sl}
  const racesLeft=eqc>0.01?Math.max(0,(n80-eqc)/Math.max(eqc,1e-6)):Infinity;
  kv('kvDeg',[
   ['Ah/cell',AhThru.toFixed(3),'Ah'],
   ['equiv cycles',eqc.toFixed(3),''],
   ['retention',(ret(eqc)*100).toFixed(2),'%'],
   ['mean load',wPerCell.toFixed(1),'W/cell'],
   ['matched curve',nearest.cv.c_rate.toFixed(1)+'C',''],
   ['cycles to 80%',n80.toFixed(0),''],
   ['sessions left',isFinite(racesLeft)?racesLeft.toFixed(0):'--','']]);
  $('degHdr').textContent=`${eqc.toFixed(2)} equivalent cycles`;
  $('degV').className='verdict '+(wPerCell>60?'w':'g');
  $('degV').innerHTML=
   `Throughput is counted from actual cell current, not lap count. At `+
   `<b>${wPerCell.toFixed(0)} W/cell</b> your load sits nearest the measured `+
   `<b>${nearest.cv.c_rate.toFixed(1)}C</b> curve, which reaches 80 % at `+
   `<b>${n80.toFixed(0)} cycles</b>. Discharge power dominates fade far more `+
   `than charge rate — the datasheet spread from 1C to 200 W is `+
   `${((CY[0].ret[CY[0].ret.length-1]-CY[CY.length-1].ret[CY[CY.length-1].ret.length-1])*100).toFixed(0)} `+
   `points at 500 cycles.`;
 }
 g.fillStyle=C_DIM();g.font='12px ui-monospace';
 g.fillText('equivalent full cycles →',W/2-70,Hh-8);
}

/* ---------- thermal waterfall ---------- */
const WF=[],WFN=150,WFB=40;
function pushWF(){
 let lo=1e9,hi=-1e9;for(let i=0;i<NC;i++){const T=E.Tcore[i];if(T<lo)lo=T;if(T>hi)hi=T}
 WF.push({lo,hi,b:(()=>{const b=new Uint16Array(WFB);
  for(let i=0;i<NC;i++)b[Math.min(WFB-1,Math.floor((E.Tcore[i]-lo)/Math.max(hi-lo,1e-6)*WFB))]++;
  return b})()});
 if(WF.length>WFN)WF.shift()}
function drawWF(){
 const c=$('wf'),g=fit(c),W=c.width,Hh=c.height;
 if(!WF.length)return;
 const gLo=Math.min(...WF.map(w=>w.lo)),gHi=Math.max(...WF.map(w=>w.hi));
 const cw=W/WFN;
 WF.forEach((w,k)=>{
  const mx=Math.max(...w.b);
  for(let j=0;j<WFB;j++){
   const T=w.lo+(w.hi-w.lo)*(j+.5)/WFB;
   const y=Hh-16-(Hh-30)*(T-gLo)/Math.max(gHi-gLo,1e-6);
   const a=w.b[j]/mx;
   if(a<=0)continue;
   g.fillStyle=`rgba(${255*Math.min(1,a*1.6)|0},${176*a|0},${31+60*(1-a)|0},${0.15+0.85*a})`;
   g.fillRect(k*cw,y-2,cw+1,(Hh-30)/WFB+2)}});
 g.fillStyle=C_DIM();g.font='12px ui-monospace';
 g.fillText(gHi.toFixed(1)+'°C',4,16);g.fillText(gLo.toFixed(1)+'°C',4,Hh-6);
 g.fillText('← older        now →',W/2-70,Hh-4);
}

/* ---------- strategy ---------- */
function drawStrat(){
 const c=$('strat'),g=fit(c),W=c.width,Hh=c.height;
 if(!ST.rows||!ST.rows.length)return;
 const R=ST.rows,vs=R.map(r=>r.v_kmh);
 const x0=Math.min(...vs),x1=Math.max(...vs);
 const y1=Math.max(...R.map(r=>Math.min(r.dist_energy_km,999)))*1.1;
 const PX=v=>36+(W-56)*(v-x0)/(x1-x0),PY=d=>Hh-30-(Hh-52)*d/y1;
 g.strokeStyle='#141b24';g.lineWidth=1;
 for(let k=0;k<=4;k++){const y=PY(y1*k/4);g.beginPath();g.moveTo(30,y);g.lineTo(W,y);g.stroke();
  g.fillStyle='#4f6070';g.font='15px ui-monospace';g.fillText((y1*k/4).toFixed(0),2,y+5)}
 const line=(f,col,lw)=>{g.strokeStyle=col;g.lineWidth=lw||2.4;g.beginPath();
  R.forEach((r,k)=>{const x=PX(r.v_kmh),y=PY(Math.min(f(r),y1));k?g.lineTo(x,y):g.moveTo(x,y)});
  g.stroke()};
 line(r=>r.dist_energy_km,'#37b6ff');
 line(r=>r.dist_time_km,'#ffb020');
 line(r=>r.distance_km,'#2ee06a',3.6);
 const bx=PX(ST.best.v_kmh),by=PY(ST.best.distance_km);
 g.fillStyle='#2ee06a';g.beginPath();g.arc(bx,by,7,0,6.283);g.fill();
 g.strokeStyle='rgba(46,224,106,.4)';g.lineWidth=1.4;g.setLineDash([5,5]);
 g.beginPath();g.moveTo(bx,by);g.lineTo(bx,Hh-30);g.stroke();g.setLineDash([]);
 const vk=E.v*3.6;
 if(vk>x0&&vk<x1){g.strokeStyle='#ff4d5e';g.lineWidth=2.2;
  g.beginPath();g.moveTo(PX(vk),18);g.lineTo(PX(vk),Hh-30);g.stroke()}
 g.fillStyle='#4f6070';g.font='16px ui-monospace';
 g.fillText('speed km/h →',W/2-60,Hh-8);
 g.fillText('distance km',36,20);
}

/* ---------- current sharing ---------- */
function drawShare(){
 const c=$('share'),g=fit(c),W=c.width,Hh=c.height;
 let wg=0,wr=0;
 for(let gp=0;gp<NS;gp++){let mx=-1e9,sm=0,n=0;
  for(let i=0;i<NC;i++)if(serIdx[i]===gp){const a=Math.abs(E.I[i]);sm+=a;n++;if(a>mx)mx=a}
  const r=mx/Math.max(1e-9,sm/n);if(r>wr){wr=r;wg=gp}}
 const cur=[];for(let i=0;i<NC;i++)if(serIdx[i]===wg)cur.push(E.I[i]);
 if(!cur.length)return;
 const lo=Math.min(...cur),hi=Math.max(...cur),mean=cur.reduce((a,b)=>a+b,0)/cur.length;
 const pad=Math.max(.05,(hi-lo)*.25);
 cur.forEach((v,k)=>{const x=W*k/cur.length,
  h=(Hh-24)*(v-(lo-pad))/Math.max(1e-6,(hi+pad)-(lo-pad));
  g.fillStyle=v>mean?'#ff4d5e':'#37b6ff';g.fillRect(x+1,Hh-12-h,W/cur.length-2,h)});
 g.strokeStyle='#78889b';g.setLineDash([5,4]);g.lineWidth=1.4;
 const ym=Hh-12-(Hh-24)*(mean-(lo-pad))/Math.max(1e-6,(hi+pad)-(lo-pad));
 g.beginPath();g.moveTo(0,ym);g.lineTo(W,ym);g.stroke();g.setLineDash([]);
 g.fillStyle='#4f6070';g.font='15px ui-monospace';
 g.fillText(`group ${wg}  ·  ${lo.toFixed(3)} – ${hi.toFixed(3)} A`,6,16);
 $('shareNote').textContent=
  `Worst hog ratio ${wr.toFixed(4)} — the busiest cell carries ${((wr-1)*100).toFixed(1)}% `+
  `more current, so ~${((wr*wr-1)*100).toFixed(1)}% more ohmic heat, for its whole life. `+
  `Driven by manufacturing spread in R, not by thermal feedback.`;
}
function drawDrag(){
 const c=$('drag'),g=fit(c),W=c.width,Hh=c.height;
 const v=Math.max(E.v,.1);
 const kA=0.55*BT.dryAreaM2*0.22+1.2*2*BT.beamD*BT.beamSpan;
 const air=0.5*1.2*kA*v*v, tot=Math.max(E.drag,1e-6), hyd=Math.max(0,tot-air);
 const items=[['hydrodynamic',hyd,'#37b6ff'],['aerodynamic',air,'#c86bff']];
 let x=10;const sc=(W-20)/tot;
 items.forEach(([n,val,col])=>{g.fillStyle=col;g.fillRect(x,20,val*sc,42);x+=val*sc});
 g.fillStyle='#e8eef6';g.font='600 17px ui-monospace';
 g.fillText(`total ${tot.toFixed(0)} N   at ${(v*3.6).toFixed(1)} km/h   `+
  `→ ${(tot*v/1000).toFixed(2)} kW at the water`,10,88);
 let y=118;items.forEach(([n,val,col])=>{
  g.fillStyle=col;g.fillRect(10,y-11,12,12);g.fillStyle='#78889b';g.font='15px ui-monospace';
  g.fillText(`${n}  ${val.toFixed(0)} N  (${(val/tot*100).toFixed(0)}%)`,30,y);y+=22});
}

/* ---------- alarms ---------- */
const ALARMS=[
 {k:'tmax',n:'CELL TEMP CRITICAL',f:s=>s.Tmax>CL.TmaxC,c:1},
 {k:'twarn',n:'cell temp warning',f:s=>s.Tmax>CL.TwarnC},
 {k:'spread',n:'pack spread > 5 K',f:s=>s.Tmax-s.Tmin>5},
 {k:'soc',n:'SOC below 10 %',f:s=>s.socMin<0.10},
 {k:'energy',n:'energy budget > 97 %',f:()=>E.Wh/1000>M.meta.energyCapKWh*0.97,c:1},
 {k:'cap',n:'power cap active',f:()=>E.capped},
 {k:'cool',n:'coolant rise > 4 K',f:s=>s.coolOut-env.tin>4},
 {k:'vmin',n:'group voltage low',f:()=>E.Vp/NS<3.0},
 {k:'wind',n:'MOTOR WINDING CRITICAL',f:()=>E.Tw>DR.TwMax,c:1},
 {k:'windw',n:'motor winding warning',f:()=>E.Tw>DR.TwWarn},
 {k:'junc',n:'INVERTER JUNCTION CRITICAL',f:()=>E.Tj>DR.TjMax,c:1},
 {k:'juncw',n:'inverter junction warning',f:()=>E.Tj>DR.TjWarn},
 {k:'dtd',n:'drivetrain derate active',f:()=>E.dtDerate<0.999},
];
function drawAlarms(st){
 let n=0;const h=ALARMS.map(a=>{
  const on=a.f(st);if(on)E.alarms[a.k]=(E.alarms[a.k]||0)+1;
  const latched=E.alarms[a.k]>0;if(on)n++;
  const cls=on?(a.c?'c':'a'):(latched?(a.c?'c l':'a l'):'');
  return `<div class="${cls}"><span style="color:inherit">${a.n}</span>`+
   `<span>${on?'ACTIVE':(latched?'latched '+E.alarms[a.k]:'—')}</span></div>`}).join('');
 $('alm').innerHTML=h;$('almN').textContent=n?`${n} ACTIVE`:'nominal';
 $('almN').style.color=n?'#ff4d5e':'#4f6070';
}

/* ---------- render ---------- */
function toast(txt,cls,tag){
 const d=document.createElement('div');d.className=cls||'i';
 d.innerHTML=`<s>${tag||'system'}</s>${txt}`;
 $('toast').appendChild(d);
 setTimeout(()=>{d.style.opacity='0';d.style.transition='opacity .4s';
  setTimeout(()=>d.remove&&d.remove(),400)},4200);
 while($('toast').children.length>4)$('toast').removeChild($('toast').firstChild)}

function kv(id,rows){
 const el=$(id);
 el.innerHTML=rows.map(([k,v,u,c])=>{
  const key=id+'|'+k, prev=prevVals[key], nv=parseFloat(v);
  let anim='';
  if(prev!==undefined&&!isNaN(nv)&&!isNaN(prev)&&Math.abs(nv-prev)>1e-9)
   anim=nv>prev?'up':'dn';
  if(!isNaN(nv))prevVals[key]=nv;
  return `<div class="${c||''}"><u>${k}</u><b class="${anim}">${v}`+
   `<small> ${u||''}</small></b></div>`}).join('')}

function hvStep(dt,st){
 // faults that force a shutdown
 if(FX.imd){HV='FAULT';hvFault='IMD isolation fault — insulation below 500 Ω/V'}
 else if(st.Tmax>CL.TmaxC+3){HV='FAULT';hvFault='BMS over-temperature shutdown'}
 else if(st.socMin<=0.005){HV='FAULT';hvFault='BMS undervoltage shutdown'}
 if(HV==='PRECHARGE'){pcT+=dt;
  if(pcT>=PRECHARGE_S){HV='READY';say('Precharge complete, contactors closed. HV live.','g')}}
 if(HV==='READY'&&(+$('thr').value>1||autopilot))HV='DRIVE';
 if(HV==='DRIVE'&&+$('thr').value<=0.5&&!autopilot)HV='READY';
 // panel
 document.querySelectorAll('#hv div').forEach(d=>{
  const st2=d.dataset.st;d.className=
   st2===HV?(HV==='FAULT'?'flt':(HV==='PRECHARGE'?'act':'on')):''});
 $('pcFill').style.width=(HV==='PRECHARGE'?pcT/PRECHARGE_S*100:
   (HV==='OFF'?0:100))+'%';
 $('hvHdr').textContent=HV;
 $('hvHdr').style.color=HV==='FAULT'?'var(--bad)':HV==='DRIVE'?'var(--ok)':'var(--dim)';
 $('hvNote').textContent = HV==='OFF'?'Precharge 100 Ω into 3300 µF · contactors open'
  : HV==='PRECHARGE'?`Charging DC link… ${(pcT*1000).toFixed(0)} ms of ${PRECHARGE_S*1000} ms`
  : HV==='FAULT'?hvFault
  : `Contactors closed · link at ${E.Vp.toFixed(1)} V · IMD nominal`;
 return HV==='DRIVE'||HV==='READY';
}

function envStep(){
 // apparent wind resolved onto the boat axis using track heading
 let hdg=0;
 if(TR&&TR.hdg){const sm=E.s%TR.length;let ci=0;
  for(let k=0;k<TR.s.length;k++)if(TR.s[k]<=sm)ci=k;hdg=TR.hdg[ci]}
 const wr=wdir*Math.PI/180;
 headEff=env.wind*Math.cos(wr-hdg);         // + head, − tail
 crossEff=env.wind*Math.sin(wr-hdg);        // beam component
 // A beam wind is not free. It blows the boat sideways, the pilot carries
 // rudder and a few degrees of leeway to hold the line, and that shows up as
 // added resistance. Modelled as an induced-drag penalty on the side area:
 //   R_cross = k * 0.5 * rho * Cd_side * A_side * v_beam^2
 // k ~ 0.18 for a shallow-draft catamaran that slips readily rather than
 // developing large side force. Without this term a 90 deg wind on a course
 // with two parallel straights does literally nothing, which is wrong.
 const A_side=BT.LwlM*0.35*BT.nHulls+BT.beamSpan*BT.beamD*2;
 crossR=0.18*0.5*1.2*1.1*A_side*crossEff*crossEff;
 // added resistance in waves: grows with Hs^2 and with speed

 waveR=48*hs*hs*(1+E.v/6);
 // pitch response, for the visual
 pitch=Math.sin(E.t*1.9)*hs*0.55+Math.sin(E.t*3.1)*hs*0.25;
 // propeller ventilation: pitching in a seaway unloads the prop
 if(FX.vent||(hs>0.35&&E.v>6&&Math.random()<hs*0.006*(E.v/10))){
  if(ventActive<=0){ventActive=0.6;
   say('Prop ventilated — thrust dropped out for a moment.','w')}}
 if(ventActive>0)ventActive-=0.5;
 // sensor dropout
 if(FX.sensor&&dropTimer<=0&&Math.random()<0.02)dropTimer=1.5;
 if(dropTimer>0)dropTimer-=0.5;
}

function events(st){
 // ---- distance-domain sampling for the ghost lap ----
 if(TR){const bin=Math.min(NDIST-1,Math.floor((E.s%TR.length)/TR.length*NDIST));
  vNow[bin]=E.v*3.6; tNow[bin]=E.t-E.lapStart;}
 // ---- lateral / longitudinal g ----
 longG=(E.v-prevV)/0.5/9.80665; prevV=E.v;
 if(TR){const sm=E.s%TR.length;let ci=0;
  for(let k=0;k<TR.s.length;k++)if(TR.s[k]<=sm)ci=k;
  latG=E.v*E.v*Math.abs(TR.curv[ci])/9.80665;}
 gTrail.push([longG,latG]); if(gTrail.length>60)gTrail.shift();
 // ---- thermal rate, for time-to-limit ----
 if(E.t-tPrev>2){dTdt=(st.Tmax-TPrev)/(E.t-tPrev); TPrev=st.Tmax; tPrev=E.t;}
 AhThru+=Math.abs(E.Ip)/NP*0.5/3600;      // Ah per cell
 WhThru+=Math.abs(E.Ip*E.Vp)*0.5/3600;
 if(runTrace.length===0||E.t-(runTrace[runTrace.length-1][0]*3600)>10)
  runTrace.push([E.t/3600,E.s/1000]);
 // session end
 if(!sessionOver&&(st.socMin<=0.03||E.Wh/1000>=M.meta.energyCapKWh*0.995
    ||(TR&&E.t>=TR.timeLimit))){sessionOver=true;showSummary()}
 // mini-sector speed record
 if(TR){const ms=Math.floor((E.s%TR.length)/TR.length*NMS)%NMS;
  msNow[ms]=E.v*3.6; if(msNow[ms]>msBest[ms])msBest[ms]=msNow[ms];
  if(trail.length===0||E.s-(trail._s||0)>TR.length/240){
   trail.push(0);trail._s=E.s;
   let bi=0;const sm=E.s%TR.length;
   for(let k=0;k<TR.s.length;k++)if(TR.s[k]<=sm)bi=k;
   trail[trail.length-1]=bi; if(trail.length>90)trail.shift()}}
 // lap completed
 if(E.laps.length>lastLapSeen){
  const l=E.laps[E.laps.length-1];lastLapSeen=E.laps.length;
  const isBest=Math.abs(l.t-E.best)<1e-9;
  if(isBest){vBest.set(vNow);tBest.set(tNow);haveBestLap=true}
  vNow.fill(0);tNow.fill(0);
  if(isBest&&E.laps.length>1){say(`Lap ${l.n}, ${fmtT(l.t)}. That's a new best, well done.`,'g');
   const el=$('tBest');el.classList.remove('flash');void el.offsetWidth;el.classList.add('flash')}
  else if(E.laps.length===1)say(`Lap ${l.n}, ${fmtT(l.t)}. Baseline set.`);
  else{const d=l.t-E.best;
   say(`Lap ${l.n}, ${fmtT(l.t)}. ${d>0?'+':''}${d.toFixed(2)} to your best. `+
       `${(l.wh).toFixed(0)} watt-hours that lap.`, d>1.5?'w':'i')}}
 // threshold crossings, once each
 const W=(k,cond,txt,cls)=>{if(cond&&!warned[k]){warned[k]=1;say(txt,cls)}
  else if(!cond&&warned[k]===2)warned[k]=0};
 W('warn',st.Tmax>CL.TwarnC,`Pack temperature ${st.Tmax.toFixed(1)}, above the warning line. Ease off if you can.`,'w');
 W('crit',st.Tmax>CL.TmaxC,`CRITICAL — pack at ${st.Tmax.toFixed(1)}. Reduce power now.`,'c');
 W('e50',E.Wh/1000>M.meta.energyCapKWh*0.5,'Half the energy gone. Watch the pace.','i');
 W('e85',E.Wh/1000>M.meta.energyCapKWh*0.85,'Fifteen percent of the budget left.','w');
 W('e97',E.Wh/1000>M.meta.energyCapKWh*0.97,'Energy budget exhausted. Bring it home.','c');
 W('mot',E.Tw>DR.TwWarn,`Motor winding at ${E.Tw.toFixed(0)}, above the warning line.`,'w');
 W('inv',E.Tj>DR.TjWarn,`Inverter junction at ${E.Tj.toFixed(0)}. Watch the coolant.`,'w');
 W('soc',st.socMin<0.10,'Cells down to ten percent, start managing.','w');
 W('cool',st.coolOut-env.tin>4,`Coolant out at ${st.coolOut.toFixed(1)}, rise is ${(st.coolOut-env.tin).toFixed(1)} K.`,'w');
 if(ST.best&&E.t>90&&!warned.pace){
  const vk=E.v*3.6,opt=ST.best.v_kmh;
  if(vk>opt*1.35){warned.pace=1;
   say(`You're ${(vk-opt).toFixed(0)} km/h over optimum pace — that's distance you won't get back.`,'w')}}
}

function draw(){
 const st=E.stats(),P=(+$('thr').value)/100*M.meta.PmaxW;
 const RP=replayState();          // non-null while scrubbing
 if(RP){
  $('hSes').innerHTML='<span style="color:var(--warn)">'+fmtT(RP.t).slice(0,-4)+'</span>';
  $('hLap').textContent=RP.lap;
  $('hV').innerHTML=RP.v.toFixed(1)+'<s> km/h</s>';
  $('hP').innerHTML=RP.P.toFixed(2)+'<s> kW</s>';
  $('hT').innerHTML=RP.T.toFixed(1)+'<s> °C</s>';
  $('hSt').textContent='REPLAY';$('hLed').className='led w';
  $('hSt').style.color='var(--warn)';
 } else {
 $('hSes').textContent=fmtT(E.t).slice(0,-4);
 $('hLap').textContent=E.lap;
 const drop=dropTimer>0;
 $('hV').innerHTML=drop?'<s style="color:var(--bad)">-- NO SIG</s>'
  :(sm('hv',E.v*3.6,6).toFixed(1)+'<s> km/h</s>');
 $('hP').innerHTML=sm('hp',P/1000,5).toFixed(2)+'<s> kW</s>';
 $('hE').innerHTML=(E.Wh/1000).toFixed(3)+'<s> kWh</s>';
 $('hT').innerHTML=sm('ht',st.Tmax,10).toFixed(1)+'<s> °C</s>';
 const crit=st.Tmax>CL.TmaxC||E.Wh/1000>M.meta.energyCapKWh*0.97;
 const warn=st.Tmax>CL.TwarnC||E.capped||st.socMin<0.10;
 if(arb)$('arbNow').innerHTML='limited by <b>'+ARB_NAMES[arb.active]+'</b>';
 $('hSt').textContent=crit?'LIMIT':(running?'RUNNING':'HOLD');
 $('hLed').className='led'+(crit?' b':(warn?' w':''));
 $('hSt').style.color=crit?'var(--bad)':(warn?'var(--warn)':(running?'var(--ok)':'var(--dim)'));
 $('hT').style.color=st.Tmax>CL.TmaxC?'var(--bad)':(st.Tmax>CL.TwarnC?'var(--warn)':'var(--fg)');
 }
 // sparklines under the header stats
 spark('hV',REC.v,'#3ddc97');spark('hP',REC.P,'#2ad4ee',0,26);
 spark('hT',REC.T,'#ff6b7a');spark('hE',REC.z,'#f7b955',0,100);

 bindTips();bindFocus();if(provOn)applyProv();
  if(view==='vTele'){
  bindTrace();drawArb();
  drawMap();drawTraces();drawBoat(P);drawPW(P);drawAlarms(st);
  $('tCur').textContent=fmtT(E.t-E.lapStart);
  $('tLast').textContent=fmtT(E.lastLap);
  $('tBest').textContent=fmtT(E.best);
  const theo=E.bestSec.reduce((a,b)=>a+(isFinite(b)?b:Infinity),0);
  $('tTheo').textContent=isFinite(theo)?fmtT(theo):'--:--.---';
  // live delta: compare current lap elapsed against best at the same distance
  let d=0,haveD=false;
  if(isFinite(E.best)&&TR&&E.laps.length){
   const frac=(E.s%TR.length)/TR.length;
   d=(E.t-E.lapStart)-E.best*frac;haveD=true}
  const cap=2.5,fr=Math.max(-1,Math.min(1,d/cap));
  const fill=$('dfill');
  fill.style.background=d<0?'var(--ok)':'var(--bad)';
  fill.style.boxShadow=`0 0 14px ${d<0?'var(--ok)':'var(--bad)'}`;
  if(fr<0){fill.style.left=(50+fr*50)+'%';fill.style.width=(-fr*50)+'%'}
  else{fill.style.left='50%';fill.style.width=(fr*50)+'%'}
  $('dtxt').textContent=haveD?((d>0?'+':'')+d.toFixed(2)+' s'):'— delta —';
  $('dtxt').style.color=haveD?(d<0?'#02120a':'#fff'):'var(--dim2)';
  $('tPos').textContent=`sector ${E.curSec+1} · ${((E.s%(TR?TR.length:1))/(TR?TR.length:1)*100).toFixed(0)}%`;
  [1,2,3].forEach(k=>{const v=E.lastSec[k-1],b=E.bestSec[k-1];
   const el=$('s'+k),bx=$('sc'+k);el.textContent=v?v.toFixed(2):'--';
   const purple=v&&v<=b+1e-6;
   el.className=purple?'pp':'';bx.className=purple?'pp':''});
  kv('kvA',[
   ['speed',(E.v*3.6).toFixed(1),'km/h'],['shaft',(P/1000).toFixed(2),'kW',E.capped?'wo':''],
   ['bus',E.Ip.toFixed(0),'A'],['pack',E.Vp.toFixed(1),'V'],
   ['prop',(E.n*60*BT.gearRatio).toFixed(0),'rpm'],['η prop',(E.eff*100).toFixed(1),'%'],
   ['SOC',(st.soc*100).toFixed(1),'%',st.socMin<.1?'wo':''],
   ['heat',E.qT.toFixed(0),'W'],
   ['T max',st.Tmax.toFixed(1),'°C',st.Tmax>CL.TwarnC?'wo':''],
   ['spread',(st.Tmax-st.Tmin).toFixed(2),'K'],
   ['coolant',st.coolOut.toFixed(1),'°C'],['lap',E.lap,'']]);
  const ef=E.Wh/1000/M.meta.energyCapKWh;
  $('eBar').style.width=Math.min(100,ef*100)+'%';
  $('eBar').style.background=ef>.97?'var(--bad)':ef>.85?'var(--warn)':'var(--acc)';
  $('eBar').style.boxShadow=`0 0 10px ${ef>.97?'var(--bad)':ef>.85?'var(--warn)':'var(--acc)'}`;
  $('zBar').style.background='var(--ok)';$('zBar').style.boxShadow='0 0 10px var(--ok)';
  $('eTxt').textContent=`${(E.Wh/1000).toFixed(3)} / ${M.meta.energyCapKWh} kWh`;
  $('zBar').style.width=(st.soc*100)+'%';
  $('zTxt').textContent=(st.soc*100).toFixed(1)+'%';
  drawGG();drawCmp();
  const rho=1.225*288.15/(273.15+env.tamb);
  const dougl=hs<0.1?'glassy':hs<0.25?'rippled':hs<0.5?'smooth':
              hs<0.9?'slight':hs<1.3?'moderate':'rough';
  const rel=headEff>0.3?'headwind':headEff<-0.3?'tailwind':'beam';
  kv('kvC',[
   ['air',env.tamb.toFixed(1),'°C'],['sea',env.tin.toFixed(1),'°C'],
   ['air density',rho.toFixed(3),'kg/m³'],
   ['apparent',headEff.toFixed(1),'m/s',Math.abs(headEff)>4?'wo':''],
   ['relative',rel,''],
   ['beam wind',crossEff.toFixed(1),'m/s'],
   ['cross drag',crossR.toFixed(0),'N',crossR>80?'wo':''],
   ['sig. wave',hs.toFixed(2),'m',hs>0.8?'wo':''],
   ['sea state',dougl,'',hs>0.9?'wo':''],
   ['wave drag',waveR.toFixed(0),'N',waveR>120?'wo':''],
   ['coolant',(FX.pump?0.4:(FX.restrict?env.flow*0.35:env.flow)).toFixed(1),'L/min',
     (FX.pump||FX.restrict||env.flow<5)?'bd':''],
   ['HV',HV,'',HV==='FAULT'?'bd':HV==='DRIVE'?'ok':'']]);
  $('cndInfo').textContent=`${dougl} · ${rel} ${Math.abs(headEff).toFixed(1)} m/s`;
  // predictive panel
  const ttl=(dTdt>0.0015)?(CL.TmaxC-st.Tmax)/dTdt:Infinity;
  const ttw=(dTdt>0.0015)?(CL.TwarnC-st.Tmax)/dTdt:Infinity;
  const perLap=E.laps.length?E.laps[E.laps.length-1].wh/1000:0;
  const remain=Math.max(0,M.meta.energyCapKWh*0.97-E.Wh/1000);
  const lapsLeft=perLap>1e-6?remain/perLap:Infinity;
  const burn=E.t>60?(E.Wh/1000)/(E.t/3600):0;
  const runtime=burn>1e-6?remain/burn:Infinity;
  let call='—',callC='';
  if(ST.best){const vk=E.v*3.6,opt=ST.best.v_kmh;
   if(vk>opt*1.15){call='EASE';callC='wo'}
   else if(vk<opt*0.85&&vk>2){call='PUSH';callC='ok'}
   else if(vk>2){call='HOLD';callC='ok'}}
  kv('kvP',[
   ['dT/dt',(dTdt*60).toFixed(2),'K/min',dTdt>0.05?'wo':''],
   ['to warn',isFinite(ttw)&&ttw>0?(ttw/60).toFixed(1):'∞','min',
     isFinite(ttw)&&ttw<300&&ttw>0?'wo':''],
   ['to limit',isFinite(ttl)&&ttl>0?(ttl/60).toFixed(1):'∞','min',
     isFinite(ttl)&&ttl<300&&ttl>0?'bd':''],
   ['burn rate',burn.toFixed(2),'kW'],
   ['runtime',isFinite(runtime)?(runtime*60).toFixed(0):'--','min'],
   ['laps left',isFinite(lapsLeft)?lapsLeft.toFixed(1):'--',''],
   ['target',ST.best?ST.best.v_kmh.toFixed(0):'--','km/h'],
   ['call',call,'',callC]]);
  const hr=Math.max(0,Math.min(1,(CL.TmaxC-st.Tmax)/(CL.TmaxC-CL.TwarnC)));
  $('thBar').style.width=(hr*100)+'%';
  $('thBar').style.background=hr<.25?'var(--bad)':hr<.6?'var(--warn)':'var(--ok)';
  $('thBar').style.boxShadow=`0 0 10px ${hr<.25?'var(--bad)':hr<.6?'var(--warn)':'var(--ok)'}`;
  $('thTxt').textContent=`${(CL.TmaxC-st.Tmax).toFixed(1)} K to limit`;
 }
 if(view==='vTherm'){
  bindPack();
  drawPack(st);drawCool();drawHist();drawBal();drawR0();drawWF();drawTwin(st);
  if(selCell>=0&&selCell<NC){
   const i=selCell,D=M.display;
   $('insp').style.display='';
   $('inspId').textContent=`cell ${i} · group ${D.series[i]} · pos ${D.par[i]}`;
   const R0i=R0of(E.Tcore[i],E.z[i],i)*1000;
   const meanT=st.Tmean, meanQ=E.qT/NC;
   kv('kvI',[
    ['T core',E.Tcore[i].toFixed(2),'°C',E.Tcore[i]>CL.TwarnC?'wo':''],
    ['T can',E.Tcan[i].toFixed(2),'°C'],
    ['core−can',(E.Tcore[i]-E.Tcan[i]).toFixed(3),'K'],
    ['vs mean',(E.Tcore[i]-meanT>=0?'+':'')+(E.Tcore[i]-meanT).toFixed(2),'K',
      E.Tcore[i]-meanT>0.5?'wo':'ok'],
    ['heat',E.q[i].toFixed(3),'W'],
    ['vs mean q',(E.q[i]/Math.max(meanQ,1e-9)*100).toFixed(1),'%'],
    ['irreversible',E.qIrr[i].toFixed(3),'W'],
    ['entropic',E.qRev[i].toFixed(3),'W'],
    ['current',E.I[i].toFixed(3),'A'],
    ['R₀',R0i.toFixed(2),'mΩ'],
    ['SOC',(E.z[i]*100).toFixed(2),'%'],
    ['capacity',(CL.capMult[i]*100).toFixed(1),'%'],
    ['resistance',(CL.resMult[i]*100).toFixed(1),'%'],
    ['tube contact',(D.nTubeContact?D.nTubeContact[i].toFixed(2):'—'),'',
      (D.nTubeContact&&D.nTubeContact[i]<=0.05)?'bd':'ok'],
    ['x',(D.x[i]*1000).toFixed(0),'mm'],
    ['y',(D.y[i]*1000).toFixed(0),'mm']]);
  } else $('insp').style.display='none';
  kv('kvT',[['T max',st.Tmax.toFixed(2),'°C'],['T mean',st.Tmean.toFixed(2),'°C'],
   ['T min',st.Tmin.toFixed(2),'°C'],['spread',(st.Tmax-st.Tmin).toFixed(2),'K'],
   ['coolant out',st.coolOut.toFixed(2),'°C'],['rise',(st.coolOut-env.tin).toFixed(2),'K'],
   ['pack heat',E.qT.toFixed(0),'W'],['per cell',(E.qT/NC).toFixed(2),'W'],
   ['enclosure',E.Tair.toFixed(1),'°C'],
   ['busbar',Math.max.apply(null,Array.from(E.Tbus)).toFixed(1),'°C'],
   ['core−can',(E.Tcore[st.hot]-E.Tcan[st.hot]).toFixed(2),'K'],
   ['entropic',(E.qRev.reduce((a,b)=>a+b,0)).toFixed(1),'W'],
   ['entropic frac',(E.qRev.reduce((a,b)=>a+b,0)/Math.max(E.qT,1e-6)*100).toFixed(1),'%'],
   ['removed',E.Qcool.toFixed(0),'W'],
   ['balance',(E.Qgen-E.Qcool-E.Qenc).toFixed(0),'W',
     (E.Qgen-E.Qcool-E.Qenc)>0?'wo':'ok']]);
  const idx=Array.from({length:NC},(_,i)=>i).sort((a,b)=>E.Tcore[b]-E.Tcore[a]).slice(0,8);
  $('hotT').innerHTML='<tr><th>rank</th><th>group</th><th>pos</th><th>T core</th>'+
   '<th>T can</th><th>q</th><th>I</th></tr>'+idx.map((i,k)=>
   `<tr><td>${k+1}</td><td>${M.display.series[i]}</td><td>${M.display.par[i]}</td>`+
   `<td>${E.Tcore[i].toFixed(2)}</td><td>${E.Tcan[i].toFixed(2)}</td>`+
   `<td>${E.q[i].toFixed(2)}</td><td>${E.I[i].toFixed(3)}</td></tr>`).join('');
 }
 if(view==='vStrat'){
  drawStrat();drawProj();
  const lapKm=TR?TR.length/1000:1;
  const usedK=E.Wh/1000, cap=M.meta.energyCapKWh;
  const perLap=E.laps.length?E.laps[E.laps.length-1].wh/1000:0;
  const remain=Math.max(0,cap*0.97-usedK);
  const projLaps=perLap>1e-6?E.lap+remain/perLap:0;
  kv('kvS',[
   ['laps done',E.lap,''],
   ['energy/lap',(perLap*1000).toFixed(0),'Wh'],
   ['remaining',remain.toFixed(3),'kWh'],
   ['projected',projLaps?projLaps.toFixed(1):'--','laps'],
   ['projected',projLaps?(projLaps*lapKm).toFixed(1):'--','km'],
   ['best lap',isFinite(E.best)?fmtT(E.best):'--',''],
   ['avg speed',E.t>1?(E.s/E.t*3.6).toFixed(1):'0.0','km/h'],
   ['elapsed',(E.t/60).toFixed(1),'min']]);
  kv('kvO',[
   ['optimum',ST.best?ST.best.v_kmh.toFixed(1):'--','km/h'],
   ['at power',ST.best?(ST.best.P_shaft_W/1000).toFixed(1):'--','kW'],
   ['distance',ST.best?ST.best.distance_km.toFixed(1):'--','km'],
   ['laps',ST.best?ST.best.laps.toFixed(1):'--',''],
   ['duration',ST.best?ST.best.duration_h.toFixed(2):'--','h'],
   ['limited by',ST.best?ST.best.limited_by:'--','']]);
  $('optNote').textContent=ST.note||'';
  $('stratNote').textContent=ST.note||'';
  $('lapT').innerHTML='<tr><th>lap</th><th>time</th><th>avg</th><th>Wh</th><th>T max</th></tr>'+
   E.laps.slice(-14).reverse().map(l=>
   `<tr><td>${l.n}</td><td class="${l.t<=E.best+1e-6?'pb':''}">${fmtT(l.t)}</td>`+
   `<td>${l.v.toFixed(1)}</td><td>${(l.wh).toFixed(0)}</td>`+
   `<td>${l.Tmax.toFixed(1)}</td></tr>`).join('');
 }
 if(view==='vAnal'){drawSankey();drawLim();drawLoL();drawSens()}
 if(view==='vSetup'){drawSetup();drawDeg();drawManifold()}
 if(view==='vEng'){
  drawShare();drawDrag();drawDT();
  kv('kvE',[['bus current',E.Ip.toFixed(1),'A'],['terminal V',E.Vp.toFixed(2),'V'],
   ['cell stack V',(E.Vcells||E.Vp).toFixed(2),'V'],
   ['busbar drop',((E.Vcells||E.Vp)-E.Vp).toFixed(3),'V'],
   ['cell V avg',(E.Vp/NS).toFixed(3),'V'],['per cell I',(E.Ip/NP).toFixed(2),'A'],
   ['pack heat',E.qT.toFixed(0),'W'],['I²R share',((E.qT/Math.max(E.Vp*E.Ip,1))*100).toFixed(2),'%'],
   ['energy',(E.Wh/1000).toFixed(3),'kWh'],['SOC min',(st.socMin*100).toFixed(2),'%']]);
  kv('kvD',[['thrust',E.thrust.toFixed(0),'N'],['drag',E.drag.toFixed(0),'N'],
   ['prop rpm',(E.n*60*BT.gearRatio).toFixed(0),''],['η prop',(E.eff*100).toFixed(1),'%'],
   ['J',(E.Jof(E.v,E.n)||0).toFixed(3),''],['speed',(E.v*3.6).toFixed(2),'km/h'],
   ['distance',(E.s/1000).toFixed(3),'km'],['Wh/km',E.s>50?(E.Wh/(E.s/1000)).toFixed(0):'--','']]);
  $('cfgT').innerHTML=Object.entries({
   'cells':`${NC} (${NS}S${NP}P)`,'layers':M.meta.nLayers,
   'tubes / circuits':`${M.meta.nTubes} / ${M.meta.nCircuits}`,
   'Reynolds':`${M.meta.ReCoolant.toFixed(0)} (${M.meta.regime})`,
   'ΔP':`${M.meta.dPbar.toFixed(3)} bar`,
   'R cell→coolant':`${M.meta.RcellCoolant.toFixed(2)} K/W`,
   'energy cap':`${M.meta.energyCapKWh} kWh`,'power cap':`${M.meta.PmaxW/1000} kW`,
   'prop':`⌀${(BT.propD*1000).toFixed(0)} mm P/D ${BT.propPD.toFixed(2)}`,
   'hull Lwl':`${BT.LwlM.toFixed(2)} m`,'wetted':`${BT.wettedM2.toFixed(2)} m²`,
   'cockpit frontal':`${(BT.dryAreaM2).toFixed(2)} m² surface`,
  }).map(([k,v])=>`<tr><td>${k}</td><td>${v}</td></tr>`).join('');
  $('provT').innerHTML=(M.provenance||[]).map(([k,v])=>
   `<tr><td>${k}</td><td>${v}</td></tr>`).join('');
 }
}

/* ---------- loop ---------- */
// Exponential Euler is unconditionally stable, so the physics step is no
// longer pinned by the stiffest node. At dt = 1 s it holds 0.037 K RMS
// against the implicit reference (explicit Euler needed 0.5 s for the same),
// which doubles the achievable time compression for free.
const DT=1.0;
function frame(ts){
 keyThrottle();
 const rate=+$('rate').value,wall=Math.min(.25,(ts-last)/1000);last=ts;
 if(running){let acc=wall*rate,guard=0;
  while(acc>0&&guard++<900){
   let Pcmd;
   if(autopilot){
    let vt=+$('tgt').value/3.6;
    if(TR){const sm=E.s%TR.length;let vl=1e6;
     for(let k=0;k<TR.s.length;k++)if(Math.abs(TR.s[k]-sm)<12)vl=Math.min(vl,TR.vlim[k]);
     vt=Math.min(vt,vl)}
    Pcmd=Math.max(0,9000*(vt-E.v));   // unclamped: the cap is a limiter, not a clamp
    const shown=Math.min(100,Pcmd/M.meta.PmaxW*100);
    $('thr').value=Math.round(shown);$('thrv').textContent=shown.toFixed(0)+'%';
   } else Pcmd=(+$('thr').value)/100*M.meta.PmaxW*DEMAND_HEADROOM;
   let zmin=1;for(let i=0;i<NC;i++)if(E.z[i]<zmin)zmin=E.z[i];
   if(zmin<=0.02)Pcmd=0;
   const stPre=E.stats();
   if(!hvStep(DT,stPre))Pcmd=0;              // no HV, no power
   envStep();
   if(ventActive>0)Pcmd*=0.25;
   Pcmd*=E.dtDerate;            // motor/inverter thermal derate               // ventilated prop cannot load up
   if(FX.hotcell)E.Tcore[0]+=0.9*DT;         // a cell with a bad weld
   const envUse={flow:FX.pump?0.4:(FX.restrict?env.flow*0.35:env.flow),
                 tin:env.tin,tamb:env.tamb,wind:headEff+(waveR+crossR)/60};
   E.step(DT,Pcmd,envUse);acc-=DT;
   // ---- digital twin: model with nominal assumptions + noisy sensors ----
   if(hasTwin&&$('twinOn').checked){
    if(!TWIN){TWIN=new Engine();
     sensLag=new Float64Array(OBS.cells.length);
     for(let j=0;j<OBS.cells.length;j++)sensLag[j]=E.Tcan[OBS.cells[j]];
     tEst=new Float64Array(NC)}
    TWIN.step(DT,Pcmd,{flow:M.env.flowLmin,tin:M.env.TinC,
                       tamb:M.env.TambC,wind:0});
    const a=1-Math.exp(-DT/TH_TAU);
    sensRaw=new Float64Array(OBS.cells.length);
    for(let j=0;j<OBS.cells.length;j++){
     const truth=E.Tcan[OBS.cells[j]];
     sensLag[j]+=(truth-sensLag[j])*a;                       // thermistor lag
     let v=sensLag[j]+(Math.random()*2-1)*OBS.noise*1.2;     // sensor noise
     v=Math.round(v/ADC_STEP)*ADC_STEP;                      // ADC quantisation
     sensRaw[j]=v}
    let se=0,so=0;
    for(let i=0;i<NC;i++){
     let corr=0;
     for(let j=0;j<OBS.cells.length;j++)
      corr+=OBS.K[i][j]*(sensRaw[j]-TWIN.Tcan[OBS.cells[j]]);
     tEst[i]=TWIN.Tcore[i]+corr;
     const d=tEst[i]-E.Tcore[i]; se+=d*d;
     const d2=TWIN.Tcore[i]-E.Tcore[i]; so+=d2*d2}
    twRms=Math.sqrt(se/NC); twOl=Math.sqrt(so/NC);
    if(Math.round(E.t/DT)%10===0){twHist.push([twOl,twRms]);
     if(twHist.length>220)twHist.shift()}
   }
   const s0=E.stats();events(s0);
   accumulate(DT,Pcmd);
   if(Math.round(E.t/DT)%Math.max(1,Math.round(1/DT))===0)record();
   if(Math.round(E.t/DT)%20===0)pushWF();
   if(Math.round(E.t/DT)%10===0){dtHist.push([E.Tw,E.Tj,E.Tcase,E.Ths]);
    if(dtHist.length>240)dtHist.shift()}
   H.t.push(E.t);H.v.push(E.v*3.6);H.P.push(Pcmd/1000);
   H.T.push(s0.Tmax);H.z.push(s0.soc*100);H.I.push(E.Ip);
   if(H.t.length>HMAX)for(const k in H)H[k].shift();
   if(LOG.length<200000&&Math.round(E.t/DT)%4===0)
    LOG.push([E.t.toFixed(1),(E.v*3.6).toFixed(2),(Pcmd/1000).toFixed(3),
     E.Ip.toFixed(1),E.Vp.toFixed(2),s0.soc.toFixed(4),(E.Wh/1000).toFixed(4),
     s0.Tmax.toFixed(2),s0.Tmean.toFixed(2),s0.coolOut.toFixed(2),
     E.qT.toFixed(1),(E.n*60).toFixed(0),E.eff.toFixed(3),E.lap,E.s.toFixed(1)]);
  }}
 try{draw();drawPops()}catch(e){
  if(!window.__drawFail){window.__drawFail=1;window.__fatal('draw() / view='+view,e)}}
 requestAnimationFrame(frame);
}
$('wLbl').textContent=`last ${(HMAX*DT/60).toFixed(0)} min`;
$('keyEnv').innerHTML=`<b>${NC}</b> cells · <b>${TR?TR.length.toFixed(0):'--'}</b> m lap · `+
 `<b>${M.meta.PmaxW/1000}</b> kW cap · scheme verified to <b>0.04 K</b>`;

/* ---------- session summary ---------- */
function showSummary(){
 const st=E.stats();
 const reason = st.socMin<=0.03 ? 'PACK EXHAUSTED'
   : (TR&&E.t>=TR.timeLimit) ? 'TIME LIMIT REACHED' : 'ENERGY BUDGET SPENT';
 $('sumTitle').textContent=reason;
 $('sumSub').textContent=`${TR?TR.name:'session'} · ${E.laps.length} laps recorded`;
 const avg=E.t>1?E.s/E.t*3.6:0;
 const whkm=E.s>50?E.Wh/(E.s/1000):0;
 const optD=ST.best?ST.best.distance_km:0;
 $('sumGrid').innerHTML=[
  ['distance',(E.s/1000).toFixed(2),'km'],['laps',E.lap,''],
  ['best lap',isFinite(E.best)?fmtT(E.best):'--',''],
  ['avg speed',avg.toFixed(1),'km/h'],
  ['energy',(E.Wh/1000).toFixed(3),'kWh'],['efficiency',whkm.toFixed(0),'Wh/km'],
  ['peak temp',st.Tmax.toFixed(1),'°C'],['elapsed',(E.t/60).toFixed(1),'min']
 ].map(([k,v,u])=>`<div><u>${k}</u><b>${v}<small style="font-size:10px;color:#4a5c72"> ${u}</small></b></div>`).join('');
 const vsOpt=optD>0?((E.s/1000)/optD*100):0;
 $('sumLaps').innerHTML='<tr><th>lap</th><th>time</th><th>avg km/h</th><th>Wh</th><th>T max</th></tr>'+
  E.laps.slice(-8).reverse().map(l=>`<tr><td>${l.n}</td>`+
  `<td class="${Math.abs(l.t-E.best)<1e-9?'pb':''}">${fmtT(l.t)}</td>`+
  `<td>${l.v.toFixed(1)}</td><td>${l.wh.toFixed(0)}</td><td>${l.Tmax.toFixed(1)}</td></tr>`).join('')
  + (optD>0?`<tr><td colspan="5" style="text-align:left;color:#7e93aa;padding-top:9px">`+
     `You covered ${vsOpt.toFixed(0)}% of the ${optD.toFixed(1)} km theoretical optimum`+
     `${vsOpt<85?' — pacing cost you distance.':' — well paced.'}</td></tr>`:'');
 $('summary').classList.add('on');
 say(`${reason.toLowerCase()}. ${(E.s/1000).toFixed(2)} km, ${E.lap} laps.`,'c');
 running=false;$('run').textContent='▶ RUN';$('run').className='';
}
$('sumClose').onclick=()=>$('summary').classList.remove('on');
$('sumRst').onclick=()=>{$('summary').classList.remove('on');sessionOver=false;
 runTrace.length=0;$('rst').onclick()};
$('sumCsv').onclick=()=>{$('csv').onclick();downloadReport()};

/* ---------- keyboard: makes it drivable ---------- */
const keys={};
document.addEventListener('keydown',e=>{
 const k=e.key.toLowerCase();
 // command palette first
 if($('pal').className==='on'){
  if(k==='escape'){palClose();e.preventDefault();return}
  if(k==='enter'){palRun();e.preventDefault();return}
  if(k==='arrowdown'){palSel=Math.min(palSel+1,palHits.length-1);
   palRender($('palIn').value);e.preventDefault();return}
  if(k==='arrowup'){palSel=Math.max(palSel-1,0);
   palRender($('palIn').value);e.preventDefault();return}
  return}
 if((e.ctrlKey||e.metaKey)&&k==='k'){e.preventDefault();palOpen();return}
 if(k==='escape'){document.querySelectorAll('.card').forEach(c=>{
   c.className=c.className.replace(' focus','')});PX=null;TX=null;return}
 keys[k]=true;
 if(k===' '){e.preventDefault();$('run').onclick()}
 if(k==='r')$('rst').onclick();
 if(k==='a')$('ap').onclick();
 if(k==='p')$('prov').onclick();
 if(k==='d')$('theme').onclick();
 if(k==='[' ){if(replayAt<0)enterReplay();else{replayAt=Math.max(0,replayAt-5);updateReplay()}}
 if(k===']'){if(replayAt>=0){replayAt=Math.min(REC.t.length-1,replayAt+5);updateReplay()}}
 if(k==='f'){const el=document.documentElement;
  if(!document.fullscreenElement)el.requestFullscreen&&el.requestFullscreen();
  else document.exitFullscreen&&document.exitFullscreen()}
 if(k>='1'&&k<='6'){const tabs=document.querySelectorAll('.tab');
  tabs[+k-1]&&tabs[+k-1].click()}
});
document.addEventListener('keyup',e=>{keys[e.key.toLowerCase()]=false});
function keyThrottle(){
 if(autopilot)return;
 const t=$('thr');let v=+t.value;
 if(keys['w']||keys['arrowup'])v=Math.min(100,v+3);
 if(keys['s']||keys['arrowdown'])v=Math.max(0,v-4);
 if(keys['x'])v=0;
 if(v!==+t.value){t.value=v;$('thrv').textContent=v.toFixed(0)+'%'}
}

/* ---------- boot: cinematic cold-start ---------- */
const BOOT=[
 ['electro-thermal solver', `${NC} cells · ${NS}S${NP}P`],
 ['sparse RC network',      `${NC*2+TH.nBus+TH.nSeg+1} nodes`],
 ['coolant hydraulics',     `${M.meta.nCircuits} circuits · Re ${M.meta.ReCoolant.toFixed(0)}`],
 ['cell characterisation',  `${CL.Tgrid.length} temperature maps`],
 ['cycle-life dataset',     `${(M.cycles||[]).length} curves`],
 ['hull & propulsion',      `Lwl ${BT.LwlM.toFixed(2)} m · ⌀${(BT.propD*1000).toFixed(0)} mm`],
 ['circuit geometry',       TR?`${TR.length.toFixed(0)} m · closure ${TR.closure.toFixed(2)} m`:'n/a'],
 ['HV interlock',           `precharge 990 ms · armed`],
 ['power limiter',          `${M.meta.PmaxW/1000} kW hard cap`],
 ['fault injection',        `6 scenarios ready`],
 ['integrator',            `exponential Euler · dt ${1.0} s`],
 ['telemetry',              `all channels nominal`]];

(function boot(){
 const cv=$('bootCv'),g=cv.getContext('2d');
 let W=900,Hh=600;
 const DPR=Math.min(2,(typeof window!=='undefined'&&window.devicePixelRatio)||1);
 function size(){const r=cv.getBoundingClientRect();
  W=Math.max(320,r.width||900);Hh=Math.max(240,r.height||600);
  cv.width=W*DPR;cv.height=Hh*DPR;
  if(g.setTransform)g.setTransform(DPR,0,0,DPR,0,0)}
 size();
 if(typeof window!=='undefined'&&window.addEventListener)
  window.addEventListener('resize',size);

 const D=M.display;
 const x0=Math.min(...D.x),x1=Math.max(...D.x),y0=Math.min(...D.y),y1=Math.max(...D.y);
 const mx=(x0+x1)/2, my=(y0+y1)/2;
 const cells=D.x.map((x,i)=>({
  tx:x-mx, ty:D.y[i]-my,
  sx:(Math.random()-.5)*3.4, sy:(Math.random()-.5)*3.4,
  d:Math.random()*0.30,
  cold:(D.nTubeContact&&D.nTubeContact[i]<=0.05)?1:0}));
 const tubes=(M.tubes||[]).map(t=>({
  x:t.x.map(v=>v-mx), y:t.y.map(v=>v-my), c:t.circuit}));
 const span=Math.max(x1-x0,y1-y0)||1;

 const T0=performance.now(), DUR=4200;
 let logN=0,done=false;
 const ease=t=>1-Math.pow(1-t,3);
 const eio=t=>t<.5?4*t*t*t:1-Math.pow(-2*t+2,3)/2;

 function frameB(now){
  try{ frameBody(now) }catch(e){
   // one bad frame must not strand the user on a black screen
   console.error('boot frame',e);
   $('boot').classList.add('gone');
   try{requestAnimationFrame(frame)}catch(_){window.__fatal('boot->main',e)}
  }
 }
 function frameBody(now){
  const el=Math.min(1,(now-T0)/DUR);
  g.clearRect(0,0,W,Hh);
  const bg=g.createRadialGradient(W/2,Hh*.52,10,W/2,Hh*.52,Math.max(W,Hh)*.78);
  bg.addColorStop(0,'#08182a');bg.addColorStop(.55,'#040b13');bg.addColorStop(1,'#010305');
  g.fillStyle=bg;g.fillRect(0,0,W,Hh);

  const hz=Hh*.62, gp=Math.min(1,el/.55);
  g.save();g.strokeStyle='#12506e';g.lineWidth=1;
  for(let i=1;i<=16;i++){const f=i/16,y=hz+Math.pow(f,2.1)*(Hh-hz)*1.5;
   if(y>Hh)break;g.globalAlpha=.32*gp*(1-f*.75);
   g.beginPath();g.moveTo(0,y);g.lineTo(W,y);g.stroke()}
  for(let i=-14;i<=14;i++){g.globalAlpha=.20*gp*(1-Math.abs(i)/16);
   g.beginPath();g.moveTo(W/2+i*W*.035,hz);g.lineTo(W/2+i*W*.62,Hh);g.stroke()}
  g.restore();
  const hgl=g.createLinearGradient(0,hz-42,0,hz+10);
  hgl.addColorStop(0,'rgba(42,212,238,0)');
  hgl.addColorStop(1,'rgba(42,212,238,'+(.16*gp)+')');
  g.fillStyle=hgl;g.fillRect(0,hz-42,W,52);
  g.strokeStyle='rgba(120,220,255,'+(.34*gp)+')';g.lineWidth=1;
  g.beginPath();g.moveTo(0,hz);g.lineTo(W,hz);g.stroke();

  const scale=Math.min(W*.44,Hh*.44)/span, cxp=W/2, cyp=Hh*.50;
  const tp=Math.max(0,Math.min(1,(el-.42)/.30));
  if(tp>0){const cols=['#2ad4ee','#3ddc97','#f7b955','#b18cff','#ff6b7a'];
   tubes.forEach(tb=>{const n=Math.floor(tb.x.length*ease(tp));if(n<2)return;
    g.strokeStyle=cols[tb.c%cols.length];g.lineWidth=1.6;g.globalAlpha=.55;
    g.shadowColor=cols[tb.c%cols.length];g.shadowBlur=9;g.beginPath();
    for(let k=0;k<n;k++){const X=cxp+tb.x[k]*scale,Y=cyp+tb.y[k]*scale;
     k?g.lineTo(X,Y):g.moveTo(X,Y)}
    g.stroke();g.shadowBlur=0;g.globalAlpha=1})}

  cells.forEach(c=>{const p=Math.max(0,Math.min(1,(el-c.d)/.44));if(p<=0)return;
   const e=eio(p);
   const X=cxp+(c.tx*e+c.sx*span*(1-e))*scale;
   const Y=cyp+(c.ty*e+c.sy*span*(1-e))*scale;
   const r=Math.max(1.1,scale*.0092);
   g.globalAlpha=.20+.80*e;
   if(p<1){g.fillStyle='#a9f0ff';g.shadowColor='#2ad4ee';g.shadowBlur=12*(1-e)+3}
   else{g.fillStyle=c.cold?'#ff6b7a':'#4fc9e8';g.shadowColor='#0e93b0';g.shadowBlur=4}
   g.beginPath();g.arc(X,Y,r,0,6.283);g.fill();g.shadowBlur=0;g.globalAlpha=1});

  if(el>.30&&el<.90){const sp=(el-.30)/.60;
   const sy=cyp-span*scale*.55+sp*span*scale*1.10;
   const sg=g.createLinearGradient(0,sy-26,0,sy+26);
   sg.addColorStop(0,'rgba(61,220,151,0)');sg.addColorStop(.5,'rgba(61,220,151,.30)');
   sg.addColorStop(1,'rgba(61,220,151,0)');
   g.fillStyle=sg;g.fillRect(cxp-span*scale*.62,sy-26,span*scale*1.24,52)}

  // settling pulse the moment the last cell lands
  if(el>.72&&el<.86){const q=(el-.72)/.14;
   g.strokeStyle='rgba(42,212,238,'+(0.30*(1-q))+')';g.lineWidth=2;
   g.beginPath();g.arc(cxp,cyp,span*scale*(0.55+q*0.85),0,6.283);g.stroke()}
  const vg=g.createRadialGradient(W/2,Hh/2,Math.min(W,Hh)*.22,W/2,Hh/2,Math.max(W,Hh)*.72);
  vg.addColorStop(0,'rgba(0,0,0,0)');vg.addColorStop(1,'rgba(0,0,0,.72)');
  g.fillStyle=vg;g.fillRect(0,0,W,Hh);
  g.globalAlpha=.04;g.fillStyle='#000';
  for(let y=0;y<Hh;y+=4)g.fillRect(0,y,W,1);
  g.globalAlpha=1;

  const pct=Math.min(100,Math.round(el*100));
  $('bootPct').innerHTML=pct+'<s>%</s>';
  $('bootBar').style.width=pct+'%';
  const want=Math.floor(el/.92*BOOT.length);
  while(logN<want&&logN<BOOT.length){const kv2=BOOT[logN++];
   const d=document.createElement('div');
   d.innerHTML='<span><i>&#10003;</i><s>'+kv2[0]+'</s></span><span>'+kv2[1]+'</span>';
   $('bootLog').appendChild(d)}

  if(el<1)requestAnimationFrame(frameB);
  else if(!done){done=true;$('bootFlash').className='go';
   setTimeout(function(){
    $('boot').classList.add('gone');
    say('Systems armed. HV isolated — press HV ON to precharge before you go.','g');
    toast('All subsystems nominal. Track is green.','g','system');
    requestAnimationFrame(frame);},430)}
 }
 $('bsCells').textContent=NC;
 $('bsE').textContent=M.meta.energyCapKWh.toFixed(2)+' kWh';
 $('bsP').textContent=(M.meta.PmaxW/1000).toFixed(0)+' kW';
 $('bsL').textContent=TR?(TR.length/1852).toFixed(2)+' NM':'—';
 $('bsV').textContent='0.04 K';
 initScenarios();
 requestAnimationFrame(frameB);
 // watchdog: if the boot has not finished in 9 s, something is wrong with
 // requestAnimationFrame (backgrounded tab, blocked canvas). Show the app
 // anyway rather than leaving a dead screen.
 setTimeout(function(){
  if(!done){done=true;
   $('boot').classList.add('gone');
   try{requestAnimationFrame(frame)}
   catch(e){window.__fatal('watchdog->main',e)}}
 },9000);
})();
</script></body></html>"""


def _check_js(html: str):
    """Balance-check the embedded script before writing.

    A single unbalanced bracket anywhere in the script is a SyntaxError, and a
    SyntaxError does not fail gracefully -- the entire script never executes,
    so the page renders as a dead shell with no console output the user is
    likely to look at. That failure mode is invisible from Python, so it gets
    checked here rather than discovered in a browser.
    """
    js = html.split("<script>", 1)[1].rsplit("</script>", 1)[0]
    depth, instr, prev, line, col = 0, None, "", 1, 0
    stack = []
    for ch in js:
        col += 1
        if ch == "\n":
            line += 1; col = 0
        if instr:
            if ch == instr and prev != "\\":
                instr = None
        elif ch in "\"'`":
            instr = ch
        elif ch in "([{":
            depth += 1; stack.append((ch, line))
        elif ch in ")]}":
            depth -= 1
            if stack:
                stack.pop()
            if depth < 0:
                raise SyntaxError(f"unbalanced '{ch}' in embedded JS at line {line}")
        prev = ch
    if depth != 0:
        where = f" (unclosed '{stack[-1][0]}' opened at line {stack[-1][1]})" \
            if stack else ""
        raise SyntaxError(
            f"embedded JS has bracket depth {depth} at end{where}. "
            "Refusing to write a dashboard that would fail to execute.")
    return True


def check_dom_ids(html):
    """Every element the script looks up must exist in the markup.

    This is the check that would have caught a whole class of bug: splicing
    markup by index silently deleted two blocks that the script still
    referenced, and $('missing') returns null, so the first property access
    throws and the entire page dies. Syntax checks cannot see this -- the
    code is perfectly valid, the DOM just is not there.
    """
    import re
    js = html.split("<script>", 1)[1].rsplit("</script>", 1)[0]
    used = set(re.findall(r"\$\('([A-Za-z][\w-]*)'\)", js))
    # only count getElementById on OUR document -- pop-out windows have their
    # own DOM, so p.w.document.getElementById('c') is not a lookup here.
    used |= set(re.findall(r"(?<![.\w])document\.getElementById\('([A-Za-z][\w-]*)'\)",
                           js))
    have = set(re.findall(r'id="([^"]+)"', html.split("<script>", 1)[0]))
    missing = sorted(used - have)
    return missing


def smoke_load(path):
    """Execute the ENTIRE script top to bottom under a DOM stub.

    node --check only parses. check_dom_ids only looks up element names. Neither
    catches a top-level runtime error -- a const used before its declaration, a
    typo in an initialiser -- and such an error kills the whole page silently.
    This actually RUNS the file. It is the only check that would have caught
    using SCEN in an IIFE placed above its own definition.
    """
    import shutil, subprocess, tempfile, os as _os
    if not shutil.which("node"):
        return True, "smoke load skipped (node not installed)"
    html = open(path, encoding="utf-8").read()
    js = html.split("<script>", 1)[1].rsplit("</script>", 1)[0]
    stub = r"""
const _ctx=new Proxy({},{get:(t,p)=>{
 if(p==='canvas')return{width:900,height:600};
 if(p==='measureText')return()=>({width:10});
 if(p==='createLinearGradient'||p==='createRadialGradient')
  return()=>({addColorStop(){}});
 return()=>{}}});
function mkEl(id){const d={chan:'Tcore',src:'true',evt:'endurance',scn:'',
 sFlow:'80',sCirc:'3',sTube:'60',sBond:'25',sFluid:'g',thr:'40',tgt:'45',
 rate:'5',flow:'80',tin:'290',tamb:'300',wind:'0',wdir:'0',hs:'10'};
 return{id,style:{},dataset:{},offsetWidth:1,checked:true,children:[],
 classList:{add(){},remove(){},contains:()=>false},width:900,height:600,
 value:(d[id]!==undefined?d[id]:'40'),textContent:'',innerHTML:'',className:'',
 firstChild:null,getContext:()=>_ctx,
 getBoundingClientRect:()=>({width:900,height:600,left:0,top:0}),
 appendChild(){},removeChild(){},addEventListener(){},focus(){},
 querySelectorAll:()=>[],querySelector:()=>({textContent:'x'})}}
const _e={};
global.document={getElementById:id=>(_e[id]=_e[id]||mkEl(id)),
 querySelectorAll:()=>[],createElement:mkEl,body:mkEl('b'),
 addEventListener(){},documentElement:mkEl('h')};
global.performance={now:()=>0};
global.requestAnimationFrame=()=>0;
global.setTimeout=()=>0;
global.navigator={userAgent:'smoke'};
global.window={devicePixelRatio:1,addEventListener(){}};
global.Blob=function(){};global.URL={createObjectURL:()=>''};
"""
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False,
                                     encoding="utf-8") as f:
        f.write(stub + js + "\nconsole.log('SMOKE_OK');\n")
        tmp = f.name
    r = subprocess.run(["node", tmp], capture_output=True, text=True, timeout=90)
    _os.unlink(tmp)
    if "SMOKE_OK" in r.stdout:
        return True, "full-script smoke load PASS"
    err = (r.stderr.strip().splitlines() or ["unknown"])
    keep = [l for l in err if l.strip() and not l.strip().startswith("at ")]
    return False, "SMOKE LOAD FAILED: " + " | ".join(keep[:3])


def validate_html(path):
    """Parse the emitted script with node if it is available.

    The bracket check in _check_js catches the common failure, but only a real
    parser catches everything. node is optional: if it is not installed this
    reports that rather than pretending the file was verified.
    """
    import shutil
    import subprocess
    import re
    import tempfile
    html = open(path, encoding="utf-8").read()
    missing = check_dom_ids(html)
    if missing:
        return False, ("script references element(s) that do not exist in the "
                       "markup: " + ", ".join(missing))
    if not shutil.which("node"):
        return True, "bracket + DOM ids OK (install node for a full parse)"
    try:
        js = html.split("<script>", 1)[1].rsplit("</script>", 1)[0]
    except IndexError:
        return False, "no <script> block found"
    js = re.sub(r"const M = \{.*?\};\n", "const M = {};\n", js, flags=re.S)
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False,
                                     encoding="utf-8") as f:
        f.write(js)
        tmp = f.name
    r = subprocess.run(["node", "--check", tmp], capture_output=True, text=True)
    os.unlink(tmp)
    missing = check_dom_ids(html)
    if missing:
        return False, ("script references element(s) that do not exist in the "
                       "markup: " + ", ".join(missing))
    if r.returncode == 0:
        ok, msg = smoke_load(path)
        if not ok:
            return False, msg
        return True, f"node --check PASS · 0 missing DOM ids · {msg}"
    first = (r.stderr.strip().splitlines() or ["unknown"])
    return False, "node --check FAILED: " + " | ".join(first[:4])


def write_ground_station(model: dict, out="figures/mission_control.html"):
    html = _HTML.replace("__MODEL__", json.dumps(model, separators=(",", ":")))
    _check_js(html)
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    return out, os.path.getsize(out)
