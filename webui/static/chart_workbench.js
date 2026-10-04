/* Shared live/historical chart editor. Settings are local to this browser. */
const ChartWorkbench = (() => {
    const storageKey = 'kronos-chart-workbench-v1';
    const defaults = {
        theme:'dark', height:650, fontSize:13, type:'candlestick', gaps:false, grid:true,
        legend:true, crosshair:true, log:false, scrollZoom:true, rangeSlider:false,
        history:true, forecast:true, actual:true, volume:false, rsi:false, rsiPeriod:14,
        macd:false, fast:12, slow:26, signal:9, bollinger:false, bandPeriod:20, bandSigma:2,
        vwap:false, up:'#26a69a', down:'#ef5350', forecastUp:'#60a5fa', forecastDown:'#c084fc',
        mas:[{enabled:true,type:'SMA',period:20,source:'close',color:'#f59e0b',width:2,offset:0,dash:'solid'},
             {enabled:true,type:'EMA',period:50,source:'close',color:'#38bdf8',width:2,offset:0,dash:'solid'}]
    };
    let config = structuredClone(defaults);
    const charts = new Map();
    const clamp = (value, min, max, fallback) => Number.isFinite(Number(value)) ? Math.max(min, Math.min(max, Number(value))) : fallback;
    const color = value => /^#[\da-f]{6}$/i.test(value) ? value : '#f59e0b';
    function validated(input) {
        if (!input || typeof input !== 'object' || Array.isArray(input)) throw new Error('Invalid chart settings file.');
        const c = structuredClone(defaults);
        Object.keys(c).forEach(key => {
            if (typeof c[key] === 'boolean' && typeof input[key] === 'boolean') c[key] = input[key];
        });
        c.theme = input.theme === 'light' ? 'light' : 'dark';
        c.type = ['candlestick','line','ohlc'].includes(input.type) ? input.type : c.type;
        for (const [key,min,max] of [['height',300,1800],['fontSize',9,24],['rsiPeriod',2,500],['fast',2,500],['slow',3,1000],['signal',2,500],['bandPeriod',2,1000],['bandSigma',0.1,10]]) c[key] = clamp(input[key],min,max,c[key]);
        for (const key of ['up','down','forecastUp','forecastDown']) c[key] = color(input[key] || c[key]);
        if (Array.isArray(input.mas)) c.mas = input.mas.slice(0,30).map(ma => ({
            enabled:ma.enabled !== false, type:['SMA','EMA','WMA','RMA'].includes(ma.type) ? ma.type : 'SMA',
            period:Math.round(clamp(ma.period,1,5000,20)), source:['open','high','low','close','hl2','hlc3','ohlc4'].includes(ma.source) ? ma.source : 'close',
            color:color(ma.color), width:clamp(ma.width,1,8,2), offset:Math.round(clamp(ma.offset,-500,500,0)),
            dash:['solid','dash','dot','dashdot'].includes(ma.dash) ? ma.dash : 'solid'
        }));
        return c;
    }
    try { const stored = localStorage.getItem(storageKey); if (stored) config = validated(JSON.parse(stored)); } catch { /* Invalid saved settings reset to documented defaults. */ }
    function persist() { try { localStorage.setItem(storageKey, JSON.stringify(config)); } catch { message('Browser storage unavailable; export settings to keep this layout.'); } }
    function message(text) { charts.forEach(state => { state.workspace.querySelector('.chart-message').textContent = text; }); }
    function download(filename, content, mime) {
        const url = URL.createObjectURL(new Blob([content], {type:mime}));
        const link = document.createElement('a'); link.href = url; link.download = filename; link.click();
        setTimeout(() => URL.revokeObjectURL(url), 1000);
    }
    const field = (name,title,type='checkbox',attrs='') => `<label>${title}<input data-setting="${name}" aria-label="${title}" type="${type}" ${attrs}></label>`;
    const select = (name,title,options) => `<label>${title}<select data-setting="${name}" aria-label="${title}">${options.map(([value,text])=>`<option value="${value}">${text}</option>`).join('')}</select></label>`;
    function setup(id) {
        const plot = document.getElementById(id), workspace = plot.closest('.chart-workspace');
        const toolbar = document.createElement('div'); toolbar.className = 'chart-toolbar';
        toolbar.innerHTML = `<button data-action="expand">Expand chart</button><button data-action="fullscreen">Fullscreen</button><button data-action="reset-view">Reset zoom</button><button data-action="png">Export PNG</button><button data-action="csv">Export candles CSV</button><button data-action="save">Export settings</button><button data-action="import">Import settings</button><button data-action="defaults">Reset settings</button><input type="file" accept="application/json,.json" aria-label="Import chart settings file" hidden>`;
        const settings = document.createElement('details'); settings.className = 'chart-settings';
        settings.innerHTML = `<summary>Chart settings and indicators</summary><div class="chart-settings-grid">` +
            select('theme','Chart theme',[['dark','Dark'],['light','Light']]) + select('type','Price chart style',[['candlestick','Candles'],['line','Close line'],['ohlc','OHLC bars']]) +
            field('height','Chart height','number','min="300" max="1800" step="50"') + field('fontSize','Chart font size','number','min="9" max="24"') +
            field('gaps','Show calendar gaps') + field('grid','Show grid') + field('legend','Show legend') + field('crosshair','Crosshair') + field('log','Log price scale') + field('scrollZoom','Mouse wheel zoom') + field('rangeSlider','Time range slider') +
            field('history','Show history') + field('forecast','Show forecast') + field('actual','Show held-out actuals') + field('volume','Volume pane') +
            field('up','Rising candle color','color') + field('down','Falling candle color','color') + field('forecastUp','Rising forecast color','color') + field('forecastDown','Falling forecast color','color') +
            field('bollinger','Bollinger bands') + field('bandPeriod','Band period','number','min="2" max="1000"') + field('bandSigma','Band deviations','number','min="0.1" max="10" step="0.1"') +
            field('vwap','Session VWAP (observed only)') + field('rsi','RSI pane') + field('rsiPeriod','RSI period','number','min="2" max="500"') +
            field('macd','MACD pane') + field('fast','MACD fast period','number','min="2" max="500"') + field('slow','MACD slow period','number','min="3" max="1000"') + field('signal','MACD signal period','number','min="2" max="500"') +
            `</div><h4>Moving averages</h4><p class="chart-help">Enable · type · period · source · color · width · offset in candles · line style. Forecast-derived indicator segments are dashed. Warm-up requires a full period.</p><div class="ma-rows"></div><button data-action="add-ma">Add moving average</button><p class="chart-help">Indicators describe the displayed data; they do not change Kronos input. VWAP resets by New York session date. RSI and MACD include model-generated candles after the forecast anchor. Settings are saved in this browser and shared by both charts.</p>`;
        const feedback = document.createElement('div'); feedback.className = 'chart-message'; feedback.setAttribute('role','status');
        workspace.prepend(feedback); workspace.prepend(settings); workspace.prepend(toolbar);
        const state = {id, plot, workspace, figure:null, result:null}; charts.set(id,state);
        settings.addEventListener('change', event => {
            const control = event.target;
            if (control.dataset.setting) {
                config[control.dataset.setting] = control.type === 'checkbox' ? control.checked : control.type === 'number' ? Number(control.value) : control.value;
                config = validated(config); persist(); sync(); redraw();
            }
        });
        workspace.addEventListener('click', async event => {
            const action = event.target.dataset.action; if (!action) return;
            try {
                if (action === 'expand') { document.body.classList.toggle('chart-expanded'); sync(); resize(); }
                if (action === 'fullscreen') {
                    if (document.fullscreenElement) await document.exitFullscreen();
                    else if (workspace.classList.contains('chart-overlay')) { workspace.classList.remove('chart-overlay'); redraw(); resize(); }
                    else {
                        // The desktop in-app browser may not implement OS fullscreen.
                        // A viewport overlay remains usable there and exits with Escape.
                        workspace.classList.add('chart-overlay'); redraw(); resize();
                    }
                }
                if (action === 'reset-view') await Plotly.relayout(plot, {'xaxis.autorange':true,'yaxis.autorange':true});
                if (action === 'png') await Plotly.downloadImage(plot, {format:'png',filename:`Kronos-${id}`,width:1600,height:config.height,scale:2});
                if (action === 'csv' && state.figure) {
                    const bars = extract(state.figure);
                    download(`Kronos-${id}.csv`, 'series,timestamp,open,high,low,close,volume\n' + bars.flatMap(group=>group.bars.map(b=>[group.kind,b.timestamp,b.open,b.high,b.low,b.close,b.volume ?? ''].join(','))).join('\n'), 'text/csv');
                }
                if (action === 'save') download('Kronos-chart-settings.json',JSON.stringify(config,null,2),'application/json');
                if (action === 'import') toolbar.querySelector('input[type=file]').click();
                if (action === 'defaults') { config = structuredClone(defaults); persist(); sync(); redraw(); }
                if (action === 'add-ma') {
                    if (config.mas.length >= 30) return message('Maximum 30 moving averages per chart.');
                    config.mas.push({...defaults.mas[0],period:200}); persist(); sync(); redraw();
                }
            } catch (error) { message(error.message || 'Chart action failed.'); }
        });
        toolbar.querySelector('input[type=file]').addEventListener('change', async event => {
            const file = event.target.files[0]; if (!file) return;
            try { if (file.size > 100000) throw new Error('Settings file exceeds 100 KB.'); config = validated(JSON.parse(await file.text())); persist(); sync(); redraw(); }
            catch (error) { message(error.message); } finally { event.target.value = ''; }
        });
        sync(); return state;
    }
    function sync() {
        charts.forEach(state => {
            state.workspace.dataset.theme = config.theme;
            state.workspace.querySelector('[data-action=expand]').textContent = document.body.classList.contains('chart-expanded') ? 'Restore controls' : 'Expand chart';
            state.workspace.querySelectorAll('[data-setting]').forEach(control => {
                if (control.type === 'checkbox') control.checked = config[control.dataset.setting]; else control.value = config[control.dataset.setting];
            });
            const rows = state.workspace.querySelector('.ma-rows'); rows.replaceChildren();
            config.mas.forEach((ma,index) => {
                const row = document.createElement('div'); row.className = 'ma-row';
                for (const [key,kind,choices] of [['enabled','checkbox'],['type','select',['SMA','EMA','WMA','RMA']],['period','number'],['source','select',['open','high','low','close','hl2','hlc3','ohlc4']],['color','color'],['width','number'],['offset','number'],['dash','select',['solid','dash','dot','dashdot']]]) {
                    const control = document.createElement(kind === 'select' ? 'select' : 'input');
                    control.setAttribute('aria-label',`Moving average ${index + 1} ${key}`);
                    if (choices) choices.forEach(text=>{ const option=document.createElement('option'); option.value=option.textContent=text; control.append(option); });
                    else control.type = kind;
                    if (kind === 'checkbox') control.checked = ma[key]; else control.value = ma[key];
                    control.addEventListener('change',()=>{ ma[key] = kind === 'checkbox' ? control.checked : kind === 'number' ? Number(control.value) : control.value; config = validated(config); persist(); sync(); redraw(); });
                    row.append(control);
                }
                const remove = document.createElement('button'); remove.textContent='Remove'; remove.setAttribute('aria-label',`Remove moving average ${index+1}`);
                remove.addEventListener('click',()=>{ config.mas.splice(index,1); persist(); sync(); redraw(); }); row.append(remove); rows.append(row);
            });
        });
    }
    function extract(figure) {
        return figure.data.filter(t=>t.type === 'candlestick' || t.type === 'ohlc').map(trace=>({
            kind:/forecast|prediction/i.test(trace.name) ? 'forecast' : /actual/i.test(trace.name) ? 'actual' : 'history',
            name:trace.name, bars:Array.from(trace.x).map((timestamp,i)=>({timestamp,open:trace.open[i],high:trace.high[i],low:trace.low[i],close:trace.close[i],volume:trace.customdata?.[i]}))
        }));
    }
    function lines(traces,x,y,name,line,axis='y') { traces.push({type:'scatter',mode:'lines',x,y,name,line,connectgaps:false,yaxis:axis,hovertemplate:'%{x}<br>%{y:.4f}<extra>%{fullData.name}</extra>'}); }
    async function draw(state) {
        if (!state.figure) return;
        const groups = extract(state.figure);
        if (state.result?.candles) {
            const history = groups.find(g=>g.kind === 'history');
            if (history) history.bars = state.result.candles;
        }
        if (state.result?.prediction_results) {
            const future=groups.find(g=>g.kind === 'forecast'); if(future) future.bars=state.result.prediction_results;
        }
        const observed=groups.find(g=>g.kind==='history')?.bars || [], predicted=groups.find(g=>g.kind==='forecast')?.bars || [];
        const combined=[...observed,...predicted], x=combined.map(b=>b.timestamp), values=combined.map(b=>b.close), traces=[];
        const dark=config.theme==='dark', text=dark?'#cbd5e1':'#334155', bg=dark?'#101827':'#ffffff', grid=dark?'#334155':'#e2e8f0';
        groups.forEach(group=>{
            if (!config[group.kind]) return;
            const future=group.kind==='forecast', up=future?config.forecastUp:config.up, down=future?config.forecastDown:config.down;
            if (config.type==='line') lines(traces,group.bars.map(b=>b.timestamp),group.bars.map(b=>b.close),group.name,{color:up,width:2,dash:future?'dash':'solid'});
            else traces.push({type:config.type,x:group.bars.map(b=>b.timestamp),open:group.bars.map(b=>b.open),high:group.bars.map(b=>b.high),low:group.bars.map(b=>b.low),close:group.bars.map(b=>b.close),name:group.name,increasing:{line:{color:up}},decreasing:{line:{color:down}}});
        });
        function overlay(series,name,line,offset=0) {
            const shifted=series.map((_,i)=>series[i-offset] ?? null), cut=observed.length;
            if (config.history) lines(traces,x.slice(0,cut),shifted.slice(0,cut),name,line);
            if (config.forecast && predicted.length) {
                lines(traces,x.slice(Math.max(0,cut-1)),shifted.slice(Math.max(0,cut-1)),`${name} forecast-derived`,{...line,dash:'dash'});
                traces[traces.length-1].showlegend = false;
                traces[traces.length-1].legendgroup = name;
            }
        }
        config.mas.filter(ma=>ma.enabled).forEach(ma=>overlay(ChartMath.average(combined.map(b=>ChartMath.source(b,ma.source)),ma.period,ma.type),`${ma.type} ${ma.period} ${ma.source}`,{color:ma.color,width:ma.width,dash:ma.dash},ma.offset));
        if (config.bollinger) {
            const bb=ChartMath.bands(values,Math.round(config.bandPeriod),config.bandSigma);
            for(const [name,series] of Object.entries(bb)) overlay(series,`BB ${name} ${config.bandPeriod}`,{color:'#a78bfa',width:1});
        }
        if (config.vwap && config.history) lines(traces,observed.map(b=>b.timestamp),ChartMath.vwap(observed),'Session VWAP',{color:'#f472b6',width:2});
        const panes=[]; if(config.volume) panes.push('Volume'); if(config.rsi) panes.push('RSI'); if(config.macd) panes.push('MACD');
        const bottom=panes.length * 0.16;
        const axis={showgrid:config.grid,gridcolor:grid,zeroline:false,showspikes:config.crosshair,spikemode:'across',spikesnap:'cursor',spikecolor:text};
        const layout={paper_bgcolor:bg,plot_bgcolor:bg,font:{color:text,size:config.fontSize},autosize:true,height:document.fullscreenElement===state.workspace || state.workspace.classList.contains('chart-overlay')?Math.max(config.height,window.innerHeight-200):config.height,
            margin:{l:70,r:70,t:20,b:100},showlegend:config.legend,legend:{orientation:'h',x:0,y:-0.12,bgcolor:bg,font:{color:text}},
            hovermode:'x',dragmode:'pan',uirevision:state.id + (state.result?.feed ? `${state.result.feed.ticker}-${state.result.feed.interval_minutes}` : ''), xaxis:{...axis,type:config.gaps?'date':'category',categoryorder:'array',categoryarray:[...new Set(x)],rangeslider:{visible:config.rangeSlider},anchor:'free',position:0},
            yaxis:{...axis,title:'Price',type:config.log?'log':'linear',domain:[bottom,1],fixedrange:false}};
        // Gapless bars retain original timestamps. Explicit labels avoid category
        // axes printing every ISO timestamp or compressing the trading session.
        if (!config.gaps && x.length) {
            const unique=[...new Set(x)], stride=Math.max(1,Math.ceil(unique.length/7));
            layout.xaxis.tickvals=unique.filter((_,i)=>i%stride===0 || i===unique.length-1);
            layout.xaxis.ticktext=layout.xaxis.tickvals.map(stamp=>new Date(stamp).toLocaleString(undefined,{timeZone:state.result?.feed?'America/New_York':undefined,month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'}));
            layout.xaxis.title=state.result?.feed?'Candle start (ET)':'Candle start (source)';
        }
        panes.forEach((pane,i)=>{
            const n=i+2, key=`yaxis${n}`, axisName=`y${n}`, lower=bottom-(i+1)*0.16;
            layout[key]={...axis,title:{text:pane,font:{size:Math.min(11,config.fontSize)},standoff:4},domain:[lower+0.025,lower+0.15],anchor:'x',fixedrange:false};
            if (pane==='Volume') {
                for(const group of groups.filter(g=>g.kind!=='actual' && config[g.kind])) traces.push({type:'bar',x:group.bars.map(b=>b.timestamp),y:group.bars.map(b=>b.volume ?? null),name:group.kind==='forecast'?'Forecast volume':'Observed volume',yaxis:axisName,marker:{color:group.kind==='forecast'?config.forecastUp:config.up},opacity:0.5});
            }
            if(pane==='RSI') { lines(traces,x,ChartMath.rsi(values,Math.round(config.rsiPeriod)),`RSI ${config.rsiPeriod}`,{color:'#a78bfa',width:2},axisName); layout[key].range=[0,100]; }
            if(pane==='MACD') {
                const m=ChartMath.macd(values,Math.round(config.fast),Math.round(config.slow),Math.round(config.signal));
                lines(traces,x,m.line,'MACD',{color:'#38bdf8',width:2},axisName); lines(traces,x,m.signal,'Signal',{color:'#f59e0b',width:1},axisName);
                traces.push({type:'bar',x,y:m.histogram,name:'MACD histogram',yaxis:axisName,marker:{color:m.histogram.map(v=>v>=0?config.up:config.down)}});
            }
        });
        const legendRows=Math.ceil(traces.filter(t=>t.showlegend!==false).reduce((length,t)=>length+(t.name?.length||0)+8,0)*config.fontSize*0.6/Math.max(250,state.plot.clientWidth-100));
        layout.margin.b=config.legend?Math.min(300,60+legendRows*24):60;
        layout.newshape={line:{color:'#f59e0b',width:2}};
        await Plotly.react(state.plot,traces,layout,{responsive:true,scrollZoom:config.scrollZoom,displaylogo:false,modeBarButtonsToAdd:['drawline','drawopenpath','drawrect','eraseshape'],toImageButtonOptions:{format:'png',filename:`Kronos-${state.id}`,width:1600,height:config.height,scale:2}});
    }
    function redraw() { charts.forEach(state=>draw(state).catch(error=>message(error.message))); }
    function resize() { requestAnimationFrame(()=>charts.forEach(state=>{if(state.figure) Plotly.Plots.resize(state.plot);})); }
    document.addEventListener('fullscreenchange',()=>{redraw(); resize();});
    document.addEventListener('keydown',event=>{if(event.key==='Escape'){charts.forEach(state=>state.workspace.classList.remove('chart-overlay')); redraw(); resize();}});
    document.addEventListener('DOMContentLoaded',()=>{['live-chart','chart'].forEach(setup);});
    return {async render(id,figure,result=null) { const state=charts.get(id)||setup(id); state.figure=figure; state.result=result; await draw(state); }};
})();
