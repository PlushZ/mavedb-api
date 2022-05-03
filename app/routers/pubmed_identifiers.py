from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_, func
from sqlalchemy.orm import Session
from typing import Any, List

from app import deps
from app.models.experiment import Experiment
from app.models.pubmed_identifier import PubmedIdentifier
import app.view_models.pubmed_identifier
from app.view_models.search import TextSearch


router = APIRouter(
    prefix="/api/v1/pubmedIdentifiers",
    tags=["PubMed identifiers"],
    responses={404: {"description": "Not found"}}
)


@router.post(
    '/search',
    status_code=200,
    response_model=List[app.view_models.pubmed_identifier.PubmedIdentifier]
)
def search_pubmed_identifiers(
    search: TextSearch,
    db: Session = Depends(deps.get_db)
) -> Any:
    """
    Search PubMed identifiers.
    """

    query = db.query(PubmedIdentifier)

    if search.text and len(search.text.strip()) > 0:
        lower_search_text = search.text.strip().lower()
        query = query.filter(func.lower(PubmedIdentifier.identifier).contains(lower_search_text))
    else:
        raise HTTPException(status_code=500, detail='Search text is required')

    items = query.order_by(PubmedIdentifier.identifier)\
        .limit(50)\
        .all()
    if not items:
        items = []
    return items