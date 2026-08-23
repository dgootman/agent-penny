import os
from datetime import date
from pathlib import Path
from typing import NotRequired, TypedDict

import pytest
import yaml
from pydantic_ai import Agent

from agent_penny.available_models import AVAILABLE_MODELS, MODEL_ENV_VARS_BY_PROVIDER
from tests.utils import init_chainlit_context

VALIDATED_MODELS_PATH = Path("tests/validated_models.yaml")


class ValidatedModel(TypedDict):
    model: str
    last_tested: NotRequired[str]
    notes: NotRequired[str]


def load_validated_models() -> list[ValidatedModel]:
    return yaml.safe_load(VALIDATED_MODELS_PATH.read_text()) or []


def record_validated_model(model_name: str) -> None:
    validated_models = load_validated_models()
    validated_models.append(
        {"model": model_name, "last_tested": date.today().isoformat()}
    )
    validated_models.sort(key=lambda item: item["model"])
    VALIDATED_MODELS_PATH.write_text(yaml.safe_dump(validated_models, sort_keys=False))


VALIDATED_MODELS = {item["model"]: item for item in load_validated_models()}

MODELS_WITHOUT_CONTEXT_WINDOW = (
    "bedrock:us.anthropic.claude-fable-5",
    "bedrock:us.anthropic.claude-opus-5",
    "bedrock:us.anthropic.claude-sonnet-5",
    "bedrock:us.anthropic.claude-haiku-4-5-20251001-v1:0",
    "google:gemini-3.1-pro-preview",
    "google:gemini-2.5-pro",
    "google:gemini-2.5-flash",
)
MODELS_WITH_CONTEXT_WINDOW = tuple(
    model for model in AVAILABLE_MODELS if model not in MODELS_WITHOUT_CONTEXT_WINDOW
)


@pytest.mark.available_models
@pytest.mark.asyncio
@pytest.mark.parametrize("model_name", AVAILABLE_MODELS)
async def test_available_models(model_name: str):
    """Every unvalidated configured model must answer a live prompt."""

    from agent_penny.available_models import resolve_model
    from agent_penny.models.codex import CodexOpenAIResponsesModel

    if validated_model := VALIDATED_MODELS.get(model_name):
        details = validated_model.get("last_tested") or validated_model.get("notes")
        reason = "Model was already validated"
        if details:
            reason = f"{reason}: {details}"
        pytest.skip(reason)

    provider = model_name.split(":", 1)[0]
    env_var = MODEL_ENV_VARS_BY_PROVIDER[provider]
    if not os.environ.get(env_var):
        pytest.skip(f"{env_var} is not configured")

    model = resolve_model(model_name)
    if isinstance(model, CodexOpenAIResponsesModel):
        # Codex model requires chainlit context
        await init_chainlit_context()

    agent = Agent(model)
    async with agent.run_stream(
        "Say OK",
        model_settings={"max_tokens": 100},
    ) as result:
        output = await result.get_output()

    assert isinstance(output, str)
    assert "ok" in output.lower()
    record_validated_model(model_name)


@pytest.mark.parametrize("model_name", MODELS_WITH_CONTEXT_WINDOW)
def test_context_window_available(model_name: str):
    from agent_penny.available_models import get_context_window

    context_window = get_context_window(model_name)

    assert isinstance(context_window, int)
    assert context_window > 0


@pytest.mark.parametrize("model_name", MODELS_WITHOUT_CONTEXT_WINDOW)
def test_context_window_unavailable(model_name: str):
    from agent_penny.available_models import get_context_window

    assert get_context_window(model_name) is None
