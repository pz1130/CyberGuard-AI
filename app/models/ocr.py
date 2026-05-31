"""Global OCR configuration (single row)."""
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String

from app.core.database import Base


class OcrConfig(Base):
    """Single-row global OCR settings (mirrors SsoConfig)."""

    __tablename__ = "ocr_config"

    id = Column(Integer, primary_key=True)
    enabled = Column(Boolean, nullable=False, default=True)
    engine = Column(String(20), nullable=False, default="tesseract")  # tesseract | vision
    vision_provider_id = Column(Integer, ForeignKey("providers.id"), nullable=True)
    vision_model = Column(String(255), nullable=True)
    languages = Column(String(64), nullable=False, default="chi_sim+eng")
    max_pages = Column(Integer, nullable=False, default=30)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
