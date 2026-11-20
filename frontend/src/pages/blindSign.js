import {esc,formData} from '../utils/format.js';
import {notify} from '../components/press.js';
import {send} from '../api.js';

export function render(s){
 const rows=s.myBlind||[];
 const signed=rows.filter(x=>x.signed).length;
 return `<div class="head"><div><div class="eyebrow">BLIND SIGN / ANONYMOUS SAMPLE / B</div><h1>只看样张，不看机判。</h1><p>请按留样号标签取实物样张，凭四色密度与网点扩大独立定缺陷。签字前系统不显示该张任何机判、工单或色标编号。</p></div><span class="mono">BLIND / ${esc(s.user.email)}</span></div>
 <div class="production-layout">
 <section class="section"><h2>凭留样号签字</h2>
 <form id="blind-sign"><label>匿名留样号</label><input name="anon_code" placeholder="B-XXXXXXXX" required autocomplete="off"><label>我的判定</label><select name="defect"><option>合格</option><option>乳化</option><option>偏色</option></select><div class="actions"><button class="primary">确认签字</button></div></form>
 <p class="note">每张只能签字一次；同一结论重试不会重复入账，结论一经签字不可改写。标签与样张仅用于评估。</p>
 <div class="metricstrip"><div>我的留样<b>${rows.length}</b></div><div>已签字<b>${signed}</b></div><div>待签字<b>${rows.length-signed}</b></div></div>
 <h2>待我判定的留样</h2>
 ${rows.map(x=>`<article class="section sample"><div class="eyebrow">留样号 ${esc(x.anon_code)}</div><h3>${x.signed?'已签字 · '+esc(x.signed_defect):'待我的判定'} <span class="status ${x.signed?'pass':''}">${x.signed?'SIGNED':'OPEN'}</span></h3><p class="muted">请在样张台取对应匿名标签的实物，按色标读数独立判定；此页不提供任何机判或车间记录。</p></article>`).join('')||'<p class="note">暂无可评留样。</p>'}
 </section>
 <aside class="section"><h2>盲评纪律</h2><p class="muted">仅凭匿名留样号与实物样张判定；不得查询车间机判、工单或色标记录。签字前页面不展示任何机判结果。盲评样张与标签只用于评估。</p><p class="note">留样号与车间色标、工单的对应关系由主管掌握，签字完成前不对盲评员开放。</p></aside>
 </div>`}

export function bind(s,reload){
 const f=document.querySelector('#blind-sign');
 if(!f)return;
 f.onsubmit=async e=>{
  e.preventDefault();
  try{await send('/blind/sign',formData(f));notify('盲评签字已记录');await reload()}
  catch(err){notify(err.message)}
 };
}
