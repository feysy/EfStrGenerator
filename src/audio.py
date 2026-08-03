import os
import traceback
import subprocess
import tempfile
import uuid
from typing import Tuple, Optional

VIDEO_EXTENSIONS = {
    ".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv",
    ".wmv", ".m4v", ".3gp", ".ogv", ".ts", ".mts", ".m2ts"
}

AUDIO_EXTENSIONS = {
    ".mp3", ".wav", ".ogg", ".flac", ".m4a", ".aac",
    ".wma", ".opus", ".alac", ".aiff"
}

def is_video_file(file_path: str) -> bool:
    """Returns True if the given file has a video file extension."""
    ext = os.path.splitext(file_path)[1].lower()
    return ext in VIDEO_EXTENSIONS

def is_media_file(file_path: str) -> bool:
    """Returns True if the file has a supported audio or video extension."""
    ext = os.path.splitext(file_path)[1].lower()
    return ext in VIDEO_EXTENSIONS or ext in AUDIO_EXTENSIONS

def get_ffmpeg_executable() -> str:
    """Finds available ffmpeg executable from imageio-ffmpeg or system PATH."""
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        traceback.print_exc()
        return "ffmpeg"

def extract_audio_from_video(video_path: str) -> str:
    """
    Extracts audio from a video file into a temporary 16kHz WAV file.
    Returns the absolute path to the generated temporary WAV file.
    """
    ffmpeg_exe = get_ffmpeg_executable()
    temp_dir = tempfile.gettempdir()
    unique_id = uuid.uuid4().hex[:8]
    temp_audio_path = os.path.join(temp_dir, f"efstr_audio_{unique_id}.wav")

    cmd = [
        ffmpeg_exe,
        "-y",               # Overwrite output file if exists
        "-i", video_path,   # Input video
        "-vn",              # Disable video recording
        "-acodec", "pcm_s16le", # 16-bit PCM WAV codec
        "-ar", "16000",     # 16kHz sampling rate
        "-ac", "1",         # Mono channel
        temp_audio_path
    ]

    try:
        # Run process hidden on Windows if needed
        creationflags = 0
        if os.name == 'nt':
            creationflags = getattr(subprocess, 'CREATE_NO_WINDOW', 0x08000000)

        process = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=creationflags,
            check=True
        )
    except subprocess.CalledProcessError as e:
        error_msg = e.stderr.decode('utf-8', errors='ignore') if e.stderr else str(e)
        raise RuntimeError(f"Failed to extract audio from video: {error_msg}")
    except FileNotFoundError:
        raise RuntimeError(
            "FFmpeg executable not found. Please install ffmpeg or imageio-ffmpeg package."
        )

    if not os.path.exists(temp_audio_path) or os.path.getsize(temp_audio_path) == 0:
        raise RuntimeError("Extracted audio file is empty or missing.")

    return temp_audio_path

def cleanup_temp_file(file_path: Optional[str]) -> None:
    """Safely removes a temporary file if it exists."""
    if file_path and os.path.exists(file_path):
        try:
            os.remove(file_path)
        except Exception:
            traceback.print_exc()
