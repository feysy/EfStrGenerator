import os
from sqlalchemy import create_engine, Column, String, Float, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./jobs.db")

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class JobModel(Base):
    __tablename__ = "jobs"

    id = Column(String, primary_key=True, index=True)
    status = Column(String, default="queued")  # queued, processing, completed, failed
    media_file = Column(String)
    language = Column(String)
    model_size = Column(String)
    transcription_mode = Column(String)
    progress = Column(Float, default=0.0)
    status_text = Column(String, default="Queued")
    result_srt = Column(Text, nullable=True)
    error = Column(Text, nullable=True)


Base.metadata.create_all(bind=engine)
