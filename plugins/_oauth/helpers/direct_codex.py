from __future__ import annotations

import hashlib
from typing import Any

from plugins._oauth.helpers import codex
from plugins._oauth.helpers.config import codex_config


def configure_direct_codex_model(model: Any, agent: Any = None) -> bool:
    """Configure a Codex OAuth model for direct upstream inference."""
    config = getattr(model, "a0_model_conf", None)
    provider = str(getattr(config, "provider", "") or "").strip().lower()
    if not model or provider != "codex_oauth":
        return False

    auth = codex.load_auth()
    settings = codex_config()
    kwargs = model.kwargs
    kwargs["api_base"] = settings["upstream_base_url"]
    kwargs["api_key"] = auth.access_token
    kwargs["responses_state"] = "local"

    extra_body = dict(kwargs.get("extra_body") or {})
    metadata = dict(extra_body.get("client_metadata") or {})
    session_id = str(metadata.get("session_id") or "") or _agent_session_id(agent)
    if not session_id:
        session_id = codex.build_client_metadata()["session_id"]
    metadata.setdefault("session_id", session_id)
    metadata.setdefault("thread_id", session_id)
    metadata[codex.CLIENT_METADATA_INSTALLATION_ID] = codex.resolve_installation_id()
    metadata[codex.CLIENT_METADATA_WINDOW_ID] = "agent-zero"
    extra_body["client_metadata"] = metadata
    kwargs["extra_body"] = extra_body

    cache_key = metadata["session_id"]
    if len(cache_key) > 64:
        cache_key = hashlib.sha256(cache_key.encode("utf-8")).hexdigest()
    kwargs.setdefault("prompt_cache_key", cache_key)

    reasoning = kwargs.get("reasoning")
    if not isinstance(reasoning, dict):
        reasoning = {}
    reasoning = dict(reasoning)
    effort = settings.get("reasoning_effort", "high")
    summary = settings.get("reasoning_summary", "auto")
    if effort != "default":
        reasoning.setdefault("effort", effort)
    if summary != "off":
        reasoning.setdefault("summary", summary)
    if reasoning:
        kwargs["reasoning"] = reasoning

    text = kwargs.get("text")
    text = dict(text) if isinstance(text, dict) else {}
    verbosity = settings.get("text_verbosity", "medium")
    if verbosity != "default":
        text.setdefault("verbosity", verbosity)
    if text:
        kwargs["text"] = text

    include = list(kwargs.get("include") or [])
    if "reasoning.encrypted_content" not in include:
        include.append("reasoning.encrypted_content")
    kwargs["include"] = include
    kwargs.pop("max_output_tokens", None)

    headers = dict(kwargs.get("extra_headers") or {})
    headers.update(
        {
            "chatgpt-account-id": auth.account_id,
            "OpenAI-Beta": "responses=experimental",
            "originator": codex.CODEX_ORIGINATOR,
            codex.CLIENT_METADATA_INSTALLATION_ID: metadata[
                codex.CLIENT_METADATA_INSTALLATION_ID
            ],
            codex.CLIENT_METADATA_WINDOW_ID: metadata[
                codex.CLIENT_METADATA_WINDOW_ID
            ],
            "session-id": metadata["session_id"],
            "thread-id": metadata["thread_id"],
        }
    )
    version = codex.resolve_codex_version()
    if version:
        headers["version"] = version
    kwargs["extra_headers"] = headers
    return True


def _agent_session_id(agent: Any) -> str:
    context = getattr(agent, "context", None)
    context_id = str(getattr(context, "id", "") or "")
    number = getattr(agent, "number", None)
    if not context_id or number is None:
        return ""
    return f"agent-zero-{context_id}-{number}"
