import asyncio
import os
import sys
import wave
from functools import cache
from io import BytesIO
from pathlib import Path

import logfire
import numpy
import torch
import torchaudio  # type: ignore[import-untyped]
from faster_whisper import WhisperModel  # type: ignore[import-untyped]
from loguru import logger
from piper import PiperVoice
from piper.download_voices import download_voice
from silero_vad import VADIterator, load_silero_vad  # type: ignore[import-untyped]
from torchaudio.transforms import Resample  # type: ignore[import-untyped]
from torchcodec.encoders import AudioEncoder  # type: ignore[import-untyped]


@cache
@logfire.instrument()
def whisper_model() -> WhisperModel:
    return WhisperModel(os.environ["WHISPER_MODEL"], device="cpu", compute_type="int8")


@cache
@logfire.instrument()
def piper_model() -> PiperVoice:
    voice = os.environ.get("PIPER_MODEL", "en_GB-cori-high")
    voice_dir = Path("~/.cache/piper").expanduser()

    if not voice_dir.exists():
        voice_dir.mkdir(parents=True)

    if not (voice_dir / f"{voice}.onnx").exists():
        download_voice(voice, voice_dir)

    return PiperVoice.load(voice_dir / f"{voice}.onnx", download_dir=voice_dir)


def startup():
    # Prime the audio model caches in the background
    asyncio.create_task(asyncio.to_thread(whisper_model))
    asyncio.create_task(asyncio.to_thread(piper_model))


class StreamingTranscriber:
    def __init__(self, sample_rate: int) -> None:
        vad = load_silero_vad()
        self.vad_iterator = VADIterator(vad, sampling_rate=16000)
        self.buffer = BytesIO()
        self.sample_rate = sample_rate
        self.resample = (
            Resample(sample_rate, 16000)
            if sample_rate != 16000
            else lambda audio: audio
        )

    def pcm_to_wave(self, pcm: bytes) -> BytesIO:
        wave_buffer = BytesIO()
        with wave.open(wave_buffer, "wb") as f:
            f.setparams((1, 2, self.sample_rate, 0, "NONE", "NONE"))
            f.writeframes(pcm)

        wave_buffer.seek(0)

        return wave_buffer

    async def add_chunk(self, chunk: bytes) -> str | None:
        audio, _ = torchaudio.load(self.pcm_to_wave(chunk))
        audio = self.resample(audio)

        triggered = self.vad_iterator.triggered
        for vad_chunk in torch.split(audio[0], 512):
            # TODO: if the last VAD chunk is too short, carry it over to the next chunk to analyze
            if len(vad_chunk) == 512:
                vad_result = self.vad_iterator(vad_chunk)
                if self.vad_iterator.triggered:
                    triggered = True
                if vad_result:
                    logger.trace("VAD", vad_result=vad_result)

        if triggered:
            self.buffer.write(chunk)
            return None
        elif self.buffer.tell() > 0:
            return await self.transcribe()
        else:
            return None

    @logfire.instrument()
    async def transcribe(self) -> str | None:
        if self.buffer.tell() == 0:
            return None

        pcm = self.buffer.getvalue()
        self.buffer = BytesIO()

        wave_data = self.pcm_to_wave(pcm)

        with logfire.span("whisper_transcribe"):
            segments, info = await asyncio.to_thread(
                lambda: whisper_model().transcribe(
                    wave_data, language="en", word_timestamps=False
                )
            )

        with logfire.span("collect_segments"):
            segments = await asyncio.to_thread(lambda: list(segments))

        text = "\n".join(s.text for s in segments)

        logger.trace("Transcription", info=info, segments=segments, text=text)

        return text if text else None


@cache
def get_resampler(orig_freq: int, new_freq: int):
    return Resample(orig_freq, new_freq)


@logfire.instrument()
def text_to_speech(text: str, sample_rate=16000):
    voice = piper_model()

    resampler = get_resampler(voice.config.sample_rate, sample_rate)

    sound = numpy.concatenate(
        [chunk.audio_float_array for chunk in voice.synthesize(text)]
    )

    # Convert the audio tensor from 24000HZ to 16000HZ
    # Then load the data as bytes
    buffer = BytesIO()
    audio = resampler(torch.from_numpy(sound))
    AudioEncoder(audio, sample_rate=sample_rate).to_file_like(buffer, "wav")

    buffer.seek(0)
    with wave.open(buffer, "rb") as f:
        return f.readframes(sys.maxsize)
