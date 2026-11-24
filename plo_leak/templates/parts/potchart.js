(function(){
  // Stapeldiagram över pottstorlekar: rött (mest minus) → grått (noll) → grönt (mest plus).
  document.querySelectorAll('.pots').forEach(function(box){
    var cfg=box.querySelector('[data-r=cfg]'), plot=box.querySelector('[data-r=plot]'); if(!cfg||!plot) return;
    var rows=JSON.parse(cfg.textContent).filter(function(r){return r.n;}), metric='ev', unit='tot';
    function val(r){
      var tot=metric==='ev'?r.ev:r.net;
      if(unit==='hand') return metric==='ev'?r.ev_hand:r.net_hand;
      if(unit==='b100') return metric==='ev'?r.ev100:r.net100;
      if(unit==='usd') return metric==='ev'?r.ev_money:r.money;
      return tot;
    }
    function fmt(v){ var d=unit==='hand'?2:(unit==='b100'?1:0); var a=Math.abs(v).toLocaleString('sv-SE',{minimumFractionDigits:d,maximumFractionDigits:d});
      return (v>0?'+':v<0?'−':'')+(unit==='usd'?'$':'')+a+(unit==='usd'?'':(unit==='hand'?' bb/hand':unit==='b100'?' bb/100':' bb')); }
    function draw(){
      var vals=rows.map(val), m=Math.max.apply(null,vals.map(Math.abs).concat([1e-9])), sc=plot.clientWidth<520?26:38;
      var h='';
      rows.forEach(function(r,i){
        var v=vals[i], w=Math.abs(v)/m*sc, t=Math.min(1,Math.abs(v)/m);
        var col='color-mix(in srgb, var('+(v>=0?'--good':'--bad')+') '+Math.round(25+75*t)+'%, var(--chip))';
        var bar=v>=0?'left:50%;width:'+w+'%':'left:'+(50-w)+'%;width:'+w+'%';
        h+='<div class="pr" title="'+r.label+' bb: '+r.n+' händer"><div class="pl">'+r.label+'</div><div class="pt"><div class="pz"></div><div class="pb" style="'+bar+';background:'+col+'"></div>'
          +'<div class="pv '+(v>=0?'r':'l')+'" style="'+(v>=0?'left:calc(50% + '+w+'% + 6px)':'right:calc(50% + '+w+'% + 6px)')+'">'+fmt(v)+'</div></div><div class="pn">'+r.n+'</div></div>';
      });
      plot.innerHTML='<div class="ph2"><span>Pott (bb)</span><span>← förlust · vinst →</span><span>händer</span></div>'+h;
    }
    box.querySelectorAll('[data-r=metric] button').forEach(function(b){ b.addEventListener('click',function(){ metric=b.dataset.m; box.querySelectorAll('[data-r=metric] button').forEach(function(x){x.classList.toggle('on',x===b);}); draw(); }); });
    box.querySelectorAll('[data-r=unit] button').forEach(function(b){ b.addEventListener('click',function(){ unit=b.dataset.u; box.querySelectorAll('[data-r=unit] button').forEach(function(x){x.classList.toggle('on',x===b);}); draw(); }); });
    draw();
    var lw=plot.clientWidth; window.addEventListener('resize',function(){ if(plot.clientWidth!==lw){ lw=plot.clientWidth; draw(); } });
  });
})();
