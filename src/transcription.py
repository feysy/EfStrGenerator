import traceback

from src.api_client import fetch_job_details, update_db_progress, update_db_result, normalize_path
from src.transcriber import transcribe_core
from src.srt_formatter import format_subtitles_as_srt


def process_transcription_job(job_id: str) -> None:
    """Full transcription pipeline wrapper for a single queued worker job."""
    print(f"[{job_id}] Fetching job details...")
    try:
        job_data = fetch_job_details(job_id)
    except Exception as e:
        traceback.print_exc()
        print(f"[{job_id}] Failed to fetch job details: {e}")
        return

    media_file = normalize_path(job_data["media_file"])
    language = job_data["language"]
    model_size = job_data["model_size"]
    transcription_mode = job_data["transcription_mode"]

    try:
        def on_progress(status: str, percent: float):
            update_db_progress(job_id, percent, status)

        # Delegate the actual heavy lifting to the unified transcriber
        subtitles = transcribe_core(
            input_filepath=media_file,
            language_code=language,
            model_size=model_size,
            mode=transcription_mode,
            backend="ct2",
            target_chunk_sec=30.0,
            progress_callback=on_progress,
        )

        # Serialize and upload results
        update_db_progress(job_id, 0.95, "Uploading results...")
        srt_content = format_subtitles_as_srt(subtitles)
        update_db_result(job_id, "completed", result_srt=srt_content)
        print(f"[{job_id}] Transcription completed successfully.")

    except Exception as e:
        traceback.print_exc()
        error_msg = str(e)
        print(f"[{job_id}] Error: {error_msg}")
        update_db_result(job_id, "failed", error=error_msg)
