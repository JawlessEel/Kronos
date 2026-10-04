/* Browser-only dashboard snapshot: local libraries, no upload, unique downloads. */
document.addEventListener('DOMContentLoaded', () => {
    const button = document.getElementById('download-ui-pdf');
    const status = document.getElementById('pdf-export-status');
    let exporting = false;
    const loadScript = (source, available) => new Promise((resolve,reject) => {
        if (available()) return resolve();
        const script = document.createElement('script'); script.src=source;
        script.onload=()=>available()?resolve():reject(new Error('PDF dependency failed to initialize.'));
        script.onerror=()=>reject(new Error('Could not load the local PDF export library.'));
        document.head.append(script);
    });
    button.addEventListener('click', async () => {
        if (exporting) return;
        exporting = true; button.disabled = true;
        let clone = null;
        try {
            status.textContent='Preparing PDF snapshot...';
            await Promise.all([
                loadScript('/static/vendor/html2canvas.min.js',()=>typeof html2canvas==='function'),
                loadScript('/static/vendor/pdf-lib.min.js',()=>typeof PDFLib!=='undefined')
            ]);
            const captured = new Date();
            const charts = new Map();
            for(const id of ['live-chart','chart']) {
                const plot=document.getElementById(id);
                if(plot.data?.length) charts.set(id, await Plotly.toImage(plot,{format:'png',width:1000,height:plot.layout?.height||650,scale:2}));
            }
            const original=document.querySelector('.container');
            clone=original.cloneNode(true);
            clone.setAttribute('aria-hidden','true'); clone.inert=true;
            // Copy current control state, not the initial HTML attribute values.
            const controls=original.querySelectorAll('input,select,textarea');
            clone.querySelectorAll('input,select,textarea').forEach((control,i)=>{
                control.value=controls[i].value; control.checked=controls[i].checked;
                if(control.tagName==='SELECT') Array.from(control.options).forEach(option=>option.selected=option.value===control.value);
            });
            clone.querySelectorAll('[data-html2canvas-ignore]').forEach(node=>node.remove());
            clone.querySelectorAll('.forecast-candle-data').forEach(node=>{
                if(node.hidden) return;
                node.replaceChildren();const note=document.createElement('p');note.textContent='All predicted candle rows are included in the data pages at the end of this PDF.';node.append(note);
            });
            clone.querySelectorAll('.chart-overlay').forEach(node=>node.classList.remove('chart-overlay'));
            clone.querySelectorAll('details').forEach(node=>node.open=true);
            clone.querySelector('.main-content').style.display='block';
            clone.querySelector('.control-panel').style.setProperty('display','block','important');
            clone.querySelector('.control-panel').style.marginBottom='20px';
            clone.querySelectorAll('.chart-container').forEach(node=>node.style.padding='12px');
            clone.querySelectorAll('[style*="max-height"]').forEach(node=>{node.style.maxHeight='none';node.style.overflow='visible';});
            for(const id of ['live-chart','chart']) {
                const plot=clone.querySelector('#'+id); plot.replaceChildren(); plot.style.height='auto';
                if(charts.has(id)) {
                    const image=document.createElement('img'); image.src=charts.get(id); image.alt=id==='live-chart'?'Polygon candles and Kronos forecast':'Historical forecast comparison';
                    image.style.width='100%'; image.style.display='block'; image.dataset.pdfChart='true'; plot.append(image);
                } else { const note=document.createElement('p'); note.textContent='No chart generated at export time.'; plot.append(note); }
            }
            clone.style.cssText='position:absolute;left:-20000px;top:0;width:1000px;max-width:none;padding:20px;background:#eef2ff;color:#334155;';
            const header=clone.querySelector('.header'); header.style.color='#334155';
            const stamp=document.createElement('p'); stamp.textContent=`Captured ${captured.toLocaleString()} | ${captured.toISOString()}`; stamp.style.fontSize='14px'; header.append(stamp);
            document.body.append(clone);
            // Native input baselines are inconsistent in canvas renderers. Use
            // styled static controls only in the detached export snapshot.
            clone.querySelectorAll('input,select,textarea').forEach(control => {
                if(control.hidden || control.type==='file') { control.remove(); return; }
                const style=getComputedStyle(control);
                const box=document.createElement('div');
                box.style.cssText=`box-sizing:border-box;display:${style.display==='inline-block'?'inline-flex':'flex'};align-items:center;white-space:pre-wrap;overflow-wrap:anywhere;min-height:${Math.max(30,parseFloat(style.height)||0)}px;width:${style.width};padding:${style.padding};border:${style.border};border-radius:${style.borderRadius};background:${style.backgroundColor};color:${style.color};font:${style.font};line-height:1.4;vertical-align:middle;`;
                if(control.type==='checkbox') {
                    box.style.cssText='display:inline-flex;width:20px;height:20px;align-items:center;justify-content:center;border:1px solid #64748b;border-radius:3px;color:#334155;background:#fff;font-size:16px;line-height:1;';
                    box.textContent=control.checked?'X':'';
                } else if(control.type==='color') {
                    box.style.background=control.value;box.style.minHeight='30px';
                } else if(control.type==='range') {
                    const percentage=(Number(control.value)-Number(control.min))/(Number(control.max)-Number(control.min))*100;
                    box.style.cssText=`position:relative;display:inline-block;width:${style.width};height:24px;vertical-align:middle;`;
                    const track=document.createElement('div');track.style.cssText='position:absolute;left:0;right:0;top:10px;height:5px;border-radius:3px;background:#94a3b8;';
                    const thumb=document.createElement('div');thumb.style.cssText=`position:absolute;left:${percentage}%;top:4px;width:18px;height:18px;border-radius:50%;background:#667eea;transform:translateX(-50%);`;
                    box.append(track,thumb);
                } else {
                    box.textContent=control.tagName==='SELECT'?control.selectedOptions[0]?.textContent||control.value:control.value;
                }
                control.replaceWith(box);
            });
            await document.fonts.ready;
            await Promise.all(Array.from(clone.querySelectorAll('img')).map(image=>image.decode()));
            if(clone.scrollHeight*1000*2.25>35000000) throw new Error('Dashboard is too large to export safely. Reduce chart heights or visible table rows and retry.');
            const rect=clone.getBoundingClientRect();
            const breaks=Array.from(clone.querySelectorAll('.form-group,.chart-toolbar,.chart-settings,summary,.chart-help,h2,h3,[data-pdf-chart],tr'))
                .flatMap(node=>{const box=node.getBoundingClientRect(); return [box.top-rect.top,box.bottom-rect.top];}).filter(y=>y>0).sort((a,b)=>a-b);
            const protectedCharts=Array.from(clone.querySelectorAll('[data-pdf-chart]')).map(node=>{const box=node.getBoundingClientRect();return [box.top-rect.top,box.bottom-rect.top];});
            status.textContent='Rendering charts and controls...';
            const canvas=await html2canvas(clone,{backgroundColor:'#eef2ff',scale:1.5,logging:false,useCORS:false,scrollX:0,scrollY:0,windowWidth:1000,windowHeight:clone.scrollHeight});
            const pdf=await PDFLib.PDFDocument.create();
            pdf.setTitle('Kronos dashboard snapshot'); pdf.setCreator('Kronos Web UI'); pdf.setCreationDate(captured);
            const font=await pdf.embedFont(PDFLib.StandardFonts.Helvetica);
            const width=841.89,height=595.28,margin=22,contentWidth=width-2*margin,contentHeight=height-2*margin-25;
            const ratio=contentWidth/canvas.width, capacity=contentHeight/ratio;
            let cursor=0, pageNumber=0;
            while(cursor<canvas.height) {
                let end=Math.min(canvas.height,cursor+capacity);
                if(end<canvas.height) {
                    const candidates=breaks.map(y=>Math.floor(y*1.5)).filter(y=>y>cursor+capacity*0.5 && y<=end);
                    if(candidates.length) end=candidates[candidates.length-1];
                    for(const [start,finish] of protectedCharts) {
                        if(end>start*1.5 && end<finish*1.5 && start*1.5>cursor+10) end=Math.floor(start*1.5);
                    }
                }
                const slice=document.createElement('canvas'); slice.width=canvas.width; slice.height=Math.ceil(end-cursor);
                slice.getContext('2d').drawImage(canvas,0,cursor,canvas.width,slice.height,0,0,canvas.width,slice.height);
                const image=await pdf.embedPng(slice.toDataURL('image/png'));
                const page=pdf.addPage([width,height]);
                page.drawImage(image,{x:margin,y:height-margin-slice.height*ratio,width:contentWidth,height:slice.height*ratio});
                pageNumber++;
                page.drawText(`Kronos | ${captured.toISOString()} | Page ${pageNumber}`,{x:margin,y:12,size:9,font,color:PDFLib.rgb(.3,.35,.4)});
                cursor=end; slice.width=slice.height=0;
                if(pageNumber>100) throw new Error('PDF exceeds 100 pages. Reduce chart/table size and retry.');
            }
            canvas.width=canvas.height=0;
            // Vector tables keep every prediction row readable without creating
            // an enormous screenshot canvas for long forecast horizons.
            for(const snapshot of PredictionCandles.snapshots()) {
                let page=null,y=0;
                const widths=[25,115,55,55,55,55,55,45,65,80,95,65];
                const headings=['#',snapshot.live?'Candle start ET':'Source time','Open','High','Low','Close','Change','Change %','Move/body','Volume','Turnover','Quality'];
                const ascii=text=>String(text).replace(/[^\x20-\x7e]/g,'-');
                const drawRow=(values,header=false)=>{
                    let x=margin;
                    values.forEach((text,i)=>{
                        page.drawText(ascii(text),{x:x+3,y,size:header?8:7.5,font,color:PDFLib.rgb(.15,.2,.3),maxWidth:widths[i]-6});x+=widths[i];
                    });y-=19;
                };
                const startPage=()=>{
                    page=pdf.addPage([width,height]);pageNumber++;y=height-32;
                    page.drawText(ascii(snapshot.title),{x:margin,y,size:14,font});y-=22;
                    page.drawText('Model predictions. Change compares to preceding close; movement/body = previous close / candle open.',{x:margin,y,size:9,font});y-=24;
                    page.drawText(`Anchor close: ${Number(snapshot.anchor).toFixed(4)}. Quality flags inconsistent OHLC or negative sizes; raw outputs retained.`,{x:margin,y,size:8,font});y-=20;
                    drawRow(headings,true);
                    page.drawText(`Kronos | ${captured.toISOString()} | Page ${pageNumber}`,{x:margin,y:12,size:9,font});
                };
                for(const row of snapshot.rows) { if(!page||y<38) startPage();drawRow(PredictionCandles.cells(row)); }
            }
            const filename=`Kronos-WebUI-${captured.toISOString().replace(/[:.]/g,'-')}-${crypto.randomUUID().slice(0,8)}.pdf`;
            const url=URL.createObjectURL(new Blob([await pdf.save()],{type:'application/pdf'}));
            const link=document.createElement('a');link.href=url;link.download=filename;link.click();
            setTimeout(()=>URL.revokeObjectURL(url),60000);
            status.textContent=`Downloaded ${filename} (${pageNumber} pages).`;
        } catch(error) { status.textContent=`PDF export failed: ${error.message || 'unknown error'}`; }
        finally { clone?.remove(); exporting=false;button.disabled=false; }
    });
});
