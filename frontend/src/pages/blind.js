import {esc,formData,fixed,localStamp} from '../utils/format.js';
import {notify,jobLabel} from '../components/press.js';
import {send} from '../api.js';

const stateOf=x=>x.outcome||(!x.machine_recorded_at?'待机判回写':!x.signed_at?'待盲评签字':'证据齐全待封存');

export function render(s){
 const enrolled=new Map(s.blind.map(b=>[b.sample_id,b]));
 const sum=s.blindSummary||{};
 const canSeal=s.user.role==='admin';
 return `<div class="head"><div><div class="eyebrow">BLIND REVIEW / SAMPLE POOL / 10</div><h1>留出集判得准，车间漏判了多少要逐张核对。</h1><p>主管在量产抽检收样时圈定盲评名单，车间照常判读放行。盲评员只凭匿名留样号独立定缺陷，签字前看不到任何机判；主管再逐张封存漏判与误报。</p></div></div>
 <div class="production-layout">
 <section class="section"><h2>量产抽检样本池</h2>
 ${s.samples.map(x=>{const p=s.proofs.find(p=>p.id===x.proof_id),b=enrolled.get(x.id);return `<article class="section sample" data-sample="${x.id}"><div class="eyebrow">${jobLabel(s,x.job_id)} / 序${x.sequence} / 已印${x.quantity}张</div><h3>${esc(p?.code)} <span class="status">${esc(p?.defect||'等待worker')}</span></h3><p class="muted">四色${fixed(p?.density_c)}/${fixed(p?.density_m)}/${fixed(p?.density_y)}/${fixed(p?.density_k)} · 网点扩大${fixed(p?.dot_gain)}%<br>${b?`留样号 <b class="mono">${esc(b.anon_code)}</b> · ${esc(stateOf(b))}`:'尚未圈入盲评名单'}</p><div class="actions">${b?'<span class="note" style="margin:0">已入盲评名单</span>':`<button class="primary" data-enroll="${x.id}" ${canSeal?'':'disabled'}>圈定盲评</button>`}</div></article>`}).join('')||'<p class="note">暂无量产抽检样张。先在“量产抽检停复机”登记收样。</p>'}
 </section>
 <section><h2>盲评封存簿</h2>
 <div class="metricstrip"><div>名单总数<b>${sum.total??0}</b></div><div>待机判<b>${sum.awaiting_machine??0}</b></div><div>待签字<b>${sum.awaiting_human??0}</b></div><div>可封存<b>${sum.ready_to_seal??0}</b></div></div>
 <div class="metricstrip"><div>已封存<b>${sum.sealed??0}</b></div><div>漏判<b>${sum.missed??0}</b></div><div>误报<b>${sum.false_alarm??0}</b></div><div>一致率<b>${sum.agreement_rate==null?'—':(sum.agreement_rate*100).toFixed(1)+'%'}</b></div></div>
 ${s.blind.map(b=>`<article class="section sample" data-blind="${b.id}"><div class="eyebrow">留样号 ${esc(b.anon_code)} / ${jobLabel(s,b.job_id)}</div><h3>${esc(b.outcome||stateOf(b))} <span class="status ${b.outcome==='一致'?'pass':b.outcome?'fail':''}">${esc(b.outcome||'待核对')}</span></h3><p class="muted">色标#${b.proof_id} · 机判 ${esc(b.machine_defect||'尚未回写')} · 人工签字 ${esc(b.human_defect||'尚未签字')}<br>签字人 ${esc(b.signed_by||'—')} · 封存人 ${esc(b.sealed_by||'—')} · ${esc(localStamp(b.sealed_at))}${b.signed_before_machine?'<br><b>签字早于机判回写，签字时该张无任何机判可见</b>':''}</p>${b.outcome?`<p class="note">${esc(b.seal_note)}</p>`:`<form class="blind-seal" data-key="${b.id}"><label>封存依据</label><input name="note" minlength="5" placeholder="逐张核对入选后首判与人工签字" required><div class="actions"><button class="magenta" ${canSeal?'':'disabled'}>封存该张</button></div></form><small>${b.evidence_ready?'证据齐全，可封存':'证据未齐，继续等待；封存与回写并发也逐张核对'}</small>`}</article>`).join('')||'<p class="note">盲评名单为空。</p>'}
 <form id="seal-ready"><label>批次封存依据</label><input name="note" minlength="5" placeholder="本次收样证据齐全样张逐张封存" required><div class="actions"><button class="primary" ${canSeal?'':'disabled'}>封存全部已齐样张</button></div></form>
 <p class="note">封存只核对入选后首次机判与人工签字；重试不重复入账，证据未齐的样张本轮继续等待。盲评样张与标签只用于评估，不回写车间判读。</p>
 </section></div>`}

export function bind(s,reload){
 async function act(path,body){try{await send(path,body);await reload();notify('盲评记录已更新');}catch(e){notify(e.message);}}
 document.querySelectorAll('[data-enroll]').forEach(b=>b.onclick=()=>act('/press-samples/'+b.dataset.enroll+'/enroll-blind',{}));
 document.querySelectorAll('.blind-seal').forEach(f=>f.onsubmit=e=>{e.preventDefault();act('/blind-samples/'+f.dataset.key+'/seal',formData(f));});
 document.querySelector('#seal-ready').onsubmit=e=>{e.preventDefault();act('/blind-samples/seal-ready',formData(e.target));};
}
