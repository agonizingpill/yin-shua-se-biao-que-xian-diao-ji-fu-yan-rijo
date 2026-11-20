from fastapi import APIRouter,Depends
from sqlalchemy import select
from .db import db_session
from .auth import admin,blind_only
from .blind_models import BlindSample
from .blind_schemas import BlindSignInput,BlindSealInput
from .blind_service import admin_view,blind_view,enroll,sign,seal,seal_ready,summary
router=APIRouter()
@router.post('/press-samples/{key}/enroll-blind')
def enroll_blind(key:int,s=Depends(db_session),u=Depends(admin)):
    # 收样时由主管圈定；车间照常判读放行，盲评独立进行。
    return admin_view(enroll(s,key,u))
@router.get('/blind-samples')
def blind_list(s=Depends(db_session),u=Depends(admin)):
    return [admin_view(x) for x in s.scalars(select(BlindSample).order_by(BlindSample.id))]
@router.get('/blind-samples/summary')
def blind_summary(s=Depends(db_session),u=Depends(admin)):
    return summary(s)
@router.post('/blind-samples/{key}/seal')
def blind_seal(key:int,p:BlindSealInput,s=Depends(db_session),u=Depends(admin)):
    return admin_view(seal(s,key,p.note,u))
@router.post('/blind-samples/seal-ready')
def blind_seal_ready(p:BlindSealInput,s=Depends(db_session),u=Depends(admin)):
    # 证据齐全的逐张封存；未齐的本轮继续等待，不预占、不丢失。
    return seal_ready(s,p.note,u)
@router.get('/blind/my-samples')
def my_samples(s=Depends(db_session),u=Depends(blind_only)):
    return [blind_view(s,x,u) for x in s.scalars(select(BlindSample).order_by(BlindSample.id))]
@router.post('/blind/sign')
def blind_sign(p:BlindSignInput,s=Depends(db_session),u=Depends(blind_only)):
    return blind_view(s,sign(s,p.anon_code,p.defect,u),u)
