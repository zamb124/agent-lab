"""Извлечение аудиодорожки из видеоконтейнера через ffmpeg."""

import subprocess
import tempfile
from pathlib import Path


def extract_audio_from_video(*, video_bytes: bytes, base_name: str) -> tuple[bytes, str]:
    """Извлекает аудио из видео в MP3 моно 16 kHz через ffmpeg.

    Args:
        video_bytes: байты видеофайла
        base_name: исходное имя файла (для формирования имени аудио)

    Returns:
        (audio_bytes, audio_file_name)
    """
    if not video_bytes:
        raise ValueError("video_bytes не может быть пустым.")
    stem = Path(base_name).stem or "recording"
    with tempfile.TemporaryDirectory(prefix="media-video-stt-") as work_dir:
        in_path = Path(work_dir) / "input.mp4"
        out_path = Path(work_dir) / "audio.mp3"
        _ = in_path.write_bytes(video_bytes)
        ffmpeg_cmd = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(in_path),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-b:a",
            "64k",
            str(out_path),
        ]
        ffmpeg_result = subprocess.run(
            ffmpeg_cmd,
            check=False,
            capture_output=True,
            text=True,
        )
        if ffmpeg_result.returncode != 0:
            stderr = ffmpeg_result.stderr.strip()
            message = (
                "Не удалось извлечь аудио из видео для STT. "
                + f"return_code={ffmpeg_result.returncode}; stderr={stderr}"
            )
            raise RuntimeError(message)
        audio_bytes_out = out_path.read_bytes()
        if len(audio_bytes_out) == 0:
            raise ValueError("Извлечённая аудиодорожка пуста.")
        return audio_bytes_out, f"{stem}-audio.mp3"
