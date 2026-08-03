from typing import Optional
from pydantic import BaseModel


class JobCreate(BaseModel):
    media_file: str
    language: str
    model_size: str
    transcription_mode: str


class JobResponse(BaseModel):
    id: str
    status: str
    media_file: str
    language: str
    model_size: str
    transcription_mode: str
    progress: float
    status_text: str
    result_srt: Optional[str] = None
    error: Optional[str] = None

    class Config:
        from_attributes = True


class ProgressUpdate(BaseModel):
    percent: float
    status_text: str


class ResultUpdate(BaseModel):
    status: str
    result_srt: Optional[str] = None
    error: Optional[str] = None
