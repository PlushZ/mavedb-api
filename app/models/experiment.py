from datetime import date
from sqlalchemy import Boolean, Column, Date, ForeignKey, Integer, String
from sqlalchemy.event import listens_for
from sqlalchemy.orm import relationship
from sqlalchemy.schema import Table

from app.db.base import Base
from app.deps import JSONB
from app.lib.urns import generate_temp_urn
from app.models.experiment_set import ExperimentSet
from app.models.keyword import Keyword

experiments_doi_identifiers_association_table = Table(
    'dataset_experiment_doi_ids',
    Base.metadata,
    Column('experiment_id', ForeignKey('dataset_experiment.id'), primary_key=True),
    Column('doiidentifier_id', ForeignKey('metadata_doiidentifier.id'), primary_key=True)
)


experiments_keywords_association_table = Table(
    'dataset_experiment_keywords',
    Base.metadata,
    Column('experiment_id', ForeignKey('dataset_experiment.id'), primary_key=True),
    Column('keyword_id', ForeignKey('metadata_keyword.id'), primary_key=True)
)


experiments_pubmed_identifiers_association_table = Table(
    'dataset_experiment_pubmed_ids',
    Base.metadata,
    Column('experiment_id', ForeignKey('dataset_experiment.id'), primary_key=True),
    Column('pubmedidentifier_id', ForeignKey('metadata_pubmedidentifier.id'), primary_key=True)
)


experiments_sra_identifiers_association_table = Table(
    'dataset_experiment_sra_ids',
    Base.metadata,
    Column('experiment_id', ForeignKey('dataset_experiment.id'), primary_key=True),
    Column('sraidentifier_id', ForeignKey('metadata_sraidentifier.id'), primary_key=True)
)


class Experiment(Base):
    __tablename__ = 'dataset_experiment'

    id = Column(Integer, primary_key=True, index=True)

    urn = Column(String(64), nullable=True, default=generate_temp_urn)  # index=True, nullable=True
    title = Column(String(250), nullable=False)
    short_description = Column(String, nullable=False)
    abstract_text = Column(String, nullable=False)
    method_text = Column(String, nullable=False)
    extra_metadata = Column(JSONB, nullable=False)

    private = Column(Boolean, nullable=False, default=False)
    approved = Column(Boolean, nullable=False, default=False)
    published_date = Column('publish_date', Date, nullable=True)
    processing_state = Column(String(32), nullable=True)

    # TODO Refactor the way we track the number of scoresets?
    num_scoresets = Column('last_child_value', Integer, nullable=False, default=0)

    experiment_set_id = Column('experimentset_id', Integer, ForeignKey('dataset_experimentset.id'), nullable=True)
    experiment_set = relationship('ExperimentSet', backref='experiments')

    created_by_id = Column(Integer, ForeignKey('auth_user.id'), nullable=True)
    created_by = relationship('User', foreign_keys='Experiment.created_by_id')
    modified_by_id = Column(Integer, ForeignKey('auth_user.id'), nullable=True)
    modified_by = relationship('User', foreign_keys='Experiment.modified_by_id')
    creation_date = Column(Date, nullable=False, default=date.today)
    modification_date = Column(Date, nullable=False, default=date.today, onupdate=date.today)

    scoresets = relationship('Scoreset', back_populates='experiment')
    keyword_objs = relationship('Keyword', secondary=experiments_keywords_association_table, backref='experiments')
    doi_identifiers = relationship('DoiIdentifier', secondary=experiments_doi_identifiers_association_table, backref='experiments')
    pubmed_identifiers = relationship('PubmedIdentifier', secondary=experiments_pubmed_identifiers_association_table, backref='experiments')
    sra_identifiers = relationship('SraIdentifier', secondary=experiments_sra_identifiers_association_table, backref='experiments')

    # Unfortunately, we can't use association_proxy here, because in spite of what the documentation seems to imply, it
    # doesn't check for a pre-existing keyword with the same text.
    # keywords = association_proxy('keyword_objs', 'text', creator=lambda text: Keyword(text=text))

    # _updated_keywords: list[str] = None
    # _updated_doi_identifiers: list[str] = None

    @property
    def keywords(self) -> list[str]:
        # if self._updated_keywords:
        #     return self._updated_keywords
        # else:
        keyword_objs = self.keyword_objs or []  # getattr(self, 'keyword_objs', [])
        return list(map(lambda keyword_obj: keyword_obj.text, keyword_objs))

    async def set_keywords(self, db, keywords: list[str]):
        self.keyword_objs = [await self._find_or_create_keyword(db, text) for text in keywords]

    # See https://gist.github.com/tachyondecay/e0fe90c074d6b6707d8f1b0b1dcc8e3a
    # @keywords.setter
    # async def set_keywords(self, db, keywords: list[str]):
    #     self._keyword_objs = [await self._find_or_create_keyword(text) for text in keywords]

    async def _find_or_create_keyword(self, db, keyword_text):
        keyword_obj = db.query(Keyword).filter(Keyword.text == keyword_text).one_or_none()
        if not keyword_obj:
            keyword_obj = Keyword(text=keyword_text)
            # object_session.add(keyword_obj)
        return keyword_obj


@listens_for(Experiment, 'before_insert')
def create_parent_object(mapper, connect, target):
    if target.experiment_set_id is None:
        target.experiment_set = ExperimentSet(
            title=target.title,
            method_text=target.method_text,
            abstract_text=target.abstract_text,
            short_description=target.short_description,
            extra_metadata={},
            num_experiments=1,
            created_by=target.created_by,
            modified_by=target.modified_by
        )