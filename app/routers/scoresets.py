import csv
import logging
import io
import re
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, Form, File, HTTPException, Request, UploadFile, Request, status
from fastapi.responses import StreamingResponse
from mavecore.validation.constants import null_values_list
import numpy as np
import pandas as pd
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import MultipleResultsFound
from fastapi.exceptions import HTTPException
from fastapi.encoders import jsonable_encoder

from app import deps
from app.lib.auth import require_current_user
from app.lib.identifiers import find_or_create_doi_identifier, find_or_create_pubmed_identifier
from app.lib.scoresets import create_variants_data, VariantData
from app.models.enums.processing_state import ProcessingState
from app.models.experiment import Experiment
from app.models.reference_map import ReferenceMap
from app.models.scoreset import Scoreset
from app.models.target_gene import TargetGene
from app.models.user import User
from app.models.variant import Variant
from app.models.wild_type_sequence import WildTypeSequence
# from app.tasks.scoreset_tasks import create_variants_task
from app.view_models import scoreset


logger = logging.getLogger(__name__)


null_values_re = re.compile(
    r'\s+|none|nan|na|undefined|n/a|null|nil',
    flags=re.IGNORECASE
)


def is_null(value):
    '''Return True if a string represents a null value.'''
    value = str(value).strip().lower()
    return null_values_re.fullmatch(value) or not value


router = APIRouter(
    prefix='/api/v1/scoresets',
    tags=['scoresets'],
    responses={404: {'description': 'Not found'}}
)


@router.get('/{urn}', status_code=200, response_model=scoreset.Scoreset, responses={404: {}, 500: {}})
def fetch_scoreset(
    *,
    urn: str,
    db: Session = Depends(deps.get_db)
) -> Any:
    """
    Fetch a single scoreset by URN.
    """
    try:
        item = db.query(Scoreset).filter(Scoreset.urn == urn).filter(Scoreset.private.is_(False)).one_or_none()
    except MultipleResultsFound:
        raise HTTPException(
            status_code=500, detail=f'Multiple scoresets with URN {urn} were found.'
        )
    if not item:
        raise HTTPException(
            status_code=404, detail=f'Scoreset with URN {urn} not found'
        )
    return item


@router.get(
    "/{urn}/scores",
    status_code=200,
    responses={
        200: {
            "content": {"text/csv": {}},
            "description": '''Variant scores in CSV format, with four fixed columns (accession, hgvs_nt, hgvs_pro,'''
                ''' and hgvs_splice), plus score columns defined by the scoreset.'''
        }
    }
)
def fetch_scoreset_scores(
    *,
    urn: str,
    db: Session = Depends(deps.get_db),
) -> Any:
    """
    Fetch scores from a scoreset, by scoreset URN.
    """
    scoreset = db.query(Scoreset).filter(Scoreset.urn==urn).first()
    if not scoreset:
        raise HTTPException(
            status_code=404, detail=f"Recipe with ID {id} not found"
        )
    columns = ["accession", "hgvs_nt", "hgvs_pro", "hgvs_splice"] + scoreset.dataset_columns["score_columns"]
    type_column = "score_data"
    rows = format_csv_rows(scoreset.variants, columns=columns, dtype=type_column)
    stream = io.StringIO()
    writer = csv.DictWriter(
        stream, fieldnames=columns, quoting=csv.QUOTE_MINIMAL
    )
    writer.writeheader()
    writer.writerows(rows)
    return StreamingResponse(iter([stream.getvalue()]),
                                 media_type="text/csv"
    )


class HGVSColumns:
    NUCLEOTIDE: str = 'hgvs_nt'  # dataset.constants.hgvs_nt_column
    TRANSCRIPT: str = 'hgvs_splice'  # dataset.constants.hgvs_splice_column
    PROTEIN: str = 'hgvs_pro'  # dataset.constants.hgvs_pro_column

    @classmethod
    def options(cls) -> List[str]:
        return [cls.NUCLEOTIDE, cls.TRANSCRIPT, cls.PROTEIN]


@router.post("/", response_model=scoreset.Scoreset, responses={422: {}})
async def create_scoreset(
    *,
    item_create: scoreset.ScoresetCreate,
    db: Session = Depends(deps.get_db),
    user: User = Depends(require_current_user)
) -> Any:
    """
    Create a scoreset.
    """

    # TODO Confirm that the experiment is editable by this user.

    if item_create is None:
        return None
    experiment = db.query(Experiment).filter(Experiment.urn == item_create.experiment_urn).one_or_none()
    if not experiment:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Unknown experiment')

    wt_sequence = WildTypeSequence(**jsonable_encoder(
        item_create.target_gene.wt_sequence,
        by_alias=False
    ))
    target_gene = TargetGene(
        **jsonable_encoder(
            item_create.target_gene,
            by_alias=False,
            exclude=['reference_maps', 'wt_sequence'],
        ),
        wt_sequence=wt_sequence
    )
    reference_map = ReferenceMap(
        genome_id=item_create.target_gene.reference_maps[0].genome_id,
        target=target_gene
    )
    doi_identifiers = [await find_or_create_doi_identifier(db, identifier.identifier) for identifier in item_create.doi_identifiers or []]
    pubmed_identifiers = [await find_or_create_pubmed_identifier(db, identifier.identifier) for identifier in item_create.pubmed_identifiers or []]
    item = Scoreset(
        **jsonable_encoder(item_create, by_alias=False, exclude=['doi_identifiers', 'experiment_urn', 'keywords', 'pubmed_identifiers', 'target_gene']),
        experiment=experiment,
        target_gene=target_gene,
        doi_identifiers=doi_identifiers,
        pubmed_identifiers=pubmed_identifiers,
        processing_state=ProcessingState.incomplete,
        created_by=user,
        modified_by=user
    )
    # item.experiment = experiment
    # item.processing_state = ProcessingState.incomplete
    await item.set_keywords(db, item_create.keywords)
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.post("/{urn}/variants/data", response_model=scoreset.Scoreset, responses={422: {}})
async def upload_scoreset_variant_data(
    *,
    urn: str,
    counts_file: Optional[UploadFile] = File(None),
    scores_file: UploadFile = File(...),
    db: Session = Depends(deps.get_db),
    user: User = Depends(require_current_user)
) -> Any:
    """
    Upload scores and variant count files for a scoreset, and initiate processing these files to
    create variants.
    """

    # TODO Confirm access.

    item = db.query(Scoreset).filter(Scoreset.urn == urn).filter(Scoreset.private.is_(False)).one_or_none()
    if not item.urn or not scores_file:
        return None

    extra_na_values = set(
        list(null_values_list)
        + [str(x).lower() for x in null_values_list]
        + [str(x).upper() for x in null_values_list]
        + [str(x).capitalize() for x in null_values_list]
    )

    scores_df = pd.read_csv(
        filepath_or_buffer=scores_file.file,
        sep=',',
        encoding='utf-8',
        quotechar='"',
        comment='#',
        na_values=extra_na_values,
        keep_default_na=True,
        dtype={
            **{col: str for col in HGVSColumns.options()},
            # **{c: str for c in cls.HGVSColumns.options()},
            'scores': float
            # MaveScoresDataset.AdditionalColumns.SCORES: float,
        }
    ).replace(null_values_re, np.NaN)
    for c in HGVSColumns.options():
        if c not in scores_df.columns:
            scores_df[c] = np.NaN
    score_columns = {col for col in scores_df.columns if col not in HGVSColumns.options()}

    counts_df = None
    count_columns = []
    if counts_file and counts_file.filename:
        counts_df = pd.read_csv(
            filepath_or_buffer=counts_file.file,
            sep=',',
            encoding='utf-8',
            quotechar='"',
            comment='#',
            na_values=extra_na_values,
            keep_default_na=True,
            dtype={
                **{col: str for col in HGVSColumns.options()},
                # **{c: str for c in cls.HGVSColumns.options()},
                'scores': float
                # MaveScoresDataset.AdditionalColumns.SCORES: float,
            }
        ).replace(null_values_re, np.NaN)
        for c in HGVSColumns.options():
            if c not in counts_df.columns:
                counts_df[c] = np.NaN
        count_columns = {col for col in counts_df.columns if col not in HGVSColumns.options()}

    variants_data = create_variants_data(scores_df, counts_df, None) # , index_col)

    if variants_data:
        logger.error(f'{item.urn}:{variants_data[-1]}')
    logger.error(variants_data)

    # with transaction.atomic():
    logger.error(f'Deleting existing variants for {item.urn}')
    #self.instance.delete_variants()
    logger.error(f'Creating variants for {item.urn}')
    create_variants(db, item, variants_data)
    logger.error(f'Saving {item.urn}')

    item.dataset_columns = {
        'count_columns': list(count_columns),
        'score_columns': list(score_columns)
    }
    item.modified_by = user
    db.add(item)

    #create_variants_task.submit_task(kwargs={
    #    'user_id': None,
    #    'scoreset_urn': item.urn,
    #    'scores': None
    #    # 'counts',
    #    # 'index_col',
    #    # 'dataset_columns'
    #})

    db.commit()
    db.refresh(item)
    return item


# @classmethod
# @transaction.atomic
def create_variants(db, scoreset: Scoreset, variants_data: list[VariantData], batch_size=None) -> int:
    num_variants = len(variants_data)
    variant_urns = bulk_create_urns(num_variants, scoreset)
    variants = (
        Variant(urn=urn, scoreset_id=scoreset.id, **kwargs)
        for urn, kwargs in zip(variant_urns, variants_data)
    )
    db.bulk_save_objects(variants)
    db.add(scoreset)
    return len(scoreset.variants)


# @staticmethod
def bulk_create_urns(n, scoreset, reset_counter=False) -> List[str]:
    start_value = 0 if reset_counter else scoreset.num_variants
    parent_urn = scoreset.urn
    child_urns = [
        "{}#{}".format(parent_urn, start_value + (i + 1)) for i in range(n)
    ]
    current_value = start_value + n
    scoreset.num_variants = current_value
    return child_urns


@router.put("/{urn}", response_model=scoreset.Scoreset, responses={422: {}})
async def update_scoreset(
    *,
    urn: str,
    item_update: scoreset.ScoresetUpdate,
    db: Session = Depends(deps.get_db)
) -> Any:
    """
    Update a scoreset.
    """
    if item_update is None:
        return None
    item = db.query(Scoreset).filter(Scoreset.urn == urn).filter(Scoreset.private.is_(False)).one_or_none()
    if item is None:
        return None
    for var, value in vars(item_update).items():
        setattr(item, var, value) if value else None
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def format_csv_rows(variants, columns, dtype, na_rep="NA"):
    """
    Formats each variant into a dictionary row containing the keys specified
    in `columns`.

    Parameters
    ----------
    variants : list[variant.models.Variant`]
        List of variants.
    columns : list[str]
        Columns to serialize.
    dtype : str, {'scores', 'counts'}
        The type of data requested. Either the 'score_data' or 'count_data'.
    na_rep : str
        String to represent null values.

    Returns
    -------
    list[dict]
    """
    rowdicts = []
    for variant in variants:
        data = {}
        for column_key in columns:
            if column_key == "hgvs_nt":
                value = str(variant.hgvs_nt)
            elif column_key == "hgvs_pro":
                value = str(variant.hgvs_pro)
            elif column_key == "hgvs_splice":
                value = str(variant.hgvs_splice)
            elif column_key == "accession":
                value = str(variant.urn)
            else:
                value = str(variant.data[dtype][column_key])
            if is_null(value):
                value = na_rep
            data[column_key] = value
        rowdicts.append(data)
    return rowdicts