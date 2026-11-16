"use strict";
window.PortfolioWorkspace = (() => {
  const params=new URLSearchParams(location.search), id=params.get('portfolio');
  const {escape:e,icon,money,percent,request,radar,toast}=Cabinet;
  const endpoint='/api/account/portfolios/'+encodeURIComponent(id || '');
  let record=null, catalog=[], saveTimer=null, queue=Promise.resolve(), lastSaved='', busy=false, currentTab='current', focusBeforeChat=null;
  let confirmPlan=null, lastRender='', chatOpen=false, sourceIntent='question', sourceKind='article';
  const $w=id=>document.getElementById(id);
  const snapshot=()=>JSON.stringify({state:S,editor_chat:CHAT});
  const setStatus=(text,error=false)=>{const el=$w('pf-save-status');if(el){el.textContent=text;el.hidden=!text;el.classList.toggle('bad',error);}};
  async function flush() {
    if(!id || !record) return;
    clearTimeout(saveTimer);
    const task=queue.catch(()=>{}).then(async()=>{
      const data=snapshot();
      if(data===lastSaved) return;
      setStatus('Сохраняем…');
      try {
        const result=await request(endpoint,{method:'PUT',body:JSON.stringify({...JSON.parse(data),revision:record.revision})});
        record={...record,...result};lastSaved=data;setStatus('');window.PortfolioManagement?.render();
      } catch(error){setStatus('Не сохранено · повторить',true);throw error;}
    });
    queue=task;return task;
  }
  function scheduleSave() {
    if(!record || busy || snapshot()===lastSaved) return;
    setStatus('Есть несохранённые изменения');clearTimeout(saveTimer);
    saveTimer=setTimeout(()=>flush().catch(error=>toast(error.message)),650);
  }
  function currentRows() {
    if(record.management?.mode==='agent')return record.current?.holdings || [];
    if(!S.executed?.length) return [];
    const amount=S.executed_value ?? S.amount_rub;
    const total=S.executed.reduce((sum,h)=>sum+(h.weight>0 && catalog.some(s=>s.secid===h.secid)?h.weight:0),0) || 1;
    return S.executed.map(h=>{const sec=catalog.find(s=>s.secid===h.secid);return sec && h.weight>0 ? {...sec,weight:h.weight/total,rub:Math.round(amount*h.weight/total),sector_ru:META.sectors[sec.sector] || sec.sector}:null;}).filter(Boolean).sort((a,b)=>b.weight-a.weight);
  }
  function sectors(rows) {
    const sums={};rows.forEach(h=>sums[h.sector]=(sums[h.sector]||0)+h.weight);
    return Object.entries(sums).map(([sector,weight])=>({sector,weight,name:META.sectors[sector]||sector})).sort((a,b)=>b.weight-a.weight);
  }
  function renderHoldings() {
    const actual=currentRows(), plan=P?.holdings || [];
    const rows=currentTab==='current'?actual:plan;
    $w('pf-table-body').innerHTML=rows.length ? rows.map(h=>`<tr><td><span class="pf-security-icon">${e(h.secid.slice(0,2))}</span><span class="pf-security-info"><strong>${e(h.shortname)}</strong><small>${e(h.secid)} · ${e(h.sector_ru || META.sectors[h.sector])}</small></span></td><td>${money(h.price)}</td><td><span class="pf-weight"><span class="pf-weight-track"><i style="width:${Math.min(100,h.weight*400)}%"></i></span>${(h.weight*100).toFixed(1).replace('.',',')}%</span></td><td>${money(h.rub)}</td></tr>`).join('') : `<tr><td colspan="4" style="display:table-cell;text-align:center;padding:35px;color:var(--muted)">${P?.error?e(P.error):'Подтвердите покупку, чтобы сформировать состав.'}</td></tr>`;
    $w('pf-position-count').textContent=rows.length+' бумаг';
    const distribution=sectors(rows),colors=['#333333','#FFDD2D','#888888','#C4B85C','#C4C4C4','#575757'];
    $w('pf-distribution-list').innerHTML=distribution.map((s,i)=>`<div class="pf-sector-row"><div><span>${e(s.name)}</span><b>${percent(s.weight)}</b></div><div class="pf-sector-track"><i style="width:${s.weight*100}%;background:${colors[i%colors.length]}"></i></div></div>`).join('') || '<p class="cab-field-hint">Состав ещё не сформирован.</p>';
    const differs=actual.length && plan.length && [...new Set([...actual,...plan].map(h=>h.secid))].some(secid=>Math.abs((actual.find(h=>h.secid===secid)?.weight||0)-(plan.find(h=>h.secid===secid)?.weight||0))>.005);
    $w('pf-plan-alert').hidden=!differs;
    $w('pf-buy').textContent=record.management?.mode==='agent'?'Журнал агента':actual.length?'Обсудить ребалансировку':'Подтвердить покупку';
    $w('pf-buy').disabled=!plan.length || !!P?.error;
    $w('pf-amount').textContent=money(record.management?.mode==='agent'?record.current?.amount:S.executed_value ?? S.amount_rub);
  }
  function sync() {
    if(!record) return;
    const data=JSON.stringify({state:S,plan:P});
    if(data!==lastRender){renderHoldings();lastRender=data;}renderSources();window.PortfolioManagement?.render();
    scheduleSave();
  }
  function shell() {
    document.body.classList.add('portfolio-mode');
    document.querySelector('.top .brand').innerHTML='<span class="logo" aria-hidden="true"></span>Портфель с агентом';
    document.querySelector('.top-right').insertAdjacentHTML('beforeend','<span class="cab-study"><i></i>Демо</span>');
    const main=document.querySelector('main');
    main.insertAdjacentHTML('afterbegin',`<div class="pf-breadcrumb"><a href="/account">← Все портфели</a><span>/</span><span>${e(record.title)}</span></div><section class="pf-hero"><div><div class="pf-heading-line"><span class="cab-source-icon">${icon(record.source_kind==='video'?'video':'oil',25)}</span><h1 id="pf-title">${e(record.title)}</h1><button id="pf-rename" class="cab-icon-button" aria-label="Переименовать портфель">${icon('edit',15)}</button></div><p class="pf-hero-description">${e(record.description || '')}</p><div class="pf-meta"><span>${record.strategy_origin==='external' || record.source_kind==='video'?'Чужая идея':'Своя стратегия'}</span><button id="pf-save-status" class="pf-saved" type="button" hidden></button></div></div><div class="pf-hero-actions"><strong class="pf-hero-amount" id="pf-amount">${money(S.amount_rub)}</strong><div class="pf-hero-controls"><button class="pf-add-idea" id="pf-add-idea">${icon('plus',17)}Добавить идею</button><button class="pf-chat-button" id="pf-open-chat">${icon('chat',18)}Обсудить с агентом</button></div></div></section>`);
    document.querySelector('#step1>h1').textContent='Ваши предпочтения и границы';
    document.querySelector('#step1>.sub').hidden=true;
    $w('step1').insertAdjacentHTML('afterend',`<section class="pf-holdings" id="pf-holdings"><div class="pf-section-heading"><div><h2>Состав портфеля <span class="cab-muted" id="pf-position-count"></span></h2></div><button id="pf-buy" class="cab-btn cab-btn-secondary pf-trust">Подтвердить покупку</button></div><div id="pf-plan-alert" class="pf-plan-alert" hidden>Новый план ещё не применён к текущему составу.</div><div class="pf-holdings-layout"><div class="pf-table-card"><div class="pf-view-tabs" role="tablist" aria-label="Какой состав показать"><button role="tab" aria-selected="true" data-view="current" class="on">Текущий состав</button><button role="tab" aria-selected="false" data-view="plan">Подобранный план</button></div><table class="pf-table"><thead><tr><th>Бумага / отрасль</th><th title="По данным загруженной базы Мосбиржи">Цена</th><th>Доля</th><th>Сумма</th></tr></thead><tbody id="pf-table-body"></tbody></table></div><aside class="pf-distribution"><h3>По отраслям</h3><div id="pf-distribution-list"></div></aside></div><div class="pf-research-banner">${icon('chat',27)}<div><h3>Новости и чужие идеи — в контексте вашего портфеля</h3><p>Обсудите событие или стратегию, которую услышали.</p></div><button id="pf-news-chat" class="cab-btn cab-btn-secondary">Открыть чат ${icon('arrow',14)}</button></div><section class="pf-ideas" id="pf-ideas" hidden><div class="pf-section-heading"><h2>Добавленные идеи</h2></div><div id="pf-ideas-list" class="pf-ideas-list"></div></section><details class="pf-source-details"><summary>Исходная идея и источник</summary><p>${e(record.source_text || 'Идея пока не описана.')}</p>${record.source_url?`<a href="${e(record.source_url)}" target="_blank" rel="noopener noreferrer">Открыть сохранённый источник ${icon('arrow',13)}</a>`:''}</details></section>`);
    document.body.insertAdjacentHTML('beforeend',`<div class="pf-research-overlay" id="pf-chat-overlay" hidden></div><aside class="pf-research-panel" id="pf-chat-panel" role="dialog" aria-modal="true" aria-labelledby="pf-chat-title" tabindex="-1" hidden><header class="pf-research-header"><div><h2 id="pf-chat-title">Чат с агентом</h2><p id="pf-chat-context-title">${e(record.title)}</p></div><button id="pf-close-chat" class="cab-icon-button" aria-label="Закрыть чат">${icon('close',17)}</button></header><div id="pf-research-log" class="pf-research-log" aria-live="polite"></div><form id="pf-chat-form" class="pf-research-composer"><div id="pf-chat-suggestions" class="pf-chat-suggestions"><button type="button" data-question="Напомни, почему мы создали этот портфель">Что мы обсуждали?</button><button type="button" data-question="Как снизить риск концентрации моего портфеля?">Проверить риски</button></div><div id="pf-source-fields" class="pf-source-fields" hidden><div class="pf-source-purpose" role="group" aria-label="Что добавляем"><button type="button" data-source-intent="question" aria-pressed="true">Новость</button><button type="button" data-source-intent="idea" aria-pressed="false">Чужая идея</button></div><div class="cab-format-choice" role="group" aria-label="Формат источника"><label><input type="radio" name="pf-source-kind" value="video"><span>Видео</span></label><label><input type="radio" name="pf-source-kind" value="article" checked><span>Статья</span></label><label><input type="radio" name="pf-source-kind" value="text"><span>Текст</span></label></div><label id="pf-source-title-label" hidden>Название идеи<input id="pf-source-title" maxlength="160" placeholder="Например, технологии в дивидендном портфеле"></label><label id="pf-news-url-label">Ссылка на статью<input id="pf-news-url" type="url" placeholder="https://…" maxlength="2000"></label><label id="pf-video-upload" class="video-upload" hidden><span id="pf-video-name">Загрузить видео</span><input id="pf-video-file" class="sr" type="file" accept="video/mp4,video/quicktime,video/webm,.mp4,.mov,.webm"></label><label id="pf-news-text-label">Текст статьи<textarea id="pf-news-text" placeholder="Вставьте текст или укажите ссылку выше" maxlength="16000"></textarea></label><label id="pf-text-upload">Текстовый файл<input id="pf-news-file" type="file" accept=".txt,.md,text/plain,text/markdown"></label></div><div class="pf-composer-box"><label class="sr" for="pf-question">Вопрос об этом портфеле</label><textarea id="pf-question" placeholder="Что эта новость меняет для моего портфеля?" maxlength="8000"></textarea><div class="pf-composer-actions"><button id="pf-attach-news" type="button" aria-expanded="false">${icon('link',14)}Добавить источник</button><button id="pf-send-question" type="submit" aria-label="Отправить вопрос">${icon('send',18)}</button></div></div><p id="pf-chat-error" class="pf-research-error" role="alert" hidden></p></form></aside><dialog id="pf-rename-dialog" class="cab-dialog" aria-labelledby="pf-rename-title"><form id="pf-rename-form"><div class="cab-dialog-top"><h2 id="pf-rename-title">Название портфеля</h2><button type="button" id="pf-rename-close" class="cab-icon-button" aria-label="Закрыть">✕</button></div><label>Название<input id="pf-new-title" required maxlength="80" value="${e(record.title)}"></label><button class="cab-btn cab-btn-primary" type="submit">Сохранить название</button><p id="pf-rename-error" class="cab-form-error" role="alert"></p></form></dialog>`);
    $w('pf-open-chat').onclick=$w('pf-news-chat').onclick=()=>openChat();
    $w('pf-add-idea').onclick=()=>openChat({intent:'idea'});
    document.querySelectorAll('[data-source-intent]').forEach(b=>b.onclick=()=>setSource(b.dataset.sourceIntent,sourceKind));
    document.querySelectorAll('input[name=pf-source-kind]').forEach(input=>input.onchange=()=>setSource(sourceIntent,input.value));
    $w('pf-ideas-list').onclick=event=>{const b=event.target.closest('[data-source-chat]');if(!b)return;openChat();const message=$w('pf-research-log').querySelector('[data-source-id="'+b.dataset.sourceChat+'"]');message?.scrollIntoView({block:'start'});};
    $w('pf-close-chat').onclick=$w('pf-chat-overlay').onclick=closeChat;
    $w('pf-save-status').onclick=()=>flush().then(()=>toast('Портфель сохранён')).catch(error=>toast(error.message));
    $w('pf-buy').onclick=()=>{if(record.management?.mode==='agent'){const journal=$w('mg-journal');if(journal){journal.open=true;journal.scrollIntoView({block:'center',behavior:'smooth'});}}else $w('trust').click();};
    document.querySelectorAll('[data-view]').forEach(b=>b.onclick=()=>{
      currentTab=b.dataset.view;document.querySelectorAll('[data-view]').forEach(t=>{const on=t===b;t.classList.toggle('on',on);t.setAttribute('aria-selected',String(on));});renderHoldings();
    });
    $w('pf-attach-news').onclick=()=>{const expand=$w('pf-source-fields').hidden;setSource(sourceIntent,sourceKind,expand);if(expand)(sourceKind==='text'?$w('pf-news-text'):$w('pf-news-url')).focus();};
    $w('pf-video-file').onchange=event=>{const file=event.target.files[0];if(!file)return;if(file.size>100*1024*1024){toast('Выберите видео до 100 МБ');event.target.value='';return;}$w('pf-video-name').textContent=file.name;$w('pf-news-url').value='';};
    $w('pf-news-file').onchange=async event=>{
      const file=event.target.files[0];if(!file)return;
      if(file.size>100000 || !/\.(txt|md)$/i.test(file.name)){toast('Добавьте текстовый файл .txt или .md размером до 100 КБ.');event.target.value='';return;}
      const text=await file.text();if(text.length>16000){toast('В файле больше 16 000 символов. Выберите нужный отрывок.');return;}$w('pf-news-text').value=text;
    };
    $w('pf-chat-form').onsubmit=sendQuestion;
    $w('pf-question').onkeydown=event=>{if(event.key==='Enter' && (event.ctrlKey||event.metaKey)){event.preventDefault();$w('pf-chat-form').requestSubmit();}};
    document.querySelectorAll('[data-question]').forEach(b=>b.onclick=()=>{$w('pf-question').value=b.dataset.question;$w('pf-question').focus();});
    $w('pf-research-log').onclick=async event=>{const b=event.target.closest('[data-apply-plan]');if(b)applyPlan(b.dataset.applyPlan);};
    $w('pf-rename').onclick=()=>$w('pf-rename-dialog').showModal();$w('pf-rename-close').onclick=()=>$w('pf-rename-dialog').close();
    $w('pf-rename-form').onsubmit=async event=>{
      event.preventDefault();const title=$w('pf-new-title').value.trim();if(!title)return;
      const button=event.submitter;button.disabled=true;
      try{await flush();const result=await request(endpoint,{method:'PUT',body:JSON.stringify({state:S,editor_chat:CHAT,revision:record.revision,title})});record={...record,...result};$w('pf-title').textContent=title;$w('pf-chat-context-title').textContent=title;document.querySelector('.pf-breadcrumb>span:last-child').textContent=title;$w('pf-rename-dialog').close();toast('Название сохранено');}
      catch(error){$w('pf-rename-error').textContent=error.message;}finally{button.disabled=false;}
    };
    document.addEventListener('keydown',event=>{
      if(!chatOpen)return;
      if(event.key==='Escape' && !$w('modal').matches(':not(.hidden)')){event.preventDefault();closeChat();return;}
      if(event.key==='Tab'){
        const focusable=[...$w('pf-chat-panel').querySelectorAll('button:not(:disabled),a,input,textarea,[tabindex="0"]')].filter(el=>el.getClientRects().length);
        const first=focusable[0],last=focusable.at(-1);
        if(event.shiftKey && document.activeElement===first){event.preventDefault();last?.focus();}
        else if(!event.shiftKey && document.activeElement===last){event.preventDefault();first?.focus();}
      }
    });
    window.PortfolioManagement?.mount({getRecord:()=>record,flush,accept:acceptRecord});
    window.PortfolioSharing?.mount({getRecord:()=>record,flush});
    const accountLink=document.querySelector('.pf-breadcrumb a');accountLink.onclick=event=>navigate(event,accountLink);
    document.addEventListener('click',event=>{const a=event.target.closest('.cab-bottom a');if(a && id)navigate(event,a);});
    window.addEventListener('beforeunload',event=>{if(record && snapshot()!==lastSaved){event.preventDefault();event.returnValue='';}});
  }
  async function navigate(event,link) {
    if(event.defaultPrevented || event.button!==0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey || (link.target && link.target!=='_self'))return;
    event.preventDefault();
    if(link.getAttribute('aria-busy')==='true')return;
    link.classList.add('is-opening');link.setAttribute('aria-busy','true');document.body.classList.add('ui-navigating');
    try {await flush();location.href=link.href;}
    catch(error){link.classList.remove('is-opening');link.removeAttribute('aria-busy');document.body.classList.remove('ui-navigating');toast(error.message);}
  }
  function setSource(intent,kind,expand=true) {
    sourceIntent=intent;sourceKind=kind;
    $w('pf-source-fields').hidden=!expand;
    $w('pf-attach-news').setAttribute('aria-expanded',String(expand));
    document.querySelectorAll('[data-source-intent]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.sourceIntent===intent)));
    document.querySelectorAll('input[name=pf-source-kind]').forEach(input=>input.checked=input.value===kind);
    $w('pf-source-title-label').hidden=intent!=='idea';
    $w('pf-news-url-label').hidden=kind==='text';
    $w('pf-news-url-label').firstChild.textContent=kind==='video'?'Ссылка на видео':'Ссылка на статью';
    $w('pf-news-url').placeholder=kind==='video'?'https://www.tiktok.com/…':'https://…';
    $w('pf-news-text-label').firstChild.textContent=kind==='video'?'Расшифровка или тезисы видео':kind==='article'?'Текст статьи':'Текст идеи';
    $w('pf-news-text').placeholder=kind==='video'?'Вставьте расшифровку или основные тезисы ролика.':kind==='article'?'Вставьте текст или укажите ссылку выше.':'Что предлагает автор?';
    $w('pf-news-text').required=expand && intent==='idea' && kind==='text';
    $w('pf-news-text-label').hidden=kind==='video';$w('pf-text-upload').hidden=kind==='video';$w('pf-video-upload').hidden=kind!=='video';
    $w('pf-question').placeholder=intent==='idea'?'Как применить эту идею к моему портфелю?':'Что эта новость меняет для моего портфеля?';
    $w('pf-question').required=false;
    $w('pf-news-url').disabled=!expand||kind==='text';$w('pf-news-text').disabled=!expand||kind==='video';$w('pf-news-file').disabled=!expand||kind==='video';$w('pf-video-file').disabled=!expand||kind!=='video';$w('pf-source-title').disabled=!expand||intent!=='idea';
  }
  function renderSources() {
    const sources=record.sources || [];
    $w('pf-ideas').hidden=!sources.length;
    Cabinet.setHTML($w('pf-ideas-list'),sources.map(source=>{
      const plan=(record.plans || []).filter(p=>p.source_id===source.id).at(-1);
      return `<button type="button" class="pf-idea-source" data-source-chat="${e(source.id)}"><span class="pf-idea-source-icon">${icon(source.kind==='video'?'video':source.kind==='article'?'link':'idea',21)}</span><span><b>${e(source.title)}</b><small>${{video:'Видео',article:'Статья',text:'Текст'}[source.kind] || 'Идея'}${plan?' · '+(plan.status==='applied'?'Добавлена к плану':'Есть предложение'):''}</small></span>${icon('arrow',17)}</button>`;
    }).join(''));
  }
  function acceptRecord(result){
    record=result;S=result.state;P=result.portfolio;lastSaved=snapshot();lastRender='';renderAll();
  }
  function computeState(){
    if(!record || record.management?.mode!=='agent')return S;
    return {...S,amount_rub:record.current?.amount || S.amount_rub};
  }
  function planMarkup(plan) {
    const before=Object.fromEntries(plan.before.map(s=>[s.sector,s])),after=Object.fromEntries(plan.after.map(s=>[s.sector,s]));
    const keys=[...new Set([...Object.keys(before),...Object.keys(after)])].sort((a,b)=>(before[b]?.weight||after[b]?.weight||0)-(before[a]?.weight||after[a]?.weight||0));
    const pending=plan.status==='pending', confirming=confirmPlan===plan.id;
    return `<section class="pf-plan"><span class="cab-eyebrow">ПРЕДЛОЖЕНИЕ АГЕНТА</span><h4>${e(plan.title)}</h4><div class="pf-plan-radars"><div>${radar(plan.before_axes,'#FFFFFF')}Текущий состав</div><span class="cab-muted">→</span><div>${radar(plan.after_axes,'#FFDD2D')}Предложенный план</div></div>${keys.map(k=>{const b=before[k]?.weight||0,a=after[k]?.weight||0;return `<div class="pf-plan-sector"><div><span>${e(before[k]?.name||after[k]?.name)}</span><span>${percent(b)} → <b style="color:var(--text)">${percent(a)}</b></span></div><div class="pf-compare-bars"><i style="width:${Math.max(1,b*100)}%"></i><i style="width:${Math.max(1,a*100)}%"></i></div></div>`;}).join('')}<div class="pf-plan-checks">${plan.checks.map(c=>'✓ '+e(c.label)).join('<br>')}</div><details><summary>Предлагаемые сделки</summary>${plan.proposal.trades.map(t=>`<div class="pf-trade-row"><span>${t.side==='buy'?'Купить':'Продать'} ${e(t.shortname)}</span><span>≈ ${money(t.rub)}</span></div>`).join('') || '<p>Нет сделок, проходящих минимальный лот.</p>'}</details><p class="pf-plan-description">Обновит план. Для изменения состава потребуется подтверждение ребалансировки.</p>${pending?`<button type="button" class="cab-btn ${confirming?'cab-btn-primary':'cab-btn-secondary'}" data-apply-plan="${e(plan.id)}">${confirming?'Подтверждаю изменение плана':'Применить к плану'}</button>`:'<div class="pf-plan-applied">✓ Вы применили этот сценарий к плану</div>'}</section>`;
  }
  function renderResearch(scroll=true) {
    const plans=Object.fromEntries((record.plans||[]).map(p=>[p.id,p]));
    $w('pf-research-log').innerHTML=``+(record.messages||[]).map(m=>`<article class="pf-research-msg ${m.role==='user'?'user':'assistant'}" ${m.attachment?.source_id?`data-source-id="${e(m.attachment.source_id)}"`:""}>${m.role!=='user'?`<div class="pf-msg-label"><span class="pf-chat-symbol">${icon('sparkle',12)}</span> АГЕНТ</div>${m.title?`<h3>${e(m.title)}</h3>`:''}`:''}<p>${e(m.text)}</p>${m.attachment?`<div class="pf-source-note">${icon('link',11)} ${e(m.attachment.title || m.attachment.url || 'Текст источника')}${m.attachment.status!=='read'?'<br>'+e(m.attachment.notice || ''):''}${m.attachment.text?`<details><summary>Текст, учтённый в анализе</summary><p>${e(m.attachment.text)}</p></details>`:''}</div>`:''}${m.watchpoints?.length?`<ul>${m.watchpoints.map(w=>`<li>${e(w)}</li>`).join('')}</ul>`:''}${m.plan_id && plans[m.plan_id]?planMarkup(plans[m.plan_id]):''}</article>`).join('')+(busy?'<div class="pf-chat-busy"><span class="spin"></span>Сопоставляю вопрос с вашим портфелем…</div>':'');
    if(scroll)$w('pf-research-log').scrollTop=$w('pf-research-log').scrollHeight;
  }
  function openChat(options={}) {
    if(!record)return;focusBeforeChat=document.activeElement;chatOpen=true;
    $w('pf-chat-overlay').hidden=$w('pf-chat-panel').hidden=false;document.body.classList.add('pf-chat-open');
    document.querySelector('main').inert=true;document.querySelector('.top').inert=true;const nav=document.querySelector('.cab-bottom');if(nav)nav.inert=true;
    renderResearch();if(options.intent==='idea')setSource('idea','video');$w('pf-question').focus();
  }
  function closeChat() {
    chatOpen=false;$w('pf-chat-overlay').hidden=$w('pf-chat-panel').hidden=true;document.body.classList.remove('pf-chat-open');
    document.querySelector('main').inert=false;document.querySelector('.top').inert=false;const nav=document.querySelector('.cab-bottom');if(nav)nav.inert=false;
    focusBeforeChat?.focus();
  }
  async function sendQuestion(event) {
    event.preventDefault();if(busy)return;
    const attachmentOpen=!$w('pf-source-fields').hidden;const text=$w('pf-question').value.trim(),source_url=attachmentOpen&&sourceKind!=='text'?$w('pf-news-url').value.trim():'';let article_text=attachmentOpen?$w('pf-news-text').value.trim():'',source_file_name='',source_analysis_mode='provided';
    const intent=attachmentOpen?sourceIntent:'question',source_kind=attachmentOpen?sourceKind:'article',source_title=$w('pf-source-title').value.trim();
    if(!text&&!article_text&&!source_url&&!(attachmentOpen&&$w('pf-video-file').files[0])){$w('pf-question').focus();return;}
    const errorBox=$w('pf-chat-error');errorBox.hidden=true;
    try {
      await flush();busy=true;$w('pf-send-question').disabled=true;renderResearch();
      if(source_kind==='video'&&!$w('pf-source-fields').hidden){const file=$w('pf-video-file').files[0];const analysis=await Cabinet.analyzeVideo(source_url,file?.name||'');article_text=analysis.text;source_file_name=file?.name||'';source_analysis_mode=analysis.mode;}
      const result=await request(endpoint+'/chat',{method:'POST',body:JSON.stringify({text,article_text,source_url,intent,source_kind,source_title,source_file_name,source_analysis_mode})});
      record={...record,...result.record};$w('pf-question').value='';$w('pf-news-text').value='';$w('pf-news-url').value='';$w('pf-news-file').value='';$w('pf-video-file').value='';$w('pf-video-name').textContent='Загрузить видео';$w('pf-source-title').value='';setSource('question','article',false);renderSources();
    } catch(error){errorBox.textContent=error.message;errorBox.hidden=false;}
    finally{busy=false;$w('pf-send-question').disabled=false;renderResearch();$w('pf-question').focus();}
  }
  async function applyPlan(planId) {
    if(busy)return;
    if(confirmPlan!==planId){confirmPlan=planId;renderResearch(false);return;}
    try {
      await flush();busy=true;
      const result=await request(endpoint+'/plans/'+encodeURIComponent(planId)+'/apply',{method:'POST'});
      record=result;S=result.state;P=result.portfolio;lastSaved=snapshot();confirmPlan=null;lastRender='';renderAll();toast('План обновлён. Подтвердите ребалансировку, чтобы изменить состав.');
    } catch(error){toast(error.message);}finally{busy=false;renderResearch(false);}
  }
  async function load() {
    if(!id)return true;
    try {
      [record,catalog]=await Promise.all([request(endpoint),request('/api/universe')]);
      S=record.state;CHAT=record.editor_chat || [];P=record.portfolio;
      try{localStorage.setItem('active-portfolio',id);}catch{}
      lastSaved=snapshot();shell();
      if(!S.executed?.length){currentTab='plan';document.querySelectorAll('[data-view]').forEach(b=>{const on=b.dataset.view==='plan';b.classList.toggle('on',on);b.setAttribute('aria-selected',String(on));});}
      if(params.get('q'))$w('pf-question').value=params.get('q').slice(0,8000);
      if(params.get('chat')==='1')setTimeout(openChat,150);
      return true;
    } catch(error){document.querySelector('main').innerHTML=`<section class="pf-error"><h1>Не удалось открыть портфель</h1><p>${e(error.message)}</p><a href="/account" style="color:var(--text)">Вернуться в аккаунт</a></section>`;return false;}
  }
  return {active:!!id,load,sync,flush,openChat,computeState};
})();
