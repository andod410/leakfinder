(function(){
  var root=document.documentElement, body=document.body;
  // tema
  var tt=document.getElementById('theme-t');
  function lab(){ if(tt) tt.textContent = root.getAttribute('data-theme')==='light' ? 'Mörkt tema' : 'Ljust tema'; }
  lab();
  if(tt) tt.addEventListener('click',function(){
    var t = root.getAttribute('data-theme')==='light' ? 'dark' : 'light';
    root.setAttribute('data-theme',t); lab();
    try{ localStorage.setItem('plo-theme',t); }catch(e){}
  });
  // meny och urval på mobil
  function tog(id,cls){ var b=document.getElementById(id); if(b) b.addEventListener('click',function(){ body.classList.toggle(cls); sizes(); }); }
  tog('nav-t','nav-open'); tog('f-t','f-open');
  var sc=document.getElementById('scrim'); if(sc) sc.addEventListener('click',function(){ body.classList.remove('nav-open'); });
  // flikar: varje rubrik (h2) eller graf med data-tab startar en flik
  document.querySelectorAll('.tabbed').forEach(function(box){
    var kids=Array.prototype.slice.call(box.children), panes=[], cur=null, head=[];
    kids.forEach(function(el){
      var starts = el.tagName==='H2' || (el.dataset && el.dataset.tab && el.tagName!=='H2');
      if(starts){ cur={title:(el.dataset.tab||el.textContent).trim(), els:[]}; panes.push(cur); }
      if(cur) cur.els.push(el); else head.push(el);
    });
    if(panes.length<2) return;
    var bar=document.createElement('div'); bar.className='tabs'; bar.setAttribute('role','tablist');
    var wraps=panes.map(function(p,i){
      var w=document.createElement('div'); w.className='tabpane'; w.hidden=i>0;
      p.els.forEach(function(el){ w.appendChild(el); });
      var b=document.createElement('button'); b.type='button'; b.textContent=p.title; b.setAttribute('role','tab');
      b.addEventListener('click',function(){ show(i,true); });
      bar.appendChild(b); return {w:w,b:b,slug:p.title.toLowerCase().replace(/[^a-z0-9åäö]+/g,'-')};
    });
    var anchor=head.length?head[head.length-1].nextSibling:box.firstChild;
    box.insertBefore(bar,anchor);
    wraps.forEach(function(x){ box.appendChild(x.w); });
    function show(i,push){
      wraps.forEach(function(x,j){ x.w.hidden=j!==i; x.b.classList.toggle('on',j===i); });
      if(push){ try{ history.replaceState(null,'','#'+wraps[i].slug); }catch(e){} var y=bar.getBoundingClientRect().top; if(y<0) window.scrollTo(0, window.scrollY+y-parseInt(getComputedStyle(root).getPropertyValue('--toph')||0)); }
      window.dispatchEvent(new Event('resize'));
    }
    var h=decodeURIComponent((location.hash||'').slice(1)), start=0;
    wraps.forEach(function(x,i){ if(x.slug===h) start=i; });
    show(start,false);
  });
  // bb eller dollar: samma val gäller graferna och all-in-tabellen, och sparas till nästa gång
  (function(){
    var sw=document.querySelectorAll('.unitsw'); if(!sw.length) return;
    var u='bb'; try{ u=localStorage.getItem('plo-unit')||'bb'; }catch(e){}
    function set(v){ u=v; document.querySelectorAll('[data-unit]').forEach(function(el){ el.hidden=el.dataset.unit!==v; });
      document.querySelectorAll('.unitsw button').forEach(function(b){ var on=b.dataset.u===v; b.classList.toggle('on',on); b.setAttribute('aria-pressed',on); });
      try{ localStorage.setItem('plo-unit',v); }catch(e){} window.dispatchEvent(new Event('resize')); }
    document.querySelectorAll('.unitsw button').forEach(function(b){ b.addEventListener('click',function(){ set(b.dataset.u); }); });
    set(u);
  })();
  // flikraden fastnar under topplisten
  function sizes(){ var t=document.getElementById('top'); if(t) root.style.setProperty('--toph', t.offsetHeight+'px'); }
  sizes(); window.addEventListener('resize', sizes);
})();
