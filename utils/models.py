from sqlalchemy import Column, BigInteger, String, Boolean, DateTime
from sqlalchemy.sql import func as sql_func

from utils.database import Base

class Camera(Base):
    __tablename__ = "cameras"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False, unique=True)
    url = Column(String(255), nullable=False)
    enabled = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, server_default=sql_func.now())
    updated_at = Column(
        DateTime,
        nullable=False,
        server_default=sql_func.now(),
        onupdate=sql_func.now()
    )
    last_capture_attempt = Column(DateTime, nullable=True)
    last_capture_completed = Column(DateTime, nullable=True)
    last_timelapse_run = Column(DateTime, nullable=True)

    def __repr__(self):
        return f"<Camera(id={self.id}, name={self.name}, url={self.url})>"
