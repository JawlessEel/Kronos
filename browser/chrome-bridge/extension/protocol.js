(function (root) {
  'use strict';
  const intervals = {'1m':60,'5m':300,'15m':900,'1h':3600,'4h':14400,'1d':86400,'1w':604800};
  function validate(value, now = Date.now()) {
    if (!value || value.schema !== 'kronos-tradingview/1' || value.engine !== 'kronos-local') throw new Error('A real Kronos forecast is required');
    if (!/^[A-Z0-9_]+:[A-Z0-9_.!/-]+$/.test(value.targetSymbol || '') || value.targetSymbol.length > 80) throw new Error('Use an exchange-qualified TradingView symbol, for example OKX:BTCUSDT');
    const seconds = intervals[value.timeframe];
    if (!seconds || value.seconds !== seconds) throw new Error('Unsupported or inconsistent timeframe');
    if (!['regular','24x7'].includes(value.session)) throw new Error('Unsupported session');
    for (const key of ['generatedAt','anchorTime']) if (!Number.isSafeInteger(value[key]) || value[key] < 946684800000 || value[key] > now + 300000) throw new Error('Invalid forecast timestamps');
    if (now - value.generatedAt > Math.max(86400000, seconds * 2000)) throw new Error('Forecast is too old; regenerate');
    if (!Array.isArray(value.rows) || !value.rows.length || value.rows.length > 120) throw new Error('Forecast needs 1–120 candles');
    let previous = value.anchorTime;
    const rows = value.rows.map(row => {
      if (!Number.isSafeInteger(row.t) || row.t <= previous || row.t > now + 366 * 86400000) throw new Error('Candle timestamps must increase after the anchor');
      previous = row.t;
      for (const key of ['o','h','l','c']) if (typeof row[key] !== 'number' || !Number.isFinite(row[key]) || row[key] <= 0) throw new Error('Forecast contains missing or invalid prices');
      if (row.flag !== undefined && row.flag !== 0 && row.flag !== 1) throw new Error('Invalid candle quality flag');
      const flag = (row.flag === undefined ? row.quality !== 'OK' : row.flag !== 0) || row.h < Math.max(row.o,row.c) || row.l > Math.min(row.o,row.c) || row.h < row.l;
      return {t:row.t,o:row.o,h:row.h,l:row.l,c:row.c,flag:flag ? 1 : 0};
    });
    if (rows.at(-1).t + seconds * 1000 <= now) throw new Error('Forecast horizon has already ended; regenerate');
    return {schema:value.schema,engine:value.engine,targetSymbol:value.targetSymbol,timeframe:value.timeframe,seconds,session:value.session,generatedAt:value.generatedAt,anchorTime:value.anchorTime,provider:String(value.provider || '').slice(0,80),rows};
  }
  function encode(value, now) {
    const data = validate(value, now);
    return ['KRONOS1|' + [data.targetSymbol,data.seconds,data.generatedAt,data.anchorTime,data.session].join('|'), ...data.rows.map(r => [r.t,r.o,r.h,r.l,r.c,r.flag].join(','))].join('\n');
  }
  const api = {validate,encode,intervals};
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.KronosTVContract = api;
})(typeof window !== 'undefined' ? window : typeof self !== 'undefined' ? self : globalThis);
