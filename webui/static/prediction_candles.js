/* Predicted movements are derived from model output, never future observations. */
(function(root) {
    const snapshots = new Map();
    const number = (value,digits=4) => Number.isFinite(value) ? value.toLocaleString('en-US',{minimumFractionDigits:digits,maximumFractionDigits:digits}) : '—';
    function time(timestamp, live) {
        if (!live) return timestamp.replace('T',' ').slice(0,19);
        const parts=new Intl.DateTimeFormat('en-US',{timeZone:'America/New_York',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hourCycle:'h23',timeZoneName:'short'}).formatToParts(new Date(timestamp));
        const p=Object.fromEntries(parts.map(item=>[item.type,item.value]));
        return `${p.year}-${p.month}-${p.day} ${p.hour}:${p.minute} ${p.timeZoneName}`;
    }
    function rowsFor(bars, anchor, live) {
        let previous=anchor;
        return bars.map((bar,index)=>{
            const change=Number.isFinite(previous)?bar.close-previous:null;
            const percent=Number.isFinite(previous)&&previous!==0?100*change/previous:null;
            const movement=change===null?'Unknown':change>0?'Up':change<0?'Down':'Flat';
            const body=bar.close>bar.open?'Up':bar.close<bar.open?'Down':'Flat';
            const quality=bar.high<Math.max(bar.open,bar.close) || bar.low>Math.min(bar.open,bar.close) || bar.high<bar.low ? 'OHLC bounds' : bar.volume<0 || bar.amount<0 ? 'Negative size' : 'OK';
            const row={index:index+1,timestamp:bar.timestamp,time:time(bar.timestamp,live),open:bar.open,high:bar.high,low:bar.low,close:bar.close,change,percent,movement,body,volume:bar.volume,amount:bar.amount,quality};
            previous=bar.close;return row;
        });
    }
    const cells=row=>[String(row.index),row.time,number(row.open),number(row.high),number(row.low),number(row.close),number(row.change),Number.isFinite(row.percent)?number(Math.abs(row.percent)<.005?0:row.percent,2)+'%':'—',row.movement+'/'+row.body,number(row.volume,2),number(row.amount,2),row.quality];
    function render(id,result) {
        const section=document.getElementById(id), bars=result.prediction_results||[];
        if(!bars.length) { section.hidden=true;snapshots.delete(id);return; }
        const live=!!result.feed;
        let anchor=result.feed?.last_close;
        if(!Number.isFinite(anchor)) {
            const history=JSON.parse(result.chart).data.find(trace=>/historical/i.test(trace.name));
            anchor=history?.close?.[history.close.length-1];
        }
        const rows=rowsFor(bars,anchor,live);
        const flagged=rows.filter(row=>row.quality!=='OK').length;
        const title=live?`${result.feed.ticker} predicted candles (${result.feed.interval_minutes}-minute)`:'Historical model-predicted candles';
        snapshots.set(id,{id,title,rows,live,anchor});section.hidden=false;section.replaceChildren();
        const heading=document.createElement('h3');heading.textContent=title;
        const note=document.createElement('p');note.className='chart-help';
        note.textContent=`${rows.length} predicted candles. ${live?'Times are candle starts in New York (ET).':'Times retain the source CSV timestamps.'} Close change compares with the preceding close; row 1 starts from ${number(anchor)}. Movement/body means change from prior close / change from this candle's open. Volume and turnover are model estimates.`;
        if(flagged) note.textContent+=` ${flagged} ${flagged===1?'row violates':'rows violate'} OHLC/size constraints; raw model values are preserved and flagged in Quality.`;
        const summary=document.createElement('p');summary.className='forecast-summary';
        summary.textContent=`First: ${rows[0].time} · Last: ${rows.at(-1).time} · Final predicted close: ${number(rows.at(-1).close)} · Change from anchor: ${number(rows.at(-1).close-anchor)}`;
        const exportButton=document.createElement('button');exportButton.type='button';exportButton.textContent='Download predicted candles CSV';
        exportButton.addEventListener('click',()=>{
            const header='row,timestamp,open,high,low,close,close_change,close_change_percent,movement,body,volume,amount,quality';
            const csv=header+'\n'+rows.map(row=>[row.index,row.timestamp,row.open,row.high,row.low,row.close,row.change,row.percent,row.movement,row.body,row.volume,row.amount,row.quality].join(',')).join('\n');
            const url=URL.createObjectURL(new Blob([csv],{type:'text/csv'}));const link=document.createElement('a');link.href=url;link.download=`Kronos-predicted-candles-${new Date().toISOString().replace(/[:.]/g,'-')}.csv`;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
        });
        const scroll=document.createElement('div');scroll.className='forecast-table-scroll';
        const table=document.createElement('table');table.className='forecast-candle-table';
        const head=document.createElement('thead');const header=document.createElement('tr');
        ['#',live?'Candle start (ET)':'Candle start (source)','Open','High','Low','Close','Close change','Change %','Move/body','Volume','Turnover','Quality'].forEach(name=>{const th=document.createElement('th');th.textContent=name;header.append(th);});head.append(header);
        const body=document.createElement('tbody');
        rows.forEach(row=>{const tr=document.createElement('tr');cells(row).forEach((value,index)=>{const td=document.createElement('td');td.textContent=value;if(index>=6&&index<=8) td.className=row.movement==='Up'?'movement-up':row.movement==='Down'?'movement-down':'';tr.append(td);});body.append(tr);});
        table.append(head,body);scroll.append(table);section.append(heading,note,summary,exportButton,scroll);
    }
    root.PredictionCandles={render,snapshots:()=>Array.from(snapshots.values()),rowsFor,cells};
    if(typeof module!=='undefined') module.exports=root.PredictionCandles;
})(typeof window!=='undefined'?window:globalThis);
