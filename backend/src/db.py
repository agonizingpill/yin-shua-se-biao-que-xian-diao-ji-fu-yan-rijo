import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
_url=os.environ['DATABASE_URL']
# MySQL 用 READ COMMITTED 配合行锁；SQLite 仅供本地/测试，按自身隔离级别连接。
engine = create_engine(_url, pool_pre_ping=True, **({'isolation_level':'READ COMMITTED'} if not _url.startswith('sqlite') else {'connect_args':{'check_same_thread':False}}))
Session = sessionmaker(engine, expire_on_commit=False)
class Base(DeclarativeBase): pass
def db_session():
    with Session() as s:
        yield s
