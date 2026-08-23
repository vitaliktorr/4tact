async function api(url, options={}){
  const opts={...options,headers:{...(options.headers||{})}};
  if(!(options.body instanceof FormData) && options.body && typeof options.body!=='string'){
    opts.headers['Content-Type']='application/json';opts.body=JSON.stringify(options.body);
  }
  try{
    const res=await fetch(url,opts); const data=await res.json().catch(()=>({ok:false,error:'Ошибка сервера'}));
    if(!res.ok || data.ok===false){toast(data.error||'Не удалось выполнить действие');}
    return data;
  }catch(e){toast('Нет соединения с сервером'); return {ok:false,error:e.message};}
}
function money(v){return Number(v||0).toLocaleString('ru-RU',{maximumFractionDigits:2})+' ₽'}
function esc(s){return String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
function toast(text){document.querySelector('.toast')?.remove();const t=document.createElement('div');t.className='toast';t.textContent=text;document.body.appendChild(t);setTimeout(()=>t.remove(),2600)}
function openModal(id){document.getElementById(id).classList.add('open')}
function closeModal(id){document.getElementById(id).classList.remove('open')}
function productCard(p){return `<article class="product-card"><div class="product-image">${p.images?.[0]?`<img src="${p.images[0]}" alt="${esc(p.name)}">`:'<span class="placeholder-img">▦</span>'}</div><h3>${esc(p.name)}</h3><span class="product-meta">${esc(p.brand||'Бренд не указан')} · ${esc(p.car_make||'') } ${esc(p.car_model||'')}</span><span class="product-meta">${esc(p.sku||'')}</span><div class="product-price">${money(p.price)}</div><div class="card-actions"><button class="fav-btn ${p.favorite?'active':''}" onclick="toggleFavorite(${p.id},this)">${p.favorite?'♥':'♡'}</button><button onclick="addToCart(${p.id})">В корзину</button></div></article>`}
async function toggleFavorite(id,btn){const d=await api('/api/favorites/'+id,{method:'POST'});if(d.ok){btn.classList.toggle('active',d.favorite);btn.textContent=d.favorite?'♥':'♡';}}
async function addToCart(id){const d=await api('/api/cart/'+id,{method:'POST'});if(d.ok){toast(d.message||'Добавлено в корзину');}}
window.addEventListener('click',e=>{if(e.target.classList.contains('modal-backdrop'))e.target.classList.remove('open')});
