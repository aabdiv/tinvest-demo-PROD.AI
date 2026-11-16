"use strict";
window.PortfolioSharing=(()=>{
  const {escape:e,icon,request,toast}=Cabinet;let context=null;
  const el=id=>document.getElementById(id);
  function mount(api){
    context=api;
    document.querySelector('.pf-heading-line').insertAdjacentHTML('beforeend',`<button id="pf-share" class="cab-icon-button" aria-label="Поделиться стратегией" title="Поделиться стратегией">${icon('share',16)}</button>`);
    document.body.insertAdjacentHTML('beforeend',`<dialog id="share-dialog" class="cab-dialog" aria-labelledby="share-title"><form id="share-form"><div class="cab-dialog-top"><div><span class="cab-eyebrow">ИДЕИ СООБЩЕСТВА</span><h2 id="share-title">Поделиться стратегией</h2></div><button id="share-close" type="button" class="cab-icon-button" aria-label="Закрыть">✕</button></div><label>Название<input id="share-name" maxlength="80" required></label><label>Описание<textarea id="share-description" maxlength="300" rows="3"></textarea></label><div class="mg-mandate-box"><span class="cab-eyebrow">В КАРТОЧКЕ БУДУТ</span><p style="font-size:14px;color:var(--muted);line-height:1.8">Профиль стратегии, доли бумаг и правила управления. Суммы на ваших счетах и личная переписка останутся в аккаунте.</p><div id="share-rules"></div></div><p id="share-error" role="alert" class="cab-form-error" hidden></p><button id="share-submit" class="cab-btn cab-btn-primary">Опубликовать в «Идеях»</button></form></dialog>`);
    el('pf-share').onclick=()=>{const r=context.getRecord();el('share-name').value=r.title;el('share-description').value=r.description||'';el('share-error').hidden=true;el('share-rules').innerHTML=(r.portfolio?.red_lines||[]).filter(rule=>rule.active).map(rule=>`<div style="font-size:14px;color:var(--muted);margin-top:6px">✓ ${e(rule.label)}</div>`).join('');el('share-dialog').showModal();};
    el('share-close').onclick=()=>el('share-dialog').close();
    el('share-form').onsubmit=async event=>{event.preventDefault();el('share-submit').disabled=true;el('share-error').hidden=true;try{await context.flush();const item=await request('/api/community/publish',{method:'POST',body:JSON.stringify({portfolio_id:context.getRecord().id,title:el('share-name').value.trim(),description:el('share-description').value,kind:'portfolio'})});el('share-dialog').close();toast('Стратегия опубликована');location.href='/community?item='+encodeURIComponent(item.id);}catch(error){el('share-error').textContent=error.message;el('share-error').hidden=false;el('share-submit').disabled=false;}};
  }
  return{mount};
})();
