"""SAP AI SDK transport and local-proxy configuration, without orchestration."""
import math
import os
from dataclasses import dataclass, field
from urllib.parse import urlsplit

import httpx
from gen_ai_hub.proxy.core.base import BaseDeployment, BaseProxyClient
from gen_ai_hub.proxy.native.openai import OpenAI as SAPOpenAI
from pydantic import SecretStr

from .errors import DemoError


@dataclass(frozen=True)
class Settings:
    base_url: str
    model: str
    api_key: SecretStr = field(repr=False)
    timeout_seconds: float = 30
    max_output_tokens: int = 512

    @classmethod
    def from_env(cls):
        key = os.environ.get("AI_PROXY_API_KEY", "")
        model = os.environ.get("AI_MODEL", "")
        if not key or key.startswith("REPLACE_") or not model or model.startswith("REPLACE_"):
            raise DemoError("missing_configuration", "Set AI_PROXY_API_KEY and AI_MODEL in your shell.")
        url = os.environ.get("AI_PROXY_URL", "http://localhost:6655/openai/v1").rstrip("/")
        try:
            parsed = urlsplit(url)
            if (parsed.scheme not in {"http", "https"}
                    or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}
                    or parsed.username is not None or parsed.password is not None
                    or parsed.query or parsed.fragment or not parsed.path
                    or parsed.port == 0):
                raise ValueError("Not a loopback proxy URL")
            timeout = float(os.environ.get("AI_TIMEOUT_SECONDS", "30"))
            tokens = int(os.environ.get("AI_MAX_OUTPUT_TOKENS", "512"))
            if not math.isfinite(timeout) or timeout <= 0 or tokens <= 0:
                raise ValueError("Invalid request limits")
            if any(not char.isprintable() for char in key + model):
                raise ValueError("Invalid credentials or model")
        except ValueError as exc:
            raise DemoError("invalid_configuration", "Check the loopback proxy URL and positive finite request limits.") from exc
        return cls(url, model, SecretStr(key), timeout, tokens)


class LocalDeployment(BaseDeployment):
    """Only the configured model and URL; no invented AI Core deployment IDs."""

    model_name: str
    url: str

    @property
    def prediction_url(self):
        return self.url.rstrip("/") + "/chat/completions"

    @classmethod
    def get_model_identification_kwargs(cls):
        return ("model_name",)

    def additional_request_body_kwargs(self):
        return {}


class LocalProxyClient(BaseProxyClient):
    """Adapt the SDK's proxy interface to HAI, without discovery or OAuth calls."""

    base_url: str
    model_name: str
    api_key: SecretStr

    @property
    def request_header(self):
        return {"Authorization": "Bearer " + self.api_key.get_secret_value()}

    @property
    def deployment_class(self):
        return LocalDeployment

    @property
    def deployments(self):
        return [LocalDeployment(model_name=self.model_name, url=self.base_url)]

    def select_deployment(self, **criteria):
        if criteria != {"model_name": self.model_name}:
            raise ValueError("Only the configured model is permitted")
        return self.deployments[0]


class LocalSAPOpenAI(SAPOpenAI):
    @property
    def default_query(self):
        # SAP's wrapper adds an Azure api-version query by default. HAI exposes
        # the OpenAI API, not Azure, so do not send that unrelated parameter.
        return {}


def complete_json(system_prompt: str, user_message: str, *, settings: Settings | None = None,
                  http_client: httpx.Client | None = None) -> str:
    settings = settings or Settings.from_env()
    if settings.model.startswith("cohere--"):
        # SAP's Cohere compatibility path removes max_completion_tokens.
        raise DemoError("unsupported_model", "Choose an OpenAI-compatible chat model that preserves the output-token cap; SAP Cohere aliases are not supported.")
    proxy = LocalProxyClient(base_url=settings.base_url, model_name=settings.model, api_key=settings.api_key)
    try:
        with LocalSAPOpenAI(proxy_client=proxy, timeout=settings.timeout_seconds,
                            max_retries=0, http_client=http_client) as client:
            response = client.chat.completions.create(
                model=settings.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
                response_format={"type": "json_object"},
                max_completion_tokens=settings.max_output_tokens,
                timeout=settings.timeout_seconds,
            )
            if len(response.choices) != 1:
                raise DemoError("invalid_model_response", "AI request did not return exactly one response.")
            choice = response.choices[0]
            if (choice.finish_reason != "stop" or choice.message.tool_calls
                    or choice.message.function_call or choice.message.refusal or not choice.message.content):
                raise DemoError("incomplete_model_response", "AI response was incomplete, refused, or requested an unauthorized action.")
            return choice.message.content
    except DemoError:
        raise
    except Exception as exc:
        # SDK exceptions can contain credentials, URLs, prompts, and response bodies.
        # Expose safe categories only. Never retry or fall back to a fake response.
        from openai import APIConnectionError, APIStatusError, APITimeoutError

        if isinstance(exc, APITimeoutError):
            message = "AI proxy request timed out; no retry was attempted."
        elif isinstance(exc, APIConnectionError):
            message = "Cannot connect to the local AI proxy; no retry was attempted."
        elif isinstance(exc, APIStatusError) and exc.status_code in {401, 403}:
            message = "AI proxy rejected authorization; check your local proxy key."
        else:
            message = "AI proxy request failed; check proxy availability and model/API compatibility."
        raise DemoError("ai_request_failed", message) from exc
