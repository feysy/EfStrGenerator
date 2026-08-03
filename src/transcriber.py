import torch
from typing import Callable, Optional, Dict, Any

from src.audio import is_video_file, extract_audio_from_video, cleanup_temp_file
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


def transcribe_core(
    input_filepath: str,
    language_code: Optional[str] = "en",
    model_size: str = "large-v3",
    progress_callback: Optional[Callable[[str, float], None]] = None,
    **kwargs
) -> list:
    """faster-whisper core pipeline using CTranslate2 and stable-ts."""
    def update_progress(status: str, percent: float):
        if progress_callback:
            progress_callback(status, percent)

    temp_audio_path = None
    try:
        temp_audio_path, target_audio_path = prepare_audio_track(input_filepath, update_progress)

        update_progress(f"Loading faster-whisper model ({model_size}) via CTranslate2...", 0.35)
        try:
            import stable_whisper
        except ImportError:
            raise ImportError(
                "stable-ts is not installed. Please run: pip install stable-ts faster-whisper"
            )

        device = "cuda" if torch.cuda.is_available() else "cpu"
        compute_type = "float16" if device == "cuda" else "int8"
        
        update_progress("Device set to: " + device + " Compute type: " + compute_type, 0.38)

        # Load faster-whisper model via stable-ts wrapper
        try:
            model = stable_whisper.load_faster_whisper(
                model_size, 
                device=device, 
                compute_type=compute_type
            )

            update_progress("Transcribing with faster-whisper + VAD alignment...", 0.55)
            
            # Transcribe using CTranslate2 engine with VAD filtering and alignment
            result = model.transcribe(
                target_audio_path,
                language=language_code,
                vad=True,
                regroup=True
            )
        except RuntimeError as e:
            err_str = str(e)
            import traceback
            traceback.print_exc()
            if device == "cuda" and any(term in err_str for term in ["libcublas", "cudnn", "Library", "not found", "cannot be loaded", "CUDA"]):
                update_progress("⚠️ CUDA library load failed. Falling back to CPU...", 0.40)
                device = "cpu"
                compute_type = "int8"
                model = stable_whisper.load_faster_whisper(
                    model_size, 
                    device=device, 
                    compute_type=compute_type
                )
                update_progress("Transcribing on CPU fallback...", 0.55)
                result = model.transcribe(
                    target_audio_path,
                    language=language_code,
                    vad=True,
                    regroup=True
                )
            else:
                raise

        update_progress("Formatting word timestamps into SRT structure...", 0.85)
        words_list = []
        for segment in result.segments:
            for word_obj in segment.words:
                words_list.append({
                    "word": word_obj.word,
                    "start": word_obj.start,
                    "end": word_obj.end
                })

        subtitles = group_words_to_subtitles(words_list)
        return subtitles

    finally:
        if temp_audio_path:
            cleanup_temp_file(temp_audio_path)


def transcribe_media_file(
    input_filepath: str,
    output_filepath: str,
    language_code: Optional[str] = "en",
    model_size: str = "large-v3",
    progress_callback: Optional[Callable[[str, float], None]] = None,
    **kwargs
) -> Dict[str, Any]:
    """Wrapper function for local file output."""
    subtitles = transcribe_core(
        input_filepath=input_filepath,
        language_code=language_code,
        model_size=model_size,
        progress_callback=progress_callback,
    )

    if progress_callback:
        progress_callback("Saving SRT file...", 0.95)
    write_srt_file(subtitles, output_filepath)

    if progress_callback:
        progress_callback("Faster-Whisper Transcription complete!", 1.0)

    return {"output_filepath": output_filepath, "subtitle_count": len(subtitles)}