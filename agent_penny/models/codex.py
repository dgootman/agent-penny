import json
from datetime import datetime, timezone
from textwrap import dedent
from typing import Any, Optional, override

import chainlit as cl
import httpx
from openai import AsyncOpenAI
from openai._compat import cached_property
from openai._types import Omit, omit
from openai.resources.responses import AsyncResponses
from pydantic_ai.models import ModelSettings
from pydantic_ai.models.openai import OpenAIModelName, OpenAIResponsesModel
from pydantic_ai.providers.openai import OpenAIProvider

from agent_penny import user_data

# Adapted from https://github.com/NousResearch/hermes-agent/blob/main/hermes_cli/auth.py

DEFAULT_CODEX_BASE_URL = "https://chatgpt.com/backend-api/codex"
CODEX_OAUTH_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
CODEX_OAUTH_TOKEN_URL = "https://auth.openai.com/oauth/token"


class AuthError(RuntimeError):
    """Structured auth error with UX mapping hints."""

    def __init__(
        self,
        message: str,
        *,
        provider: str = "",
        code: str | None = None,
        relogin_required: bool = False,
    ) -> None:
        super().__init__(message)
        self.provider = provider
        self.code = code
        self.relogin_required = relogin_required


async def _codex_device_code_login() -> dict[str, Any]:
    """Run the OpenAI device code login flow and return credentials dict."""
    import time as _time

    issuer = "https://auth.openai.com"
    client_id = CODEX_OAUTH_CLIENT_ID

    # Step 1: Request device code
    async with httpx.AsyncClient(timeout=httpx.Timeout(15.0)) as client:
        resp = await client.post(
            f"{issuer}/api/accounts/deviceauth/usercode",
            json={"client_id": client_id},
            headers={"Content-Type": "application/json"},
        )

    if resp.status_code != 200:
        raise AuthError(
            f"Device code request returned status {resp.status_code}.",
            provider="openai-codex",
            code="device_code_request_error",
        )

    device_data = resp.json()
    user_code = device_data.get("user_code", "")
    device_auth_id = device_data.get("device_auth_id", "")
    poll_interval = max(3, int(device_data.get("interval", "5")))

    if not user_code or not device_auth_id:
        raise AuthError(
            "Device code response missing required fields.",
            provider="openai-codex",
            code="device_code_incomplete",
        )

    # Step 2: Show user the code
    await cl.Message(
        dedent(
            f"""\
            To continue, follow these steps:
              1. Open this URL in your browser:
                 {issuer}/codex/device
              2. Enter this code:
                 `{user_code}`"""
        )
    ).send()

    # Step 3: Poll for authorization code
    max_wait = 15 * 60  # 15 minutes
    start = _time.monotonic()
    code_resp = None

    async with httpx.AsyncClient(timeout=httpx.Timeout(15.0)) as client:
        while _time.monotonic() - start < max_wait:
            _time.sleep(poll_interval)
            poll_resp = await client.post(
                f"{issuer}/api/accounts/deviceauth/token",
                json={"device_auth_id": device_auth_id, "user_code": user_code},
                headers={"Content-Type": "application/json"},
            )

            if poll_resp.status_code == 200:
                code_resp = poll_resp.json()
                break
            elif poll_resp.status_code in (403, 404):
                continue  # User hasn't completed login yet
            else:
                raise AuthError(
                    f"Device auth polling returned status {poll_resp.status_code}.",
                    provider="openai-codex",
                    code="device_code_poll_error",
                )

    if code_resp is None:
        raise AuthError(
            "Login timed out after 15 minutes.",
            provider="openai-codex",
            code="device_code_timeout",
        )

    # Step 4: Exchange authorization code for tokens
    authorization_code = code_resp.get("authorization_code", "")
    code_verifier = code_resp.get("code_verifier", "")
    redirect_uri = f"{issuer}/deviceauth/callback"

    if not authorization_code or not code_verifier:
        raise AuthError(
            "Device auth response missing authorization_code or code_verifier.",
            provider="openai-codex",
            code="device_code_incomplete_exchange",
        )

    async with httpx.AsyncClient(timeout=httpx.Timeout(15.0)) as client:
        token_resp = await client.post(
            CODEX_OAUTH_TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "code": authorization_code,
                "redirect_uri": redirect_uri,
                "client_id": client_id,
                "code_verifier": code_verifier,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

    if token_resp.status_code != 200:
        raise AuthError(
            f"Token exchange returned status {token_resp.status_code}.",
            provider="openai-codex",
            code="token_exchange_error",
        )

    tokens = token_resp.json()
    access_token = tokens.get("access_token", "")
    refresh_token = tokens.get("refresh_token", "")

    if not access_token:
        raise AuthError(
            "Token exchange did not return an access_token.",
            provider="openai-codex",
            code="token_exchange_no_access_token",
        )

    # Return tokens for the caller to persist (no longer writes to ~/.codex/)
    base_url = DEFAULT_CODEX_BASE_URL

    return {
        "tokens": {
            "access_token": access_token,
            "refresh_token": refresh_token,
        },
        "base_url": base_url,
        "last_refresh": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "auth_mode": "chatgpt",
        "source": "device-code",
    }


async def codex_api_key():
    codex_auth = user_data.load("codex_auth.json")
    if codex_auth:
        creds = json.loads(codex_auth)
    else:
        creds = await _codex_device_code_login()
        user_data.save("codex_auth.json", json.dumps(creds))
    return creds["tokens"]["access_token"]


class CodexAsyncResponses(AsyncResponses):
    @override
    async def create(
        self,
        *,
        instructions: Optional[str] | Omit = omit,
        store: Optional[bool] | Omit = omit,
        **kwargs,
    ):
        if not instructions or instructions == omit:
            instructions = "You are a helpful assistant."

        if store is None or store == omit:
            store = False

        return await super().create(instructions=instructions, store=store, **kwargs)


class CodexAsyncOpenAI(AsyncOpenAI):
    @override
    @cached_property
    def responses(self) -> AsyncResponses:
        return CodexAsyncResponses(self)


class CodexOpenAIResponsesModel(OpenAIResponsesModel):
    def __init__(
        self, model_name: OpenAIModelName, *, settings: ModelSettings | None = None
    ):
        client = CodexAsyncOpenAI(
            base_url="https://chatgpt.com/backend-api/codex",
            api_key=codex_api_key,
        )

        provider = OpenAIProvider(openai_client=client)

        super().__init__(
            model_name,
            provider=provider,
            settings=settings,
        )
