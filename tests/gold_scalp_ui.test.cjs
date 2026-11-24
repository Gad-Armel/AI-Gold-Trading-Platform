// Exercise the actual dashboard renderer with a small DOM test double.
// This checks text/control state, not pixel layout or browser rendering.
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
class Element {
  constructor() { this.textContent=''; this.dataset={}; this.children=[]; this.value='60'; this.classList={add(){},remove(){},toggle(){}}; }
  append(...items) { this.children.push(...items); }
  replaceChildren(...items) { this.children=items; }
  add(item) { this.append(item); }
  addEventListener() {}
  getBoundingClientRect() { return {width:800,height:300}; }
  getContext() { return new Proxy({}, {get:()=>()=>{}}); }
}
const nodes=new Map();
const document={hidden:false,body:new Element(),getElementById(id){if(!nodes.has(id))nodes.set(id,new Element());return nodes.get(id);},createElement(){return new Element();},createDocumentFragment(){return new Element();},addEventListener(){}};
const context=vm.createContext({document,window:{devicePixelRatio:1,addEventListener(){}},Option:Element,console,setTimeout(){},clearTimeout(){},fetch(){throw Error('Tests must never send network or trading commands');}});
const source=fs.readFileSync(path.join(__dirname,'../services/dashboard/gold_scalp_assets/app.js'),'utf8').replace('drawCandles(); drawEquity(); poll();','drawCandles(); drawEquity();');
vm.runInContext(source,context);
const snapshot={currency:'USD',symbol:'XAUUSD',server:'TEST',login:'FIXTURE',version:'3.21',paused:true,locked:true,server_time:'TEST',instance:'TEST',status:'TEST',account:{},kpi:{},market:{},filters:{},risk:{text:'Fixed risk'},positions:[],candles:[],deals:[],events:[],controls:{enabled:true,instance:'TEST',can_execute:true},scalp:{enabled:true,sessions:[]}};
context.fixture={state:'live',source:'fixture',sources:[],control_token:'LOCAL_TEST_ONLY',snapshot};
vm.runInContext('render(fixture)',context);
const checks=[];
const check=(value,name)=>checks.push({name,passed:!!value});
check(!nodes.get('risk-summary').textContent.includes('undefined'),'legacy snapshot has no undefined risk values');
Object.assign(snapshot.risk,{rolling_remaining:.5,rolling_realized:-4.5,rolling_limit:5,loss_streak:3,cooldown_seconds:120,entries_hour:5,entries_hour_max:36});
Object.assign(snapshot.scalp,{confirmation_samples:4,confirmation_age_ms:1000,confirmation_grace:true,counterflow_guard:true});
vm.runInContext('render(fixture)',context);
check(nodes.get('risk-summary').textContent.includes('Remaining before stop reservations 0.50 USD'),'remaining rolling budget visible');
check(nodes.get('risk-summary').textContent.includes('Cooldown 120s'),'cooldown visible');
check(nodes.get('risk-summary').textContent.includes('Entries/hour 5/36'),'hourly cap visible');
check(nodes.get('scalp-summary').textContent.includes('4 sampled quotes / 1000 ms'),'confirmation evidence visible');
check(nodes.get('scalp-summary').textContent.includes('Counterflow guard: on'),'counterflow state visible');
check(nodes.get('pause-trading').disabled,'locked paused account cannot resume');
check(nodes.get('reset-session').disabled,'older native feed cannot reset');
snapshot.controls.can_reset=true;snapshot.risk.manual_reset_required=true;
vm.runInContext('render(fixture)',context);
check(!nodes.get('reset-session').disabled,'flat supported live EA can reset loss session');
check(nodes.get('safety-lock').textContent.includes('manual loss-session reset'),'manual loss stop does not promise automatic restart');
vm.runInContext('clearData()',context);
check(nodes.get('reset-session').disabled,'missing feed disables reset');
check(!nodes.get('risk-summary').textContent.includes('0.50'),'missing feed clears budget values');
console.log(JSON.stringify({passed:checks.filter(c=>c.passed).length,total:checks.length,checks}));
if(checks.some(c=>!c.passed))process.exitCode=1;
