#!/usr/bin/env python3
"""Offline by default. Live checks require explicit flags; importing does no work."""
import argparse
import importlib.util
import io
import sys
from contextlib import closing
from pathlib import Path


def build_attachments():
    """Generate valid, in-memory fixtures; never send local user files."""
    from PIL import Image
    from pypdf import PdfWriter
    png = io.BytesIO()
    with Image.new("RGB", (16, 16), "red") as image:
        image.save(png, format="PNG")
    pdf = io.BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    writer.write(pdf)
    writer.close()
    return png.getvalue(), pdf.getvalue()


def run_live_checks(config, model_id, *, inference=False, auth_session=None):
    from services.aws_config import create_aws_client
    with closing(create_aws_client("sts", config=config)) as client:
        identity = client.get_caller_identity()
        if not identity.get("Account") or not identity.get("Arn"):
            raise ValueError("Invalid identity response")
    print("PASS: AWS identity check (identity details omitted)")
    with closing(create_aws_client("bedrock", config=config)) as client:
        response = client.list_foundation_models()
        if not isinstance(response.get("modelSummaries"), list):
            raise ValueError("Invalid catalog response")
    print("PASS: Bedrock catalog reachable; this does not prove inference access")
    if not inference:
        print("SKIP: Inference checks; add --live-inference to authorize model calls")
        return
    from services.bedrock_service import BedrockService
    # Explicit local demo mode + both CLI live flags remain the approved local
    # diagnostic path. Cognito callers must supply their authenticated session.
    import os
    if auth_session is None and os.environ.get("NOVAMIND_AUTH_MODE") == "demo":
        from services.auth_service import login
        state = {}
        login(state, "demo", "demo1234")
        auth_session = state["auth_session"]
    service = BedrockService(region=config.region, model_id=model_id, max_tokens=128,
                             temperature=0.0, auth_session=auth_session)
    try:
        png, pdf = build_attachments()
        for label, prompt, kwargs in (
            ("text streaming", "Reply with OK.", {}),
            ("image streaming", "Describe the image briefly.", {"image_bytes": png, "image_format": "png"}),
            ("PDF streaming", "Describe this blank document briefly.", {"doc_bytes": pdf, "doc_format": "pdf", "doc_name": "Document 1"}),
        ):
            service.invoke_response(prompt, [], **kwargs)
            print("PASS: " + label)
    finally:
        service._client.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live-check", action="store_true", help="Authorize live STS and Bedrock catalog calls")
    parser.add_argument("--live-inference", action="store_true", help="Also authorize paid text/image/PDF streaming checks; requires --live-check")
    args = parser.parse_args(argv)
    if args.live_inference and not args.live_check:
        print("ERROR: --live-inference requires --live-check.")
        return 2
    # Needed for direct execution from any working directory; no import-time setup.
    root = str(Path(__file__).resolve().parents[1])
    if root not in sys.path:
        sys.path.insert(0, root)
    missing = [name for name in ("boto3", "botocore", "PIL", "pypdf", "streamlit")
               if importlib.util.find_spec(name) is None]
    if missing:
        print("FAIL: Required packages unavailable: " + ", ".join(missing))
        return 1
    from services.aws_config import load_aws_config, bedrock_options, safe_aws_error, AWSConfigurationError
    from services.request_limits import MODEL_POLICIES
    try:
        config = load_aws_config()
        model_id = bedrock_options()["model_id"]
        if model_id not in MODEL_POLICIES:
            raise AWSConfigurationError("Selected Bedrock model has no configured capability policy.")
        print(f"Configuration: mode={config.mode}; region={config.region}; profile={config.profile or 'task role'}")
        if not args.live_check:
            print("PASS: Offline configuration checks only. Credentials and AWS access were not checked.")
            return 0
        run_live_checks(config, model_id, inference=args.live_inference)
        return 0
    except Exception as exc:
        print("FAIL: " + safe_aws_error(exc))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
