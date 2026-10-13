"""
services/bedrock_service.py
────────────────────────────
Central service for all Amazon Bedrock interactions.

Responsibilities:
  - Build well-formed Converse API message payloads for text, image, and document inputs
  - Call Amazon Bedrock via boto3 bedrock-runtime (streaming + non-streaming)
  - Manage conversation history as a plain list of role/content dicts
  - Provide a clean public interface consumed by mod_chatbot_frontend.py
  - No Streamlit imports — this layer is UI-agnostic

Model routing policy (Task 1D):
  - The configured model_id is always used first.
  - A single automatic fallback to an inference profile is attempted ONLY when:
      a) The configured model is the Nova Pro base model ID, AND
      b) The first call returns AccessDeniedException.
  - The fallback is NOT attempted for Nova Lite, Claude, or any other model —
    auto-substituting a different model family would silently change behaviour.
  - The fallback is bounded to exactly one additional attempt (no recursion).
  - Candidate selection is per-call, not persistent.
    Instance state records the last *successfully used* model for observability,
    but it never permanently replaces the user's configured model_id.
  - Fallback is forbidden once output has started.
  - Only completed text responses enter history; GenerationError carries failures
    and partial text separately from yielded model content.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, replace
from uuid import uuid4
from typing import Generator, Literal, Optional

import botocore.exceptions
from services.usage_accounting import MODEL_PRICING, UsageRecord, make_usage_record
from services.request_limits import validate_request, RequestLimitError
from services.aws_config import load_aws_config, bedrock_options, create_aws_client
from services.auth_service import authorize_bedrock, AuthenticationError
from services.observability import log_event, safe_error_category

logger = logging.getLogger(__name__)


def _notify_metrics(callback, values):
    """Observability must never change provider or stream behavior."""
    if callback is not None:
        try:
            callback(values)
        except Exception:
            logger.debug("Metrics display update failed")

# The inference profile for Nova Pro's cross-region routing.
# This is the ONLY approved automatic fallback target.
# It is only attempted when model_id == _NOVA_PRO_BASE_ID.
_NOVA_PRO_BASE_ID        = "amazon.nova-pro-v1:0"
_NOVA_PRO_PROFILE_ID     = "us.amazon.nova-pro-v1:0"

@dataclass(frozen=True)
class GenerationResult:
    """Display outcome. Only completed outcomes belong in model context."""

    text: str
    status: Literal["completed", "failed", "incomplete"] = "completed"
    error_message: str = ""
    error_code: str | None = None
    stop_reason: str | None = None
    usage_records: tuple[UsageRecord, ...] = ()


class GenerationError(Exception):
    """Safe failure contract for streaming and invoke_response callers.

    Already-yielded text is available in result.text; diagnostic strings are
    never yielded as model text. The original exception is chained for debugging.
    """

    def __init__(self, code: str, partial_text: str = "", stop_reason: str | None = None, *, safe_message: str | None = None):
        status = "incomplete" if partial_text else "failed"
        message = (
            "Response incomplete. It was not added to AI context. Please retry."
            if partial_text else
            "Unable to complete the response. It was not added to AI context. Please retry."
        )
        message = safe_message or message
        self.result = GenerationResult(partial_text, status, message, code, stop_reason)
        super().__init__(message)


class BedrockService:
    """
    Manages all communication with Amazon Bedrock's Converse API.

    Usage:
        service = BedrockService()
        history = []

        # Text only
        for chunk in service.stream_response("What is AWS?", history):
            print(chunk, end="", flush=True)

        # With an image
        for chunk in service.stream_response(
            "What is in this image?", history, image_bytes=img_bytes, image_format="jpeg"
        ):
            print(chunk, end="", flush=True)

        # With a PDF document
        for chunk in service.stream_response(
            "Summarise this document.", history, doc_bytes=pdf_bytes, doc_name="report"
        ):
            print(chunk, end="", flush=True)
    """

    def __init__(
        self,
        region: Optional[str] = None,
        model_id: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        system_prompt: Optional[str] = None,
        auth_session=None,
    ):
        authorize_bedrock(auth_session)
        self._auth_session = auth_session
        config = load_aws_config(region=region)
        options = bedrock_options(model_id=model_id, max_tokens=max_tokens,
                                  temperature=temperature, system_prompt=system_prompt)
        self.region = config.region
        self.model_id = options["model_id"]
        self.max_tokens = options["max_tokens"]
        self.temperature = options["temperature"]
        self.system_prompt = options["system_prompt"]
        self._client = create_aws_client("bedrock-runtime", config=config)

        # Records the model ID actually used on the most recent successful call.
        # Read-only for observability (get_model_info).  Never used to route calls.
        self._last_used_model_id: Optional[str] = None

    # ── Public API ─────────────────────────────────────────────────────────────

    def stream_response(
        self,
        user_text: str,
        history: list[dict],
        *,
        image_bytes:  Optional[bytes] = None,
        image_format: Optional[str]   = None,   # "jpeg" | "png" | "gif" | "webp"
        doc_bytes:    Optional[bytes] = None,
        doc_name:     Optional[str]   = None,
        doc_format:   Optional[str]   = "pdf",  # "pdf" | "txt" | "html" | "md" | "csv"
        operation: Literal["chat", "summary"] = "chat",
        usage_records: list[UsageRecord] | None = None,
        authorization_check=None,
        metrics_callback=None,
    ) -> Generator[str, None, GenerationResult]:
        """Yield model text, then commit a completed user/assistant pair.

        Raises GenerationError for failed or incomplete generations. History
        stays unchanged on failure or consumer cancellation. Call close() on
        this generator when abandoning it so the underlying stream is released.
        Task 1D routing remains bounded, and never retries after output starts.
        Each attempted invocation appends a frozen accounting record to the
        optional usage_records sink, even on cancellation. No shared last-result
        state is used. Generator return / GenerationError also carry the records.
        """
        authorize_bedrock(self._auth_session)
        if authorization_check is not None:
            authorization_check()
        if operation not in {"chat", "summary"}:
            raise ValueError("Unsupported operation")
        request_id = str(uuid4())
        records: list[UsageRecord] = []
        if (not isinstance(history, list) or not isinstance(user_text, str)
                or not user_text.strip()
                or (image_bytes is not None and (not isinstance(image_bytes, bytes) or not image_bytes or not isinstance(image_format, str)))
                or (image_format is not None and image_bytes is None)
                or (doc_bytes is not None and (not isinstance(doc_bytes, bytes) or not doc_bytes))
                or (doc_format is not None and not isinstance(doc_format, str))
                or (doc_name is not None and not isinstance(doc_name, str))):
            raise GenerationError("RequestStructure", safe_message="Enter a nonblank message and provide complete attachment data. Conversation history was not changed.")
        content_blocks = self._build_content_blocks(
            user_text, image_bytes, image_format, doc_bytes, doc_name, doc_format
        )
        messages_for_api = history + [{"role": "user", "content": content_blocks}]
        candidates = self._build_candidate_list()
        try:
            # Validate every possible route before any invocation; never trim history.
            for candidate in candidates:
                validate_request(candidate, self.system_prompt, self.max_tokens,
                                 self.temperature, messages_for_api)
        except RequestLimitError as exc:
            raise GenerationError(exc.code, safe_message=str(exc)) from exc
        except (TypeError, ValueError, OverflowError) as exc:
            raise GenerationError("RequestStructure", safe_message="Request content cannot be encoded safely. Conversation history was not changed.") from exc
        stream_error_events = {
            "internalServerException", "modelStreamErrorException",
            "validationException", "throttlingException", "serviceUnavailableException",
        }

        for attempt, model_id_to_try in enumerate(candidates):
            if authorization_check is not None:
                authorization_check()
            # Recheck before every invocation, including the bounded fallback.
            authorize_bedrock(self._auth_session)
            if authorization_check is not None:
                authorization_check()
            full_reply = ""
            output_started = False
            stop_reason = None
            stopped = False
            stream = None
            metadata = {}
            metadata_seen = False
            outcome = "incomplete"
            failure = None
            error_category = None
            # Snapshot pricing before invoking; later configuration edits cannot
            # reprice this attempt or earlier requests.
            invocation_region = self.region
            attempt_started = time.perf_counter()
            first_token_ms = None
            log_event(request_id=request_id, event_type="bedrock.request", provider="Amazon Bedrock",
                      model=model_id_to_try, duration_ms=0, status="generating", attempt=attempt + 1)
            _notify_metrics(metrics_callback, {"provider": "Amazon Bedrock", "model": model_id_to_try,
                                               "region": invocation_region, "status": "generating"})
            rates = MODEL_PRICING.get((invocation_region, model_id_to_try))
            payload = {
                "modelId": model_id_to_try,
                "messages": messages_for_api,
                "system": [{"text": self.system_prompt}],
                "inferenceConfig": {
                    "maxTokens": self.max_tokens,
                    "temperature": self.temperature,
                },
            }
            try:
                response = self._client.converse_stream(**payload)
                stream = response["stream"]
                for event in stream:
                    if authorization_check is not None:
                        authorization_check()
                    # No network per chunk; expiration/logout still stops output.
                    authorize_bedrock(self._auth_session, online=False)
                    event_error = next((key for key in stream_error_events if key in event), None)
                    if event_error:
                        raise GenerationError(event_error, full_reply, stop_reason)
                    if "contentBlockStart" in event or "contentBlockDelta" in event:
                        if stopped:
                            raise GenerationError("InvalidStreamSequence", full_reply, stop_reason)
                        output_started = True
                    if "contentBlockDelta" in event:
                        delta = event["contentBlockDelta"]["delta"]
                        # This application supports text answers, not tool execution
                        # or reasoning/signature blocks that would require full replay.
                        if "text" not in delta:
                            raise GenerationError("UnsupportedOutput", full_reply)
                        chunk = delta["text"]
                        if not isinstance(chunk, str):
                            raise GenerationError("InvalidTextDelta", full_reply)
                        if chunk:
                            full_reply += chunk
                            if first_token_ms is None:
                                first_token_ms = (time.perf_counter() - attempt_started) * 1000
                            _notify_metrics(metrics_callback, {
                                "latency_ms": (time.perf_counter() - attempt_started) * 1000,
                                "time_to_first_token_ms": first_token_ms})
                            yield chunk
                    elif "messageStop" in event:
                        if stopped:
                            raise GenerationError("InvalidStreamSequence", full_reply, stop_reason)
                        stopped = True
                        stop_reason = event["messageStop"].get("stopReason")
                    elif "metadata" in event:
                        # Metadata is a final snapshot, never an additive delta.
                        # Duplicate snapshots are ambiguous: retain text outcome
                        # but mark usage unknown instead of double counting.
                        metadata = event["metadata"] if not metadata_seen else {}
                        metadata_seen = True

                if not stopped:
                    raise GenerationError("UnexpectedStreamEnd", full_reply)
                if stop_reason not in {"end_turn", "stop_sequence"}:
                    raise GenerationError("UnsuccessfulStop", full_reply, stop_reason)
                if not full_reply.strip():
                    raise GenerationError("EmptyResponse", full_reply, stop_reason)
                authorize_bedrock(self._auth_session, online=False)
                if authorization_check is not None:
                    authorization_check()
                outcome = "completed"
            except AuthenticationError as exc:
                outcome = "failed"
                error_category = safe_error_category(exception_type=type(exc).__name__)
                raise
            except GenerationError as exc:
                failure = exc
                outcome = exc.result.status
                error_category = safe_error_category(code=exc.result.error_code)
                raise
            except botocore.exceptions.ClientError as exc:
                code = exc.response.get("Error", {}).get("Code", "BedrockError")
                if (code == "AccessDeniedException" and attempt == 0
                        and len(candidates) > 1 and not output_started and not stopped):
                    outcome = "failed"
                    error_category = safe_error_category(code=code)
                    log_event(request_id=request_id, event_type="bedrock.fallback", provider="Amazon Bedrock",
                              model=model_id_to_try, duration_ms=(time.perf_counter() - attempt_started) * 1000,
                              status="retrying", error_category=error_category, attempt=attempt + 1)
                    continue
                error_category = safe_error_category(code=code)
                failure = GenerationError(code, full_reply, stop_reason)
                outcome = failure.result.status
                raise failure from exc
            except Exception as exc:
                error_category = safe_error_category(exception_type=type(exc).__name__)
                failure = GenerationError("UnexpectedError", full_reply, stop_reason)
                outcome = failure.result.status
                raise failure from exc
            finally:
                # Also executes on GeneratorExit/Streamlit cancellation. Never close
                # the shared boto3 client, and never mask the primary outcome.
                close = getattr(stream, "close", None)
                if callable(close):
                    try:
                        close()
                    except Exception:
                        log_event(request_id=request_id, event_type="bedrock.stream_cleanup",
                                  provider="Amazon Bedrock", model=model_id_to_try,
                                  duration_ms=(time.perf_counter() - attempt_started) * 1000,
                                  status="warning", error_category="stream", attempt=attempt + 1)
                record = make_usage_record(
                    request_id=request_id, attempt=attempt + 1, operation=operation,
                    model_id=model_id_to_try, region=invocation_region, status=outcome,
                    stop_reason=stop_reason, metadata=metadata, rates=rates,
                )
                records.append(record)
                log_event(request_id=request_id, event_type="bedrock.request", provider="Amazon Bedrock",
                          model=model_id_to_try,
                          duration_ms=(time.perf_counter() - attempt_started) * 1000,
                          status=outcome, error_category=error_category, attempt=attempt + 1)
                _notify_metrics(metrics_callback, {
                    "latency_ms": (time.perf_counter() - attempt_started) * 1000,
                    "time_to_first_token_ms": first_token_ms,
                    "input_tokens": record.input_tokens,
                    "output_tokens": record.output_tokens,
                    "cost_usd": record.cost_usd,
                    "status": outcome, "model": model_id_to_try,
                    "provider": "Amazon Bedrock"})
                if usage_records is not None:
                    usage_records.append(record)
                if failure is not None:
                    failure.result = replace(failure.result, usage_records=tuple(records))

            # Stream cleanup can block; recheck before committing caller history.
            authorize_bedrock(self._auth_session, online=False)
            if authorization_check is not None:
                authorization_check()
            self._last_used_model_id = model_id_to_try
            history.extend([
                {"role": "user", "content": content_blocks},
                {"role": "assistant", "content": [{"text": full_reply}]},
            ])
            return GenerationResult(full_reply, stop_reason=stop_reason, usage_records=tuple(records))

    def invoke_response(
        self,
        user_text: str,
        history: list[dict],
        *,
        image_bytes:  Optional[bytes] = None,
        image_format: Optional[str]   = None,
        doc_bytes:    Optional[bytes] = None,
        doc_name:     Optional[str]   = None,
        doc_format:   Optional[str]   = "pdf",
        operation: Literal["chat", "summary"] = "chat",
        usage_records: list[UsageRecord] | None = None,
        authorization_check=None,
        metrics_callback=None,
    ) -> str:
        """
        Non-streaming version of stream_response.
        Returns the full reply as a single string; raises GenerationError on failure.
        Useful for simple tests or non-UI contexts.
        """
        return "".join(
            self.stream_response(
                user_text, history,
                image_bytes=image_bytes, image_format=image_format,
                doc_bytes=doc_bytes, doc_name=doc_name, doc_format=doc_format,
                operation=operation, usage_records=usage_records,
                authorization_check=authorization_check,
                metrics_callback=metrics_callback,
            )
        )

    def clear_history(self, history: list[dict]) -> None:
        """Clear all turns from the provided history list."""
        history.clear()

    def get_model_info(self) -> dict:
        """Return a dict with the current model configuration."""
        return {
            "model_id":       self.model_id,              # user's configured choice — never changes
            "last_used_model": self._last_used_model_id,  # actual model used on last call
            "region":         self.region,
            "max_tokens":     self.max_tokens,
            "temperature":    self.temperature,
            "streaming":      True,
        }

    # ── Private helpers ────────────────────────────────────────────────────────

    def _build_candidate_list(self) -> list[str]:
        """
        Return the ordered list of model IDs to attempt for a single request.

        Policy:
          - Always start with self.model_id (user's configured choice).
          - Append the Nova Pro cross-region inference profile as a single
            fallback IF AND ONLY IF the configured model is the Nova Pro base
            model ID.  No other automatic fallback is defined.
          - Result is always 1 or 2 items — never more.
        """
        if self.model_id == _NOVA_PRO_BASE_ID:
            return [_NOVA_PRO_BASE_ID, _NOVA_PRO_PROFILE_ID]
        # For Nova Lite, Claude, or any custom model — no automatic fallback.
        return [self.model_id]

    def _build_content_blocks(
        self,
        user_text:    str,
        image_bytes:  Optional[bytes],
        image_format: Optional[str],
        doc_bytes:    Optional[bytes],
        doc_name:     Optional[str],
        doc_format:   Optional[str],
    ) -> list[dict]:
        """
        Build the Converse API content blocks list for a user turn.

        Converse API format:
          [
            { "image": { "format": "jpeg", "source": { "bytes": <bytes> } } },
            { "document": { "format": "pdf", "name": "myfile", "source": { "bytes": <bytes> } } },
            { "text": "user question here" }
          ]

        Text block always goes last — this is the recommended ordering for
        multimodal prompts with Nova models.
        """
        blocks: list[dict] = []

        # Image block
        if image_bytes and image_format:
            fmt = image_format.lower().lstrip(".")
            # Nova Pro supports: jpeg, png, gif, webp
            if fmt == "jpg":
                fmt = "jpeg"
            blocks.append({
                "image": {
                    "format": fmt,
                    "source": {"bytes": image_bytes},
                }
            })

        # Document block
        if doc_bytes:
            # doc_name must comply with Bedrock DocumentBlock.name constraints:
            #   - Alphanumeric, single spaces, hyphens, parentheses, square brackets
            #   - Length 1–200 characters
            #   - AWS recommends a neutral name to avoid prompt injection
            # The caller (frontend) now passes doc_result.api_name which is always
            # a neutral "Document N" string, but we sanitise defensively here too.
            import re as _re
            _disallowed = _re.compile(r"[^a-zA-Z0-9 \-()\[\]]")
            raw_name = (doc_name or "Document").strip()
            cleaned  = _disallowed.sub(" ", raw_name)
            # Collapse multiple spaces to one (API allows single spaces only)
            cleaned  = _re.sub(r" {2,}", " ", cleaned).strip()
            name     = cleaned[:200] or "Document"
            fmt  = (doc_format or "pdf").lower().lstrip(".")
            # Nova Pro document formats: pdf, csv, doc, docx, xls, xlsx, html, txt, md
            blocks.append({
                "document": {
                    "format": fmt,
                    "name":   name,
                    "source": {"bytes": doc_bytes},
                }
            })

        # Text block (always last)
        if user_text and user_text.strip():
            blocks.append({"text": user_text.strip()})

        return blocks

    def update_settings(
        self,
        temperature:   Optional[float] = None,
        max_tokens:    Optional[int]   = None,
        system_prompt: Optional[str]   = None,
    ) -> None:
        """Dynamically update inference settings without rebuilding the client."""
        if temperature   is not None: self.temperature   = temperature
        if max_tokens    is not None: self.max_tokens    = max_tokens
        if system_prompt is not None: self.system_prompt = system_prompt


# ── Module-level convenience factory ─────────────────────────────────────────

def get_bedrock_service(
    region:        Optional[str] = None,
    model_id:      Optional[str] = None,
    max_tokens:    Optional[int]  = None,
    temperature:   Optional[float] = None,
    system_prompt: Optional[str]  = None,
    auth_session=None,
) -> BedrockService:
    """
    Factory function — returns a BedrockService instance.
    The frontend calls this once at startup and caches it in session_state.
    """
    return BedrockService(
        region=region,
        model_id=model_id,
        max_tokens=max_tokens,
        temperature=temperature,
        system_prompt=system_prompt,
        auth_session=auth_session,
    )
