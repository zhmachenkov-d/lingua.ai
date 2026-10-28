from datetime import datetime

from sqlalchemy import Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, created_at_col


class Textbook(Base):
    """Corpus catalog — textbook identity (AD-11). Ingest is the sole writer."""

    __tablename__ = "textbook"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    title: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = created_at_col()
