"""orchestration / uploads responsibilities extracted from the Streamlit launcher."""
from hashlib import sha256
from uuid import uuid4
from pathlib import Path
from services.document_service import (
    DocumentResult, DocumentValidationError, MAX_DOC_SIZE_BYTES, SUPPORTED_DOC_FORMATS,
)
from services.image_service import (
    ImageResult, ImageValidationError, MAX_IMAGE_SIZE_BYTES, SUPPORTED_IMAGE_FORMATS,
)
from utils.validators import validate_file_upload, sanitize_filename
from novamind.domain.session import _upload_widget_key
from services.auth_service import protect_state, AuthenticationError
from services.authorization import capture_scope, check_scope, publish_data


def _handle_file_upload(state, uploaded_file) -> None:
    scope = capture_scope(state)
    if uploaded_file is None:
        publish_data(state, expected=scope, pending_image=None, pending_document=None,
                     attachment_id=None, upload_identity=None, upload_error=None)
        return

    # Browser/Streamlit file IDs are cache hints only, never ownership IDs.
    file_id = getattr(uploaded_file, "file_id", None)
    identity = ("upload", file_id) if file_id is not None else None
    if identity is not None and identity == state.upload_identity:
        return

    previous_identity = state.upload_identity
    previous_image = state.pending_image
    previous_document = state.pending_document
    previous_error = state.upload_error
    previous_attachment_id = state.attachment_id
    publish_data(state, expected=scope, pending_image=None, pending_document=None,
                 attachment_id=None, upload_identity=identity, upload_error=None)
    try:
        file_name = sanitize_filename(uploaded_file.name)
        uploaded_size = getattr(uploaded_file, "size", None)
        extension = Path(file_name).suffix.lower()
        size_limit = MAX_IMAGE_SIZE_BYTES if extension in SUPPORTED_IMAGE_FORMATS else MAX_DOC_SIZE_BYTES
        if type(uploaded_size) is int and uploaded_size > size_limit:
            publish_data(state, expected=scope,
                         upload_error="File exceeds the allowed size. Upload a smaller file.")
            return
        raw_bytes = uploaded_file.getvalue()
        check_scope(state, scope)
        if identity is None:
            identity = ("content", uploaded_file.name, sha256(raw_bytes).digest())
            publish_data(state, expected=scope, upload_identity=identity)
            if identity == previous_identity:
                publish_data(state, expected=scope, pending_image=previous_image,
                             pending_document=previous_document, upload_error=previous_error,
                             attachment_id=previous_attachment_id)
                return
        result = validate_file_upload(raw_bytes, file_name)
        check_scope(state, scope)
        if isinstance(result, (ImageValidationError, DocumentValidationError)):
            publish_data(state, expected=scope, upload_error=result.error_message)
        elif isinstance(result, ImageResult) and result.is_valid:
            publish_data(state, expected=scope, pending_image=result, attachment_id=uuid4().hex)
        elif isinstance(result, DocumentResult) and result.is_valid:
            publish_data(state, expected=scope, pending_document=result, attachment_id=uuid4().hex)
        else:
            publish_data(state, expected=scope,
                         upload_error="File validation did not succeed. Please upload another file.")
    except AuthenticationError:
        raise
    except Exception:
        publish_data(state, expected=scope,
                     upload_error="Unable to process this upload. Please remove it and upload again.")


def _on_upload_changed(state, widget_key: str) -> None:
    protect_state(state)
    # A callback from a retired widget must not restore a consumed attachment.
    if widget_key == _upload_widget_key(state):
        _handle_file_upload(state, state.get(widget_key))
