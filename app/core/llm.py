from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

from openai import OpenAI

from app.core.config import settings
from app.schemas.contracts import AgentDetail


class LLMConfigurationError(RuntimeError):
    pass


def _normalize_provider(provider: str | None) -> str:
    if not provider:
        return settings.default_llm_provider
    return provider.strip().lower()


def _resolve_provider_runtime(provider: str) -> tuple[str | None, str | None, str | None]:
    if provider in {"openai-compatible", "openai_compatible"}:
        return (
            settings.openai_compatible_base_url,
            settings.openai_compatible_api_key,
            settings.openai_compatible_default_model,
        )

    if provider == "openai":
        return (
            settings.openai_base_url,
            settings.openai_api_key,
            settings.openai_default_model,
        )

    raise LLMConfigurationError(f"unsupported provider: {provider}")


def build_messages(agent: AgentDetail, resolved_input: dict[str, Any]) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []
    system_parts = [part for part in [agent.role, agent.system_prompt, agent.instructions] if part]
    if system_parts:
        messages.append({"role": "system", "content": "\n\n".join(system_parts)})

    for item in resolved_input.get("messages") or []:
        if not isinstance(item, dict):
            continue
        role = item.get("role")
        content = item.get("content")
        if role in {"user", "assistant"} and content:
            messages.append({"role": role, "content": str(content)})

    user_message = resolved_input.get("user_message") or resolved_input.get("query")
    if not user_message:
        user_message = json.dumps(resolved_input, ensure_ascii=False, indent=2)
    messages.append({"role": "user", "content": str(user_message)})
    return messages


def _build_request(agent: AgentDetail, resolved_input: dict[str, Any]) -> tuple[str, str, dict[str, Any]]:
    llm_config = agent.llm_config
    provider = _normalize_provider(llm_config.provider)
    base_url, api_key, default_model = _resolve_provider_runtime(provider)
    model_name = llm_config.model or default_model

    if not model_name:
        raise LLMConfigurationError(
            f"model is not configured for provider {provider}; set it on the agent or via environment"
        )

    if not api_key:
        raise LLMConfigurationError(
            f"api key is not configured for provider {provider}; set the matching environment variable first"
        )

    if provider in {"openai-compatible", "openai_compatible"} and not base_url:
        raise LLMConfigurationError(
            "base_url is not configured for openai-compatible provider; set OPENAI_COMPATIBLE_BASE_URL first"
        )

    client = OpenAI(api_key=api_key, base_url=base_url, timeout=agent.timeout_seconds or settings.llm_timeout_seconds)
    request_kwargs: dict[str, Any] = {
        "model": model_name,
        "messages": build_messages(agent, resolved_input),
    }

    if llm_config.temperature is not None:
        request_kwargs["temperature"] = llm_config.temperature

    if "max_tokens" in llm_config.extra:
        request_kwargs["max_tokens"] = llm_config.extra["max_tokens"]

    return provider, model_name, {"client": client, "kwargs": request_kwargs}


def invoke_agent_llm(agent: AgentDetail, resolved_input: dict[str, Any]) -> dict[str, Any]:
    provider, model_name, request = _build_request(agent, resolved_input)
    client = request["client"]
    request_kwargs = request["kwargs"]
    response = client.chat.completions.create(**request_kwargs)
    choice = response.choices[0] if response.choices else None
    message = ""
    finish_reason = None

    if choice is not None:
        finish_reason = choice.finish_reason
        content = choice.message.content
        if isinstance(content, str):
            message = content
        elif isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if hasattr(item, "text") and item.text:
                    parts.append(item.text)
                elif isinstance(item, dict) and item.get("text"):
                    parts.append(str(item["text"]))
            message = "\n".join(parts)

    usage = None
    if response.usage is not None:
        usage = {
            "prompt_tokens": response.usage.prompt_tokens,
            "completion_tokens": response.usage.completion_tokens,
            "total_tokens": response.usage.total_tokens,
        }

    return {
        "agent_id": agent.id,
        "agent_name": agent.name,
        "provider": provider,
        "model": model_name,
        "message": message,
        "echo_input": resolved_input,
        "normalized_task": (resolved_input.get("user_message") or resolved_input.get("query") or "")[:120],
        "finish_reason": finish_reason,
        "usage": usage,
    }


def stream_agent_llm(agent: AgentDetail, resolved_input: dict[str, Any]) -> Iterator[dict[str, Any]]:
    provider, model_name, request = _build_request(agent, resolved_input)
    client = request["client"]
    request_kwargs = {**request["kwargs"], "stream": True}
    message_parts: list[str] = []
    finish_reason = None

    for chunk in client.chat.completions.create(**request_kwargs):
        choice = chunk.choices[0] if chunk.choices else None
        if choice is None:
            continue
        if choice.finish_reason:
            finish_reason = choice.finish_reason
        delta = getattr(choice.delta, "content", None)
        if not delta:
            continue
        message_parts.append(delta)
        yield {"type": "delta", "delta": delta}

    message = "".join(message_parts)
    yield {
        "type": "completed",
        "output": {
            "agent_id": agent.id,
            "agent_name": agent.name,
            "provider": provider,
            "model": model_name,
            "message": message,
            "echo_input": resolved_input,
            "normalized_task": (resolved_input.get("user_message") or resolved_input.get("query") or "")[:120],
            "finish_reason": finish_reason,
            "usage": None,
        },
    }
