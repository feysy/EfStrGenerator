import uuid
import traceback
from fastapi import FastAPI, HTTPException, BackgroundTasks

from src.database import SessionLocal, JobModel
from src.schemas import JobCreate, JobResponse, ProgressUpdate, ResultUpdate
from src.queue import publish_job_to_queue

app = FastAPI(title="EfStrGenerator Subtitle API")


@app.post("/jobs", response_model=JobResponse, status_code=201)
def create_job(payload: JobCreate, background_tasks: BackgroundTasks):
    db = SessionLocal()
    try:
        job_id = str(uuid.uuid4())
        job = JobModel(
            id=job_id,
            media_file=payload.media_file,
            language=payload.language,
            model_size=payload.model_size,
            transcription_mode=payload.transcription_mode,
            status="queued",
            progress=0.0,
            status_text="Queued",
        )
        db.add(job)
        db.commit()
        db.refresh(job)
        background_tasks.add_task(publish_job_to_queue, job_id)
        return job
    finally:
        db.close()


@app.get("/jobs/{job_id}", response_model=JobResponse)
def get_job(job_id: str):
    db = SessionLocal()
    try:
        job = db.query(JobModel).filter(JobModel.id == job_id).first()
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        return job
    finally:
        db.close()


# Internal routes used by the worker
@app.get("/internal/jobs/{job_id}", response_model=JobResponse)
def get_job_internal(job_id: str):
    db = SessionLocal()
    try:
        job = db.query(JobModel).filter(JobModel.id == job_id).first()
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        return job
    finally:
        db.close()


@app.post("/internal/jobs/{job_id}/progress")
def update_job_progress(job_id: str, payload: ProgressUpdate):
    db = SessionLocal()
    try:
        job = db.query(JobModel).filter(JobModel.id == job_id).first()
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        job.progress = payload.percent
        job.status_text = payload.status_text
        if job.status == "queued":
            job.status = "processing"
        db.commit()
        return {"status": "ok"}
    finally:
        db.close()


@app.post("/internal/jobs/{job_id}/result")
def update_job_result(job_id: str, payload: ResultUpdate):
    db = SessionLocal()
    try:
        job = db.query(JobModel).filter(JobModel.id == job_id).first()
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        job.status = payload.status
        job.progress = 1.0 if payload.status == "completed" else 0.0
        job.status_text = "Completed" if payload.status == "completed" else "Failed"
        if payload.result_srt:
            job.result_srt = payload.result_srt
        if payload.error:
            job.error = payload.error
        db.commit()
        return {"status": "ok"}
    finally:
        db.close()
