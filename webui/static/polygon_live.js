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

    function stop(message) {
        active = false;
        clearTimeout(timer);
        timer = null;
        refreshButton.textContent = 'Start 60-second refresh';
        if (message) status.textContent += '\n' + message;
    }

    function parameters() {
        return {ticker: ticker.value.trim().toUpperCase(), interval: Number(interval.value)};
    }

    async function requestJson(url, options = {}) {
        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), 120000);
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
        return `${info.ticker} | ${info.interval_minutes}-minute candles | ${info.rows} completed bars\n` +
            `Latest close: $${info.last_close.toFixed(2)} | Latest bar: ${bar.toLocaleString()}\n` +
            `Data fetched: ${fetched.toLocaleString()} | Regular market ${info.market_open ? 'open' : 'closed'}\n` +
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
                forecastNote.textContent = 'Saved forecast: ' + result.saved_file + '. Forecast anchor: ' + new Date(result.forecast_anchor).toLocaleString() + '.';
            } else {
                forecastNote.textContent = 'Latest available candles. Click Forecast latest candles to generate a new forecast.';
            }
            const figure = JSON.parse(result.chart);
            await Plotly.newPlot('live-chart', figure.data, figure.layout, {responsive: true});
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
        status.textContent = info.configured ? 'Polygon key configured on server. Ready to fetch SPY.' : 'Add POLYGON_API_KEY to the project .env, then fetch again.';
    }).catch(error => { status.textContent = error.message; });
});
