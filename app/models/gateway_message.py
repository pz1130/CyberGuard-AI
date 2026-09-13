"""GatewayMessage — task queue between CyberGuard and OpenClaw nodes."""
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from app.core.database import Base
from app.core.time import utc_now


class GatewayMessage(Base):
    __tablename__ = "gateway_messages"

    id = Column(Integer, primary_key=True, index=True)
    agent_id = Column(Integer, ForeignKey("agent_configs.id", ondelete="CASCADE"), nullable=False, index=True)
    # Who sent the task
    sender_user_id = Column(Integer, nullable=True)
    # Original conversation / execution ID for context
    execution_id = Column(String(36), nullable=True, index=True)
    # The task text sent to the agent
    content = Column(Text, nullable=False)
    # pending → delivered → completed / failed
    status = Column(String(20), nullable=False, default="pending", index=True)
    # Result text reported back by the OpenClaw node
    result = Column(Text, nullable=True)
    error = Column(Text, nullable=True)

    created_at = Column(DateTime, nullable=False, default=utc_now)
    delivered_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
