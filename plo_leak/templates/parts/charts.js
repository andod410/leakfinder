(function(){
  // Vinstkurvan: linjer kan slås av och på; axlar och rutnät anpassas efter det som visas.
  var NS='http://www.w3.org/2000/svg';
  function nice(raw){ var m=Math.pow(10,Math.floor(Math.log10(Math.max(raw,1e-9)))), f=raw/m;
    return (f<=1?1:f<=2?2:f<=2.5?2.5:f<=5?5:10)*m; }
  function ticks(lo,hi,want){ var st=nice((hi-lo)/want), out=[]; for(var t=Math.ceil(lo/st)*st;t<=hi+st*1e-6;t+=st) out.push(Math.abs(t)<st*1e-6?0:t); return out; }
  function el(n,a,txt){ var e=document.createElementNS(NS,n); for(var k in a) e.setAttribute(k,a[k]); if(txt!=null) e.textContent=txt; return e; }
  function css(name){ return getComputedStyle(document.documentElement).getPropertyValue(name).trim()||'#888'; }
  document.querySelectorAll('.panel.chart').forEach(function(panel){
    var cfgEl=panel.querySelector('[data-r=cfg]'); if(!cfgEl) return;
    var c=JSON.parse(cfgEl.textContent); if(!c.s) return;
    var money=c.unit==='$', svg=panel.querySelector('svg'), plot=panel.querySelector('[data-r=plot]'), tip=panel.querySelector('[data-r=tip]');
    var store='plo-chart-'+(money?'m':'b');
    try{ var saved=JSON.parse(localStorage.getItem(store)||'null'); if(saved) c.s.forEach(function(x){ if(x.k in saved) x.on=saved[x.k]; }); }catch(e){}
    panel.querySelectorAll('.lg').forEach(function(b){
      var x=c.s.find(function(z){return z.k===b.dataset.k;}); b.classList.toggle('off',!x.on); b.setAttribute('aria-pressed',x.on);
      b.addEventListener('click',function(){ x.on=!x.on; b.classList.toggle('off',!x.on); b.setAttribute('aria-pressed',x.on);
        try{ var o={}; c.s.forEach(function(z){o[z.k]=z.on;}); localStorage.setItem(store,JSON.stringify(o)); }catch(e){}
        draw(); });
    });
    function fmtY(v){ var a=Math.abs(v); var t=a>=10000?Math.round(a).toLocaleString('sv-SE'):a.toLocaleString('sv-SE',{maximumFractionDigits:money&&a<100?2:0});
      return (v<0?'−':'')+(money?'$':'')+t; }
    function fmtX(v){ return v>=10000&&v%1000===0?(v/1000).toLocaleString('sv-SE')+'k':v.toLocaleString('sv-SE'); }
    function fmtV(v){ return (v>=0?'+':'−')+(money?'$':'')+Math.abs(v).toLocaleString('sv-SE',{minimumFractionDigits:money?2:1,maximumFractionDigits:money?2:1})+(money?'':' bb'); }
    var G=null;
    function draw(){
      var W=Math.max(280,plot.clientWidth||800), H=W<560?240:300, vis=c.s.filter(function(x){return x.on;});
      var pl=W<560?46:58, pr=W<560?62:96, pt=12, pb=26, w=W-pl-pr, h=H-pt-pb;
      svg.setAttribute('viewBox','0 0 '+W+' '+H); svg.setAttribute('width',W); svg.setAttribute('height',H);
      while(svg.firstChild) svg.removeChild(svg.firstChild);
      var lo=0, hi=0; vis.forEach(function(x){ x.v.forEach(function(v){ if(v<lo) lo=v; if(v>hi) hi=v; }); });
      if(hi-lo<1){ hi+=1; }
      var yt=ticks(lo,hi,H<260?4:5); lo=Math.min(lo,yt[0]); hi=Math.max(hi,yt[yt.length-1]);
      var n=c.n, X=function(i){return pl+w*(i-1)/Math.max(n-1,1);}, Y=function(v){return pt+h*(hi-v)/(hi-lo);};
      var g=el('g',{'class':'grid'}); svg.appendChild(g);
      yt.forEach(function(t){ g.appendChild(el('line',{x1:pl,x2:pl+w,y1:Y(t),y2:Y(t)})); svg.appendChild(el('text',{'class':'tick',x:pl-6,y:Y(t)+4,'text-anchor':'end'},fmtY(t))); });
      var xs=nice(n/(W<560?3:W<900?5:7)); if(xs<1) xs=1;
      for(var t=xs;t<=n;t+=xs){ g.appendChild(el('line',{x1:X(t),x2:X(t),y1:pt,y2:pt+h})); if(X(t)<pl+w-24) svg.appendChild(el('text',{'class':'tick',x:X(t),y:H-6,'text-anchor':'middle'},fmtX(t))); }
      svg.appendChild(el('text',{'class':'tick',x:pl,y:H-6,'text-anchor':'start'},'0'));
      svg.appendChild(el('text',{'class':'tick',x:pl+w,y:H-6,'text-anchor':'end'},fmtX(n)+' händer'));
      svg.appendChild(el('line',{'class':'zero',x1:pl,x2:pl+w,y1:Y(0),y2:Y(0)}));
      var ends=[];
      vis.slice().reverse().forEach(function(x){
        var d=''; for(var k=0;k<c.x.length;k++) d+=(k?'L':'M')+X(c.x[k]).toFixed(1)+','+Y(x.v[k]).toFixed(1);
        var p=el('path',{'class':'line',d:d}); p.style.stroke='var('+x.color+')'; if(x.dash) p.setAttribute('stroke-dasharray','6 4');
        svg.appendChild(p); ends.push({x:x,y:Y(x.v[x.v.length-1])});
      });
      ends.sort(function(a,b){return a.y-b.y;}); for(var i=1;i<ends.length;i++) if(ends[i].y-ends[i-1].y<14) ends[i].y=ends[i-1].y+14;
      ends.forEach(function(e){ var t=el('text',{'class':'lab',x:pl+w+6,y:e.y+4},fmtY(e.x.v[e.x.v.length-1])); t.style.fill='var('+e.x.color+')'; svg.appendChild(t); });
      var cross=el('line',{'class':'cross',y1:pt,y2:pt+h,style:'display:none'}); svg.appendChild(cross);
      var dots=vis.map(function(x){ var d=el('circle',{'class':'dot',r:4,style:'display:none'}); d.style.fill='var('+x.color+')'; svg.appendChild(d); return d; });
      var band=el('rect',{'class':'selband',y:pt,height:h,x:0,width:0,style:'display:none;fill:var(--accent);opacity:.15'}); svg.appendChild(band);
      var hit=el('rect',{x:pl,y:0,width:w,height:H,fill:'transparent'}); svg.appendChild(hit);
      G={X:X,Y:Y,pl:pl,w:w,n:n,vis:vis,cross:cross,dots:dots,band:band};
      hit.addEventListener('pointermove',function(e){ show(e); if(drag!=null){ var k=idxAt(e); var a=Math.min(drag,k), b=Math.max(drag,k);
        band.setAttribute('x',X(c.x[a])); band.setAttribute('width',Math.max(1,X(c.x[b])-X(c.x[a]))); band.style.display=''; } });
      hit.addEventListener('pointerleave',hide);
      hit.addEventListener('pointerdown',function(e){ drag=idxAt(e); band.style.display='none'; });
      hit.addEventListener('pointerup',function(e){ if(drag==null) return; var k=idxAt(e), a=Math.min(drag,k), b=Math.max(drag,k); drag=null;
        if(b-a<2){ band.style.display='none'; selBox(null); return; } selBox([a,b]); });
    }
    var drag=null;
    function idxAt(e){ var r=svg.getBoundingClientRect(), px=e.clientX-r.left, i=(px-G.pl)/G.w*(G.n-1)+1, k=0, best=1e18;
      for(var j=0;j<c.x.length;j++){ var dd=Math.abs(c.x[j]-i); if(dd<best){best=dd;k=j;} } return k; }
    function selBox(ab){
      var box=panel.querySelector('[data-r=sel]');
      if(!box){ box=document.createElement('div'); box.setAttribute('data-r','sel'); box.className='note'; box.style.margin='6px 0 0'; plot.parentNode.insertBefore(box, plot.nextSibling); }
      if(!ab){ box.innerHTML=''; return; }
      var a=ab[0], b=ab[1], hands=c.x[b]-c.x[a];
      var rows=G.vis.map(function(x){ var d=x.v[b]-x.v[a]; return '<span style="margin-right:12px"><i style="display:inline-block;width:9px;height:9px;border-radius:2px;background:var('+x.color+')"></i> '+x.label+': <b>'+fmtV(d)+'</b>'+(money?'':' ('+(d/Math.max(hands,1)*100).toLocaleString('sv-SE',{maximumFractionDigits:1})+' bb/100)')+'</span>'; }).join('');
      var dates=c.d?(' · '+c.d[a]+' – '+c.d[b]):'';
      var btn=(c.d && document.querySelector('form.fbar'))?' <button class="btn sm" type="button" data-r="selgo">Visa som urval</button>':'';
      box.innerHTML='<b>Markerat:</b> hand '+c.x[a].toLocaleString('sv-SE')+'–'+c.x[b].toLocaleString('sv-SE')+' ('+hands.toLocaleString('sv-SE')+' händer)'+dates+'<br>'+rows+btn+' <button class="btn sm ghost" type="button" data-r="selx">✕</button>';
      var go=box.querySelector('[data-r=selgo]'); if(go) go.onclick=function(){ var f=document.querySelector('form.fbar'); f.fran.value=c.d[a].slice(0,10); f.till.value=c.d[b].slice(0,10);
        var m=document.createElement('input'); m.type='hidden'; m.name='mode'; m.value='visa'; f.appendChild(m); if(window.plSending) plSending(); f.submit(); };
      box.querySelector('[data-r=selx]').onclick=function(){ selBox(null); if(G&&G.band) G.band.style.display='none'; };
    }
    function show(e){
      if(!G||!G.vis.length) return;
      var r=svg.getBoundingClientRect(), k=idxAt(e);
      var xx=G.X(c.x[k]); G.cross.setAttribute('x1',xx); G.cross.setAttribute('x2',xx); G.cross.style.display='';
      G.vis.forEach(function(x,q){ G.dots[q].setAttribute('cx',xx); G.dots[q].setAttribute('cy',G.Y(x.v[k])); G.dots[q].style.display=''; });
      tip.innerHTML='<b>Hand '+c.x[k].toLocaleString('sv-SE')+'</b>'+(c.d?'<div class="note" style="margin:0">'+c.d[k]+'</div>':'')+G.vis.map(function(x){return '<div><i style="background:var('+x.color+')"></i>'+x.label+': '+fmtV(x.v[k])+'</div>';}).join('');
      tip.style.display='block'; var tw=tip.offsetWidth; tip.style.left=Math.min(Math.max(xx+12,0),r.width-tw-4)+'px'; if(xx+12+tw>r.width) tip.style.left=Math.max(xx-tw-12,0)+'px'; tip.style.top='8px';
    }
    function hide(){ if(!G) return; G.cross.style.display='none'; G.dots.forEach(function(d){d.style.display='none';}); tip.style.display='none'; }
    draw();
    var last=plot.clientWidth; window.addEventListener('resize',function(){ if(plot.clientWidth!==last){ last=plot.clientWidth; draw(); } });
  });
})();
