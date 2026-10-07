"""Structured JSON generation against the local Ollama daemon.

Ollama has supported constrained decoding via ``format=<json schema>`` for a long
time, and this codebase never used it. Every existing call instead asks the model
for JSON in prose and then recovers it by brace-slicing the reply
(``text.find("{")`` .. ``text.rfind("}")``). That works right up until the model
emits a stray brace — inside a bio, a code fragment, a thinking block — at which
point the slice silently returns a *different* object than the model produced,
and the caller has no way to tell.

Passing the schema to the daemon makes the grammar itself constrain the sampler,
so the reply parses on the first try. Brace-slicing is kept only as a last-ditch
fallback, and every use of it is logged as a warning: the degradation must be
visible, not silent.

Failure is always ``None``. Callers of this module treat the LLM as an optional
enrichment, so an unreachable daemon must degrade the answer rather than break
the request.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import re
import time
from collections.abc import AsyncIterator, Sequence
from typing import Any

import httpx
import ollama

from app.config import get_settings
from app.services.ollama_client import build_ollama_client
from app.utils.logger import logger

# qwen3 emits its chain of thought inline. It is not part of the JSON and must be
# removed before any parse attempt. Same shape as `AIService._strip_thinking`.
_THINK_BLOCK = re.compile(r"<think>[\s\S]*?</think>")

# The narrative budget can reach 120 s, and a stream that has said nothing
# for a whole minute is hung rather than slow.
_STREAM_STALL_CEILING_S = 60.0


def strip_thinking(text: str) -> str:
    """Remove ``<think>...</think>`` blocks from a model reply."""
    return _THINK_BLOCK.sub("", text or "").strip()


def _brace_slice(text: str) -> dict[str, Any] | None:
    """Last-resort recovery: take the outermost ``{...}`` span and parse it.

    Deliberately unreliable — a stray brace anywhere in the reply moves the
    boundaries. Only reached when constrained decoding did not hold.
    """
    start = text.find("{")
    end = text.rfind("}") + 1
    if start == -1 or end <= start:
        return None
    try:
        parsed = json.loads(text[start:end])
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


async def generate_json(
    prompt: str,
    schema: dict[str, Any],
    *,
    model: str | None = None,
    timeout_s: float | None = None,
    temperature: float = 0.1,
    system: str | None = None,
    max_output_tokens: int = 4096,
    images: Sequence[str] | None = None,
    keep_alive: str | None = None,
) -> dict[str, Any] | None:
    """Ask the local model for JSON matching `schema`. Returns None on any failure.

    Args:
        prompt: The user-side instruction.
        schema: A JSON Schema dict handed to Ollama as ``format=``, which
            constrains decoding rather than merely describing the target.
        model: Overrides ``settings.ollama_model``.
        timeout_s: Overrides ``settings.llm_extraction_timeout_seconds``.
        temperature: Sampling temperature; low by default because this is
            extraction, not writing.
        system: Optional system prompt.
        images: Base64-encoded images for a multimodal model. The browse tier
            needs a screenshot and a schema in the same call; splitting them
            across two calls would load and evict a 6 GB model twice per step.
        keep_alive: How long ollama should hold the model after answering. The
            browse tier passes a short value so the vision model releases its
            VRAM before the text model needs it — on an 8 GB card the two do not
            fit together.
        max_output_tokens: Hard output budget (``num_predict``). Set explicitly
            rather than left to the server default, which is small enough that a
            thinking model can spend the entire allowance inside its ``<think>``
            block and return an empty answer — seen live with qwen3.5. When the
            model does hit this ceiling the call reports it rather than looking
            like a model that had nothing to say.
    """
    settings = get_settings()
    chosen_model = model or settings.ollama_model
    budget = timeout_s if timeout_s is not None else settings.llm_extraction_timeout_seconds
    client = build_ollama_client(read_timeout=budget)

    async def _call(constrained: bool) -> Any:
        kwargs: dict[str, Any] = {
            "model": chosen_model,
            "prompt": prompt,
            "system": system,
            "options": {"temperature": temperature, "top_p": 0.1, "num_predict": max_output_tokens},
        }
        if images:
            kwargs["images"] = list(images)
        if keep_alive is not None:
            kwargs["keep_alive"] = keep_alive
        if constrained:
            kwargs["format"] = schema
        return await asyncio.wait_for(client.generate(**kwargs), timeout=budget)

    try:
        response = await _call(constrained=True)

        # Hybrid reasoning models (qwen3, qwen3.5 — the configured default) emit a
        # <think> block before their answer. Constrained decoding applies to the
        # whole output, so the grammar and the thinking fight each other and the
        # model returns nothing at all. Verified live: `format=` of any shape gives
        # an empty string, while the identical unconstrained call answers correctly.
        # Retrying without the constraint costs one extra call only in the broken
        # case, and the prompt already states the required shape.
        # Stripped before the test, not after: the constraint fails in two shapes
        # and they look different only until the thinking block is removed. One is
        # a literally empty string; the other is a reply that is *all* <think> and
        # no answer. Testing the raw text saw the second as content, skipped the
        # retry, and then discarded it a few lines below as empty — the caller got
        # None and the biography fell back to the template with no retry spent.
        if not strip_thinking(str(response.get("response") or "")):
            logger.log_warning(
                f"llm_json: '{chosen_model}' returned nothing usable under format= "
                "(typical of a thinking model) — retrying unconstrained"
            )
            response = await _call(constrained=False)
    # TimeoutError must be caught before ConnectionError: on 3.11
    # asyncio.TimeoutError aliases the builtin TimeoutError, an OSError subclass,
    # and ConnectionError is also an OSError. Order decides which name the log
    # reports, and a timeout mislabelled as a connection failure sends the reader
    # to the wrong place.
    except TimeoutError:
        logger.log_warning(f"llm_json: model '{chosen_model}' timed out after {budget:.0f}s")
        return None
    except ollama.ResponseError as exc:
        # Only the status code is logged. The raw body can echo the prompt back,
        # and prompts here carry scraped personal data.
        logger.log_warning(f"llm_json: ollama refused the request: HTTP {exc.status_code}")
        return None
    # httpx.HTTPError is listed explicitly and NOT folded into ConnectionError:
    # `httpx.ConnectError` descends from `httpx.HTTPError`, not from the builtin
    # `ConnectionError`, so catching only the builtin lets a refused connection
    # escape this function entirely. Verified against a stopped daemon.
    except (httpx.HTTPError, ConnectionError) as exc:
        logger.log_warning(f"llm_json: cannot reach the ollama daemon: {type(exc).__name__}")
        return None

    truncated = response.get("done_reason") == "length"
    text = strip_thinking(str(response.get("response") or ""))
    if not text:
        if truncated:
            # The model spent its whole budget reasoning and never reached an
            # answer. That is a budget problem, not an empty-minded model, and the
            # two need different fixes — so they get different messages.
            logger.log_warning(
                f"llm_json: '{chosen_model}' hit the {max_output_tokens}-token ceiling while still reasoning; "
                "raise max_output_tokens or shorten the prompt"
            )
        else:
            logger.log_warning("llm_json: model returned an empty response")
        return None
    if truncated:
        logger.log_warning(f"llm_json: '{chosen_model}' output was cut at {max_output_tokens} tokens — may be partial")

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        # Reached whenever the reply was produced unconstrained (see the retry
        # above) or the daemon ignored `format`. Brace slicing is the fallback the
        # rest of the codebase already relies on.
        return _brace_slice(text)

    if not isinstance(parsed, dict):
        logger.log_warning(f"llm_json: expected a JSON object, got {type(parsed).__name__}")
        return None
    return parsed


# -- streaming ---------------------------------------------------------------


def _visible(raw: str) -> str:
    """``raw`` with the model's thinking removed, truncated at an open ``<think>``.

    Truncating rather than ignoring is the point: a hybrid reasoning model
    deliberates *about* the schema, so its monologue routinely contains a decoy
    ``"claims": [``. Scanning into an unterminated block would start the array on
    the model's notes instead of on its answer.
    """
    text = _THINK_BLOCK.sub("", raw)
    opened = text.find("<think>")
    return text if opened == -1 else text[:opened]


def _loads_object(span: str) -> dict[str, Any] | None:
    try:
        parsed = json.loads(span)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


class _JsonArrayScanner:
    """Cut complete objects out of a ``"<key>": [ ... ]`` array as bytes arrive.

    Three phases. Thinking is filtered first (see :func:`_visible`). Then
    everything before the array is discarded, which disposes of prose and code
    fences for free — a fence cannot appear inside valid JSON, so there is
    nothing left to strip once the cursor is past the ``[``. Then objects are cut
    on brace depth with string and escape state tracked, so a ``}`` inside a
    value cannot close one early.

    Scan state persists across feeds and the cursor only moves forward. That is
    safe because the *prefix* of :func:`_visible` never changes: removing a
    completed think block, or revealing text past a ``</think>``, only appends.
    """

    def __init__(self, array_key: str) -> None:
        self._needle = '"' + array_key + '"'
        self._raw = ""
        self._cursor = 0
        self._in_array = False
        self._closed = False
        self._depth = 0
        self._start = -1
        self._in_string = False
        self._escaped = False
        self._unparsable = 0

    @property
    def closed(self) -> bool:
        """True once the array's ``]`` has arrived."""
        return self._closed

    @property
    def pending_chars(self) -> int:
        """Characters of a half-written object left over when the stream ended."""
        return 0 if self._start < 0 else len(_visible(self._raw)) - self._start

    @property
    def unparsable(self) -> int:
        """Balanced spans that were not valid JSON. Non-zero means the scan drifted."""
        return self._unparsable

    def _locate_array(self, visible: str) -> int | None:
        """Offset just past the ``[`` opening the target array, if it is here yet.

        Every occurrence of the key is tried, not just the first. A model that
        narrates before it answers ("I will return \"claims\" shortly.") puts the
        needle in prose first, and stopping there would wait forever for an array
        that opens a few characters later.
        """
        at = visible.find(self._needle)
        while at != -1:
            after = at + len(self._needle)
            opened = visible.find("[", after)
            if opened == -1:
                return None
            # Only a colon and whitespace may sit between the key and its array.
            # Anything else means this was the key's name appearing in a value.
            if visible[after:opened].strip() == ":":
                return opened + 1
            at = visible.find(self._needle, after)
        return None

    def feed(self, text: str) -> list[dict[str, Any]]:
        """Absorb the next chunk and return every object it completed."""
        if self._closed:
            return []
        self._raw += text
        visible = _visible(self._raw)

        if not self._in_array:
            start = self._locate_array(visible)
            if start is None:
                return []
            self._cursor = start
            self._in_array = True

        found: list[dict[str, Any]] = []
        index = self._cursor
        while index < len(visible):
            char = visible[index]
            if self._in_string:
                if self._escaped:
                    self._escaped = False
                elif char == "\\":
                    self._escaped = True
                elif char == '"':
                    self._in_string = False
            elif char == '"':
                self._in_string = True
            elif char == "{":
                if self._depth == 0:
                    self._start = index
                self._depth += 1
            elif char == "}":
                self._depth -= 1
                if self._depth == 0 and self._start >= 0:
                    parsed = _loads_object(visible[self._start : index + 1])
                    if parsed is None:
                        self._unparsable += 1
                    else:
                        found.append(parsed)
                    self._start = -1
            elif char == "]" and self._depth == 0:
                self._closed = True
                self._cursor = index + 1
                return found
            index += 1

        self._cursor = index
        return found


async def stream_json_items(
    prompt: str,
    *,
    array_key: str,
    budget_s: float,
    stall_timeout_s: float | None = None,
    model: str | None = None,
    temperature: float = 0.1,
    system: str | None = None,
    max_output_tokens: int = 4096,
    keep_alive: str | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """Yield each object of the reply's ``array_key`` array as the model writes it.

    Deliberately unlike :func:`generate_json` in one respect: **no ``format=``**.
    ``generate_json`` can afford to try constrained decoding and pay one retry
    when a thinking model answers nothing; a stream cannot, because that retry is
    a second whole generation and there is only one budget. The configured
    default *is* such a model, so this path goes unconstrained from the first
    token and leans on the scanner instead. The prompt already states the shape.

    Two independent clocks, because they measure different failures.
    ``stall_timeout_s`` becomes the httpx read timeout — "no new bytes for this
    long", the only bound that works on a lazy stream. ``budget_s`` is an
    absolute deadline checked between chunks, so a model dribbling one token
    every few seconds cannot outlive the search waiting on it.

    Never raises, and never yields a partial object. On any failure it simply
    stops, which the caller cannot distinguish from a model that had nothing to
    say — and does not need to: ``payload is None`` and ``{"claims": []}``
    already take the identical fallback branch today.
    """
    settings = get_settings()
    chosen_model = model or settings.ollama_model
    read_timeout = stall_timeout_s if stall_timeout_s is not None else min(budget_s, _STREAM_STALL_CEILING_S)
    client = build_ollama_client(read_timeout=read_timeout)
    scanner = _JsonArrayScanner(array_key)
    deadline = time.monotonic() + budget_s
    delivered = 0

    kwargs: dict[str, Any] = {
        "model": chosen_model,
        "prompt": prompt,
        "system": system,
        "stream": True,
        "options": {"temperature": temperature, "top_p": 0.1, "num_predict": max_output_tokens},
    }
    if keep_alive is not None:
        kwargs["keep_alive"] = keep_alive

    stream = None
    try:
        stream = await client.generate(**kwargs)
        async for chunk in stream:
            piece = str(chunk.get("response") or "")
            if piece:
                for item in scanner.feed(piece):
                    delivered += 1
                    yield item
            if chunk.get("done"):
                if chunk.get("done_reason") == "length":
                    logger.log_warning(
                        f"llm_json: '{chosen_model}' hit the {max_output_tokens}-token ceiling mid-stream; "
                        f"the {delivered} item(s) already delivered stand"
                    )
                break
            if time.monotonic() >= deadline:
                logger.log_warning(
                    f"llm_json: '{chosen_model}' exceeded its {budget_s:.0f}s stream budget after {delivered} item(s)"
                )
                break
    # Ordered exactly as in `generate_json`: on 3.11 asyncio.TimeoutError aliases
    # the builtin TimeoutError, an OSError subclass, and so is ConnectionError.
    except TimeoutError:
        logger.log_warning(f"llm_json: the stream from '{chosen_model}' went silent for {read_timeout:.0f}s")
    except ollama.ResponseError as exc:
        logger.log_warning(f"llm_json: ollama refused the stream: HTTP {exc.status_code}")
    except (httpx.HTTPError, ConnectionError) as exc:
        logger.log_warning(f"llm_json: the stream from the ollama daemon failed: {type(exc).__name__}")
    except json.JSONDecodeError:
        # The daemon can emit a malformed frame mid-stream. Whatever already
        # arrived is still good.
        logger.log_warning("llm_json: the ollama stream carried a malformed frame")
    finally:
        if stream is not None:
            with contextlib.suppress(Exception):
                await stream.aclose()

    if scanner.unparsable:
        logger.log_warning(f"llm_json: skipped {scanner.unparsable} balanced span(s) that were not valid JSON")
    if not scanner.closed and scanner.pending_chars:
        logger.log_warning(
            f"llm_json: the stream ended mid-array after {delivered} item(s); "
            f"{scanner.pending_chars} unterminated char(s) discarded"
        )
