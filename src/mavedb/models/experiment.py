from datetime import date

from typing import Optional, List, TYPE_CHECKING

from sqlalchemy import Boolean, Column, Date, ForeignKey, Integer, String
from sqlalchemy.event import listens_for
from sqlalchemy.ext.associationproxy import association_proxy, AssociationProxy
from sqlalchemy.orm import relationship, Mapped
from sqlalchemy.schema import Table
from sqlalchemy.dialects.postgresql import JSONB

from mavedb.db.base import Base
from mavedb.lib.temp_urns import generate_temp_urn
from mavedb.models.experiment_set import ExperimentSet
from mavedb.models.keyword import Keyword
from mavedb.models.doi_identifier import DoiIdentifier
from mavedb.models.raw_read_identifier import RawReadIdentifier
from mavedb.models.experiment_publication_identifier import ExperimentPublicationIdentifierAssociation
from mavedb.models.user import User
from mavedb.models.publication_identifier import PublicationIdentifier

if TYPE_CHECKING:
    from mavedb.models.score_set import ScoreSet

experiments_doi_identifiers_association_table = Table(
    "experiment_doi_identifiers",
    Base.metadata,
    Column("experiment_id", ForeignKey("experiments.id"), primary_key=True),
    Column("doi_identifier_id", ForeignKey("doi_identifiers.id"), primary_key=True),
)


experiments_keywords_association_table = Table(
    "experiment_keywords",
    Base.metadata,
    Column("experiment_id", ForeignKey("experiments.id"), primary_key=True),
    Column("keyword_id", ForeignKey("keywords.id"), primary_key=True),
)


# experiments_sra_identifiers_association_table = Table(
experiments_raw_read_identifiers_association_table = Table(
    "experiment_sra_identifiers",
    Base.metadata,
    Column("experiment_id", ForeignKey("experiments.id"), primary_key=True),
    Column("sra_identifier_id", ForeignKey("sra_identifiers.id"), primary_key=True),
)


class Experiment(Base):
    __tablename__ = "experiments"

    id = Column(Integer, primary_key=True)

    urn = Column(String(64), nullable=True, default=generate_temp_urn, unique=True, index=True)
    title = Column(String, nullable=False)
    short_description = Column(String, nullable=False)
    abstract_text = Column(String, nullable=False)
    method_text = Column(String, nullable=False)
    extra_metadata = Column(JSONB, nullable=False)

    private = Column(Boolean, nullable=False, default=True)
    approved = Column(Boolean, nullable=False, default=False)
    published_date = Column(Date, nullable=True)
    processing_state = Column(String, nullable=True)

    # TODO Remove this obsolete column.
    num_score_sets = Column("num_scoresets", Integer, nullable=False, default=0)
    score_sets: Mapped[List["ScoreSet"]] = relationship(back_populates="experiment", cascade="all, delete-orphan")

    experiment_set_id = Column(Integer, ForeignKey("experiment_sets.id"), index=True, nullable=True)
    experiment_set: Mapped[Optional[ExperimentSet]] = relationship(back_populates="experiments")

    created_by_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=True)
    created_by: Mapped[User] = relationship("User", foreign_keys="Experiment.created_by_id")
    modified_by_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=True)
    modified_by: Mapped[User] = relationship("User", foreign_keys="Experiment.modified_by_id")
    creation_date = Column(Date, nullable=False, default=date.today)
    modification_date = Column(Date, nullable=False, default=date.today, onupdate=date.today)

    keyword_objs: Mapped[list[Keyword]] = relationship(
        "Keyword", secondary=experiments_keywords_association_table, backref="experiments"
    )
    doi_identifiers: Mapped[list[DoiIdentifier]] = relationship(
        "DoiIdentifier", secondary=experiments_doi_identifiers_association_table, backref="experiments"
    )
    publication_identifier_associations: Mapped[list[ExperimentPublicationIdentifierAssociation]] = relationship(
        "ExperimentPublicationIdentifierAssociation", back_populates="experiment", cascade="all, delete-orphan"
    )
    publication_identifiers: AssociationProxy[List[PublicationIdentifier]] = association_proxy(
        "publication_identifier_associations",
        "publication",
        creator=lambda p: ExperimentPublicationIdentifierAssociation(publication=p, primary=p.primary),
    )

    # sra_identifiers = relationship('SraIdentifier', secondary=experiments_sra_identifiers_association_table, backref='experiments')
    raw_read_identifiers: Mapped[list[RawReadIdentifier]] = relationship(
        "RawReadIdentifier", secondary=experiments_raw_read_identifiers_association_table, backref="experiments"
    )

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
        return [keyword_obj.text for keyword_obj in keyword_objs if keyword_obj.text is not None]

    async def set_keywords(self, db, keywords: Optional[list[str]]):
        if keywords is None:
            self.keyword_objs = []
        else:
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


@listens_for(Experiment, "before_insert")
def create_parent_object(mapper, connect, target):
    if target.experiment_set_id is None:
        target.experiment_set = ExperimentSet(
            extra_metadata={},
            num_experiments=1,
            created_by=target.created_by,
            modified_by=target.modified_by,
        )
