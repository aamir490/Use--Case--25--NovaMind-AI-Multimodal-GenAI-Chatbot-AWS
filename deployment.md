# Deployment status and future deployment requirements

## What is supported now

The verified local target is documented in [setup](docs/setup.md) and
[dependencies](docs/dependencies.md). This review does not establish that any AWS
host, IAM policy, model entitlement, TLS endpoint or infrastructure stack exists.
No deployment was performed. The Windows dependency lock is not a validated Linux
container lock. Earlier instructions to expose port 8501 publicly, attach broad
Bedrock permissions and use `nohup` are not a production deployment procedure.

## Implemented deployed credential mode

`services/aws_config.py:create_aws_session` supports `NOVAMIND_AWS_MODE=task-role`
with region `us-east-1`. It removes all credential providers except `container-role`.
The deployment must supply legitimate workload credentials through that provider,
for example an ECS task role. The ECS execution role and application task role have
different responsibilities; application Bedrock access belongs to the task role.

Do not set `AWS_PROFILE` or `AWS_DEFAULT_PROFILE` in task-role mode. Do not bake
shared credential files or static AWS keys into an image. Static credential
environment variables are rejected. Do not configure a default profile.
An ordinary EC2 instance profile using IMDS will not work with this implementation.
Supporting it would require a separately approved code change; ECS on EC2 using
container task credentials is a different deployment model.

## Proposed execution order, requiring separate approval

1. Validate a Linux runtime/dependency lock, container build and isolated parser
   resource ceilings; run the offline suite adapted for that target. The current
   baseline test deliberately checks Windows x64/CPython 3.14.6.
2. Configure and live-validate the [Task 3A Cognito integration](docs/task_3a_cognito_auth.md).
   Default authentication fails closed until pool/client settings exist. Use task-role
   mode and Cognito in deployment; demo is local-only. Define upload retention and data policy.
3. Provision container hosting, task role, TLS termination and restricted network
   access with reviewed IaC. Keep the backend reachable only through the intended
   ingress path; preserve Streamlit WebSocket/session routing. Scaling replicas
   requires a strategy for in-memory sessions; process restarts lose conversations.
4. Scope streaming invocation permissions to approved model/profile resources and
   any resources required by that profile. Diagnostics separately use identity and
   catalog operations. Confirm account-specific access with approved live checks;
   neither catalog visibility nor a local test proves inference permission.
5. Add structured, sanitized logs/metrics, health checks, limits and deployment
   rollback. Use immutable releases; rolling back code cannot recover lost sessions.
6. Validate streaming, uploads, IAM failures and reconnect behavior before rollout.

These steps are proposals, not completed tasks. Resource sizing must include the
Streamlit process, parser subprocesses and concurrent session payloads; no instance
size or free-tier cost guarantee is made. Hosting can incur idle costs. Usage shown
in the app covers recorded chat/summary attempts and is not total AWS billing.
