import os
import sys
import wave
from pathlib import Path

import pytest
from loguru import logger


async def transcribe(file: str) -> str:
    from agent_penny.audio import StreamingTranscriber

    os.environ["WHISPER_MODEL"] = "small.en"
    with wave.open(file, "rb") as f:
        audio = f.readframes(sys.maxsize)

    transcriber = StreamingTranscriber(16000)
    text = await transcriber.add_chunk(audio)
    if text is None:
        logger.debug("Chunk wasn't transcribed immediately")
        text = await transcriber.transcribe()

    logger.debug("Transcription", text=text)

    assert text is not None

    return text


@pytest.mark.asyncio
async def test_speech_to_text():
    text = await transcribe("tests/test_audio.wav")

    assert "this is a test" in text.lower()
    assert "text" in text.lower()
    assert "speech" in text.lower()
    assert "system" in text.lower()


@pytest.mark.asyncio
async def test_end_to_end(tmp_path: Path):
    from agent_penny.audio import text_to_speech

    wave_file = str(tmp_path / "output.wav")

    speech = text_to_speech("Hello! My name is Agent Penny")
    chunk = next(speech)
    with wave.open(wave_file, "wb") as f:
        f.setparams((1, 2, 16000, 0, "NONE", "NONE"))
        f.writeframes(chunk)
    assert next(speech, None) is None

    text = await transcribe(wave_file)

    assert text is not None
    assert "hello" in text.lower()
    assert "name is " in text.lower()
    assert "agent penny" in text.lower()
