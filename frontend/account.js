"use strict";
(() => {
  const {escape:e,icon,money,percent,plural,request,radar,spark,href}=Cabinet;
  let portfolios=[];
  document.getElementById('edit-portfolio').innerHTML=icon('edit')+'Редактировать существующий портфель';
  document.getElementById('new-portfolio').innerHTML=icon('plus')+'Создать новый портфель';
  document.getElementById('prompt-icon').innerHTML=icon('chat',26);
  document.querySelector('.cab-hero-mark>span').innerHTML=icon('sparkle',56);
  document.querySelector('#example-chat>span').innerHTML=icon('arrow',14);
  function card(p,i) {
    const video=p.source_kind==='video', external=p.strategy_origin==='external' || video, color='var(--chart-accent)';
    const sectors=p.current?.sectors || [];
    return `<a href="${href(p.id)}" class="cab-portfolio ${external?'video':'oil'}" data-portfolio="${e(p.id)}"><div class="cab-card-top"><span class="cab-source-icon">${icon(video?'video':'oil',24)}</span><span class="cab-portfolio-number">ПОРТФЕЛЬ ${String(i+1).padStart(2,'0')}</span><span class="cab-card-arrow">${icon('arrow',18)}</span></div><div class="cab-card-content"><div><span class="cab-source-label">${external?'ЧУЖАЯ ИДЕЯ':'СВОЯ СТРАТЕГИЯ'}</span><h3>${e(p.title)}</h3><p>${e(p.description || '')}</p></div>${radar(p.target,color)}</div><div class="cab-card-tags">${(sectors.length?sectors.slice(0,2).map(s=>`<span>${e(s.name)} ${percent(s.weight)}</span>`):['<span>Состав ещё не выбран</span>']).join('')}<span class="cab-management-tag">${p.management?.mode==='agent'?icon('bot',11)+' Агент '+e(p.management.account?.agent?.name||''):icon('account',10)+' Самостоятельно'}</span></div><div class="cab-card-bottom"><div><small>Бюджет портфеля</small><strong>${money(p.amount_rub)}</strong></div><div class="cab-history">${spark(p.current?.history,color)}<span>Историческая динамика состава</span></div></div><div class="cab-card-foot"><span>${p.horizon_years} ${plural(p.horizon_years,['год','года','лет'])} · ${p.current?.holdings.length || 0} позиций</span><span>Открыть портфель ${icon('arrow',16)}</span></div></a>`;
  }
  async function load() {
    try {
      const data=await request('/api/account/portfolios');portfolios=data.portfolios;
      document.getElementById('portfolio-grid').innerHTML=portfolios.map(card).join('') || '<p>Начните со своей первой идеи.</p>';
      document.getElementById('cab-total').textContent=money(portfolios.reduce((s,p)=>s+p.amount_rub,0));
      document.getElementById('cab-count').textContent=String(portfolios.length).padStart(2,'0');
      document.getElementById('cab-subcount').textContent='';
      document.getElementById('edit-list').innerHTML=portfolios.map(p=>`<a href="${href(p.id)}">${icon(p.source_kind==='video'?'video':'oil',24)}<span><b>${e(p.title)}</b><small>${money(p.amount_rub)} · ${p.horizon_years} ${plural(p.horizon_years,['год','года','лет'])}</small></span>${icon('arrow')}</a>`).join('');
      document.getElementById('edit-portfolio').disabled=!portfolios.length;
      const example=portfolios.find(p=>p.id==='example-oil') || portfolios[0];
      if(example) document.getElementById('example-chat').href=href(example.id)+'&chat=1&q='+encodeURIComponent('Закрыли Ормузский пролив. Что делать с моим портфелем?');
    } catch(error) { const box=document.getElementById('cab-error');box.hidden=false;box.textContent=error.message;document.getElementById('portfolio-grid').innerHTML=''; }
  }
  document.getElementById('new-portfolio').onclick=()=>document.getElementById('create-dialog').showModal();
  document.getElementById('edit-portfolio').onclick=()=>document.getElementById('edit-dialog').showModal();
  document.querySelectorAll('[data-close]').forEach(b=>b.onclick=()=>document.getElementById(b.dataset.close).close());
  function updateSourceForm() {
    const external=document.querySelector('input[name=strategy_origin]:checked').value==='external';
    const kind=document.querySelector('input[name=source_kind]:checked').value;
    document.getElementById('external-source-fields').hidden=!external;
    document.getElementById('create-video-upload').hidden=kind!=='video';document.getElementById('idea-label').hidden=external&&kind==='video';
    document.getElementById('create-url-label').hidden=kind==='text';
    document.getElementById('create-url-label').firstChild.textContent=kind==='video'?'Ссылка на видео':'Ссылка на статью';
    document.querySelector('input[name=source_url]').placeholder=kind==='video'?'https://www.tiktok.com/…':'https://…';
    const input=document.querySelector('textarea[name=text]');
    input.required=external && kind==='text';input.disabled=external&&kind==='video';document.querySelector('input[name=source_url]').disabled=!external||kind==='text';document.getElementById('create-video-file').disabled=!external||kind!=='video';
    document.getElementById('idea-label').firstChild.textContent=!external?'Что для вас важно':kind==='video'?'Расшифровка или тезисы видео':kind==='article'?'Текст статьи':'Идея, которую хотите использовать';
    input.placeholder=!external?'Чего хотите от денег, на какой срок, какой риск допустим?':kind==='video'?'Вставьте расшифровку или основные тезисы ролика.':kind==='article'?'Вставьте текст или укажите ссылку выше.':'Например, небольшая доля технологий в дивидендном портфеле.';
  }
  document.querySelectorAll('input[name=strategy_origin],input[name=source_kind]').forEach(input=>input.addEventListener('change',updateSourceForm));
  updateSourceForm();
  document.getElementById('create-video-file').onchange=event=>{const file=event.target.files[0];if(!file)return;if(file.size>100*1024*1024){Cabinet.toast('Выберите видео до 100 МБ');event.target.value='';return;}document.getElementById('create-video-name').textContent=file.name;document.querySelector('input[name=source_url]').value='';};
  document.getElementById('create-form').onsubmit=async event=>{
    event.preventDefault();const button=document.getElementById('create-submit');button.disabled=true;button.textContent='Сохраняем идею…';
    const fields=Object.fromEntries(new FormData(event.target));fields.amount_rub=Number(fields.amount_rub);fields.horizon_years=Number(fields.horizon_years);
    if(fields.strategy_origin==='own'){fields.source_kind='idea';fields.source_url='';}else if(fields.source_kind==='text') fields.source_url='';
    try {if(fields.strategy_origin==='external'&&fields.source_kind==='video'){button.textContent='Анализируем видео…';const file=document.getElementById('create-video-file').files[0];const analysis=await Cabinet.analyzeVideo(fields.source_url,file?.name||'');fields.text=analysis.text;fields.source_file_name=file?.name||'';fields.source_analysis_mode=analysis.mode;}const p=await request('/api/account/portfolios',{method:'POST',body:JSON.stringify(fields)});location.href=href(p.id);}
    catch(error) {document.getElementById('create-error').textContent=error.message;button.disabled=false;button.textContent='Создать портфель →';}
  };
  load();
})();
