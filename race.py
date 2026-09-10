r"""
volare_thermal.race
===================

Couples the boat to the pack and renders an interactive dashboard.

THE LOOP
--------
    pilot     -> commanded shaft power (capped at 25 kW, REQ_188)
    boat      -> thrust, resistance, dv/dt, new speed and lap position
    pack      -> bus current for that power, per-cell heat, new temperatures
    limiter   -> thermal derate and energy-budget derate fold back into the
                 next power command

That last line is the point.  An uncoupled model lets you ask "what happens
at 20 kW".  A coupled one answers "what actually happens when I ask for
20 kW", which is different once the pack sags, warms, and starts limiting.

OUTPUT
------
`build_dashboard()` writes ONE self-contained HTML file: no server, no
dependencies, opens in any browser.  It embeds every scenario you asked for,
so you can switch between them and scrub through time with the pack heatmap,
the boat state, and the energy budget all synchronised.
"""

from __future__ import annotations

import json
import os
import numpy as np

import pack_thermal as pt
import geometry as gm
import boat as bt
import simulator as sm


# ============================================================================
#  COUPLED RACE
# ============================================================================

def simulate_race(pack_geom, cell, coolant, hull, resistance, propeller,
                  course=None, target_speed_kmh=55.0, duration_s=1200.0,
                  dt=0.5, mass_kg=250.0, P_shaft_max_W=25_000.0,
                  T_init_C=28.0, T_ambient_C=30.0,
                  cap_mult=None, res_mult=None,
                  energy_cap_kWh=9.828, reserve_frac=0.03,
                  thermal_derate=True, energy_derate=True,
                  inverter_eff=0.96, sample_every=4, wind_ms=0.0):
    """Run the coupled boat + pack simulation.  Returns a dict of arrays."""
    course = course or bt.RaceCourse()
    pilot = bt.Pilot(course, target_speed_kmh=target_speed_kmh,
                     P_max_W=P_shaft_max_W)
    dyn = bt.BoatDynamics(hull, resistance, propeller, mass_kg=mass_kg,
                          P_shaft_max_W=P_shaft_max_W)
    pack = sm.PackSimulator(pack_geom, cell, coolant, dt=dt, T_init_C=T_init_C,
                            T_ambient_C=T_ambient_C, cap_mult=cap_mult,
                            res_mult=res_mult, inverter_eff=inverter_eff)

    n = int(duration_s / dt)
    rec = {k: [] for k in ("t", "P_cmd", "P_shaft", "v_kmh", "n_rpm",
                           "prop_eff", "thrust_N", "drag_N", "s_m", "lap",
                           "I_pack", "V_pack", "soc", "energy_kWh",
                           "T_max", "T_mean", "T_min", "q_W", "cool_out",
                           "derate", "leg")}
    frames, s_along = [], 0.0
    stop = "duration reached"

    for k in range(n):
        P_req = pilot.command(dyn.v, s_along)

        derate = 1.0
        if thermal_derate:
            derate = min(derate, pack.thermal_power_limit_W(1.0))
        if energy_derate:
            used = pack.energy_Wh / 1000.0
            left = energy_cap_kWh * (1 - reserve_frac) - used
            if left <= 0:
                stop = f"energy budget exhausted at t={k*dt:.0f} s"
                break
            # taper the last 10 % so it does not fall off a cliff
            derate = min(derate, float(np.clip(
                left / (0.10 * energy_cap_kWh), 0.15, 1.0)))
        P_cmd = P_req * derate

        st = dyn.step(dt, P_cmd, wind_ms)
        pack.step(power_W=st["P_shaft_W"])
        s_along += dyn.v * dt

        if pack.z.min() <= 0.03:
            stop = f"pack SOC exhausted at t={k*dt:.0f} s"
            break
        if pack.T_core_C.max() > cell.T_max_C:
            stop = f"cell temperature limit at t={k*dt:.0f} s"
            break

        if k % sample_every == 0:
            Tc = pack.T_core_C
            rec["t"].append(k * dt)
            rec["P_cmd"].append(P_req)
            rec["P_shaft"].append(st["P_shaft_W"])
            rec["v_kmh"].append(st["v_kmh"])
            rec["n_rpm"].append(st["n_rpm"])
            rec["prop_eff"].append(st["prop_eff"])
            rec["thrust_N"].append(st["thrust_N"])
            rec["drag_N"].append(st["resistance_N"])
            rec["s_m"].append(s_along)
            rec["lap"].append(s_along / course.lap_length_m)
            rec["I_pack"].append(pack.I_pack)
            rec["V_pack"].append(pack.V_pack)
            rec["soc"].append(float(pack.z.mean()))
            rec["energy_kWh"].append(pack.energy_Wh / 1000.0)
            rec["T_max"].append(float(Tc.max()))
            rec["T_mean"].append(float(Tc.mean()))
            rec["T_min"].append(float(Tc.min()))
            rec["q_W"].append(float(pack.q_cell.sum()))
            rec["cool_out"].append(float(pack.T_coolant_C.max())
                                   if pack.net.M else T_ambient_C)
            rec["derate"].append(derate)
            rec["leg"].append(course.leg_name(s_along))
            frames.append(Tc.copy())

    out = {k: (np.array(v) if k != "leg" else v) for k, v in rec.items()}
    out["field"] = np.array(frames)
    out["stop_reason"] = stop
    out["lap_length_m"] = course.lap_length_m
    out["energy_cap_kWh"] = energy_cap_kWh
    return out


# ============================================================================
#  DASHBOARD
# ============================================================================

_HTML = r"""<!DOCTYPE html><html><head><meta charset="utf-8">
<title>Volare — Race Simulator</title><style>
:root{--bg:#0d1117;--panel:#161b22;--line:#30363d;--fg:#e6edf3;--dim:#8b949e;
--acc:#58a6ff;--warn:#d29922;--bad:#f85149;--ok:#3fb950}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);
font:13px/1.5 ui-monospace,"SF Mono",Menlo,Consolas,monospace}
header{padding:12px 18px;border-bottom:1px solid var(--line);
display:flex;gap:18px;align-items:center;flex-wrap:wrap}
h1{font-size:15px;margin:0;font-weight:600;letter-spacing:.3px}
.sub{color:var(--dim);font-size:11px}
select,button{background:var(--panel);color:var(--fg);border:1px solid var(--line);
border-radius:5px;padding:5px 10px;font:inherit;cursor:pointer}
button:hover,select:hover{border-color:var(--acc)}
main{display:grid;grid-template-columns:minmax(340px,1fr) minmax(420px,1.25fr);
gap:12px;padding:12px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:7px;padding:12px}
.card h2{font-size:11px;margin:0 0 9px;color:var(--dim);font-weight:600;
text-transform:uppercase;letter-spacing:.8px}
#packc{width:100%;image-rendering:pixelated;border-radius:4px;background:#000}
.kv{display:grid;grid-template-columns:repeat(auto-fit,minmax(96px,1fr));gap:8px}
.kv div{background:#0d1117;border:1px solid var(--line);border-radius:5px;padding:7px 9px}
.kv b{display:block;font-size:17px;font-weight:600}
.kv span{color:var(--dim);font-size:10px;text-transform:uppercase;letter-spacing:.5px}
.ctl{display:flex;gap:10px;align-items:center;padding:10px 18px;
border-top:1px solid var(--line);border-bottom:1px solid var(--line);
background:var(--panel);position:sticky;top:0;z-index:5;flex-wrap:wrap}
input[type=range]{flex:1;min-width:200px;accent-color:var(--acc)}
canvas.tr{width:100%;height:118px;display:block}
.legend{display:flex;gap:12px;font-size:10px;color:var(--dim);margin-top:6px;flex-wrap:wrap}
.sw{display:inline-block;width:9px;height:9px;border-radius:2px;margin-right:4px;
vertical-align:middle}
.warn{color:var(--warn)}.bad{color:var(--bad)}.ok{color:var(--ok)}
.note{color:var(--dim);font-size:10.5px;margin-top:8px;line-height:1.5}
</style></head><body>
<header>
<h1>VOLARE — Coupled Race Simulator</h1>
<span class="sub" id="cfg"></span>
<span style="flex:1"></span>
<label class="sub">scenario</label><select id="scn"></select>
</header>
<div class="ctl">
<button id="play">▶ play</button>
<input type="range" id="t" min="0" value="0" step="1">
<span class="sub" id="tl" style="min-width:150px"></span>
<label class="sub">speed</label>
<select id="rate"><option value="1">1×</option><option value="4" selected>4×</option>
<option value="10">10×</option><option value="30">30×</option><option value="60">60×</option></select>
</div>
<main>
<div>
 <div class="card"><h2>Pack — cell core temperature</h2>
  <canvas id="packc"></canvas>
  <div class="legend" id="scale"></div>
  <div class="note" id="hot"></div>
 </div>
 <div class="card" style="margin-top:12px"><h2>State</h2><div class="kv" id="kv"></div></div>
</div>
<div>
 <div class="card"><h2>Power — commanded vs delivered (25 kW cap)</h2>
  <canvas class="tr" id="cP"></canvas>
  <div class="legend"><span><i class="sw" style="background:#58a6ff"></i>delivered</span>
  <span><i class="sw" style="background:#8b949e"></i>commanded</span>
  <span><i class="sw" style="background:#f85149"></i>25 kW cap</span></div></div>
 <div class="card" style="margin-top:12px"><h2>Boat speed</h2>
  <canvas class="tr" id="cV"></canvas></div>
 <div class="card" style="margin-top:12px"><h2>Energy used vs REQ_7 cap</h2>
  <canvas class="tr" id="cE"></canvas></div>
 <div class="card" style="margin-top:12px"><h2>Pack temperature</h2>
  <canvas class="tr" id="cT"></canvas>
  <div class="legend"><span><i class="sw" style="background:#f85149"></i>hottest</span>
  <span><i class="sw" style="background:#58a6ff"></i>mean</span>
  <span><i class="sw" style="background:#3fb950"></i>coolant out</span></div></div>
</div></main>
<script>
const DATA = __DATA__;
let S = DATA.scenarios[0], i = 0, playing = false, last = 0;
const $ = id => document.getElementById(id);

const sel = $('scn');
DATA.scenarios.forEach((s,k)=>{const o=document.createElement('option');
  o.value=k;o.textContent=s.name;sel.appendChild(o)});
sel.onchange = e => { S = DATA.scenarios[+e.target.value]; i = 0; setup(); draw(); };

function setup(){
  $('t').max = S.t.length-1; $('t').value = 0;
  $('cfg').textContent = S.subtitle;
  const c=$('packc'); c.width=S.nx*14; c.height=S.ny*14*S.nlayers;
}
// perceptual blue->yellow->red ramp
function col(u){u=Math.max(0,Math.min(1,u));
  const st=[[13,17,23],[31,84,140],[56,160,150],[210,153,34],[248,81,73],[255,235,180]];
  const x=u*(st.length-1), k=Math.min(st.length-2,Math.floor(x)), f=x-k;
  const a=st[k],b=st[k+1];
  return `rgb(${a[0]+(b[0]-a[0])*f|0},${a[1]+(b[1]-a[1])*f|0},${a[2]+(b[2]-a[2])*f|0})`}

function drawPack(){
  const c=$('packc'), g=c.getContext('2d'), px=14;
  const f=S.field[i], lo=S.tlo, hi=S.thi;
  g.clearRect(0,0,c.width,c.height);
  for(let L=0;L<S.nlayers;L++)
   for(let y=0;y<S.ny;y++) for(let x=0;x<S.nx;x++){
    const idx=L*S.ny*S.nx+y*S.nx+x; if(idx>=f.length) continue;
    g.fillStyle=col((f[idx]-lo)/Math.max(1e-6,hi-lo));
    g.fillRect(x*px, (L*S.ny+y)*px, px-1, px-1)}
  const h=S.hot[i];
  g.strokeStyle='#fff';g.lineWidth=2;g.beginPath();
  g.arc((h[1]+0.5)*px,(h[0]+0.5)*px,px*0.55,0,6.284);g.stroke();
  $('scale').innerHTML = `<span>${lo.toFixed(1)} °C</span>` +
    Array.from({length:22},(_,k)=>`<i class="sw" style="width:11px;background:${col(k/21)}"></i>`).join('') +
    `<span>${hi.toFixed(1)} °C</span>` +
    (S.nlayers>1?`<span style="margin-left:10px">${S.nlayers} layers stacked vertically</span>`:'');
  $('hot').textContent = `hotspot: series group ${h[0]}, parallel position ${h[1]}`
    + `  ·  ${S.T_max[i].toFixed(2)} °C  ·  spread ${(S.T_max[i]-S.T_min[i]).toFixed(2)} K`;
}

function trace(id, series, opts){
  const c=$(id), g=c.getContext('2d');
  const w=c.width=c.clientWidth*2, h=c.height=236;
  g.scale(1,1); g.clearRect(0,0,w,h);
  const n=S.t.length, pad=26;
  let lo=opts.lo, hi=opts.hi;
  g.strokeStyle='#30363d'; g.lineWidth=1;
  for(let k=0;k<=3;k++){const y=pad+(h-2*pad)*k/3;
    g.beginPath();g.moveTo(0,y);g.lineTo(w,y);g.stroke();
    g.fillStyle='#8b949e';g.font='16px ui-monospace';
    g.fillText((hi-(hi-lo)*k/3).toFixed(opts.dp??1),4,y-4)}
  if(opts.ref!==undefined){const y=pad+(h-2*pad)*(1-(opts.ref-lo)/(hi-lo));
    g.strokeStyle='#f85149';g.setLineDash([7,5]);g.beginPath();
    g.moveTo(0,y);g.lineTo(w,y);g.stroke();g.setLineDash([])}
  series.forEach(s=>{g.strokeStyle=s.c;g.lineWidth=s.lw||2.4;g.beginPath();
    for(let k=0;k<n;k++){const x=w*k/(n-1),
      y=pad+(h-2*pad)*(1-(s.d[k]-lo)/(hi-lo));
      k?g.lineTo(x,y):g.moveTo(x,y)} g.stroke()});
  const x=w*i/(n-1);
  g.strokeStyle='#e6edf3';g.lineWidth=1.6;g.beginPath();
  g.moveTo(x,0);g.lineTo(x,h);g.stroke();
}

function draw(){
  drawPack();
  const cap=S.energy_cap;
  trace('cP',[{d:S.P_cmd,c:'#8b949e',lw:1.6},{d:S.P_shaft,c:'#58a6ff'}],
        {lo:0,hi:27,ref:25,dp:0});
  trace('cV',[{d:S.v_kmh,c:'#3fb950'}],{lo:0,hi:Math.max(...S.v_kmh)*1.15,dp:0});
  trace('cE',[{d:S.energy,c:'#d29922'}],{lo:0,hi:cap*1.1,ref:cap,dp:2});
  trace('cT',[{d:S.T_max,c:'#f85149'},{d:S.T_mean,c:'#58a6ff'},
              {d:S.cool_out,c:'#3fb950',lw:1.6}],
        {lo:Math.min(...S.cool_out)-2,hi:Math.max(...S.T_max)+3,dp:1});
  const d=S.derate[i];
  $('kv').innerHTML = [
   ['speed',S.v_kmh[i].toFixed(1),'km/h'],
   ['shaft power',(S.P_shaft[i]/1000).toFixed(2),'kW'],
   ['prop rpm',S.n_rpm[i].toFixed(0),''],
   ['prop eff',(S.prop_eff[i]*100).toFixed(1),'%'],
   ['bus current',S.I_pack[i].toFixed(0),'A'],
   ['pack voltage',S.V_pack[i].toFixed(1),'V'],
   ['SOC',(S.soc[i]*100).toFixed(1),'%'],
   ['energy used',S.energy[i].toFixed(3),'kWh'],
   ['pack heat',S.q_W[i].toFixed(0),'W'],
   ['T max',S.T_max[i].toFixed(1),'°C'],
   ['lap',S.lap[i].toFixed(2),''],
   ['derate',(d*100).toFixed(0),'%']
  ].map(([k,v,u])=>`<div><span>${k}</span><b class="${
     k==='derate'&&d<0.999?'warn':(k==='T max'&&S.T_max[i]>45?'bad':'')
   }">${v}<small style="font-size:11px;color:#8b949e"> ${u}</small></b></div>`).join('');
  $('tl').textContent = `t = ${(S.t[i]/60).toFixed(2)} min   ·   ${S.leg[i]}`;
  $('t').value = i;
}
$('t').oninput = e => { i = +e.target.value; draw(); };
$('play').onclick = () => { playing = !playing;
  $('play').textContent = playing ? '❚❚ pause' : '▶ play';
  last = performance.now(); if (playing) requestAnimationFrame(tick); };
function tick(ts){ if(!playing) return;
  const r = +$('rate').value, dtf = (ts-last)/1000; last = ts;
  i += Math.max(1, Math.round(dtf*r*S.fps));
  if (i >= S.t.length){ i = 0; }
  draw(); requestAnimationFrame(tick); }
window.onresize = draw;
setup(); draw();
</script></body></html>"""


def build_dashboard(scenarios, out="figures/race_simulator.html"):
    """scenarios: list of (name, subtitle, race_dict, geometry)."""
    payload = {"scenarios": []}
    for name, subtitle, r, geom in scenarios:
        nx, ny = geom.n_parallel, geom.n_series // max(1, geom.n_layers)
        nlayers = geom.n_layers
        # reorder cells to (layer, row, col) for the canvas
        order = np.lexsort((geom.parallel_index,
                            geom.series_index % ny,
                            geom.layer_id))
        f = r["field"][:, order]
        payload["scenarios"].append(dict(
            name=name, subtitle=subtitle,
            nx=int(nx), ny=int(ny), nlayers=int(nlayers),
            fps=float(1.0 / max(1e-6, r["t"][1] - r["t"][0])) if len(r["t"]) > 1 else 1.0,
            t=[round(float(x), 2) for x in r["t"]],
            P_cmd=[round(float(x) / 1000, 3) for x in r["P_cmd"]],
            P_shaft=[round(float(x) / 1000, 3) for x in r["P_shaft"]],
            v_kmh=[round(float(x), 2) for x in r["v_kmh"]],
            n_rpm=[round(float(x), 0) for x in r["n_rpm"]],
            prop_eff=[round(float(x), 4) for x in r["prop_eff"]],
            I_pack=[round(float(x), 1) for x in r["I_pack"]],
            V_pack=[round(float(x), 2) for x in r["V_pack"]],
            soc=[round(float(x), 4) for x in r["soc"]],
            energy=[round(float(x), 4) for x in r["energy_kWh"]],
            q_W=[round(float(x), 1) for x in r["q_W"]],
            T_max=[round(float(x), 3) for x in r["T_max"]],
            T_mean=[round(float(x), 3) for x in r["T_mean"]],
            T_min=[round(float(x), 3) for x in r["T_min"]],
            cool_out=[round(float(x), 3) for x in r["cool_out"]],
            derate=[round(float(x), 4) for x in r["derate"]],
            lap=[round(float(x), 3) for x in r["lap"]],
            leg=list(r["leg"]),
            hot=[[int(np.argmax(fr) // nx) % ny, int(np.argmax(fr) % nx)]
                 for fr in f],
            field=[[round(float(v), 2) for v in fr] for fr in f],
            tlo=float(np.floor(f.min())), thi=float(np.ceil(f.max())),
            energy_cap=float(r["energy_cap_kWh"]),
            stop=r["stop_reason"]))
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(_HTML.replace("__DATA__", json.dumps(payload,
                                                      separators=(",", ":"))))
    return out, os.path.getsize(out)
