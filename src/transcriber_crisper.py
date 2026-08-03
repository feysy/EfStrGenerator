import sys
import types
import torch
import numpy as np
from typing import Callable, Optional, Dict, Any

from src.constants import LANGUAGE_MAPPING  # noqa: F401
from src.audio import is_video_file, extract_audio_from_video, cleanup_temp_file
from src.audio_splitter import get_smart_audio_splits  # noqa: F401
from src.srt_formatter import group_words_to_subtitles, write_srt_file


def prepare_audio_track(
    input_filepath: str,
    update_progress: Callable[[str, float], None]
) -> tuple[Optional[str], str]:
    """Extracts audio to a temporary file if input is a video file."""
    temp_audio_path = None
    target_audio_path = input_filepath

    if is_video_file(input_filepath):
        update_progress("Extracting audio track from video...", 0.15)
        temp_audio_path = extract_audio_from_video(input_filepath)
        target_audio_path = temp_audio_path
    else:
        update_progress("Processing audio file...", 0.15)

    return temp_audio_path, target_audio_path


def load_crisper_whisper_model(
    model_size: str,
    backend: str,
    update_progress: Callable[[str, float], None]
) -> Any:
    """Loads CrisperWhisper model."""
    update_progress(f"Loading CrisperWhisper model ({model_size})...", 0.35)

    if backend == "transformers" and "ctranslate2" not in sys.modules:
        try:
            import ctranslate2  # noqa: F401
        except ImportError:
            sys.modules["ctranslate2"] = types.ModuleType("ctranslate2")

    try:
        from crisperwhisper import CrisperWhisperModel
    except ImportError:
        raise ImportError(
            "crisperwhisper package is not installed. "
            "Please install it using 'pip install crisperwhisper'."
        )

    device = "cuda" if torch.cuda.is_available() else "cpu"
    return CrisperWhisperModel(model_size, backend=backend, device=device)


def plan_audio_chunks(
    target_audio_path: str,
    target_chunk_sec: float,
    update_progress: Callable[[str, float], None]
) -> tuple[np.ndarray, list[int], int]:
    """Loads audio and plans smart splits near silence points."""
    update_progress("Loading audio track and planning segment chunks...", 0.50)
    from crisperwhisper.audio import load_audio

    audio_arr = load_audio(target_audio_path)
    sampling_rate = 16000

    split_points = get_smart_audio_splits(
        audio_arr, sampling_rate=sampling_rate, target_chunk_sec=target_chunk_sec
    )
    split_indices = [0] + split_points + [len(audio_arr)]
    return audio_arr, split_indices, sampling_rate


def _collect_words_from_chunk(chunk_res, start_sec: float) -> tuple[list, list]:
    """Extracts word timestamps and fallback segments from a single chunk."""
    words_list = []
    fallback_segments = []

    chunk_words = []
    if hasattr(chunk_res, "words") and chunk_res.words:
        chunk_words = chunk_res.words
    elif isinstance(chunk_res, dict) and "words" in chunk_res:
        chunk_words = chunk_res["words"]

    if chunk_words:
        for w in chunk_words:
            if hasattr(w, "word"):
                from crisperwhisper.result import WordTimestamp
                words_list.append(
                    WordTimestamp(word=w.word, start=w.start + start_sec, end=w.end + start_sec)
                )
            elif isinstance(w, dict):
                words_list.append(
                    {"word": w["word"], "start": w["start"] + start_sec, "end": w["end"] + start_sec}
                )
    else:
        segments = getattr(chunk_res, "segments", []) or (
            chunk_res.get("segments", []) if isinstance(chunk_res, dict) else []
        )
        for seg in segments:
            seg_dict = vars(seg) if hasattr(seg, "__dict__") else seg
            fallback_segments.append(
                {
                    "start": seg_dict.get("start", 0.0) + start_sec,
                    "end": seg_dict.get("end", 0.0) + start_sec,
                    "text": seg_dict.get("text", "").strip(),
                }
            )

    return words_list, fallback_segments


def transcribe_chunks(
    model: Any,
    audio_arr: np.ndarray,
    split_indices: list[int],
    sampling_rate: int,
    kwargs: dict,
    update_progress: Callable[[str, float], None]
) -> tuple[list, list]:
    """Transcribes audio chunk by chunk."""
    words_list = []
    fallback_segments = []
    total_chunks = len(split_indices) - 1

    for i in range(total_chunks):
        start_idx = split_indices[i]
        end_idx = split_indices[i + 1]
        chunk_arr = audio_arr[start_idx:end_idx]

        start_sec = start_idx / sampling_rate
        end_sec = end_idx / sampling_rate

        update_progress(
            f"Transcribing segment {i + 1}/{total_chunks} ({int(start_sec)}s - {int(end_sec)}s)...",
            0.50 + 0.35 * (i / total_chunks),
        )

        if len(chunk_arr) < 1600:
            continue

        chunk_res = model.transcribe(chunk_arr, **kwargs)
        chunk_words, chunk_fallbacks = _collect_words_from_chunk(chunk_res, start_sec)
        words_list.extend(chunk_words)
        fallback_segments.extend(chunk_fallbacks)

    return words_list, fallback_segments


def transcribe_core(
    input_filepath: str,
    language_code: Optional[str] = "en",
    model_size: str = "large",
    mode: str = "verbatim",
    backend: str = "transformers",
    target_chunk_sec: float = 30.0,
    progress_callback: Optional[Callable[[str, float], None]] = None,
) -> list:
    """CrisperWhisper core transcription execution."""
    def update_progress(status: str, percent: float):
        if progress_callback:
            progress_callback(status, percent)

    temp_audio_path = None
    try:
        temp_audio_path, target_audio_path = prepare_audio_track(input_filepath, update_progress)
        model = load_crisper_whisper_model(model_size, backend, update_progress)
        audio_arr, split_indices, sampling_rate = plan_audio_chunks(
            target_audio_path, target_chunk_sec, update_progress
        )

        kwargs: Dict[str, Any] = {"word_timestamps": True}
        if language_code:
            kwargs["language"] = language_code
        if mode in ("verbatim", "intended"):
            kwargs["mode"] = mode

        words_list, fallback_segments = transcribe_chunks(
            model, audio_arr, split_indices, sampling_rate, kwargs, update_progress
        )

        update_progress("Formatting transcript into SRT subtitle structure...", 0.88)
        subtitles = group_words_to_subtitles(words_list) if words_list else fallback_segments
        return subtitles

    finally:
        if temp_audio_path:
            cleanup_temp_file(temp_audio_path)


def transcribe_media_file(
    input_filepath: str,
    output_filepath: str,
    language_code: Optional[str] = "en",
    model_size: str = "large",
    mode: str = "verbatim",
    progress_callback: Optional[Callable[[str, float], None]] = None,
) -> Dict[str, Any]:
    """Wrapper function for local file output."""
    subtitles = transcribe_core(
        input_filepath=input_filepath,
        language_code=language_code,
        model_size=model_size,
        mode=mode,
        backend="transformers",
        target_chunk_sec=10.0,
        progress_callback=progress_callback,
    )

    if progress_callback:
        progress_callback("Saving SRT file...", 0.95)
    write_srt_file(subtitles, output_filepath)

    if progress_callback:
        progress_callback("CrisperWhisper Transcription complete!", 1.0)

    return {"output_filepath": output_filepath, "subtitle_count": len(subtitles)}
    