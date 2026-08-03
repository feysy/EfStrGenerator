import os
import traceback
import requests
from typing import Optional

API_URL = os.getenv("API_URL", "http://localhost:8000")


# ---------------------------------------------------------------------------
# Worker helpers — called by src.transcription to report progress / results
# ---------------------------------------------------------------------------

def normalize_path(path: str) -> str:
    """Converts Windows-style paths to Linux paths when running in a container."""
    if os.name != "nt":  # Linux container
        if path.lower().startswith("c:\\users\\") or path.lower().startswith("c:/users/"):
            path = "/c/Users/" + path[9:]
        path = path.replace("\\", "/")
    return path


def update_db_progress(job_id: str, percent: float, status_text: str) -> None:
    """Reports transcription progress to the API."""
    try:
        url = f"{API_URL}/internal/jobs/{job_id}/progress"
        requests.post(
            url,
            json={"percent": percent, "status_text": status_text},
            headers={"Connection": "close"}
        )
    except Exception as e:
        traceback.print_exc()
        print(f"Error updating progress: {e}")


def update_db_result(
    job_id: str,
    status: str,
    result_srt: Optional[str] = None,
    error: Optional[str] = None,
) -> None:
    """Reports final job status (completed / failed) to the API."""
    try:
        url = f"{API_URL}/internal/jobs/{job_id}/result"
        payload: dict = {"status": status}
        if result_srt:
            payload["result_srt"] = result_srt
        if error:
            payload["error"] = error
        requests.post(
            url,
            json=payload,
            headers={"Connection": "close"}
        )
    except Exception as e:
        traceback.print_exc()
        print(f"Error updating result: {e}")


# ---------------------------------------------------------------------------
# Desktop GUI helpers — called by src.gui to submit jobs and poll results
# ---------------------------------------------------------------------------

def submit_job(
    media_file: str,
    language: str,
    model_size: str,
    transcription_mode: str,
) -> str:
    """Posts a new transcription job and returns the job ID."""
    payload = {
        "media_file": media_file,
        "language": language,
        "model_size": model_size,
        "transcription_mode": transcription_mode,
    }
    res = requests.post(
        f"{API_URL}/jobs",
        json=payload,
        headers={"Connection": "close"}
    )
    res.raise_for_status()
    return res.json()["id"]


def poll_job(job_id: str) -> dict:
    """Fetches current job status from the API."""
    res = requests.get(
        f"{API_URL}/jobs/{job_id}",
        headers={"Connection": "close"}
    )
    res.raise_for_status()
    return res.json()


def fetch_job_details(job_id: str) -> dict:
    """Fetches job details from the internal API endpoint (used by worker)."""
    res = requests.get(
        f"{API_URL}/internal/jobs/{job_id}",
        headers={"Connection": "close"}
    )
    res.raise_for_status()
    return res.json()


def ping_api(timeout: float = 1.0) -> bool:
    """Returns True if the API is reachable."""
    try:
        requests.get(
            f"{API_URL}/jobs/health-check-dummy",
            timeout=timeout,
            headers={"Connection": "close"}
        )
        return True
    except requests.exceptions.ConnectionError:
        return False
