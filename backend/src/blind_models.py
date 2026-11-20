from sqlalchemy import String,Boolean,ForeignKey,CheckConstraint
from sqlalchemy.orm import Mapped,mapped_column
from .db import Base
class BlindSample(Base):
    __tablename__='blind_samples'
    __table_args__=(CheckConstraint("(machine_defect IS NULL OR machine_defect IN ('合格','乳化','偏色')) AND (human_defect IS NULL OR human_defect IN ('合格','乳化','偏色'))"),)
    id:Mapped[int]=mapped_column(primary_key=True)
    job_id:Mapped[int]=mapped_column(ForeignKey('print_jobs.id'))
    sample_id:Mapped[int]=mapped_column(ForeignKey('press_samples.id'),unique=True)
    proof_id:Mapped[int]=mapped_column(ForeignKey('proof_sheets.id'),unique=True)
    anon_code:Mapped[str]=mapped_column(String(32),unique=True)
    enrolled_by:Mapped[str]=mapped_column(String(100))
    enrolled_at:Mapped[str]=mapped_column(String(40))
    machine_defect:Mapped[str|None]=mapped_column(String(20),nullable=True)
    machine_pass:Mapped[bool|None]=mapped_column(Boolean,nullable=True)
    machine_classified_at:Mapped[str|None]=mapped_column(String(40),nullable=True)
    machine_recorded_at:Mapped[str|None]=mapped_column(String(40),nullable=True)
    human_defect:Mapped[str|None]=mapped_column(String(20),nullable=True)
    signed_by:Mapped[str]=mapped_column(String(100),default='')
    signed_at:Mapped[str|None]=mapped_column(String(40),nullable=True)
    outcome:Mapped[str]=mapped_column(String(24),default='')
    sealed_by:Mapped[str]=mapped_column(String(100),default='')
    sealed_at:Mapped[str|None]=mapped_column(String(40),nullable=True)
    seal_note:Mapped[str]=mapped_column(String(500),default='')
