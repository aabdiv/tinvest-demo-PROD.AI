"use strict";
window.PortfolioManagement=(()=>{
  const {escape:e,icon,money,request,toast}=Cabinet;
  const agents=[{id:'balance',name:'Баланс',role:'Диверсификация и контроль риска'}, {id:'dividend',name:'Дивиденд',role:'Денежный поток и качество'}, {id:'momentum',name:'Импульс',role:'Рост и тренды'}];
  let context=null, desiredMode='agent', pending=false;
  const el=id=>document.getElementById(id);
  const get=()=>context.getRecord();
  function mount(api){
    context=api;
    document.querySelector('.pf-hero').insertAdjacentHTML('afterend',`<section id="pf-management" class="mg-section" aria-label="Управление портфелем"><div class="mg-title"><h2>Управление портфелем</h2><button id="mg-settings" class="mg-link">Настроить</button></div><div class="mg-modes"><button id="mg-manual" class="mg-mode">${icon('account',23)}<span><b>Самостоятельно</b><small>Вы принимаете решения и подтверждаете сделки</small></span><i></i></button><button id="mg-agent" class="mg-mode">${icon('bot',25)}<span><b>Поручить агенту</b><small>Отдельный счёт и ваши правила управления</small></span><i></i></button></div><div id="mg-active"></div></section>`);
    document.body.insertAdjacentHTML('beforeend',`<dialog id="mg-dialog" class="cab-dialog mg-dialog" aria-labelledby="mg-dialog-title"><form id="mg-form"><div class="cab-dialog-top"><div><span class="cab-eyebrow">УПРАВЛЕНИЕ ПОРТФЕЛЕМ</span><h2 id="mg-dialog-title">Поручить агенту</h2></div><button id="mg-close" type="button" class="cab-icon-button" aria-label="Закрыть">${icon('close',16)}</button></div><p id="mg-dialog-description" class="mg-dialog-description"></p><div id="mg-agent-fields"><label>Агент<select id="mg-agent-select">${agents.map(a=>`<option value="${a.id}">${a.name} — ${a.role}</option>`).join('')}</select></label><label>Сумма на отдельном счёте, ₽<input id="mg-budget" type="number" min="10000" max="10000000000" step="1000" value="250000" required></label><div class="mg-mandate-box"><span class="cab-eyebrow">ПОРУЧЕНИЕ</span><h3 id="mg-mandate-title"></h3><div id="mg-rules"></div></div></div><p id="mg-error" class="cab-form-error" role="alert" hidden></p><button id="mg-confirm" type="submit" class="cab-btn cab-btn-primary">Открыть счёт и поручить агенту</button></form></dialog>`);
    el('mg-manual').onclick=()=>{if(get().management?.mode==='agent')open('manual');};
    el('mg-agent').onclick=()=>open('agent');el('mg-settings').onclick=()=>open('agent');
    el('mg-close').onclick=()=>el('mg-dialog').close();el('mg-form').onsubmit=configure;
    el('mg-active').onclick=event=>{const journal=event.target.closest('a[href="#mg-journal"]');if(journal){el('mg-journal').open=true;return;}const button=event.target.closest('[data-mg-action]');if(!button)return;button.dataset.mgAction==='mandate'?open('agent'):action(button.dataset.mgAction);};
    render();
  }
  function renderActive(html) {
    const journalOpen=el('mg-journal')?.open;
    const focused=el('mg-active').contains(document.activeElement)?document.activeElement.dataset.mgAction:null;
    const changed=Cabinet.setHTML(el('mg-active'),html);
    if(changed && journalOpen && el('mg-journal'))el('mg-journal').open=true;
    el('mg-active').querySelectorAll('button').forEach(button=>{
      button.disabled=pending || (button.dataset.mgAction==='review' && get().management?.account?.status!=='active');
    });
    if(changed && focused)el('mg-active').querySelector(`[data-mg-action="${focused}"]`)?.focus();
  }
  function render(){
    if(!context)return;
    const r=get(),m=r.management||{mode:'manual'},a=m.account,active=m.mode==='agent';
    el('mg-manual').classList.toggle('selected',!active);el('mg-agent').classList.toggle('selected',active);
    el('mg-manual').setAttribute('aria-pressed',String(!active));el('mg-agent').setAttribute('aria-pressed',String(active));
    document.querySelector('#amount')?.closest('.param').toggleAttribute('hidden',active);
    if(!active||!a){renderActive(a?`<div class="mg-retained">Счёт ${e(a.id)} сохранён. Агент на паузе.<button data-mg-action="resume">Возобновить управление →</button></div>`:'');return;}
    const agent=a.agent || agents.find(agent=>agent.id===a.agent_id),paused=a.status!=='active';
    renderActive(`<div class="mg-account"><div class="mg-account-main"><span class="mg-avatar">${icon('bot',25)}</span><div><div class="mg-agent-name">Агент ${e(agent?.name||'Баланс')}<span class="mg-status ${paused?'paused':''}"><i></i>${paused?'На паузе':'Управляет портфелем'}</span></div><small>Отдельный счёт ${e(a.id)}</small></div><div class="mg-balance"><strong>${money(a.value)}</strong><small>В управлении</small></div></div><div class="mg-tools"><button data-mg-action="${paused?'resume':'pause'}">${icon(paused?'play':'pause',14)}${paused?'Возобновить':'Поставить на паузу'}</button><button data-mg-action="review" ${paused?'disabled':''}>${icon('chart',15)}Проверить портфель</button><a href="#mg-journal">Журнал решений ↓</a></div></div>${m.mandate_changed?'<div class="mg-policy-change">Вы изменили профиль. Агент пока следует прежнему поручению.<button data-mg-action="mandate">Обновить поручение →</button></div>':''}<details id="mg-journal" class="mg-journal"><summary>Последние решения <span>${a.events?.length||0}</span></summary><div>${(a.events||[]).slice(-5).reverse().map(event=>`<article class="mg-event"><div><span class="mg-event-dot"></span><strong>${e(event.text)}</strong><time>${e(new Date(event.at).toLocaleTimeString('ru-RU',{hour:'2-digit',minute:'2-digit'}))}</time></div>${event.trades?.length?`<div class="mg-trades">${event.trades.slice(0,6).map(t=>`<span class="${t.side}">${t.side==='buy'?'Купить':'Продать'} ${e(t.shortname)} <b>${money(t.rub)}</b></span>`).join('')}</div>`:''}${event.checks?.length?`<p class="mg-check-result">${event.checks.every(c=>c.ok)?'✓ Ограничения поручения соблюдены':'Есть ограничения, требующие внимания'}</p>`:''}</article>`).join('')}</div></details>`);
  }
  function open(mode='agent'){
    if(!context)return;desiredMode=mode;
    const r=get(),account=r.management?.account;
    el('mg-error').hidden=true;el('mg-dialog-title').textContent=mode==='agent'?'Поручить портфель агенту':'Управлять самостоятельно';
    el('mg-dialog-description').textContent=mode==='agent'?'Агент работает на выделенном счёте в рамках вашего поручения. Управление можно остановить в любой момент.':'Агент остановится. Его счёт и история сохранятся, а решения по портфелю будете принимать вы.';
    el('mg-agent-fields').hidden=mode!=='agent';el('mg-budget').disabled=!!account||mode!=='agent';
    el('mg-budget').value=account?.initial_amount || Math.min(r.state.amount_rub,250000);
    el('mg-agent-select').value=account?.agent_id || r.community_origin?.agent_id || 'balance';
    el('mg-mandate-title').textContent=r.title;
    const rules=r.portfolio?.red_lines?.filter(line=>line.active) || [];
    el('mg-rules').innerHTML=rules.map(rule=>`<span>${icon('shield',13)}${e(rule.label)}</span>`).join('');
    el('mg-confirm').textContent=mode==='manual'?'Вернуть управление себе':account?'Подтвердить поручение':'Открыть счёт и поручить агенту';
    el('mg-dialog').showModal();
  }
  async function configure(event){
    event.preventDefault();if(pending)return;pending=true;el('mg-confirm').disabled=true;el('mg-error').hidden=true;
    try{await context.flush();const r=get();const result=await request('/api/account/portfolios/'+r.id+'/management',{method:'PUT',body:JSON.stringify({revision:r.revision,mode:desiredMode,agent_id:el('mg-agent-select').value,amount_rub:Number(el('mg-budget').value)})});context.accept(result);el('mg-dialog').close();toast(desiredMode==='agent'?'Портфель передан агенту':'Управление у вас');}
    catch(error){el('mg-error').textContent=error.message;el('mg-error').hidden=false;}finally{pending=false;el('mg-confirm').disabled=false;}
  }
  async function action(action){
    if(pending)return;pending=true;el('mg-active').querySelectorAll('button').forEach(b=>b.disabled=true);
    try{await context.flush();const r=get();const result=await request('/api/account/portfolios/'+r.id+'/management/actions',{method:'POST',body:JSON.stringify({revision:r.revision,action})});context.accept(result);if(action==='review'){el('mg-journal').open=true;toast('Обзор завершён. Решение добавлено в журнал.');}}
    catch(error){toast(error.message);}finally{pending=false;render();if(action==='review'&&el('mg-journal'))el('mg-journal').open=true;}
  }
  return {mount,render,open};
})();
