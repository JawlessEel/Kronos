'use strict';
window.addEventListener('message', async event => {
  if (event.source !== window || event.origin !== location.origin || event.data?.channel !== 'kronos-tv-forecast') return;
  const {requestId,payload} = event.data;
  if (typeof requestId !== 'string' || requestId.length > 80) return;
  let response;
  try {
    const clean = KronosTVContract.validate(payload);
    response = await chrome.runtime.sendMessage({type:'forecast',payload:clean});
  } catch(e) { response = {ok:false,error:e.message}; }
  window.postMessage({channel:'kronos-tv-response',requestId,...response},location.origin);
});
