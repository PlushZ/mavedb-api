from datetime import date
from sqlalchemy import Column, Date, Integer, String

from app.db.base import Base


class UnitprotIdentifier(Base):
    __tablename__ = 'metadata_uniprotidentifier'

    id = Column(Integer, primary_key=True, index=True)
    identifier = Column(String(256), nullable=False)
    db_name = Column('dbname', String(256), nullable=False)
    db_version = Column('dbversion', String(256), nullable=True)
    url = Column(String(256), nullable=True)
    reference_html = Column(String, nullable=True)
    creation_date = Column(Date, nullable=False, default=date.today)
    modification_date = Column(Date, nullable=False, default=date.today, onupdate=date.today)