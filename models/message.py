from datetime import datetime
from sqlalchemy import BigInteger, DateTime, String, Text, Index
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class CargoMessage(Base):
    __tablename__ = "cargo_messages"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, index=True)
    chat_title: Mapped[str | None] = mapped_column(String, nullable=True)
    message_id: Mapped[int] = mapped_column(BigInteger, index=True)
    
    # ID отправителя (логиста), чтобы отличать одного автора от другого
    sender_id: Mapped[int | None] = mapped_column(BigInteger, index=True, nullable=True)
    
    text: Mapped[str] = mapped_column(Text, nullable=False)
    message_date: Mapped[datetime] = mapped_column(DateTime, index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index('idx_chat_message_unique', 'chat_id', 'message_id', unique=True),
    )