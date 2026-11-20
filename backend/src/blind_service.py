import secrets
from sqlalchemy import select,update
from sqlalchemy.exc import IntegrityError
from fastapi import HTTPException
from .models import ProofSheet
from .production_models import PressSample
from .blind_models import BlindSample
from .services import get,audit,now

PASS='合格'
OUTCOME_AGREE='一致'
OUTCOME_MISSED='漏判'
OUTCOME_FALSE='误报'
OUTCOME_MISCLASS='分类不一致'

def _anon(s):
    while True:
        code='B-'+secrets.token_hex(4).upper()
        if not s.scalar(select(BlindSample.id).where(BlindSample.anon_code==code)):return code

def _find(s,where,lock=True):
    q=select(BlindSample).where(where)
    if lock:q=q.with_for_update()
    return s.scalar(q.execution_options(populate_existing=True))

def _reload(s,key):return s.scalar(select(BlindSample).where(BlindSample.id==key).execution_options(populate_existing=True))

def enroll(s,sample_id,u):
    # 主管在量产抽检收样时圈定盲评名单；车间既有判读与放行流程不变。
    item=s.scalar(select(PressSample).where(PressSample.id==sample_id).with_for_update())
    if not item:raise HTTPException(404,'量产抽检记录不存在')
    existing=_find(s,BlindSample.sample_id==item.id)
    if existing:return existing
    job_id,sample_key,proof_key=item.job_id,item.id,item.proof_id
    proof=get(s,ProofSheet,proof_key)
    for _ in range(3):
        row=BlindSample(job_id=job_id,sample_id=sample_key,proof_id=proof_key,anon_code=_anon(s),enrolled_by=u.email,enrolled_at=now())
        s.add(row)
        try:
            s.flush();break
        except IntegrityError:
            # 留样号撞号或并发圈定同一张：回滚后复用既有名单，否则换号重试。
            s.rollback()
            existing=_find(s,BlindSample.sample_id==sample_key)
            if existing:return existing
            proof=get(s,ProofSheet,proof_key)
    else:raise HTTPException(409,'留样号分配冲突，请重试圈定')
    # 入选时若样张已完成首次机判，沿用该张首判；否则等待 worker 入选后的首个结果。
    record_machine(s,proof)
    audit(s,u,f'圈定量产盲评 {row.anon_code} 色标{proof.code}');s.commit();return row

def record_machine(s,proof):
    # 只接收该张样张的首次机判。条件更新保证 worker 重试、并发回写与主管圈定
    # 之间只有第一条判读入账，后续判读既不覆盖也不重复计入。
    row=_find(s,BlindSample.proof_id==proof.id)
    if not row:return None
    if row.machine_recorded_at:return row
    fresh=s.scalar(select(ProofSheet).where(ProofSheet.id==proof.id).with_for_update().execution_options(populate_existing=True))
    if not fresh or fresh.classification_state!='classified' or not fresh.classified_at or not fresh.defect:return row
    s.execute(update(BlindSample).where(BlindSample.id==row.id,BlindSample.machine_recorded_at.is_(None)).values(machine_defect=fresh.defect,machine_pass=fresh.pass_flag,machine_classified_at=fresh.classified_at,machine_recorded_at=now()))
    return _reload(s,row.id)

def sign(s,anon_code,defect,u):
    row=_find(s,BlindSample.anon_code==anon_code)
    if not row:raise HTTPException(404,'留样号不存在，请核对盲评样张标签')
    if row.signed_at:
        if row.signed_by==u.email and row.human_defect==defect:return row
        raise HTTPException(409,'该留样号已由盲评员签字，不能改写')
    # 条件更新：并发或重试时只有第一次签字落账，后到者读到既有签字再判定是否幂等。
    result=s.execute(update(BlindSample).where(BlindSample.id==row.id,BlindSample.signed_at.is_(None)).values(human_defect=defect,signed_by=u.email,signed_at=now()))
    row=_reload(s,row.id)
    if not result.rowcount:
        if row.signed_by==u.email and row.human_defect==defect:return row
        raise HTTPException(409,'该留样号已由盲评员签字，不能改写')
    audit(s,u,f'盲评签字 {row.anon_code} {defect}');s.commit();return row

def outcome_of(machine,human):
    if machine==human:return OUTCOME_AGREE
    if machine==PASS:return OUTCOME_MISSED
    if human==PASS:return OUTCOME_FALSE
    return OUTCOME_MISCLASS

def _seal_cond(s,row,note,u):
    # 证据齐全才落账；条件更新确保封存与结果回写、重复封存并发时每张只入账一次。
    if not row.machine_recorded_at:raise HTTPException(409,'该张入选后首次机判尚未回写，继续等待')
    if not row.signed_at:raise HTTPException(409,'盲评员尚未签字，继续等待')
    outcome=outcome_of(row.machine_defect,row.human_defect)
    result=s.execute(update(BlindSample).where(BlindSample.id==row.id,BlindSample.outcome=='').values(outcome=outcome,sealed_by=u.email,sealed_at=now(),seal_note=note))
    fresh=_reload(s,row.id)
    if not result.rowcount:
        if fresh and fresh.outcome:return fresh,False
        raise HTTPException(409,'该张盲评结论已被并发更新，请刷新后核对')
    audit(s,u,f'主管封存盲评 {fresh.anon_code} {fresh.outcome}')
    return fresh,True

def seal(s,key,note,u):
    row=_find(s,BlindSample.id==key)
    if not row:raise HTTPException(404,'盲评样张不存在')
    # 已封存的样张直接返回原结果，网络重试不会重复入账或改写结论。
    if row.outcome:return row
    fresh,_=_seal_cond(s,row,note,u);s.commit();return fresh

def seal_ready(s,note,u):
    # 逐张独立提交：某张证据未齐只跳过，不影响同批其他已齐样张；重复与并发调用都不会重复入账。
    ids=s.scalars(select(BlindSample.id).where(BlindSample.outcome=='').order_by(BlindSample.id)).all()
    done=[];waiting=0
    for key in ids:
        row=_find(s,BlindSample.id==key)
        if not row or row.outcome:
            s.commit();continue
        if not (row.machine_recorded_at and row.signed_at):
            waiting+=1;s.commit();continue
        try:
            fresh,sealed=_seal_cond(s,row,note,u);s.commit()
            if sealed:done.append(admin_view(fresh))
        except HTTPException:
            s.rollback();waiting+=1
    return {'sealed':done,'sealed_count':len(done),'waiting':waiting}

def admin_view(r):
    return {'id':r.id,'job_id':r.job_id,'sample_id':r.sample_id,'proof_id':r.proof_id,'anon_code':r.anon_code,'enrolled_by':r.enrolled_by,'enrolled_at':r.enrolled_at,'machine_defect':r.machine_defect,'machine_pass':r.machine_pass,'machine_classified_at':r.machine_classified_at,'machine_recorded_at':r.machine_recorded_at,'human_defect':r.human_defect,'signed_by':r.signed_by,'signed_at':r.signed_at,'signed_before_machine':bool(r.signed_at and (not r.machine_recorded_at or r.signed_at<r.machine_recorded_at)),'outcome':r.outcome,'sealed_by':r.sealed_by,'sealed_at':r.sealed_at,'seal_note':r.seal_note,'evidence_ready':bool(r.machine_recorded_at and r.signed_at)}

def blind_view(s,r,u):
    # 盲评员只看到匿名留样号与本人签字；机判、工单、色标编号与任何色标读数一律不返回。
    # 实物样张与匿名标签在车间外单独流转，接口不参与判读。
    return {'anon_code':r.anon_code,'signed':bool(r.signed_at),'signed_defect':r.human_defect if r.signed_by==u.email else None}

def summary(s):
    rows=s.scalars(select(BlindSample).order_by(BlindSample.id)).all()
    sealed=[r for r in rows if r.outcome]
    names=(OUTCOME_AGREE,OUTCOME_MISSED,OUTCOME_FALSE,OUTCOME_MISCLASS)
    counts={name:sum(1 for r in sealed if r.outcome==name) for name in names}
    return {'total':len(rows),'awaiting_machine':sum(1 for r in rows if not r.machine_recorded_at),'awaiting_human':sum(1 for r in rows if not r.signed_at),'ready_to_seal':sum(1 for r in rows if r.machine_recorded_at and r.signed_at and not r.outcome),'sealed':len(sealed),'agree':counts[OUTCOME_AGREE],'missed':counts[OUTCOME_MISSED],'false_alarm':counts[OUTCOME_FALSE],'misclassified':counts[OUTCOME_MISCLASS],'agreement_rate':round(counts[OUTCOME_AGREE]/len(sealed),4) if sealed else None}
