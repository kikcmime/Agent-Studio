from __future__ import annotations

import json
import re
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


def _build_client(provider: str, timeout_seconds: int) -> tuple[str, str, OpenAI]:
    normalized_provider = _normalize_provider(provider)
    base_url, api_key, default_model = _resolve_provider_runtime(normalized_provider)

    if not api_key:
        raise LLMConfigurationError(
            f"api key is not configured for provider {normalized_provider}; set the matching environment variable first"
        )

    if normalized_provider in {"openai-compatible", "openai_compatible"} and not base_url:
        raise LLMConfigurationError(
            "base_url is not configured for openai-compatible provider; set OPENAI_COMPATIBLE_BASE_URL first"
        )

    client = OpenAI(api_key=api_key, base_url=base_url, timeout=timeout_seconds or settings.llm_timeout_seconds)
    return normalized_provider, default_model or "", client


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
    provider, default_model, client = _build_client(llm_config.provider, agent.timeout_seconds or settings.llm_timeout_seconds)
    model_name = llm_config.model or default_model

    if not model_name:
        raise LLMConfigurationError(
            f"model is not configured for provider {provider}; set it on the agent or via environment"
        )

    request_kwargs: dict[str, Any] = {
        "model": model_name,
        "messages": build_messages(agent, resolved_input),
    }

    if llm_config.temperature is not None:
        request_kwargs["temperature"] = llm_config.temperature

    if "max_tokens" in llm_config.extra:
        request_kwargs["max_tokens"] = llm_config.extra["max_tokens"]

    return provider, model_name, {"client": client, "kwargs": request_kwargs}


def _extract_flow_directives(message: str) -> dict[str, Any]:
    text = (message or "").strip()
    lowered = text.lower()

    flow_status_match = re.search(
        r"flow_status\s*[:=：]\s*(success|fail|failed|retry)",
        text,
        flags=re.IGNORECASE,
    )
    status_match = re.search(
        r"(?:^|\b)status\s*[:=：]\s*(success|fail|failed|retry)",
        text,
        flags=re.IGNORECASE,
    )
    result_match = re.search(r"结果\s*[:=：]\s*([^\n；;]+)", text)

    flow_status = flow_status_match.group(1).lower() if flow_status_match else None
    status = status_match.group(1).lower() if status_match else None
    result = result_match.group(1).strip() if result_match else None

    # Demo-safe normalization:
    # if the model explicitly says the result is a draw, a contradictory
    # FLOW_STATUS=success should not suppress the configured retry loop.
    if "平局" in text and flow_status in {None, "success"}:
        flow_status = "fail"
    if "平局" in text and status in {None, "success"}:
        status = "fail"
    if flow_status is None and result and "获胜" in result:
        flow_status = "success"
    if status is None and result and "获胜" in result:
        status = "success"

    return {
        "flow_status": flow_status,
        "status": status,
        "result": result,
        "is_draw": "平局" in lowered or "平局" in text,
    }


def invoke_text_classification(
    *,
    text: str,
    categories: list[str],
    prompt: str | None = None,
    model: str | None = None,
    provider: str | None = None,
    temperature: float = 0,
    timeout_seconds: int | None = None,
) -> dict[str, Any]:
    normalized_provider, default_model, client = _build_client(
        provider or settings.default_llm_provider,
        timeout_seconds or settings.llm_timeout_seconds,
    )
    model_name = model or default_model

    if not model_name:
        raise LLMConfigurationError(
            f"model is not configured for provider {normalized_provider}; set it in config or request first"
        )

    categories_text = "\n".join(f"- {item}" for item in categories)
    system_prompt = prompt or "你是一个路由分类器。只能返回一个类别标签，不要解释。"
    user_prompt = (
        "请只从下面这些类别中选择一个最合适的标签，并且只输出标签本身。\n"
        f"{categories_text}\n\n"
        f"用户输入：{text}"
    )

    response = client.chat.completions.create(
        model=model_name,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=temperature,
        max_tokens=24,
    )

    choice = response.choices[0] if response.choices else None
    raw_text = ""
    if choice is not None and choice.message and choice.message.content:
        raw_text = str(choice.message.content).strip()

    normalized_text = raw_text.strip().strip("`").strip()
    matched_category = next((item for item in categories if item == normalized_text), None)
    if matched_category is None:
        matched_category = next((item for item in categories if item in normalized_text), None)

    usage = None
    if response.usage is not None:
        usage = {
            "prompt_tokens": response.usage.prompt_tokens,
            "completion_tokens": response.usage.completion_tokens,
            "total_tokens": response.usage.total_tokens,
        }

    return {
        "provider": normalized_provider,
        "model": model_name,
        "raw_text": raw_text,
        "category": matched_category,
        "usage": usage,
    }


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

    directives = _extract_flow_directives(message)

    return {
        "agent_id": agent.id,
        "agent_name": agent.name,
        "provider": provider,
        "model": model_name,
        "message": message,
        "flow_status": directives["flow_status"],
        "status": directives["status"],
        "result": directives["result"],
        "is_draw": directives["is_draw"],
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
    directives = _extract_flow_directives(message)
    yield {
        "type": "completed",
        "output": {
            "agent_id": agent.id,
            "agent_name": agent.name,
            "provider": provider,
            "model": model_name,
            "message": message,
            "flow_status": directives["flow_status"],
            "status": directives["status"],
            "result": directives["result"],
            "is_draw": directives["is_draw"],
            "echo_input": resolved_input,
            "normalized_task": (resolved_input.get("user_message") or resolved_input.get("query") or "")[:120],
            "finish_reason": finish_reason,
            "usage": None,
        },
    }
