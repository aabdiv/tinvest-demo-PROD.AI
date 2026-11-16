"use strict";
window.Cabinet = (() => {
  const escape = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const paths = {
    lock: '<rect x="5" y="10" width="14" height="11" rx="3"/><path d="M8 10V6a4 4 0 0 1 8 0v4"/>',
    warning: '<path d="m12 3 10 18H2Z M12 9v5 M12 17v.2"/>', 
    sparkle: '<path d="M12 2v20M2 12h20M5 5l14 14M5 19 19 5"/>',
    account: '<circle cx="12" cy="8" r="3.5"/><path d="M5 21v-2a7 7 0 0 1 14 0v2"/>',
    bot: '<rect x="4" y="7" width="16" height="13" rx="4"/><path d="M12 3v4M1 12h3m16 0h3M9 16h6"/><circle cx="9" cy="11" r=".7"/><circle cx="15" cy="11" r=".7"/>',
    community: '<path d="m12 3 3 6 6 3-6 3-3 6-3-6-6-3 6-3Z"/>',
    pause: '<path d="M8 5v14M16 5v14"/>',
    play: '<path d="m8 4 12 8-12 8Z"/>',
    share: '<path d="M12 16V3m-5 5 5-5 5 5M5 12v8h14v-8"/>',
    chart: '<path d="M4 4v16h16M8 15l4-5 4 2 5-7"/>',
    plus: '<path d="M12 5v14M5 12h14"/>',
    arrow: '<path d="M5 12h14m-6-6 6 6-6 6"/>',
    chat: '<path d="M21 11a8 8 0 0 1-8 8H8l-5 3V11a9 9 0 0 1 18 0Z"/><path d="M8 10h8m-8 4h5"/>',
    video: '<rect x="3" y="3" width="18" height="18" rx="6"/><path d="m10 8 6 4-6 4Z"/>',
    idea: '<path d="M9 18h6m-6 3h6M8 14a7 7 0 1 1 8 0c-1 1-1 2-1 3H9c0-1 0-2-1-3Z"/>',
    oil: '<path d="M12 2S5 10 5 15a7 7 0 0 0 14 0c0-5-7-13-7-13Z"/><path d="M8 15a4 4 0 0 0 4 4"/>',
    shield: '<path d="m12 3 8 3v6c0 5-8 9-8 9s-8-4-8-9V6Z"/><path d="m8 12 3 3 5-6"/>',
    link: '<path d="m10 13 4-4m-6 6-2 2a4 4 0 0 1-5-5l4-4a4 4 0 0 1 5 0m4 0 2-2a4 4 0 0 1 5 5l-4 4a4 4 0 0 1-5 0"/>',
    close: '<path d="m6 6 12 12M6 18 18 6"/>',
    edit: '<path d="m14 5 5 5M4 20l5-1L21 7a3.5 3.5 0 0 0-5-5L4 14Z"/>',
    send: '<path d="m12 20 0-16M5 11l7-7 7 7"/>',
    clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  };
  const icon = (name, size=20) => `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${paths[name] || paths.chart}</svg>`;
  const pin = (x,y) => `<g transform="translate(${x-6},${y-6})" fill="none" stroke="var(--chart-text)" stroke-width="1.3" aria-hidden="true"><path d="M4 1h4L7 5l3 3H2l3-3Z M6 8v4"/></g>`;
  const money = v => Math.round(v || 0).toLocaleString('ru-RU') + ' ₽';
  const percent = v => Math.round(v * 100) + '%';
  const plural = (n, forms) => forms[n % 10 === 1 && n % 100 !== 11 ? 0 : [2,3,4].includes(n % 10) && ![12,13,14].includes(n % 100) ? 1 : 2];
  async function request(path, options={}) {
    const r = await fetch(path, {...options, headers: {'Content-Type':'application/json', ...options.headers}});
    const data = await r.json().catch(()=>({}));
    if (!r.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Не удалось выполнить запрос. Проверьте введённые данные.');
    return data;
  }
  function radar(values, color='var(--chart-accent)') {
    const axes = ['growth','trend','dividends','stability','quality'];
    const points = scale => axes.map((a,i) => {
      const r = typeof scale === 'number' ? scale : Math.max(0, Math.min(10, scale[a] ?? 5))/10;
      return [60+48*r*Math.cos((-90+i*72)*Math.PI/180),60+48*r*Math.sin((-90+i*72)*Math.PI/180)].join(',');
    }).join(' ');
    return `<svg class="cab-radar" viewBox="0 0 120 120" role="img" aria-label="Форма профиля по пяти осям"><polygon points="${points(1)}" fill="none" stroke="var(--chart-grid)"/><polygon points="${points(.65)}" fill="none" stroke="var(--chart-grid)"/><polygon points="${points(values)}" fill="${color}" fill-opacity=".14" stroke="${color}" stroke-width="1.5"/></svg>`;
  }
  function spark(values, color='var(--chart-accent)') {
    if (!values?.length) return '';
    const lo=Math.min(...values), span=Math.max(...values)-lo || 1;
    const pts=values.map((v,i)=>`${i/(values.length-1||1)*300},${44-(v-lo)/span*38}`).join(' ');
    return `<svg class="cab-spark" viewBox="0 0 300 50" preserveAspectRatio="none" role="img" aria-label="Историческая динамика состава"><polyline points="${pts}" fill="none" stroke="${color}" stroke-width="1.5" vector-effect="non-scaling-stroke"/></svg>`;
  }
  function toast(message) {
    let box=document.getElementById('cab-toast');
    if (!box) {box=document.createElement('div');box.id='cab-toast';box.setAttribute('role','status');document.body.append(box);}
    box.textContent=message;box.classList.add('visible');clearTimeout(toast.timer);toast.timer=setTimeout(()=>box.classList.remove('visible'),5000);
  }
  function href(id) {return '/v2?portfolio='+encodeURIComponent(id);}
  const renderedHTML = new WeakMap();
  function setHTML(element, html) {
    if (renderedHTML.get(element) === html) return false;
    element.innerHTML = html;
    renderedHTML.set(element, html);
    return true;
  }
  async function analyzeVideo(source_url, file_name='') {return request('/api/video/analyze',{method:'POST',body:JSON.stringify({source_url,file_name})});}
  function nav() {
    document.body.classList.add('has-account-nav');
    let active='';try {active=localStorage.getItem('active-portfolio') || '';}catch{}
    const isAccount=location.pathname==='/account', isCommunity=location.pathname==='/community';
    const bar=document.createElement('nav');bar.className='cab-bottom';bar.setAttribute('aria-label','Основная навигация');
    bar.innerHTML=`<div><a href="${active?href(active):'/v2'}" class="${!isAccount&&!isCommunity?'active':''}">${icon('chart')}<span>Портфель</span></a><a href="/community" class="${isCommunity?'active':''}" ${isCommunity?'aria-current="page"':''}>${icon('community')}<span>Идеи</span></a><a href="/account" class="${isAccount?'active':''}" ${isAccount?'aria-current="page"':''}>${icon('account')}<span>Аккаунт</span></a></div>`;
    document.body.append(bar);
    document.getElementById('nav-research')?.addEventListener('click',()=>window.PortfolioWorkspace?.openChat());
  }
  document.addEventListener('DOMContentLoaded',nav);
  return {pin, escape,icon,money,percent,plural,request,radar,spark,toast,href,analyzeVideo,setHTML};
})();
