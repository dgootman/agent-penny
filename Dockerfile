FROM python:3.12

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/

WORKDIR /app

# Omit development dependencies
ENV UV_NO_DEV=1

# Install dependencies
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project

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
