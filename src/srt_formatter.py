import re
from typing import List, Dict, Any, Union

def format_timestamp(seconds: float) -> str:
    """Converts seconds into SRT timestamp format: HH:MM:SS,mmm"""
    if seconds < 0:
        seconds = 0.0
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int(round((seconds - int(seconds)) * 1000))
    if millis >= 1000:
        secs += 1
        millis -= 1000
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"

def group_words_to_subtitles(words: List[Any], max_words_per_segment: int = 14) -> List[Dict[str, Any]]:
    """
    Groups individual word objects into sentence or block chunks.
    Works with both CrisperWhisper word objects (w.word, w.start, w.end) or dict objects.
    """
    subtitles = []
    current_words = []
    start_time = None
    end_time = 0.0

    for w in words:
        if isinstance(w, dict):
            word_text = w.get("word", "")
            w_start = w.get("start", 0.0)
            w_end = w.get("end", 0.0)
        else:
            word_text = getattr(w, "word", "")
            w_start = getattr(w, "start", 0.0)
            w_end = getattr(w, "end", 0.0)

        cleaned_text = word_text.strip()
        if not cleaned_text:
            continue

        if start_time is None:
            start_time = w_start

        current_words.append(cleaned_text)
        end_time = w_end

        # Check for sentence-ending punctuation or max word threshold
        if re.search(r'[.!?]$', cleaned_text) or len(current_words) >= max_words_per_segment:
            subtitles.append({
                "start": start_time,
                "end": end_time,
                "text": " ".join(current_words)
            })
            current_words = []
            start_time = None

    if current_words:
        subtitles.append({
            "start": start_time if start_time is not None else 0.0,
            "end": end_time,
            "text": " ".join(current_words)
        })

    return subtitles

def format_subtitles_as_srt(subtitles: List[Dict[str, Any]]) -> str:
    """Formats a list of subtitle dicts {"start", "end", "text"} into a single SRT formatted string."""
    blocks = []
    for index, sub in enumerate(subtitles, start=1):
        start_srt = format_timestamp(sub["start"])
        end_srt = format_timestamp(sub["end"])
        blocks.append(f"{index}\n{start_srt} --> {end_srt}\n{sub['text']}\n")
    return "\n".join(blocks) + "\n"

def write_srt_file(subtitles: List[Dict[str, Any]], output_filepath: str) -> None:
    """Writes list of subtitle dicts {"start", "end", "text"} to an SRT format file."""
    content = format_subtitles_as_srt(subtitles)
    with open(output_filepath, "w", encoding="utf-8") as f:
        f.write(content)
