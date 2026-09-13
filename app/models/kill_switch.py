"""Kill switch state model."""
from sqlalchemy import Column, Integer, String, DateTime, Text
from app.core.database import Base
from app.core.time import utc_now


class KillSwitchState(Base):
    __tablename__ = "kill_switch_state"
    id = Column(Integer, primary_key=True, index=True)
    scope = Column(String(64), unique=True, nullable=False, index=True)
    engaged_by = Column(String(255), nullable=True)
    reason = Column(Text, nullable=True)
    engaged_at = Column(DateTime, default=utc_now, nullable=False)
