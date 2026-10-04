(function () {
  'use strict';
  let busy = false;
  let maybeSend = () => {};
  function forecast(targetSymbol) {
    const result = window.WB && WB.fc.result;
    if (!result || WB.fc.busy || WB.fc.stale || result.key !== WB.fcKey()) throw new Error('Generate a fresh forecast for the current selection first');
    return KronosTVContract.validate({schema:'kronos-tradingview/1',engine:result.engine,targetSymbol:targetSymbol.trim().toUpperCase(),timeframe:state.tf,seconds:KronosTVContract.intervals[state.tf],session:WB.market === 'stocks' ? 'regular' : '24x7',generatedAt:result.generationTime,anchorTime:result.anchorTime,provider:result.provider,rows:result.rows});
  }
  function mount() {
    const anchor = document.getElementById('wbCsvExpBtn');
    if (!anchor || document.getElementById('kronosTVBridge')) return;
    const panel = document.createElement('div'); panel.id = 'kronosTVBridge'; panel.className = 'nitem';
    const title = document.createElement('strong'); title.textContent = 'TradingView · Chrome bridge';
    const label = document.createElement('label'); label.textContent = 'Target TradingView symbol ';
    const input = document.createElement('input'); input.type = 'text'; input.placeholder = 'OKX:BTCUSDT or AMEX:SPY'; input.style.width = '240px'; input.setAttribute('aria-label','Target TradingView symbol');
    const venue = String(WB.activeVenue || WB.provider).toLowerCase();
    const exchange = venue.includes('okx') ? 'OKX' : venue.includes('binance') ? 'BINANCE' : venue.includes('bybit') ? 'BYBIT' : '';
    input.value = WB.market === 'crypto' && exchange ? exchange + ':' + state.sym.replace(/[-/]/g,'') : '';
    label.append(input);
    const send = document.createElement('button'); send.type = 'button'; send.className = 'btn sm'; send.textContent = 'Send to Chrome bridge';
    const copy = document.createElement('button'); copy.type = 'button'; copy.className = 'btn sm'; copy.textContent = 'Copy TradingView data';
    const autoLabel = document.createElement('label'); const auto = document.createElement('input'); auto.type = 'checkbox'; autoLabel.append(auto,document.createTextNode(' Send each newly generated forecast'));
    const status = document.createElement('p'); status.className = 'hint'; status.setAttribute('role','status'); status.textContent = 'Use the exact exchange and symbol from your TradingView chart. Forecast data will be saved locally in the extension.';
    panel.append(title,document.createElement('br'),label,send,copy,autoLabel,status); anchor.parentElement.after(panel);
    copy.onclick = async () => { try { await navigator.clipboard.writeText(KronosTVContract.encode(forecast(input.value))); status.textContent = 'Copied. Paste into the Kronos Forecast Bridge indicator’s Forecast payload setting.'; } catch(e) { status.textContent = e.message; } };
    send.onclick = async () => {
      if (busy) return;
      try {
        const payload = forecast(input.value); const requestId = crypto.randomUUID(); busy = true; send.disabled = true;
        status.textContent = 'Waiting for the Chrome extension…';
        const response = await new Promise((resolve,reject) => {
          const timer = setTimeout(() => { cleanup(); reject(new Error('Extension not connected. Load the Chrome bridge extension and reload this page, or use Copy TradingView data.')); },5000);
          function cleanup() { clearTimeout(timer); window.removeEventListener('message',receive); }
          function receive(event) { if (event.source !== window || event.origin !== location.origin || event.data?.channel !== 'kronos-tv-response' || event.data.requestId !== requestId) return; cleanup(); resolve(event.data); }
          window.addEventListener('message',receive);
          window.postMessage({channel:'kronos-tv-forecast',requestId,payload},location.origin);
        });
        if (!response.ok) throw new Error(response.error || 'Bridge rejected forecast');
        status.textContent = response.warning || (response.submitted ? 'Forecast submitted to your paired TradingView indicator. Check its status table.' : 'Forecast received by Chrome bridge. Open its toolbar popup and choose your TradingView tab to apply it.');
      } catch(e) { status.textContent = e.message; }
      finally { busy = false; send.disabled = false; }
    };
    let lastSent = null;
    maybeSend = () => {
      if (!input.matches(':focus') && !input.dataset.custom) {
        const venueNow = String(WB.activeVenue || WB.provider).toLowerCase();
        const exchangeNow = venueNow.includes('okx') ? 'OKX' : venueNow.includes('binance') ? 'BINANCE' : venueNow.includes('bybit') ? 'BYBIT' : '';
        const next = WB.market === 'crypto' && exchangeNow ? exchangeNow + ':' + state.sym.replace(/[-/]/g,'') : '';
        if (input.value !== next) input.value = next;
      }
      const result = WB.fc.result;
      if (!auto.checked || busy || WB.fc.busy || WB.fc.stale || !result || result.generationTime === lastSent || result.key !== WB.fcKey()) return;
      lastSent = result.generationTime; send.click();
    };
    input.addEventListener('input',()=>{input.dataset.custom='1';});
    auto.onchange = () => { lastSent = WB.fc.result?.generationTime || null; status.textContent = auto.checked ? 'Newly generated forecasts will be sent while this page stays open.' : 'Automatic sending disabled.'; };
  }
  const observer = new MutationObserver(()=>{mount();maybeSend();}); observer.observe(document.documentElement,{childList:true,subtree:true}); mount();
})();
