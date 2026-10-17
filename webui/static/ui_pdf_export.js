/* Browser-only dashboard snapshot: single continuous scrolling page for phone & desktop screens. */
document.addEventListener('DOMContentLoaded', () => {
    const button = document.getElementById('download-ui-pdf');
    const status = document.getElementById('pdf-export-status');
    let exporting = false;
    const loadScript = (source, available) => new Promise((resolve, reject) => {
        if (available()) return resolve();
        const script = document.createElement('script');
        script.src = source;
        script.onload = () => available() ? resolve() : reject(new Error('PDF dependency failed to initialize.'));
        script.onerror = () => reject(new Error('Could not load the local PDF export library.'));
        document.head.append(script);
    });

    button.addEventListener('click', async () => {
        if (exporting) return;
        exporting = true;
        button.disabled = true;
        let clone = null;
        try {
            status.textContent = 'Preparing continuous-scroll Darkwave PDF...';
            await Promise.all([
                loadScript('/static/vendor/html2canvas.min.js', () => typeof html2canvas === 'function'),
                loadScript('/static/vendor/pdf-lib.min.js', () => typeof PDFLib !== 'undefined')
            ]);
            const captured = new Date();

            // 1. Rasterize all active Plotly charts at high resolution with proper width so legends/bars never clip
            const chartSpecs = [
                { id: 'lab-chart-container', width: 1240, height: 540, alt: 'Tuned Model & VIX Confluence Forecast' },
                { id: 'bt-chart-container', width: 1240, height: 480, alt: 'Walk-Forward Backtest Evaluation' },
                { id: 'opt-oi-gex-chart', width: 1240, height: 560, alt: 'Options Open Interest & Dealer GEX' },
                { id: 'opt-iv-smile-chart', width: 1240, height: 560, alt: 'Options Implied Volatility Smile' },
                { id: 'live-chart', width: 1240, height: 560, alt: 'Polygon Live Candles and Kronos Forecast' },
                { id: 'chart', width: 1240, height: 560, alt: 'Historical Forecast Comparison' },
                { id: 'chart-daily-macro', width: 1240, height: 460, alt: 'Daily Macro Timeframe (1D) — 50-Day SMA & Daily ATR Budget' },
                { id: 'chart-intraday-5m', width: 1240, height: 540, alt: 'Intraday Execution Timeframe (5M) — 4 Liquidity Levels & Kronos Forecast' }
            ];
            const charts = new Map();
            for (const spec of chartSpecs) {
                const plot = document.getElementById(spec.id);
                if (plot && Array.isArray(plot.data) && plot.data.length > 0) {
                    const panel = plot.closest('.hub-tab-panel');
                    if (panel && panel.hidden) continue;
                    const h = plot.layout?.height || spec.height;
                    const imgData = await Plotly.toImage(plot, {
                        format: 'png',
                        width: spec.width,
                        height: h,
                        scale: 2
                    });
                    charts.set(spec.id, { src: imgData, alt: spec.alt });
                }
            }

            const original = document.querySelector('.container, .three-r-container');
            if (!original) {
                throw new Error('Could not locate dashboard container to export.');
            }
            const isThreeR = original.classList.contains('three-r-container');
            clone = original.cloneNode(true);
            clone.classList.add('pdf-export-clone');
            clone.setAttribute('aria-hidden', 'true');
            clone.inert = true;

            // 2. Copy current control values into the cloned DOM
            const controls = original.querySelectorAll('input,select,textarea');
            clone.querySelectorAll('input,select,textarea').forEach((control, i) => {
                if (!controls[i]) return;
                control.value = controls[i].value;
                control.checked = controls[i].checked;
                if (control.tagName === 'SELECT') {
                    Array.from(control.options).forEach(option => {
                        option.selected = option.value === control.value;
                    });
                }
            });

            // 3. Remove ignored elements & interactive-only action buttons
            clone.querySelectorAll('[data-html2canvas-ignore]').forEach(node => node.remove());
            clone.querySelectorAll('.chart-overlay').forEach(node => node.classList.remove('chart-overlay'));
            clone.querySelectorAll([
                '.chart-toolbar',
                '.tv-chart-toolbar',
                '.preset-actions',
                '#load-model-btn',
                '#load-data-btn',
                '#predict-btn',
                '#live-fetch',
                '#live-refresh',
                '#live-predict',
                '#lab-run-btn',
                '#lab-run-all-spy-btn',
                '#opt-fetch-btn',
                '#bt-run-btn',
                '#pg-refresh-btn',
                '.lab-actions',
                '.ctrl-action',
                '[id="3r-run-btn"]'
            ].join(',')).forEach(node => node.remove());

            // Keep <details> closed unless the user explicitly opened them on screen
            const origDetails = original.querySelectorAll('details');
            clone.querySelectorAll('details').forEach((node, idx) => {
                if (!origDetails[idx] || !origDetails[idx].open) {
                    node.remove();
                } else {
                    node.open = true;
                }
            });

            // Remove the interactive-only "Quick Action" / "Load Chart" column in tables
            const scoreTable = clone.querySelector('#models-scoreboard-table');
            if (scoreTable) {
                scoreTable.querySelectorAll('tr').forEach(tr => {
                    if (tr.children.length >= 10) tr.lastElementChild.remove();
                });
            }
            const spyMatrixTable = clone.querySelector('#spy-setups-matrix-table');
            if (spyMatrixTable) {
                spyMatrixTable.querySelectorAll('tr').forEach(tr => {
                    if (tr.children.length >= 13) tr.lastElementChild.remove();
                });
            }

            // Expand any visible forecast candle table in-place so it scrolls naturally on the single page
            clone.querySelectorAll('[style*="max-height"]').forEach(node => {
                node.style.maxHeight = 'none';
                node.style.overflow = 'visible';
            });

            // 4. Replace Plotly containers with crisp high-DPI images (or compact empty state)
            for (const spec of chartSpecs) {
                const plot = clone.querySelector(`[id="${spec.id}"]`);
                if (!plot) continue;
                plot.replaceChildren();
                plot.style.height = 'auto';
                plot.style.minHeight = '0';
                if (charts.has(spec.id)) {
                    const info = charts.get(spec.id);
                    const image = document.createElement('img');
                    image.src = info.src;
                    image.alt = info.alt;
                    image.style.cssText = 'width:100%;height:auto;display:block;border-radius:10px;border:1px solid rgba(0,245,212,0.28);';
                    image.dataset.pdfChart = 'true';
                    plot.append(image);
                } else if (spec.id === 'live-chart' || spec.id === 'chart') {
                    const workspace = plot.closest('.chart-workspace') || plot;
                    workspace.replaceChildren();
                    const note = document.createElement('div');
                    note.textContent = spec.id === 'live-chart'
                        ? 'Live Polygon chart not active at snapshot time.'
                        : 'Historical file comparison chart not active at snapshot time.';
                    note.style.cssText = 'padding:10px 14px;border-radius:8px;background:rgba(8,10,20,0.65);border:1px solid rgba(148,163,184,0.16);color:#94a3b8;font-size:12px;';
                    workspace.append(note);
                } else if (spec.id === 'chart-daily-macro' || spec.id === 'chart-intraday-5m') {
                    const note = document.createElement('div');
                    note.textContent = spec.id === 'chart-daily-macro'
                        ? 'Daily Macro (1D) chart not active at snapshot time.'
                        : 'Intraday Execution (5M) chart not active at snapshot time.';
                    note.style.cssText = 'padding:10px 14px;border-radius:8px;background:rgba(8,10,20,0.65);border:1px solid rgba(148,163,184,0.16);color:#94a3b8;font-size:12px;';
                    plot.append(note);
                } else {
                    plot.remove();
                }
            }

            // 5. Inject dedicated PDF export stylesheet into the clone
            const pdfStyle = document.createElement('style');
            pdfStyle.textContent = `
                .pdf-export-clone {
                    position: absolute !important;
                    left: -20000px !important;
                    top: 0 !important;
                    width: 1320px !important;
                    max-width: 1320px !important;
                    padding: 28px !important;
                    background: #07080f !important;
                    color: #f0f6fc !important;
                    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif !important;
                }
                .pdf-export-clone *,
                .pdf-export-clone *::before,
                .pdf-export-clone *::after {
                    backdrop-filter: none !important;
                    -webkit-backdrop-filter: none !important;
                    box-shadow: none !important;
                    content-visibility: visible !important;
                    contain-intrinsic-size: none !important;
                    contain: none !important;
                    container-type: normal !important;
                }
                /* Fix html2canvas background-clip:text bug */
                .pdf-export-clone .header h1,
                .pdf-export-clone .testing-hub-header h2,
                .pdf-export-clone .control-panel h2,
                .pdf-export-clone .chart-container h2,
                .pdf-export-clone .hub-section-block h3,
                .pdf-export-clone .preset-panel h3,
                .pdf-export-clone section[aria-label="Polygon live feed"] h3 {
                    background: transparent !important;
                    background-image: none !important;
                    -webkit-background-clip: initial !important;
                    background-clip: initial !important;
                    -webkit-text-fill-color: #00f5d4 !important;
                    color: #00f5d4 !important;
                    text-shadow: none !important;
                }
                .pdf-export-clone .header {
                    background: #0d101d !important;
                    border: 1px solid rgba(0, 245, 212, 0.35) !important;
                    border-radius: 14px !important;
                    padding: 18px 24px !important;
                    margin-bottom: 20px !important;
                    text-align: left !important;
                }
                .pdf-export-clone .header h1 {
                    font-size: 24px !important;
                    margin: 0 0 6px 0 !important;
                }
                .pdf-export-clone .header p {
                    color: #cbd5e1 !important;
                    font-size: 13px !important;
                    margin: 2px 0 !important;
                }
                /* Align all Testing Lab fields cleanly along their top labels */
                .pdf-export-clone .lab-controls-grid {
                    display: grid !important;
                    grid-template-columns: repeat(5, minmax(0, 1fr)) !important;
                    gap: 12px 14px !important;
                    align-items: start !important;
                }
                .pdf-export-clone .lab-field {
                    display: flex !important;
                    flex-direction: column !important;
                    justify-content: flex-start !important;
                }
                .pdf-export-clone .hub-kpi-card .kpi-val {
                    background: transparent !important;
                    background-image: none !important;
                    -webkit-background-clip: initial !important;
                    background-clip: initial !important;
                    -webkit-text-fill-color: #f8fafc !important;
                    color: #f8fafc !important;
                }
                .pdf-export-clone .hub-kpi-card .kpi-val.kpi-up {
                    -webkit-text-fill-color: #00f5d4 !important;
                    color: #00f5d4 !important;
                }
                .pdf-export-clone .hub-kpi-card .kpi-val.kpi-down {
                    -webkit-text-fill-color: #ff2a85 !important;
                    color: #ff2a85 !important;
                }
                .pdf-export-clone .hub-kpi-card .kpi-val.kpi-warn {
                    -webkit-text-fill-color: #ffbe0b !important;
                    color: #ffbe0b !important;
                }
                /* Prevent section blocks and tables from clipping or overlapping subsequent sections */
                .pdf-export-clone .hub-section-block {
                    display: block !important;
                    position: relative !important;
                    clear: both !important;
                    height: auto !important;
                    min-height: 0 !important;
                    max-height: none !important;
                    max-block-size: none !important;
                    overflow: visible !important;
                    margin-top: 24px !important;
                    margin-bottom: 24px !important;
                }
                /* Ensure tables fit 100% horizontally & vertically without clipping or overlapping */
                .pdf-export-clone .table-wrapper,
                .pdf-export-clone .table-scroll-wrap,
                .pdf-export-clone .forecast-candle-scroll,
                .pdf-export-clone .forecast-table-scroll {
                    overflow: visible !important;
                    max-height: none !important;
                    max-block-size: none !important;
                    height: auto !important;
                    block-size: auto !important;
                    width: 100% !important;
                    border: 1px solid rgba(0, 245, 212, 0.25) !important;
                    border-radius: 10px !important;
                    margin-bottom: 18px !important;
                }
                .pdf-export-clone .hub-table thead,
                .pdf-export-clone .hub-table tbody th {
                    position: static !important;
                }
                .pdf-export-clone .hub-table,
                .pdf-export-clone .comparison-table,
                .pdf-export-clone .scaling-matrix-table,
                .pdf-export-clone .forecast-candle-table {
                    width: 100% !important;
                    table-layout: auto !important;
                    border-collapse: collapse !important;
                    font-size: 11.5px !important;
                }
                .pdf-export-clone .hub-table th,
                .pdf-export-clone .hub-table td,
                .pdf-export-clone .comparison-table th,
                .pdf-export-clone .comparison-table td,
                .pdf-export-clone .scaling-matrix-table th,
                .pdf-export-clone .scaling-matrix-table td,
                .pdf-export-clone .forecast-candle-table th,
                .pdf-export-clone .forecast-candle-table td {
                    padding: 7px 9px !important;
                    white-space: normal !important;
                    word-break: break-word !important;
                    line-height: 1.35 !important;
                    color: #e2e8f0 !important;
                }
                .pdf-export-clone .hub-table th,
                .pdf-export-clone .scaling-matrix-table th,
                .pdf-export-clone .forecast-candle-table th {
                    background: #13182e !important;
                    color: #00f5d4 !important;
                    font-size: 10.5px !important;
                }
                /* Organize Control Panel & Polygon Live Feed into clean, balanced multi-column grids */
                .pdf-export-clone .main-content {
                    display: block !important;
                }
                .pdf-export-clone .control-panel {
                    display: grid !important;
                    grid-template-columns: repeat(3, minmax(0, 1fr)) !important;
                    gap: 14px 18px !important;
                    align-items: start !important;
                    padding: 20px 22px !important;
                    margin-bottom: 18px !important;
                    background: #0d101d !important;
                    border: 1px solid rgba(0, 245, 212, 0.25) !important;
                    border-radius: 14px !important;
                }
                .pdf-export-clone .control-panel > h2,
                .pdf-export-clone .control-panel > hr,
                .pdf-export-clone .control-panel > .preset-panel,
                .pdf-export-clone .control-panel > section[aria-label="Polygon live feed"],
                .pdf-export-clone .control-panel > .data-info,
                .pdf-export-clone .control-panel > .time-window-container,
                .pdf-export-clone .control-panel > .status {
                    grid-column: 1 / -1 !important;
                }
                .pdf-export-clone .time-window-info {
                    display: flex !important;
                    flex-wrap: wrap !important;
                    gap: 8px 18px !important;
                    justify-content: space-between !important;
                }
                .pdf-export-clone .control-panel > hr {
                    margin: 4px 0 !important;
                }
                .pdf-export-clone section[aria-label="Polygon live feed"] {
                    display: grid !important;
                    grid-template-columns: repeat(5, minmax(0, 1fr)) !important;
                    gap: 12px 14px !important;
                    align-items: start !important;
                    padding: 14px 16px !important;
                    margin-top: 4px !important;
                    background: rgba(8, 10, 20, 0.65) !important;
                    border: 1px solid rgba(0, 245, 212, 0.2) !important;
                    border-radius: 10px !important;
                }
                .pdf-export-clone section[aria-label="Polygon live feed"] > h3,
                .pdf-export-clone section[aria-label="Polygon live feed"] > p {
                    grid-column: 1 / -1 !important;
                    margin: 0 !important;
                }
                .pdf-export-clone .preset-panel {
                    display: grid !important;
                    grid-template-columns: repeat(2, minmax(0, 1fr)) !important;
                    gap: 8px 16px !important;
                    padding: 14px 16px !important;
                    margin-bottom: 4px !important;
                }
                .pdf-export-clone .preset-panel > h3,
                .pdf-export-clone .preset-panel > #preset-status {
                    grid-column: 1 / -1 !important;
                    margin: 0 !important;
                }
                .pdf-export-clone .form-group {
                    margin-bottom: 0 !important;
                    display: flex !important;
                    flex-direction: column !important;
                    justify-content: flex-start !important;
                }
                .pdf-export-clone .chart-container {
                    display: grid !important;
                    grid-template-columns: ${(!charts.has('live-chart') && !charts.has('chart')) ? 'repeat(2, minmax(0, 1fr))' : '1fr'} !important;
                    gap: 16px !important;
                }
                .pdf-export-clone .chart-card {
                    padding: 16px 20px !important;
                    margin-bottom: 0 !important;
                    background: #0d101d !important;
                }
            `;
            clone.prepend(pdfStyle);

            const header = clone.querySelector('.header, .three-r-header .header-left, .three-r-header');
            if (header) {
                const stamp = document.createElement('p');
                stamp.textContent = `Report Snapshot Captured: ${captured.toLocaleString()} (${captured.toISOString()})`;
                stamp.style.cssText = 'font-size:12px;color:#00f5d4;margin-top:6px;font-family:JetBrains Mono,monospace;';
                header.append(stamp);
            }

            document.body.append(clone);

            // 6. Replace native form controls with crisp static display boxes for html2canvas
            clone.querySelectorAll('input,select,textarea').forEach(control => {
                if (control.hidden || control.type === 'file') {
                    control.remove();
                    return;
                }
                const box = document.createElement('div');
                box.style.cssText = 'box-sizing:border-box;display:flex;align-items:center;white-space:normal;overflow-wrap:anywhere;min-height:36px;width:100%;padding:7px 11px;border:1px solid rgba(0,245,212,0.28);border-radius:7px;background:#080a14;color:#f8fafc;font-size:12.5px;font-weight:500;line-height:1.35;';
                if (control.type === 'checkbox') {
                    box.style.cssText = 'display:inline-flex;width:18px;height:18px;align-items:center;justify-content:center;border:1px solid #00f5d4;border-radius:4px;color:#00f5d4;background:#080a14;font-size:13px;font-weight:700;line-height:1;';
                    box.textContent = control.checked ? '✓' : '';
                } else if (control.type === 'color') {
                    box.style.background = control.value;
                    box.style.minHeight = '28px';
                } else if (control.type === 'range') {
                    const percentage = (Number(control.value) - Number(control.min)) / (Number(control.max) - Number(control.min)) * 100;
                    box.style.cssText = 'position:relative;display:inline-block;width:78%;height:22px;vertical-align:middle;background:transparent;border:none;padding:0;';
                    const track = document.createElement('div');
                    track.style.cssText = 'position:absolute;left:0;right:0;top:9px;height:5px;border-radius:3px;background:#1e293b;';
                    const thumb = document.createElement('div');
                    thumb.style.cssText = `position:absolute;left:${percentage}%;top:3px;width:16px;height:16px;border-radius:50%;background:#00f5d4;transform:translateX(-50%);`;
                    box.append(track, thumb);
                } else {
                    box.textContent = control.tagName === 'SELECT'
                        ? (control.selectedOptions[0]?.textContent || control.value)
                        : control.value;
                }
                control.replaceWith(box);
            });

            await document.fonts.ready;
            await Promise.all(Array.from(clone.querySelectorAll('img')).map(image => image.decode().catch(() => {})));

            const renderScale = 1.6;
            if (clone.scrollHeight * 1320 * renderScale * renderScale > 55000000) {
                throw new Error('Dashboard is too large to export safely. Reduce visible table rows and retry.');
            }

            status.textContent = 'Rendering single continuous-scroll PDF page...';
            const canvas = await html2canvas(clone, {
                backgroundColor: '#07080f',
                scale: renderScale,
                logging: false,
                useCORS: false,
                scrollX: 0,
                scrollY: 0,
                windowWidth: 1320,
                windowHeight: clone.scrollHeight
            });

            // 7. Create ONE single continuous scrolling PDF page sized dynamically to the rendered dashboard
            const pdf = await PDFLib.PDFDocument.create();
            pdf.setTitle(
                isThreeR
                    ? 'Kronos · The 3R Rule Structural Trading System Report'
                    : 'Kronos Research & Options Analytics Report'
            );
            pdf.setCreator('Kronos Web UI');
            pdf.setCreationDate(captured);
            const font = await pdf.embedFont(PDFLib.StandardFonts.Helvetica);
            const fontBold = await pdf.embedFont(PDFLib.StandardFonts.HelveticaBold);

            const pageWidth = 960;
            const margin = 20;
            const headerBarHeight = 22;
            const footerBarHeight = 22;
            const contentWidth = pageWidth - 2 * margin;
            const ratio = contentWidth / canvas.width;
            const totalContentHeight = canvas.height * ratio;
            const pageHeight = Math.ceil(totalContentHeight + 2 * margin + headerBarHeight + footerBarHeight);

            const page = pdf.addPage([pageWidth, pageHeight]);

            // Deep-space Darkwave background
            page.drawRectangle({
                x: 0, y: 0, width: pageWidth, height: pageHeight,
                color: PDFLib.rgb(0.027, 0.031, 0.059)
            });

            // Top header bar
            page.drawRectangle({
                x: margin, y: pageHeight - margin - 2, width: contentWidth, height: 1.5,
                color: PDFLib.rgb(0.0, 0.96, 0.83)
            });
            page.drawText(
                isThreeR
                    ? 'KRONOS × DOUG 3R RULE STRUCTURAL TRADING SYSTEM — MULTI-TIMEFRAME & RISK SIZING REPORT'
                    : 'KRONOS MULTI-MODEL FORECASTING, OPTIONS GEX & POSTGRES RESEARCH REPORT',
                {
                    x: margin, y: pageHeight - margin + 5, size: 8.5, font: fontBold,
                    color: PDFLib.rgb(0.0, 0.96, 0.83)
                }
            );
            page.drawText(`Continuous Scroll View | Captured ${captured.toLocaleString()}`, {
                x: pageWidth - margin - 250, y: pageHeight - margin + 5, size: 8, font,
                color: PDFLib.rgb(0.65, 0.72, 0.82)
            });

            // Draw the canvas in seamless high-res strips onto the single page (avoids browser PNG size limits)
            const maxStripPx = 2400;
            let cursor = 0;
            const topY = pageHeight - margin - headerBarHeight;
            while (cursor < canvas.height) {
                const stripHeight = Math.min(maxStripPx, canvas.height - cursor);
                const strip = document.createElement('canvas');
                strip.width = canvas.width;
                strip.height = stripHeight;
                const ctx = strip.getContext('2d');
                ctx.fillStyle = '#07080f';
                ctx.fillRect(0, 0, strip.width, strip.height);
                ctx.drawImage(canvas, 0, cursor, canvas.width, stripHeight, 0, 0, canvas.width, stripHeight);

                const image = await pdf.embedPng(strip.toDataURL('image/png'));
                const drawHeight = stripHeight * ratio;
                const drawY = topY - (cursor * ratio) - drawHeight;
                page.drawImage(image, {
                    x: margin,
                    y: drawY,
                    width: contentWidth,
                    height: drawHeight
                });
                strip.width = strip.height = 0;
                cursor += stripHeight;
            }
            canvas.width = canvas.height = 0;

            // Bottom footer bar
            page.drawRectangle({
                x: margin, y: margin + 12, width: contentWidth, height: 0.75,
                color: PDFLib.rgb(0.18, 0.22, 0.34)
            });
            page.drawText(`Kronos Research Vault (kronos_research) | ${captured.toISOString()}`, {
                x: margin, y: margin, size: 8.5, font,
                color: PDFLib.rgb(0.58, 0.64, 0.72)
            });
            page.drawText('Single-Page Continuous Scroll Report', {
                x: pageWidth - margin - 155, y: margin, size: 8.5, font: fontBold,
                color: PDFLib.rgb(0.0, 0.96, 0.83)
            });

            const prefix = isThreeR ? 'Kronos-3R-Report' : 'Kronos-WebUI';
            const shortId = (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function')
                ? crypto.randomUUID().slice(0, 8)
                : Math.random().toString(36).slice(2, 10);
            const filename = `${prefix}-${captured.toISOString().replace(/[:.]/g, '-')}-${shortId}.pdf`;
            const url = URL.createObjectURL(new Blob([await pdf.save()], { type: 'application/pdf' }));
            const link = document.createElement('a');
            link.href = url;
            link.download = filename;
            link.click();
            setTimeout(() => URL.revokeObjectURL(url), 60000);
            status.textContent = `Downloaded ${filename} (1 continuous scrolling page).`;
        } catch (error) {
            status.textContent = `PDF export failed: ${error.message || 'unknown error'}`;
        } finally {
            clone?.remove();
            exporting = false;
            button.disabled = false;
        }
    });
});


