"""Small transaction-safe repository layer."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Generic, TypeVar

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Base

T = TypeVar("T", bound=Base)


class Repository(Generic[T]):
    def __init__(self, session: Session, model: type[T]) -> None:
        self.session = session
        self.model = model

    def add(self, entity: T) -> T:
        self.session.add(entity)
        self.session.flush()
        return entity

    def get(self, identity: Any) -> T | None:
        return self.session.get(self.model, identity)

    def list(self) -> Sequence[T]:
        return self.session.scalars(select(self.model)).all()

    def delete(self, entity: T) -> None:
        self.session.delete(entity)
        self.session.flush()
