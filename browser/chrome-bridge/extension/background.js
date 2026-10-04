'use strict';
importScripts('protocol.js');
let pending = Promise.resolve();
function allowedSource(url) {
  try { const u = new URL(url); return (u.protocol === 'http:' && ['127.0.0.1','localhost'].includes(u.hostname)) || (u.protocol === 'https:' && (u.hostname === 'perchance.org' || u.hostname.endsWith('.perchance.org'))); } catch { return false; }
}
chrome.runtime.onMessage.addListener((message,sender,reply) => {
  if (message?.type !== 'forecast' || !sender.tab || !allowedSource(sender.url)) return;
  const job = pending.catch(()=>{}).then(async () => {
    const payload = KronosTVContract.validate(message.payload);
    const prior = await chrome.storage.local.get('forecast');
    if (prior.forecast?.targetSymbol === payload.targetSymbol && prior.forecast.generatedAt > payload.generatedAt) throw new Error('A newer forecast is already stored; regenerate');
    await chrome.storage.local.set({forecast:payload,receivedAt:Date.now()});
    await chrome.action.setBadgeText({text:'NEW'});
    await chrome.action.setBadgeBackgroundColor({color:'#147b88'});
    const settings = await chrome.storage.local.get(['autoApply','targetTabId']);
    if (settings.autoApply && Number.isSafeInteger(settings.targetTabId)) {
      try {
        const tab = await chrome.tabs.get(settings.targetTabId);
        if (!tab.url?.startsWith('https://www.tradingview.com/chart/')) throw new Error('Paired tab is no longer a TradingView chart');
        const submitted = await chrome.tabs.sendMessage(tab.id,{type:'apply-forecast',payload});
        if (!submitted?.ok) throw new Error(submitted?.error || 'Indicator did not respond');
        await chrome.action.setBadgeText({text:''});
        return {ok:true,submitted:true};
      } catch(e) { return {ok:true,submitted:false,warning:'Forecast saved; auto-apply failed: ' + e.message}; }
    }
    return {ok:true};
  });
  pending = job;
  job.then(reply,e => reply({ok:false,error:e.message}));
  return true;
});
