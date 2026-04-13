FROM python:3.12

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/

WORKDIR /app

# Omit development dependencies
ENV UV_NO_DEV=1

# Install binary dependencies
# ffmpeg is required by torchcodec, which is used by silero_vad to decode audio
RUN apt update && apt install -y ffmpeg && apt clean

# Install Python dependencies
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project

# Download Whisper model for speech-to-text
RUN echo 'from faster_whisper import WhisperModel; WhisperModel("small.en", device="cpu", compute_type="int8")' | uv run -

# Download Piper voice model for text-to-speech
RUN uv run python -m piper.download_voices --download-dir ~/.cache/piper/ en_GB-cori-high

# Copy the project into the image
COPY pyproject.toml uv.lock ./
COPY chainlit.md .
COPY .chainlit .chainlit
COPY *.py .
COPY ./agent_penny ./agent_penny
COPY ./public ./public

# Sync the project
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked

VOLUME [ "/usr/local/share/agent-penny" ]
ENV DATA_DIR=/usr/local/share/agent-penny

EXPOSE 8000

CMD [ "uv", "run", "chainlit", "run", "--host", "0.0.0.0", "app.py" ]
