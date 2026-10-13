# NovaMind AI — Interview Guide

Use these as natural speaking points. Be clear about what exists today and what you would add in production.

## 30-second introduction

“NovaMind AI is a Streamlit-based multimodal chatbot built on Amazon Bedrock. It streams text conversations and lets a user attach one image or document for analysis in the same chat. I separated the frontend from validation and Bedrock service layers, use Bedrock Converse content blocks for text/image/document input, and keep history only for the active session. It is intentionally a focused portfolio application; production would add Cognito, durable storage, observability, and RAG for a document collection.”

## Five project stories

### 1. End-to-end story

“I wanted to show more than a text-only chatbot, because real users often have screenshots and documents. The Streamlit UI lets the user choose a model, persona, language, and inference settings. Uploads are validated for type, size, and basic signature before use. Image processing corrects orientation and makes a thumbnail; document processing supplies a small preview where possible.

The frontend calls an isolated Bedrock service. That service builds a Converse message containing an image or document content block and the user question, then uses ConverseStream so the answer appears progressively. I keep a separate display history and API history because binary attachment content should not be repeatedly rendered in the UI. This gives a clean user experience and a maintainable code structure.”

### 2. Multimodal design story

“The key decision was a unified Bedrock Converse interface, rather than separate chatbot, OCR, and document products. The request can carry an image block or document block plus a text instruction, so the model reasons about the attachment and question together. I perform lightweight local checks and previews, but the model receives the source bytes. For one small document, direct attachment is simpler than RAG. RAG becomes valuable for many documents, retrieval, citations, filtering, and reuse.”

### 3. AWS services story

“Bedrock Runtime is the core service: ConverseStream returns incremental output and the connection check also collects a ConverseStream response. IAM authorises model invocation. STS and the Bedrock control plane are used by the diagnostic script to verify identity and service/model access. Streamlit supplies the interface, while Pillow and pypdf support attachments. I deliberately did not add Lambda, API Gateway, S3, or DynamoDB yet because the present scope has no durable API, background job, or persistence requirement. In production I would add services only when the requirement needs them.”

### 4. Security story

“I started with credentials and files. The service does not contain AWS keys; local boto3 sessions explicitly use profile novamind in us-east-1; deployed task-role mode allows only container credentials. Files are checked for size, extension, decoding and parser resource limits; names are sanitised; attachment bytes stay in session memory rather than a permanent local folder.

I would be explicit that the sign-in screen is portfolio-only because it has sample credentials in source. A production build would use Cognito or enterprise OIDC, TLS behind an ALB, least-privilege IAM, Secrets Manager, WAF/rate limits, encrypted S3 uploads, scanning, CloudWatch, and retention policies.”

### 5. Scale and cost story

“Bedrock scales model inference as a managed pay-per-use service. The Streamlit app itself has per-session in-memory state, so for multi-user production I would run containers on ECS/Fargate behind an ALB and move history into DynamoDB or Aurora. Uploads would move to encrypted S3 and operations data to CloudWatch.

Actual Bedrock usage metadata is captured per attempt with the invoked model and operation. Cost remains an estimate from frozen, unverified project rates; missing usage or pricing is unknown. Production chargeback still needs authoritative billing reconciliation. For document collections I would retrieve only relevant chunks rather than attach everything.”

## Architecture in plain English

~~~text
User question/attachment
  → Streamlit receives it and updates session state
  → validation prepares a safe image/document result
  → Bedrock service creates a multimodal Converse message
  → Bedrock streams answer
  → Streamlit displays it and stores current-session history
~~~

Two histories are intentional:

- chat_history: text and small attachment metadata for display and export.
- bedrock_history: structured API content, potentially including binary bytes, for model context.

## Questions and strong answers

### Why ConverseStream?

It provides structured, model-facing messages and incremental text output. Streaming improves perceived response time because users see the answer begin before the complete generation has finished.

### How do images/documents work?

An upload is routed to the correct service by extension. After validation, the service returns bytes plus a Bedrock-compatible format. The Bedrock service builds an image or document block plus the user text into the current Converse message.

### Why two histories?

The model needs structured API content and may need attachment bytes. The UI needs only lightweight, safe-to-render content. Keeping them separate avoids rendering/exporting raw API payloads and keeps UI concerns separate from inference concerns.

### Is the cost counter accurate?

Token counts come from Bedrock usage metadata when present. Costs are configured-rate estimates, not exact bills; unknown usage/pricing remains unknown, and historical costs do not change when the model selector changes.

### Why not RAG?

This is one small attachment in one session. Direct model attachment keeps the path simple and avoids retrieval/chunking errors. RAG is the next capability for a durable, searchable collection of documents, metadata filters, and citations.

### Why not run Streamlit on Lambda?

Streamlit is a long-running interactive application with session behaviour. Lambda is suited to short-lived stateless handlers. I would containerise Streamlit on ECS/Fargate and use Lambda only for small asynchronous processing tasks if useful.

### How would you secure uploads?

Today: extension, size, and basic signature checks; name sanitisation; session-memory data. Production: encrypted S3, malware scanning, strict MIME/content checks, quotas, short-lived upload URLs, retention/deletion policy, and strong access control.

### How would you make it multi-user and highly available?

Containerise it; use ECS/Fargate and an ALB; add Cognito; persist conversations and metadata in DynamoDB/Aurora; store uploads in S3; then add autoscaling, CloudWatch alarms, WAF/rate limits, retries, and tracing. Moving local session state is necessary before horizontal scale.

### What are the limitations?

Demo-only login, no persistent history, one pending attachment at a time, no RAG/citations, unverified configured pricing, limited production observability, and a deliberately narrow Nova Pro-only pre-output fallback. Naming limitations proactively shows sound judgement.

## Closing statement

“NovaMind AI demonstrates a practical managed-GenAI pattern: a user-friendly frontend, an isolated service layer, validated multimodal input, and streamed Bedrock inference. I kept the first version small enough to explain and test, while designing clear next steps for identity, persistence, safety, observability, and enterprise-scale document intelligence.”

See [architecture.md](architecture.md) for the technical detail.
