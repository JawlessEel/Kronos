window.KronosLocal = (() => {
  const scriptUrl = document.currentScript.src;
  const configuredBase = window.KronosLocalConfig && window.KronosLocalConfig.assetBase;
  const base = configuredBase ? new URL(configuredBase,document.baseURI) : (scriptUrl.startsWith('blob:') ? new URL('./src/kronos-local/',document.baseURI) : new URL('./',scriptUrl));
  const state={backend:'unknown',ready:false,loading:false,progress:0,model:'kronos-mini',job:0,error:null};
  let worker, workerUrl, pending;
  let cacheEnabled=false;
  try{cacheEnabled=localStorage.getItem('kronos-cache-opt-in')==='true';}catch(e){state.cacheWarning='Preference storage unavailable; model persistence defaults off';}
  async function detect() {
    const info={secure:isSecureContext,hasGPU:!!navigator.gpu,adapter:false,device:false};
    try {
      if(info.secure&&navigator.gpu) {
        const adapter=await navigator.gpu.requestAdapter(); info.adapter=!!adapter;
        if(adapter){const device=await adapter.requestDevice();info.device=true;device.destroy();}
      }
    } catch(e){info.error=e.message;}
    state.backend=info.device?'webgpu':'unavailable';state.deviceInfo=info;return info;
  }
  async function ensureWorker() {
    if(worker)return worker;
    const response=await fetch(new URL('kronos-worker.js',base));
    if(!response.ok)throw Error('Worker HTTP '+response.status);
    workerUrl=URL.createObjectURL(new Blob([await response.text()],{type:'text/javascript'}));
    worker=new Worker(workerUrl,{type:'module'});return worker;
  }
  function request(message,progress,timeout) {
    if(pending)throw Error('A model operation is already running');
    return new Promise((resolve,reject)=>{
      const w=worker;
      const finish=(error,result)=>{clearTimeout(timer);w.removeEventListener('message',receive);w.removeEventListener('error',crashed);pending=null;error?reject(error):resolve(result);};
      const crashed=e=>finish(Error(e.message||'Model worker crashed'));
      const receive=({data:m})=>{
        if(message.type==='load'?m.model!==message.model:m.job!==message.job)return;
        if(m.type.endsWith('-progress')){state.progress=m.frac||state.progress;if(progress)progress(m);}
        else if(m.type.endsWith('-error'))finish(Error(m.error));
        else if(m.type.endsWith('-done'))finish(null,m.result||m.artifacts);
      };
      const timer=setTimeout(()=>{finish(Error('Model operation timed out'));stopWorker();},timeout);
      pending={reject:reason=>finish(Error(reason))};
      w.addEventListener('message',receive);w.addEventListener('error',crashed);w.postMessage(message);
    });
  }
  function stopWorker(){if(worker)worker.terminate();worker=null;if(workerUrl)URL.revokeObjectURL(workerUrl);workerUrl=null;state.ready=false;state.loading=false;}
  async function unloadModel(){if(pending)pending.reject('Model unloaded');stopWorker();state.artifacts=null;state.progress=0;}
  async function loadManifest(){const r=await fetch(new URL('manifest.json',base));if(!r.ok)throw Error('Manifest HTTP '+r.status);return r.json();}
  async function loadModel(model,onProgress){
    if(state.loading)throw Error('Model load already running');
    if(state.ready&&state.model===model)return true;
    await unloadModel();state.loading=true;state.error=null;
    try {
      await detect();if(state.backend!=='webgpu')throw Error('WebGPU unavailable. Use a supported browser on HTTPS; existing charts remain available.');
      const manifest=await loadManifest();await ensureWorker();
      state.artifacts=await request({type:'load',model,manifest,manifestUrl:new URL('manifest.json',base).href,preprocessUrl:new URL('preprocess-module.js',base).href,persistent:cacheEnabled},onProgress,600000);
      state.model=model;state.ready=true;state.progress=1;return true;
    }catch(e){state.error=e.message;stopWorker();throw e;}finally{state.loading=false;}
  }
  async function predict(req,onStep){if(!state.ready)throw Error('Load the local model first');return request({type:'predict',job:++state.job,req},onStep,600000);}
  function cancelPredict(){if(worker)worker.postMessage({type:'cancel'});if(pending)pending.reject('Cancelled');stopWorker();}
  async function removeCache(model){
    const manifest=await loadManifest(), item=manifest.models.find(v=>v.id===model);
    if(!item)throw Error('Unknown model');
    const cache=await caches.open('kronos-local-v2');
    for(const f of item.files)await cache.delete(new URL(f.url,new URL('manifest.json',base)).href);
  }
  function setPersistentCache(enabled){cacheEnabled=!!enabled;try{localStorage.setItem('kronos-cache-opt-in',String(cacheEnabled));}catch(e){state.cacheWarning='Cache preference could not be saved for later visits';}}
  return {state,limits:{lookback:256,horizon:24,samples:1},detect,loadManifest,loadModel,predict,cancelPredict,unloadModel,removeCache,setPersistentCache,manifestUrl:()=>new URL('manifest.json',base).href};
})();
