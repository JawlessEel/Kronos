let ort, entry, sessions = {}, busy = false, cancelled = false;
let pre;
let cacheStats;
const CACHE = 'kronos-local-v2';
const send = (type, extra) => postMessage({type, ...extra});
const tensor = (data, dims) => new ort.Tensor('float32', Float32Array.from(data.flat(Infinity)), dims);
const indices = (data, dims) => new ort.Tensor('int32', Int32Array.from(data.flat(Infinity)), dims);
async function dispose() {
  for (const s of Object.values(sessions)) await s.release();
  sessions = {}; entry = null;
}
async function artifact(file, base, persistent, progress) {
  const url = new URL(file.url, base).href;
  let cache=null,response;
  if(persistent){try{cache=await caches.open(CACHE);response=await cache.match(url);}catch(e){cacheStats.warnings.push('Persistent cache unavailable: '+e.message);}}
  let bytes;
  if (response) bytes = new Uint8Array(await response.arrayBuffer());
  async function valid(b) {
    if (b.length !== file.bytes) return false;
    const hash = await crypto.subtle.digest('SHA-256', b);
    return [...new Uint8Array(hash)].map(v => v.toString(16).padStart(2,'0')).join('') === file.sha256;
  }
  if (bytes && !await valid(bytes)) {await cache.delete(url); bytes = null;}
  if(bytes)cacheStats.hits++;
  if (!bytes) {
    cacheStats.misses++;
    response = await fetch(url);
    if (!response.ok) throw Error('Model download HTTP ' + response.status);
    const reader = response.body.getReader(), chunks = []; let count = 0;
    for (;;) {
      const r = await reader.read(); if (r.done) break;
      if (cancelled) {await reader.cancel(); throw Error('Cancelled');}
      chunks.push(r.value); count += r.value.length; progress(count/file.bytes);
    }
    bytes = new Uint8Array(count); let offset = 0;
    for (const c of chunks) {bytes.set(c,offset); offset += c.length;}
    if (!await valid(bytes)) throw Error('Model size or SHA-256 mismatch: ' + file.name);
    if(cache){try{await cache.put(url,new Response(bytes));}catch(e){cacheStats.warnings.push('Model runs in memory; cache write failed: '+e.message);}}
  }
  progress(1); return bytes;
}
async function load(m) {
  await dispose(); cancelled = false;
  cacheStats={enabled:!!m.persistent,hits:0,misses:0,warnings:[]};
  entry = m.manifest.models.find(v => v.id === m.model);
  if (!entry || !['graph-validated','validated'].includes(entry.status)) throw Error('Model export not validated');
  ort = await import(m.manifest.runtime.url);
  ort.env.wasm.wasmPaths = new URL('./',m.manifest.runtime.url).href;
  ort.env.wasm.numThreads = 1;
  // Keep all preprocessing in the worker. The source URL is resolved by the
  // controller, since a blob worker cannot resolve relative module imports.
  pre = (await import(m.preprocessUrl)).KronosPre;
  for (let i=0;i<entry.files.length;i++) {
    const f = entry.files[i];
    const bytes = await artifact(f,m.manifestUrl,m.persistent,frac => send('load-progress',{model:m.model,file:f.name,frac:(i+frac)*0.9/entry.files.length}));
    sessions[f.name] = await ort.InferenceSession.create(bytes,{executionProviders:['webgpu'],graphOptimizationLevel:'disabled'});
    send('load-progress',{model:m.model,file:f.name+' session created',frac:(i+1)*0.9/entry.files.length});
  }
  // Exercise every graph, not merely session creation or a nonempty download.
  send('load-progress',{model:m.model,file:'tokenizer encode smoke',frac:0.91});
  const encoded = await sessions['tokenizer-encode'].run({x:tensor(new Array(16*6).fill(0),[1,16,6])});
  send('load-progress',{model:m.model,file:'tokenizer decode smoke',frac:0.93});
  const decoded = await sessions['tokenizer-decode'].run(encoded);
  send('load-progress',{model:m.model,file:'predictor s1 smoke',frac:0.95});
  const s1 = await sessions['predictor-s1'].run({s1_ids:indices(Array.from(encoded.s1_ids.data),[1,16]),s2_ids:indices(Array.from(encoded.s2_ids.data),[1,16]),stamp:indices(Array.from({length:16},()=>[0,10,0,4,10]),[1,16,5])});
  send('load-progress',{model:m.model,file:'predictor s2 smoke',frac:0.97});
  const s2 = await sessions['predictor-s2'].run({context:s1.context,s1_ids:indices([0],[1,1])});
  if (![...decoded.x.data,...s1.logits.data,...s2.logits.data].every(Number.isFinite)) throw Error('Inference smoke test returned nonfinite data');
  send('load-done',{model:m.model,artifacts:{backend:'webgpu',smokePassed:true,cache:cacheStats,files:entry.files.map(f=>({name:f.name,bytes:f.bytes,sha256:f.sha256}))}});
}
async function predict(m) {
  if (!entry) throw Error('Load model first');
  const r = m.req, caps=entry.browserDefaults;
  for (const [key,value,max] of [['lookback',r.lookback,caps.lookback],['horizon',r.horizon,caps.horizon],['samples',r.samples,caps.samples]])
    if (!Number.isInteger(value)||value<1||value>max) throw Error(key+' must be between 1 and '+max);
  if (!(r.temperature>0) || !(r.top_p>0&&r.top_p<=1)) throw Error('Invalid sampling parameters');
  if(!Number.isFinite(r.temperature)||!Number.isInteger(r.seed)||!Number.isInteger(r.top_k||0)||(r.top_k||0)<0)throw Error('Invalid temperature, seed or top_k');
  if(!['UTC','ET'].includes(r.timeMode))throw Error('Use UTC or ET calendar features');
  if (!Array.isArray(r.candles)||r.candles.length<r.lookback||!Array.isArray(r.futureTimes)||r.futureTimes.length!==r.horizon) throw Error('Candle or future timestamp count mismatch');
  const bars=r.candles.slice(-r.lookback);
  const times=[...bars.map(b=>b.t),...r.futureTimes];
  if (!times.every((t,i)=>Number.isFinite(t)&&(!i||t>times[i-1]))) throw Error('Timestamps must be finite and strictly increasing');
  const prepared=pre.assemble6(bars.map(b=>({...b,vBase:b.v})));
  if (!prepared.matrix.flat().every(Number.isFinite)) throw Error('Missing or invalid input data');
  // KronosPredictor converts inputs to float32 BEFORE calculating statistics.
  const f=Math.fround, matrix=prepared.matrix.map(row=>row.map(f));
  if(!matrix.flat().every(Number.isFinite))throw Error('Input exceeds float32 range');
  const mean=Array(6).fill(0),std=Array(6).fill(0),n=matrix.length;
  for(const row of matrix)for(let j=0;j<6;j++)mean[j]=f(mean[j]+row[j]);
  for(let j=0;j<6;j++)mean[j]=f(mean[j]/n);
  for(const row of matrix)for(let j=0;j<6;j++){const d=f(row[j]-mean[j]);std[j]=f(std[j]+f(d*d));}
  for(let j=0;j<6;j++)std[j]=f(Math.sqrt(f(std[j]/n)));
  const stats={mean,std};
  const input=matrix.map(row=>row.map((v,j)=>Math.max(-5,Math.min(5,f(f(v-mean[j])/f(std[j]+1e-5))))));
  const feature=r.timeMode==='ET'?pre.timeFeaturesET:pre.timeFeaturesUTC;
  const stamps=times.map(feature), random=pre.mulberry32(r.seed);
  if(!stamps.flat().every(Number.isFinite))throw Error('Invalid calendar features');
  const paths=[], diagnostics={};
  for (let sample=0;sample<r.samples;sample++) {
    const ids=await sessions['tokenizer-encode'].run({x:tensor(input,[1,input.length,6])});
    const a=Array.from(ids.s1_ids.data), b=Array.from(ids.s2_ids.data);
    if(r.diagnostics){diagnostics.s1_ids=a.slice();diagnostics.s2_ids=b.slice();diagnostics.mean=stats.mean;diagnostics.std=stats.std;}
    for(let step=0;step<r.horizon;step++) {
      if(cancelled) throw Error('Cancelled');
      const start=Math.max(0,a.length-entry.maxContext), length=a.length-start;
      const out=await sessions['predictor-s1'].run({s1_ids:indices(a.slice(start),[1,length]),s2_ids:indices(b.slice(start),[1,length]),stamp:indices(stamps.slice(start,a.length),[1,length,5])});
      const nextA=pre.sampleFromLogits(Array.from(out.logits.data),r.temperature,r.top_k||0,r.top_p,random,!!r.greedy);
      const out2=await sessions['predictor-s2'].run({context:out.context,s1_ids:indices([nextA],[1,1])});
      if(r.diagnostics&&step===0){diagnostics.s1_logits=Array.from(out.logits.data);diagnostics.context=Array.from(out.context.data).slice(-256);diagnostics.s2_logits=Array.from(out2.logits.data);diagnostics.embedding=Array.from(out.embedding.data);diagnostics.time_embedding=Array.from(out.time_embedding.data);}
      const nextB=pre.sampleFromLogits(Array.from(out2.logits.data),r.temperature,r.top_k||0,r.top_p,random,!!r.greedy);
      a.push(nextA); b.push(nextB);
      send('predict-progress',{job:m.job,step:step+1,of:r.horizon,sample:sample+1});
    }
    const length=Math.min(a.length,entry.maxContext);
    const decoded=await sessions['tokenizer-decode'].run({s1_ids:tensor(a.slice(-length),[1,length]),s2_ids:tensor(b.slice(-length),[1,length])});
    const data=Array.from(decoded.x.data).slice(-r.horizon*6);
    const matrix=Array.from({length:r.horizon},(_,i)=>data.slice(i*6,i*6+6));
    paths.push(matrix.map(row=>row.map((v,j)=>f(f(v*f(stats.std[j]+1e-5))+stats.mean[j]))));
  }
  if(cancelled) throw Error('Cancelled');
  const rows=Array.from({length:r.horizon},(_,i)=>{
    const values=Array.from({length:6},(_,j)=>paths.reduce((v,p)=>v+p[i][j],0)/paths.length);
    if (!values.every(Number.isFinite)) throw Error('Nonfinite forecast');
    return Object.fromEntries(['o','h','l','c','v','turnover'].map((k,j)=>[k,values[j]]));
  });
  send('predict-done',{job:m.job,result:{model:entry.id,tokenizer:entry.tokenizer,rows,times:r.futureTimes,sample_paths:paths,diagnostics:r.diagnostics?diagnostics:undefined,provenance:{backend:'webgpu',runtime:'onnxruntime-web/1.22.0',sourceBars:bars.length,seed:r.seed,greedy:!!r.greedy,missingVolume:prepared.missingVolume,estimatedAmount:prepared.missingAmount,normalization:'population standard deviation, epsilon 1e-5, clip 5',rawModelOHLC:true}}});
}
self.onmessage=async ({data:m})=>{
  if(m.type==='cancel'){cancelled=true;return;}
  if(busy){send(m.type==='load'?'load-error':'predict-error',{model:m.model,job:m.job,error:'Worker busy'});return;}
  busy=true; cancelled=false;
  try {
    if(m.type==='load') await load(m);
    else if(m.type==='predict') await predict(m);
    else if(m.type==='unload') await dispose();
  } catch(e) {
    if(m.type==='load') await dispose();
    send(m.type==='load'?'load-error':'predict-error',{model:m.model,job:m.job,error:e.message||String(e)});
  } finally {busy=false;}
};
