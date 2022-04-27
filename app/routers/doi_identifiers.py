from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_, func
from sqlalchemy.orm import Session
from typing import Any, List

from app import deps
from app.models.experiment import Experiment
from app.models.doi_identifier import DoiIdentifier
import app.view_models.doi_identifier
from app.view_models.search import TextSearch


router = APIRouter(
    prefix="/api/v1/doiIdentifiers",
    tags=["DOI identifiers"],
    responses={404: {"description": "Not found"}}
)


@router.post(
    '/search',
    status_code=200,
    response_model=List[app.view_models.doi_identifier.DoiIdentifier]
)
def search_doi_identifiers(
    search: TextSearch,
    db: Session = Depends(deps.get_db)
) -> Any:
    """
    Search DOI identifiers.
    """

    query = db.query(DoiIdentifier)

    if search.text and len(search.text.strip()) > 0:
        lower_search_text = search.text.strip().lower()
        query = query.filter(func.lower(DoiIdentifier.identifier).contains(lower_search_text))
    else:
        raise HTTPException(status_code=500, detail='Search text is required')

    items = query.order_by(DoiIdentifier.identifier)\
        .limit(50)\
        .all()
    if not items:
        items = []
    return items
