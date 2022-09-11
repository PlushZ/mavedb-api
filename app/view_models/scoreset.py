from datetime import date
from typing import Dict

from pydantic import Field
from pydantic.types import Optional

from app.view_models.base.base import BaseModel
from app.view_models.doi_identifier import DoiIdentifier, DoiIdentifierCreate, SavedDoiIdentifier
from app.view_models.experiment import Experiment, SavedExperiment
from app.view_models.pubmed_identifier import PubmedIdentifier, PubmedIdentifierCreate, SavedPubmedIdentifier
from app.view_models.target_gene import SavedTargetGene, ShortTargetGene, TargetGene, TargetGeneCreate
from app.view_models.user import SavedUser, User
from app.view_models.variant import VariantInDbBase


class ScoresetBase(BaseModel):
    urn: Optional[str]
    title: str
    method_text: str
    abstract_text: str
    short_description: str
    extra_metadata: Dict
    data_usage_policy: Optional[str]
    licence_id: Optional[int]
    replaces_id: Optional[int]
    keywords: Optional[list[str]]


class ScoresetCreate(ScoresetBase):
    experiment_urn: str
    target_gene: TargetGeneCreate
    doi_identifiers: Optional[list[DoiIdentifierCreate]]
    pubmed_identifiers: Optional[list[PubmedIdentifierCreate]]


class ScoresetUpdate(ScoresetBase):
    doi_identifiers: list[DoiIdentifierCreate]
    pubmed_identifiers: list[PubmedIdentifierCreate]
    target_gene: TargetGeneCreate


# Properties shared by models stored in DB
class SavedScoreset(ScoresetBase):
    # id: int
    urn: str
    num_variants: int
    experiment: SavedExperiment
    doi_identifiers: list[SavedDoiIdentifier]
    pubmed_identifiers: list[SavedPubmedIdentifier]
    published_date: Optional[date]
    creation_date: date
    modification_date: date
    created_by: Optional[SavedUser]
    modified_by: Optional[SavedUser]
    target_gene: SavedTargetGene
    dataset_columns: Dict

    class Config:
        orm_mode = True
        arbitrary_types_allowed = True


# Properties to return to non-admin clients
class Scoreset(SavedScoreset):
    experiment: Experiment
    doi_identifiers: list[DoiIdentifier]
    pubmed_identifiers: list[PubmedIdentifier]
    created_by: Optional[User]
    modified_by: Optional[User]
    target_gene: TargetGene
    num_variants: int
    private: bool
    # processing_state: Optional[str]


# Properties to return to clients when variants are requested
class ScoresetWithVariants(Scoreset):
    variants: list[VariantInDbBase]


# Properties to return to admin clients
class AdminScoreset(Scoreset):
    normalised: bool
    approved: bool


class ShortScoreset(BaseModel):
    urn: str
    title: str
    short_description: str
    published_date: Optional[date]
    replaces_id: Optional[int]
    num_variants: int
    experiment: Experiment
    creation_date: date
    modification_date: date
    target_gene: ShortTargetGene
    private: bool

    class Config:
        orm_mode = True
        arbitrary_types_allowed = True
