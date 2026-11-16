"use strict";
(()=>{
  const {escape:e,icon,radar,spark,percent,plural,request,href,toast}=Cabinet;
  const el=id=>document.getElementById(id), risks={low:'Низкий риск',moderate:'Умеренный риск',high:'Высокий риск'};
  let items=[],risk='all',query='',selected=null;
  el('cm-hero-icon').innerHTML=icon('community',68);
  function card(item){
    const color='var(--chart-accent)';
    return `<button class="cm-card" data-cm-open="${e(item.id)}"><div class="cm-card-head"><span class="cm-author-avatar" >${e(item.initials)}</span><span class="cm-author">АВТОР<b>${e(item.author)}</b></span><span class="cm-risk ${item.risk}">${risks[item.risk]}</span></div><div class="cm-card-body"><span class="cab-eyebrow">АВТОРСКАЯ СТРАТЕГИЯ</span><h2>${e(item.title)}</h2><p>${e(item.description)}</p>${radar(item.target,color)}</div><div class="cm-tags">${item.tags.map(t=>`<span>${e(t)}</span>`).join('')}</div><div class="cm-card-stats"><div><span>Горизонт</span><b>${item.horizon} ${plural(item.horizon,['год','года','лет'])}</b></div><div><span>Состав</span><b>${item.holdings.length} бумаг</b></div><div class="cm-mini-history">${spark(item.history,color)}<span>История состава</span></div></div><div class="cm-card-footer"><span>Можно адаптировать под себя</span><b>Посмотреть портфель ${icon('arrow',15)}</b></div></button>`;
  }
  function render(){
    const result=items.filter(item=>(risk==='all'||risk===item.risk)&&(!query||(item.title+' '+item.author+' '+item.description+' '+item.tags.join(' ')).toLowerCase().includes(query)));
    el('cm-grid').innerHTML=result.map(card).join('')||'<div class="cm-empty">Ничего не нашлось. Попробуйте другой запрос или уровень риска.</div>';
    el('cm-result-count').textContent=result.length+' '+plural(result.length,['идея','идеи','идей']);
    document.querySelectorAll('[data-cm-risk]').forEach(button=>{const on=button.dataset.cmRisk===risk;button.classList.toggle('on',on);button.setAttribute('aria-pressed',String(on));});
  }
  function detail(id){
    selected=items.find(item=>item.id===id);if(!selected)return;
    el('cm-detail-content').innerHTML=`<div class="cab-dialog-top"><div><span class="cab-eyebrow">ПОРТФЕЛЬ СООБЩЕСТВА</span><h2 id="cm-detail-title">${e(selected.title)}</h2><span class="cm-detail-author">${e(selected.author)}</span></div><button class="cab-icon-button" data-cm-close="cm-detail" aria-label="Закрыть">${icon('close',17)}</button></div><p class="cm-detail-description">${e(selected.description)}</p><div class="cm-detail-layout"><div><h3>Как устроена стратегия</h3><div class="cm-detail-metrics"><span>${risks[selected.risk]}</span><span>${selected.horizon} ${plural(selected.horizon,['год','года','лет'])}</span><span>${selected.holdings.length} бумаг</span></div><div class="cm-detail-rules">${selected.rules.map(rule=>`<div>${icon('shield',14)}${e(rule)}</div>`).join('')}</div><h3>Распределение по отраслям</h3>${selected.sectors.slice(0,5).map((s,i)=>`<div class="pf-sector-row"><div><span>${e(s.name)}</span><b>${percent(s.weight)}</b></div><div class="pf-sector-track"><i style="width:${s.weight*100}%;background:${['#333333','#FFDD2D','#888888','#C4B85C','#C4C4C4'][i]}"></i></div></div>`).join('')}</div><div class="cm-detail-figure">${radar(selected.target,'#FFDD2D')}<div class="cm-axis-captions"><span>Рост ${selected.target.growth}</span><span>Дивиденды ${selected.target.dividends}</span><span>Устойчивость ${selected.target.stability}</span></div></div></div><section class="cm-detail-holdings"><h3>Бумаги в стратегии</h3><div>${selected.holdings.slice(0,12).map(h=>`<span>${e(h.shortname)} <b>${percent(h.weight)}</b></span>`).join('')}</div></section><footer class="cm-detail-actions"><button data-cm-action="add" class="cab-btn cab-btn-secondary">Добавить к моему портфелю</button><button data-cm-action="use" class="cab-btn cab-btn-primary">Взять за основу ${icon('arrow',15)}</button></footer>`;
    el('cm-detail').showModal();
  }
  function openUse(mode){
    el('cm-selection').innerHTML=icon('chart',24)+`<span><b>${e(selected.title)}</b><small>${e(selected.portfolio_title||selected.author)}</small></span>`;
    el('cm-new-title').value=selected.portfolio_title||selected.title;el('cm-use-error').hidden=true;
    document.querySelector(`input[name=cm-mode][value=${mode}]`).checked=true;updateUse();el('cm-use-dialog').showModal();
  }
  function updateUse(){el('cm-use-submit').textContent=document.querySelector('input[name=cm-mode]:checked').value==='agent'?'Открыть счёт и поручить агенту':'Создать мой портфель';}
  async function openAdd(){
    try{const data=await request('/api/account/portfolios');el('cm-own-portfolios').innerHTML=data.portfolios.map(p=>`<option value="${e(p.id)}">${e(p.title)}</option>`).join('');el('cm-add-selection').innerHTML=icon('idea',24)+`<span><b>${e(selected.title)}</b><small>${e(selected.author)}</small></span>`;el('cm-add-error').hidden=true;el('cm-add-dialog').showModal();}
    catch(error){toast(error.message);}
  }
  document.querySelectorAll('[data-cm-risk]').forEach(button=>button.onclick=()=>{risk=button.dataset.cmRisk;render();});
  el('cm-search').oninput=event=>{query=event.target.value.trim().toLowerCase();render();};
  el('cm-grid').onclick=event=>{const button=event.target.closest('[data-cm-open]');if(button)detail(button.dataset.cmOpen);};
  document.addEventListener('click',event=>{const close=event.target.closest('[data-cm-close]');if(close)el(close.dataset.cmClose).close();const button=event.target.closest('[data-cm-action]');if(button){if(button.dataset.cmAction==='add')openAdd();else openUse('manual');}});
  document.querySelectorAll('input[name=cm-mode]').forEach(input=>input.onchange=updateUse);
  el('cm-use-form').onsubmit=async event=>{event.preventDefault();el('cm-use-submit').disabled=true;el('cm-use-error').hidden=true;try{const result=await request('/api/community/'+selected.id+'/use',{method:'POST',body:JSON.stringify({title:el('cm-new-title').value.trim(),amount_rub:Number(el('cm-amount').value),mode:document.querySelector('input[name=cm-mode]:checked').value})});location.href=href(result.id);}catch(error){el('cm-use-error').textContent=error.message;el('cm-use-error').hidden=false;el('cm-use-submit').disabled=false;}};
  el('cm-add-form').onsubmit=async event=>{event.preventDefault();el('cm-add-submit').disabled=true;el('cm-add-error').hidden=true;try{const id=el('cm-own-portfolios').value;const text=selected.description+'\nАвтор предлагает: '+selected.sectors.slice(0,2).map(s=>s.name).join(', ')+'.';await request('/api/account/portfolios/'+id+'/chat',{method:'POST',body:JSON.stringify({intent:'idea',source_kind:'text',source_title:selected.title,article_text:text,source_url:location.origin+'/community?item='+selected.id,text:el('cm-add-question').value})});location.href=href(id)+'&chat=1';}catch(error){el('cm-add-error').textContent=error.message;el('cm-add-error').hidden=false;el('cm-add-submit').disabled=false;}};
  request('/api/community').then(data=>{items=data.items.filter(item=>item.kind==='portfolio');el('cm-portfolio-count').textContent=items.length;render();const id=new URLSearchParams(location.search).get('item');if(id)detail(id);}).catch(error=>{el('cm-grid').innerHTML='';el('cm-error').textContent=error.message;el('cm-error').hidden=false;});
})();
