#!/usr/bin/env python3
r"""
volare_thermal.functest
=======================

Functional test. The audit proves every control is WIRED; this proves every
control WORKS — it actually fires each one, in every view, and checks that
nothing throws and that the interface stays coherent afterwards.

Covers:
  * every button, select and range in the control rail and panels
  * all 48 command-palette entries
  * all 8 UI-flag combinations
  * all 6 views, cold and warm, in both themes
  * the full HV state machine and every fault
  * replay entry, scrubbing and exit
  * event switching across all five courses
  * report and CSV generation

Run:  python3 functest.py
"""

from __future__ import annotations
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
HTML = os.path.join(HERE, "figures", "mission_control.html")

STUB = r"""
// ---- strict canvas: throws on the things a real browser throws on ----
let OPS=0;
function chk(n,a){OPS++;for(const v of a) if(typeof v==='number'&&!isFinite(v))
 throw new Error(n+': non-finite ('+a.join(',')+')')}
function makeCtx(){return{
 canvas:{width:900,height:600},setTransform(){},
 clearRect(...a){chk('clearRect',a)},fillRect(...a){chk('fillRect',a)},
 beginPath(){},closePath(){},fill(){OPS++},stroke(){OPS++},save(){},restore(){},clip(){},
 moveTo(...a){chk('moveTo',a)},lineTo(...a){chk('lineTo',a)},
 quadraticCurveTo(...a){chk('quadraticCurveTo',a)},arcTo(...a){chk('arcTo',a)},
 arc(x,y,r,s,e){chk('arc',[x,y,r,s,e]);if(r<0)throw new Error('arc: r<0')},
 rect(...a){chk('rect',a)},translate(...a){chk('translate',a)},
 rotate(...a){chk('rotate',a)},scale(...a){chk('scale',a)},
 setLineDash(a){for(const v of a)if(!isFinite(v))throw new Error('setLineDash')},
 measureText(t){return{width:String(t).length*6}},
 fillText(t,x,y){chk('fillText',[x,y])},strokeText(t,x,y){chk('strokeText',[x,y])},
 createLinearGradient(...a){chk('lg',a);return{addColorStop(o,c){
  if(!isFinite(o)||o<0||o>1)throw new Error('stop '+o);
  if(String(c).indexOf('NaN')>=0)throw new Error('colour '+c)}}},
 createRadialGradient(...a){chk('rg',a);if(a[2]<0||a[5]<0)throw new Error('rg r<0');
  return{addColorStop(o,c){if(!isFinite(o)||o<0||o>1)throw new Error('stop '+o);
  if(String(c).indexOf('NaN')>=0)throw new Error('colour '+c)}}},
 set fillStyle(v){if(String(v).indexOf('NaN')>=0)throw new Error('fillStyle NaN')},
 get fillStyle(){return '#000'},
 set strokeStyle(v){if(String(v).indexOf('NaN')>=0)throw new Error('strokeStyle NaN')},
 get strokeStyle(){return '#000'},
 set lineWidth(v){if(!isFinite(v))throw new Error('lineWidth')},get lineWidth(){return 1},
 set globalAlpha(v){if(!isFinite(v)||v<0||v>1)throw new Error('alpha '+v)},
 get globalAlpha(){return 1},
 set shadowBlur(v){if(!isFinite(v)||v<0)throw new Error('shadowBlur')},
 get shadowBlur(){return 0},
 shadowColor:'#000',font:'12px m',lineCap:'butt',lineJoin:'miter'}}

let RAF=[],TIMERS=[],CLK=0;
const DEFAULTS={chan:'Tcore',src:'true',evt:'endurance',scn:'',sFlow:'80',
 sCirc:'3',sTube:'60',sBond:'25',sFluid:'g',sHdr:'160',thr:'40',tgt:'45',
 rate:'5',flow:'80',tin:'290',tamb:'300',wind:'0',wdir:'0',hs:'10'};
function mkEl(id){const ev={};const ctx=makeCtx();
 return{id,style:{},dataset:{},offsetWidth:1,offsetHeight:60,checked:true,
 children:[],width:900,height:600,firstChild:null,
 value:(DEFAULTS[id]!==undefined?DEFAULTS[id]:'40'),
 textContent:'',innerHTML:'',className:'',title:'',
 classList:{add(){},remove(){},contains:()=>false},
 getContext:()=>ctx,
 getBoundingClientRect:()=>({width:900,height:600,left:0,top:0,right:900,bottom:600}),
 appendChild(c){this.children.push(c)},removeChild(){this.children.pop()},
 addEventListener(t,f){(ev[t]=ev[t]||[]).push(f)},
 fire(t,e){(ev[t]||[]).forEach(f=>f(e||{}))},
 focus(){},click(){},querySelectorAll:()=>[],
 querySelector:function(s){if(s==='h3'){if(!this._h3){this._h3=mkEl('h3');
   this._h3._title=this._title}return this._h3}
  if(s==='span')return{textContent:this._title||'Panel'};
  return{textContent:'T max'}},
 set oninput(f){this._i=f},get oninput(){return this._i},
 set onchange(f){this._c=f},get onchange(){return this._c},
 set onclick(f){this._k=f},get onclick(){return this._k}}}
const _e={},_fx=[],_tabs=[],_cards=[];
for(const k of ['pump','restrict','imd','sensor','hotcell','vent']){
 const b=mkEl('fx_'+k);b.dataset={fx:k};_fx.push(b)}
for(let i=0;i<6;i++){const t=mkEl('tab'+i);
 t.dataset={v:['vTele','vTherm','vStrat','vEng','vSetup','vAnal'][i]};_tabs.push(t)}
for(const t of ['Pack — physical layout','Boat','Digital twin','Drivetrain',
 'Timing','Coolant circuits']){const c=mkEl('card');c._title=t;_cards.push(c)}
const _html=mkEl('html'),_body=mkEl('body');
global.document={getElementById:id=>(_e[id]=_e[id]||mkEl(id)),
 createElement:mkEl,body:_body,documentElement:_html,addEventListener(){},
 querySelectorAll:s=>(s==='.fx button'?_fx:s==='.tab'?_tabs:
  s==='.card'?_cards:s==='#hv div'?[]:[])};
global.performance={now:()=>CLK};
global.requestAnimationFrame=f=>{RAF.push(f);return RAF.length};
global.setTimeout=(f,ms)=>{TIMERS.push([ms||0,f]);return TIMERS.length};
global.navigator={userAgent:'functest'};
global.window={devicePixelRatio:2,addEventListener(){},innerWidth:1600,
 innerHeight:900,open:()=>({closed:false,document:{write(){},close(){},
  getElementById:()=>mkEl('c')}})};
global.Blob=function(){};
global.URL={createObjectURL:()=>'blob:x'};
"""

DRIVER = r"""
// ======================= FUNCTIONAL TEST =======================
let FAILS=0, RUN=0;
function T(name,fn){RUN++;try{fn()}catch(e){FAILS++;
 console.log('  FAIL  '+name+'  ->  '+e.message)}}
const VIEWS=['vTele','vTherm','vStrat','vEng','vSetup','vAnal'];
function renderAll(tag){for(const v of VIEWS){view=v;
 T(tag+' render '+v,()=>{
  const before=OPS; draw();
  // a view that renders nothing is broken, even if it does not throw
  if(OPS-before < 40)
   throw new Error('only '+(OPS-before)+' canvas ops — view drew nothing')})}}
function step(n,P){for(let k=0;k<n;k++){let Pc=P;
 if(!hvStep(1,E.stats()))Pc=0;
 envStep();Pc=arbitrate(Pc,E.stats());
 E.step(1,Pc,{flow:env.flow,tin:env.tin,tamb:env.tamb,
              wind:headEff+(waveR+crossR)/60});
 accumulate(1,Pc);record();
 const s=E.stats();events(s);
 if(k%10===0){dtHist.push([E.Tw,E.Tj,E.Tcase,E.Ths]);
  if(dtHist.length>240)dtHist.shift()}
 if(k%20===0)pushWF();
 H.t.push(E.t);H.v.push(E.v*3.6);H.P.push(Pc/1000);H.T.push(s.Tmax);
 H.z.push(s.soc*100);H.I.push(E.Ip);
 if(H.t.length>HMAX)for(const q in H)H[q].shift()}}

console.log('1. BOOT');
let fn=RAF[0];
for(const t of [0,900,2200,3600,4200,4400]){CLK=t;RAF=[];
 T('boot frame t='+t,()=>fn(t));if(RAF.length)fn=RAF[0]}
const handoff=TIMERS.filter(x=>x[0]===430);
T('boot scheduled a handoff',()=>{if(!handoff.length)
 throw new Error('boot never reached its completion branch')});
handoff.forEach(x=>T('boot handoff',()=>x[1]()));
T('boot log populated',()=>{if($('bootLog').children.length<5)
 throw new Error('only '+$('bootLog').children.length+' log lines')});
T('boot progress reached 100%',()=>{
 if(String($('bootBar').style.width)!=='100%')
  throw new Error('bar at '+$('bootBar').style.width)});
T('main loop reachable',()=>{if(!RAF.length)
 throw new Error('boot did not hand off to frame()')});
console.log('   boot dismissed, '+$('bootLog').children.length+' log lines, '+
 'bar '+$('bootBar').style.width);
renderAll('cold');

console.log('\n2. SIMULATE');
T('hv on',()=>$('hvBtn').onclick());
step(900,25000*DEMAND_HEADROOM);
console.log('   t='+(E.t/60).toFixed(1)+' min  v='+(E.v*3.6).toFixed(1)+
 ' km/h  T='+E.stats().Tmax.toFixed(1)+' C  laps='+E.lap);
renderAll('warm');

console.log('\n3. EVERY RAIL CONTROL');
for(const b of ['run','rst','ap','theme','dens','rpt','prov','csv','hvBtn','estop'])
 T('button '+b,()=>{if($(b).onclick)$(b).onclick({stopPropagation(){}})});
T('button run (restore)',()=>{if(!running)$('run').onclick()});
T('button hv (restore)',()=>{if(HV==='FAULT')$('hvBtn').onclick();
 if(HV==='OFF')$('hvBtn').onclick()});
for(const sl of ['thr','tgt','flow','tin','tamb','wind','wdir','hs'])
 for(const v of ['0','50','100'])
  T('slider '+sl+'='+v,()=>{$(sl).value=v;if($(sl).oninput)$(sl).oninput()});
for(const s of ['chan','src','evt','scn','sFlow','sCirc','sTube','sBond',
                'sFluid','sHdr'])
 T('select '+s,()=>{if($(s).onchange)$(s).onchange();
                    if($(s).oninput)$(s).oninput()});
T('popPack',()=>$('popPack').onclick({stopPropagation(){}}));
T('popMap',()=>$('popMap').onclick({stopPropagation(){}}));
T('drawPops',()=>drawPops());
console.log('   pop-out windows tracked: '+POPS.length);

console.log('\n4. THERMAL CHANNELS x FIELD SOURCES');
view='vTherm';
for(const c of ['Tcore','Tcan','dT','q','qRev','I','R0','z'])
 for(const s of ['true','bms','err']){
  $('chan').value=c;$('src').value=s;
  T('chan '+c+' src '+s,()=>{const b=OPS;draw();
   if(OPS-b<40)throw new Error('drew nothing')})}
$('chan').value='Tcore';$('src').value='true';
for(const tb of [true,false]){$('showTubes').checked=tb;
 T('tubes '+tb,()=>draw())}
$('showTubes').checked=true;

console.log('\n5. UI FLAGS — all 8 combinations, both themes rendered');
for(let m=0;m<8;m++){
 setFlag('day',!!(m&1));setFlag('tight',!!(m&2));setFlag('prov',!!(m&4));
 const want=[(m&1)?'day':'',(m&2)?'tight':'',(m&4)?'prov':''].filter(Boolean).join(' ');
 T('flags m='+m,()=>{
  if(document.documentElement.className!==want)
   throw new Error('html "'+document.documentElement.className+'" != "'+want+'"');
  if(document.body.className!==want)
   throw new Error('body mismatch')});
 PX=null;TX=null;
 for(const v of VIEWS){view=v;T('flags m='+m+' '+v,()=>draw())}}
setFlag('day',false);setFlag('tight',false);setFlag('prov',false);

console.log('\n6. FAULT INJECTION');
for(const b of _fx){
 T('inject '+b.dataset.fx,()=>b.onclick());
 step(30,15000);renderAll('fault-'+b.dataset.fx);
 T('clear '+b.dataset.fx,()=>b.onclick())}
if(HV==='FAULT')T('clear hv fault',()=>$('hvBtn').onclick());
if(HV==='OFF')T('hv back on',()=>$('hvBtn').onclick());

console.log('\n7. SCENARIOS');
for(const k of Object.keys(SCEN)){
 T('scenario '+k,()=>applyScenario(k));
 step(60,20000);renderAll('scn-'+k)}
T('scenario nominal',()=>applyScenario('nominal'));

console.log('\n8. EVENTS');
for(const ev of ['endurance','qualifying','championship_outer',
                 'championship_inner','slalom']){
 T('event '+ev,()=>setEvent(ev));
 step(40,18000);renderAll('evt-'+ev)}
T('event endurance',()=>setEvent('endurance'));

console.log('\n9. REPLAY');
step(300,18000);
T('enter replay',()=>enterReplay());
for(const f of [0,0.2,0.4,0.6,0.8,1]){
 T('scrub '+f,()=>{replayAt=Math.round(f*(REC.t.length-1));updateReplay()});
 for(const v of VIEWS){view=v;T('replay render '+v+' @'+f,()=>draw())}}
T('exit replay',()=>exitReplay());

console.log('\n10. PALETTE — all '+CMDS.length+' commands');
T('open palette',()=>palOpen());
for(let i=0;i<CMDS.length;i++){
 palSel=i;palHits=CMDS;
 T('cmd "'+CMDS[i][0]+'"',()=>palRun())}
T('close palette',()=>palClose());
if(HV==='FAULT')T('recover hv',()=>$('hvBtn').onclick());

console.log('\n11. INTERACTION');
T('pack click',()=>$('pack').fire('click',{clientX:300,clientY:200}));
T('pack hover',()=>$('pack').fire('mousemove',{clientX:300,clientY:200}));
T('pack leave',()=>$('pack').fire('mouseleave'));
T('trace hover',()=>$('trc').fire('mousemove',{clientX:400,clientY:200}));
T('trace leave',()=>$('trc').fire('mouseleave'));
T('inspector renders',()=>{view='vTherm';draw()});

console.log('\n12. OUTPUT');
T('report builds',()=>{const m=buildReport();
 if(m.indexOf('undefined')>=0)throw new Error('report contains "undefined"');
 if(m.indexOf('NaN')>=0)throw new Error('report contains NaN');
 if(m.length<1200)throw new Error('report too short');});
T('report downloads',()=>downloadReport());
T('csv downloads',()=>$('csv').onclick());
T('summary shows',()=>showSummary());
T('summary close',()=>$('sumClose').onclick());
T('new session',()=>$('sumRst').onclick());
renderAll('post-reset');

console.log('\n13. RESET AND RERUN');
T('reset',()=>$('rst').onclick());
T('hv on again',()=>{if(HV==='OFF')$('hvBtn').onclick()});
step(200,15000);
renderAll('rerun');

console.log('\n'+RUN+' assertions · '+FAILS+' failures · '+OPS+' canvas ops');
if(FAILS)process.exit(1);
"""


def main():
    if not shutil.which("node"):
        print("node is required"); return 1
    if not os.path.exists(HTML):
        print("no dashboard — run: python3 run.py mission"); return 1
    html = open(HTML, encoding="utf-8").read()
    js = html.split("<script>", 1)[1].rsplit("</script>", 1)[0]
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False,
                                     encoding="utf-8") as f:
        f.write(STUB + js + DRIVER)
        tmp = f.name
    r = subprocess.run(["node", tmp], capture_output=True, text=True,
                       timeout=600)
    os.unlink(tmp)
    print(r.stdout)
    if r.returncode:
        print(r.stderr[:3000])
    return r.returncode


if __name__ == "__main__":
    sys.exit(main())
