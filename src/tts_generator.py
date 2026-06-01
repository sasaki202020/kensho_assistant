from __future__ import annotations

import math
import os
import shutil
import subprocess
import tempfile
import wave
from array import array
from pathlib import Path

from .config import AppConfig
from .script_generator import SlidePlan


def estimate_duration_seconds(text: str) -> float:
    chars = len(text.replace("\n", ""))
    return max(10.0, chars / 6.0)


def _write_silence_wav(path: Path, duration_sec: float, sample_rate: int = 22050) -> None:
    frames = int(duration_sec * sample_rate)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        silence = array("h", [0]) * min(frames, sample_rate)
        remaining = frames
        while remaining > 0:
            chunk = min(remaining, sample_rate)
            wav.writeframes(silence[:chunk].tobytes())
            remaining -= chunk


def _pad_wav_to_duration(path: Path, target_duration: float) -> None:
    with wave.open(str(path), "rb") as source:
        params = source.getparams()
        frames = source.readframes(source.getnframes())
        current_duration = source.getnframes() / float(source.getframerate())
        if current_duration >= target_duration:
            return
        sample_rate = source.getframerate()
        channels = source.getnchannels()
        sampwidth = source.getsampwidth()
    extra_frames = int((target_duration - current_duration) * sample_rate)
    silence = b"\x00" * extra_frames * channels * sampwidth
    with wave.open(str(path), "wb") as dest:
        dest.setparams(params)
        dest.writeframes(frames + silence)


def _normalize_wav(path: Path, sample_rate: int = 22050) -> None:
    temp_path = path.with_suffix(".normalized.wav")
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(path),
            "-ac",
            "1",
            "-ar",
            str(sample_rate),
            "-c:a",
            "pcm_s16le",
            str(temp_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    temp_path.replace(path)


def _synthesize_with_powershell(text: str, output_path: Path, rate: int) -> bool:
    script = f"""
Add-Type -AssemblyName System.Speech
$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
$synth.Rate = {rate}
$synth.SetOutputToWaveFile("{output_path}")
$synth.Speak(@'
{text}
'@)
$synth.Dispose()
"""
    with tempfile.NamedTemporaryFile("w", suffix=".ps1", delete=False, encoding="utf-8-sig") as temp:
        temp.write(script)
        temp_path = temp.name
    try:
        completed = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", temp_path],
            capture_output=True,
            text=True,
            check=False,
        )
        return completed.returncode == 0 and output_path.exists()
    finally:
        try:
            os.remove(temp_path)
        except OSError:
            pass


def _synthesize_with_openai(text: str, output_path: Path, config: AppConfig) -> bool:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return False
    try:
        from openai import OpenAI  # type: ignore
    except Exception:
        return False
    try:
        client = OpenAI(api_key=api_key)
        response = client.audio.speech.create(  # type: ignore[attr-defined]
            model=os.getenv("OPENAI_TTS_MODEL", config.openai_tts_model),
            voice=os.getenv("OPENAI_TTS_VOICE", config.openai_voice),
            input=text,
            response_format="wav",
        )
        response.stream_to_file(str(output_path))
        return output_path.exists()
    except Exception:
        return False


def synthesize_slide_audio(
    slide: SlidePlan,
    output_dir: Path,
    config: AppConfig,
    index: int,
) -> tuple[Path, float]:
    audio_dir = output_dir / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    out_path = audio_dir / f"slide_{index:02d}.wav"
    text = slide.narration.strip()
    duration_guess = max(float(slide.duration_sec), estimate_duration_seconds(text))

    if _synthesize_with_openai(text, out_path, config):
        duration_guess = get_audio_duration(out_path)
        target = max(duration_guess, float(slide.duration_sec))
        _pad_wav_to_duration(out_path, target)
        _normalize_wav(out_path)
        return out_path, target

    if _synthesize_with_powershell(text, out_path, config.tts_rate):
        duration_guess = get_audio_duration(out_path)
        _pad_wav_to_duration(out_path, max(duration_guess, float(slide.duration_sec)))
        _normalize_wav(out_path)
        return out_path, max(duration_guess, float(slide.duration_sec))

    _write_silence_wav(out_path, duration_guess)
    _normalize_wav(out_path)
    return out_path, duration_guess


def concat_audio_files(audio_files: list[Path], output_path: Path) -> Path:
    if not audio_files:
        raise ValueError("audio_files is empty")
    if len(audio_files) == 1:
        shutil.copy2(audio_files[0], output_path)
        return output_path
    inputs: list[str] = []
    for path in audio_files:
        inputs.extend(["-i", str(path)])
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            *inputs,
            "-filter_complex",
            f"concat=n={len(audio_files)}:v=0:a=1",
            "-c:a",
            "pcm_s16le",
            str(output_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return output_path


def get_audio_duration(path: Path) -> float:
    with wave.open(str(path), "rb") as wav:
        frames = wav.getnframes()
        rate = wav.getframerate()
    return frames / float(rate)
