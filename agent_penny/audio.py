import asyncio
import os
import sys
import wave
from functools import cache
from io import BytesIO

import logfire
import torch
import torchaudio  # type: ignore[import-untyped]
from faster_whisper import WhisperModel  # type: ignore[import-untyped]
from kokoro import KPipeline  # type: ignore[import-untyped]
from loguru import logger
from silero_vad import VADIterator, load_silero_vad  # type: ignore[import-untyped]
from torchaudio.transforms import Resample  # type: ignore[import-untyped]
from torchcodec.encoders import AudioEncoder  # type: ignore[import-untyped]


@cache
@logfire.instrument()
def whisper_model() -> WhisperModel:
    return WhisperModel(os.environ["WHISPER_MODEL"], device="cpu", compute_type="int8")


@cache
@logfire.instrument()
def kokoro_model() -> KPipeline:
    pipeline = KPipeline(lang_code="a", repo_id="hexgrad/Kokoro-82M")
    pipeline.load_single_voice("af_heart")
    return pipeline


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

    def pcm_to_wave(self, pcm: bytes) -> bytes:
        wave_buffer = BytesIO()
        with wave.open(wave_buffer, "wb") as f:
            f.setparams((1, 2, self.sample_rate, 0, "NONE", "NONE"))
            f.writeframes(pcm)

        return wave_buffer.getvalue()

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
                    BytesIO(wave_data), language="en", word_timestamps=False
                )
            )

        with logfire.span("collect_segments"):
            segments = await asyncio.to_thread(lambda: list(segments))

        text = "\n".join(s.text for s in segments)

        logger.trace("Transcription", info=info, segments=segments, text=text)

        return text if text else None


text_to_speech_resample = Resample(24000, 16000)


def text_to_speech(text: str):
    pipeline = kokoro_model()
    generator = pipeline(text, voice="af_heart", speed=1.25)

    for gs, ps, audio in generator:
        # Convert the audio tensor from 24000HZ to 16000HZ
        # Then load the data as bytes
        buffer = BytesIO()
        audio = text_to_speech_resample(audio)
        AudioEncoder(audio, sample_rate=16000).to_file_like(buffer, "wav")

        buffer.seek(0)
        with wave.open(buffer, "rb") as f:
            yield f.readframes(sys.maxsize)
