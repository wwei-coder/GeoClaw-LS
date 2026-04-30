import json
import time
import asyncio
import re
import requests
import httpx
from typing import Generator, AsyncGenerator, Optional, Any, Dict
from opentelemetry import trace
from openinference.semconv.trace import SpanAttributes, OpenInferenceSpanKindValues
from utils.logger import logger

from core.config import (
    LLM_PROVIDER,
    OLLAMA_URL,
    OLLAMA_MODEL,
    OLLAMA_TEMPERATURE,
    OLLAMA_TIMEOUT,
    OLLAMA_STREAM_TIMEOUT,
    LLM_API_BASE_URL,
    LLM_API_KEY,
    LLM_API_MODEL,
    LLM_API_TIMEOUT,
    LLM_API_STREAM_TIMEOUT,
    LLM_API_MAX_TOKENS,
)

tracer = trace.get_tracer(__name__)
_RETRYABLE_STATUS_CODES = {408, 429, 500, 502, 503, 504}
_MAX_RETRIES = 2
_BACKOFF_BASE = 0.6


class OllamaError(RuntimeError):
    """统一 LLM 客户端异常（兼容旧命名）。"""
    pass


def _format_error(error: Exception) -> str:
    text = str(error).strip()
    if text:
        return f"{type(error).__name__}: {text}"
    return type(error).__name__


def _backoff_sleep_seconds(attempt_index: int) -> float:
    return _BACKOFF_BASE * (2 ** attempt_index)


def _is_openai_compatible_provider() -> bool:
    # Project runs in local-only mode: remote API providers are disabled.
    return False


def _extract_status_code(error: Exception) -> Optional[int]:
    text = str(error)
    match = re.search(r"(?:状态码|status)\s*[: ]\s*(\d+)", text, flags=re.IGNORECASE)
    if not match:
        return None
    try:
        return int(match.group(1))
    except Exception:
        return None


def _should_try_local_ollama_fallback(error: Exception) -> bool:
    if not _is_openai_compatible_provider():
        return False
    if not (OLLAMA_URL or "").strip():
        return False
    if isinstance(error, (requests.RequestException, httpx.RequestError)):
        return True
    status_code = _extract_status_code(error)
    return status_code in _RETRYABLE_STATUS_CODES if status_code is not None else False


def _is_retryable_exception(error: Exception) -> bool:
    if isinstance(error, (requests.RequestException, httpx.RequestError)):
        return True
    status_code = _extract_status_code(error)
    return status_code in _RETRYABLE_STATUS_CODES if status_code is not None else False


def _local_ollama_timeout(timeout: Optional[int], stream: bool) -> int:
    if timeout is not None:
        return timeout
    return OLLAMA_STREAM_TIMEOUT if stream else OLLAMA_TIMEOUT


def _make_local_ollama_payload(prompt: str, temperature: float, stream: bool) -> Dict[str, Any]:
    return {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "temperature": temperature,
        "stream": stream,
    }


def _ask_local_ollama_nonstream_sync(prompt: str, temperature: float, timeout: Optional[int]) -> str:
    payload = _make_local_ollama_payload(prompt, temperature, stream=False)
    resp = requests.post(
        OLLAMA_URL,
        json=payload,
        headers={"Content-Type": "application/json"},
        timeout=_local_ollama_timeout(timeout, stream=False),
    )
    if resp.status_code != 200:
        raise OllamaError(f"本地 Ollama 兜底失败，状态码 {resp.status_code}: {resp.text}")
    data = resp.json()
    return data.get("response", "") or ""


async def _ask_local_ollama_nonstream_async(prompt: str, temperature: float, timeout: Optional[int]) -> str:
    payload = _make_local_ollama_payload(prompt, temperature, stream=False)
    async with httpx.AsyncClient(timeout=_local_ollama_timeout(timeout, stream=False)) as client:
        resp = await client.post(
            OLLAMA_URL,
            json=payload,
            headers={"Content-Type": "application/json"},
        )
    if resp.status_code != 200:
        raise OllamaError(f"本地 Ollama 兜底失败，状态码 {resp.status_code}: {resp.text}")
    data = resp.json()
    return data.get("response", "") or ""


def _resolve_target_url(custom_url: Optional[str] = None) -> str:
    if custom_url:
        return custom_url.strip()
    if _is_openai_compatible_provider():
        base_url = (LLM_API_BASE_URL or "").strip()
        if not base_url:
            raise OllamaError("当前 provider 为 openai_compatible，但未配置 models.api.base_url 或 LLM_API_BASE_URL")
        if base_url.endswith("/chat/completions"):
            return base_url
        return base_url.rstrip("/") + "/chat/completions"
    return OLLAMA_URL


def _resolve_model_name(model: Optional[str] = None) -> str:
    if model:
        return model
    return LLM_API_MODEL if _is_openai_compatible_provider() else OLLAMA_MODEL


def _resolve_timeout(timeout: Optional[int], stream: bool) -> int:
    if timeout is not None:
        return timeout
    if _is_openai_compatible_provider():
        return LLM_API_STREAM_TIMEOUT if stream else LLM_API_TIMEOUT
    return OLLAMA_STREAM_TIMEOUT if stream else OLLAMA_TIMEOUT


def _resolve_headers() -> Dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if _is_openai_compatible_provider():
        if not LLM_API_KEY:
            raise OllamaError("当前 provider 为 openai_compatible，但未配置 models.api.api_key 或 LLM_API_KEY")
        headers["Authorization"] = f"Bearer {LLM_API_KEY}"
    return headers


def _make_payload(
    prompt: str,
    model: Optional[str] = None,
    temperature: float = OLLAMA_TEMPERATURE,
    stream: bool = False,
) -> Dict[str, Any]:
    model_name = _resolve_model_name(model)
    if _is_openai_compatible_provider():
        payload: Dict[str, Any] = {
            "model": model_name,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "stream": stream,
        }
        if LLM_API_MAX_TOKENS > 0:
            payload["max_tokens"] = LLM_API_MAX_TOKENS
        return payload
    return {
        "model": model_name,
        "prompt": prompt,
        "temperature": temperature,
        "stream": stream,
    }


def _parse_nonstream_response(response: requests.Response) -> str:
    if response.status_code != 200:
        raise OllamaError(f"LLM API 调用失败，状态码 {response.status_code}: {response.text}")
    data = response.json()
    if _is_openai_compatible_provider():
        choices = data.get("choices") or []
        if not choices:
            return ""
        message = choices[0].get("message") or {}
        return message.get("content", "") or ""
    return data.get("response", "") or ""


def _extract_stream_text_openai_chunk(chunk: Dict[str, Any]) -> str:
    choices = chunk.get("choices") or []
    if not choices:
        return ""
    delta = choices[0].get("delta") or {}
    return delta.get("content", "") or ""


def _iter_stream_text_requests(resp: requests.Response) -> Generator[str, None, None]:
    if _is_openai_compatible_provider():
        for raw_line in resp.iter_lines():
            if not raw_line:
                continue
            line = raw_line.decode("utf-8", errors="ignore") if isinstance(raw_line, bytes) else str(raw_line)
            line = line.strip()
            if not line.startswith("data:"):
                continue
            payload = line[5:].strip()
            if payload == "[DONE]":
                return
            try:
                chunk = json.loads(payload)
            except json.JSONDecodeError:
                continue
            text_chunk = _extract_stream_text_openai_chunk(chunk)
            if text_chunk:
                yield text_chunk
    else:
        for raw_line in resp.iter_lines():
            if not raw_line:
                continue
            try:
                chunk = json.loads(raw_line)
            except json.JSONDecodeError:
                continue
            if chunk.get("done"):
                return
            text_chunk = chunk.get("response", "") or ""
            if text_chunk:
                yield text_chunk


def ask_ollama(
    prompt: str,
    model: Optional[str] = None,
    temperature: float = OLLAMA_TEMPERATURE,
    timeout: Optional[int] = None,
    url: Optional[str] = None,
) -> str:
    with tracer.start_as_current_span("ask_ollama") as span:
        model_name = _resolve_model_name(model)
        target_url = _resolve_target_url(url)
        req_timeout = _resolve_timeout(timeout, stream=False)

        span.set_attribute(SpanAttributes.OPENINFERENCE_SPAN_KIND, OpenInferenceSpanKindValues.LLM.value)
        span.set_attribute(SpanAttributes.LLM_MODEL_NAME, model_name)
        span.set_attribute(SpanAttributes.INPUT_VALUE, prompt)
        span.set_attribute(SpanAttributes.LLM_INVOCATION_PARAMETERS, json.dumps({"temperature": temperature}))
        span.set_attribute("llm.provider", LLM_PROVIDER)
        span.set_attribute("retry.max_attempts", _MAX_RETRIES)

        payload = _make_payload(prompt, model, temperature, stream=False)
        headers = _resolve_headers()

        last_exc = None
        for attempt in range(_MAX_RETRIES):
            try:
                resp = requests.post(target_url, json=payload, headers=headers, timeout=req_timeout)
                if resp.status_code in _RETRYABLE_STATUS_CODES and attempt < _MAX_RETRIES - 1:
                    span.add_event(f"retry.http_status.{resp.status_code}", {"attempt": attempt + 1})
                    time.sleep(_backoff_sleep_seconds(attempt))
                    continue
                response_text = _parse_nonstream_response(resp)
                span.set_attribute(SpanAttributes.OUTPUT_VALUE, response_text)
                if attempt > 0:
                    span.set_attribute("retry.attempts_used", attempt + 1)
                return response_text
            except requests.RequestException as e:
                last_exc = e
                if attempt < _MAX_RETRIES - 1:
                    span.add_event("retry.network_error", {"attempt": attempt + 1, "error": str(e)})
                    time.sleep(_backoff_sleep_seconds(attempt))
                    continue
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                span.record_exception(e)
                raise OllamaError(f"LLM 网络请求失败: {_format_error(e)}") from e
            except Exception as e:
                if attempt == _MAX_RETRIES - 1 and _should_try_local_ollama_fallback(e):
                    span.add_event("fallback.local_ollama.sync", {"error": str(e)})
                    logger.warning("LLM 主链路失败，已自动回退到本地 Ollama（sync）")
                    try:
                        response_text = _ask_local_ollama_nonstream_sync(prompt, temperature, timeout)
                        span.set_attribute(SpanAttributes.OUTPUT_VALUE, response_text)
                        span.set_attribute("fallback.local_ollama.used", True)
                        return response_text
                    except Exception as fallback_error:
                        raise OllamaError(f"{e} | 本地兜底也失败: {fallback_error}") from fallback_error
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                span.record_exception(e)
                raise
        if last_exc is not None:
            raise OllamaError(f"LLM 网络请求失败: {_format_error(last_exc)}") from last_exc
        raise OllamaError("LLM 调用在重试后仍失败")


def ask_ollama_stream(
    prompt: str,
    model: Optional[str] = None,
    temperature: float = OLLAMA_TEMPERATURE,
    timeout: Optional[int] = None,
    url: Optional[str] = None,
    cancel_event=None,
) -> Generator[str, None, None]:
    with tracer.start_as_current_span("ask_ollama_stream") as span:
        model_name = _resolve_model_name(model)
        target_url = _resolve_target_url(url)
        req_timeout = _resolve_timeout(timeout, stream=True)

        span.set_attribute(SpanAttributes.OPENINFERENCE_SPAN_KIND, OpenInferenceSpanKindValues.LLM.value)
        span.set_attribute(SpanAttributes.LLM_MODEL_NAME, model_name)
        span.set_attribute(SpanAttributes.INPUT_VALUE, prompt)
        span.set_attribute(SpanAttributes.LLM_INVOCATION_PARAMETERS, json.dumps({"temperature": temperature}))
        span.set_attribute("llm.provider", LLM_PROVIDER)
        span.set_attribute("retry.max_attempts", _MAX_RETRIES)

        payload = _make_payload(prompt, model, temperature, stream=True)
        headers = _resolve_headers()
        full_response = []

        for attempt in range(_MAX_RETRIES):
            emitted_any = False
            try:
                with requests.post(target_url, json=payload, headers=headers, stream=True, timeout=req_timeout) as resp:
                    if resp.status_code in _RETRYABLE_STATUS_CODES and attempt < _MAX_RETRIES - 1:
                        span.add_event(f"retry.http_status.{resp.status_code}", {"attempt": attempt + 1})
                        time.sleep(_backoff_sleep_seconds(attempt))
                        continue
                    if resp.status_code != 200:
                        error_msg = f"LLM 流式调用失败，状态码 {resp.status_code}: {resp.text}"
                        span.set_status(trace.Status(trace.StatusCode.ERROR, error_msg))
                        raise OllamaError(error_msg)

                    for text_chunk in _iter_stream_text_requests(resp):
                        if cancel_event is not None and getattr(cancel_event, "is_set", None) and cancel_event.is_set():
                            span.add_event("cancelled")
                            break
                        full_response.append(text_chunk)
                        emitted_any = True
                        yield text_chunk

                span.set_attribute(SpanAttributes.OUTPUT_VALUE, "".join(full_response))
                if attempt > 0:
                    span.set_attribute("retry.attempts_used", attempt + 1)
                return
            except requests.RequestException as e:
                if emitted_any or attempt == _MAX_RETRIES - 1:
                    span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                    span.record_exception(e)
                    raise OllamaError(f"LLM 流式网络请求失败: {_format_error(e)}") from e
                span.add_event("retry.network_error", {"attempt": attempt + 1, "error": str(e)})
                time.sleep(_backoff_sleep_seconds(attempt))
            except Exception as e:
                if attempt == _MAX_RETRIES - 1 and _should_try_local_ollama_fallback(e):
                    span.add_event("fallback.local_ollama.stream_sync", {"error": str(e)})
                    logger.warning("LLM 流式主链路失败，已自动回退到本地 Ollama（sync stream->nonstream）")
                    try:
                        fallback_text = _ask_local_ollama_nonstream_sync(prompt, temperature, timeout)
                        if fallback_text:
                            full_response.append(fallback_text)
                            yield fallback_text
                        span.set_attribute(SpanAttributes.OUTPUT_VALUE, "".join(full_response))
                        span.set_attribute("fallback.local_ollama.used", True)
                        return
                    except Exception as fallback_error:
                        raise OllamaError(f"{e} | 本地兜底也失败: {fallback_error}") from fallback_error
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                span.record_exception(e)
                raise


async def ask_ollama_async(
    prompt: str,
    model: Optional[str] = None,
    temperature: float = OLLAMA_TEMPERATURE,
    timeout: Optional[int] = None,
    url: Optional[str] = None,
) -> str:
    with tracer.start_as_current_span("ask_ollama_async") as span:
        model_name = _resolve_model_name(model)
        target_url = _resolve_target_url(url)
        req_timeout = _resolve_timeout(timeout, stream=False)

        span.set_attribute(SpanAttributes.OPENINFERENCE_SPAN_KIND, OpenInferenceSpanKindValues.LLM.value)
        span.set_attribute(SpanAttributes.LLM_MODEL_NAME, model_name)
        span.set_attribute(SpanAttributes.INPUT_VALUE, prompt)
        span.set_attribute(SpanAttributes.LLM_INVOCATION_PARAMETERS, json.dumps({"temperature": temperature}))
        span.set_attribute("llm.provider", LLM_PROVIDER)
        span.set_attribute("retry.max_attempts", _MAX_RETRIES)

        payload = _make_payload(prompt, model, temperature, stream=False)
        headers = _resolve_headers()

        last_exc = None
        for attempt in range(_MAX_RETRIES):
            try:
                async with httpx.AsyncClient(timeout=req_timeout, trust_env=False) as client:
                    resp = await client.post(target_url, json=payload, headers=headers)
                if resp.status_code in _RETRYABLE_STATUS_CODES and attempt < _MAX_RETRIES - 1:
                    span.add_event(f"retry.http_status.{resp.status_code}", {"attempt": attempt + 1})
                    await asyncio.sleep(_backoff_sleep_seconds(attempt))
                    continue
                if resp.status_code != 200:
                    raise OllamaError(f"LLM API 调用失败，状态码 {resp.status_code}: {resp.text}")
                data = resp.json()
                if _is_openai_compatible_provider():
                    choices = data.get("choices") or []
                    response_text = ((choices[0].get("message") or {}).get("content", "") if choices else "")
                else:
                    response_text = data.get("response", "")
                response_text = response_text or ""
                span.set_attribute(SpanAttributes.OUTPUT_VALUE, response_text)
                if attempt > 0:
                    span.set_attribute("retry.attempts_used", attempt + 1)
                return response_text
            except httpx.RequestError as e:
                last_exc = e
                if attempt < _MAX_RETRIES - 1:
                    span.add_event("retry.network_error", {"attempt": attempt + 1, "error": str(e)})
                    await asyncio.sleep(_backoff_sleep_seconds(attempt))
                    continue
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                span.record_exception(e)
                raise OllamaError(f"LLM 网络请求失败: {_format_error(e)}") from e
            except Exception as e:
                if attempt == _MAX_RETRIES - 1 and _is_retryable_exception(e):
                    span.add_event("fallback.requests.sync_path.async", {"error": str(e)})
                    logger.warning("LLM 异步链路失败，回退到 requests 同步通道")
                    try:
                        response_text = await asyncio.to_thread(
                            ask_ollama,
                            prompt,
                            model,
                            temperature,
                            timeout,
                            url,
                        )
                        span.set_attribute(SpanAttributes.OUTPUT_VALUE, response_text)
                        span.set_attribute("fallback.requests.sync_path.used", True)
                        return response_text
                    except Exception as sync_fallback_error:
                        # For openai-compatible provider, additionally try direct local-ollama fallback.
                        if _should_try_local_ollama_fallback(e):
                            span.add_event("fallback.local_ollama.async", {"error": str(e)})
                            logger.warning("LLM 主链路失败，已自动回退到本地 Ollama（async）")
                            try:
                                response_text = await _ask_local_ollama_nonstream_async(prompt, temperature, timeout)
                                span.set_attribute(SpanAttributes.OUTPUT_VALUE, response_text)
                                span.set_attribute("fallback.local_ollama.used", True)
                                return response_text
                            except Exception as fallback_error:
                                raise OllamaError(f"{e} | 同步回退失败: {sync_fallback_error} | 本地兜底也失败: {fallback_error}") from fallback_error
                        raise OllamaError(f"{e} | 同步回退失败: {sync_fallback_error}") from sync_fallback_error
                if attempt == _MAX_RETRIES - 1 and _should_try_local_ollama_fallback(e):
                    span.add_event("fallback.local_ollama.async", {"error": str(e)})
                    logger.warning("LLM 主链路失败，已自动回退到本地 Ollama（async）")
                    try:
                        response_text = await _ask_local_ollama_nonstream_async(prompt, temperature, timeout)
                        span.set_attribute(SpanAttributes.OUTPUT_VALUE, response_text)
                        span.set_attribute("fallback.local_ollama.used", True)
                        return response_text
                    except Exception as fallback_error:
                        raise OllamaError(f"{e} | 本地兜底也失败: {fallback_error}") from fallback_error
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                span.record_exception(e)
                raise
        if last_exc is not None:
            raise OllamaError(f"LLM 网络请求失败: {_format_error(last_exc)}") from last_exc
        raise OllamaError("LLM 异步调用在重试后仍失败")


async def ask_ollama_stream_async(
    prompt: str,
    model: Optional[str] = None,
    temperature: float = OLLAMA_TEMPERATURE,
    timeout: Optional[int] = None,
    url: Optional[str] = None,
    cancel_event=None,
) -> AsyncGenerator[str, None]:
    with tracer.start_as_current_span("ask_ollama_stream_async") as span:
        model_name = _resolve_model_name(model)
        target_url = _resolve_target_url(url)
        req_timeout = _resolve_timeout(timeout, stream=True)

        span.set_attribute(SpanAttributes.OPENINFERENCE_SPAN_KIND, OpenInferenceSpanKindValues.LLM.value)
        span.set_attribute(SpanAttributes.LLM_MODEL_NAME, model_name)
        span.set_attribute(SpanAttributes.INPUT_VALUE, prompt)
        span.set_attribute(SpanAttributes.LLM_INVOCATION_PARAMETERS, json.dumps({"temperature": temperature}))
        span.set_attribute("llm.provider", LLM_PROVIDER)
        span.set_attribute("retry.max_attempts", _MAX_RETRIES)

        payload = _make_payload(prompt, model, temperature, stream=True)
        headers = _resolve_headers()
        full_response = []

        for attempt in range(_MAX_RETRIES):
            emitted_any = False
            try:
                async with httpx.AsyncClient(timeout=req_timeout, trust_env=False) as client:
                    async with client.stream("POST", target_url, json=payload, headers=headers) as resp:
                        if resp.status_code in _RETRYABLE_STATUS_CODES and attempt < _MAX_RETRIES - 1:
                            span.add_event(f"retry.http_status.{resp.status_code}", {"attempt": attempt + 1})
                            await asyncio.sleep(_backoff_sleep_seconds(attempt))
                            continue
                        if resp.status_code != 200:
                            content = await resp.aread()
                            err_body = content.decode("utf-8", errors="ignore")
                            error_msg = f"LLM 流式调用失败，状态码 {resp.status_code}: {err_body}"
                            span.set_status(trace.Status(trace.StatusCode.ERROR, error_msg))
                            raise OllamaError(error_msg)

                        async for line in resp.aiter_lines():
                            if cancel_event is not None and getattr(cancel_event, "is_set", None) and cancel_event.is_set():
                                span.add_event("cancelled")
                                break
                            if not line:
                                continue
                            text_chunk = ""
                            if _is_openai_compatible_provider():
                                line = line.strip()
                                if not line.startswith("data:"):
                                    continue
                                payload_text = line[5:].strip()
                                if payload_text == "[DONE]":
                                    break
                                try:
                                    chunk = json.loads(payload_text)
                                except json.JSONDecodeError:
                                    continue
                                text_chunk = _extract_stream_text_openai_chunk(chunk)
                            else:
                                try:
                                    chunk = json.loads(line)
                                except json.JSONDecodeError:
                                    continue
                                if chunk.get("done"):
                                    break
                                text_chunk = chunk.get("response", "") or ""
                            if text_chunk:
                                full_response.append(text_chunk)
                                emitted_any = True
                                yield text_chunk

                span.set_attribute(SpanAttributes.OUTPUT_VALUE, "".join(full_response))
                if attempt > 0:
                    span.set_attribute("retry.attempts_used", attempt + 1)
                return
            except httpx.RequestError as e:
                if emitted_any or attempt == _MAX_RETRIES - 1:
                    span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                    span.record_exception(e)
                    raise OllamaError(f"LLM 流式网络请求失败: {_format_error(e)}") from e
                span.add_event("retry.network_error", {"attempt": attempt + 1, "error": str(e)})
                await asyncio.sleep(_backoff_sleep_seconds(attempt))
            except Exception as e:
                if attempt == _MAX_RETRIES - 1 and _is_retryable_exception(e):
                    span.add_event("fallback.requests.sync_path.stream_async", {"error": str(e)})
                    logger.warning("LLM 异步流式链路失败，回退到 requests 同步通道")
                    try:
                        fallback_text = await asyncio.to_thread(
                            ask_ollama,
                            prompt,
                            model,
                            temperature,
                            timeout,
                            url,
                        )
                        if fallback_text:
                            full_response.append(fallback_text)
                            yield fallback_text
                        span.set_attribute(SpanAttributes.OUTPUT_VALUE, "".join(full_response))
                        span.set_attribute("fallback.requests.sync_path.used", True)
                        return
                    except Exception as sync_fallback_error:
                        if _should_try_local_ollama_fallback(e):
                            span.add_event("fallback.local_ollama.stream_async", {"error": str(e)})
                            logger.warning("LLM 流式主链路失败，已自动回退到本地 Ollama（async stream->nonstream）")
                            try:
                                fallback_text = await _ask_local_ollama_nonstream_async(prompt, temperature, timeout)
                                if fallback_text:
                                    full_response.append(fallback_text)
                                    yield fallback_text
                                span.set_attribute(SpanAttributes.OUTPUT_VALUE, "".join(full_response))
                                span.set_attribute("fallback.local_ollama.used", True)
                                return
                            except Exception as fallback_error:
                                raise OllamaError(f"{e} | 同步回退失败: {sync_fallback_error} | 本地兜底也失败: {fallback_error}") from fallback_error
                        raise OllamaError(f"{e} | 同步回退失败: {sync_fallback_error}") from sync_fallback_error
                if attempt == _MAX_RETRIES - 1 and _should_try_local_ollama_fallback(e):
                    span.add_event("fallback.local_ollama.stream_async", {"error": str(e)})
                    logger.warning("LLM 流式主链路失败，已自动回退到本地 Ollama（async stream->nonstream）")
                    try:
                        fallback_text = await _ask_local_ollama_nonstream_async(prompt, temperature, timeout)
                        if fallback_text:
                            full_response.append(fallback_text)
                            yield fallback_text
                        span.set_attribute(SpanAttributes.OUTPUT_VALUE, "".join(full_response))
                        span.set_attribute("fallback.local_ollama.used", True)
                        return
                    except Exception as fallback_error:
                        raise OllamaError(f"{e} | 本地兜底也失败: {fallback_error}") from fallback_error
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                span.record_exception(e)
                raise
