from sqlalchemy import Column, BigInteger, String, DateTime, Boolean
from datetime import datetime
from database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(BigInteger, primary_key=True, index=True)
    username = Column(String, nullable=True)
    full_name = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    is_authenticated = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    subscription_expires_at = Column(DateTime, nullable=True)