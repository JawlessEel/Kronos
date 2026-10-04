(function () {
  'use strict';
  if (window.KronosTVAdapter) return;
  let applying = false;
  const title = 'Kronos Forecast Bridge';
  const visible = element => !!element && element.getClientRects().length > 0;
  function dialog() {
    const candidates = [...document.querySelectorAll('[role="dialog"][data-name="indicator-properties-dialog"]')].filter(el => visible(el) && el.getAttribute('data-dialog-name') === title);
    if (candidates.length > 1) throw new Error('Multiple Kronos settings dialogs; close extras first');
    return candidates[0];
  }
  async function waitFor(get, message) {
    for (let i=0;i<30;i++) { const result=get(); if (result) return result; await new Promise(resolve=>setTimeout(resolve,100)); }
    throw new Error(message);
  }
  function openSettings() {
    const legends = [...document.querySelectorAll('[data-qa-id="legend-source-item"]')].filter(el => [...el.querySelectorAll('[data-qa-id~="legend-source-title"]')].some(n=>n.textContent.trim() === title) || el.textContent.trim() === title);
    if (legends.length !== 1) throw new Error('Open the Kronos Forecast Bridge indicator settings manually, then try Apply again. Add the supplied Pine indicator first if absent.');
    const buttons = [...legends[0].querySelectorAll('[data-qa-id="legend-settings-action"]')];
    if (buttons.length !== 1) throw new Error('Cannot identify the dedicated indicator’s Settings control. Open its settings manually.');
    buttons[0].dispatchEvent(new MouseEvent('mousedown',{bubbles:true,cancelable:true,button:0,buttons:1}));
    buttons[0].dispatchEvent(new MouseEvent('mouseup',{bubbles:true,cancelable:true,button:0,buttons:0}));
    buttons[0].click();
  }
  async function apply(payload) {
    if (applying) throw new Error('An update is already in progress');
    applying = true;
    try {
      const encoded = KronosTVContract.encode(payload);
      if (!dialog()) openSettings();
      const settings = await waitFor(dialog,'Kronos settings did not open');
      const inputsTab = [...settings.querySelectorAll('[role="tab"]')].find(el=>el.textContent.trim()==='Inputs');
      if (inputsTab && inputsTab.getAttribute('aria-selected') !== 'true') inputsTab.click();
      const area = await waitFor(() => {
        const fields = [...settings.querySelectorAll('textarea')].filter(visible);
        if (fields.length > 1) throw new Error('More than one text area in indicator settings; refusing to change ambiguous fields');
        return fields.length === 1 ? fields[0] : null;
      },'Forecast payload text area not found. Check the supplied indicator version.');
      const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype,'value').set;
      setter.call(area,encoded); area.dispatchEvent(new Event('input',{bubbles:true})); area.dispatchEvent(new Event('change',{bubbles:true}));
      if (area.value !== encoded) throw new Error('TradingView did not retain the forecast payload');
      const ok = [...settings.querySelectorAll('button')].filter(el=>visible(el) && ['Ok','OK'].includes(el.textContent.trim()));
      if (ok.length !== 1 || ok[0].disabled) throw new Error('Payload filled. Press OK manually; its button could not be safely identified.');
      ok[0].click();
      await waitFor(()=> !visible(settings),'TradingView kept the settings dialog open; inspect its error message');
      return {ok:true,message:'Forecast submitted to the indicator. Check its status table for symbol, timeframe, session, or expiry warnings.'};
    } finally { applying = false; }
  }
  window.KronosTVAdapter = {apply};
  if (typeof chrome !== 'undefined' && chrome.runtime?.onMessage) chrome.runtime.onMessage.addListener((message,sender,reply)=> {
    if (message?.type !== 'apply-forecast') return;
    apply(message.payload).then(reply,e=>reply({ok:false,error:e.message})); return true;
  });
})();
