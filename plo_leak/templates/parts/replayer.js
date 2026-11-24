(function(){
  const SYM={h:'♥',d:'♦',c:'♣',s:'♠'}, RK={10:'T',11:'J',12:'Q',13:'K',14:'A'};
  const card=c=>`<span class="pc ${c[1]}">${RK[c[0]]||c[0]}<i>${SYM[c[1]]}</i></span>`;
  const esc=t=>String(t).replace(/[&<>"]/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[m]));
  function init(el, D){
    const n=D.players.length, hi=D.hero??0;
    const ang=i=>(90+(i-hi)*360/n)*Math.PI/180;
    el.insertAdjacentHTML('beforeend',`<div class="info">${esc(D.date)} · ${esc(D.stake)} · ditt resultat ${D.net>0?'+':''}${D.net} bb</div><div class="felt"></div>
      <div class="txt"></div><div class="ctl"><button data-a="start" title="Början">⏮</button><button data-a="prev" title="Bakåt">◀</button><button data-a="next" title="Framåt">▶</button><button data-a="end" title="Slutet">⏭</button><input type="range" min="0" max="${D.steps.length-1}" value="0"><span class="info stepn"></span></div>
      <div class="info eqn"></div>${D.coach?`<div class="coach ${D.coach_ok?'':'unsure'}" hidden>🎯 ${esc(D.coach)}</div>`:''}`);
    const felt=el.querySelector('.felt'), txt=el.querySelector('.txt'), rng=el.querySelector('input'), stepn=el.querySelector('.stepn'), eqn=el.querySelector('.eqn');
    let k=0;
    function draw(){
      const S=D.steps[k]; let h='';
      const narrow=felt.clientWidth<520, rx=narrow?34:44, ry=narrow?44:43, brx=narrow?20:27, bry=narrow?28:25;
      D.players.forEach((p,i)=>{
        const a=ang(i), x=50+rx*Math.cos(a), y=50+ry*Math.sin(a), bx=50+brx*Math.cos(a), by=50+bry*Math.sin(a);
        const s=S.seats[i]; const eq=S.eq&&S.eq.by[String(i)];
        const cards=p.cards?`<div class="cards ${p.hero?'':'sm'}">${p.cards.map(card).join('')}</div>`:(s.folded?'':`<div class="cards"><span class="back"></span></div>`);
        h+=`<div class="seat ${p.hero?'hero':''} ${s.folded?'fold':''} ${S.actor===i?'act':''}" style="left:${x}%;top:${y}%">${cards}<div class="plate"><b>${esc(p.name)}</b> ${s.stack} bb</div>${(eq!=null&&!s.folded)?`<span class="eqp">${eq.toFixed(0)} %</span>`:''}</div>`;
        if(s.won) h+=`<div class="bet won" style="left:${bx}%;top:${by}%">+${s.won} bb</div>`;
        else if(s.bet>0) h+=`<div class="bet" style="left:${bx}%;top:${by}%">${s.bet} bb</div>`;
      });
      const unk=S.eq&&S.eq.unknown!=null?`<div class="unk">Okända händer: ${S.eq.unknown.toFixed(0)} %</div>`:'';
      h+=`<div class="mid"><div class="board">${S.board.map(card).join('')}</div><div class="pot">Pott ${S.pot} bb</div>${unk}</div>`;
      felt.innerHTML=h;
      txt.textContent=`${S.street}: ${S.text}`; txt.className='txt'+(S.hero_act?' me':'');
      rng.value=k; stepn.textContent=`steg ${k+1} av ${D.steps.length}`;
      const co=el.querySelector('.coach'); if(co) co.hidden=S.street!=='River';
      const live=S.seats.filter(x=>!x.folded).length;
      eqn.textContent=S.eq?('Equity räknas bara mellan händerna vars kort syns (tillsammans 100 %).'+(S.eq.ignored?` ${S.eq.ignored} spelare med okända kort räknas inte med.`:'')):(live>1?'Equity visas när minst två händer med kända kort är kvar.':'');
    }
    el.addEventListener('click',e=>{const a=e.target.dataset.a; if(!a) return;
      k=a==='start'?0:a==='end'?D.steps.length-1:a==='prev'?Math.max(0,k-1):Math.min(D.steps.length-1,k+1); draw();});
    rng.addEventListener('input',()=>{k=+rng.value; draw();});
    el.tabIndex=0; el.addEventListener('keydown',e=>{if(e.key==='ArrowRight'){k=Math.min(D.steps.length-1,k+1);draw();e.preventDefault();} if(e.key==='ArrowLeft'){k=Math.max(0,k-1);draw();e.preventDefault();}});
    draw();
  }
  let dlg=null;
  async function load(b){
    if(!b.dataset.hid) return JSON.parse(b.nextElementSibling.textContent);
    const r=await fetch((window.RPL_API||'')+'/'+encodeURIComponent(b.dataset.hid));
    if(!r.ok) throw new Error('Handen kunde inte hämtas ('+r.status+').');
    return await r.json();
  }
  function target(){
    const dock=document.getElementById('rpl-dock');
    if(dock && dock.offsetParent!==null) return dock;
    if(!dlg){dlg=document.createElement('dialog');dlg.id='rpl-modal';document.body.appendChild(dlg);
      dlg.addEventListener('click',e=>{if(e.target===dlg||e.target.dataset.close) dlg.close();});}
    return dlg;
  }
  // Händerna i samma tabell (synliga rader, i den ordning de visas) – för Föregående/Nästa hand.
  function siblings(b){
    const box=b.closest('table')||b.closest('.panel'); if(!box) return [b];
    return [...box.querySelectorAll('.rpl-open[data-hid]')].filter(x=>x.offsetParent!==null||x===b);
  }
  async function open(b){
    const t=target(), modal=t.tagName==='DIALOG';
    const sib=siblings(b), i=sib.indexOf(b), prev=i>0?sib[i-1]:null, next=i>=0&&i<sib.length-1?sib[i+1]:null;
    const nav=sib.length>1?`<span class="hnav"><button data-h="prev" ${prev?'':'disabled'} title="Föregående hand">⏮ Föregående</button><span class="info">${i+1}/${sib.length}</span><button data-h="next" ${next?'':'disabled'} title="Nästa hand">Nästa hand ⏭</button></span>`:'';
    t.innerHTML=`<div class="mh"><b>Laddar handen …</b>${nav}${modal?'<button data-close="1">Stäng</button>':''}</div><div class="mb"><div class="rpl"></div></div>`;
    t.querySelectorAll('[data-h]').forEach(x=>x.addEventListener('click',e=>{e.stopPropagation();
      const n=x.dataset.h==='prev'?prev:next; if(n) open(n);}));
    if(modal && !t.open) t.showModal();
    try{
      const D=await load(b);
      t.querySelector('.mh b').textContent=b.dataset.label?b.dataset.label:'Handen '+D.id;
      t.querySelector('.mh b').title=D.id;
      const el=t.querySelector('.rpl'); init(el, D); el.focus();
      el.addEventListener('keydown',e=>{if(e.key==='n'&&next){open(next);} if(e.key==='p'&&prev){open(prev);}});
    }catch(err){ t.querySelector('.mb').textContent=err.message; }
  }
  document.addEventListener('click',e=>{
    const b=e.target.closest('.rpl-open'); if(!b) return;
    e.preventDefault(); e.stopPropagation(); open(b);
  });
  window.RPL={open:open};
})();
