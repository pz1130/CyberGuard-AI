from typing import Optional
from pydantic import BaseModel


class OcrConfigRead(BaseModel):
    enabled: bool
    engine: str
    vision_provider_id: Optional[int] = None
    vision_model: Optional[str] = None
    languages: str
    max_pages: int


class OcrConfigUpdate(BaseModel):
    enabled: Optional[bool] = None
    engine: Optional[str] = None
    vision_provider_id: Optional[int] = None
    vision_model: Optional[str] = None
    languages: Optional[str] = None
    max_pages: Optional[int] = None
