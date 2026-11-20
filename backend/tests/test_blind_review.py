import os,itertools
os.environ.setdefault('DATABASE_URL','sqlite:////tmp/pytest-blind.db')
os.environ.setdefault('REDIS_URL','redis://localhost:6379/0')
os.environ.setdefault('JWT_SECRET','test-secret')
os.environ.setdefault('SEED_DEMO','false')

import pytest
from fastapi.testclient import TestClient
from src.main import app
from src import main
from src.db import Base,engine,Session
from src.models import PrintJob,ProofSheet
from src.production_models import PlateSet,PressSample
from scripts.seed_demo import seed

SEQ=itertools.count(1)


class Queue:
    def __init__(self):self.items=[]
    def ping(self):return True
    def rpush(self,name,value):self.items.append(value);return len(self.items)
    def blpop(self,*a,**k):return None


@pytest.fixture()
def client(monkeypatch):
    Base.metadata.drop_all(engine);Base.metadata.create_all(engine);seed()
    monkeypatch.setattr(main,'r',Queue())
    with TestClient(app) as c:
        yield c


def login(c,email):
    r=c.post('/auth/login',json={'email':email,'password':'Press2026!'})
    assert r.status_code==200,r.text
    return {'Authorization':'Bearer '+r.json()['token']}


@pytest.fixture()
def tokens(client):
    return {role:login(client,role+'@qianye.demo') for role in ('admin','pressman','viewer','blind')}


def make_sample(job_status='production'):
    n=next(SEQ)
    with Session() as s:
        job=PrintJob(code=f'PJ-B{n}',title='盲评样张',paper='157g 哑粉',target_density=1.4,status=job_status)
        s.add(job);s.flush()
        plate=PlateSet(job_id=job.id,version='V1',source_note='客户定稿测试版',registration_error_mm=.08,state='ready',approved_by='admin@qianye.demo')
        s.add(plate);s.flush()
        proof=ProofSheet(job_id=job.id,code=f'PS-BLIND-{n}',density_c=1.02,density_m=1.04,density_y=1.0,density_k=1.05,dot_gain=28,classification_state='classifying')
        s.add(proof);s.flush()
        sample=PressSample(job_id=job.id,proof_id=proof.id,plate_id=plate.id,sequence=1,quantity=1000,plate_snapshot={'version':'V1'})
        s.add(sample);s.commit()
        return sample.id,proof.id


def machine_judge(proof_id,defect,stamp='2026-11-20T01:00:00+00:00'):
    """模拟 worker：写入首次机判并调用 finish；重复执行不得覆盖盲评首判。"""
    from src.sampling_service import finish
    with Session() as s:
        p=s.get(ProofSheet,proof_id)
        p.defect=defect;p.pass_flag=defect=='合格';p.classification_state='classified';p.classified_at=stamp
        s.flush();finish(s,p);s.commit()


def enroll(client,tokens,sample_id):
    r=client.post(f'/press-samples/{sample_id}/enroll-blind',headers=tokens['admin'])
    assert r.status_code==200,r.text
    return r.json()


def sign(client,tokens,code,defect):
    r=client.post('/blind/sign',headers=tokens['blind'],json={'anon_code':code,'defect':defect})
    assert r.status_code==200,r.text
    return r.json()


def test_blind_role_isolation(client,tokens):
    for path in ('/jobs','/proofs','/press-samples','/press-holds','/plates','/adjustments','/audits','/paper-lots','/print-packs'):
        assert client.get(path,headers=tokens['blind']).status_code==403,path
    assert client.get('/blind/my-samples',headers=tokens['blind']).status_code==200
    assert client.get('/me',headers=tokens['blind']).json()['role']=='blind'
    # 车间角色也不能进入盲评专用接口
    assert client.get('/blind/my-samples',headers=tokens['admin']).status_code==403
    assert client.get('/blind-samples',headers=tokens['pressman']).status_code==403
    assert client.get('/blind-samples',headers=tokens['viewer']).status_code==403


def test_enroll_requires_supervisor_and_is_idempotent(client,tokens):
    sample_id,_=make_sample()
    assert client.post(f'/press-samples/{sample_id}/enroll-blind',headers=tokens['pressman']).status_code==403
    first=enroll(client,tokens,sample_id)
    second=enroll(client,tokens,sample_id)
    assert first['anon_code']==second['anon_code'] and first['id']==second['id']
    assert client.post('/press-samples/99999/enroll-blind',headers=tokens['admin']).status_code==404


def test_blind_view_exposes_no_machine_verdict(client,tokens):
    sample_id,proof_id=make_sample()
    enrolled=enroll(client,tokens,sample_id)
    machine_judge(proof_id,'乳化')
    rows=client.get('/blind/my-samples',headers=tokens['blind']).json()
    row=next(x for x in rows if x['anon_code']==enrolled['anon_code'])
    # 只给匿名留样号与本人签字状态，连色标读数与机判都不返回
    assert set(row)=={'anon_code','signed','signed_defect'}
    assert row['signed_defect'] is None
    # 盲评页不泄露工单、色标编号或机判
    serialized=client.get('/blind/my-samples',headers=tokens['blind']).text
    assert 'PS-BLIND' not in serialized and '乳化' not in serialized and 'PJ-B' not in serialized
    # 主管接口仍保留机判与签字对照
    admin_row=client.get('/blind-samples',headers=tokens['admin']).json()[0]
    assert admin_row['machine_defect']=='乳化' and set(admin_row)>= {'machine_defect','human_defect','outcome'}


def test_sign_is_blind_only_and_immutable(client,tokens):
    sample_id,_=make_sample()
    code=enroll(client,tokens,sample_id)['anon_code']
    assert client.post('/blind/sign',headers=tokens['admin'],json={'anon_code':code,'defect':'乳化'}).status_code==403
    assert client.post('/blind/sign',headers=tokens['blind'],json={'anon_code':'B-NOPE','defect':'乳化'}).status_code==404
    ok=sign(client,tokens,code,'乳化')
    assert ok['signed'] is True and ok['signed_defect']=='乳化'
    # 同一盲评员同结论重试幂等（留样号大小写不敏感）
    assert sign(client,tokens,code.lower(),'乳化')['signed'] is True
    # 改写结论被拒绝
    assert client.post('/blind/sign',headers=tokens['blind'],json={'anon_code':code,'defect':'合格'}).status_code==409


def test_seal_waits_for_both_evidences_and_is_idempotent(client,tokens):
    sample_id,proof_id=make_sample()
    enrolled=enroll(client,tokens,sample_id)
    key=enrolled['id']
    body={'note':'核对证据齐全'}
    # 机判未回写、盲评未签字：继续等待
    assert client.post(f'/blind-samples/{key}/seal',headers=tokens['admin'],json=body).status_code==409
    machine_judge(proof_id,'乳化')
    assert client.post(f'/blind-samples/{key}/seal',headers=tokens['admin'],json=body).status_code==409
    sign(client,tokens,enrolled['anon_code'],'乳化')
    sealed=client.post(f'/blind-samples/{key}/seal',headers=tokens['admin'],json=body)
    assert sealed.status_code==200,sealed.text
    result=sealed.json()
    assert result['outcome']=='一致' and result['evidence_ready'] is True
    # 重复封存幂等，不重复入账
    repeat=client.post(f'/blind-samples/{key}/seal',headers=tokens['admin'],json={'note':'网络重试再次封存'})
    assert repeat.status_code==200 and repeat.json()['sealed_at']==result['sealed_at']
    summary=client.get('/blind-samples/summary',headers=tokens['admin']).json()
    assert summary['sealed']==1 and summary['agree']==1 and summary['agreement_rate']==1.0


def test_supervisor_only_seal_and_reason_required(client,tokens):
    sample_id,proof_id=make_sample()
    enrolled=enroll(client,tokens,sample_id)
    machine_judge(proof_id,'合格');sign(client,tokens,enrolled['anon_code'],'合格')
    assert client.post(f'/blind-samples/{enrolled["id"]}/seal',headers=tokens['pressman'],json={'note':'车间封存'}).status_code==403
    assert client.post(f'/blind-samples/{enrolled["id"]}/seal',headers=tokens['admin'],json={'note':'短'}).status_code==422


def test_outcomes_capture_missed_and_false_alarm(client,tokens):
    cases=[('合格','乳化','漏判'),('乳化','合格','误报'),('偏色','乳化','分类不一致'),('偏色','偏色','一致')]
    for machine,human,expected in cases:
        sample_id,proof_id=make_sample()
        enrolled=enroll(client,tokens,sample_id)
        machine_judge(proof_id,machine)
        sign(client,tokens,enrolled['anon_code'],human)
        r=client.post(f'/blind-samples/{enrolled["id"]}/seal',headers=tokens['admin'],json={'note':'逐张核对结论'})
        assert r.status_code==200,r.text
        assert r.json()['outcome']==expected,(machine,human,r.json())
    summary=client.get('/blind-samples/summary',headers=tokens['admin']).json()
    assert (summary['missed'],summary['false_alarm'],summary['misclassified'],summary['agree'])==(1,1,1,1)
    assert summary['agreement_rate']==0.25


def test_first_machine_verdict_is_not_overwritten_on_retry(client,tokens):
    sample_id,proof_id=make_sample()
    enroll(client,tokens,sample_id)
    machine_judge(proof_id,'乳化')
    first=client.get('/blind-samples',headers=tokens['admin']).json()[0]
    assert first['machine_defect']=='乳化'
    # worker 重试给出不同结论，不得改写首判或重复入账
    machine_judge(proof_id,'偏色','2026-11-20T02:00:00+00:00')
    again=client.get('/blind-samples',headers=tokens['admin']).json()[0]
    assert again['machine_defect']=='乳化'
    assert again['machine_recorded_at']==first['machine_recorded_at']


def test_machine_verdict_recorded_when_enrolled_after_classification(client,tokens):
    sample_id,proof_id=make_sample()
    machine_judge(proof_id,'偏色')
    enrolled=enroll(client,tokens,sample_id)
    assert enrolled['machine_defect']=='偏色' and enrolled['machine_recorded_at']


def test_seal_ready_batches_but_waits_for_incomplete(client,tokens):
    ready=set()
    for machine,human in (('合格','合格'),('乳化','乳化')):
        sample_id,proof_id=make_sample()
        enrolled=enroll(client,tokens,sample_id)
        machine_judge(proof_id,machine)
        sign(client,tokens,enrolled['anon_code'],human)
        ready.add(enrolled['id'])
    sample_id,proof_id=make_sample()
    pending=enroll(client,tokens,sample_id)
    body={'note':'收样批次逐张封存'}
    result=client.post('/blind-samples/seal-ready',headers=tokens['admin'],json=body).json()
    assert result['sealed_count']==2 and result['waiting']==1
    assert {x['id'] for x in result['sealed']}==ready
    # 未齐的继续等待，不预占不落账
    assert client.get('/blind-samples/summary',headers=tokens['admin']).json()['sealed']==2
    # 补齐证据后再次封存，仅新增该张；重复调用不重复入账
    machine_judge(proof_id,'偏色')
    sign(client,tokens,pending['anon_code'],'偏色')
    second=client.post('/blind-samples/seal-ready',headers=tokens['admin'],json=body).json()
    assert second['sealed_count']==1 and second['waiting']==0
    third=client.post('/blind-samples/seal-ready',headers=tokens['admin'],json=body).json()
    assert third['sealed_count']==0 and third['waiting']==0
    summary=client.get('/blind-samples/summary',headers=tokens['admin']).json()
    assert summary['sealed']==3 and summary['total']==3


def test_concurrent_seal_ready_does_not_double_count(client,tokens):
    """两个主管同时点“封存全部已齐样张”，每张只能入账一次。"""
    import threading
    ids=set()
    for machine,human in (('合格','合格'),('乳化','乳化'),('偏色','偏色')):
        sample_id,proof_id=make_sample()
        enrolled=enroll(client,tokens,sample_id)
        machine_judge(proof_id,machine)
        sign(client,tokens,enrolled['anon_code'],human)
        ids.add(enrolled['id'])
    results=[]
    def worker():
        r=client.post('/blind-samples/seal-ready',headers=tokens['admin'],json={'note':'并发批次逐张封存'})
        results.append(r.json()['sealed_count'])
    threads=[threading.Thread(target=worker) for _ in range(2)]
    [t.start() for t in threads];[t.join() for t in threads]
    assert sum(results)==3,results
    summary=client.get('/blind-samples/summary',headers=tokens['admin']).json()
    assert summary['sealed']==3


def test_blind_evaluation_never_writes_back_to_workshop(client,tokens):
    """盲评签字与封存只读车间判读；样张、色标与工单状态保持原样。"""
    sample_id,proof_id=make_sample()
    enrolled=enroll(client,tokens,sample_id)
    machine_judge(proof_id,'合格')
    with Session() as s:
        before=(s.get(ProofSheet,proof_id).defect,s.get(ProofSheet,proof_id).classification_state,s.get(PressSample,sample_id).state,s.get(PrintJob,s.get(PressSample,sample_id).job_id).status)
    sign(client,tokens,enrolled['anon_code'],'乳化')
    client.post(f'/blind-samples/{enrolled["id"]}/seal',headers=tokens['admin'],json={'note':'评估留档不回写车间'})
    with Session() as s:
        sample=s.get(PressSample,sample_id)
        after=(s.get(ProofSheet,proof_id).defect,s.get(ProofSheet,proof_id).classification_state,sample.state,s.get(PrintJob,sample.job_id).status)
    assert before==after
