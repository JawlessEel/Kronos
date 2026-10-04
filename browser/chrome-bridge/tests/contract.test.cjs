const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const base = path.resolve(__dirname,'../extension');
const contract = require(path.resolve(base,'../../perchance/src/tradingview-contract.js'));
const now = Date.now();
function sample() { return {schema:'kronos-tradingview/1',engine:'kronos-local',targetSymbol:'OKX:BTCUSDT',timeframe:'1h',seconds:3600,session:'24x7',generatedAt:now,anchorTime:now-3600000,rows:[{t:now,o:100,h:102,l:99,c:101,quality:'OK'},{t:now+3600000,o:101,h:103,l:100,c:102,quality:'OK'}]}; }
test('Pine encoding retains exact timestamps, prices and repeated-validation quality flags',()=>{
  const clean = contract.validate(sample(),now);
  const again = contract.validate(clean,now);
  assert.deepEqual(again.rows,clean.rows);
  assert.equal(again.rows[0].flag,0);
  assert.equal(contract.encode(clean,now).split('\n')[1],`${now},100,102,99,101,0`);
});
test('OHLC inconsistencies are preserved and flagged, never repaired',()=>{
  const value=sample(); value.rows[0].h=98;
  const result=contract.validate(value,now); assert.equal(result.rows[0].h,98); assert.equal(result.rows[0].flag,1);
});
for (const [name,edit] of [
  ['statistical engine',v=>v.engine='statistical'],
  ['unqualified symbol',v=>v.targetSymbol='BTCUSDT'],
  ['markup in symbol',v=>v.targetSymbol='OKX:<script>'],
  ['timeframe mismatch',v=>v.seconds=60],
  ['unsupported session',v=>v.session='mixed'],
  ['old forecast',v=>v.generatedAt=now-3*86400000],
  ['future generation',v=>v.generatedAt=now+600000],
  ['out of order',v=>v.rows[1].t=v.rows[0].t],
  ['nonfinite price',v=>v.rows[0].h=Infinity],
  ['null price',v=>v.rows[0].c=null],
  ['invalid quality flag',v=>v.rows[0].flag=2],
  ['oversized horizon',v=>v.rows=Array(121).fill(v.rows[0])],
  ['expired horizon',v=>{v.anchorTime=now-4*3600000;v.rows[0].t=now-3*3600000;v.rows[1].t=now-2*3600000;}]
]) test(`Rejects ${name}`,()=>{const value=sample();edit(value);assert.throws(()=>contract.validate(value,now));});
test('Extra source data is excluded from stored/encoded payload',()=>{
  const value=sample();value.unrelated='do not retain';value.rows[0].unrelated='do not retain';
  assert.equal(contract.validate(value,now).unrelated,undefined);assert.equal(contract.validate(value,now).rows[0].unrelated,undefined);
});
test('Shared page and extension contracts stay byte-identical',()=>assert.equal(fs.readFileSync(path.join(base,'protocol.js'),'utf8'),fs.readFileSync(path.resolve(base,'../../perchance/src/tradingview-contract.js'),'utf8')));
test('Extension ships Pine source, scopes host access, and loads only local extension code',()=>{
  const manifest=JSON.parse(fs.readFileSync(path.join(base,'manifest.json'),'utf8'));
  assert.equal(manifest.manifest_version,3);assert.deepEqual(manifest.permissions,['storage']);
  assert.ok(!JSON.stringify(manifest).includes('<all_urls>'));
  for (const entry of manifest.content_scripts) for(const file of entry.js) assert.ok(fs.existsSync(path.join(base,file)));
  assert.ok(fs.existsSync(path.join(base,'Kronos-Forecast-Bridge.pine')));
});
test('Worker accepts only designated source origins and validates before persistence',async()=>{
  let listener;const stored={};const context={URL,Date,Number,Error,KronosTVContract:contract,importScripts:()=>{},chrome:{runtime:{onMessage:{addListener:f=>listener=f}},storage:{local:{set:async x=>Object.assign(stored,x),get:async()=>({})}},action:{setBadgeText:async()=>{},setBadgeBackgroundColor:async()=>{}}}};
  vm.runInNewContext(fs.readFileSync(path.join(base,'background.js'),'utf8'),context);
  assert.equal(listener({type:'forecast',payload:sample()},{tab:{id:1},url:'https://evil.example/'},()=>assert.fail('Untrusted source replied')),undefined);
  assert.equal(stored.forecast,undefined);
  const response=await new Promise(resolve=>listener({type:'forecast',payload:sample()},{tab:{id:1},url:'http://127.0.0.1:7082/'},resolve));
  assert.equal(response.ok,true);assert.equal(stored.forecast.rows[0].flag,0);
  const invalid=sample();invalid.engine='statistical';
  const rejected=await new Promise(resolve=>listener({type:'forecast',payload:invalid},{tab:{id:1},url:'http://localhost:7082/'},resolve));assert.equal(rejected.ok,false);
});
