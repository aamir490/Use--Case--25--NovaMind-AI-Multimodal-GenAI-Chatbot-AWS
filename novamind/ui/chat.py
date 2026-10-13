"""ui / chat responsibilities extracted from the Streamlit launcher."""
import html as _html
from contextlib import closing
from dataclasses import replace
from datetime import datetime
import time
from copy import deepcopy
import streamlit as st
from services.bedrock_service import BedrockService, GenerationError, GenerationResult
from services.document_service import DocumentResult
from services.image_service import ImageResult
from utils.validators import sanitize_user_input
from novamind.ui.state import _get_or_create_service, _record_usage, _reset_attachment
from services.auth_service import protect_state, AuthenticationError
from services.aws_config import AWSConfigurationError
from novamind.ui.private_media import render_private_thumbnail
from services.authorization import capture_scope, check_scope, capture_attachments, publish_data, AuthorizationError
from services.conversation_memory import request_history, single_turn, MAX_DISPLAY_MESSAGES
from services.request_limits import RequestLimitError
from novamind.ui.live_metrics import _markup as _metrics_markup
from novamind.domain.usage import _session_cost
from novamind.config.settings import MODEL_OPTIONS, MODEL_PROVIDERS


def _render_chat_history() -> None:
    protect_state(st.session_state)
    for msg in st.session_state.chat_history:
        role      = msg["role"]
        text      = msg.get("text", "")
        msg_type  = msg.get("type", "text")
        file_name = msg.get("file_name", "")
        avatar    = "🧑" if role == "user" else "🤖"

        with st.chat_message(role, avatar=avatar):
            if msg_type == "image" and file_name:
                st.markdown(
                    f'<div class="nm-attachment">'
                    f'🖼️ <span class="nm-badge-image">IMAGE</span> {_html.escape(file_name)}'
                    f'</div>',
                    unsafe_allow_html=True,
                )
                if msg.get("thumbnail_bytes"):
                    render_private_thumbnail(msg["thumbnail_bytes"])
            elif msg_type == "document" and file_name:
                st.markdown(
                    f'<div class="nm-attachment">'
                    f'📄 <span class="nm-badge-document">DOCUMENT</span> {_html.escape(file_name)}'
                    f'</div>',
                    unsafe_allow_html=True,
                )
            if text:
                st.markdown(text)
            if role == "assistant" and msg.get("status", "completed") != "completed":
                st.warning(msg.get("error_message") or "Response incomplete; excluded from AI context.")


def _stream_and_display_response(
    user_text:    str,
    service:      BedrockService | None,
    image_result: ImageResult | None,
    doc_result:   DocumentResult | None,
    *,
    history: list[dict] | None = None,
    operation: str = "chat",
    expected_scope=None,
    attachment_selection=None,
) -> GenerationResult:
    """Display partial output separately from failure status; commit only success."""
    scope = capture_scope(st.session_state) if expected_scope is None else check_scope(st.session_state, expected_scope)
    auth_failed = False
    target_history = st.session_state.bedrock_history if history is None else history
    if target_history is not st.session_state.bedrock_history:
        raise AuthorizationError("This resource is not available to this session.")
    if image_result is not None or doc_result is not None:
        if (attachment_selection is None or attachment_selection.scope is not scope
                or attachment_selection.image is not image_result
                or attachment_selection.document is not doc_result):
            raise AuthorizationError("This resource is not available to this session.")
    original_history = deepcopy(target_history)
    working_history = deepcopy(target_history)
    full_response = ""
    records = []
    result = GenerationError("Interrupted").result

    with st.chat_message("assistant", avatar="🤖"):
        placeholder = st.empty()
        metrics_placeholder = st.empty()
        kwargs: dict = {}
        if image_result:
            kwargs["image_bytes"] = image_result.raw_bytes
            kwargs["image_format"] = image_result.img_format
        if doc_result:
            kwargs["doc_bytes"] = doc_result.raw_bytes
            kwargs["doc_name"] = doc_result.api_name
            kwargs["doc_format"] = doc_result.doc_format

        try:
            request_started = time.perf_counter()
            publish_data(st.session_state, expected=scope, ai_metrics={
                "provider": ("Groq Cloud" if MODEL_PROVIDERS[MODEL_OPTIONS[st.session_state.selected_model_label]] == "groq"
                             else "Amazon Bedrock"),
                "model": MODEL_OPTIONS[st.session_state.selected_model_label],
                "status": "generating", "latency_ms": None,
                "time_to_first_token_ms": None, "input_tokens": None,
                "output_tokens": None, "tokens_per_second": None, "cost_usd": None,
            })

            def update_metrics(values):
                check_scope(st.session_state, scope)
                updated = dict(st.session_state.ai_metrics or {})
                updated.update(values)
                elapsed = updated.get("latency_ms")
                first = updated.get("time_to_first_token_ms")
                output = updated.get("output_tokens")
                generation_seconds = ((elapsed - first) / 1000
                                      if elapsed is not None and first is not None else 0)
                updated["tokens_per_second"] = (
                    output / generation_seconds if output is not None and generation_seconds > 0 else None)
                publish_data(st.session_state, expected=scope, ai_metrics=updated)

            service = service or _get_or_create_service()
            if service._auth_session is not scope.session:
                raise AuthorizationError("This resource is not available to this session.")
            content = service._build_content_blocks(
                user_text, kwargs.get("image_bytes"), kwargs.get("image_format"),
                kwargs.get("doc_bytes"), kwargs.get("doc_name"), kwargs.get("doc_format", "pdf"))
            try:
                working_history = request_history(service, working_history, content)
            except RequestLimitError as exc:
                raise GenerationError(exc.code, safe_message=str(exc)) from exc
            if len(working_history) < len(original_history):
                st.caption("Using recent completed turns to stay within the context budget. Older turns will leave AI memory after a successful response.")
            # Closing protects the SDK stream even if rendering fails or Streamlit
            # interrupts execution. The working copy prevents premature commits.
            with closing(service.stream_response(
                user_text=user_text, history=working_history,
                operation=operation, usage_records=records, **kwargs,
                authorization_check=lambda: check_scope(st.session_state, scope),
                metrics_callback=update_metrics,
            )) as chunks:
                for chunk in chunks:
                    check_scope(st.session_state, scope)
                    full_response += chunk
                    placeholder.markdown(full_response + "▌")
                    current_metrics = dict(st.session_state.ai_metrics or {})
                    if current_metrics.get("time_to_first_token_ms") is None:
                        current_metrics["time_to_first_token_ms"] = (time.perf_counter() - request_started) * 1000
                    current_metrics["latency_ms"] = (time.perf_counter() - request_started) * 1000
                    update_metrics(current_metrics)
                    metrics_placeholder.markdown(
                        _metrics_markup(st.session_state.ai_metrics or {}, _session_cost(st.session_state)),
                        unsafe_allow_html=True)
            check_scope(st.session_state, scope)
            placeholder.markdown(full_response)
            result = GenerationResult(full_response, stop_reason=records[-1].stop_reason if records else None)
        except (AuthenticationError, AWSConfigurationError):
            auth_failed = True
            placeholder.empty()
            raise
        except GenerationError as exc:
            check_scope(st.session_state, scope)
            result = exc.result
            placeholder.markdown(result.text)
            st.warning(result.error_message)
        except Exception:
            check_scope(st.session_state, scope)
            result = GenerationError("UnexpectedError", full_response).result
            placeholder.markdown(result.text)
            st.warning(result.error_message)
        except BaseException:
            result = replace(GenerationError("Interrupted", full_response).result, status="incomplete")
            raise
        finally:
            # Closing the generator finalizes accounting even on UI interruption.
            result = replace(result, usage_records=tuple(records),
                             stop_reason=records[-1].stop_reason if records else result.stop_reason)
            # Locally rejected requests made no invocation and incurred no model usage.
            if not auth_failed and (records or not (result.error_code or "").startswith("Request")):
                check_scope(st.session_state, scope)
                _record_usage(records, result.status, operation)
            if not auth_failed and "request_started" in locals():
                try:
                    check_scope(st.session_state, scope)
                    final_metrics = dict(st.session_state.ai_metrics or {})
                    final_metrics.update({
                        "status": result.status if result.status in {"completed", "generating", "idle", "incomplete"} else "failed",
                        "latency_ms": (time.perf_counter() - request_started) * 1000,
                        "input_tokens": records[-1].input_tokens if records else None,
                        "output_tokens": records[-1].output_tokens if records else None,
                        "cost_usd": records[-1].cost_usd if records else None,
                    })
                    elapsed = final_metrics["latency_ms"]
                    first = final_metrics.get("time_to_first_token_ms")
                    output = final_metrics["output_tokens"]
                    final_metrics["tokens_per_second"] = (
                        output / ((elapsed - first) / 1000)
                        if output is not None and first is not None and elapsed > first else None)
                    publish_data(st.session_state, expected=scope, ai_metrics=final_metrics)
                except AuthenticationError:
                    pass

    if result.status == "completed":
        check_scope(st.session_state, scope)
        if target_history != original_history:
            raise AuthorizationError("Conversation changed during this request. Please retry.")
        target_history[:] = working_history

    return result


@single_turn
def _handle_user_input(user_input: str) -> bool:
    """Submit a nonblank prompt; False keeps validation feedback on screen."""
    scope = capture_scope(st.session_state)
    user_text    = sanitize_user_input(user_input)
    if not user_text:
        st.warning("Please enter a message before sending.")
        return False
    selection = capture_attachments(st.session_state)
    image_result = selection.image
    doc_result   = selection.document

    # Consume the selection before rendering/invocation, including failed sends.
    _reset_attachment()

    # Display user message
    with st.chat_message("user", avatar="🧑"):
        if image_result:
            st.markdown(
                f'<div class="nm-attachment">'
                f'🖼️ <span class="nm-badge-image">IMAGE</span> {_html.escape(image_result.file_name)}'
                f'</div>',
                unsafe_allow_html=True,
            )
            if image_result.thumbnail_bytes:
                render_private_thumbnail(image_result.thumbnail_bytes)
        elif doc_result:
            st.markdown(
                f'<div class="nm-attachment">'
                f'📄 <span class="nm-badge-document">DOCUMENT</span> {_html.escape(doc_result.file_name)}'
                f'</div>',
                unsafe_allow_html=True,
            )
        st.markdown(user_text)

    # Save user turn
    user_msg: dict = {
        "role":      "user",
        "text":      user_text,
        "timestamp": datetime.now().strftime("%H:%M"),
        "avatar":    "🧑",
    }
    if image_result:
        user_msg["type"]            = "image"
        user_msg["file_name"]       = image_result.file_name
        user_msg["thumbnail_bytes"] = image_result.thumbnail_bytes
    elif doc_result:
        user_msg["type"]      = "document"
        user_msg["file_name"] = doc_result.file_name
    else:
        user_msg["type"] = "text"
    check_scope(st.session_state, scope)
    st.session_state.chat_history.append(user_msg)

    # Stream AI response
    result = _stream_and_display_response(
        user_text=user_text,
        service=None,
        image_result=image_result,
        doc_result=doc_result,
        expected_scope=scope,
        attachment_selection=selection,
    )

    check_scope(st.session_state, scope)
    user_msg["status"] = result.status
    # Display history can include failed/incomplete output; model history cannot.
    st.session_state.chat_history.append({
        "role":      "assistant",
        "text":      result.text,
        "status":    result.status,
        "error_message": result.error_message,
        "error_code": result.error_code,
        "stop_reason": result.stop_reason,
        "usage_records": result.usage_records,
        "type":      "text",
        "timestamp": datetime.now().strftime("%H:%M"),
        "avatar":    "🤖",
    })
    del st.session_state.chat_history[:-MAX_DISPLAY_MESSAGES]
    return True


@single_turn
def _handle_summary() -> None:
    """Ask the model to summarise the current conversation."""
    scope = capture_scope(st.session_state)
    if not st.session_state.bedrock_history:
        st.info("There are no completed turns to summarise yet.")
        return

    summary_prompt = (
        "Please provide a concise summary of our conversation so far. "
        "Format as:\n"
        "**Main topics discussed:**\n- ...\n\n"
        "**Key points and answers:**\n- ...\n\n"
        "**Action items / follow-ups (if any):**\n- ..."
    )

    with st.chat_message("user", avatar="🧑"):
        st.markdown("📝 *Conversation summary requested*")

    check_scope(st.session_state, scope)
    st.session_state.chat_history.append({
        "role":      "user",
        "text":      "📝 *Conversation summary requested*",
        "type":      "text",
        "timestamp": datetime.now().strftime("%H:%M"),
        "avatar":    "🧑",
    })

    # Reuse the same transactional rendering path as ordinary chat.
    result = _stream_and_display_response(
        user_text=summary_prompt, service=None,
        image_result=None, doc_result=None, operation="summary",
        expected_scope=scope,
    )

    check_scope(st.session_state, scope)
    st.session_state.chat_history[-1]["status"] = result.status

    st.session_state.chat_history.append({
        "role":      "assistant",
        "text":      result.text,
        "status":    result.status,
        "error_message": result.error_message,
        "error_code": result.error_code,
        "stop_reason": result.stop_reason,
        "usage_records": result.usage_records,
        "type":      "text",
        "timestamp": datetime.now().strftime("%H:%M"),
        "avatar":    "🤖",
    })
    del st.session_state.chat_history[:-MAX_DISPLAY_MESSAGES]


def _render_welcome() -> None:
    st.markdown(
        '<div class="nm-welcome"><h2>What would you like to explore?</h2>'
        '<p>Start a conversation, upload an image or bring a document.</p></div>',
        unsafe_allow_html=True,
    )

    col1, col2, col3 = st.columns(3)
    cards = [
        ("💬", "#58a6ff", "Text Chat",
         "Multi-turn conversations with bounded recent context memory. "
         "Follow-up questions, reasoning, and explanations."),
        ("🖼️", "#3fb950", "Image Analysis",
         "Upload JPEG, PNG, GIF, or WebP. "
         "Ask questions, extract text, describe scenes."),
        ("📄", "#d29922", "Document Q&A",
         "Upload PDF, DOCX, CSV, TXT and more. "
         "Summarise, extract data, ask specific questions."),
    ]
    for col, (icon, color, title, desc) in zip([col1, col2, col3], cards):
        with col:
            st.markdown(
                f'<div class="nm-feat-card">'
                f'<div class="nm-feat-icon">{icon}</div>'
                f'<div class="nm-feat-title">{title}</div>'
                f'<div class="nm-feat-desc">{desc}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

    st.markdown(
        '<div class="nm-welcome-meta">'
        'Powered by Amazon Bedrock &nbsp;·&nbsp; '
        '3 AI models &nbsp;·&nbsp; 8 languages'
        '</div>',
        unsafe_allow_html=True,
    )

    st.markdown("<div style='height:1rem'></div>", unsafe_allow_html=True)
    st.markdown(
        '<p class="nm-suggestions-label">Try a starting point</p>',
        unsafe_allow_html=True,
    )
    suggestions = [
        "What is Amazon Bedrock and how does it work?",
        "Explain the difference between RAG and fine-tuning.",
        "What AWS services would you use for a serverless AI app?",
    ]
    cols = st.columns(len(suggestions))
    for col, suggestion in zip(cols, suggestions):
        with col:
            if st.button(suggestion, width="stretch"):
                _handle_user_input(suggestion)
                st.rerun()
