/**
 * Kronos Multi-Model Testing Dashboard, Options Chain & PostgreSQL Analytics Hub
 * Includes TradingView-Style Cursor-Locked Wheel Zoom, Free Pan, Responsive Anti-Collision
 * Layout Engine, Visible-Tab Resize Controller & SPY Multi-Setup Matrix.
 */
document.addEventListener('DOMContentLoaded', () => {
    const hub = document.getElementById('testing-dashboard-hub');
    if (!hub) return;

    let overviewData = null;
    let tickerMap = {};
    const tvStateMap = new Map();
    const chartFigureCache = new Map();
    const spySetupResultsCache = new Map();

    // =========================================================================
    // VISIBILITY, WIDTH MEASUREMENT & ANTI-COLLISION RESPONSIVE LAYOUT ENGINE
    // =========================================================================
    function isPlotVisible(plotEl) {
        if (!plotEl) return false;
        const panel = plotEl.closest('.hub-tab-panel');
        if (panel && (panel.hidden || !panel.classList.contains('active'))) {
            return false;
        }
        const rect = plotEl.getBoundingClientRect();
        return rect.width >= 100 && plotEl.offsetParent !== null;
    }

    function measurePlotWidth(plotEl) {
        if (!plotEl) return 800;
        const parent = plotEl.parentElement;
        let w = plotEl.clientWidth;
        if (parent && parent.clientWidth > 120) {
            const cs = window.getComputedStyle(parent);
            const padX = (parseFloat(cs.paddingLeft) || 0) + (parseFloat(cs.paddingRight) || 0);
            const avail = Math.floor(parent.clientWidth - padX - 4);
            if (avail > 120) w = avail;
        }
        return Math.max(320, Math.floor(w || 800));
    }

    function adaptLayoutForWidth(rawLayout, containerWidth, targetHeight) {
        const layout = structuredClone(rawLayout || {});
        const hasSubplot = Boolean(layout.xaxis2 || layout.yaxis2);
        const isNarrow = containerWidth < 760;
        const isMedium = containerWidth >= 760 && containerWidth < 1080;

        const titleFontSize = isNarrow ? 11.5 : (isMedium ? 12.5 : 14);
        const subTitleFontSize = isNarrow ? 10.5 : (isMedium ? 11.5 : 12.5);
        const legendFontSize = isNarrow ? 10 : 11.5;
        const axisTitleFontSize = isNarrow ? 11 : 12;
        const tickFontSize = isNarrow ? 10 : 11;

        // Lock explicit dimensions so Plotly never collapses container height/width on window resize
        layout.autosize = false;
        layout.width = containerWidth;
        layout.height = targetHeight;

        if (layout.title) {
            if (typeof layout.title === 'string') {
                layout.title = { text: layout.title };
            }
            layout.title.font = {
                ...(layout.title.font || {}),
                size: titleFontSize,
                color: layout.title.font?.color || '#00f5d4',
            };
            layout.title.x = 0.01;
            layout.title.xanchor = 'left';
            layout.title.y = 0.97;
            layout.title.yanchor = 'top';
        }

        // Always place horizontal legend at the bottom below the X-axis title so it never collides with top titles
        layout.legend = {
            ...(layout.legend || {}),
            orientation: 'h',
            x: 0.0,
            xanchor: 'left',
            y: hasSubplot ? (isNarrow ? -0.19 : -0.16) : (isNarrow ? -0.27 : -0.23),
            yanchor: 'top',
            font: {
                ...(layout.legend?.font || {}),
                size: legendFontSize,
                color: '#e2e8f0',
            },
            bgcolor: 'rgba(12, 14, 26, 0.78)',
        };

        const estLegendRowCount = isNarrow ? 3 : (isMedium ? 2 : 1);
        const bottomMargin = (hasSubplot ? 116 : 120) + (estLegendRowCount - 1) * 24;
        layout.margin = {
            l: isNarrow ? 66 : 84,
            r: isNarrow ? 24 : 36,
            t: layout.title?.text ? (isNarrow ? 74 : 66) : (isNarrow ? 60 : 56),
            b: bottomMargin,
        };

        // Responsive subplot title annotations & reference badges
        if (Array.isArray(layout.annotations)) {
            layout.annotations = layout.annotations.map(ann => {
                const copy = { ...ann, font: { ...(ann.font || {}) } };
                if (copy.xref === 'paper' && copy.yref === 'paper') {
                    copy.font.size = subTitleFontSize;
                    copy.font.color = copy.font.color || '#00f5d4';
                    if (isNarrow && typeof copy.text === 'string' && copy.text.length > 66) {
                        copy.text = copy.text.slice(0, 63) + '…';
                    } else if (isMedium && typeof copy.text === 'string' && copy.text.length > 94) {
                        copy.text = copy.text.slice(0, 91) + '…';
                    }
                } else {
                    copy.font.size = isNarrow ? 10 : (copy.font.size || 11);
                }
                return copy;
            });
        }

        ['xaxis', 'xaxis2', 'yaxis', 'yaxis2'].forEach(axKey => {
            if (!layout[axKey]) return;
            layout[axKey] = {
                ...layout[axKey],
                automargin: true,
                tickfont: { ...(layout[axKey].tickfont || {}), size: tickFontSize },
            };
            if (layout[axKey].title) {
                if (typeof layout[axKey].title === 'string') {
                    layout[axKey].title = { text: layout[axKey].title };
                }
                layout[axKey].title = {
                    ...layout[axKey].title,
                    font: { ...(layout[axKey].title.font || {}), size: axisTitleFontSize },
                    standoff: 10,
                };
            }
        });

        // Prevent Row 1 X-axis tick labels from printing in the middle gap above Row 2's subplot title
        if (hasSubplot && layout.xaxis) {
            layout.xaxis.showticklabels = false;
            if (layout.xaxis.title) layout.xaxis.title.text = '';
        }

        return layout;
    }

    async function renderChartSafely(plotId, fig, tvOptions = {}) {
        const plotEl = typeof plotId === 'string' ? document.getElementById(plotId) : plotId;
        if (!plotEl || !fig) return;
        const id = plotEl.id;
        const baseHeight = Number(fig.layout?.height) || 600;

        chartFigureCache.set(id, {
            rawFig: structuredClone(fig),
            baseHeight,
            tvOptions,
        });

        const existingState = tvStateMap.get(id);
        const targetHeight = existingState?.isTall ? Math.round(baseHeight * 1.4) : baseHeight;
        plotEl.style.height = `${targetHeight}px`;
        plotEl.style.minHeight = `${targetHeight}px`;
        plotEl.style.width = '100%';

        // If inside a hidden tab, defer rendering until the tab is switched to visible
        if (!isPlotVisible(plotEl)) {
            plotEl.dataset.needsRender = 'true';
            return;
        }

        delete plotEl.dataset.needsRender;
        const width = measurePlotWidth(plotEl);
        const adaptedLayout = adaptLayoutForWidth(fig.layout, width, targetHeight);

        await Plotly.react(plotEl, structuredClone(fig.data), adaptedLayout, {
            responsive: false,
            scrollZoom: false,
            displaylogo: false,
        });
        plotEl.dataset.lastRenderedWidth = String(width);
        enableTradingViewChart(id, tvOptions);
    }

    async function resizeVisibleCharts(force = false) {
        for (const [plotId, cached] of chartFigureCache.entries()) {
            const plotEl = document.getElementById(plotId);
            if (!plotEl || !isPlotVisible(plotEl)) continue;

            const hasSvg = Boolean(plotEl.querySelector('.main-svg'));
            if (plotEl.dataset.needsRender === 'true' || !plotEl._fullLayout || !hasSvg) {
                await renderChartSafely(plotId, cached.rawFig, cached.tvOptions);
                continue;
            }

            const newWidth = measurePlotWidth(plotEl);
            const lastWidth = Number(plotEl.dataset.lastRenderedWidth || 0);
            if (!force && Math.abs(newWidth - lastWidth) < 3) continue;

            const st = tvStateMap.get(plotId);
            const [curMin, curMax] = st ? getLiveXRange(plotEl, st) : [NaN, NaN];
            const targetHeight = st?.isTall ? Math.round(cached.baseHeight * 1.4) : cached.baseHeight;

            plotEl.style.height = `${targetHeight}px`;
            plotEl.style.minHeight = `${targetHeight}px`;

            const adapted = adaptLayoutForWidth(cached.rawFig.layout, newWidth, targetHeight);
            if (Number.isFinite(curMin) && Number.isFinite(curMax) && curMax > curMin) {
                if (adapted.xaxis) {
                    adapted.xaxis.range = [curMin, curMax];
                    adapted.xaxis.autorange = false;
                }
                if (adapted.xaxis2) {
                    adapted.xaxis2.range = [curMin, curMax];
                    adapted.xaxis2.autorange = false;
                }
            }

            if (st) st.isUpdating = true;
            try {
                await Plotly.react(plotEl, plotEl.data || structuredClone(cached.rawFig.data), adapted, {
                    responsive: false,
                    scrollZoom: false,
                    displaylogo: false,
                });
                plotEl.dataset.lastRenderedWidth = String(newWidth);
            } finally {
                if (st) st.isUpdating = false;
            }

            if (st && Number.isFinite(curMin) && Number.isFinite(curMax) && curMax > curMin) {
                applyTradingViewViewport(plotEl, st, curMin, curMax, {
                    fromDrag: true,
                    containerWidth: newWidth,
                });
            }
        }
    }

    let hubResizeTimer = null;
    function scheduleChartResize(force = false) {
        if (hubResizeTimer) clearTimeout(hubResizeTimer);
        hubResizeTimer = setTimeout(() => {
            resizeVisibleCharts(force);
        }, 85);
    }

    window.addEventListener('resize', () => scheduleChartResize(false));
    if (typeof ResizeObserver === 'function') {
        const ro = new ResizeObserver(() => scheduleChartResize(false));
        ro.observe(hub);
    }

    // =========================================================================
    // TRADINGVIEW-STYLE INTERACTIVE CHART ENGINE (Cursor-Locked Wheel Zoom & Pan)
    // =========================================================================
    function computeTraceXBounds(plotEl, isCategory) {
        const data = plotEl.data || [];
        if (isCategory) {
            const catArr = plotEl._fullLayout?.xaxis?.categoryarray || [];
            if (catArr.length) {
                return { minX: -0.5, maxX: catArr.length - 0.5, count: catArr.length, categories: catArr };
            }
            let maxLen = 0;
            let longestX = [];
            data.forEach(tr => {
                if (Array.isArray(tr.x) && tr.x.length > maxLen) {
                    maxLen = tr.x.length;
                    longestX = tr.x;
                }
            });
            return { minX: -0.5, maxX: Math.max(10, maxLen - 0.5), count: maxLen, categories: longestX };
        }

        let minX = Infinity;
        let maxX = -Infinity;
        data.forEach(tr => {
            if (!Array.isArray(tr.x)) return;
            for (let i = 0; i < tr.x.length; i++) {
                const v = Number(tr.x[i]);
                if (Number.isFinite(v)) {
                    if (v < minX) minX = v;
                    if (v > maxX) maxX = v;
                }
            }
        });
        if (!Number.isFinite(minX) || !Number.isFinite(maxX) || minX >= maxX) {
            return { minX: 0, maxX: 100, count: 100, categories: [] };
        }
        return { minX, maxX, count: 100, categories: [] };
    }

    function computeVisibleYBounds(plotEl, xMin, xMax, isCategory, categories) {
        const data = plotEl.data || [];
        const yBoundsByAxis = {};

        const recordY = (axisName, val) => {
            const num = Number(val);
            if (!Number.isFinite(num)) return;
            if (!yBoundsByAxis[axisName]) {
                yBoundsByAxis[axisName] = { min: num, max: num, hasBars: false };
            } else {
                if (num < yBoundsByAxis[axisName].min) yBoundsByAxis[axisName].min = num;
                if (num > yBoundsByAxis[axisName].max) yBoundsByAxis[axisName].max = num;
            }
        };

        const catIndexMap = new Map();
        if (isCategory && Array.isArray(categories)) {
            categories.forEach((c, idx) => catIndexMap.set(String(c), idx));
        }

        data.forEach(tr => {
            if (tr.visible === false || tr.visible === 'legendonly') return;
            const yAxis = tr.yaxis || 'y';
            const xs = tr.x || [];
            const len = xs.length;

            for (let i = 0; i < len; i++) {
                let xNum;
                if (isCategory) {
                    const mapped = catIndexMap.get(String(xs[i]));
                    xNum = mapped !== undefined ? mapped : i;
                } else {
                    xNum = Number(xs[i]);
                }
                if (!Number.isFinite(xNum) || xNum < xMin - 0.5 || xNum > xMax + 0.5) continue;

                if (tr.type === 'candlestick' || tr.type === 'ohlc') {
                    if (tr.high && tr.high[i] != null) recordY(yAxis, tr.high[i]);
                    if (tr.low && tr.low[i] != null) recordY(yAxis, tr.low[i]);
                } else if (tr.type === 'bar') {
                    if (tr.y && tr.y[i] != null) {
                        recordY(yAxis, tr.y[i]);
                        recordY(yAxis, 0);
                        if (yBoundsByAxis[yAxis]) yBoundsByAxis[yAxis].hasBars = true;
                    }
                } else if (tr.y && tr.y[i] != null) {
                    recordY(yAxis, tr.y[i]);
                }
            }
        });

        return yBoundsByAxis;
    }

    function buildCategoryTicks(categories, xMin, xMax, containerWidth = 1000) {
        if (!Array.isArray(categories) || !categories.length) return null;
        const startIdx = Math.max(0, Math.floor(xMin));
        const endIdx = Math.min(categories.length - 1, Math.ceil(xMax));
        if (endIdx < startIdx) return null;

        const visibleCount = Math.max(1, endIdx - startIdx + 1);
        const maxTicks = containerWidth < 600 ? 4 : (containerWidth < 920 ? 6 : 8);
        const numTicks = Math.min(maxTicks, visibleCount);
        const tickvals = [];

        if (numTicks <= 1) {
            tickvals.push(categories[startIdx]);
        } else {
            for (let i = 0; i < numTicks; i++) {
                const idx = Math.round(startIdx + (i * (endIdx - startIdx)) / (numTicks - 1));
                const label = categories[idx];
                if (label !== undefined && tickvals[tickvals.length - 1] !== label) {
                    tickvals.push(label);
                }
            }
        }
        return { tickvals, ticktext: tickvals };
    }

    function getLiveXRange(plotEl, state) {
        const masterAxis = plotEl._fullLayout?.xaxis2 || plotEl._fullLayout?.xaxis;
        const r = masterAxis?.range || plotEl._fullLayout?.xaxis?.range || state.focusRange;
        return [Number(r[0]), Number(r[1])];
    }

    function applyTradingViewViewport(plotEl, state, nextMin, nextMax, options = {}) {
        const { isCategory, bounds } = state;
        const fullSpan = Math.max(1e-6, bounds.maxX - bounds.minX);
        const minSpan = isCategory ? 4 : fullSpan * 0.02;
        const maxSpan = isCategory ? Math.max(50, bounds.count * 3) : fullSpan * 4.0;
        const width = options.containerWidth || plotEl.clientWidth || 1000;

        const relayoutPatch = {};

        // Only modify X-axis range on wheel zoom or toolbar buttons — NEVER overwrite X-axis range after a mouse drag!
        if (!options.fromDrag) {
            const curSpan = Math.max(1e-6, nextMax - nextMin);
            const clampedSpan = Math.max(minSpan, Math.min(maxSpan, curSpan));
            if (Math.abs(clampedSpan - curSpan) > 1e-6) {
                const anchorRatio = options.anchorRatio ?? 0.5;
                const anchor = nextMin + curSpan * anchorRatio;
                nextMin = anchor - clampedSpan * anchorRatio;
                nextMax = nextMin + clampedSpan;
            }
            relayoutPatch['xaxis.range'] = [nextMin, nextMax];
            relayoutPatch['xaxis.autorange'] = false;
            if (state.hasXaxis2) {
                relayoutPatch['xaxis2.range'] = [nextMin, nextMax];
                relayoutPatch['xaxis2.autorange'] = false;
            }
        }

        if (isCategory && bounds.categories.length) {
            const ticks = buildCategoryTicks(bounds.categories, nextMin, nextMax, width);
            if (ticks && ticks.tickvals.length) {
                if (state.hasXaxis2) {
                    relayoutPatch['xaxis.showticklabels'] = false;
                    relayoutPatch['xaxis2.showticklabels'] = true;
                    relayoutPatch['xaxis2.tickmode'] = 'array';
                    relayoutPatch['xaxis2.tickvals'] = ticks.tickvals;
                    relayoutPatch['xaxis2.ticktext'] = ticks.ticktext;
                } else {
                    relayoutPatch['xaxis.showticklabels'] = true;
                    relayoutPatch['xaxis.tickmode'] = 'array';
                    relayoutPatch['xaxis.tickvals'] = ticks.tickvals;
                    relayoutPatch['xaxis.ticktext'] = ticks.ticktext;
                }
            }
        }

        // Auto-fit visible Y axes with comfortable 8% top/bottom breathing room
        const yBounds = computeVisibleYBounds(plotEl, nextMin, nextMax, isCategory, bounds.categories);
        Object.entries(yBounds).forEach(([axisKey, b]) => {
            if (!Number.isFinite(b.min) || !Number.isFinite(b.max)) return;
            const layoutAxisName = axisKey === 'y' ? 'yaxis' : `yaxis${axisKey.slice(1)}`;
            const ySpan = Math.max(1e-6, b.max - b.min);
            const pad = ySpan * 0.08;
            const low = b.hasBars && b.min >= 0 ? 0 : b.min - pad;
            const high = b.max + pad * 1.15;
            relayoutPatch[`${layoutAxisName}.range`] = [low, high];
            relayoutPatch[`${layoutAxisName}.autorange`] = false;
        });

        if (Object.keys(relayoutPatch).length === 0) return;

        state.isUpdating = true;
        Plotly.relayout(plotEl, relayoutPatch).finally(() => {
            state.isUpdating = false;
        });
    }

    function ensureTvToolbar(plotEl, state) {
        const parent = plotEl.parentElement;
        if (!parent) return;
        let toolbar = parent.querySelector(`.tv-chart-toolbar[data-for="${plotEl.id}"]`);
        if (!toolbar) {
            toolbar = document.createElement('div');
            toolbar.className = 'tv-chart-toolbar';
            toolbar.setAttribute('data-for', plotEl.id);
            toolbar.setAttribute('data-html2canvas-ignore', 'true');
            toolbar.innerHTML = `
                <div class="tv-toolbar-hint">
                    <span class="tv-badge">⚡ TRADINGVIEW ENGINE</span>
                    <span>Mouse Wheel = Cursor-Locked Zoom • Drag = Free Pan (Stays Where Released)</span>
                </div>
                <div class="tv-toolbar-actions">
                    <button type="button" class="tv-tool-btn" data-tv-act="zoom-in" title="Zoom In around center">🔍+ Zoom In</button>
                    <button type="button" class="tv-tool-btn" data-tv-act="zoom-out" title="Zoom Out / Expand Window">🔍− Zoom Out</button>
                    <button type="button" class="tv-tool-btn" data-tv-act="pan-left" title="Pan Left (Earlier / Lower Strikes)">◀ Pan Left</button>
                    <button type="button" class="tv-tool-btn" data-tv-act="pan-right" title="Pan Right (Later / Higher Strikes)">Pan Right ▶</button>
                    <button type="button" class="tv-tool-btn" data-tv-act="focus" title="Snap to Active Trading / Spot Zone">🎯 Focus Zone</button>
                    <button type="button" class="tv-tool-btn" data-tv-act="full" title="Show Entire Dataset Range">↔️ Full Range</button>
                    <button type="button" class="tv-tool-btn" data-tv-act="tall" title="Toggle Extra-Tall Chart Height">⤢ Tall View</button>
                </div>
            `;
            parent.insertBefore(toolbar, plotEl);

            toolbar.addEventListener('click', (e) => {
                const btn = e.target.closest('[data-tv-act]');
                if (!btn) return;
                const act = btn.getAttribute('data-tv-act');
                const st = tvStateMap.get(plotEl.id) || state;
                const [curMin, curMax] = getLiveXRange(plotEl, st);
                const span = Math.max(1e-6, curMax - curMin);
                const center = curMin + span * 0.5;

                if (act === 'zoom-in') {
                    const newSpan = span * 0.72;
                    applyTradingViewViewport(plotEl, st, center - newSpan * 0.5, center + newSpan * 0.5);
                } else if (act === 'zoom-out') {
                    const newSpan = span * 1.38;
                    applyTradingViewViewport(plotEl, st, center - newSpan * 0.5, center + newSpan * 0.5);
                } else if (act === 'pan-left') {
                    const shift = span * 0.32;
                    applyTradingViewViewport(plotEl, st, curMin - shift, curMax - shift);
                } else if (act === 'pan-right') {
                    const shift = span * 0.32;
                    applyTradingViewViewport(plotEl, st, curMin + shift, curMax + shift);
                } else if (act === 'focus') {
                    applyTradingViewViewport(plotEl, st, st.focusRange[0], st.focusRange[1]);
                } else if (act === 'full') {
                    applyTradingViewViewport(plotEl, st, st.fullRange[0], st.fullRange[1]);
                } else if (act === 'tall') {
                    st.isTall = !st.isTall;
                    btn.classList.toggle('active', st.isTall);
                    const nextH = st.isTall ? Math.round(st.baseHeight * 1.4) : st.baseHeight;
                    plotEl.style.height = `${nextH}px`;
                    plotEl.style.minHeight = `${nextH}px`;
                    Plotly.relayout(plotEl, { height: nextH });
                }
            });
        }
    }

    function enableTradingViewChart(plotId, options = {}) {
        const plotEl = typeof plotId === 'string' ? document.getElementById(plotId) : plotId;
        if (!plotEl || !plotEl._fullLayout) return;

        const xType = plotEl._fullLayout.xaxis?.type || 'linear';
        const isCategory = xType === 'category';
        const hasXaxis2 = Boolean(plotEl._fullLayout.xaxis2);
        const bounds = computeTraceXBounds(plotEl, isCategory);

        const initialRange = plotEl._fullLayout.xaxis?.range
            ? [Number(plotEl._fullLayout.xaxis.range[0]), Number(plotEl._fullLayout.xaxis.range[1])]
            : [bounds.minX, bounds.maxX];

        const fullRange = isCategory
            ? [-0.5, Math.max(10, bounds.count - 0.5 + 1.2)]
            : [bounds.minX - (bounds.maxX - bounds.minX) * 0.02, bounds.maxX + (bounds.maxX - bounds.minX) * 0.02];

        const focusRange = options.focusRange || initialRange;
        const cached = chartFigureCache.get(plotEl.id);
        const baseHeight = cached?.baseHeight || plotEl._fullLayout.height || plotEl.clientHeight || 580;
        const prevState = tvStateMap.get(plotEl.id);

        const state = {
            plotEl,
            isCategory,
            hasXaxis2,
            bounds,
            focusRange,
            fullRange,
            baseHeight,
            isTall: Boolean(prevState?.isTall),
            isUpdating: false,
        };
        tvStateMap.set(plotEl.id, state);

        if (options.showToolbar !== false) {
            ensureTvToolbar(plotEl, state);
        }

        // Attach capture-phase wheel listener once per DOM element
        if (!plotEl.dataset.tvWheelAttached) {
            plotEl.dataset.tvWheelAttached = 'true';

            plotEl.addEventListener('wheel', (e) => {
                const st = tvStateMap.get(plotEl.id);
                if (!st || !plotEl._fullLayout?.xaxis) return;

                // Intercept wheel over plot area to perform cursor-locked X-zoom + Y-autofit
                e.preventDefault();
                e.stopPropagation();

                const dragLayer = plotEl.querySelector('.nsewdrag') || plotEl;
                const rect = dragLayer.getBoundingClientRect();
                const cursorRatio = Math.max(0.05, Math.min(0.95, (e.clientX - rect.left) / Math.max(1, rect.width)));

                const [curMin, curMax] = getLiveXRange(plotEl, st);
                if (!Number.isFinite(curMin) || !Number.isFinite(curMax)) return;

                const curSpan = Math.max(1e-6, curMax - curMin);
                const zoomIn = e.deltaY < 0;
                const factor = zoomIn ? 0.82 : 1.22;
                const newSpan = curSpan * factor;

                // Lock anchor to exact cursor X coordinate
                const anchor = curMin + curSpan * cursorRatio;
                const nextMin = anchor - newSpan * cursorRatio;
                const nextMax = nextMin + newSpan;

                applyTradingViewViewport(plotEl, st, nextMin, nextMax, { anchorRatio: cursorRatio });
            }, { passive: false, capture: true });
        }

        // When user drags either the upper or lower panel, leave X-axis exactly where released and only auto-fit Y-axes
        if (typeof plotEl.on === 'function' && !plotEl.dataset.tvRelayoutAttached) {
            plotEl.dataset.tvRelayoutAttached = 'true';
            plotEl.on('plotly_relayout', (eventData) => {
                const st = tvStateMap.get(plotEl.id);
                if (!st || st.isUpdating || !eventData) return;

                const hasXChange = Object.keys(eventData).some(k => k.startsWith('xaxis'));
                if (!hasXChange) return;

                const [n0, n1] = getLiveXRange(plotEl, st);
                if (Number.isFinite(n0) && Number.isFinite(n1) && n1 > n0) {
                    applyTradingViewViewport(plotEl, st, n0, n1, { fromDrag: true });
                }
            });
        }

        // Perform initial Y-axis auto-fit for the active focus zone
        applyTradingViewViewport(plotEl, state, focusRange[0], focusRange[1]);
    }

    // Expose globally so ChartWorkbench (#live-chart and #chart) also gets TradingView wheel zoom
    window.KronosTradingView = { enableTradingViewChart, renderChartSafely, resizeVisibleCharts };

    // Hook into ChartWorkbench.render if present so #live-chart and #chart get cursor-locked zoom too
    if (window.ChartWorkbench && typeof window.ChartWorkbench.render === 'function') {
        const origRender = window.ChartWorkbench.render.bind(window.ChartWorkbench);
        window.ChartWorkbench.render = async function(id, figure, result = null) {
            const out = await origRender(id, figure, result);
            const el = document.getElementById(id);
            if (el && el._fullLayout) {
                const catLen = el._fullLayout.xaxis?.categoryarray?.length || 0;
                const focusRange = catLen > 85 ? [catLen - 85, catLen + 2] : undefined;
                enableTradingViewChart(id, { showToolbar: false, focusRange });
            }
            return out;
        };
    }

    // =========================================================================
    // TAB SWITCHING & FORMATTING HELPERS
    // =========================================================================
    const tabs = hub.querySelectorAll('.hub-tab');
    const panels = hub.querySelectorAll('.hub-tab-panel');
    tabs.forEach(tab => {
        tab.addEventListener('click', () => {
            const targetId = tab.getAttribute('data-tab');
            tabs.forEach(t => {
                const active = t === tab;
                t.classList.toggle('active', active);
                t.setAttribute('aria-selected', active ? 'true' : 'false');
            });
            panels.forEach(p => {
                const show = p.id === targetId;
                p.classList.toggle('active', show);
                p.hidden = !show;
            });
            // Render or resize any charts in the newly activated tab at full visible container width
            requestAnimationFrame(() => {
                resizeVisibleCharts(true);
            });
        });
    });

    function fmtNum(v, decimals = 2, prefix = '', suffix = '') {
        if (v === null || v === undefined || Number.isNaN(Number(v))) return '-';
        return `${prefix}${Number(v).toLocaleString('en-US', { minimumFractionDigits: decimals, maximumFractionDigits: decimals })}${suffix}`;
    }

    function fmtInt(v) {
        if (v === null || v === undefined || Number.isNaN(Number(v))) return '-';
        return Number(v).toLocaleString('en-US');
    }

    async function apiJson(url, options = {}) {
        const resp = await fetch(url, options);
        const text = await resp.text();
        let data = {};
        try {
            data = JSON.parse(text);
        } catch {
            throw new Error(`Server returned HTTP ${resp.status}`);
        }
        if (!resp.ok || data.error) {
            throw new Error(data.error || `HTTP ${resp.status}`);
        }
        return data;
    }

    // Load overview & populate models + Postgres counts + Scoreboard
    async function loadTestingOverview() {
        try {
            const data = await apiJson('/api/testing/overview');
            overviewData = data;
            tickerMap = data.ticker_map || {};

            const accelBadge = document.getElementById('accel-status-badge');
            if (accelBadge) {
                accelBadge.textContent = `Accelerator: ${(data.accelerator || 'cpu').toUpperCase()}`;
                accelBadge.className = 'hub-badge badge-info';
            }

            updatePostgresExplorer(data.database);
            populateLabModelSelect(data.tuned_models || []);
            renderScoreboard(data.tuned_models || [], data.benchmarks || {});
        } catch (err) {
            console.error('Failed loading testing overview:', err);
            const pgBadge = document.getElementById('pg-status-badge');
            if (pgBadge) {
                pgBadge.textContent = 'Postgres: Error';
                pgBadge.className = 'hub-badge badge-danger';
            }
        }
    }

    function populateLabModelSelect(tunedModels) {
        const sel = document.getElementById('lab-model');
        if (!sel || !tunedModels.length) return;
        sel.innerHTML = '';
        tunedModels.forEach(m => {
            const opt = document.createElement('option');
            opt.value = m.model_key;
            opt.textContent = `${m.name} [${(m.tickers || []).join(', ')}]`;
            sel.appendChild(opt);
        });
        syncLabTickerSelection(document.getElementById('lab-ticker').value);
    }

    function syncLabTickerSelection(rawTicker) {
        const t = String(rawTicker || 'SPY').trim().toUpperCase();
        const labTicker = document.getElementById('lab-ticker');
        const optTicker = document.getElementById('opt-ticker');
        if (labTicker) labTicker.value = t;
        if (optTicker && !t.startsWith('I:')) optTicker.value = t;

        hub.querySelectorAll('.ticker-pill').forEach(pill => {
            pill.classList.toggle('active', pill.getAttribute('data-ticker') === t);
        });

        const spec = tickerMap[t];
        if (spec) {
            const modelSel = document.getElementById('lab-model');
            const normSel = document.getElementById('lab-norm');
            if (modelSel && spec.model_key) modelSel.value = spec.model_key;
            if (normSel && spec.normalization_mode) normSel.value = spec.normalization_mode;
        }
    }

    hub.querySelectorAll('.ticker-pill').forEach(pill => {
        pill.addEventListener('click', () => {
            const t = pill.getAttribute('data-ticker');
            syncLabTickerSelection(t);
        });
    });

    document.getElementById('lab-ticker')?.addEventListener('change', (e) => {
        syncLabTickerSelection(e.target.value);
    });

    // Render Tuned Models Scoreboard
    function renderScoreboard(tunedModels, benchmarks) {
        const tbody = document.getElementById('models-scoreboard-tbody');
        if (!tbody) return;
        tbody.innerHTML = '';

        const confSpot = benchmarks?.confluence_spot_vix;
        if (confSpot) {
            const tr = document.createElement('tr');
            tr.style.background = 'rgba(0, 245, 212, 0.08)';
            tr.innerHTML = `
                <th><strong>SPY_23yr + VIX_companion (Spot I:VIX Confluence)</strong></th>
                <td>SPY + I:VIX</td>
                <td>5m, 15m, 1h, 1d</td>
                <td><code>detrend + standard</code></td>
                <td>3,025,974</td>
                <td><span class="hub-badge badge-success">CONFLUENCE VERIFIED</span></td>
                <td><strong>${fmtNum(confSpot.confirmed_accuracy, 1, '', '%')}</strong> (${confSpot.confirmed_hits}/${confSpot.confirmed_trades} confirmed, p=${fmtNum(confSpot.confirmed_p_value, 4)})</td>
                <td>${fmtNum(confSpot.confirmed_avg_mae, 2, '$')}</td>
                <td>0.42%</td>
                <td><button type="button" class="ticker-pill" data-quick-lab="SPY">Test SPY+VIX</button></td>
            `;
            tbody.appendChild(tr);
        }

        tunedModels.forEach(m => {
            const tr = document.createElement('tr');
            const primaryTicker = (m.tickers && m.tickers[0]) || 'SPY';
            const accText = m.benchmark_accuracy_pct != null ? `<strong>${fmtNum(m.benchmark_accuracy_pct, 1, '', '%')}</strong>` : 'Ready';
            tr.innerHTML = `
                <th><code>${m.model_key}</code></th>
                <td><strong>${(m.tickers || []).join(', ')}</strong></td>
                <td>${(m.timeframes || []).join(', ')}</td>
                <td><code>${m.normalization_mode}</code></td>
                <td>${fmtInt(m.total_training_bars)}</td>
                <td><span class="hub-badge badge-success">${m.training_status || 'COMPLETED'}</span></td>
                <td>${accText}</td>
                <td>${m.benchmark_mae != null ? fmtNum(m.benchmark_mae, 2, '$') : '-'}</td>
                <td>${m.benchmark_mape_pct != null ? fmtNum(m.benchmark_mape_pct, 2, '', '%') : '-'}</td>
                <td><button type="button" class="ticker-pill" data-quick-lab="${primaryTicker}">Analyze ${primaryTicker}</button></td>
            `;
            tbody.appendChild(tr);
        });

        tbody.querySelectorAll('[data-quick-lab]').forEach(btn => {
            btn.addEventListener('click', () => {
                const tkr = btn.getAttribute('data-quick-lab');
                syncLabTickerSelection(tkr);
                tabs[0].click();
                runEnhancedAnalysis();
            });
        });
    }

    // =========================================================================
    // TAB 1: RENDER ANALYSIS RESULT INTO KPI CARDS + TRADINGVIEW CHART
    // =========================================================================
    async function displayAnalysisResponse(res) {
        const s = res.summary || {};
        const conf = res.confluence;
        document.getElementById('lab-kpi-grid').style.display = 'grid';

        document.getElementById('kpi-price-move').textContent = `${fmtNum(s.last_close, 2, '$')} → ${fmtNum(s.predicted_close, 2, '$')}`;
        const retSign = s.predicted_return_pct >= 0 ? '+' : '';
        const modeTag = res.mode_badge || (res.eval_mode === 'future' ? 'LIVE FORWARD FORECAST' : 'HISTORICAL HOLDOUT BACKTEST');
        const latTag = res.inference_ms ? ` • ${fmtNum(res.inference_ms, 0, '', 'ms')}` : '';
        document.getElementById('kpi-pred-ret').textContent = `${retSign}${fmtNum(s.predicted_return_pct, 2, '', '%')} (${s.pred_len} bars) • ${modeTag}${latTag}`;

        if (res.actual_return_pct !== null && res.actual_return_pct !== undefined) {
            const actSign = res.actual_return_pct >= 0 ? '+' : '';
            document.getElementById('kpi-actual-ret').textContent = `${actSign}${fmtNum(res.actual_return_pct, 2, '', '%')}`;
            document.getElementById('kpi-dir-hit').textContent = s.direction_hit ? '✅ Direction Hit (Aligned)' : '❌ Direction Miss (Diverged)';
        } else {
            document.getElementById('kpi-actual-ret').textContent = 'Live Forward Horizon';
            document.getElementById('kpi-dir-hit').textContent = `Anchor: ${s.anchor_timestamp || 'Latest'} (${res.source_provenance || 'POLYGON_LIVE_FEED'})`;
        }

        if (conf) {
            document.getElementById('kpi-conf-signal').textContent = String(conf.signal || '').replace(/_/g, ' ');
            document.getElementById('kpi-conf-detail').textContent = `${conf.companion_symbol} Pred: ${conf.vix_return_pct >= 0 ? '+' : ''}${conf.vix_return_pct}% | Conviction: ${fmtNum(conf.conviction_score * 100, 0, '', '%')}`;
        } else {
            document.getElementById('kpi-conf-signal').textContent = 'Single-Model Mode';
            document.getElementById('kpi-conf-detail').textContent = 'Companion filter disabled';
        }

        document.getElementById('kpi-env-range').textContent = `${fmtNum(s.env_low_min, 2, '$')} – ${fmtNum(s.env_high_max, 2, '$')}`;
        const skillTag = s.mae_skill_pct != null ? ` | Skill vs RW: ${s.mae_skill_pct >= 0 ? '+' : ''}${fmtNum(s.mae_skill_pct, 1, '', '%')}` : '';
        document.getElementById('kpi-error-metrics').textContent = s.mae != null
            ? `MAE: ${fmtNum(s.mae, 2, '$')} | MAPE: ${fmtNum(s.mape_pct, 2, '', '%')}${skillTag}`
            : `Model Range: ${fmtNum(s.predicted_low, 2, '$')} – ${fmtNum(s.predicted_high, 2, '$')} (${res.source_provenance || 'LOCAL_23YR_RESEARCH_CSV'})`;

        const fig = JSON.parse(res.chart);
        await renderChartSafely('lab-chart-container', fig, {
            focusRange: fig.layout?.xaxis?.range,
        });
    }

    async function runEnhancedAnalysis() {
        const btn = document.getElementById('lab-run-btn');
        const status = document.getElementById('lab-status-msg');
        const ticker = document.getElementById('lab-ticker').value.trim().toUpperCase();
        const modelKey = document.getElementById('lab-model').value;
        const timeframe = document.getElementById('lab-timeframe').value;
        const normMode = document.getElementById('lab-norm').value;
        const evalMode = document.getElementById('lab-eval-mode').value;
        const dataSource = document.getElementById('lab-data-source').value;
        const lookback = Number(document.getElementById('lab-lookback').value);
        const predLen = Number(document.getElementById('lab-horizon').value);
        const sampleCount = Number(document.getElementById('lab-samples').value);
        const windowOffset = Number(document.getElementById('lab-window-offset').value);
        const companion = document.getElementById('lab-companion').value;

        btn.disabled = true;
        status.textContent = `Running ${modelKey} on ${ticker} (${timeframe}, ${sampleCount} medoid paths, ${normMode})...`;

        try {
            const res = await apiJson('/api/testing/run-analysis', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    ticker,
                    model_key: modelKey,
                    timeframe,
                    normalization_mode: normMode,
                    eval_mode: evalMode,
                    data_source: dataSource,
                    lookback,
                    pred_len: predLen,
                    sample_count: sampleCount,
                    window_offset: windowOffset,
                    include_confluence: companion !== 'NONE',
                    companion_symbol: companion === 'NONE' ? 'I:VIX' : companion,
                }),
            });

            await displayAnalysisResponse(res);
            status.innerHTML = `✅ Completed <strong>${ticker}</strong> analysis with <code>${modelKey}</code> (${res.mode_badge || 'EVAL'} • ${res.source_provenance || 'DATA'} • ${fmtNum(res.inference_ms, 0, '', 'ms')}). Saved to PostgreSQL <code>model_forecast_runs</code> (Run ID #${res.saved_run_id || 'N/A'}).`;
            refreshPostgresHistory();
        } catch (err) {
            status.textContent = `❌ Analysis failed: ${err.message}`;
        } finally {
            btn.disabled = false;
        }
    }

    document.getElementById('lab-run-btn')?.addEventListener('click', runEnhancedAnalysis);

    // =========================================================================
    // RUN ALL 7 SPY SETUPS MATRIX
    // =========================================================================
    const SPY_ALL_SETUPS = [
        {
            id: 'spy_1h_spot_vix',
            label: '1. SPY 23-Yr + Spot I:VIX Confluence (1h Swing)',
            ticker: 'SPY',
            model_key: 'SPY_23yr_multi_tf',
            timeframe: '1hour',
            normalization_mode: 'detrend',
            eval_mode: 'held_out',
            data_source: 'local',
            lookback: 256,
            pred_len: 24,
            sample_count: 5,
            window_offset: 1,
            include_confluence: true,
            companion_symbol: 'I:VIX',
        },
        {
            id: 'spy_1h_vixy',
            label: '2. SPY 23-Yr + VIXY Futures ETF Confluence (1h)',
            ticker: 'SPY',
            model_key: 'SPY_23yr_multi_tf',
            timeframe: '1hour',
            normalization_mode: 'detrend',
            eval_mode: 'held_out',
            data_source: 'local',
            lookback: 256,
            pred_len: 24,
            sample_count: 5,
            window_offset: 1,
            include_confluence: true,
            companion_symbol: 'VIXY',
        },
        {
            id: 'spy_1h_live_forward',
            label: '3. SPY 23-Yr Live Polygon Forward + GEX Walls (1h)',
            ticker: 'SPY',
            model_key: 'SPY_23yr_multi_tf',
            timeframe: '1hour',
            normalization_mode: 'detrend',
            eval_mode: 'future',
            data_source: 'live',
            lookback: 256,
            pred_len: 24,
            sample_count: 5,
            window_offset: 1,
            include_confluence: true,
            companion_symbol: 'I:VIX',
        },
        {
            id: 'spy_5m_scalper',
            label: '4. SPY 23-Yr Intraday 5m Scalper & 0DTE Options',
            ticker: 'SPY',
            model_key: 'SPY_23yr_multi_tf',
            timeframe: '5min',
            normalization_mode: 'last_price_anchor',
            eval_mode: 'held_out',
            data_source: 'local',
            lookback: 256,
            pred_len: 24,
            sample_count: 5,
            window_offset: 1,
            include_confluence: true,
            companion_symbol: 'I:VIX',
        },
        {
            id: 'spy_5m_specialist',
            label: '5. SPY Dedicated 5-Min Intraday Specialist (5m)',
            ticker: 'SPY',
            model_key: 'SPY_5min_intraday',
            timeframe: '5min',
            normalization_mode: 'last_price_anchor',
            eval_mode: 'held_out',
            data_source: 'local',
            lookback: 256,
            pred_len: 24,
            sample_count: 5,
            window_offset: 1,
            include_confluence: true,
            companion_symbol: 'VIXY',
        },
        {
            id: 'spy_1d_macro',
            label: '6. SPY 23-Yr Daily Macro Position & LEAPS (1d)',
            ticker: 'SPY',
            model_key: 'SPY_23yr_multi_tf',
            timeframe: '1day',
            normalization_mode: 'detrend',
            eval_mode: 'held_out',
            data_source: 'local',
            lookback: 256,
            pred_len: 20,
            sample_count: 5,
            window_offset: 1,
            include_confluence: true,
            companion_symbol: 'I:VIX',
        },
        {
            id: 'spy_1h_20yr_bench',
            label: '7. SPY 20-Yr Pre-2025 Legacy Benchmark (1h)',
            ticker: 'SPY',
            model_key: 'SPY_20yr_multi_timeframe',
            timeframe: '1hour',
            normalization_mode: 'detrend',
            eval_mode: 'held_out',
            data_source: 'local',
            lookback: 256,
            pred_len: 24,
            sample_count: 5,
            window_offset: 1,
            include_confluence: true,
            companion_symbol: 'I:VIX',
        },
    ];

    async function runAllSpySetups() {
        const allBtn = document.getElementById('lab-run-all-spy-btn');
        const status = document.getElementById('lab-status-msg');
        const matrixSec = document.getElementById('spy-setups-matrix-section');
        const tbody = document.getElementById('spy-setups-matrix-tbody');
        if (!tbody || !matrixSec) return;

        if (allBtn) allBtn.disabled = true;
        matrixSec.style.display = 'block';
        tbody.innerHTML = '';

        let completed = 0;
        let firstResult = null;

        for (const setup of SPY_ALL_SETUPS) {
            status.innerHTML = `🚀 Running SPY Setup <strong>${completed + 1}/${SPY_ALL_SETUPS.length}</strong>: <code>${setup.label}</code>...`;
            try {
                const res = await apiJson('/api/testing/run-analysis', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(setup),
                });
                spySetupResultsCache.set(setup.id, { setup, res });
                if (!firstResult) {
                    firstResult = res;
                    await displayAnalysisResponse(firstResult);
                }
                completed++;

                const s = res.summary || {};
                const conf = res.confluence || {};
                const predRet = s.predicted_return_pct;
                const actRet = res.actual_return_pct;
                const hitBadge = s.direction_hit === true
                    ? '<span class="hub-badge badge-success">✅ HIT</span>'
                    : s.direction_hit === false
                        ? '<span class="hub-badge badge-danger">❌ MISS</span>'
                        : '<span class="hub-badge badge-info">LIVE FWD</span>';

                const skillStr = s.mae_skill_pct != null ? ` • Skill ${s.mae_skill_pct >= 0 ? '+' : ''}${fmtNum(s.mae_skill_pct, 0, '', '%')}` : '';
                const maeCell = s.mae != null
                    ? `${fmtNum(s.mae, 2, '$')} (${fmtNum(s.mape_pct, 2, '', '%')}${skillStr})`
                    : `${fmtNum(s.env_low_min, 2, '$')}–${fmtNum(s.env_high_max, 2, '$')}`;

                const tr = document.createElement('tr');
                if (completed === 1) tr.style.background = 'rgba(0, 245, 212, 0.08)';
                tr.innerHTML = `
                    <th><strong>${setup.label}</strong></th>
                    <td><code>${setup.model_key}</code></td>
                    <td>${setup.timeframe} (${setup.eval_mode === 'future' || setup.data_source === 'live' ? 'Live' : 'Holdout'})</td>
                    <td><code>${setup.normalization_mode}</code></td>
                    <td>${fmtNum(s.last_close, 2, '$')} &rarr; <strong>${fmtNum(s.predicted_close, 2, '$')}</strong></td>
                    <td><strong style="color:${predRet >= 0 ? '#00f5d4' : '#ff2a85'}">${predRet >= 0 ? '+' : ''}${fmtNum(predRet, 2, '', '%')}</strong></td>
                    <td>${actRet != null ? `${actRet >= 0 ? '+' : ''}${fmtNum(actRet, 2, '', '%')}` : 'Live Forward'}</td>
                    <td>${hitBadge}</td>
                    <td>${conf.companion_symbol ? `<strong>${conf.companion_symbol}</strong> (${conf.vix_return_pct >= 0 ? '+' : ''}${fmtNum(conf.vix_return_pct, 2, '', '%')})` : '-'}</td>
                    <td>${conf.signal ? `<code>${conf.signal}</code>` : '-'}</td>
                    <td>${maeCell}</td>
                    <td>#${res.saved_run_id || 'N/A'}</td>
                    <td><button type="button" class="ticker-pill" data-view-spy-setup="${setup.id}">🔍 View Chart</button></td>
                `;
                tbody.appendChild(tr);
            } catch (err) {
                const tr = document.createElement('tr');
                tr.innerHTML = `
                    <th><strong>${setup.label}</strong></th>
                    <td><code>${setup.model_key}</code></td>
                    <td>${setup.timeframe}</td>
                    <td colspan="10" style="color:#ff2a85;">❌ Error: ${err.message}</td>
                `;
                tbody.appendChild(tr);
            }
        }

        // Bind "View Chart" buttons on each row
        tbody.querySelectorAll('[data-view-spy-setup]').forEach(btn => {
            btn.addEventListener('click', async () => {
                const setupId = btn.getAttribute('data-view-spy-setup');
                const cached = spySetupResultsCache.get(setupId);
                if (!cached) return;
                tbody.querySelectorAll('tr').forEach(r => { r.style.background = ''; });
                const row = btn.closest('tr');
                if (row) row.style.background = 'rgba(0, 245, 212, 0.08)';
                await displayAnalysisResponse(cached.res);
                status.innerHTML = `📊 Viewing cached SPY Setup: <strong>${cached.setup.label}</strong> (Run ID #${cached.res.saved_run_id || 'N/A'})`;
            });
        });

        if (firstResult) {
            await displayAnalysisResponse(firstResult);
        }
        status.innerHTML = `✅ Executed all <strong>${completed}/${SPY_ALL_SETUPS.length} SPY Setups</strong> and saved every run to PostgreSQL <code>kronos_research</code>. Click any row's <strong>🔍 View Chart</strong> button to inspect its chart.`;
        refreshPostgresHistory();
        if (allBtn) allBtn.disabled = false;
    }

    document.getElementById('lab-run-all-spy-btn')?.addEventListener('click', runAllSpySetups);

    // =========================================================================
    // TAB 2: OPTIONS CHAIN, GEX & UNDERLYING INTEL
    // =========================================================================
    async function pullOptionsAndUnderlying() {
        const btn = document.getElementById('opt-fetch-btn');
        const status = document.getElementById('opt-status-msg');
        const ticker = document.getElementById('opt-ticker').value.trim().toUpperCase();
        const expDate = document.getElementById('opt-expiration').value;
        const strikePct = Number(document.getElementById('opt-strike-pct').value) / 100.0;
        const maxDaysOut = Number(document.getElementById('opt-days-out').value);

        btn.disabled = true;
        status.textContent = `Fetching Polygon live Options Chain, Greeks, IV Skew, and Underlying Technicals for ${ticker}...`;

        try {
            const [undRes, optRes] = await Promise.all([
                apiJson('/api/testing/underlying', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ ticker, save_to_db: true }),
                }),
                apiJson('/api/testing/options-chain', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        ticker,
                        expiration_date: expDate || null,
                        strike_window_pct: strikePct,
                        max_days_out: maxDaysOut,
                        save_to_db: true,
                    }),
                }),
            ]);

            const u = undRes.underlying || {};
            const o = optRes.summary || {};

            const expSel = document.getElementById('opt-expiration');
            if (expSel && o.expirations && o.expirations.length) {
                const prevVal = expSel.value;
                expSel.innerHTML = '<option value="">All Near-Term Expirations</option>';
                o.expirations.forEach(exp => {
                    const op = document.createElement('option');
                    op.value = exp;
                    op.textContent = exp;
                    expSel.appendChild(op);
                });
                if (o.expirations.includes(prevVal)) expSel.value = prevVal;
            }

            document.getElementById('opt-kpi-grid').style.display = 'grid';

            const chgSign = (u.today_change_pct || 0) >= 0 ? '+' : '';
            document.getElementById('opt-spot-val').textContent = `${fmtNum(u.price || o.underlying_price, 2, '$')} (${chgSign}${fmtNum(u.today_change_pct, 2, '', '%')})`;
            document.getElementById('opt-bid-ask').textContent = `Bid/Ask: ${fmtNum(u.bid, 2, '$')} / ${fmtNum(u.ask, 2, '$')} | VWAP: ${fmtNum(u.day_vwap, 2, '$')}`;

            document.getElementById('opt-pc-ratio').textContent = `OI P/C: ${fmtNum(o.put_call_oi_ratio, 2)} | Vol P/C: ${fmtNum(o.put_call_vol_ratio, 2)}`;
            document.getElementById('opt-oi-totals').textContent = `Call OI: ${fmtInt(o.total_call_oi)} | Put OI: ${fmtInt(o.total_put_oi)}`;

            document.getElementById('opt-max-pain').textContent = `Max Pain: ${fmtNum(o.max_pain_strike, 1, '$')}`;
            document.getElementById('opt-walls').textContent = `Call Wall: ${fmtNum(o.call_wall_strike, 1, '$')} | Put Wall: ${fmtNum(o.put_wall_strike, 1, '$')}`;

            document.getElementById('opt-atm-iv').textContent = `ATM IV: ${fmtNum(o.atm_iv, 1, '', '%')}`;
            document.getElementById('opt-iv-skew').textContent = `25Δ Skew: ${fmtNum(o.iv_skew_25d, 2, '', '%')} | Call/Put IV: ${fmtNum(o.avg_call_iv, 1, '', '%')}/${fmtNum(o.avg_put_iv, 1, '', '%')}`;

            document.getElementById('opt-net-gex').textContent = `Net GEX: ${fmtNum((o.net_gamma_exposure || 0) / 1e6, 2, '$', 'M')}`;
            document.getElementById('opt-net-dex').textContent = `Net DEX: ${fmtNum((o.net_delta_exposure || 0) / 1e6, 1, '$', 'M')} (${fmtInt(o.contracts_count)} contracts)`;

            document.getElementById('opt-rsi-val').textContent = `RSI(14): ${fmtNum(u.rsi_14, 1)}`;
            document.getElementById('opt-macd-sma').textContent = `MACD: ${fmtNum(u.macd_val, 2)} | SMA20: ${fmtNum(u.sma_20, 2, '$')}`;

            // Render Full-Width Options / GEX / IV Smile Charts with Safe Responsive Renderer
            if (optRes.charts) {
                const fig1 = JSON.parse(optRes.charts.oi_gex_chart);
                const fig2 = JSON.parse(optRes.charts.iv_smile_chart);
                await renderChartSafely('opt-oi-gex-chart', fig1, {
                    focusRange: fig1.layout?.xaxis?.range,
                });
                await renderChartSafely('opt-iv-smile-chart', fig2, {
                    focusRange: fig2.layout?.xaxis?.range,
                });
            }

            // Populate Top Active Contracts Table
            const cTbody = document.getElementById('opt-contracts-tbody');
            cTbody.innerHTML = '';
            (o.top_active_contracts || []).forEach(c => {
                const tr = document.createElement('tr');
                const badgeClass = c.contract_type === 'call' ? 'badge-success' : 'badge-danger';
                tr.innerHTML = `
                    <th><code>${c.contract_ticker}</code></th>
                    <td><span class="hub-badge ${badgeClass}">${c.contract_type.toUpperCase()}</span></td>
                    <td>${c.expiration_date}</td>
                    <td><strong>${fmtNum(c.strike_price, 2, '$')}</strong></td>
                    <td>${fmtNum(c.last_price ?? c.midpoint, 2, '$')}</td>
                    <td>${fmtNum(c.bid, 2, '$')} / ${fmtNum(c.ask, 2, '$')}</td>
                    <td><strong>${fmtInt(c.volume)}</strong></td>
                    <td>${fmtInt(c.open_interest)}</td>
                    <td>${fmtNum(c.implied_volatility_pct, 1, '', '%')}</td>
                    <td>${fmtNum(c.delta, 3)}</td>
                    <td>${fmtNum(c.gamma, 4)}</td>
                    <td>${fmtNum(c.theta, 3)}</td>
                    <td>${fmtNum(c.gex_dollars, 0, '$')}</td>
                `;
                cTbody.appendChild(tr);
            });

            // Populate Company Description & News
            const newsSec = document.getElementById('opt-news-section');
            const newsList = document.getElementById('opt-news-list');
            const descEl = document.getElementById('opt-company-desc');
            if (u.description || (u.news && u.news.length)) {
                newsSec.style.display = 'block';
                descEl.textContent = `${u.company_name || ticker} (${u.primary_exchange || 'US'}) — ${u.sic_description || ''} ${u.description ? '• ' + u.description : ''}`;
                newsList.innerHTML = '';
                (u.news || []).forEach(n => {
                    const card = document.createElement('div');
                    card.className = 'hub-news-card';
                    card.innerHTML = `
                        <a href="${n.article_url || '#'}" target="_blank" rel="noopener noreferrer">${n.title}</a>
                        <div class="hub-news-meta">${n.publisher} • ${n.published_utc ? new Date(n.published_utc).toLocaleString() : ''}</div>
                    `;
                    newsList.appendChild(card);
                });
            }

            status.innerHTML = `✅ Pulled &amp; stored <strong>${fmtInt(optRes.contracts_stored)}</strong> option contracts (Snapshot #${o.saved_snapshot_id || 'N/A'}) and underlying snapshot (#${u.saved_snapshot_id || 'N/A'}) into PostgreSQL <code>kronos_research</code>.`;
            refreshPostgresHistory();
        } catch (err) {
            status.textContent = `❌ Options/Underlying fetch failed: ${err.message}`;
        } finally {
            btn.disabled = false;
        }
    }

    document.getElementById('opt-fetch-btn')?.addEventListener('click', pullOptionsAndUnderlying);

    // =========================================================================
    // TAB 3: RUN ROLLING WALK-FORWARD BACKTEST
    // =========================================================================
    async function runRollingBacktest() {
        const btn = document.getElementById('bt-run-btn');
        const status = document.getElementById('bt-status-msg');
        const ticker = document.getElementById('bt-ticker').value;
        const timeframe = document.getElementById('bt-timeframe').value;
        const companion = document.getElementById('bt-companion')?.value || 'I:VIX';
        const numWindows = Number(document.getElementById('bt-windows').value);
        const horizon = Number(document.getElementById('bt-horizon').value);
        const sampleCount = Number(document.getElementById('bt-samples').value);

        btn.disabled = true;
        status.textContent = `Running ${numWindows}-window walk-forward evaluation on ${ticker} (${timeframe}, horizon=${horizon} bars, companion=${companion})...`;

        try {
            const res = await apiJson('/api/testing/run-backtest', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    ticker,
                    timeframe,
                    companion_symbol: companion,
                    num_windows: numWindows,
                    horizon,
                    sample_count: sampleCount,
                }),
            });

            const bt = res.backtest || {};
            const btKpiGrid = document.getElementById('bt-kpi-grid');
            if (btKpiGrid) {
                btKpiGrid.style.display = 'grid';
                document.getElementById('bt-kpi-acc').textContent = `${fmtNum(bt.direction_accuracy_pct, 1, '', '%')} (${bt.direction_hits}/${bt.total_valid_windows})`;
                document.getElementById('bt-kpi-ci').textContent = `95% Wilson CI: [${fmtNum(bt.ci_95_low_pct, 1, '', '%')}, ${fmtNum(bt.ci_95_high_pct, 1, '', '%')}] • p=${fmtNum(bt.p_value, 4)}`;

                if (bt.confirmed_accuracy_pct != null) {
                    document.getElementById('bt-kpi-conf').textContent = `${fmtNum(bt.confirmed_accuracy_pct, 1, '', '%')} (${bt.confirmed_hits}/${bt.confirmed_trades})`;
                    document.getElementById('bt-kpi-conf-sub').textContent = `${bt.companion_symbol || companion} Confirmed • p=${fmtNum(bt.confirmed_p_value, 4)}`;
                } else {
                    document.getElementById('bt-kpi-conf').textContent = 'Unfiltered Mode';
                    document.getElementById('bt-kpi-conf-sub').textContent = `Always-Long Baseline: ${fmtNum(bt.always_long_accuracy_pct, 1, '', '%')}`;
                }

                document.getElementById('bt-kpi-mae').textContent = `${fmtNum(bt.avg_mae, 2, '$')} (${fmtNum(bt.avg_mape_pct, 2, '', '%')})`;
                const skSign = (bt.skill_vs_naive_pct || 0) >= 0 ? '+' : '';
                document.getElementById('bt-kpi-skill').textContent = `Naive RW MAE: ${fmtNum(bt.avg_naive_mae, 2, '$')} • Skill: ${skSign}${fmtNum(bt.skill_vs_naive_pct, 1, '', '%')}`;

                const stratSign = (bt.cum_strategy_return_pct || 0) >= 0 ? '+' : '';
                const bhSign = (bt.cum_buy_hold_return_pct || 0) >= 0 ? '+' : '';
                document.getElementById('bt-kpi-strat').textContent = `${stratSign}${fmtNum(bt.cum_strategy_return_pct, 2, '', '%')}`;
                document.getElementById('bt-kpi-bh').textContent = `Buy & Hold: ${bhSign}${fmtNum(bt.cum_buy_hold_return_pct, 2, '', '%')} • ${fmtNum(bt.elapsed_ms, 0, '', 'ms')}`;
            }

            const fig = JSON.parse(res.chart);
            await renderChartSafely('bt-chart-container', fig);

            const confTxt = bt.confirmed_accuracy_pct != null
                ? ` | VIX Confirmed: <strong>${bt.confirmed_hits}/${bt.confirmed_trades} (${fmtNum(bt.confirmed_accuracy_pct, 1, '', '%')})</strong>`
                : '';
            status.innerHTML = `✅ Walk-Forward Backtest complete for <strong>${ticker} (${timeframe})</strong>: <strong>${bt.direction_hits}/${bt.total_valid_windows} (${fmtNum(bt.direction_accuracy_pct, 1, '', '%')})</strong> direction accuracy (95% CI [${fmtNum(bt.ci_95_low_pct, 1, '', '%')}, ${fmtNum(bt.ci_95_high_pct, 1, '', '%')}], p=${fmtNum(bt.p_value, 4)})${confTxt} | Avg MAE: ${fmtNum(bt.avg_mae, 2, '$')} (Skill vs RW: ${(bt.skill_vs_naive_pct || 0) >= 0 ? '+' : ''}${fmtNum(bt.skill_vs_naive_pct, 1, '', '%')}). Saved to Postgres (Backtest ID #${res.saved_backtest_id || 'N/A'}).`;
            refreshPostgresHistory();
        } catch (err) {
            status.textContent = `❌ Backtest failed: ${err.message}`;
        } finally {
            btn.disabled = false;
        }
    }

    document.getElementById('bt-run-btn')?.addEventListener('click', runRollingBacktest);

    // =========================================================================
    // TAB 4: POSTGRESQL RESEARCH VAULT EXPLORER
    // =========================================================================
    async function refreshPostgresHistory() {
        const filterTicker = document.getElementById('pg-filter-ticker')?.value.trim().toUpperCase() || '';
        const q = filterTicker ? `?ticker=${encodeURIComponent(filterTicker)}&limit=40` : '?limit=40';
        try {
            const res = await apiJson(`/api/testing/db-history${q}`);
            updatePostgresExplorer(res.database);
        } catch (err) {
            console.error('Failed refreshing Postgres history:', err);
        }
    }

    function updatePostgresExplorer(db) {
        if (!db) return;
        const pgBadge = document.getElementById('pg-status-badge');
        const totalSpan = document.getElementById('pg-total-records');
        const countsSummary = document.getElementById('pg-counts-summary');

        const counts = db.counts || {};
        const totalRows = Object.values(counts).reduce((acc, v) => acc + (Number(v) || 0), 0);

        if (pgBadge) {
            if (db.connected) {
                pgBadge.textContent = `Postgres: kronos_research (${fmtInt(totalRows)} rows)`;
                pgBadge.className = 'hub-badge badge-success';
            } else {
                pgBadge.textContent = 'Postgres: Disconnected';
                pgBadge.className = 'hub-badge badge-danger';
            }
        }
        if (totalSpan) totalSpan.textContent = fmtInt(totalRows);
        if (countsSummary) {
            countsSummary.textContent = `Models: ${fmtInt(counts.tuned_models_registry)} | Forecasts: ${fmtInt(counts.model_forecast_runs)} | Backtests: ${fmtInt(counts.model_backtest_runs)} | Options Chains: ${fmtInt(counts.options_chain_snapshots)} | Option Quotes: ${fmtInt(counts.options_contracts_quotes)} | Underlyings: ${fmtInt(counts.underlying_snapshots)}`;
        }

        // 1. Forecasts table
        const fTbody = document.getElementById('pg-forecasts-tbody');
        if (fTbody) {
            const rows = db.recent_forecasts || [];
            fTbody.innerHTML = rows.length ? '' : '<tr><td colspan="13">No forecast runs stored yet. Run an analysis in Tab 1!</td></tr>';
            rows.forEach(r => {
                const tr = document.createElement('tr');
                const hitBadge = r.direction_hit === true ? '<span class="hub-badge badge-success">HIT</span>' : r.direction_hit === false ? '<span class="hub-badge badge-danger">MISS</span>' : '-';
                tr.innerHTML = `
                    <th>#${r.id}</th>
                    <td>${r.created_at ? new Date(r.created_at).toLocaleString() : '-'}</td>
                    <td><strong>${r.ticker}</strong></td>
                    <td><code>${r.model_key}</code></td>
                    <td>${r.interval_minutes}m</td>
                    <td>${r.normalization_mode}</td>
                    <td>${fmtNum(r.last_close, 2, '$')}</td>
                    <td>${fmtNum(r.predicted_close, 2, '$')}</td>
                    <td><strong>${r.predicted_return_pct >= 0 ? '+' : ''}${fmtNum(r.predicted_return_pct, 2, '', '%')}</strong></td>
                    <td>${r.confluence_signal || '-'}</td>
                    <td>${fmtNum(r.mae, 2, '$')}</td>
                    <td>${fmtNum(r.mape_pct, 2, '', '%')}</td>
                    <td>${hitBadge}</td>
                `;
                fTbody.appendChild(tr);
            });
        }

        // 2. Options Chain Snapshots table
        const oTbody = document.getElementById('pg-options-tbody');
        if (oTbody) {
            const rows = db.recent_options || [];
            oTbody.innerHTML = rows.length ? '' : '<tr><td colspan="13">No options snapshots stored yet. Pull Options Chain in Tab 2!</td></tr>';
            rows.forEach(r => {
                const tr = document.createElement('tr');
                tr.innerHTML = `
                    <th>#${r.id}</th>
                    <td>${r.captured_at ? new Date(r.captured_at).toLocaleString() : '-'}</td>
                    <td><strong>${r.ticker}</strong></td>
                    <td>${fmtNum(r.underlying_price, 2, '$')}</td>
                    <td>${fmtInt(r.contracts_count)}</td>
                    <td>${fmtInt(r.total_call_oi)}</td>
                    <td>${fmtInt(r.total_put_oi)}</td>
                    <td><strong>${fmtNum(r.put_call_oi_ratio, 2)}</strong></td>
                    <td>${fmtNum(r.atm_iv, 1, '', '%')}</td>
                    <td>${fmtNum(r.iv_skew_25d, 2, '', '%')}</td>
                    <td>${fmtNum(r.max_pain_strike, 1, '$')}</td>
                    <td>${fmtNum(r.call_wall_strike, 0, '$')} / ${fmtNum(r.put_wall_strike, 0, '$')}</td>
                    <td>${fmtNum((r.net_gamma_exposure || 0) / 1e6, 2, '$', 'M')}</td>
                `;
                oTbody.appendChild(tr);
            });
        }

        // 3. Backtests table
        const bTbody = document.getElementById('pg-backtests-tbody');
        if (bTbody) {
            const rows = db.recent_backtests || [];
            bTbody.innerHTML = rows.length ? '' : '<tr><td colspan="12">No backtest runs stored yet.</td></tr>';
            rows.forEach(r => {
                const tr = document.createElement('tr');
                tr.innerHTML = `
                    <th>#${r.id}</th>
                    <td>${r.created_at ? new Date(r.created_at).toLocaleString() : '-'}</td>
                    <td><strong>${r.ticker}</strong></td>
                    <td><code>${r.model_key}</code></td>
                    <td>${r.companion_model_key || '-'}</td>
                    <td>${r.timeframe}</td>
                    <td>${r.total_valid_windows}</td>
                    <td><strong>${fmtNum(r.direction_accuracy_pct, 1, '', '%')}</strong> (${r.direction_hits}/${r.total_valid_windows})</td>
                    <td>${r.confirmed_accuracy_pct != null ? `<strong>${fmtNum(r.confirmed_accuracy_pct, 1, '', '%')}</strong> (${r.confirmed_hits}/${r.confirmed_trades})` : '-'}</td>
                    <td>${fmtNum(r.avg_mae, 2, '$')}</td>
                    <td>${fmtNum(r.p_value, 4)}</td>
                    <td>${r.notes || ''}</td>
                `;
                bTbody.appendChild(tr);
            });
        }

        // 4. Underlyings table
        const uTbody = document.getElementById('pg-underlyings-tbody');
        if (uTbody) {
            const rows = db.recent_underlyings || [];
            uTbody.innerHTML = rows.length ? '' : '<tr><td colspan="12">No underlying snapshots stored yet.</td></tr>';
            rows.forEach(r => {
                const tr = document.createElement('tr');
                tr.innerHTML = `
                    <th>#${r.id}</th>
                    <td>${r.captured_at ? new Date(r.captured_at).toLocaleString() : '-'}</td>
                    <td><strong>${r.ticker}</strong></td>
                    <td>${fmtNum(r.price, 2, '$')}</td>
                    <td>${fmtNum(r.today_change_pct, 2, '', '%')}</td>
                    <td>${fmtInt(r.day_volume)}</td>
                    <td>${fmtNum(r.day_vwap, 2, '$')}</td>
                    <td>${fmtNum(r.bid, 2, '$')} / ${fmtNum(r.ask, 2, '$')}</td>
                    <td>${fmtNum(r.rsi_14, 1)}</td>
                    <td>${fmtNum(r.sma_20, 2, '$')}</td>
                    <td>${fmtNum(r.ema_20, 2, '$')}</td>
                    <td>${fmtNum(r.macd_val, 2)} / ${fmtNum(r.macd_signal, 2)}</td>
                `;
                uTbody.appendChild(tr);
            });
        }
    }

    document.getElementById('pg-refresh-btn')?.addEventListener('click', refreshPostgresHistory);

    // Initialize overview & auto-populate SPY analysis + SPY Options Chain/GEX + SPY Walk-Forward Backtest on startup
    (async () => {
        await loadTestingOverview();
        // Auto-load SPY Options Chain & GEX in background so Tab 2 is ready immediately when clicked
        pullOptionsAndUnderlying();
        // Auto-load SPY Walk-Forward Backtest in background so Tab 3 is ready immediately when clicked
        runRollingBacktest();
        // Auto-run all 7 SPY setups so Tab 1 has the complete SPY setup matrix + chart ready
        runAllSpySetups();
    })();
});
