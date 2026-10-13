"""Small OpenAI-compatible Groq streaming adapter; uses only the standard library."""
import json
import os
import time
from uuid import uuid4
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from services.auth_service import authorize_bedrock, AuthenticationError
from services.bedrock_service import BedrockService, GenerationError, GenerationResult
from services.observability import log_event, safe_error_category
from services.provider_config import groq_model
from services.request_limits import validate_request, RequestLimitError
from services.usage_accounting import make_usage_record


class GroqService:
    """Preserves the BedrockService streaming/history contract for text-only Groq."""
    region = "groq-cloud"

    def __init__(self, *, model_id=None, max_tokens=None, temperature=None,
                 system_prompt=None, auth_session=None):
        authorize_bedrock(auth_session)
        self._auth_session = auth_session
        self.model_id = model_id or groq_model()
        if self.model_id != groq_model():
            raise ValueError("Select the configured Groq model.")
        if not os.environ.get("GROQ_API_KEY", "").strip():
            raise GenerationError("MissingGroqApiKey",
                                  safe_message="Groq is not configured. Set GROQ_API_KEY to use this provider.")
        self.max_tokens = 2048 if max_tokens is None else max_tokens
        self.temperature = 0.7 if temperature is None else temperature
        self.system_prompt = system_prompt or "You are NovaMind, a helpful AI assistant."
        self._last_used_model_id = None
        self._client = None  # compatibility with session cleanup; no persistent HTTP client

    def _build_candidate_list(self):
        return [self.model_id]

    def _build_content_blocks(self, user_text, image_bytes=None, image_format=None,
                              doc_bytes=None, doc_name=None, doc_format=None):
        # Shared normalisation is safe: it builds data only and does not create an AWS client.
        return BedrockService._build_content_blocks(
            self, user_text, image_bytes, image_format, doc_bytes, doc_name, doc_format)

    def update_settings(self, temperature=None, max_tokens=None, system_prompt=None):
        if temperature is not None:
            self.temperature = temperature
        if max_tokens is not None:
            self.max_tokens = max_tokens
        if system_prompt is not None:
            self.system_prompt = system_prompt

    def invoke_response(self, user_text, history, **kwargs):
        return "".join(self.stream_response(user_text, history, **kwargs))

    def stream_response(self, user_text, history, *, image_bytes=None, image_format=None,
                        doc_bytes=None, doc_name=None, doc_format="pdf", operation="chat",
                        usage_records=None, authorization_check=None, metrics_callback=None):
        authorize_bedrock(self._auth_session)
        if authorization_check is not None:
            authorization_check()
        request_id = str(uuid4())
        started = time.perf_counter()
        blocks = self._build_content_blocks(user_text, image_bytes, image_format,
                                            doc_bytes, doc_name, doc_format)
        messages = history + [{"role": "user", "content": blocks}]
        try:
            validate_request(self.model_id, self.system_prompt, self.max_tokens,
                             self.temperature, messages)
        except RequestLimitError as exc:
            raise GenerationError(exc.code, safe_message=str(exc)) from None

        if operation not in {"chat", "summary"}:
            raise GenerationError("UnsupportedOperation")
        api_messages = [{"role": "system", "content": self.system_prompt}]
        for message in history:
            text = "\n".join(block["text"] for block in message["content"] if "text" in block)
            api_messages.append({"role": message["role"], "content": text})
        api_messages.append({"role": "user", "content": "\n".join(
            block["text"] for block in blocks if "text" in block)})
        payload = json.dumps({
            "model": self.model_id, "messages": api_messages,
            "temperature": self.temperature, "max_completion_tokens": self.max_tokens,
            "stream": True, "stream_options": {"include_usage": True},
        }).encode("utf-8")
        api_key = os.environ.get("GROQ_API_KEY", "").strip()
        if not api_key:
            raise GenerationError("MissingGroqApiKey",
                                  safe_message="Groq is not configured. Set GROQ_API_KEY to use this provider.")
        request = Request("https://api.groq.com/openai/v1/chat/completions", data=payload,
                          headers={"Authorization": "Bearer " + api_key,
                                   "Content-Type": "application/json",
                                   "User-Agent": "NovaMindAI/1.0",
                                   "Accept": "text/event-stream"}, method="POST")
        response = None
        full_reply = ""
        usage = {}
        status = "incomplete"
        stop_reason = None
        category = None
        failure = None
        try:
            if metrics_callback:
                try:
                    metrics_callback({"provider": "Groq Cloud", "model": self.model_id,
                                      "status": "generating"})
                except Exception:
                    pass
            response = urlopen(request, timeout=60)
            for raw_line in response:
                if authorization_check is not None:
                    authorization_check()
                line = raw_line.decode("utf-8").strip() if isinstance(raw_line, bytes) else raw_line.strip()
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                event = json.loads(data)
                if isinstance(event.get("usage"), dict):
                    raw_usage = event["usage"]
                    usage = {"inputTokens": raw_usage.get("prompt_tokens"),
                             "outputTokens": raw_usage.get("completion_tokens"),
                             "totalTokens": raw_usage.get("total_tokens")}
                choices = event.get("choices") or []
                if choices:
                    choice = choices[0]
                    stop_reason = choice.get("finish_reason") or stop_reason
                    text = (choice.get("delta") or {}).get("content")
                    if isinstance(text, str) and text:
                        full_reply += text
                        if metrics_callback:
                            try:
                                metrics_callback({"latency_ms": (time.perf_counter() - started) * 1000,
                                                  "provider": "Groq Cloud", "model": self.model_id})
                            except Exception:
                                pass
                        yield text
            if not full_reply.strip():
                raise GenerationError("EmptyResponse")
            authorize_bedrock(self._auth_session, online=False)
            if authorization_check is not None:
                authorization_check()
            status = "completed"
        except AuthenticationError:
            status = "failed"
            category = "authentication"
            raise
        except GenerationError as exc:
            failure = exc
            status = exc.result.status
            category = safe_error_category(code=exc.result.error_code)
            raise
        except HTTPError as exc:
            status = "incomplete" if full_reply else "failed"
            category = {
                400: "validation", 401: "authentication", 403: "authorization",
                408: "timeout", 422: "validation", 429: "throttling", 504: "timeout",
            }.get(exc.code, "provider")
            failure = GenerationError(f"GroqHTTP{exc.code}", full_reply)
            raise failure from None
        except (URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError) as exc:
            status = "incomplete" if full_reply else "failed"
            category = safe_error_category(exception_type=type(exc).__name__)
            failure = GenerationError("GroqRequestFailed", full_reply)
            raise failure from None
        except Exception as exc:
            status = "incomplete" if full_reply else "failed"
            category = safe_error_category(exception_type=type(exc).__name__)
            failure = GenerationError("GroqRequestFailed", full_reply)
            raise failure from None
        finally:
            if response is not None:
                try:
                    response.close()
                except Exception:
                    category = category or "stream"
            record = make_usage_record(
                request_id=request_id, attempt=1, operation=operation,
                model_id=self.model_id, region=self.region, status=status,
                stop_reason=stop_reason, metadata={"usage": usage}, rates=None)
            log_event(request_id=request_id, event_type="groq.request", provider="Groq Cloud",
                      model=self.model_id, duration_ms=(time.perf_counter() - started) * 1000,
                      status=status, error_category=category, attempt=1)
            if usage_records is not None:
                usage_records.append(record)
            if metrics_callback:
                try:
                    metrics_callback({"latency_ms": (time.perf_counter() - started) * 1000,
                                      "input_tokens": record.input_tokens,
                                      "output_tokens": record.output_tokens,
                                      "cost_usd": record.cost_usd,
                                      "status": status, "provider": "Groq Cloud",
                                      "model": self.model_id})
                except Exception:
                    pass
            if failure is not None:
                failure.result = GenerationResult(
                    failure.result.text, failure.result.status, failure.result.error_message,
                    failure.result.error_code, failure.result.stop_reason, (record,))
        authorize_bedrock(self._auth_session, online=False)
        history.extend([{"role": "user", "content": blocks},
                        {"role": "assistant", "content": [{"text": full_reply}]}])
        self._last_used_model_id = self.model_id
        return GenerationResult(full_reply, stop_reason=stop_reason, usage_records=(record,))
