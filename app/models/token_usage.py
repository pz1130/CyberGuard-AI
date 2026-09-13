"""Token usage tracking model."""
from sqlalchemy import Column, Integer, String, DateTime, BigInteger
from app.core.database import Base
from app.core.time import utc_now


class TokenUsageLog(Base):
    """Token usage log for LLM API calls."""

    __tablename__ = "token_usage_logs"

    id = Column(Integer, primary_key=True, index=True)
    provider_id = Column(String(100), nullable=False, index=True)
    provider_name = Column(String(100), nullable=False)
    model_name = Column(String(100), nullable=False, index=True)
    prompt_tokens = Column(BigInteger, default=0, nullable=False)
    completion_tokens = Column(BigInteger, default=0, nullable=False)
    total_tokens = Column(BigInteger, default=0, nullable=False)
    call_count = Column(Integer, default=0, nullable=False)
    date_str = Column(String(10), nullable=False, index=True)  # YYYY-MM-DD
    created_at = Column(DateTime, default=utc_now, nullable=False)

    def __repr__(self):
        return f"<TokenUsageLog {self.provider_name}:{self.model_name} on {self.date_str}>"
