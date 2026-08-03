import numpy as np
from typing import List


def get_smart_audio_splits(
    audio_array: np.ndarray,
    sampling_rate: int = 16000,
    target_chunk_sec: float = 30.0,
) -> List[int]:
    """
    Finds silence/pauses near target_chunk_sec intervals using absolute energy
    minimisation on the raw audio waveform.
    Returns a list of sample indices where the audio should be split.
    """
    total_samples = len(audio_array)
    target_samples = int(target_chunk_sec * sampling_rate)
    if total_samples <= target_samples:
        return []

    split_points = []
    last_split = 0
    search_margin = int(5 * sampling_rate)
    frame_size = int(0.1 * sampling_rate)  # 100ms frames

    while last_split + target_samples < total_samples:
        target_split = last_split + target_samples
        start_search = max(last_split + search_margin, target_split - search_margin)
        end_search = min(total_samples - search_margin, target_split + search_margin)

        if start_search >= end_search:
            break

        search_region = audio_array[start_search:end_search]
        num_frames = (len(search_region) - frame_size) // frame_size
        if num_frames <= 0:
            best_split = target_split
        else:
            frame_means = []
            for f in range(num_frames):
                frame = search_region[f * frame_size : (f + 1) * frame_size]
                frame_means.append(np.mean(np.abs(frame)))
            best_frame_idx = int(np.argmin(frame_means))
            best_split = start_search + best_frame_idx * frame_size + (frame_size // 2)

        split_points.append(best_split)
        last_split = best_split

    return split_points
