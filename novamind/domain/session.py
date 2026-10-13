"""domain / session responsibilities extracted from the Streamlit launcher."""
from services.auth_service import protect_state
from services.authorization import capture_scope, publish_data, rotate_conversation
from datetime import datetime
from services.aws_config import bedrock_options, AWSConfigurationError
from novamind.config.settings import MODEL_OPTIONS, DEFAULT_PROVIDER
from services.provider_config import groq_model


def _init_session_state(state) -> None:
    """Initialise state from shared defaults; subsequent UI choices take precedence."""
    protect_state(state)
    defaults = bedrock_options() if any(key not in state for key in (
        "selected_model_label", "temperature", "max_tokens", "system_prompt")) else {}
    for key, value in (("bedrock_history", []), ("chat_history", []),
                       ("bedrock_service", None), ("pending_image", None),
                       ("pending_document", None), ("attachment_id", None)):
        if key not in state:
            publish_data(state, **{key: value})
    if "upload_generation" not in state:
        publish_data(state, upload_generation=0, upload_identity=None, upload_error=None)
        # Old pending values have no corresponding keyed widget selection.
        publish_data(state, pending_image=None, pending_document=None, attachment_id=None)
    if "conversation_count"   not in state: state.conversation_count   = 0
    if "persistence_version" not in state:
        publish_data(state, persistence_version=0)
    if "ai_metrics" not in state:
        publish_data(state, ai_metrics=None)

    # Model / inference settings
    if "selected_model_label" not in state:
        default_model_id = groq_model() if DEFAULT_PROVIDER == "groq" else defaults["model_id"]
        if default_model_id not in MODEL_OPTIONS.values():
            raise AWSConfigurationError("Configured AI model is not available in the model selector.")
        state.selected_model_label = next(
            (label for label, model in MODEL_OPTIONS.items() if model == default_model_id),
            "Amazon Nova Pro  (Recommended)" if DEFAULT_PROVIDER == "bedrock" else next(
                label for label, model in MODEL_OPTIONS.items() if model == groq_model()),
        )
    if "temperature"          not in state: state.temperature   = defaults["temperature"]
    if "max_tokens"           not in state: state.max_tokens    = defaults["max_tokens"]
    if "selected_template"    not in state:
        state.selected_template = "🤖 Default Assistant"
    if "system_prompt"        not in state:
        state.system_prompt = defaults["system_prompt"]
    if "selected_language"    not in state:
        state.selected_language = "English"

    # Replace historical character estimates with a request ledger.
    if "usage_ledger" not in state:
        publish_data(state, usage_ledger=[])
        if (state.chat_history or state.bedrock_history
                or state.get("total_input_tokens", 0)
                or state.get("total_output_tokens", 0)):
            state.usage_ledger.append({
                "timestamp": datetime.now().isoformat(timespec="seconds"),
                "operation": "legacy history", "status": "unknown", "attempts": (),
            })
        state.total_input_tokens = 0
        state.total_output_tokens = 0
    # Known token subtotals only.
    if "total_input_tokens"   not in state: state.total_input_tokens  = 0
    if "total_output_tokens"  not in state: state.total_output_tokens = 0

    # UI
    if "bot_name"             not in state: state.bot_name = "NovaMind"
    if "aws_status" not in state: publish_data(state, aws_status=None)


def _upload_widget_key(state) -> str:
    scope = capture_scope(state)
    return f"attachment_upload_{scope.conversation_id}_{state.upload_generation}"


def _reset_attachment(state, attachment_id=None) -> None:
    """Clear the selection and create an empty uploader on the next rerun.

    File-uploader values are read-only. Rotate its key instead of assigning a
    value to an already instantiated widget.
    """
    protect_state(state)
    if attachment_id is not None:
        from services.authorization import attachment_snapshot
        attachment_snapshot(state, attachment_id)
    publish_data(state, pending_image=None, pending_document=None, attachment_id=None,
                 upload_identity=None, upload_error=None,
                 upload_generation=state.upload_generation + 1)


def _clear_conversation(state, conversation_id=None) -> None:
    capture_scope(state, conversation_id)
    publish_data(state, bedrock_history=[], chat_history=[])
    _reset_attachment(state)
    publish_data(state, usage_ledger=[], bedrock_service=None, aws_status=None)
    publish_data(state, persistence_version=0)
    publish_data(state, ai_metrics=None)
    state.total_input_tokens   = 0
    state.total_output_tokens  = 0
    rotate_conversation(state)
    capture_scope(state).values.pop("_saved_signature", None)
    state["_trigger_summary"] = False
