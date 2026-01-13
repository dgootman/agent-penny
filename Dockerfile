FROM python:3.12

WORKDIR /app
EXPOSE 8000

COPY requirements.txt .
RUN --mount=from=ghcr.io/astral-sh/uv,source=/uv,target=/bin/uv \
    uv pip install --system -r requirements.txt

COPY .chainlit .
COPY *.py .

CMD [ "chainlit", "run", "--host", "0.0.0.0", "app.py" ]
