<div align="center">
  <img src="./novamind-logo.png" alt="NovaMind AI logo" width="600">

# NovaMind AI — Project Build Guide & Interview Preparation

### Understand → Explain → Apply → Connect to Code → Connect to AWS → Interview Practice

**NovaMind AI | Built by Aamir**
</div>

---

## How to use this guide

Read each chapter in three passes:

1. **Understand:** explain the idea in plain language without service names.
2. **Connect:** follow the source links and identify where the idea appears in code or AWS.
3. **Defend:** answer the interview prompt using a claim, evidence, boundary, trade-off, and next improvement.

This document uses the following evidence labels:

- **Source-verified:** implemented in the current Python, configuration, test, Docker, or workflow files.
- **Deployment-evidenced:** shown by repository screenshots/diagrams, but not reproducible from infrastructure as code in this repository.
- **Optional:** implemented behind configuration and dependent on pre-existing external resources.
- **Proposed/unknown:** useful future work or a live configuration detail that the repository cannot prove.

> [!IMPORTANT]
> NovaMind AI is a **multimodal generative-AI application**, not an agentic system. It has no autonomous planning loop, tool registry, tool execution, goal decomposition, or multi-agent orchestration. In an Agentic AI interview, use it as a strong foundation and explain what would need to be added to make it agentic.

### Evidence snapshot

- Current branch: `main`; remote points to the named GitHub repository.
- Git history contains six commits: one large application baseline, two CI commits, one CD commit, and two image/documentation commits.
- The current guarded suite was independently run during README preparation on 13 October 2026: **500 tests passed in 16.545 seconds**. This is not a coverage, load, browser-visual, or live-cloud result.
- Both architecture diagrams and AWS/GitHub screenshots exist under `project-pic/`.
- No Terraform, CloudFormation, CDK, exported task definition, route table, or IAM trust policy is stored in this repository.

### Navigation

1. [Understanding my project](#chapter-1--understanding-my-project)
2. [How I built it from scratch](#chapter-2--how-i-built-this-application-from-scratch)
3. [Complete architecture walkthrough](#chapter-3--complete-architecture-walkthrough)
4. [Complete request flow](#chapter-4--complete-request-flow)
5. [Deep code walkthrough](#chapter-5--deep-code-walkthrough)
6. [Generative AI concepts](#chapter-6--generative-ai-concepts-behind-the-project)
7. [AWS services and decisions](#chapter-7--aws-services-and-design-decisions)
8. [Docker and deployment](#chapter-8--docker-and-aws-deployment)
9. [GitHub Actions CI/CD](#chapter-9--github-actions-cicd)
10. [Troubleshooting and challenges](#chapter-10--troubleshooting-and-real-engineering-challenges)
11. [55 interview questions](#chapter-11--project-interview-questions-and-answers)
12. [How to defend the project](#chapter-12--how-to-defend-my-project-in-an-interview)
13. [Practical demonstration](#chapter-13--practical-interview-demonstration)
14. [Revision and self-assessment](#chapter-14--revision-and-self-assessment)

---

<a id="chapter-1--understanding-my-project"></a>
# Chapter 1 — Understanding My Project

## 1.1 What is NovaMind AI?

### Simple explanation

NovaMind AI is a secure web application where a signed-in user can chat with an AI, ask questions about an image, or ask questions about a document. The answer appears progressively instead of making the user wait for the whole response.

### Technical explanation

It is a modular Python/Streamlit application that routes capability-checked requests to Amazon Bedrock's Converse streaming API or to an optional Groq text-streaming adapter. It adds Cognito authentication, per-session authorization, bounded conversation memory, defensive file parsing, usage telemetry, optional DynamoDB/S3 persistence, a non-root Docker runtime, and an AWS container deployment path.

### Why it exists

A basic chatbot proves only that an API can return text. NovaMind AI demonstrates the surrounding engineering needed for a credible AI product:

- who may use it;
- which data belongs to which session;
- how model capabilities are selected;
- how files are validated before reaching a model;
- what happens when a stream fails halfway;
- how credentials differ between local and deployed execution;
- how a container is built, checked, deployed, monitored, and rolled forward; and
- which facts are known versus estimated.

## 1.2 Problem, users, and value

| Question | Project answer |
|---|---|
| What problem does it solve? | It gives one authenticated workspace for text assistance, image understanding, and single-document Q&A, while handling safety and cloud-delivery concerns that a minimal chatbot omits. |
| Who can use it? | Knowledge workers, students, developers, analysts, and AWS learners with a provisioned Cognito account; an explicit loopback-only demo mode exists for development. |
| Why did I build it? | To learn and demonstrate end-to-end Generative AI engineering: UI, model APIs, security, multimodal validation, AWS containers, CI/CD, and failure handling. |
| What makes it different? | Strict stream-commit semantics, verified auth/session ownership, capability-aware routing, bounded parsers and request budgets, explicit credential policies, offline network guards, and exact-artifact deployment verification. |

## 1.3 Key capabilities

- Streaming, multi-turn text chat.
- Bedrock image understanding for JPEG, PNG, GIF, and WebP.
- Direct Bedrock document Q&A for PDF, TXT, Markdown, CSV, HTML, DOC/DOCX, and XLS/XLSX within validation limits.
- Amazon Nova Pro, Nova Lite, Nova Micro, Claude 3.5 Sonnet, and one configured Groq model in the selector.
- Persona templates, custom system prompts, eight response-language instructions, temperature, and output-token controls.
- Cognito username/password login, SMS/TOTP MFA handling, token verification, idle/absolute expiry, and global sign-out.
- Separate visible transcript and model context, with only completed outputs committed to AI memory.
- Optional owner-scoped DynamoDB conversation snapshots and S3 saved attachments.
- Live latency/token/cost-estimate UI and sanitized structured JSON events.
- Guarded offline tests, Docker build, automatic CI, and manual OIDC-based ECS deployment.

## 1.4 Honest limitations

- Active Streamlit/WebSocket state remains in process memory; a restart loses unsaved work.
- Optional saved state does not make live sessions transparently distributable across replicas.
- Direct document input is not retrieval-augmented generation; it does not search a large corpus or provide source citations.
- Groq is text-only in this implementation.
- No code execution, tools, autonomous actions, or agent loop exist.
- No infrastructure as code proves the live VPC, route, security-group, IAM, circuit-breaker, or autoscaling settings.
- Configured token prices are explicitly unverified estimates, not bills.
- Offline tests do not prove live Cognito, Bedrock entitlement, Groq access, browser appearance, load capacity, or AWS network reachability.

## 1.5 Explain it to a non-technical person

> “NovaMind AI is like a secure AI workspace. After signing in, you can type a question, attach a picture, or attach a document. The app checks that the input is safe and supported, sends it to the selected AI model, and shows the answer as it is generated. It runs in a Docker container on AWS, and automated checks make sure new code passes tests before it can be deployed.”

## 1.6 Explanations by time limit

### 30 seconds

> “I built NovaMind AI, a secure multimodal Streamlit chatbot deployed on AWS. It supports streaming text chat, image understanding, and direct document Q&A through Amazon Bedrock, plus optional Groq text inference. Cognito protects user access, Fargate runs the container behind CloudFront and an internal ALB, and GitHub Actions tests and deploys exact commit-tagged images using OIDC.”

### One minute

> “NovaMind AI demonstrates the complete engineering lifecycle around a generative-AI application. Users authenticate with Cognito, choose a supported model, and send text or validated image/document input. Bedrock uses ConverseStream; Groq is an optional text-only adapter. I separated Streamlit UI, orchestration, domain state, and service layers. The app validates the full request, bounds conversation memory, streams output, and commits only successful turns. It runs as a non-root Fargate container. CloudFront reaches an internal ALB through a VPC origin, while ECR stores images and CloudWatch receives logs. CI automatically runs a guarded 500-test suite and Docker build. CD is manual, verifies CI for the exact commit, assumes AWS through OIDC, and verifies the ECS revision and image after rollout.”

### Three minutes

Explain in this order: **problem → application behavior → code reliability → AWS path → delivery → boundaries**.

> “The problem I wanted to solve was creating one credible AI workspace rather than a model API demo. NovaMind AI lets an authenticated user hold a conversation, analyze an image, or ask questions about one document. The UI includes model, persona, language, temperature, and output controls, along with live latency and usage information.
>
> Under the UI I split responsibilities into domain/session state, orchestration, and provider services. Before any model call, uploads are decoded and structurally validated, and the complete request is checked for model capability, attachment count, payload size, context estimate, and output reservation. Bedrock receives Converse content blocks and streams text deltas. A response only enters future model context after a valid completion event. If output stops halfway, the user can see it marked incomplete, but the model will not treat it as trusted history. The only automatic model fallback is one pre-output Nova Pro attempt to the US inference profile after access denial.
>
> Cognito is the default identity provider. The code treats local JWT parsing only as a rejection check and asks Cognito GetUser to verify the exact access token. Server-side data scopes bind histories, attachments, and provider clients to that authenticated identity. Local AWS access is restricted to one named profile; ECS mode accepts only task-role container credentials and rejects static keys.
>
> In the deployed design, users connect over HTTPS to CloudFront. A CloudFront VPC origin reaches an internal ALB, which forwards to the Fargate task on port 8501 and checks Streamlit's health endpoint. The task uses Cognito and Bedrock, optionally receives a Groq secret at runtime, pulls its image from ECR, and emits logs to CloudWatch.
>
> CI runs offline tests under socket, DNS, credential, client, and API guards, then builds the Linux image. CD is deliberately manual. It verifies successful CI for the same Git SHA, uses GitHub OIDC, publishes or reuses the SHA-tagged ECR image, registers a task revision changing only that image, updates ECS, waits for stability, and verifies what actually deployed. The main limitations are in-memory active sessions, no IaC, no load-test evidence, and no agentic tool loop. Those boundaries are also my production roadmap.”

---

<a id="chapter-2--how-i-built-this-application-from-scratch"></a>
# Chapter 2 — How I Built This Application From Scratch

## 2.1 History versus logical reconstruction

The Git record does **not** contain one commit for each development step. Commit `f5bc652` introduces 107 files and the whole application baseline. Later evidence is specific:

1. `e40f4dc` added CI with Python tests and Docker build.
2. `fbe64fd` changed the test runner from Ubuntu/Python 3.14/Linux requirements/bare discovery to Windows/Python 3.14.6/Windows lock/the guarded canonical runner.
3. `8ed9561` added manual ECS CD.
4. `922c5d3` added the CI/CD screenshots and an architecture image.
5. `157e431` renamed the architecture images to the current with/without-CI/CD filenames.

The sequence below is therefore a **logical way to build and understand the system**, inferred from current dependencies and task notes. It is not claimed to be the exact historical order.

## 2.2 Logical build sequence

### Step 1 — Define requirements and boundaries

**Build:** decide on text chat, one attachment at a time, supported models, streaming, authentication, AWS deployment, and offline tests.

**Why:** boundaries prevent accidental claims such as “RAG,” “agent,” “persistent,” or “production-ready” before the code supports them.

**Code connection:** model/persona/language choices are centralized in [`novamind/config/settings.py`](./novamind/config/settings.py#L1-L62); request ceilings live in [`services/request_limits.py`](./services/request_limits.py#L13-L123).

**Next:** choose technologies that match a stateful streaming web app.

### Step 2 — Select the technology stack

**Build:** Python + Streamlit, Bedrock Converse, optional Groq HTTP adapter, Cognito, Docker, ECS/Fargate, CloudFront VPC origin + internal ALB, ECR, CloudWatch, and GitHub Actions.

**Why:** Python fits AI/AWS libraries; Streamlit accelerates chat UI; Converse normalizes supported Bedrock models; Fargate suits a long-running WebSocket server; OIDC avoids CI access keys.

**Alternatives:** React/FastAPI gives more frontend/API control; Lambda is better for stateless short requests; App Runner simplifies hosting but changes network/control trade-offs; a third-party model SDK may be convenient but adds dependency surface.

### Step 3 — Establish structure

```text
launcher → novamind.ui.app
         ├── UI components
         ├── domain/session state
         ├── orchestration
         └── services/providers/storage/validation
```

The compatibility entry point [`mod_chatbot_frontend.py`](./mod_chatbot_frontend.py#L1-L12) calls [`novamind.ui.app.main`](./novamind/ui/app.py#L29-L42). This keeps `streamlit run mod_chatbot_frontend.py` stable while moving logic into testable modules.

### Step 4 — Pin Python and dependencies

**Build:** a Windows CPython 3.14.6 lock for local/CI, a separate Linux lock for Docker, direct dependency roots, and optional legacy Office dependencies.

**Why:** exact environments reduce “works on my machine” drift. Pillow and pypdf are security-relevant validators, not decorative extras.

**Files:** [`requirements.in`](./requirements.in), [`requirements.txt`](./requirements.txt), [`requirements-linux.txt`](./requirements-linux.txt), [`requirements-legacy.txt`](./requirements-legacy.txt), and [`docs/dependencies.md`](./docs/dependencies.md).

#### Reproduce the local environment safely

The documented development baseline is standard 64-bit CPython 3.14.6 on Windows. Use a fresh virtual environment; do not overwrite one you need:

```powershell
Set-Location 'E:\codex-projetc\Chatbot_text_image'
py -3.14 -c "import sys, struct; assert sys.version_info[:3] == (3, 14, 6) and struct.calcsize('P') == 8"
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip check
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run_offline_tests.ps1
```

For an approved local AWS profile, set only non-secret selectors in the launching shell:

```powershell
$env:NOVAMIND_AWS_MODE = 'local'
$env:AWS_PROFILE = 'novamind'
$env:AWS_DEFAULT_PROFILE = 'novamind'
$env:AWS_REGION = 'us-east-1'
$env:AWS_DEFAULT_REGION = 'us-east-1'
```

Authentication defaults to Cognito. Supply existing resource identifiers as environment values—not credentials—and use an app client without a client secret:

```powershell
$env:NOVAMIND_AUTH_MODE = 'cognito'
$env:COGNITO_USER_POOL_ID = '<existing-us-east-1-pool-id>'
$env:COGNITO_APP_CLIENT_ID = '<existing-public-app-client-id>'
.\.venv\Scripts\python.exe -m streamlit run mod_chatbot_frontend.py
```

For loopback-only UI development, the repository also documents explicit `NOVAMIND_AUTH_MODE=demo`; bind Streamlit to `127.0.0.1` and never expose that mode publicly. [`.env.example`](./.env.example) is a reference only—the application does not auto-load `.env`. Never put AWS access keys, user passwords, Cognito tokens, or `GROQ_API_KEY` in Git, command history, screenshots, or logs. See [`docs/setup.md`](./docs/setup.md) for the authoritative local procedure.

### Step 5 — Build the Streamlit shell

**Build:** page configuration, CSS/branding, login gate, sidebar settings, welcome cards, chat rendering, uploader, and live metrics.

**How:** [`_run_app`](./novamind/ui/app.py#L45-L101) first checks authentication, initializes scoped state, renders the sidebar, processes summary triggers, shows the hero/metrics/history, and finally accepts chat input.

**Why:** authentication precedes private UI/state; settings precede request creation; chat rendering is separate from provider logic.

### Step 6 — Add authentication and scoped sessions

**Build:** Cognito configuration, sign-in, MFA challenges, token checks, session expiry, logout, and a local-only demo mode.

**How:** [`login`](./services/auth_service.py#L246-L280) calls Cognito `InitiateAuth`; [`verify_access_token`](./services/auth_service.py#L160-L179) validates claims then requires `GetUser`; [`require_session`](./services/auth_service.py#L320-L334) enforces ownership and expiry. [`services/authorization.py`](./services/authorization.py#L17-L158) binds private objects to the exact session.

**Why:** a `logged_in=True` UI flag is not authorization. The verified subject and server-created scope are.

### Step 7 — Integrate foundation-model providers

**Build:** a common provider contract, Bedrock implementation, and optional Groq implementation.

**How:** [`get_ai_service`](./services/ai_provider.py#L7-L16) routes the configured Groq model to `GroqService`; other supported selections go to `BedrockService`. Both expose compatible `stream_response`, settings, and history behavior.

**Why:** the UI can stream through one interface while capability policy remains explicit.

### Step 8 — Implement text chat

**Build:** sanitize input, capture session/attachment scope, render the user message, stream the assistant response, then record visible and model history.

**Code:** [`_handle_user_input`](./novamind/ui/chat.py#L212-L293) and [`_stream_and_display_response`](./novamind/ui/chat.py#L57-L210).

**Critical decision:** visible history may show failed/incomplete text; Bedrock history commits only a completed pair.

### Step 9 — Add multimodal processing

**Images:** [`ImageService.process`](./services/image_service.py#L126-L224) checks bytes, extension, magic signature, full Pillow decode, size, dimensions, animation ceilings, and creates a private thumbnail.

**Documents:** [`DocumentService.process`](./services/document_service.py#L218-L294) checks extension/signature/size, invokes bounded structural validation, creates a preview, and assigns a neutral Bedrock API name.

**Routing:** [`_handle_file_upload`](./novamind/orchestration/uploads.py#L17-L71) rejects stale callbacks and publishes exactly one pending attachment.

### Step 10 — Build memory and streaming correctness

**Build:** bounded recent completed turns, full-request validation, generator cleanup, stop-reason checks, and no unsafe replay.

**How:** [`request_history`](./services/conversation_memory.py#L20-L50) validates every historical pair, chooses a recent suffix, and trims only for size/count/context categories. [`BedrockService.stream_response`](./services/bedrock_service.py#L144-L365) owns stream events and transactional commit.

### Step 11 — Add error handling, usage, and privacy

**Build:** `GenerationResult`/`GenerationError`, safe AWS errors, per-attempt usage records, bounded retries for reads, and allowlisted JSON events.

**Files:** [`services/usage_accounting.py`](./services/usage_accounting.py#L9-L83), [`services/observability.py`](./services/observability.py#L25-L64), [`services/aws_retries.py`](./services/aws_retries.py#L9-L38), and [`services/aws_config.py`](./services/aws_config.py#L103-L112).

### Step 12 — Add optional persistence

**Build:** explicit save/list/load/delete in DynamoDB; optional attachment freeze/thaw/cleanup in S3.

**Why optional:** the core app can run without storage, and the app deliberately does not provision a table/bucket. Cognito mode is required for persistence.

**Code:** [`save_conversation`](./services/conversation_store.py#L170-L232), [`load_conversation`](./services/conversation_store.py#L264-L344), [`delete_conversation`](./services/conversation_store.py#L346-L377), and [`services/attachment_store.py`](./services/attachment_store.py#L12-L169).

### Step 13 — Test locally without AWS

**Build:** canonical discovery plus environment/network/AWS guards in [`tests/run_offline.py`](./tests/run_offline.py#L1-L30) and [`tests/offline_support.py`](./tests/offline_support.py#L1-L58).

**Why:** unit and Streamlit interaction tests must be deterministic, credential-free, and non-billable. Tests mock provider boundaries while detecting swallowed network attempts.

### Step 14 — Containerize

**Build:** Debian slim Python image, pinned Linux dependencies, non-root UID/GID 10001, explicit file copies, import smoke check, port 8501, health check, and Streamlit command.

**Code:** [`Dockerfile`](./Dockerfile#L1-L35) and [`.streamlit/config.toml`](./.streamlit/config.toml#L1-L12).

### Step 15 — Prepare AWS infrastructure

**Deployment-evidenced:** CloudFront distribution/VPC origin, internal ALB, ECS/Fargate service, ECR repository, Cognito pool, Secrets Manager entries, and CloudWatch log group.

**Unknown from source:** provisioning commands, route tables, actual task subnet/public-IP setting, security-group rules, target-group stickiness/timeout, OIDC trust policy, task/execution policies, circuit-breaker setting, and autoscaling.

### Step 16 — Deploy the image through ECR and ECS

ECR stores the image; an ECS task definition points at it; an ECS service keeps the desired task running and connects it to the target group. The execution role supports image/log bootstrap; the task role supports runtime service calls.

### Step 17 — Place CloudFront and ALB in front

CloudFront is the public HTTPS endpoint. Its VPC origin reaches the internal ALB. The ALB listens on port 80 and forwards to the task's Streamlit port 8501. WebSocket headers, cookies, query strings, and timeouts matter because Streamlit maintains an interactive session.

### Step 18 — Automate CI/CD and improve operations

CI checks Python behavior before Docker. Manual CD provides an approval boundary and verifies the exact artifact after ECS rollout. The next engineering steps are IaC, alarms, authenticated smoke tests, supply-chain controls, and distributed active-session design.

---

<a id="chapter-3--complete-architecture-walkthrough"></a>
# Chapter 3 — Complete Architecture Walkthrough

![NovaMind AI AWS runtime architecture](./project-pic/NovaMind-AI-AWS-Architecture-Blueprint-without-cicd.png)

## 3.1 Evidence boundary before the walkthrough

The diagram records a `10.20.0.0/16` VPC across two Availability Zones, two subnets labeled public (`10.20.1.0/24`, `10.20.2.0/24`), and two labeled private (`10.20.11.0/24`, `10.20.12.0/24`). It places the internal ALB in the first tier and ECS tasks in the private tier. The ALB screenshot verifies an internal scheme and two subnets. No IaC or ECS network export verifies the task subnet, public-IP flag, NAT, endpoints, or routes. Say **“the diagrammed deployment”**, not **“the repository proves.”**

## 3.2 Browser and HTTPS/WebSocket

- **What:** the user's web/mobile browser running the Streamlit frontend.
- **Why:** it provides chat, forms, uploads, and a persistent interactive session.
- **Here:** it connects to CloudFront on HTTPS/443; Streamlit uses HTTP plus WebSocket communication.
- **Failure:** blocked upgrade, cookie forwarding, or idle timeout may show the page but break interaction.
- **Why this design:** browser-based access needs no local client installation; the trade-off is WebSocket-aware proxy configuration.

## 3.3 Amazon CloudFront

- **What:** AWS's global content-delivery and edge service.
- **Why:** public HTTPS entry point, edge connection handling, and a controlled bridge to a private origin.
- **Here:** the deployment screenshot shows a distribution; the diagrams show dynamic app and WebSocket traffic forwarded to a VPC origin.
- **Failure:** users cannot reach the app, or mis-forwarded session data breaks Streamlit.
- **Alternative:** a public ALB is simpler but exposes the load balancer directly and loses CloudFront edge controls/caching options.

## 3.4 CloudFront VPC origin

- **What:** a CloudFront mechanism for reaching supported private VPC origins.
- **Why:** the ALB is internal and cannot be used as an ordinary public internet origin.
- **Here:** it connects CloudFront to the internal ALB; the diagram calls out headers, cookies, query strings, and WebSocket support.
- **Failure:** origin association, service security group, or policy errors cause origin connection failures.
- **Alternative:** make the ALB internet-facing, or introduce another public ingress. Both change the trust boundary.

## 3.5 Internal Application Load Balancer

- **What:** a layer-7 load balancer with listener rules and target health.
- **Why:** decouples CloudFront from individual tasks, checks health, and supports ECS rolling replacement.
- **Here:** deployment evidence shows scheme `Internal`, HTTP listener 80, two AZ subnets, and forwarding to the NovaMind target group. The target is Streamlit on 8501.
- **Failure:** unhealthy targets or listener/security-group errors produce 5xx/unavailable origin behavior.
- **Alternative:** direct task access is unstable and unsafe; API Gateway is not a natural transparent host for this Streamlit server/WebSocket model.

## 3.6 VPC, subnets, routes, and security groups

- **What:** the VPC is a logical network; subnets divide address space/AZ placement; routes choose paths; security groups are stateful network firewalls.
- **Why:** isolate backend tasks and limit each hop.
- **Here:** the diagram intends CloudFront-origin SG → ALB port 80 and ALB SG → ECS port 8501. Outbound AWS API and optional Groq access still need routes/endpoints.
- **Failure:** overly strict egress prevents Cognito/Bedrock/Secrets/log calls; overly broad ingress weakens the private-origin design.
- **Alternative:** fully public networking is easier but increases exposure; fully private service endpoints improve isolation but Groq still needs controlled internet egress.

## 3.7 Amazon ECS on Fargate

- **What:** ECS schedules containers; Fargate supplies managed compute without EC2 host administration.
- **Why:** Streamlit is a long-running server with health checks and WebSocket state.
- **Here:** the diagrams/screenshots show one running service/task. The image starts Streamlit on `0.0.0.0:8501`.
- **Failure:** ECS replaces unhealthy tasks, but unsaved in-memory sessions disappear; rollout failure may trigger service rollback only if the live circuit breaker is enabled.
- **Alternative:** EC2 gives host control but adds patching/capacity work; Lambda fits short stateless handlers, not this server as written; App Runner is simpler but offers different networking/deployment control.

## 3.8 Streamlit application

- **What:** the Python web/UI process inside the container.
- **Why:** rapidly implements chat widgets, uploads, sidebar settings, streaming placeholders, and session state.
- **Here:** [`main`](./novamind/ui/app.py#L29-L42) configures the page and dispatches the auth-gated application.
- **Failure:** container health may stay green while provider/auth configuration fails; health proves process readiness only.
- **Alternative:** FastAPI + React improves API/frontend separation and horizontal scaling options at greater implementation cost.

## 3.9 Amazon Cognito

- **What:** managed user directory and authentication service.
- **Why:** remove password verification/storage from the application and provide token lifecycle/MFA.
- **Here:** public user APIs perform sign-in, MFA response, `GetUser` verification, and global sign-out.
- **Failure:** login/verification fails closed and the local session is cleared; existing output already sent to a browser cannot be recalled.
- **Alternative:** enterprise OIDC or Auth0 may fit organizational identity; custom auth has much higher security responsibility.

## 3.10 Amazon Bedrock

- **What:** managed access to foundation models through AWS APIs.
- **Why:** one AWS-governed interface for Nova and Claude with task-role authorization and streaming.
- **Here:** `bedrock-runtime.converse_stream` receives system, messages, multimodal blocks, and inference parameters.
- **Failure:** safe error classification; incomplete output is excluded from AI history. Nova Pro alone has one narrow pre-output access-denied fallback.
- **Alternative:** direct vendor APIs may expose different models/features but require separate credentials, governance, payload formats, and billing.

## 3.11 Groq API

- **What:** an external OpenAI-compatible model endpoint.
- **Why:** optional low-latency text inference and provider abstraction practice.
- **Here:** standard-library HTTPS POST to the streaming chat-completions endpoint; Llama 3.3 70B or GPT-OSS 120B is configured at process start.
- **Failure:** missing key fails before network; HTTP/network errors are sanitized; attachments are rejected before network.
- **Alternative:** an SDK simplifies some code but increases dependency surface; other vendors require another adapter/capability policy.

## 3.12 AWS Secrets Manager

- **What:** managed secret storage and access control.
- **Why:** keep a Groq key out of source, images, and workflow text.
- **Here:** deployment evidence shows secret entries; ECS is expected to inject `GROQ_API_KEY`. The Python app reads the environment and does not call Secrets Manager itself.
- **Failure:** the Groq service reports missing configuration; Bedrock can still work if selected/configured.
- **Alternative:** SSM Parameter Store may suit some secrets/config; plaintext task environment variables are inspectable and inappropriate for secret values.

## 3.13 Amazon ECR

- **What:** private container registry.
- **Why:** controlled image storage integrated with ECS and IAM.
- **Here:** CD uses the full Git SHA as the tag and validates/reuses an existing digest or pushes the missing image.
- **Failure:** login/push/pull permissions or image architecture/dependency errors stop deployment/task startup.
- **Alternative:** Docker Hub/GHCR work but add cross-provider identity/network considerations.

## 3.14 Amazon CloudWatch

- **What:** AWS logs/metrics/alarms platform.
- **Why:** central place for container output and operational diagnosis.
- **Here:** evidence shows `/ecs/novamind-chatbot` with one-week retention at capture time. Application code emits sanitized JSON events.
- **Failure:** the app can run while observability is absent, but diagnosis/audit becomes much harder; log delivery permission belongs to the execution path.
- **Alternative:** third-party observability may offer richer correlation at additional integration/cost.

## 3.15 IAM roles

- **Execution role:** ECS agent operations such as ECR pull and CloudWatch log delivery.
- **Task role:** application calls such as Bedrock, DynamoDB, and S3. Least privilege belongs here.
- **GitHub deployment role:** assumed through OIDC to read/write ECR/task definitions and update/inspect the specific ECS service.
- **Failure:** identify which identity made the denied call before changing policy. Broad administrator access is not a diagnosis.
- **Unknown:** the exact live trust and permissions policies are not in the repository.

---

<a id="chapter-4--complete-request-flow"></a>
# Chapter 4 — Complete Request Flow

## 4.1 Opening the application

1. The browser opens the CloudFront HTTPS URL.
2. CloudFront forwards dynamic HTTP/WebSocket traffic through the VPC origin.
3. The internal ALB listener chooses the target group.
4. A healthy ECS task receives traffic on container port 8501.
5. Streamlit runs [`mod_chatbot_frontend.py`](./mod_chatbot_frontend.py#L1-L12), which calls [`main`](./novamind/ui/app.py#L29-L42).

If any network hop fails, the Python request flow never starts. Separate “cannot reach the page” from “page works but inference fails.”

## 4.2 Authentication and initialization

1. [`_run_app`](./novamind/ui/app.py#L45-L101) calls [`_check_login`](./novamind/ui/auth.py#L88-L106).
2. [`load_auth_config`](./services/auth_service.py#L38-L68) defaults to Cognito and rejects invalid/missing configuration.
3. The login callback passes credentials to [`login`](./services/auth_service.py#L246-L280).
4. Cognito returns an access token or supported MFA challenge.
5. [`verify_access_token`](./services/auth_service.py#L160-L179) checks token context and requires matching `GetUser` identity.
6. `_establish` creates a server-side `DataScope`; [`_init_session_state`](./novamind/domain/session.py#L10-L68) registers histories, attachments, usage, metrics, and provider state into that scope.
7. [`_session_watchdog`](./novamind/ui/auth.py#L109-L118) runs every 30 seconds without extending idle activity.

## 4.3 Model and settings selection

The sidebar maps a friendly label to a model ID in [`MODEL_OPTIONS`](./novamind/config/settings.py#L11-L21). `MODEL_PROVIDERS` maps the configured Groq model to `groq`; everything else is `bedrock`. Changing a model clears the cached service. [`_get_or_create_service`](./novamind/orchestration/bedrock.py#L11-L41) builds a new provider with the selected temperature, maximum tokens, system prompt, language instruction, and authenticated session.

## 4.4 Prompt or attachment submission

1. Streamlit returns text from `st.chat_input` to [`_handle_user_input`](./novamind/ui/chat.py#L212-L293).
2. [`sanitize_user_input`](./utils/validators.py#L217-L233) normalizes and bounds text.
3. If an upload exists, [`_handle_file_upload`](./novamind/orchestration/uploads.py#L17-L71) has already created a validated `ImageResult` or `DocumentResult`.
4. The attachment selection is captured, then reset before invocation so reruns/retries do not accidentally reuse it.
5. The user message is rendered and appended to visible history.

## 4.5 Validation and context selection

1. The provider builds content blocks; [`_build_content_blocks`](./services/bedrock_service.py#L431-L497) orders image/document before text and neutralizes document names.
2. [`request_history`](./services/conversation_memory.py#L20-L50) validates historical pairs and selects recent complete context.
3. [`validate_request`](./services/request_limits.py#L47-L123) checks structure, model capability, output/temperature, counts, raw/base64 payload size, and estimated context.
4. Any failure occurs before a provider call and leaves model history unchanged.

## 4.6 Bedrock path

1. [`BedrockService.stream_response`](./services/bedrock_service.py#L144-L365) rechecks session authorization.
2. It constructs `modelId`, `messages`, `system`, and `inferenceConfig`.
3. boto3 calls `converse_stream` using the task role in ECS or the explicit local profile.
4. The loop accepts text deltas, records first-token/total latency, watches stop/metadata events, and rejects unsupported output blocks or invalid sequencing.
5. A valid `end_turn` or `stop_sequence` plus nonblank text completes the response.
6. Only then does it append user/assistant content to the working history.

## 4.7 Groq path

[`GroqService.stream_response`](./services/groq_service.py#L57-L205) converts text history to OpenAI-compatible messages, sends an authenticated HTTPS request, parses SSE `data:` frames, yields text deltas, collects usage when supplied, and closes the response. Model policy prevents image/document content from reaching this endpoint.

## 4.8 UI streaming, commit, and failure behavior

[`_stream_and_display_response`](./novamind/ui/chat.py#L57-L210) consumes the provider generator into a Streamlit placeholder. A completed result replaces the caller's model history with the validated working history. A failure creates a safe status/error object. [`_handle_user_input`](./novamind/ui/chat.py#L212-L293) always records a visible assistant outcome, but incomplete/failed text is not copied into model context.

This is a strong interview point: **rendering and context commitment are different transactions.**

## 4.9 Optional save flow

When configured and signed in through Cognito, sidebar actions call [`save_conversation`](./services/conversation_store.py#L170-L232). The owner key derives from verified identity, payloads are bounded, and version checks prevent stale overwrite. If S3 is configured, attachments are frozen before the DynamoDB commit. Load revalidates data and publishes atomically; delete tombstones first, then cleans S3, preventing resurrection after partial failure.

---

<a id="chapter-5--deep-code-walkthrough"></a>
# Chapter 5 — Deep Code Walkthrough

## 5.1 Folder map

```text
mod_chatbot_frontend.py       Stable Streamlit launcher
novamind/config/              Model, provider, persona, language choices
novamind/domain/              Session and usage state rules
novamind/orchestration/       Provider/upload workflows independent of UI
novamind/ui/                  Streamlit rendering and callbacks
services/                     Auth, providers, validation, memory, storage, logs
utils/                        Shared input/file/transcript validation
tests/                        Offline unit and Streamlit AppTest regressions
scripts/                      Canonical test runner and opt-in live diagnostic
.github/workflows/            Automatic CI and manual CD
project-pic/                  Architecture and deployment evidence
```

## 5.2 Entry, configuration, domain, and UI

| File and important symbols | Inputs → processing → outputs | Dependencies and errors | Interview explanation |
|---|---|---|---|
| [`mod_chatbot_frontend.py`](./mod_chatbot_frontend.py#L1-L12) | Streamlit executes file → ensures root import path → calls `main()` | Imports only the app entry | “I kept a compatibility launcher and moved behavior into modules.” |
| [`novamind/config/settings.py`](./novamind/config/settings.py#L1-L62) | Environment/provider config → model labels, personas, languages | Provider config validates Groq ID | “UI choices are centralized and do not initialize AWS.” |
| [`novamind/domain/session.py`](./novamind/domain/session.py#L10-L100) | Authenticated state → initialize/reset/rotate → scoped session fields | Authorization publish/capture APIs | “State transitions are domain functions, not scattered widget mutations.” |
| [`novamind/domain/usage.py`](./novamind/domain/usage.py#L7-L35) | Usage records → ledger/totals/session cost | Decimal-aware accounting | “Usage is per attempt and can remain unknown.” |
| [`novamind/ui/app.py`](./novamind/ui/app.py#L16-L101) | Streamlit rerun → auth, state, sidebar, hero, history, input | Safe handling of auth/AWS config errors | “This is the composition root for each rerun.” |
| [`novamind/ui/auth.py`](./novamind/ui/auth.py#L11-L118) | Login/MFA widgets → callbacks → auth state | Clears widget secrets; 30-second watchdog | “The page gate uses verified session objects, not a Boolean.” |
| [`novamind/ui/sidebar.py`](./novamind/ui/sidebar.py#L22-L300) | Model/settings/conversation actions → state updates | Handles persistence errors and safe live checks | “The sidebar is the control plane for the current session.” |
| [`novamind/ui/attachments.py`](./novamind/ui/attachments.py#L9-L61) | File widget → upload orchestration → private preview | Never trusts file uploader ownership | “Widget IDs are cache hints, not authorization.” |
| [`novamind/ui/chat.py`](./novamind/ui/chat.py#L25-L400) | Text + optional attachment → streamed result → two histories | Catches provider/auth/limit errors; stale-scope checks | “The UI displays partial output but commits only completed model context.” |
| [`novamind/ui/live_metrics.py`](./novamind/ui/live_metrics.py#L8-L55) | Metric dictionary + session cost → escaped HTML | Unavailable stays unavailable | “Telemetry is user feedback, not an invoice.” |
| [`novamind/ui/styles.py`](./novamind/ui/styles.py#L8-L30) / [`novamind/ui/theme.css`](./novamind/ui/theme.css) | Logo/CSS → branded HTML | Base64 asset handling | “Presentation stays separate from application logic.” |

## 5.3 Orchestration and provider services

| File and important symbols | Purpose and behavior | Failure boundary | Interview explanation |
|---|---|---|---|
| [`novamind/orchestration/bedrock.py`](./novamind/orchestration/bedrock.py#L11-L112) | Creates/reuses the selected provider, applies settings/language, checks context, runs explicit live checks | Revalidates scope before publishing service/status | “Orchestration connects domain state to provider services without importing UI.” |
| [`novamind/orchestration/uploads.py`](./novamind/orchestration/uploads.py#L17-L78) | Detects file type, pre-checks reported size, reads bytes, validates, handles stale widget callbacks | Clears old attachment before new processing; safe generic errors | “Uploads have an explicit lifecycle across Streamlit reruns.” |
| [`services/ai_provider.py`](./services/ai_provider.py#L7-L16) | Provider factory | Invalid configured model/provider fails early | “The abstraction is small and capability-aware.” |
| [`services/bedrock_service.py`](./services/bedrock_service.py#L62-L532) | Bedrock client, content blocks, streaming, fallback, usage, history transaction | `GenerationError` separates safe visible state from chained cause | “This is the core inference boundary.” |
| [`services/groq_service.py`](./services/groq_service.py#L17-L206) | Text-only OpenAI-compatible streaming adapter | Missing key/HTTP/network/empty output become safe generation failures | “The adapter preserves the same streaming/history contract without pretending capabilities match.” |
| [`services/provider_config.py`](./services/provider_config.py#L5-L37) | Allowlisted Groq model and provider selection | Rejects malformed/unapproved IDs | “Environment configuration is validated before it becomes routing.” |

### Real Bedrock payload pattern

The project builds this shape inside [`stream_response`](./services/bedrock_service.py#L236-L247):

```python
payload = {
    "modelId": model_id_to_try,
    "messages": messages_for_api,
    "system": [{"text": self.system_prompt}],
    "inferenceConfig": {
        "maxTokens": self.max_tokens,
        "temperature": self.temperature,
    },
}
```

Explain each field: selected route, structured history, behavior instruction, and generation controls. Do not say temperature “adds knowledge”; it changes sampling variability.

## 5.4 Identity, authorization, and AWS configuration

| File | Key functions/classes | What to understand |
|---|---|---|
| [`services/auth_service.py`](./services/auth_service.py#L21-L360) | `AuthConfig`, `AuthSession`, `login`, `_claims`, `verify_access_token`, `require_session`, `logout` | Cognito default, local-only demo, exact token verification, MFA, expiry, local-first logout, safe errors |
| [`services/authorization.py`](./services/authorization.py#L13-L158) | `DataScope`, `establish_scope`, `validate_scope`, `publish_data`, `rotate_conversation` | Identity is `(mode, issuer, subject)`; state object identity prevents foreign/stale adoption; snapshots are detached |
| [`services/aws_config.py`](./services/aws_config.py#L12-L112) | `AWSConfig`, `load_aws_config`, `create_aws_session`, `create_aws_client`, `bedrock_options` | Region fixed to `us-east-1`; named profile locally; container-role only in ECS; static keys rejected |
| [`services/aws_retries.py`](./services/aws_retries.py#L9-L38) | `retry_read` | Only selected idempotent reads retry, maximum three attempts with bounded backoff; writes/streams are not blindly replayed |

Interview distinction:

- **Authentication:** “Who are you?” — Cognito verifies the user.
- **Authorization:** “May this identity access this state?” — `DataScope` and storage owner keys answer.
- **AWS workload identity:** “Which AWS APIs may the server call?” — the task role answers.

## 5.5 Files, requests, memory, and persistence

| File | Main contract | Important bounds/behavior |
|---|---|---|
| [`services/image_service.py`](./services/image_service.py#L40-L327) | bytes + filename → `ImageResult` or `ImageValidationError` | 3.75 MiB, 8,000 px/side, 16M pixels, frame limits, full decode, 400×400 thumbnail |
| [`services/document_service.py`](./services/document_service.py#L53-L408) | bytes + filename → `DocumentResult` or validation error | 4.5 MiB, supported extension/signature, preview, neutral `Document N` API name |
| [`services/document_parser.py`](./services/document_parser.py#L10-L267) | isolated document structure validation | archive member/part/expanded/ratio/page/object limits; blocks macros/external decoder paths |
| [`utils/validators.py`](./utils/validators.py#L39-L233) | shared routing, filenames, transcript, and user text | HTML-safe/sanitized display boundaries and 10,000-character input cap |
| [`services/request_limits.py`](./services/request_limits.py#L13-L123) | model + settings + full messages → admission facts or `RequestLimitError` | 20 MiB serialized, 200 messages, 20 images, 5 documents, capability/context/output checks |
| [`services/conversation_memory.py`](./services/conversation_memory.py#L7-L72) | completed history + new content → safe suffix | 40 model-context messages; only trimmable budget failures remove oldest complete pairs |
| [`services/conversation_store.py`](./services/conversation_store.py#L23-L377) | explicit save/list/load/delete | Cognito-only, owner hash, conditional version, 200 KB, max 40 saved messages/usage/context entries |
| [`services/attachment_store.py`](./services/attachment_store.py#L12-L169) | freeze/thaw/cleanup saved bytes | 20 MiB aggregate, content-addressed keys, 30-day reference retention, AES256 request, restore revalidation |

## 5.6 Usage and observability

[`UsageRecord`](./services/usage_accounting.py#L19-L38) freezes request ID, attempt, operation, actual model ID, region, status, stop reason, tokens, rate snapshot, estimate, and unknown reason. [`make_usage_record`](./services/usage_accounting.py#L45-L83) does not invent missing token data. [`log_event`](./services/observability.py#L45-L64) emits only allowlisted operational fields.

Interview line: “Unknown is a valid observability state. I do not convert missing provider metadata into zero cost.”

## 5.7 Tests and scripts

- [`tests/run_offline.py`](./tests/run_offline.py#L1-L30): canonical discovery, duplicate-ID detection, exit code.
- [`tests/offline_support.py`](./tests/offline_support.py#L1-L58): deterministic environment and blocked socket/AWS boundaries.
- `tests/test_1*` through `test_5*`: security, validation, streams, auth, storage, UI, reliability, observability, providers, deployment readiness.
- [`scripts/run_offline_tests.ps1`](./scripts/run_offline_tests.ps1#L1-L13): repository-root wrapper using `.venv`.
- [`scripts/bedrock_model_access_check.py`](./scripts/bedrock_model_access_check.py): offline by default; live identity/catalog/inference flags require deliberate use.

## 5.8 How modules connect

```text
Streamlit event
  → UI callback
  → orchestration/domain function
  → authorization check
  → validator/memory selector
  → BedrockService or GroqService
  → streamed GenerationResult
  → UI display + usage/log event
  → model-history commit only on success
```

That separation is the central code story: **UI coordinates; domain owns state rules; orchestration owns workflows; services own external boundaries.**

---

<a id="chapter-6--generative-ai-concepts-behind-the-project"></a>
# Chapter 6 — Generative AI Concepts Behind the Project

Use this learning pattern for every concept: **plain meaning → technical meaning → NovaMind implementation → AWS connection → interview line → likely follow-up**.

## 6.1 Large language models and foundation models

- **Plain:** an LLM predicts useful sequences of language based on patterns learned during training.
- **Technical:** a transformer model consumes tokenized context and autoregressively produces output tokens. A foundation model is broadly trained and adapted at inference through prompts or other techniques.
- **Here:** NovaMind does not train a model. It invokes pre-trained Nova, Claude, Llama, or GPT-OSS models.
- **AWS:** Bedrock provides managed model access; the app sends inference, not training, requests.
- **Interview:** “I engineered the application and inference boundary; I did not claim to build or fine-tune the underlying models.”
- **Follow-up:** Why choose one model over another? Discuss capability, quality, latency, cost, access, and context—not brand alone.

## 6.2 Tokens and context windows

- **Plain:** models read and write chunks called tokens; there is a maximum amount they can consider at once.
- **Technical:** input, system prompt, history, attachment representation, and reserved output all consume a context budget. Exact multimodal tokenization remains provider-authoritative.
- **Here:** [`validate_request`](./services/request_limits.py#L47-L123) uses a conservative local estimate and leaves headroom. Model policies use 128K/64K/32K local budgets, while output is capped at 8,192.
- **AWS:** Bedrock ultimately validates the real request.
- **Interview:** “My estimate is an admission guard, not an exact tokenizer.”
- **Follow-up:** Why trim complete pairs? To preserve role order and prevent half a conversation turn.

## 6.3 Prompt engineering

- **Plain:** prompts tell the model the task, context, tone, and output expectations.
- **Technical:** NovaMind combines a system prompt/persona, language instruction, conversation messages, attachment blocks, and current user text.
- **Here:** five templates and a custom override live in [`novamind/config/settings.py`](./novamind/config/settings.py#L25-L52); the summary action sends a structured summary instruction.
- **AWS:** system and message content are distinct Converse fields.
- **Interview:** “Prompt engineering is application behavior, but it is not a security boundary; model output remains untrusted.”
- **Follow-up:** How would you evaluate prompts? Create a versioned dataset, rubrics, regressions, and model-specific comparisons.

## 6.4 Inference parameters

- **Temperature:** sampling variability; lower is more deterministic, higher more diverse. It does not add truth or knowledge.
- **Maximum tokens:** upper bound reserved for generated output; a high value consumes context headroom and may increase latency/cost.
- **Here:** UI accepts temperature 0–1 and token choices up to 8,192; `bedrock_options` and `validate_request` check them again.
- **Interview:** “I validate controls both at configuration and full-request boundaries.”
- **Follow-up:** Why no top-p? It is not exposed in the current implementation; do not claim it is.

## 6.5 Multimodal AI

- **Plain:** one model request can contain more than text, such as an image or document.
- **Technical:** structured content blocks carry bytes plus an allowlisted format. Model capability policy must match retained and new content.
- **Here:** `_build_content_blocks` creates image/document/text blocks. Nova Micro and Groq policies reject attachments locally.
- **AWS:** Bedrock Converse provides a normalized multimodal message structure.
- **Interview:** “Multimodal means the model receives validated image/document bytes; this project does not perform OCR as a separate service.”
- **Follow-up:** Why validate decoded content? File extensions and magic bytes alone do not prove a safe, complete image/document.

## 6.6 Streaming responses

- **Plain:** show words as they arrive.
- **Technical:** the client consumes an event stream, validates sequence/content/terminal state, measures first-token latency, and closes resources on completion or cancellation.
- **Here:** Bedrock events include content deltas, stop, metadata, and error events. Groq uses SSE lines.
- **AWS:** `ConverseStream` is a long-lived Bedrock Runtime call; Streamlit/WebSocket keeps the UI interactive.
- **Interview:** “Streaming improves perceived latency but introduces partial-result and cleanup correctness.”
- **Follow-up:** What if the stream fails after 200 characters? Show incomplete text, close the stream, account if possible, and do not commit it to context.

## 6.7 Amazon Bedrock Converse API

- **Plain:** one consistent conversation interface for supported Bedrock models.
- **Technical:** messages have roles/content blocks; system prompts and inference config are separate; streaming returns typed events.
- **Here:** the service uses `converse_stream`, not legacy provider-specific JSON. Document names are neutralized before becoming `DocumentBlock.name`.
- **Interview:** “Converse reduces provider-specific formatting, but capability and model IDs still require local policy.”
- **Follow-up:** Does Converse make every model identical? No—features, access, limits, quality, and pricing still differ.

## 6.8 Model selection and routing

- **Plain:** choose the right model for the task.
- **Technical:** routing maps a UI label to a model ID/provider, applies capability/context policy, and creates the correct adapter.
- **Here:** `MODEL_OPTIONS`, `MODEL_PROVIDERS`, `provider_for_model`, and `get_ai_service` implement deterministic routing.
- **Interview:** “I never silently switch model families. Only Nova Pro has a documented one-attempt inference-profile fallback.”
- **Follow-up:** Why not fallback from Claude to Nova? It changes behavior, quality, policy, and possibly commercial assumptions without user consent.

## 6.9 Conversation memory and session history

- **Plain:** recent successful exchanges are sent again so the model can answer follow-ups.
- **Technical:** models are stateless between calls; the application reconstructs context. Display history and model history serve different purposes.
- **Here:** `chat_history` can include incomplete UI output; `bedrock_history` contains complete structured pairs. Up to 40 context messages are selected.
- **AWS:** no managed Bedrock memory service is used.
- **Interview:** “Conversation memory is an application data structure, not memory inside the model.”
- **Follow-up:** What happens on task restart? Unsaved in-memory state is lost; explicit optional persistence can reload a saved snapshot.

## 6.10 Document parsing and direct Q&A

- **Plain:** verify a document is what it claims to be, then let the model interpret it.
- **Technical:** cheap signatures precede bounded parser work; archive expansion, object count, filters, pages, time, and memory are controlled.
- **Here:** validated bytes go directly to Converse. No chunks, embeddings, vector database, retrieval, or citations exist.
- **Interview:** “Direct document understanding is the simplest correct design for one small document; RAG is justified by corpus retrieval requirements.”
- **Follow-up:** When would you add RAG? Many/large documents, cross-document search, fresh indexed corpora, citations, and retrieval evaluation.

## 6.11 Validation and token budgets

- **Plain:** reject unsafe or impossible requests before paying for inference.
- **Technical:** validation covers text, object structure, model capabilities, raw and encoded size, counts, context estimate, output reserve, and file internals.
- **Here:** upload validation and request admission are separate because a valid file can still make the whole conversation too large.
- **Interview:** “Validation is layered: browser filter, application file validator, full-request policy, then provider authority.”
- **Follow-up:** Why not silently drop history? That changes meaning; the app only trims the oldest complete pairs for defined budget conditions.

## 6.12 Responsible AI and security

- **Plain:** protect people/data and do not treat model output as guaranteed truth.
- **Technical:** authentication, authorization, least privilege, input limits, logging privacy, output handling, abuse controls, and evaluation are separate responsibilities.
- **Here:** safe errors/logs, private previews, session ownership, neutral filenames, and fail-closed validation are implemented. WAF, rate limiting, moderation, formal evals, and data-governance policy are future work.
- **Interview:** “Bedrock being managed does not automatically secure my application data path.”
- **Follow-up:** How do you handle prompt injection? Current defenses limit filename injection and isolate resources, but model-level prompt injection requires policy, content handling, tool authorization, and evaluation—especially before adding agents.

## 6.13 Why this is not agentic

An agent normally has a goal, iterative decision loop, tools/actions, observations, stopping policy, and often durable state. NovaMind has a single user request → model response flow. A future agentic version would require:

1. explicit tool schemas and allowlists;
2. server-side tool authorization using the verified user identity;
3. sandboxed execution and egress policy;
4. loop/step/time/cost limits;
5. human approval for consequential actions;
6. tool-result validation and prompt-injection defenses; and
7. traces/evaluations for plans, tool choices, and outcomes.

---

<a id="chapter-7--aws-services-and-design-decisions"></a>
# Chapter 7 — AWS Services and Design Decisions

## 7.1 Decision matrix

| Decision | Why selected | Alternative | Trade-off/security | Reliability, cost, and scale |
|---|---|---|---|---|
| **Bedrock** | AWS-native managed FM access and Converse streaming | Direct Anthropic/vendor API, SageMaker endpoint | Task-role governance and unified API; model availability still varies | Pay-per-use inference; quotas/throttling must be monitored |
| **Optional Groq** | Demonstrates provider abstraction and fast text streaming | Another vendor or Bedrock only | Adds external secret and egress/data boundary | Separate availability/billing; no project price estimate |
| **Cognito** | Managed user pool/token/MFA | Custom auth, Auth0, enterprise IdP | Reduces password responsibility; account recovery remains external | Usage-based pricing; availability affects login/verification |
| **ECS Fargate** | Long-running container/WebSocket without host management | EC2, Lambda, App Runner, EKS | Less host control; task role and network remain explicit | Pays while tasks run; service can replace tasks and scale |
| **CloudFront + VPC origin** | Public HTTPS edge while preserving private ALB | Public ALB, API Gateway | More configuration; minimizes direct origin exposure | Edge charges plus origin availability; WebSocket policies matter |
| **Internal ALB** | Stable target routing, health, ECS rollout | Direct task, NLB | Layer-7 features and hourly/LCU cost | Multi-AZ target routing; needs healthy tasks and correct timeouts |
| **ECR** | IAM-integrated private image source | GHCR/Docker Hub | Lifecycle/scanning must be configured | Storage/transfer costs; immutable SHA convention aids rollback |
| **CloudWatch Logs** | Native ECS logging/diagnosis | Datadog/Splunk/OpenSearch | Log privacy and retention are operator duties | Ingest/storage cost; alarms/dashboards not versioned here |
| **Secrets Manager** | Runtime secret storage/rotation controls | SSM, external vault | Application receives the value at runtime; task definition must not expose plaintext | Per-secret/API cost; rotation design is not implemented |
| **Optional DynamoDB** | Owner-scoped, conditional, bounded snapshots | RDS/Aurora, Redis, S3-only | Access patterns must match keys; not a live session store | On-demand scale/cost; strongly consistent reads used |
| **Optional S3** | Durable private attachment bytes and lifecycle | Database blobs/EFS | Bucket policy, BPA, TLS-only, lifecycle required | Cheap durable object storage; no transaction with DynamoDB |

## 7.2 Fargate versus Lambda

Reason from workload shape:

1. Streamlit runs a persistent server process.
2. Browser interaction relies on WebSocket/session continuity.
3. Model streams may be long-running.
4. File parsing can use subprocesses and memory ceilings.

Therefore Fargate fits the current code. Lambda would require redesigning UI hosting, session state, streaming integration, attachment flow, and time boundaries. Lambda could still be valuable for asynchronous document preprocessing or cleanup.

## 7.3 CloudFront plus internal ALB

CloudFront is the viewer-facing boundary; the internal ALB is the task-facing router. This is not duplication:

- CloudFront owns public HTTPS/edge behavior.
- VPC origin reaches a non-public load balancer.
- ALB owns target registration, health, and ECS task churn.

The price is operational complexity: WebSocket forwarding, cookies/query strings, timeouts, service security group, routes, and origin health must align.

## 7.4 Bedrock versus external APIs

Bedrock strengthens AWS IAM/governance and offers multiple models behind Converse. External APIs may offer particular latency/models but add vendor credentials, internet egress, different error/usage semantics, and another data-processing boundary. NovaMind exposes both patterns but does not pretend they have identical multimodal capabilities.

## 7.5 Security, reliability, cost, and scaling checklist

For every AWS service ask:

- What principal calls it?
- Which resource/actions are required?
- Which network path is required?
- What is encrypted in transit/at rest?
- What is logged, and could logs leak data?
- What happens during throttling/unavailability?
- What is the retry/idempotency policy?
- Which dimension drives cost?
- Which metric/alarm signals failure?
- Does adding replicas require state redesign?

---

<a id="chapter-8--docker-and-aws-deployment"></a>
# Chapter 8 — Docker and AWS Deployment

## 8.1 Dockerfile, instruction by instruction

| Lines | Instruction | Reason |
|---|---|---|
| [`1`](./Dockerfile#L1) | `python:3.14.6-slim-bookworm` | Match Python target in a smaller Debian runtime |
| [`3–7`](./Dockerfile#L3-L7) | Python/pip buffering/cache and container home environment | Predictable logs/runtime and less package-cache residue |
| [`9`](./Dockerfile#L9) | `/app` working directory | Stable import and command location |
| [`11–13`](./Dockerfile#L11-L13) | Create system user/group `10001` | Avoid running the application as root |
| [`15–17`](./Dockerfile#L15-L17) | Copy/install Linux lock and `pip check` | Separate platform lock and validate dependency consistency |
| [`19–24`](./Dockerfile#L19-L24) | Copy only runtime modules/config/logo with ownership | Avoid shipping tests/docs/local environments/secrets |
| [`27`](./Dockerfile#L27) | Import smoke check | Fail build if critical modules/runtime dependencies are missing |
| [`29–30`](./Dockerfile#L29-L30) | Non-root user and port 8501 | Least privilege and documented service port |
| [`32–33`](./Dockerfile#L32-L33) | Streamlit health check | Detect local process readiness |
| [`35`](./Dockerfile#L35) | Headless Streamlit on `0.0.0.0:8501` | Required for container network access |

## 8.2 Local port versus container port

`-p 8502:8501` means browser port 8502 maps to container port 8501. ECS/ALB instead registers the task's port 8501 in the target group. The Docker `EXPOSE` line documents the port; it does not publish it by itself.

## 8.3 ECR and immutable releases

CD derives `IMAGE_TAG` from `github.sha`. A full commit SHA ties code review, CI evidence, registry artifact, and task definition together. “Immutable” here is a release convention plus ECR behavior; the repository does not include an ECR tag-mutability policy export.

## 8.4 ECS task definition and roles

A task definition describes image, CPU/memory, ports, environment/secrets, log configuration, roles, and other runtime settings. CD fetches the current definition and replaces only the application image. This intentionally preserves live configuration but also means configuration is not version-controlled here.

- **Execution role:** image pull/log bootstrap.
- **Task role:** calls made by Python.
- **Secret references:** ECS resolves secret values for the container.

## 8.5 Health and deployment revisions

Three checks are different:

1. Docker health: local process answers `/_stcore/health`.
2. Target health: ALB can reach the task on 8501 and receives acceptable health responses.
3. Application readiness: authentication, egress, secrets, IAM, and model access work.

A new task-definition revision is registered for each image update. The ECS service rolls from old to new tasks. The workflow waits for service stability and verifies the primary rollout, task ARN, and image URI.

## 8.6 CloudWatch troubleshooting order

1. GitHub Actions step/error.
2. ECS service events and deployment rollout reason.
3. Stopped-task reason/container exit code.
4. Target-group health reason.
5. CloudWatch startup/application JSON logs.
6. Task definition: image, roles, secrets, port, log driver.
7. Security groups/routes/DNS/egress.
8. Cognito/Bedrock/Groq-specific configuration and authorization.

---

<a id="chapter-9--github-actions-cicd"></a>
# Chapter 9 — GitHub Actions CI/CD

![NovaMind AI AWS architecture with CI/CD](./project-pic/NovaMind-AI-AWS-Architecture-Blueprint-with-cicd.png)

## 9.1 Git and GitHub fundamentals in this project

- Git records content snapshots identified by commits.
- `main` is the protected deployment source in workflow logic.
- CI validates a commit; CD must deploy the same SHA to preserve traceability.
- A Docker image is another artifact. Tagging it with the commit SHA links artifact to source.

Repository authorship metadata attributes all six current commits to `aamir490`. This supports saying “I built and configured this repository,” but Git metadata alone cannot prove every external infrastructure action or sole authorship beyond the repository evidence.

## 9.2 CI workflow

[`.github/workflows/ci.yml`](./.github/workflows/ci.yml#L1-L49) triggers on push to `main` and pull requests targeting `main`.

### Python Tests job

- Windows runner, 15-minute timeout.
- Python 3.14.6.
- Install `requirements.txt`; run `pip check`.
- Run `python -B -m tests.run_offline`.

The offline guard patches DNS, TCP/UDP, boto/botocore client creation, credential resolution, and API calls. It records attempts and fails even if application code swallows the immediate exception. It is a process-level regression guard, not an OS network sandbox.

### Docker Build job

- Ubuntu runner, depends on `test`.
- Builds `novamind-ai:ci`.
- Does not push to ECR.

The architecture image mentions “linting/checks,” but the actual workflow has no dedicated linter, SAST, coverage, or vulnerability gate. Always describe the YAML, not the label in a diagram.

## 9.3 Verified CI engineering change

Git history proves one real correction. The original CI commit used Ubuntu, Python `3.14`, `requirements-linux.txt`, and bare unittest discovery. Commit `fbe64fd` changed it to Windows, exact Python `3.14.6`, `requirements.txt`, and the guarded runner. The lesson: **the test job must match the supported local dependency baseline, while the separate Docker job validates Linux.**

## 9.4 Manual CD workflow

[`.github/workflows/cd.yml`](./.github/workflows/cd.yml#L1-L207) uses only `workflow_dispatch`.

1. `contents: read`, `id-token: write`, and `actions: read` are granted.
2. Concurrency serializes deployments without canceling an active one.
3. The job rejects refs other than `main`.
4. GitHub's API must show a completed successful push-triggered CI run for the exact SHA.
5. `configure-aws-credentials` exchanges a GitHub OIDC token for the deployment role.
6. The job logs into ECR.
7. It validates/reuses or builds/pushes the SHA-tagged image.
8. It downloads the active task definition and uses `jq` to change only the named container image.
9. A second `jq` expression verifies no other task configuration drifted.
10. It registers the revision, updates the service, waits for stability, and verifies rollout/revision/image.

## 9.5 OIDC and IAM trust

OIDC removes long-lived AWS keys from GitHub. The trust relationship should validate:

- issuer/token provider;
- audience (`sts.amazonaws.com` for the standard action);
- repository identity;
- permitted branch/ref or environment; and
- optionally workflow/environment claims.

The workflow's `id-token: write` permission is source-verified. The AWS trust policy and any “customized immutable subject” are **not present in this repository**, and no commit/log documents an OIDC-subject incident. Treat exact subject customization as a troubleshooting scenario, not a claimed challenge.

## 9.6 ECS circuit breaker and rollback

The architecture diagram states rolling deployment with circuit breaker and automatic rollback. The workflow calls `update-service` but does not enable or inspect `deploymentCircuitBreaker`. Therefore:

- **If enabled on the live service:** ECS can fail a deployment and roll back to the last completed deployment.
- **What CD verifies:** the service stabilizes and the expected primary task revision/image is running.
- **What the repository cannot prove:** that the circuit breaker is currently enabled.

Also remember: code rollback cannot restore an unsaved in-memory user session.

## 9.7 Troubleshooting failed CI/CD

| Failure point | Checks |
|---|---|
| Python setup/install | Exact 3.14.6 availability, Windows lock, package index/wheels, `pip check` conflict |
| Offline tests | First assertion, forbidden-operation list, environment contamination, duplicate test IDs |
| Docker build | Linux wheel availability, import smoke check, build context, non-root paths |
| CI verification in CD | Main ref, exact SHA, push event, successful workflow ID/run, token `actions:read` |
| OIDC assume role | `id-token:write`, provider/audience, repo/ref subject condition, role name, session policy |
| ECR | repository/action permissions, login region/account, immutable tag/digest, network |
| Task registration | `iam:PassRole`, `ecs:DescribeTaskDefinition`, `ecs:RegisterTaskDefinition`, valid JSON, container name |
| Service update | cluster/service name, `ecs:UpdateService`, new revision, deployment concurrency |
| Stability | task startup, image pull, secrets, logs, CPU/memory, port/health, SG/routes |
| Final verification | primary rollout state, exact task-definition ARN, exact image URI |

`iam:PassRole` errors are common when registering task definitions, but no repository evidence proves a real ECS IAM-permission incident occurred here. Explain it as a realistic diagnostic: the deploy role may register a definition only if it may pass the task/execution roles to ECS.

---

<a id="chapter-10--troubleshooting-and-real-engineering-challenges"></a>
# Chapter 10 — Troubleshooting and Real Engineering Challenges

## 10.1 Evidence-backed events

### Event A — CI did not match the supported test platform

- **Evidence:** commits `e40f4dc` and `fbe64fd`.
- **Original state:** Ubuntu, Python 3.14, Linux requirements, bare discovery.
- **Fix:** Windows, exact 3.14.6, Windows lock, canonical guarded runner.
- **Lesson:** align functional CI with the declared supported environment; validate the Linux target separately through Docker.

### Event B — CI/CD documentation artifacts were added and renamed

- **Evidence:** commits `922c5d3` and `157e431`.
- **Change:** five CI/CD screenshots were added and two architecture files received clear with/without-CI/CD names.
- **Lesson:** operational evidence and clear artifact names improve review, but diagrams are not executable infrastructure.

## 10.2 Implemented defenses, not proven incidents

The following are strong engineering work, but the repository does not prove each began as a production outage:

- Nova Pro `AccessDeniedException` fallback;
- incomplete stream isolation and cleanup;
- neutral document names and parser ceilings;
- stale Streamlit upload callback rejection;
- exact Cognito token/session ownership checks;
- retrying only bounded idempotent reads;
- safe JSON logging without prompts/provider details;
- DynamoDB version conflicts and S3/Dynamo non-transactional cleanup.

Phrase them as: **“I identified this failure mode and implemented/tested a defense.”** Do not say: **“This caused a production incident”** unless you have separate evidence.

## 10.3 Deployment/networking scenarios to practice

### Page loads but chat disconnects

Reason through viewer → CloudFront behavior/origin policy → VPC origin → ALB idle timeout/stickiness → task health/logs. WebSocket and session routing differ from a one-time health request.

### Bedrock access denied

Identify selected model and actual invoked resource, then check task role, model access/region, and whether Nova Pro qualifies for the single profile fallback. Do not add broad permissions or substitute another model silently.

### Groq fails only in ECS

Check model selection, runtime `GROQ_API_KEY` secret reference, task execution/task role access to secret injection, network egress/DNS, and safe HTTP category. Never print the key.

### New task never becomes healthy

Check ECR pull, architecture/runtime, command/import error, secret/config absence, port 8501, health path, target SG, and CloudWatch. Docker health success locally does not prove VPC/model access.

### OIDC `AssumeRoleWithWebIdentity` denied

Decode only non-secret token claims in an approved diagnostic context, compare issuer/audience/subject to the role trust conditions, confirm repository/ref/environment, and avoid weakening the trust to `repo:*` as a shortcut.

## 10.4 The STAR structure for a challenge answer

- **Situation:** name a verified mismatch or risk.
- **Task:** state the correctness/security outcome needed.
- **Action:** explain the precise code/workflow/config change.
- **Result:** cite a test, commit diff, workflow verification, or known boundary.

Example:

> “The first CI configuration used a Linux test runner, but the repository's functional baseline was Windows CPython 3.14.6 and its guarded runner. I changed CI to the exact Windows/Python/dependency combination and invoked `tests.run_offline`, while retaining a separate Ubuntu Docker job to test Linux image construction. That made platform intent explicit and kept cloud/network access blocked during regression tests.”

---

<a id="chapter-11--project-interview-questions-and-answers"></a>
# Chapter 11 — Project Interview Questions and Answers

## Foundations and ownership

### 1. Tell me about NovaMind AI.

- **Evaluates:** concise ownership and system thinking.
- **Concept:** describe problem, users, core flow, architecture, and one differentiator.
- **Project answer:** “It is an authenticated multimodal Streamlit workspace using Bedrock streaming, optional Groq text inference, ECS/Fargate, private CloudFront-to-ALB ingress, and guarded CI/manual CD. Its differentiator is the reliability/security around inference.”
- **Possible follow-up:** What is your strongest engineering decision?
- **Avoid:** listing AWS logos without explaining data flow or boundaries.

### 2. What problem were you solving?

- **Evaluates:** product reasoning.
- **Concept:** engineering begins with a user/job and constraints.
- **Project answer:** “One secure interface for conversation, image analysis, and one-document Q&A, while demonstrating auth, validation, streaming correctness, deployment, and observability.”
- **Possible follow-up:** Who is the target user?
- **Avoid:** claiming universal enterprise knowledge management or RAG.

### 3. What was your contribution?

- **Evaluates:** honesty and technical ownership.
- **Concept:** connect first-person claims to evidence.
- **Project answer:** “The repository metadata attributes the application baseline and all later CI/CD/documentation commits to my GitHub identity. I can explain the Python layers, validation, auth, Docker, workflows, and architecture evidence. Live infrastructure provisioning steps are not committed as IaC, so I distinguish those.”
- **Possible follow-up:** Which code would you open first?
- **Avoid:** claiming unrecorded incidents or unverifiable team roles.

### 4. How is it more than a basic chatbot?

- **Evaluates:** engineering depth.
- **Concept:** production-style AI includes identity, data, failure, and operations.
- **Project answer:** cite Cognito/session scopes, multimodal validators, capability budgets, transactional stream commit, usage/log privacy, non-root container, offline guards, and exact-artifact CD.
- **Possible follow-up:** Which feature was hardest?
- **Avoid:** answering only “it supports images.”

### 5. Is NovaMind an agentic AI system?

- **Evaluates:** terminology discipline.
- **Concept:** agents iteratively choose tools/actions toward goals.
- **Project answer:** “No. It is request-response generative AI with conversation context. It has no tool execution, planner, action loop, or autonomous goal.”
- **Possible follow-up:** How would you make it agentic safely?
- **Avoid:** calling model routing or personas “agents.”

### 6. What are the current limitations?

- **Evaluates:** maturity.
- **Concept:** strong engineers know system boundaries.
- **Project answer:** in-memory live sessions, optional rather than default persistence, direct single-document Q&A, text-only Groq, no IaC/load tests/WAF/tracing/tool use, and unverified live network/policy details.
- **Possible follow-up:** Which limitation would you fix first?
- **Avoid:** saying “fully production-ready.”

## Python and Streamlit

### 7. Why Python?

- **Evaluates:** stack selection.
- **Concept:** language choice balances ecosystem, team skill, runtime, and delivery speed.
- **Project answer:** Python supports Streamlit, boto3, Pillow, pypdf, tests, and shared validation/provider logic with one runtime.
- **Possible follow-up:** What Python risk did you manage?
- **Avoid:** “Python is always best”; mention CPU/memory/parser and concurrency trade-offs.

### 8. Why Streamlit?

- **Evaluates:** framework fit.
- **Concept:** optimize for interactive AI delivery versus custom frontend control.
- **Project answer:** native chat, upload, sidebar, session state, and streaming made it effective for this portfolio workspace.
- **Possible follow-up:** When would you migrate?
- **Avoid:** ignoring rerun semantics or WebSocket/session scaling.

### 9. How does a Streamlit rerun affect your design?

- **Evaluates:** framework understanding.
- **Concept:** widget events rerun the script while session state persists.
- **Project answer:** stable scoped state, generation-keyed uploader keys, cached service ownership, idempotent rendering, and stale-callback checks prevent duplicate/adopted work.
- **Possible follow-up:** How do you prevent duplicate submissions?
- **Avoid:** describing it like a traditional request controller.

### 10. Why modularize the Streamlit file?

- **Evaluates:** maintainability/testability.
- **Concept:** separate UI, workflow, domain rules, and external services.
- **Project answer:** the launcher is stable; `novamind/ui`, `domain`, `orchestration`, and `services` isolate responsibilities and allow offline tests without rendering the page.
- **Possible follow-up:** Where should new business logic go?
- **Avoid:** equating more files with good architecture without dependency rules.

### 11. Why maintain two histories?

- **Evaluates:** correctness.
- **Concept:** displayed events and trusted model context have different contracts.
- **Project answer:** `chat_history` can show failed/incomplete output; `bedrock_history` contains only completed structured pairs.
- **Possible follow-up:** What happens after a partial stream?
- **Avoid:** replaying partial text as if it were a completed model answer.

### 12. How do you prevent stale session work from committing?

- **Evaluates:** concurrency/authorization thinking.
- **Concept:** capture an operation scope, then revalidate before publishing.
- **Project answer:** `capture_scope`/`check_scope` surround upload parsing, service creation, streaming, cleanup, and result publication; conversation rotation invalidates old operations.
- **Possible follow-up:** Is this a database transaction?
- **Avoid:** calling Streamlit state thread-safe distributed locking.

## Generative AI and models

### 13. What is a foundation model?

- **Evaluates:** basic AI knowledge.
- **Concept:** broadly pre-trained model adaptable through prompting/inference.
- **Project answer:** NovaMind consumes managed Nova/Claude through Bedrock and configured Groq models; it does not train them.
- **Possible follow-up:** Fine-tuning versus prompting?
- **Avoid:** claiming ownership of model training.

### 14. Why Amazon Bedrock?

- **Evaluates:** managed AI design.
- **Concept:** model access, AWS identity/governance, unified APIs.
- **Project answer:** Converse streaming handles supported text/multimodal models through boto3 and task-role authorization.
- **Possible follow-up:** Why not call Anthropic directly?
- **Avoid:** saying all Bedrock models have identical capabilities/cost.

### 15. What is the Converse API?

- **Evaluates:** Bedrock API understanding.
- **Concept:** common message/system/inference/content-block contract.
- **Project answer:** NovaMind sends role-based messages and optional image/document blocks, then consumes typed stream events.
- **Possible follow-up:** What remains model-specific?
- **Avoid:** confusing Converse with persistent server-side memory.

### 16. How does streaming work?

- **Evaluates:** event-driven correctness.
- **Concept:** yield deltas while validating stream sequence and completion.
- **Project answer:** Bedrock text deltas update the UI; stop and metadata finalize status/usage; cleanup runs in `finally`; history commits after successful completion.
- **Possible follow-up:** How is first-token latency measured?
- **Avoid:** treating any closed stream as success.

### 17. Explain temperature and max tokens.

- **Evaluates:** inference literacy.
- **Concept:** temperature controls sampling variability; max tokens bounds output.
- **Project answer:** UI values are validated 0–1 and 1–8,192, with output included in context admission.
- **Possible follow-up:** Why does a high max-token setting matter before generation?
- **Avoid:** saying temperature controls factuality directly.

### 18. How do you choose a model?

- **Evaluates:** routing/trade-offs.
- **Concept:** match capabilities, quality, latency, cost, context, and entitlement.
- **Project answer:** labels map to allowlisted IDs; request policy blocks incompatible attachments; user explicitly selects rather than hidden cross-family routing.
- **Possible follow-up:** Why Nova Micro?
- **Avoid:** choosing solely by benchmark headline.

### 19. Explain the Nova Pro fallback.

- **Evaluates:** controlled resilience.
- **Concept:** retries/fallbacks must preserve semantics and avoid duplicates.
- **Project answer:** exactly one fallback from base Nova Pro to the US inference profile, only on first-call access denial and before output. No fallback for other models or after output.
- **Possible follow-up:** Why not fallback on throttling?
- **Avoid:** calling it a general retry mechanism.

### 20. How is conversation context managed?

- **Evaluates:** LLM statelessness/context budgets.
- **Concept:** resend recent completed turns within a bounded window.
- **Project answer:** up to 40 model messages, oldest complete pairs trimmed only for approved budget conditions after each pair is independently validated.
- **Possible follow-up:** Would summarization memory help?
- **Avoid:** saying the model remembers users automatically.

### 21. Why is Groq text-only here?

- **Evaluates:** capability discipline.
- **Concept:** a common interface does not guarantee common features.
- **Project answer:** its adapter serializes text blocks; model policy has empty image/document capabilities and rejects before network.
- **Possible follow-up:** How add a multimodal provider?
- **Avoid:** sending bytes that the adapter silently discards.

### 22. How do you track tokens and cost?

- **Evaluates:** observability/financial honesty.
- **Concept:** use provider metadata and versioned rates; preserve unknown states.
- **Project answer:** each attempt stores reported tokens and a frozen configured-rate estimate. Missing/inconsistent metadata produces unknown, not zero.
- **Possible follow-up:** Is it an AWS billing system?
- **Avoid:** quoting estimates as invoices or current public pricing.

## Multimodal processing

### 23. How are images processed?

- **Evaluates:** validation depth.
- **Concept:** extension/signature/decode/dimension/resource limits are layered.
- **Project answer:** max 3.75 MiB, magic check, full Pillow decode, 8,000 px/side, pixel/frame ceilings, then private thumbnail and raw Bedrock bytes.
- **Possible follow-up:** Why full decode?
- **Avoid:** trusting filename extension.

### 24. How are documents processed?

- **Evaluates:** untrusted-file handling.
- **Concept:** validate format/structure under bounded resources before inference.
- **Project answer:** 4.5 MiB cap, signature checks, isolated PDF/Office validation, previews, and a neutral `Document N` API name.
- **Possible follow-up:** Why neutral names?
- **Avoid:** claiming malware scanning exists.

### 25. Why use direct document understanding instead of RAG?

- **Evaluates:** architecture restraint.
- **Concept:** match retrieval complexity to requirements.
- **Project answer:** one bounded document can be sent directly to Converse, avoiding chunking/indexing/retrieval failure modes. RAG is future work for corpora/citations.
- **Possible follow-up:** Design the RAG extension.
- **Avoid:** calling direct attachment Q&A “RAG.”

### 26. What is the difference between upload validation and request validation?

- **Evaluates:** layered defense.
- **Concept:** an object may be valid alone but invalid in aggregate/context.
- **Project answer:** file services validate bytes; `validate_request` checks model capability, retained content, counts, serialized payload, output, and context.
- **Possible follow-up:** Why base64-size estimation?
- **Avoid:** assuming Streamlit's uploader filter is security.

### 27. How do you prevent parser resource exhaustion?

- **Evaluates:** denial-of-service awareness.
- **Concept:** bound decompression, members, pages, objects, time, and memory.
- **Project answer:** `services/document_parser.py` limits archive expansion/ratios/parts, PDF pages/objects/filters, and runs through a bounded worker path.
- **Possible follow-up:** What remains for production?
- **Avoid:** claiming the validator is an antivirus.

## Authentication and security

### 28. How does Cognito login work?

- **Evaluates:** authentication flow.
- **Concept:** user credentials go to the IdP; the app receives and verifies a token.
- **Project answer:** `InitiateAuth` with `USER_PASSWORD_AUTH`, supported SMS/TOTP challenges, access token checks plus authoritative `GetUser`, then scoped session establishment.
- **Possible follow-up:** Where is password recovery?
- **Avoid:** saying the app stores passwords.

### 29. Why is local JWT decoding not enough?

- **Evaluates:** token security.
- **Concept:** parsing claims is not proof of signature/revocation/authoritative identity.
- **Project answer:** strict decoding rejects bad context, but `GetUser` for the exact access token must succeed and match subject/username.
- **Possible follow-up:** Could you verify JWKS locally?
- **Avoid:** calling Base64 decoding authentication.

### 30. Authentication versus authorization?

- **Evaluates:** security fundamentals.
- **Concept:** identity proof versus permitted resource access.
- **Project answer:** Cognito authenticates; `DataScope` and owner-scoped storage authorize histories, attachments, clients, exports, and saved records.
- **Possible follow-up:** What is an IDOR?
- **Avoid:** trusting a browser-supplied owner ID.

### 31. How are AWS credentials supplied?

- **Evaluates:** credential hygiene.
- **Concept:** workloads should use short-lived role credentials rather than embedded access keys.
- **Project answer:** local development can use the normal AWS SDK credential chain; on ECS, the intended mechanism is the task role. No credential should be baked into the image or committed to Git.
- **Possible follow-up:** What is credential rotation?
- **Avoid:** presenting a `.env` file as an acceptable place for permanent production keys.

### 32. How are application secrets managed?

- **Evaluates:** secret lifecycle understanding.
- **Concept:** secrets need controlled storage, least-privilege retrieval, rotation, and log redaction.
- **Project answer:** the architecture includes Secrets Manager for runtime secrets such as an optional Groq key. The task role needs narrowly scoped read access; the exact deployed secret names and policies are not exported in this repository.
- **Possible follow-up:** Secrets Manager versus Parameter Store?
- **Avoid:** claiming every configuration value is a secret.

### 33. How do session expiry and logout work?

- **Evaluates:** session security.
- **Concept:** idle and absolute lifetimes limit stolen-session exposure.
- **Project answer:** `services/auth_service.py` defaults to a 900-second idle and 3,600-second absolute timeout; the UI watchdog periodically checks expiry. Logout clears authentication and scoped session data.
- **Possible follow-up:** What changes in a multi-instance deployment?
- **Avoid:** assuming Streamlit browser state is a durable central session store.

### 34. How would you address prompt injection and unsafe output?

- **Evaluates:** responsible-AI maturity.
- **Concept:** prompt injection is an instruction-integrity problem; content safety and output authorization are separate controls.
- **Project answer:** NovaMind validates input structure and isolates user ownership, but the repository does not demonstrate a complete guardrail/policy enforcement layer. Production hardening could add Bedrock Guardrails, content policy, output encoding, audit events, and tool authorization if tools are ever introduced.
- **Possible follow-up:** Why does validation not stop prompt injection?
- **Avoid:** claiming file-type validation makes model content safe.

## AWS networking and runtime

### 35. Why CloudFront in front of an internal ALB?

- **Evaluates:** edge-to-private-origin design.
- **Concept:** CloudFront can be the public edge while a VPC origin connects to a non-public load balancer.
- **Project answer:** the diagrams show HTTPS/WebSocket clients reaching CloudFront, then a CloudFront VPC Origin, then an internal ALB and Fargate task. This reduces direct origin exposure and gives an edge control point.
- **Possible follow-up:** Why not expose the ALB publicly?
- **Avoid:** calling an internal ALB internet-facing.

### 36. Explain the VPC and subnet design.

- **Evaluates:** network boundaries.
- **Concept:** subnets divide address space and routing domains; “public” means a route to an internet gateway, not simply a public-looking label.
- **Project answer:** the diagrams label VPC `10.20.0.0/16`, two public subnet tiers and two private subnet tiers across Availability Zones. They place the internal ALB/application path in the private design. Exact live route tables, task subnet IDs, public-IP settings, NAT gateways, and VPC endpoints are not stored in the repository.
- **Possible follow-up:** How does a private task call Groq?
- **Avoid:** inventing NAT or endpoint configuration.

### 37. How should security groups be designed?

- **Evaluates:** least-privilege networking.
- **Concept:** security groups are stateful allow lists that can reference one another.
- **Project answer:** the intended pattern is origin-to-ALB access only, ALB-to-task TCP 8501 only, and controlled task egress for AWS APIs and optional Groq HTTPS. Exact deployed rules remain an infrastructure verification item.
- **Possible follow-up:** Security groups versus network ACLs?
- **Avoid:** opening task port 8501 to the internet.

### 38. Why do WebSockets matter for Streamlit?

- **Evaluates:** protocol-aware troubleshooting.
- **Concept:** Streamlit maintains an interactive browser/server channel; proxies must preserve upgrade and long-lived connection behavior.
- **Project answer:** CloudFront behavior, origin protocol, ALB listener/target health, and timeout settings must support the Streamlit channel. A page shell can load while interaction still fails if that path is misconfigured.
- **Possible follow-up:** What would you inspect first?
- **Avoid:** diagnosing every disconnect as an LLM error.

### 39. Why ECS Fargate instead of Lambda?

- **Evaluates:** compute-selection reasoning.
- **Concept:** Fargate runs long-lived containers; Lambda is event-oriented and time-bounded.
- **Project answer:** Streamlit is a stateful, continuously running web process with streaming connections, so Fargate maps naturally to its runtime. Lambda could suit decoupled asynchronous jobs, but not this UI without redesign.
- **Possible follow-up:** Why not EC2?
- **Avoid:** claiming Lambda cannot stream in any architecture.

### 40. What is the difference between an ECS execution role and task role?

- **Evaluates:** IAM precision.
- **Concept:** the execution role helps ECS launch the container; the task role authorizes application code.
- **Project answer:** the execution role needs operations such as pulling from ECR and writing configured logs. The task role should cover Bedrock, Cognito, Secrets Manager, and optional DynamoDB/S3 operations actually used by NovaMind.
- **Possible follow-up:** Which role needs `bedrock:ConverseStream`?
- **Avoid:** putting all permissions into one administrator role.

### 41. What security choices are visible in the Dockerfile?

- **Evaluates:** container hardening.
- **Concept:** minimize image surface, pin runtime, avoid root, expose only the service port, and provide health probes.
- **Project answer:** it uses Python 3.14.6 slim-bookworm, installs required Linux libraries, creates UID 10001, runs as the non-root user, exposes 8501, and health-checks `/_stcore/health`.
- **Possible follow-up:** What else would you add?
- **Avoid:** equating a non-root process with complete container security.

### 42. Why use immutable ECR image tags?

- **Evaluates:** deployment traceability.
- **Concept:** a release should identify exact bytes, not a movable label.
- **Project answer:** CD uses the full Git commit SHA as the ECR tag and resolves the image digest. That connects source, CI result, registry artifact, task definition revision, and rollback target.
- **Possible follow-up:** Tag versus digest?
- **Avoid:** deploying only `latest`.

## CI/CD

### 43. What do the offline AWS/network guards prove?

- **Evaluates:** test isolation.
- **Concept:** deterministic unit/regression tests should fail if they accidentally contact external systems.
- **Project answer:** `tests/run_offline.py` installs guards and runs the suite without requiring cloud credentials. This validates local logic and mocks, not live AWS permissions or provider availability.
- **Possible follow-up:** What still needs integration tests?
- **Avoid:** interpreting offline success as deployment success.

### 44. Why does CI test on Windows but build Docker on Ubuntu?

- **Evaluates:** workflow comprehension.
- **Concept:** jobs can validate different delivery surfaces.
- **Project answer:** the test job uses `windows-latest` and exact Python 3.14.6 with `requirements.txt`; after it succeeds, a separate Ubuntu job builds the Linux container. Git history shows CI was corrected to this exact path.
- **Possible follow-up:** Would you add a matrix?
- **Avoid:** saying tests run inside the production image when this workflow does not do that.

### 45. Why is CD manual?

- **Evaluates:** release-governance awareness.
- **Concept:** continuous delivery can retain a human promotion decision.
- **Project answer:** `.github/workflows/cd.yml` has only `workflow_dispatch` and no custom SHA input. It permits only a run dispatched from `main`, uses that run's `github.sha`, and verifies that exact commit had a successful push CI run before deployment.
- **Possible follow-up:** How would you automate promotion safely?
- **Avoid:** saying CD automatically starts after CI.

### 46. How does GitHub OIDC improve AWS authentication?

- **Evaluates:** federated identity knowledge.
- **Concept:** GitHub exchanges a signed, short-lived identity token for an AWS role session.
- **Project answer:** CD requests `id-token: write` and uses AWS credential configuration through OIDC, removing the need for stored long-lived AWS access keys. The exact live trust-policy conditions must be checked in IAM.
- **Possible follow-up:** What claims would you restrict?
- **Avoid:** asserting a customized immutable `sub` trust condition was deployed; no repository evidence proves that incident/configuration.

### 47. Why verify successful CI for the exact SHA?

- **Evaluates:** supply-chain controls.
- **Concept:** approval of one commit must not be reused to deploy another.
- **Project answer:** CD queries the successful `push` CI runs and requires a match for the selected SHA. A successful branch run at some other commit is insufficient.
- **Possible follow-up:** What race conditions remain?
- **Avoid:** verifying only the branch name.

### 48. Why validate that only the task-definition image changed?

- **Evaluates:** change control.
- **Concept:** deployment automation should mutate the minimum intended field.
- **Project answer:** the workflow downloads the active task definition, creates the new revision with the SHA/digest image, and checks that non-image fields remain unchanged before registration.
- **Possible follow-up:** When should infrastructure fields change?
- **Avoid:** silently editing CPU, IAM roles, environment, or network settings during an app release.

### 49. How does rollback work?

- **Evaluates:** recovery accuracy.
- **Concept:** ECS can stop a failed rolling deployment and, when configured, roll back to the last completed deployment.
- **Project answer:** the architecture/deployment documentation expects an ECS deployment circuit breaker with rollback on the service. The current CD workflow waits and verifies but does not create or prove that service setting; it is a live prerequisite to verify.
- **Possible follow-up:** How would you perform a manual rollback?
- **Avoid:** claiming the YAML itself enables automatic rollback.

### 50. What does “wait for service stability” prove?

- **Evaluates:** deployment validation.
- **Concept:** scheduler convergence is necessary but not the same as business-level correctness.
- **Project answer:** CD waits for ECS stability, then verifies deployment/task-definition state. ALB target health and Streamlit health support rollout decisions, but a separate post-deploy smoke test would provide stronger end-user assurance.
- **Possible follow-up:** What smoke test would you add?
- **Avoid:** treating stable tasks as proof that Bedrock and Cognito work.

## Operations, scale, and evolution

### 51. How is the application observable?

- **Evaluates:** operations design.
- **Concept:** logs, metrics, traces, health, and audit evidence answer different questions.
- **Project answer:** the app emits structured events, preserves provider attempts and usage estimates, exposes a health endpoint, and the architecture uses CloudWatch for container logs. Full dashboards, alarms, tracing, and retention settings are not versioned here.
- **Possible follow-up:** What would you alert on?
- **Avoid:** logging prompts, tokens, or document content without a privacy policy.

### 52. What drives cost and how can it be optimized?

- **Evaluates:** FinOps thinking.
- **Concept:** separate fixed runtime/edge/network cost from variable inference/storage/logging cost.
- **Project answer:** Fargate uptime, ALB/CloudFront traffic, logs, storage, Secrets Manager, Bedrock tokens, and Groq plan usage can contribute. Optimize model choice, output limits, history, task sizing/autoscaling, cache/log retention, and architecture only after measuring.
- **Possible follow-up:** Which cost is likely workload-sensitive?
- **Avoid:** quoting a monthly figure without region, load, retention, and pricing calculations.

### 53. How would you scale to thousands of users?

- **Evaluates:** systems thinking.
- **Concept:** scale compute, remove node-local state, control downstream quotas, and measure saturation.
- **Project answer:** run multiple tasks across AZs with ECS target tracking, make sessions recoverable through validated shared persistence, externalize attachments/history appropriately, test load-balancer stickiness assumptions, queue long jobs, enforce per-user quotas, and request Bedrock limits based on measurements.
- **Possible follow-up:** What becomes the first bottleneck?
- **Avoid:** saying “just increase task count.”

### 54. How would you troubleshoot a Bedrock failure?

- **Evaluates:** layered diagnosis.
- **Concept:** classify configuration, identity, authorization, model access, throttling, payload, networking, and provider faults separately.
- **Project answer:** correlate the UI-safe error with structured logs/attempt records; verify region/model ID, task role, Bedrock access, request size/capability, and network reachability. For Nova Pro only, inspect whether the tightly controlled profile fallback was eligible.
- **Possible follow-up:** What should the user see?
- **Avoid:** displaying raw AWS exceptions or automatically switching to a different model.

### 55. What are the highest-value production improvements?

- **Evaluates:** prioritization and honesty.
- **Concept:** prioritize by risk and measurable user value.
- **Project answer:** codify infrastructure, verify/export network and IAM configuration, add WAF/guardrails where justified, centralize production session persistence, add integration/smoke/load tests, instrument metrics/alarms/tracing, scan/sign images, and automate promotion only after governance is defined.
- **Possible follow-up:** What would you do first?
- **Avoid:** proposing a large rewrite without tying it to a known limitation.

---

<a id="chapter-12--how-to-defend-my-project-in-an-interview"></a>

# Chapter 12 — How to Defend My Project in an Interview

## Do not memorize—reason from evidence

Use this five-part answer pattern:

1. **Claim:** state the decision in one sentence.
2. **Evidence:** point to a file, workflow, diagram, test, or observed behavior.
3. **Mechanism:** explain how data/control moves through it.
4. **Boundary and trade-off:** say what it does not prove or what it costs.
5. **Next step:** offer the most sensible production improvement.

Example: “I chose Fargate because Streamlit is a long-running container with streaming browser sessions. The Dockerfile starts it on port 8501, and the architecture routes an ALB target to that task. Fargate removes host management, although it is not automatically the cheapest at every load. I would tune task size and target tracking from measured CPU, memory, connection count, and latency.”

## Scenario playbook

### Why did you choose Streamlit?

Reason from the requirement: this is an AI interaction portfolio application, so rapid Python-native iteration and built-in chat/file widgets were valuable. Connect that to `novamind/ui/app.py`, `novamind/ui/sidebar.py`, and `novamind/ui/chat.py`. Then name the trade-off: Streamlit couples UI execution and server-side session behavior; a large consumer product might separate a web frontend from stateless APIs.

### Why use ECS Fargate instead of Lambda?

Start with workload shape, not preference. Streamlit is continuously running, exposes port 8501, maintains an interactive connection, and streams output. Fargate supports that container shape directly. Lambda becomes attractive for short asynchronous transformations or event-driven background work, not as a drop-in replacement for this process.

### Why do you need both CloudFront and an ALB?

They solve different problems. CloudFront is the public edge and VPC-origin entry; the internal ALB performs VPC-side target routing and health checks to ECS tasks. Acknowledge that the exact distributions, behaviors, listeners, and SGs are live configuration and are not reproducible from IaC in the repository.

### Explain the VPC and subnet architecture

Use the diagram as a declared design: two-AZ VPC, public/private subnet tiers, VPC origin, internal ALB, and Fargate application path. Explicitly say that public/private labels depend on route tables. Do not invent whether tasks have public IPs or whether outbound access uses NAT or VPC endpoints.

### How is the backend secured?

Describe layers: CloudFront as public entry, private-origin path, internal ALB, SG-to-SG restriction, non-root task, Cognito identity verification, owner-scoped session/storage objects, strict file/request validation, role-based AWS access, secret retrieval, and redacted logs. Separate coded controls from diagrammed/live controls.

### How do you manage secrets?

Say what is verifiable: configuration validates secret references and the diagram includes Secrets Manager; no secret values belong in Git or the image. On ECS, the task should receive only permission to the required secret. Do not show names/ARNs in an interview unless deliberately sanitized.

### What happens if Amazon Bedrock fails?

The stream adapter records an attempt and exposes a safe error to the UI; partial output is not committed as a completed assistant turn. Nova Pro has one narrowly defined access-denied fallback before output. Other provider/model failures stay visible rather than silently changing semantics.

### How does authentication work?

Walk from Cognito password auth to supported MFA challenge to strict access-token context validation and authoritative `GetUser`. Then explain `DataScope`: authentication identifies the user; scoped handles prevent cross-user data access. Mention idle/absolute expiry and logout cleanup.

### How is conversation history maintained?

Explain the two histories: visible transcript for the UI and model-safe context for inference. Only completed results are committed; model history is bounded. Optional DynamoDB/S3 persistence is config-gated, so do not claim that every deployment persists across task replacement.

### How do you deploy a new version?

“I push a commit and CI tests it offline on Windows, then builds the Linux container. I manually dispatch CD from `main`; it resolves that run's Git SHA, verifies successful push CI for the exact SHA, obtains AWS credentials through OIDC, publishes/reuses the SHA-tagged ECR image, registers a minimally changed task definition, updates ECS, waits, and verifies.”

### What happens when CI fails?

The dependent Docker-build job does not run and that SHA cannot satisfy CD's successful-CI gate. Diagnose the first failing deterministic step—dependency install/check, offline suite, or Docker build—rather than trying to deploy around it.

### How does rollback work?

ECS service rollback is a service-side circuit-breaker capability and must be enabled in deployed configuration. The workflow waits and verifies; it does not itself prove or enable that setting. A manual fallback is to update the service to a known-good task-definition revision/image digest after diagnosing the failed rollout.

### How would you scale to thousands of users?

Break the answer into four bottlenecks: web tasks/connections, shared session data, model/API quotas, and observability/cost. Scale Fargate across AZs, externalize required state, apply rate limits/backpressure, load test WebSockets and large uploads, and obtain provider quotas based on evidence.

### What would you improve for production?

Prioritize, do not list randomly:

1. Infrastructure as code plus exported/verified network and IAM configuration.
2. Central metrics, alarms, tracing, log retention, and post-deploy smoke tests.
3. Security hardening: WAF/guardrails as appropriate, image scanning/signing, secret rotation, dependency/SBOM policy.
4. Durable session/data strategy and deletion/retention controls.
5. Load, failover, accessibility, and browser integration tests.

## Answering “What was your contribution?”

Repository history attributes the commits to `aamir490` and shows the initial application, CI, CI correction, CD, and diagrams. A defensible first-person answer is:

> I built and integrated the application represented in this repository: the modular Streamlit UI, provider adapters, validation and session controls, offline regression workflow, container path, and manual AWS deployment workflow. I can trace those changes through the repository history. The live AWS console configuration is not fully exported as infrastructure as code, so I distinguish what the repository proves from what must be verified in the account.

Adjust that statement if other people helped outside Git history. Never infer exclusive authorship from commit metadata alone.

## Handling an unknown

Use: “That exact live setting is not versioned here, so I would not guess. The intended design is X; I would verify it with Y; the security consequence of the wrong value would be Z.” This demonstrates stronger engineering judgment than an invented answer.

---

<a id="chapter-13--practical-interview-demonstration"></a>

# Chapter 13 — Practical Interview Demonstration

## Before the interview

- Use sanitized/demo credentials and files containing no personal information.
- Confirm the app, selected models, Cognito user, and AWS quota in advance.
- Keep the architecture images, key files, Actions pages, and a known-good commit ready.
- Prepare a recorded screenshot path or local fallback for a provider outage, but say when it is a fallback.
- Never display environment files, tokens, secrets, account IDs, or unsanitized logs.

## A 12-minute demonstration sequence

### 0:00–0:45 — Introduce the system

> “NovaMind AI is a secure multimodal Streamlit application running as a container on AWS. It supports governed model selection across Amazon Bedrock and an optional Groq text provider, validates images and documents before inference, uses Cognito for identity, and has offline CI plus a manually promoted OIDC-based ECS deployment.”

### 0:45–2:00 — Open the application and authenticate

Show the CloudFront URL and sign-in flow. If MFA is configured for the demo user, explain that Cognito owns the challenge. Point out that the application validates the returned access token with `GetUser`; do not expose the token.

### 2:00–3:00 — Explain the interface

Show model selection, capability notes, attachment controls, chat transcript, reset/logout, and usage display. Explain that UI controls call orchestration functions; they do not contain provider-specific logic.

### 3:00–4:30 — Demonstrate text streaming

Submit a bounded prompt and select a model deliberately. Say:

> “The request guard validates capability and size, the provider factory resolves the adapter, and the UI renders deltas from the stream. The assistant turn enters history only when the stream completes.”

### 4:30–5:45 — Demonstrate image or document understanding

Use a small sanitized supported file with a model whose policy permits it. Show preview, ask a grounded question, and explain layered byte validation. State explicitly that direct attachment Q&A is not a RAG pipeline.

### 5:45–7:15 — Walk through architecture

Open the runtime diagram and trace:

> “Browser traffic reaches CloudFront, crosses the VPC-origin path to an internal ALB, reaches the Streamlit task on port 8501, and then the task calls Cognito and the selected inference provider under its workload permissions. ECR stores images and CloudWatch receives operational logs.”

Call out the evidence boundary for subnet routes, outbound path, and exact IAM/SG policy.

### 7:15–8:45 — Walk through important code

Open, in order:

1. `mod_chatbot_frontend.py` — compatibility launcher.
2. `novamind/ui/app.py` — composition and rerun flow.
3. `services/ai_provider.py` — model-to-provider routing.
4. `services/bedrock_service.py` — Converse streaming and controlled fallback.
5. `services/request_limits.py` — aggregate guardrails.
6. `services/auth_service.py` — Cognito/session verification.

Do not line-by-line the entire repository. Follow one request across boundaries.

### 8:45–10:00 — Show Docker and CI/CD

Use the Dockerfile to explain pinned Python, non-root execution, port, and health. Then show `.github/workflows/ci.yml` and `.github/workflows/cd.yml`:

> “CI is automatic on pushes and pull requests to main. CD is intentionally manual and refuses a SHA without successful push CI. It uses OIDC, an immutable ECR tag, a new task revision, a rolling update, and stability verification.”

### 10:00–11:00 — Discuss security and failure handling

Connect identity, owner scope, validation, IAM, Secrets Manager, internal origin, log hygiene, and safe errors. Give one failure example: a Bedrock permission error is classified and recorded; it is not exposed raw or silently routed to a different model.

### 11:00–12:00 — Close with challenge and roadmap

> “The strongest engineering theme is controlled boundaries: provider capabilities are explicit, files and requests are bounded, incomplete streams are not committed, and deployment binds a tested SHA to an immutable artifact. My next production priorities are infrastructure as code, verified network/IAM exports, stronger observability and smoke/load testing, and a deliberate durable-session strategy.”

## If the live demo fails

1. Name the failing layer: browser/edge, load balancer/task, authentication, request validation, or provider.
2. Show the health endpoint and relevant sanitized logs/status rather than repeatedly clicking.
3. Explain the expected path and compare it with the observed evidence.
4. Use a prepared screenshot only after saying it is not live.
5. Turn the failure into an engineering discussion: isolation, rollback, alerting, and next diagnostic.

## Practice drills

- Explain the system once without AWS product names, then once with precise AWS names.
- Trace a text request and an image request without looking at notes.
- Defend one trade-off, then argue for the strongest alternative.
- Identify three facts proved by code, three shown only by diagrams, and three requiring live-account verification.
- Practice stopping a wrong premise: “This implementation is multimodal, but it is not agentic because there is no autonomous tool loop.”

---

<a id="chapter-14--revision-and-self-assessment"></a>

# Chapter 14 — Revision and Self-Assessment

## Quick revision notes

- **Entry:** `mod_chatbot_frontend.py` delegates to `novamind.ui.app.main()`.
- **UI:** Streamlit chat/sidebar/auth modules compose the experience.
- **Routing:** model policy + provider factory, not UI conditionals alone.
- **Bedrock:** `converse_stream`; Nova Pro has a narrow one-attempt access-denied fallback.
- **Groq:** optional, OpenAI-compatible SSE, text-only here.
- **Files:** images 3.75 MiB; documents 4.5 MiB; signatures/structure/resources validated.
- **Request guard:** 20 MiB serialized cap, 200 messages, 20 images, 5 documents plus token budgets.
- **Memory:** completed turns only; 40 model messages / 200 display messages.
- **Identity:** Cognito plus `GetUser`; SMS/TOTP MFA supported; owner-scoped data handles.
- **Persistence:** optional DynamoDB/S3 code path, config-gated; no provisioning in repository.
- **Runtime:** Python 3.14.6 slim container, non-root UID 10001, port 8501, health endpoint.
- **Edge path:** CloudFront → VPC Origin → internal ALB → ECS Fargate → Streamlit.
- **CI:** push/PR to `main`; Windows Python 3.14.6 offline suite; Linux Docker build after success.
- **CD:** manual; exact-SHA CI gate; OIDC; SHA ECR tag; task revision; ECS stability/verification.
- **Evidence rule:** code/workflow > test > Git history > diagram/screenshot > unverified live assumption.

## One-page architecture summary

```text
Public request plane
Browser (HTTPS + Streamlit interactive connection)
  -> CloudFront
  -> CloudFront VPC Origin
  -> internal ALB
  -> ECS Fargate task :8501
  -> Streamlit UI / orchestration / validation / session scope

Identity and inference plane
Task -> Cognito GetUser / auth APIs
Task -> Bedrock ConverseStream
Task -> optional Groq HTTPS SSE
Task -> optional Secrets Manager / DynamoDB / S3

Delivery and operations plane
Git push/PR -> CI offline tests -> Linux Docker build
manual CD(SHA) -> exact CI verification -> GitHub OIDC -> ECR SHA image
  -> new ECS task-definition revision -> service rolling deployment -> stability check
ECS/container events -> CloudWatch logs (diagrammed/deployment evidence)
```

### Boundaries to say aloud

- The app is multimodal, not an autonomous agent.
- Groq is text-only in this implementation.
- Optional persistence is code-supported, not proof of provisioned tables/buckets.
- The diagrams are deployment evidence, not reproducible IaC.
- Task subnets, routes/NAT/endpoints, exact SG/IAM rules, alarms, and circuit-breaker state need live verification.
- Offline tests do not prove live provider or AWS integration health.

## Key AWS concepts to remember

| Concept | Interview memory hook |
|---|---|
| Region / AZ | Region hosts services; AZs are isolated locations used for resilience. |
| VPC / subnet | VPC is the network boundary; subnet is an AZ-scoped address/routing segment. |
| Public / private subnet | Determined by routing and public reachability—not the name. |
| Security group | Stateful resource firewall; prefer source-SG rules. |
| CloudFront VPC Origin | Lets the edge reach a supported private VPC origin. |
| Internal ALB | Layer-7 routing/health without a public load-balancer address. |
| ECS task definition | Versioned runtime specification for containers. |
| ECS service | Maintains desired tasks and manages deployment. |
| Fargate | Managed container compute capacity. |
| ECR | Private versioned container registry. |
| Execution role / task role | ECS launch permissions / application permissions. |
| OIDC federation | Short-lived role session from GitHub identity—no stored AWS access key. |
| Cognito | Managed user identity, auth flows, and MFA challenges. |
| Bedrock | Managed foundation-model access through AWS APIs. |
| CloudWatch | Logs, metrics, alarms, and operational visibility. |

## Technical vocabulary

- **Foundation model:** broadly trained model adapted at inference time through prompts and context.
- **Inference:** running a trained model to produce output.
- **Token:** model text unit used for context and billing/limits.
- **Context window:** maximum combined input/history/output token space.
- **Multimodal:** accepts more than one modality, here text plus supported images/documents for selected models.
- **SSE:** event-stream format used by the Groq adapter.
- **WebSocket/interactive channel:** persistent bidirectional browser/server communication important to Streamlit behavior.
- **IdP:** identity provider; Cognito fills this role here.
- **Least privilege:** grant only the actions/resources required.
- **IDOR:** unauthorized access caused by trusting an object identifier without ownership checks.
- **Immutable artifact:** release artifact identified by content/commit rather than a moving tag.
- **Rolling deployment:** replaces tasks gradually while maintaining service capacity.
- **Circuit breaker:** marks a rollout failed and can roll it back when configured.
- **Backpressure:** limiting/queuing work when downstream capacity is saturated.
- **RAG:** retrieval-augmented generation; not implemented by direct one-request document attachment.
- **Agentic loop:** model chooses actions/tools iteratively toward a goal; not implemented here.

## Practice exercises

1. Draw the request path from memory and mark every trust boundary.
2. Find the code that prevents Groq image input and explain both policy and adapter behavior.
3. Trace when a user message enters visible history versus model history.
4. Write a sanitized example Bedrock `converse_stream` payload for text plus one image.
5. Explain why a valid 4 MiB document could still fail aggregate request validation.
6. List permissions for an execution role, task role, and GitHub deployment role separately.
7. Diagnose: CloudFront returns a page but Streamlit interaction disconnects.
8. Diagnose: ECS is stable but the model call returns access denied.
9. Design a post-deploy smoke test that does not expose a real secret or consume excessive inference.
10. Design a measured autoscaling experiment and name the signals you would collect.
11. Propose a RAG extension and identify which current modules remain unchanged.
12. Turn one unverified diagram detail into a concrete AWS CLI/console verification checklist—without running deployment commands.

## Mock interview prompts

1. Tell me about NovaMind AI without using implementation jargon.
2. Walk me through a request at packet/service/module level.
3. Why is provider capability policy a separate abstraction?
4. What guarantees that a partial response does not corrupt memory?
5. What can an attacker do with a malicious uploaded document, and what controls exist?
6. Explain the difference between model context, UI history, and persisted history.
7. How would you prove that tasks are private?
8. Which IAM principal calls Bedrock, and why?
9. What exactly does CI prove, and what does it not prove?
10. Prove that the deployed container corresponds to a reviewed commit.
11. How would you detect and recover from a broken deployment?
12. Which changes would make this system agentic, and what new risks would appear?
13. What would you change for regulated data?
14. How would you evaluate response quality rather than only software correctness?
15. What is the most important unverified infrastructure assumption in this repository?

## Self-assessment checklist

I am interview-ready when I can:

- [ ] Give the 30-second, one-minute, and three-minute explanation naturally.
- [ ] Draw both runtime and delivery paths without notes.
- [ ] Name the entry point and trace one request through UI, orchestration, validation, provider, and history.
- [ ] Explain model capabilities and why Groq is text-only here.
- [ ] Explain Converse streaming and the Nova Pro fallback boundary.
- [ ] Explain file validation without calling it antivirus scanning.
- [ ] Distinguish authentication, authorization, session state, and persistence.
- [ ] Explain CloudFront VPC Origin and why the ALB is internal.
- [ ] Distinguish ECS execution, task, and deployment roles.
- [ ] Explain why Fargate fits and when another compute model would fit better.
- [ ] Describe CI and manual CD exactly as the YAML implements them.
- [ ] Explain OIDC without implying stored AWS keys.
- [ ] Explain immutable SHA tags, task revisions, stability checks, and rollback prerequisites.
- [ ] Troubleshoot from observed layer-specific evidence instead of guessing.
- [ ] Separate implemented, diagrammed/deployed, optional, proposed, and unverified claims.
- [ ] Discuss cost and scale without inventing numbers.
- [ ] Name three production improvements in priority order.
- [ ] Answer “What was your contribution?” honestly from repository evidence.
- [ ] Complete at least two mock runs with follow-up questions.

## Final learning loop

For any topic you cannot explain, repeat:

**Understand the concept → explain it simply → locate its implementation → trace its AWS dependency → state its failure mode → defend its trade-off → practice a follow-up.**

---

<div align="center">

## NovaMind AI

**Built by Aamir**

[GitHub profile](https://github.com/aamir490) · [Project repository](https://github.com/aamir490/Use--Case--25--NovaMind-AI-Multimodal-GenAI-Chatbot-AWS)

*Understand it. Trace it. Defend it. Improve it.*

</div>



