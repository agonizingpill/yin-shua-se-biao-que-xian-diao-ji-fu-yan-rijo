from typing import Literal
from pydantic import Field,field_validator
from .production_schemas import Inputs
class BlindSignInput(Inputs):
    anon_code:str=Field(min_length=4,max_length=32)
    defect:Literal['合格','乳化','偏色']
    @field_validator('anon_code')
    @classmethod
    def normalize(cls,v):
        value=v.strip().upper()
        if len(value)<4:raise ValueError('留样号不能为空')
        return value
class BlindSealInput(Inputs):
    note:str=Field(min_length=5,max_length=500)
    @field_validator('note')
    @classmethod
    def reason(cls,v):
        if len(v.strip())<5:raise ValueError('封存依据至少5字')
        return v.strip()
