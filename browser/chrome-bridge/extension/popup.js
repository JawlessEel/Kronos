'use strict';
const status = document.getElementById('status');
let forecast;
async function refresh() {
  const stored = await chrome.storage.local.get(['forecast','autoApply','targetTabId']); forecast = stored.forecast;
  document.getElementById('summary').textContent = forecast ? `${forecast.targetSymbol} · ${forecast.timeframe} · ${forecast.rows.length} predicted candles\nGenerated ${new Date(forecast.generatedAt).toLocaleString()}\nSource: ${forecast.provider}` : 'No forecast yet. Use Send to Chrome bridge in the workbench.';
  const select = document.getElementById('target'); select.replaceChildren();
  const tabs = await chrome.tabs.query({url:'https://www.tradingview.com/chart/*'});
  for (const tab of tabs) { const option = document.createElement('option'); option.value = String(tab.id); option.textContent = tab.title || tab.url; select.append(option); }
  if (tabs.some(tab=>tab.id === stored.targetTabId)) select.value = String(stored.targetTabId);
  document.getElementById('autoApply').checked = !!stored.autoApply;
  document.getElementById('apply').disabled = !forecast || !tabs.length;
  document.getElementById('copy').disabled = !forecast;
}
function action(id,run) { document.getElementById(id).onclick = async () => { const button = document.getElementById(id); button.disabled = true; try { await run(); } catch(e) { status.textContent = e.message; } finally { await refresh(); button.disabled = id === 'apply' ? !forecast || !document.getElementById('target').options.length : id === 'copy' ? !forecast : false; } }; }
action('refresh',refresh);
action('copy',async () => { await navigator.clipboard.writeText(KronosTVContract.encode(forecast)); status.textContent = 'Copied forecast payload.'; });
action('pine',async () => { const response = await fetch(chrome.runtime.getURL('Kronos-Forecast-Bridge.pine')); if (!response.ok) throw new Error('Pine source missing from extension'); await navigator.clipboard.writeText(await response.text()); status.textContent = 'Pine source copied. Create a new indicator in TradingView, paste, and Add to chart.'; });
action('clear',async () => { await chrome.storage.local.remove(['forecast','receivedAt']); await chrome.action.setBadgeText({text:''}); status.textContent = 'Stored forecast removed.'; });
action('apply',async () => {
  const clean = KronosTVContract.validate(forecast);
  const id = Number(document.getElementById('target').value);
  if (!Number.isSafeInteger(id)) throw new Error('Choose a TradingView tab');
  await chrome.storage.local.set({targetTabId:id});
  const reply = await chrome.tabs.sendMessage(id,{type:'apply-forecast',payload:clean});
  if (!reply?.ok) throw new Error(reply?.error || 'No bridge response. Reload the TradingView tab after loading the extension.');
  await chrome.action.setBadgeText({text:''}); status.textContent = reply.message;
});
document.getElementById('autoApply').onchange = async event => {
  try {
    const targetTabId = Number(document.getElementById('target').value);
    if (!Number.isSafeInteger(targetTabId) || targetTabId <= 0) throw new Error('Choose an open TradingView chart first');
    await chrome.storage.local.set({autoApply:event.target.checked,targetTabId});
    status.textContent = event.target.checked ? 'Future received forecasts will be submitted to this tab. No trades are placed.' : 'Automatic apply disabled.';
  } catch(e) { status.textContent = e.message; await refresh(); }
};
document.getElementById('target').onchange = async event => {
  try { await chrome.storage.local.set({targetTabId:Number(event.target.value)}); } catch(e) {status.textContent = e.message;}
};
refresh().catch(e => {status.textContent = e.message;});
