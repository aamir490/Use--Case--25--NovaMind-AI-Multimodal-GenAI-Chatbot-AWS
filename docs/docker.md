# Local Linux container

The image uses Python 3.14.6 on Debian Bookworm and the separate pinned
`requirements-linux.txt` runtime closure. It runs Streamlit as UID/GID 10001 on
port 8501. The image includes the application modules, Streamlit config, CSS
and logo; the build context excludes credentials, local environments, tests and
uploaded data. AWS resources and credentials are supplied at runtime.

From the repository root in PowerShell:

```powershell
docker build --tag novamind-ai:local .
docker image inspect novamind-ai:local --format '{{.Config.User}} {{json .Config.Healthcheck}}'
docker run --rm --entrypoint python novamind-ai:local -c "import utils.validators; import novamind.ui.app; import services.attachment_store"
docker run --detach --name novamind-ai-local --publish 8501:8501 novamind-ai:local
Invoke-WebRequest http://localhost:8501/_stcore/health
docker inspect novamind-ai-local --format '{{json .State.Health}}'
docker logs novamind-ai-local
docker stop novamind-ai-local
docker rm novamind-ai-local
```

The bare run command verifies startup and health only. Authenticated local use
needs Cognito settings and the existing `novamind` AWS profile. Supply those at
runtime; never use build arguments or `COPY` for credentials. For a local-only
profile test, mount the host AWS directory read-only and set
`AWS_PROFILE=novamind`, `AWS_DEFAULT_REGION=us-east-1`, and
`NOVAMIND_AWS_MODE=local`. ECS must instead set `NOVAMIND_AWS_MODE=task-role`,
omit profile variables, attach a scoped task role, and inject `GROQ_API_KEY`
through an ECS Secrets Manager reference. Provider, model, Cognito IDs, table,
and bucket settings are ordinary runtime configuration. Do not place secret
values in shell history, task-definition plaintext, image layers or logs.

The Docker build installs exact package versions and runs `pip check`; it does
not verify package hashes or prove that every Linux wheel is available. Build
and validate this image in the target environment before release. Streamlit's
health endpoint is configured in the image. ALB/CloudFront WebSocket forwarding,
idle timeouts, stickiness, TLS and outbound access remain infrastructure checks.
