/* Indicator calculations use full periods; unavailable warm-up values stay null. */
(function (root) {
    const finite = x => typeof x === 'number' && Number.isFinite(x);
    function average(values, period, type = 'SMA') {
        const out = Array(values.length).fill(null);
        let sum = 0, weighted = 0, run = 0, previous = null;
        values.forEach((value, i) => {
            if (!finite(value)) { sum = weighted = run = 0; previous = null; return; }
            run++;
            if (run <= period) { sum += value; weighted += run * value; }
            else { weighted = weighted - sum + period * value; sum += value - values[i - period]; }
            if (run < period) return;
            if (type === 'EMA' || type === 'RMA') {
                const alpha = type === 'EMA' ? 2 / (period + 1) : 1 / period;
                previous = previous === null ? sum / period : alpha * value + (1 - alpha) * previous;
                out[i] = previous;
            } else out[i] = type === 'WMA' ? weighted / (period * (period + 1) / 2) : sum / period;
        });
        return out;
    }
    function source(bar, name) {
        if (name === 'hl2') return (bar.high + bar.low) / 2;
        if (name === 'hlc3') return (bar.high + bar.low + bar.close) / 3;
        if (name === 'ohlc4') return (bar.open + bar.high + bar.low + bar.close) / 4;
        return bar[name];
    }
    function bands(values, period, multiplier) {
        const middle = average(values, period);
        const deviation = values.map((_, i) => {
            if (middle[i] === null) return null;
            let variance = 0;
            for (let j = i - period + 1; j <= i; j++) variance += (values[j] - middle[i]) ** 2;
            return Math.sqrt(variance / period);
        });
        return {middle, upper: middle.map((v, i) => v === null ? null : v + multiplier * deviation[i]), lower: middle.map((v, i) => v === null ? null : v - multiplier * deviation[i])};
    }
    function rsi(values, period) {
        const gains = values.map((v, i) => i ? Math.max(0, v - values[i - 1]) : null);
        const losses = values.map((v, i) => i ? Math.max(0, values[i - 1] - v) : null);
        const up = average(gains, period, 'RMA'), down = average(losses, period, 'RMA');
        return up.map((v, i) => v === null ? null : down[i] === 0 ? (v === 0 ? 50 : 100) : 100 - 100 / (1 + v / down[i]));
    }
    function macd(values, fast, slow, signal) {
        const a = average(values, fast, 'EMA'), b = average(values, slow, 'EMA');
        const line = a.map((v, i) => v === null || b[i] === null ? null : v - b[i]);
        const trigger = average(line, signal, 'EMA');
        return {line, signal: trigger, histogram: line.map((v, i) => v === null || trigger[i] === null ? null : v - trigger[i])};
    }
    function vwap(bars) {
        let day = '', sum = 0, volume = 0;
        return bars.map(bar => {
            const current = new Intl.DateTimeFormat('en-CA', {timeZone:'America/New_York'}).format(new Date(bar.timestamp));
            if (current !== day) { day = current; sum = volume = 0; }
            sum += source(bar, 'hlc3') * bar.volume; volume += bar.volume;
            return volume ? sum / volume : null;
        });
    }
    root.ChartMath = {average, source, bands, rsi, macd, vwap};
    if (typeof module !== 'undefined') module.exports = root.ChartMath;
})(typeof window !== 'undefined' ? window : globalThis);
