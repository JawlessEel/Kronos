/* Named, portable presets contain settings only: never credentials or forecast data. */
const KronosPresets = (() => {
    const key='kronos-named-presets-v1';
    const ids=['model-select','device-select','live-ticker','live-interval','live-history','live-lookback','live-horizon','lookback','pred-len','temperature','top-p','sample-count'];
    const base={'model-select':'kronos-base','live-ticker':'SPY','live-interval':'5','live-history':'1000','live-lookback':'400','live-horizon':'120',lookback:'400','pred-len':'120',temperature:'0.6','top-p':'0.9','sample-count':'1'};
    const builtins=[
        {name:'SPY short horizon',controls:{...base,'live-interval':'1','live-horizon':'30'},chart:{volume:true,mas:[{type:'EMA',period:9,color:'#f59e0b'},{type:'EMA',period:21,color:'#38bdf8'}]}},
        {name:'SPY trend view',controls:base,chart:{volume:true,rsi:true,mas:[{type:'SMA',period:20,color:'#f59e0b'},{type:'EMA',period:50,color:'#38bdf8'},{type:'SMA',period:200,color:'#a78bfa'}]}},
        {name:'Compact phone view',controls:{...base,'live-history':'400','live-horizon':'60'},chart:{height:450,fontSize:12,volume:false,rsi:false,mas:[{type:'EMA',period:20,color:'#f59e0b'}]}}
    ];
    function validate(input) {
        if (!input || input.version!==1 || typeof input.name!=='string' || !input.name.trim() || input.name.length>80 || !input.controls || typeof input.controls!=='object') throw new Error('Invalid preset. Use a Kronos preset JSON file.');
        const controls={};
        for(const id of ids) if(typeof input.controls[id]==='string' && input.controls[id].length<=80) controls[id]=input.controls[id];
        return {version:1,name:input.name.trim(),controls,chart:ChartWorkbench.validateSettings(input.chart)};
    }
    let saved=[];
    function read() { const raw=JSON.parse(localStorage.getItem(key)||'[]'); if(!Array.isArray(raw) || raw.length>100) throw new Error('Preset storage is invalid.'); return raw.map(validate); }
    function write(next) { if(next.length>100) throw new Error('Maximum 100 saved presets.'); localStorage.setItem(key,JSON.stringify(next)); saved=next; }
    function snapshot(name) { return validate({version:1,name,controls:Object.fromEntries(ids.map(id=>[id,document.getElementById(id).value])),chart:ChartWorkbench.getSettings()}); }
    function apply(preset) {
        const p=validate(preset), skipped=[];
        // Model first updates context bounds before restoring forecast lengths.
        for(const id of ids) {
            if(!(id in p.controls)) continue;
            const el=document.getElementById(id), value=p.controls[id];
            if(!el || (el.tagName==='SELECT' && ![...el.options].some(o=>o.value===value && !o.disabled)) || (['number','range'].includes(el.type) && (!Number.isFinite(Number(value)) || Number(value)<Number(el.min) || Number(value)>Number(el.max)))) { skipped.push(id); continue; }
            if(el.value!==value) { el.value=value; el.dispatchEvent(new Event('input',{bubbles:true})); el.dispatchEvent(new Event('change',{bubbles:true})); }
        }
        ChartWorkbench.applySettings(p.chart);
        return skipped;
    }
    document.addEventListener('DOMContentLoaded',()=>{
        const select=document.getElementById('preset-select'), name=document.getElementById('preset-name'), status=document.getElementById('preset-status');
        const report=text=>{status.textContent=text;};
        function fill() { select.replaceChildren(); for(const [i,p] of builtins.entries()) select.add(new Option(`Built-in: ${p.name}`,`b:${i}`)); for(const [i,p] of saved.entries()) select.add(new Option(`Saved: ${p.name}`,`s:${i}`)); }
        function selected() { const [kind,i]=select.value.split(':'); return kind==='s'?saved[Number(i)]:validate({version:1,...builtins[Number(i)]}); }
        try {saved=read();} catch(error) {report(`${error.message} Existing storage was not overwritten.`);}
        fill();
        select.onchange=()=>{try{name.value=selected().name;}catch(e){report(e.message);}};
        document.getElementById('preset-apply').onclick=()=>{try {const p=selected(), skipped=apply(p); name.value=p.name; report(`Applied ${p.name}. Load the selected model and fetch candles when ready.${skipped.length?' Unavailable device or out-of-range controls kept their current values: '+skipped.join(', '):''}`);} catch(e){report(e.message);}};
        document.getElementById('preset-save').onclick=()=>{try {const p=snapshot(name.value); if(saved.some(x=>x.name===p.name)) throw new Error('That name already exists. Use Update selected or choose a new name.'); write([...saved,p]);fill();select.value=`s:${saved.length-1}`;report('Preset saved in this browser. Export it to use on another device.');}catch(e){report(e.message);}};
        document.getElementById('preset-update').onclick=()=>{try {if(!select.value.startsWith('s:')) throw new Error('Select a saved preset to update.');const i=Number(select.value.slice(2)), p=snapshot(name.value||saved[i].name);if(saved.some((x,j)=>j!==i&&x.name===p.name)) throw new Error('That name already exists.');const next=[...saved];next[i]=p;write(next);fill();select.value=`s:${i}`;report('Selected preset updated.');}catch(e){report(e.message);}};
        document.getElementById('preset-delete').onclick=()=>{try {if(!select.value.startsWith('s:')) throw new Error('Built-in presets cannot be deleted.');const i=Number(select.value.slice(2));if(!confirm(`Delete saved preset "${saved[i].name}"?`)) return;write(saved.filter((_,j)=>j!==i));fill();report('Preset deleted.');}catch(e){report(e.message);}};
        document.getElementById('preset-export').onclick=()=>{try {const p=selected(),url=URL.createObjectURL(new Blob([JSON.stringify(p,null,2)],{type:'application/json'})),link=document.createElement('a');link.href=url;link.download=`Kronos-preset-${new Date().toISOString().replace(/[:.]/g,'-')}.json`;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);report('Selected preset exported.');}catch(e){report(e.message);}};
        const file=document.getElementById('preset-file');document.getElementById('preset-import').onclick=()=>file.click();
        file.onchange=async()=>{try {const f=file.files[0];if(!f)return;if(f.size>100000)throw new Error('Preset file exceeds 100 KB.');const p=validate(JSON.parse(await f.text()));if(saved.some(x=>x.name===p.name))throw new Error('That name already exists; rename it before importing.');write([...saved,p]);fill();select.value=`s:${saved.length-1}`;name.value=p.name;report('Preset imported. Select Apply to restore its settings.');}catch(e){report(e.message);}finally{file.value='';}};
    });
    return {validate,apply,snapshot};
})();
