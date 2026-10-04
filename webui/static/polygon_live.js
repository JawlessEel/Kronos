/* Credentials stay on the local server. This page only sends symbol and settings. */
document.addEventListener('DOMContentLoaded', () => {
    const status = document.getElementById('live-status');
    const ticker = document.getElementById('live-ticker');
    const interval = document.getElementById('live-interval');
    const fetchButton = document.getElementById('live-fetch');
    const refreshButton = document.getElementById('live-refresh');
    const predictButton = document.getElementById('live-predict');
    const forecastNote = document.getElementById('live-forecast-note');
    let timer = null;
    let active = false;
    let busy = false;
    let failures = 0;
    let cycles = 0;
    const controlIds = ['model-select', 'device-select', 'live-ticker', 'live-interval', 'live-history', 'live-lookback', 'live-horizon', 'lookback', 'pred-len', 'temperature', 'top-p', 'sample-count'];
    const modelSelect = document.querySelector('label[for="model-select"]') ? document.getElementById('model-select') : document.querySelector('select[id*="model"]');
    function modelLimits() {
        const limit = modelSelect.value === 'kronos-mini' ? 2048 : 512;
        ['live-lookback','live-horizon','lookback','pred-len'].forEach(id => {
            const control = document.getElementById(id); control.max = limit;
            if (Number(control.value) > limit) control.value = limit;
        });
        document.getElementById('model-context-note').textContent = `Selected model context: ${limit.toLocaleString()} candles. Load the selected model before forecasting. Chart history is independent.`;
    }
    function restoreControls() { try {
        const saved = JSON.parse(localStorage.getItem('kronos-forecast-controls-v1') || '{}');
        document.getElementById('control-save-note').textContent = Object.keys(saved).length ? 'Saved control preferences restored.' : 'Control preferences use local browser storage.';
        controlIds.forEach(id => {
            const control = document.getElementById(id);
            if (!control || typeof saved[id] !== 'string') return;
            if (control.tagName === 'SELECT' && !Array.from(control.options).some(option => option.value === saved[id] && !option.disabled)) return;
            if (control.type === 'number' || control.type === 'range') {
                const value = Number(saved[id]); if (!Number.isFinite(value) || value < Number(control.min) || value > Number(control.max)) return;
            }
            control.value = saved[id];
            if (id === 'model-select') modelLimits();
        });
    } catch { /* Leave defaults when local settings are invalid. */ } }
    restoreControls();
    function samplingLabels() {
        document.getElementById('temperature-value').textContent = document.getElementById('temperature').value;
        document.getElementById('top-p-value').textContent = document.getElementById('top-p').value;
    }
    samplingLabels();
    document.addEventListener('kronos-models-ready', () => { restoreControls(); modelLimits(); samplingLabels(); });
    modelLimits();
    function saveControls() {
        modelLimits();
        const saved = Object.fromEntries(controlIds.filter(id=>document.getElementById(id)).map(id=>[id,document.getElementById(id).value]));
        try { localStorage.setItem('kronos-forecast-controls-v1', JSON.stringify(saved)); document.getElementById('control-save-note').textContent = 'Control preferences saved locally.'; } catch { status.textContent = 'Browser storage is unavailable; controls will not persist after reload.'; }
    }
    controlIds.forEach(id => {
        const control=document.getElementById(id);
        control?.addEventListener('change',saveControls);
        if(control?.tagName==='INPUT') control.addEventListener('input',saveControls);
    });

    function stop(message) {
        active = false;
        clearTimeout(timer);
        timer = null;
        refreshButton.textContent = 'Start 60-second refresh';
        if (message) status.textContent += '\n' + message;
    }

    function parameters() {
        return {ticker: ticker.value.trim().toUpperCase(), interval: Number(interval.value), history: Number(document.getElementById('live-history').value)};
    }

    async function requestJson(url, options = {}) {
        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), 600000);
        try {
            const response = await fetch(url, {...options, signal: controller.signal});
            const payload = await response.json();
            if (!response.ok) throw new Error(payload.error || 'Market data request failed.');
            return payload;
        } finally {
            clearTimeout(timeout);
        }
    }

    function describe(info) {
        const bar = new Date(info.last_candle);
        const fetched = new Date(info.fetched_at);
        const label = {60:'1-hour',240:'4-hour',1440:'1-day'}[info.interval_minutes] || `${info.interval_minutes}-minute`;
        const format = date => date.toLocaleString('en-US',{timeZone:info.timezone||'America/New_York',timeZoneName:'short'});
        return `${info.ticker} | ${label} candles | ${info.rows} completed bars\n` +
            `Latest close: $${info.last_close.toFixed(2)} | Latest bar: ${format(bar)}\n` +
            `Data fetched: ${format(fetched)} | ${info.market==='crypto'?'Crypto market open 24/7':`Regular market ${info.market_open ? 'open' : 'closed'}`}\n${info.session}\n` +
            info.delay_notice;
    }

    async function refresh(forecast = false) {
        if (busy) return;
        busy = true;
        fetchButton.disabled = true;
        predictButton.disabled = true;
        status.textContent = forecast ? 'Generating forecast from latest available candles...' : 'Fetching Polygon candles...';
        try {
            const args = parameters();
            let result;
            if (forecast) {
                result = await requestJson('/api/live/predict', {
                    method: 'POST', headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({...args,
                        pred_len: Number(document.getElementById('live-horizon').value),
                        lookback: Number(document.getElementById('live-lookback').value),
                        temperature: Number(document.getElementById('temperature').value),
                        top_p: Number(document.getElementById('top-p').value),
                        sample_count: Number(document.getElementById('sample-count').value)})
                });
            } else {
                result = await requestJson('/api/live/candles?' + new URLSearchParams(args));
            }
            status.textContent = describe(result.feed);
            if (forecast) {
                status.textContent += '\n' + result.message;
                forecastNote.textContent = 'Saved forecast: ' + result.saved_file + '. Forecast anchor: ' + new Date(result.forecast_anchor).toLocaleString('en-US',{timeZone:result.feed.timezone||'America/New_York',timeZoneName:'short'}) + '.';
            } else {
                forecastNote.textContent = 'Latest available candles. Click Forecast latest candles to generate a new forecast.';
            }
            const figure = JSON.parse(result.chart);
            await ChartWorkbench.render('live-chart', figure, result);
            PredictionCandles.render('live-candle-data', result);
            failures = 0;
        } catch (error) {
            failures += 1;
            status.textContent = error.name === 'AbortError' ? 'Request timed out; try again later.' : error.message;
            forecastNote.textContent = 'Previous chart retained; the most recent request failed.';
            if (failures >= 3) stop('Refresh stopped after three consecutive errors.');
        } finally {
            busy = false;
            fetchButton.disabled = false;
            predictButton.disabled = false;
        }
    }

    async function cycle() {
        if (!active) return;
        if (document.hidden) return stop('Refresh stopped because the page is hidden.');
        await refresh();
        cycles += 1;
        if (cycles >= 240) return stop('Four-hour refresh session completed.');
        if (active) timer = setTimeout(cycle, 60000);
    }

    fetchButton.addEventListener('click', () => refresh());
    predictButton.addEventListener('click', () => refresh(true));
    refreshButton.addEventListener('click', () => {
        if (active) return stop('Auto-refresh stopped.');
        active = true;
        cycles = 0;
        failures = 0;
        refreshButton.textContent = 'Stop refresh';
        cycle();
    });
    document.addEventListener('visibilitychange', () => {
        if (document.hidden && active) stop('Refresh stopped because the page is hidden.');
    });
    [ticker, interval].forEach(control => control.addEventListener('change', () => stop('Feed selection changed; fetch to update the chart.')));
    requestJson('/api/live/status').then(info => {
        status.textContent = info.configured ? 'Polygon key configured. Choose a stock or X: crypto pair and timeframe, then fetch.' : 'Add POLYGON_API_KEY to the project .env, then fetch again.';
    }).catch(error => { status.textContent = error.message; });
});
