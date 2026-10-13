"""Bind explicit-state functions to the current Streamlit session."""
import streamlit as st
from novamind.domain import session, usage
from novamind.orchestration import bedrock, uploads
from services.auth_service import load_auth_config, require_session, AuthenticationError, clear_session
from services.aws_config import AWSConfigurationError
from services.authorization import AuthorizationError


def _init_session_state():
    return session._init_session_state(st.session_state)


def _upload_widget_key():
    return session._upload_widget_key(st.session_state)


def _reset_attachment():
    return session._reset_attachment(st.session_state)


def _clear_conversation():
    return session._clear_conversation(st.session_state)


def _record_usage(records, status: str, operation: str):
    return usage._record_usage(st.session_state, records, status, operation)


def _usage_totals():
    return usage._usage_totals(st.session_state)


def _session_cost():
    return usage._session_cost(st.session_state)


def _get_or_create_service():
    return bedrock._get_or_create_service(st.session_state)


def _model_context_warning(model_id: str):
    return bedrock._model_context_warning(st.session_state, model_id)


def _update_service_settings():
    return bedrock._update_service_settings(st.session_state)


def _check_aws_connection(*, live: bool = False):
    return bedrock._check_aws_connection(st.session_state, live=live)


def _handle_file_upload(uploaded_file):
    return uploads._handle_file_upload(st.session_state, uploaded_file)


def _on_upload_changed(widget_key: str):
    # Streamlit callbacks run before main's authentication gate.
    try:
        if load_auth_config().mode == "cognito":
            require_session(st.session_state)
        return uploads._on_upload_changed(st.session_state, widget_key)
    except AuthorizationError:
        # Ignore stale work without deleting a newer valid user's data.
        return
    except (AuthenticationError, AWSConfigurationError) as exc:
        clear_session(st.session_state)
        st.session_state["auth_notice"] = str(exc)
        return
