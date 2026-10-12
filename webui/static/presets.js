/* Named, portable presets contain settings only: never credentials or forecast data. */
const KronosPresets = (() => {
    const key='kronos-named-presets-v1';
    const ids=[
        'model-select','device-select','live-ticker','live-interval','live-history','live-lookback','live-horizon',
        'lookback','pred-len','temperature','top-p','sample-count',
        'lab-ticker','lab-model','lab-timeframe','lab-norm','lab-eval-mode','lab-data-source',
        'lab-lookback','lab-horizon','lab-samples','lab-window-offset','lab-companion',
        'opt-ticker','opt-strike-pct','opt-days-out',
        'bt-ticker','bt-timeframe','bt-windows','bt-horizon','bt-samples'
    ];
    const base={
        'model-select':'SPY_23yr_multi_tf','live-ticker':'SPY','live-interval':'60','live-history':'600','live-lookback':'256','live-horizon':'24',
        lookback:'256','pred-len':'24',temperature:'0.2','top-p':'0.9','sample-count':'5',
        'lab-ticker':'SPY','lab-model':'SPY_23yr_multi_tf','lab-timeframe':'1hour','lab-norm':'detrend',
        'lab-eval-mode':'held_out','lab-data-source':'local','lab-lookback':'256','lab-horizon':'24','lab-samples':'5','lab-window-offset':'1','lab-companion':'I:VIX',
        'opt-ticker':'SPY','opt-strike-pct':'12','opt-days-out':'45',
        'bt-ticker':'SPY','bt-timeframe':'1hour','bt-windows':'10','bt-horizon':'24','bt-samples':'3'
    };
    const dwColors={theme:'dark',up:'#00f5d4',down:'#ff2a85',forecastUp:'#00bbf9',forecastDown:'#d946ef'};
    const swingChart={...dwColors,volume:true,rsi:true,macd:true,mas:[
        {enabled:true,type:'EMA',period:20,source:'close',color:'#00f5d4',width:2,offset:0,dash:'solid'},
        {enabled:true,type:'EMA',period:50,source:'close',color:'#ff2a85',width:2,offset:0,dash:'solid'},
        {enabled:true,type:'SMA',period:200,source:'close',color:'#9d4edd',width:2,offset:0,dash:'dot'}
    ]};
    const scalpChart={...dwColors,volume:true,vwap:true,rsi:true,mas:[
        {enabled:true,type:'EMA',period:9,source:'close',color:'#00f5d4',width:2,offset:0,dash:'solid'},
        {enabled:true,type:'EMA',period:21,source:'close',color:'#ff2a85',width:2,offset:0,dash:'solid'}
    ]};
    const volChart={...dwColors,volume:true,bollinger:true,rsi:true,macd:true,mas:[
        {enabled:true,type:'EMA',period:20,source:'close',color:'#00f5d4',width:2,offset:0,dash:'solid'},
        {enabled:true,type:'SMA',period:50,source:'close',color:'#ffbe0b',width:2,offset:0,dash:'solid'}
    ]};

    const builtins=[
        // --- Tuned 23-Yr SPY Setups ---
        {
            name:'SPY 23-Yr + Spot VIX Confluence (1h Swing)',
            controls:{...base},
            chart:swingChart
        },
        {
            name:'SPY 23-Yr + VIXY Futures ETF Confluence (1h)',
            controls:{...base,'lab-companion':'VIXY'},
            chart:swingChart
        },
        {
            name:'SPY 23-Yr Live Forward Forecast + GEX Walls (1h)',
            controls:{...base,'lab-eval-mode':'future','lab-data-source':'live','opt-strike-pct':'10','opt-days-out':'30'},
            chart:swingChart
        },
        {
            name:'SPY 23-Yr Intraday 5m Scalper & 0DTE Options',
            controls:{
                ...base,'live-interval':'5','live-history':'500','live-horizon':'24',
                'lab-timeframe':'5min','lab-norm':'last_price_anchor','lab-companion':'I:VIX',
                'opt-strike-pct':'8','opt-days-out':'14','bt-timeframe':'5min'
            },
            chart:scalpChart
        },
        {
            name:'SPY Dedicated 5-Min Intraday Specialist (5m)',
            controls:{
                ...base,'model-select':'SPY_5min_intraday','live-interval':'5','live-history':'500','live-horizon':'24',
                'lab-model':'SPY_5min_intraday','lab-timeframe':'5min','lab-norm':'last_price_anchor','lab-companion':'VIXY',
                'opt-strike-pct':'8','opt-days-out':'14','bt-timeframe':'5min'
            },
            chart:scalpChart
        },
        {
            name:'SPY 23-Yr Daily Macro Position & LEAPS (1d)',
            controls:{
                ...base,'live-interval':'1440','live-history':'400','live-horizon':'20','pred-len':'20',
                'lab-timeframe':'1day','lab-norm':'detrend','lab-horizon':'20','lab-companion':'I:VIX',
                'opt-strike-pct':'20','opt-days-out':'90','bt-timeframe':'1day','bt-horizon':'20'
            },
            chart:swingChart
        },
        {
            name:'SPY 20-Yr Pre-2025 Legacy Benchmark (1h)',
            controls:{
                ...base,'model-select':'SPY_20yr_multi_timeframe','lab-model':'SPY_20yr_multi_timeframe',
                'lab-timeframe':'1hour','lab-norm':'detrend'
            },
            chart:swingChart
        },

        // --- Tuned 23-Yr QQQ Setups ---
        {
            name:'QQQ 23-Yr Nasdaq Tech Momentum + VIX Confluence (1h)',
            controls:{
                ...base,'model-select':'QQQ_23yr_multi_tf','live-ticker':'QQQ',
                'lab-ticker':'QQQ','lab-model':'QQQ_23yr_multi_tf','lab-timeframe':'1hour','lab-norm':'detrend','lab-companion':'I:VIX',
                'opt-ticker':'QQQ','opt-strike-pct':'12','opt-days-out':'45',
                'bt-ticker':'QQQ','bt-timeframe':'1hour'
            },
            chart:swingChart
        },
        {
            name:'QQQ 23-Yr Intraday 15m Tech Breakout & GEX',
            controls:{
                ...base,'model-select':'QQQ_23yr_multi_tf','live-ticker':'QQQ','live-interval':'15',
                'lab-ticker':'QQQ','lab-model':'QQQ_23yr_multi_tf','lab-timeframe':'15min','lab-norm':'detrend','lab-companion':'VIXY',
                'opt-ticker':'QQQ','opt-strike-pct':'10','opt-days-out':'21',
                'bt-ticker':'QQQ','bt-timeframe':'15min'
            },
            chart:scalpChart
        },

        // --- Tuned 23-Yr IWM Setups ---
        {
            name:'IWM 23-Yr Small-Cap Rotation + VIX Confluence (1h)',
            controls:{
                ...base,'model-select':'IWM_23yr_multi_tf','live-ticker':'IWM',
                'lab-ticker':'IWM','lab-model':'IWM_23yr_multi_tf','lab-timeframe':'1hour','lab-norm':'detrend','lab-companion':'I:VIX',
                'opt-ticker':'IWM','opt-strike-pct':'12','opt-days-out':'45',
                'bt-ticker':'IWM','bt-timeframe':'1hour'
            },
            chart:swingChart
        },
        {
            name:'IWM 23-Yr Daily Mean-Reversion & Bollinger (1d)',
            controls:{
                ...base,'model-select':'IWM_23yr_multi_tf','live-ticker':'IWM','live-interval':'1440','live-horizon':'20','pred-len':'20',
                'lab-ticker':'IWM','lab-model':'IWM_23yr_multi_tf','lab-timeframe':'1day','lab-norm':'standard','lab-horizon':'20','lab-companion':'I:VIX',
                'opt-ticker':'IWM','opt-strike-pct':'15','opt-days-out':'60',
                'bt-ticker':'IWM','bt-timeframe':'1day','bt-horizon':'20'
            },
            chart:volChart
        },

        // --- Tuned 23-Yr NVDA Setups ---
        {
            name:'NVDA 23-Yr AI Semiconductor Bellwether (1h Swing)',
            controls:{
                ...base,'model-select':'NVDA_23yr_multi_tf','live-ticker':'NVDA',
                'lab-ticker':'NVDA','lab-model':'NVDA_23yr_multi_tf','lab-timeframe':'1hour','lab-norm':'standard','lab-companion':'I:VIX',
                'opt-ticker':'NVDA','opt-strike-pct':'18','opt-days-out':'45',
                'bt-ticker':'NVDA','bt-timeframe':'1hour'
            },
            chart:volChart
        },
        {
            name:'NVDA 23-Yr Intraday 5m Momentum & Options Gamma',
            controls:{
                ...base,'model-select':'NVDA_23yr_multi_tf','live-ticker':'NVDA','live-interval':'5',
                'lab-ticker':'NVDA','lab-model':'NVDA_23yr_multi_tf','lab-timeframe':'5min','lab-norm':'last_price_anchor','lab-companion':'VIXY',
                'opt-ticker':'NVDA','opt-strike-pct':'12','opt-days-out':'14',
                'bt-ticker':'NVDA','bt-timeframe':'5min'
            },
            chart:scalpChart
        },

        // --- Tuned 23-Yr GME Setup ---
        {
            name:'GME 23-Yr Volatility Squeeze & High-IV Options (1h)',
            controls:{
                ...base,'model-select':'GME_23yr_multi_tf','live-ticker':'GME',
                'lab-ticker':'GME','lab-model':'GME_23yr_multi_tf','lab-timeframe':'1hour','lab-norm':'last_price_anchor','lab-companion':'UVXY',
                'opt-ticker':'GME','opt-strike-pct':'25','opt-days-out':'45',
                'bt-ticker':'GME','bt-timeframe':'1hour'
            },
            chart:volChart
        },

        // --- Tuned 23-Yr Macro Rates & Gold (TLT & GLD) ---
        {
            name:'TLT 23-Yr Treasury Bond Rates Macro Companion (1h)',
            controls:{
                ...base,'model-select':'MACRO_TLT_GLD_23yr_multi_tf','live-ticker':'TLT',
                'lab-ticker':'TLT','lab-model':'MACRO_TLT_GLD_23yr_multi_tf','lab-timeframe':'1hour','lab-norm':'standard','lab-companion':'I:VIX',
                'opt-ticker':'TLT','opt-strike-pct':'10','opt-days-out':'60',
                'bt-ticker':'TLT','bt-timeframe':'1hour'
            },
            chart:swingChart
        },
        {
            name:'GLD 23-Yr Gold Safe-Haven & Macro Hedge (1h)',
            controls:{
                ...base,'model-select':'MACRO_TLT_GLD_23yr_multi_tf','live-ticker':'GLD',
                'lab-ticker':'GLD','lab-model':'MACRO_TLT_GLD_23yr_multi_tf','lab-timeframe':'1hour','lab-norm':'last_price_anchor','lab-companion':'I:VIX',
                'opt-ticker':'GLD','opt-strike-pct':'12','opt-days-out':'60',
                'bt-ticker':'GLD','bt-timeframe':'1hour'
            },
            chart:swingChart
        },

        // --- Tuned VIX Volatility Companion Setups (I:VIX, VIXY, UVXY) ---
        {
            name:'VIX Spot (I:VIX) Volatility Regime Forecast (1h)',
            controls:{
                ...base,'model-select':'VIX_companion_multi_tf','live-ticker':'I:VIX',
                'lab-ticker':'I:VIX','lab-model':'VIX_companion_multi_tf','lab-timeframe':'1hour','lab-norm':'standard','lab-companion':'VIXY',
                'opt-ticker':'VIXY','opt-strike-pct':'20','opt-days-out':'30',
                'bt-ticker':'VIXY','bt-timeframe':'1hour'
            },
            chart:volChart
        },
        {
            name:'VIXY Short-Term VIX Futures ETP Hedge (15m)',
            controls:{
                ...base,'model-select':'VIX_companion_multi_tf','live-ticker':'VIXY','live-interval':'15',
                'lab-ticker':'VIXY','lab-model':'VIX_companion_multi_tf','lab-timeframe':'15min','lab-norm':'standard','lab-companion':'I:VIX',
                'opt-ticker':'VIXY','opt-strike-pct':'20','opt-days-out':'30',
                'bt-ticker':'VIXY','bt-timeframe':'15min'
            },
            chart:volChart
        },
        {
            name:'UVXY 1.5x Leveraged Volatility Spike Detector (5m)',
            controls:{
                ...base,'model-select':'VIX_companion_multi_tf','live-ticker':'UVXY','live-interval':'5',
                'lab-ticker':'UVXY','lab-model':'VIX_companion_multi_tf','lab-timeframe':'5min','lab-norm':'last_price_anchor','lab-companion':'I:VIX',
                'opt-ticker':'UVXY','opt-strike-pct':'25','opt-days-out':'21',
                'bt-ticker':'VIXY','bt-timeframe':'5min'
            },
            chart:scalpChart
        },

        // --- Classic Base / Crypto / Display Presets ---
        {name:'Bitcoin 1 hour',controls:{...base,'model-select':'kronos-base','live-ticker':'X:BTCUSD','live-interval':'60','live-history':'400','live-horizon':'24'},chart:{...dwColors,volume:true,mas:[{type:'EMA',period:20,color:'#00f5d4'},{type:'EMA',period:50,color:'#ff2a85'}]}},
        {name:'Bitcoin 4 hours',controls:{...base,'model-select':'kronos-base','live-ticker':'X:BTCUSD','live-interval':'240','live-history':'400','live-horizon':'30'},chart:{...dwColors,volume:true}},
        {name:'Ethereum daily',controls:{...base,'model-select':'kronos-base','live-ticker':'X:ETHUSD','live-interval':'1440','live-history':'400','live-horizon':'30'},chart:{...dwColors,volume:true}},
        {name:'SPY short horizon',controls:{...base,'live-interval':'1','live-horizon':'30'},chart:scalpChart},
        {name:'SPY trend view',controls:base,chart:swingChart},
        {name:'Compact phone view',controls:{...base,'live-history':'400','live-horizon':'60'},chart:{...dwColors,height:450,fontSize:12,volume:false,rsi:false,mas:[{type:'EMA',period:20,color:'#00f5d4'}]}}
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
    function snapshot(name) {
        const controls=Object.fromEntries(ids.flatMap(id=>{
            const el=document.getElementById(id);
            return el && typeof el.value==='string' ? [[id,el.value]] : [];
        }));
        return validate({version:1,name,controls,chart:ChartWorkbench.getSettings()});
    }
    function syncCompanionUi(controls) {
        if (typeof document.querySelectorAll === 'function' && controls['lab-ticker']) {
            document.querySelectorAll('.ticker-pill').forEach(btn => {
                btn.classList.toggle('active', btn.dataset.ticker === controls['lab-ticker']);
            });
        }
        const fileSelect = document.getElementById('data-file-select');
        if (fileSelect && fileSelect.options && controls['lab-ticker'] && controls['lab-timeframe']) {
            const sym = controls['lab-ticker'].replace('I:VIX', 'VIX_INDEX');
            const tfFolder = `${controls['lab-timeframe']}_bars`;
            const match = [...fileSelect.options].find(o => o.value && o.value.includes(tfFolder) && o.value.includes(`/${sym}_`));
            if (match && fileSelect.value !== match.value) {
                fileSelect.value = match.value;
                fileSelect.dispatchEvent(new Event('change', {bubbles:true}));
            }
        }
    }
    function apply(preset) {
        const p=validate(preset), skipped=[];
        // Model first updates context bounds before restoring forecast lengths.
        for(const id of ids) {
            if(!(id in p.controls)) continue;
            const el=document.getElementById(id), value=p.controls[id];
            if(!el || (el.tagName==='SELECT' && ![...el.options].some(o=>o.value===value && !o.disabled)) || (['number','range'].includes(el.type) && (!Number.isFinite(Number(value)) || Number(value)<Number(el.min) || Number(value)>Number(el.max)))) { skipped.push(id); continue; }
            if(el.value!==value) { el.value=value; el.dispatchEvent(new Event('input',{bubbles:true})); el.dispatchEvent(new Event('change',{bubbles:true})); }
        }
        syncCompanionUi(p.controls);
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
        if (builtins.length) name.value = builtins[0].name;
        select.onchange=()=>{try{name.value=selected().name;}catch(e){report(e.message);}};
        document.getElementById('preset-apply').onclick=()=>{try {const p=selected(), skipped=apply(p); name.value=p.name; report(`Applied "${p.name}" across Testing Lab, Options Chain, Walk-Forward Backtester, Control Panel, and Darkwave Charts.${skipped.length?' Unavailable controls kept current values: '+skipped.join(', '):''}`);} catch(e){report(e.message);}};
        document.getElementById('preset-save').onclick=()=>{try {const p=snapshot(name.value); if(saved.some(x=>x.name===p.name)) throw new Error('That name already exists. Use Update selected or choose a new name.'); write([...saved,p]);fill();select.value=`s:${saved.length-1}`;report('Preset saved in this browser. Export it to use on another device.');}catch(e){report(e.message);}};
        document.getElementById('preset-update').onclick=()=>{try {if(!select.value.startsWith('s:')) throw new Error('Select a saved preset to update.');const i=Number(select.value.slice(2)), p=snapshot(name.value||saved[i].name);if(saved.some((x,j)=>j!==i&&x.name===p.name)) throw new Error('That name already exists.');const next=[...saved];next[i]=p;write(next);fill();select.value=`s:${i}`;report('Selected preset updated.');}catch(e){report(e.message);}};
        document.getElementById('preset-delete').onclick=()=>{try {if(!select.value.startsWith('s:')) throw new Error('Built-in presets cannot be deleted.');const i=Number(select.value.slice(2));if(!confirm(`Delete saved preset "${saved[i].name}"?`)) return;write(saved.filter((_,j)=>j!==i));fill();report('Preset deleted.');}catch(e){report(e.message);}};
        document.getElementById('preset-export').onclick=()=>{try {const p=selected(),url=URL.createObjectURL(new Blob([JSON.stringify(p,null,2)],{type:'application/json'})),link=document.createElement('a');link.href=url;link.download=`Kronos-preset-${new Date().toISOString().replace(/[:.]/g,'-')}.json`;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);report('Selected preset exported.');}catch(e){report(e.message);}};
        const file=document.getElementById('preset-file');document.getElementById('preset-import').onclick=()=>file.click();
        file.onchange=async()=>{try {const f=file.files[0];if(!f)return;if(f.size>100000)throw new Error('Preset file exceeds 100 KB.');const p=validate(JSON.parse(await f.text()));if(saved.some(x=>x.name===p.name))throw new Error('That name already exists; rename it before importing.');write([...saved,p]);fill();select.value=`s:${saved.length-1}`;name.value=p.name;report('Preset imported. Select Apply to restore its settings.');}catch(e){report(e.message);}finally{file.value='';}};
    });
    return {validate,apply,snapshot,builtins};
})();

