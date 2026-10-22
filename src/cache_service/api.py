"""HTTP endpoints."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlmodel import Session

from cache_service import service
from cache_service.db import get_session
from cache_service.schemas import PayloadCreate, PayloadCreated, PayloadRead
from cache_service.transformer import Transformer

router = APIRouter()


def get_transformer(request: Request) -> Transformer:
    return request.app.state.transformer


SessionDep = Annotated[Session, Depends(get_session)]
TransformerDep = Annotated[Transformer, Depends(get_transformer)]


@router.post(
    "/payload",
    response_model=PayloadCreated,
    status_code=status.HTTP_201_CREATED,
    responses={status.HTTP_200_OK: {"model": PayloadCreated, "description": "Payload existed"}},
)
def create_payload(
    body: PayloadCreate, response: Response, session: SessionDep, transformer: TransformerDep
) -> PayloadCreated:
    payload, created = service.create_payload(session, body.list_1, body.list_2, transformer)
    if not created:
        response.status_code = status.HTTP_200_OK
        return PayloadCreated(id=payload.id, message="Payload already exists")
    return PayloadCreated(id=payload.id, message="Payload created")


@router.get("/payload/{payload_id}", response_model=PayloadRead)
def read_payload(payload_id: uuid.UUID, session: SessionDep) -> PayloadRead:
    payload = service.get_payload(session, payload_id)
    if payload is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payload not found")
    return PayloadRead(output=payload.output)


@router.get("/health", include_in_schema=False)
def health() -> dict[str, str]:
    return {"status": "ok"}
