"""
Unified AI client — Anthropic Claude or local Ollama.

Ollama path: try OLLAMA_MODEL first (e.g. kinexis-marketing-ft 8B). On empty
output, hard failure, or invalid JSON (when json_mode), retry with
OLLAMA_FALLBACK_MODEL (e.g. kinexis-marketing 14B) with playbook + fallback boost.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Optional

import httpx

import app.config as cfg
from app.marketing_knowledge import FALLBACK_USER_SUFFIX, ensure_marketing_knowledge

logger = logging.getLogger(__name__)

_THINK_BLOCK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


def ai_configured() -> bool:
    if cfg.AI_PROVIDER == "ollama":
        return bool(cfg.OLLAMA_BASE_URL and cfg.OLLAMA_MODEL)
    return bool(cfg.ANTHROPIC_API_KEY)


def ollama_status() -> dict:
    """Probe Ollama daemon + whether configured models are installed."""
    base = (cfg.OLLAMA_BASE_URL or "").rstrip("/")
    primary = (cfg.OLLAMA_MODEL or "").strip()
    fallback = (getattr(cfg, "OLLAMA_FALLBACK_MODEL", "") or "").strip()
    result: dict = {
        "reachable": False,
        "models": [],
        "primary": primary,
        "primary_present": False,
        "fallback": fallback,
        "fallback_present": False,
        "message": "",
    }
    if not base:
        result["message"] = "Ollama base URL is empty."
        return result
    try:
        with httpx.Client(timeout=5.0) as client:
            res = client.get(f"{base}/api/tags")
            res.raise_for_status()
            data = res.json()
        names = [
            str(m.get("name") or m.get("model") or "")
            for m in (data.get("models") or [])
            if isinstance(m, dict)
        ]
        result["reachable"] = True
        result["models"] = names

        def _present(wanted: str) -> bool:
            if not wanted:
                return False
            w = wanted.lower()
            for n in names:
                nl = n.lower()
                if nl == w or nl.startswith(w + ":"):
                    return True
            return False

        result["primary_present"] = _present(primary)
        result["fallback_present"] = _present(fallback) if fallback else True
        if not result["primary_present"]:
            result["message"] = (
                f"Ollama is running but model '{primary}' is not installed. "
                f"Available: {', '.join(names[:8]) or '(none)'}."
            )
        else:
            result["message"] = "Ollama ready."
        return result
    except Exception as e:
        result["message"] = (
            f"Cannot reach Ollama at {base}. Start Ollama, then retry. ({e})"
        )
        return result


def diagnose_ai() -> dict:
    """Human-readable readiness check used by Settings → Test AI."""
    if not ai_configured():
        return {
            "ok": False,
            "message": (
                "AI is not configured. Set ANTHROPIC_API_KEY in backend .env "
                "or switch to Ollama in Settings."
            ),
        }
    if cfg.AI_PROVIDER == "ollama":
        status = ollama_status()
        if not status["reachable"]:
            return {"ok": False, "message": status["message"], "detail": status}
        if not status["primary_present"]:
            return {"ok": False, "message": status["message"], "detail": status}
    return {"ok": True, "message": "Provider configured."}


def complete(
    *,
    system: str,
    user: str,
    max_tokens: int = 4096,
    json_mode: bool = False,
    temperature: Optional[float] = None,
    purpose: str = "complete",
    client_id: Optional[int] = None,
) -> Optional[str]:
    """Return model text, or None if not configured / failed.
    
    client_id, when provided, is used for AI usage/cost logging attribution.
    """
    if not ai_configured():
        logger.warning("AI not configured — skipping generation")
        return None

    if cfg.AI_PROVIDER == "ollama":
        status = ollama_status()
        if not status["reachable"]:
            logger.error(status["message"])
            return None
        if not status["primary_present"] and not status["fallback_present"]:
            logger.error(status["message"])
            return None
        return _ollama_complete_with_fallback(
            system=system,
            user=user,
            max_tokens=max_tokens,
            json_mode=json_mode,
            temperature=temperature,
            purpose=purpose or "complete",
            client_id=client_id,
        )
    return _anthropic_complete(
        system=system,
        user=user,
        max_tokens=max_tokens,
        purpose=purpose or "complete",
        client_id=client_id,
    )


def _anthropic_complete(
    *, system: str, user: str, max_tokens: int, purpose: str = "complete", client_id: Optional[int] = None
) -> Optional[str]:
    try:
        import anthropic

        client = anthropic.Anthropic(api_key=cfg.ANTHROPIC_API_KEY)
        model = getattr(cfg, "ANTHROPIC_MODEL", "") or "claude-sonnet-4-20250514"
        message = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        try:
            from app.ai_usage import log_usage

            usage = getattr(message, "usage", None)
            log_usage(
                provider="anthropic",
                model=model,
                purpose=purpose or "complete",
                input_tokens=int(getattr(usage, "input_tokens", 0) or 0),
                output_tokens=int(getattr(usage, "output_tokens", 0) or 0),
                client_id=client_id,
            )
        except Exception as e:
            logger.debug("Failed to log Anthropic usage: %s", e)
        return _extract_text_content(message.content) if message.content else ""
    except Exception as e:
        logger.error(f"Anthropic completion failed: {e}")
        return None


def _extract_text_content(content) -> str:
    """Handle both string and list[ContentBlock] response formats from Anthropic."""
    if isinstance(content, str):
        return content
    if isinstance(content, list) and len(content) > 0:
        return getattr(content[0], "text", "") or str(content[0])
    return str(content) if content else ""


def _strip_think_blocks(text: str) -> str:
    """Remove leaked Qwen/DeepSeek think tags from model output."""
    cleaned = _THINK_BLOCK_RE.sub("", text or "").strip()
    # Unclosed think block (truncated mid-thought)
    if "<think>" in cleaned.lower():
        cleaned = re.split(r"<think>", cleaned, flags=re.IGNORECASE)[0].strip()
    return cleaned


def _json_usable(text: str) -> bool:
    """True if text parses as JSON object or array (after fence/think cleanup)."""
    if not (text or "").strip():
        return False
    try:
        parse_json_payload(text, expect=list)
        return True
    except (json.JSONDecodeError, TypeError, ValueError):
        pass
    try:
        parse_json_payload(text, expect=dict)
        return True
    except (json.JSONDecodeError, TypeError, ValueError):
        return False


def _fallback_model() -> str:
    primary = (cfg.OLLAMA_MODEL or "").strip()
    fallback = (getattr(cfg, "OLLAMA_FALLBACK_MODEL", "") or "").strip()
    if not fallback or fallback == primary:
        return ""
    return fallback


def _ollama_complete_with_fallback(
    *,
    system: str,
    user: str,
    max_tokens: int,
    json_mode: bool,
    temperature: Optional[float] = None,
    purpose: str = "complete",
    client_id: Optional[int] = None,
) -> Optional[str]:
    primary = cfg.OLLAMA_MODEL
    content = _ollama_complete(
        model=primary,
        system=system,
        user=user,
        max_tokens=max_tokens,
        json_mode=json_mode,
        temperature=temperature,
        purpose=purpose,
        client_id=client_id,
    )

    need_fallback = content is None or not content.strip()
    if json_mode and content and not _json_usable(content):
        logger.warning(
            "Primary model %s returned non-JSON / unusable payload — escalating",
            primary,
        )
        need_fallback = True

    if not need_fallback:
        return content

    fallback = _fallback_model()
    if not fallback:
        return content  # may be None

    logger.warning(
        "Falling back from %s → %s (empty/invalid primary output)",
        primary,
        fallback,
    )
    # Give 14B the full playbook + explicit escalation instructions.
    fb_system = ensure_marketing_knowledge(system)
    fb_user = (user or "").rstrip() + "\n" + FALLBACK_USER_SUFFIX
    return _ollama_complete(
        model=fallback,
        system=fb_system,
        user=fb_user,
        max_tokens=max_tokens,
        json_mode=json_mode,
        temperature=temperature if temperature is not None else min(cfg.OLLAMA_TEMPERATURE, 0.3),
        purpose=purpose,
        client_id=client_id,
    )


def _ollama_complete(
    *,
    model: str,
    system: str,
    user: str,
    max_tokens: int,
    json_mode: bool,
    temperature: Optional[float] = None,
    purpose: str = "complete",
    client_id: Optional[int] = None,
) -> Optional[str]:
    prompt = user
    if json_mode:
        prompt = (
            user
            + "\n\nIMPORTANT: Respond with valid JSON only. "
            "No markdown fences, no commentary outside the JSON."
        )
    temp = cfg.OLLAMA_TEMPERATURE if temperature is None else temperature
    try:
        # think=false is required for Qwen3 / other thinking models — otherwise
        # Ollama may return empty message.content while burning tokens on thinking.
        options = {
            "num_predict": max_tokens,
            "temperature": temp,
            "num_ctx": cfg.OLLAMA_NUM_CTX,
            "repeat_penalty": 1.25 if not json_mode else 1.1,
        }
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "stream": False,
            "think": False,
            "options": options,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        timeout = float(getattr(cfg, "OLLAMA_TIMEOUT", 300) or 300)
        with httpx.Client(timeout=timeout) as client:
            res = client.post(
                f"{cfg.OLLAMA_BASE_URL.rstrip('/')}/api/chat", json=payload
            )
            res.raise_for_status()
            data = res.json()
            message = data.get("message") or {}
            content = _strip_think_blocks(message.get("content") or "")
            if not content:
                logger.error(
                    "Ollama returned empty content (model=%s, done_reason=%s). "
                    "If using a thinking model, ensure think=false is supported.",
                    model,
                    data.get("done_reason"),
                )
                return None
            try:
                from app.ai_usage import log_usage

                eval_count = int(data.get("eval_count") or 0)
                prompt_count = int(data.get("prompt_eval_count") or 0)
                log_usage(
                    provider="ollama",
                    model=model,
                    purpose=purpose or "complete",
                    input_tokens=prompt_count,
                    output_tokens=eval_count,
                    client_id=client_id,
                )
            except Exception as e:
                logger.debug("Failed to log Ollama usage: %s", e)
            return content
    except Exception as e:
        logger.error(f"Ollama completion failed (model={model}): {e}")
        return None


def _coerce_list_payload(parsed):
    """Normalize common LLM wrappers into a list when the caller expects one."""
    if isinstance(parsed, list):
        return parsed
    if not isinstance(parsed, dict):
        return parsed
    for key in ("actions", "items", "plan", "recommendations", "briefs"):
        if isinstance(parsed.get(key), list):
            return parsed[key]
    # Single action object instead of a 1-element array
    if any(k in parsed for k in ("candidate_index", "proposed_changes", "steps", "title")):
        return [parsed]
    return parsed


def parse_json_payload(raw: str, expect: type = list):
    """Parse JSON from model output, stripping markdown fences if needed."""
    text = _strip_think_blocks(raw or "")
    if not text:
        raise json.JSONDecodeError("empty", "", 0)
    try:
        parsed = json.loads(text)
        if expect is list:
            return _coerce_list_payload(parsed)
        return parsed
    except json.JSONDecodeError:
        pass
    if expect is list:
        start, end = text.find("["), text.rfind("]") + 1
        if start < 0 or end <= start:
            start, end = text.find("{"), text.rfind("}") + 1
    else:
        start, end = text.find("{"), text.rfind("}") + 1
    if start >= 0 and end > start:
        parsed = json.loads(text[start:end])
        if expect is list:
            return _coerce_list_payload(parsed)
        return parsed
    raise json.JSONDecodeError("no json found", text, 0)
