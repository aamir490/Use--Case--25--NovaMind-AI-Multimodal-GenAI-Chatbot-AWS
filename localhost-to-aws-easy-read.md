# ☁️ NovaMind AI — From Localhost to AWS

### A visual, beginner-friendly deployment & interview handbook

**Python + Streamlit → Docker Desktop → Amazon ECR → ECS Fargate → Internal ALB → CloudFront → Public HTTPS**

> **Purpose:** Understand the *why* and *how* behind the deployment, not just memorize CLI commands. Study one chapter at a time. Open the technical notes only when you're ready.

| 📍 Project | 🔧 Tools | 🗺️ AWS Region | 🛡️ Status |
|---|---|---|---|
| NovaMind AI multimodal chatbot | Windows PowerShell, Docker, AWS CLI, GitHub Actions | `us-east-1` | Historical deployment completed; chatbot AWS infrastructure later removed |

**Safety:** AWS creation examples may be billable; deletion examples are destructive. **Do not run commands from this guide without reviewing them.** Service configurations reconstructed from repo evidence are labeled accordingly.

---

## ✨ Start here — understand the whole project in 60 seconds

There are **three different flows**. Interviewers often test whether you can tell them apart.

### ① How the app gets deployed (the image flow)

```mermaid
flowchart LR
  A[Python source] --> B[Docker build]
  B --> C[Docker image]
  C -->|push| D[Amazon ECR]
  D -->|pull at task start| E[ECS Fargate]
```

**Easy explanation:** I package the Python application with Docker, store its image in ECR, and let ECS Fargate run that image. **ECR is storage, not compute.**

### ② How a user opens the public app (the traffic flow)

```mermaid
flowchart LR
  U[Browser] -->|HTTPS 443| CF[CloudFront]
  CF --> V[VPC Origin]
  V -->|HTTP 80| ALB[Internal ALB]
  ALB -->|TCP 8501| T[ECS Fargate: Streamlit]
  T -->|response through same route| ALB
```

**Easy explanation:** CloudFront provides the public web address. Its VPC Origin connects privately to the ALB, which forwards traffic to the Streamlit container on port **8501**.

### ③ How code changes reach production (the CI/CD flow)

```mermaid
flowchart LR
  G[Git push] --> CI[Automatic CI: tests + build]
  CI --> M[Manual CD trigger]
  M --> O[GitHub OIDC to AWS]
  O --> E[ECR image by commit SHA]
  E --> S[New ECS task revision]
  S --> P[Live CloudFront check]
```

**Easy explanation:** CI checks that my code and Docker image build correctly. CD, started manually, publishes the updated image and rolls out the ECS service. Our real test was **“Welcome back” → “Welcome back folk.”**

---

## 🧭 How to study this guide

**Day 1 — Foundations:** Localhost → Docker → AWS CLI → ECR  
**Day 2 — AWS networking:** VPC → security groups → ALB → CloudFront  
**Day 3 — Application connections:** ECS → IAM → Cognito → Bedrock → Secrets  
**Day 4 — DevOps and defense:** GitHub Actions → Troubleshooting → Interview Q&A

**Remember these five questions for every AWS service:**

1. What problem does it solve?
2. Who talks to it, and why?
3. What is the protocol, port, or API?
4. What IAM permission or security-group rule allows it?
5. How would I check it using AWS CLI?

### Quick vocabulary

| Term | Easy meaning |
|---|---|
| **Docker image** | Packaged app that can be started anywhere with a compatible container engine |
| **Container** | A running instance of an image |
| **Amazon ECR** | Private place to store container images |
| **ECS service** | Keeps the requested number of tasks running |
| **Fargate task** | AWS-managed running container workload |
| **ALB** | Forwards web requests to healthy containers |
| **CloudFront** | Public HTTPS entry point used by the browser |
| **VPC Origin** | Private connection from CloudFront to the internal ALB |
| **Security group** | Firewall rules controlling allowed network traffic |
| **IAM role** | Temporary AWS permissions for a service or workflow |
| **Cognito** | Signs in application users |
| **Bedrock** | API used by the app for AI model inference |

---

## 🧩 Two diagrams worth practicing on a whiteboard

### Runtime AWS layout

```mermaid
flowchart TB
  U[Public user] -->|HTTPS| CF[Amazon CloudFront]
  CF --> VO[VPC Origin]
  subgraph VPC[Chatbot VPC 10.20.0.0/16]
    subgraph PRIV[Private subnets]
      ALB[Internal ALB :80]
    end
    subgraph PUB[Public subnets]
      ECS[Fargate Streamlit :8501]
    end
    VO --> ALB
    ALB -->|private task IP| ECS
  end
  ECS -->|HTTPS + user tokens| C[Cognito]
  ECS -->|HTTPS + task role| B[Bedrock]
  ECS -->|HTTPS + API key| G[Groq]
  ECR[ECR] -. image pull at start .-> ECS
  SM[Secrets Manager] -. startup injection .-> ECS
  ECS -. logs .-> CW[CloudWatch]
```

**Historical note:** This layout reflects the *CLI-confirmed cleanup inventory* discussed during the project: Fargate task subnets `10.20.1.0/24` and `10.20.2.0/24`, private ALB subnets `10.20.10.0/24` and `10.20.11.0/24`. The original Codex file contains a different reconstructed subnet illustration; consult the evidence note in Chapter 0 before treating a diagram as proof of historical configuration.

### Request vs permission vs deployment

| Flow | What moves? | Example |
|---|---|---|
| **Browser traffic** | HTTPS requests and Streamlit updates | CloudFront → ALB → container |
| **Container delivery** | Image bytes | Docker → ECR → Fargate |
| **IAM authorization** | Signed AWS API calls | Task role → Bedrock |
| **User authentication** | Login credentials / user access token | Streamlit → Cognito |
| **Secret injection** | Groq key at task startup | Secrets Manager → ECS environment |

---

## 📚 Chapter library

Each chapter starts with **one simple idea**. Expand **“Detailed explanation, CLI commands & interview answers”** only when you're ready.


---

## 🔎 Evidence & what we know

**What you will learn:** Which parts are confirmed, which are reconstructed.

> **Remember:** Check facts before claiming them in an interview.

<details>
<summary><strong>📖 Open detailed explanation, AWS CLI commands, diagrams & interview answers</strong></summary>

| Topic | What the repository establishes |
|---|---|
| Application | [`mod_chatbot_frontend.py`](mod_chatbot_frontend.py) calls `novamind.ui.app.main()`. [`Dockerfile`](Dockerfile) starts Streamlit on `0.0.0.0:8501`, as UID/GID 10001, with `/_stcore/health`. [`.streamlit/config.toml`](.streamlit/config.toml) enables CORS and XSRF checks. |
| Dependencies | Windows [`requirements.txt`](requirements.txt) is used in CI; Linux [`requirements-linux.txt`](requirements-linux.txt) is used in Docker. [`.env.example`](.env.example) is a reference; code does not auto-load it. |
| AWS identity | [`services/aws_config.py`](services/aws_config.py) fixes region `us-east-1`: local boto3 uses the explicit `novamind` profile; ECS `task-role` mode uses only container-role credentials, rejecting static AWS keys and profile selectors. |
| AI and auth | [`services/auth_service.py`](services/auth_service.py) defaults to Cognito, uses `USER_PASSWORD_AUTH`, handles SMS/TOTP challenges and verifies access tokens through Cognito `GetUser`. [`services/bedrock_service.py`](services/bedrock_service.py) calls Bedrock `converse_stream`. [`services/groq_service.py`](services/groq_service.py) calls Groq's HTTPS chat-completions endpoint for text only. |
| Historical cloud evidence | The [architecture image](project-pic/NovaMind-AI-AWS-Architecture-Blueprint-with-cicd.png) and [AWS screenshots](project-pic/aws-cloudfront.png) depict CloudFront/VPC origin, internal ALB, ECS/Fargate, ECR, Cognito, Secrets Manager and CloudWatch. They cannot prove routes, IAM policies, task networking, or present existence. |
| CI/CD | [CI](.github/workflows/ci.yml) runs offline Windows Python tests on push/PR to `main`, followed by Ubuntu Docker build. [CD](.github/workflows/cd.yml) is manual, checks successful push CI for the exact SHA, assumes an AWS OIDC role, publishes or reuses a SHA-tagged ECR image, changes only the task-definition image, waits for ECS stability, and verifies revision and image. |
| Demonstration | Commit `50a5d3f` changes the login heading in [`novamind/ui/auth.py`](novamind/ui/auth.py) from **Welcome back** to **Welcome back folk**. The user reports CI, CD and public URL verification; [CI/CD screenshots](project-pic/cicd-1.png) support historical workflow activity. The current endpoint is **Not verified**. |
| Optional persistence | [`services/conversation_store.py`](services/conversation_store.py) and [`services/attachment_store.py`](services/attachment_store.py) use DynamoDB/S3 only if existing table/bucket names are configured. Historical activation is **Not verified**. |

**Important correction.** The diagram labels `10.20.1.0/24` and `10.20.2.0/24` public, and `10.20.11.0/24` and `10.20.12.0/24` private. It visually places the ALB in the first tier and tasks in the private tier. Your requested design says **internal ALB in private subnets and ECS tasks in public subnets**. Neither the task subnet IDs/public-IP flag nor the route tables are exported in this repository. The deployment procedure below explicitly **reconstructs your requested placement**. An internal ALB can be internal even in a public-routed subnet because its scheme is `internal`; subnet routing and ALB scheme are separate properties. Do not present either placement as a recovered historical fact. The internal ALB itself is screenshot-evidenced.

</details>

---

## 💻 01 · Localhost

**What you will learn:** The Python Streamlit app runs on your laptop.

> **Remember:** Localhost is only your computer; port 8501 is where Streamlit listens.

<details>
<summary><strong>📖 Open detailed explanation, AWS CLI commands, diagrams & interview answers</strong></summary>

**What:** `localhost`/`127.0.0.1` means your own laptop. TCP port **8501** identifies the Streamlit server process; it is not an AWS port assignment. **Why:** local testing isolates application behavior before cloud packaging. **How:** Streamlit runs Python code that renders browser UI, receives widget/chat/upload events, reruns relevant code, and holds per-session state in server memory. There is no separately deployed frontend API service: `novamind/ui/` handles the UI, `novamind/orchestration/` coordinates requests, and `services/` handles auth, providers, validation and optional storage.

**Local PowerShell illustration (not executed):**

```powershell
Set-Location 'E:\codex-projetc\Chatbot_text_image'
& .\.venv\Scripts\python.exe --version
& .\.venv\Scripts\python.exe -m pip check
# Only for loopback development. Real deployments use Cognito.
$env:NOVAMIND_AUTH_MODE = 'demo'
$env:NOVAMIND_AWS_MODE = 'local'
$env:AWS_PROFILE = 'novamind'
$env:AWS_DEFAULT_REGION = 'us-east-1'
& .\.venv\Scripts\python.exe -m streamlit run mod_chatbot_frontend.py --server.address 127.0.0.1 --server.port 8501
# In another terminal:
Invoke-WebRequest 'http://localhost:8501/_stcore/health'
```

Open `http://localhost:8501`. HTTP 200 on the health path proves server responsiveness, not successful Cognito or inference. The app defaults to Cognito; demo mode requires explicit opt-in and is blocked in deployed environments. `requirements.txt` pins the Windows development environment; Docker installs the Linux lock. Environment variables are inherited from the launching process; merely copying `.env.example` to `.env` does not load it. Local AWS calls require the named profile, permission, regional endpoint and network access. Active Streamlit sessions are process-local; a restart loses them.

**Interview answer:** “I ran the Streamlit launcher locally on port 8501. Browser actions execute Python in the server process; I tested startup and the health endpoint before containerizing it.”

</details>

---

## 🐳 02 · Docker Desktop

**What you will learn:** Package Python and dependencies into a portable image.

> **Remember:** Image = package. Container = running copy. 8502:8501 maps laptop to container.

<details>
<summary><strong>📖 Open detailed explanation, AWS CLI commands, diagrams & interview answers</strong></summary>

**What:** an *image* is a packaged filesystem/configuration; a *container* is its running process. **Why:** ECS Fargate needs a Linux image, not a Windows source directory. **How:** Docker Desktop runs a Linux container backend via WSL2/VM on Windows. [`Dockerfile`](Dockerfile) uses `python:3.14.6-slim-bookworm`, installs exact Linux dependencies, copies runtime modules/assets, checks imports, runs non-root as UID 10001, exposes 8501, and defines a health check. [`.dockerignore`](.dockerignore) excludes local credentials, `.venv`, uploads, tests and Git state from build context.

**Local PowerShell illustration (not executed):**

```powershell
docker build --tag novamind-ai:local .
docker images
docker run --detach --name novamind-local --publish 8502:8501 novamind-ai:local
docker ps
docker ps -a
docker logs novamind-local
Invoke-WebRequest 'http://localhost:8502/_stcore/health'
docker image inspect novamind-ai:local --format '{{.Id}} {{.Config.User}}'
docker inspect novamind-local --format '{{json .State.Health}}'
docker system df
docker stop novamind-local
docker rm novamind-local
```

`build` executes Dockerfile steps; `run` starts one container. `8502:8501` means **Windows host 8502 → container 8501**. `ps` shows running containers, `ps -a` also stopped ones, `images` lists local artifacts, `logs` shows stdout/stderr, `system df` shows disk use, and `tag` (next chapter) creates another name for an existing image. Startup/health testing alone does not authenticate to Cognito or Bedrock. Runtime configuration must be injected without baking credentials into image layers. The image, tagged by SHA, is the artifact later pushed to ECR.

**Interview answer:** “I used Docker Desktop to build the Linux runtime. The container still listened on 8501, while my laptop used 8502 for the local mapping. I pushed the built image to a registry for Fargate to pull.”

</details>

---

## 🔑 03 · AWS CLI & identity

**What you will learn:** Control AWS resources from PowerShell.

> **Remember:** Your local AWS profile is not the credential used by Fargate or GitHub Actions.

<details>
<summary><strong>📖 Open detailed explanation, AWS CLI commands, diagrams & interview answers</strong></summary>

**What:** AWS CLI sends HTTPS API requests signed with credentials. **Why:** it can provision and inspect infrastructure from PowerShell. **How:** `--profile novamind` chooses the local credential source and `--region us-east-1` selects regional endpoints. A long-lived IAM *user* may have access keys; an IAM *role* is assumed for temporary credentials. Prefer approved SSO/federation for human access; never put access keys in this guide, Docker image, GitHub workflow or task definition. The laptop profile, ECS execution role, ECS task role and GitHub OIDC role are different identities.

**Read-only/setup illustration (not executed):**

```powershell
aws --version
aws configure --profile novamind  # Interactive only if your organization permits this credential method.
aws configure list --profile novamind
aws sts get-caller-identity --profile novamind --region us-east-1
aws ec2 describe-regions --profile novamind --region us-east-1 --query 'Regions[].RegionName'
```

`sts get-caller-identity` tells which principal you are, not what it may do. `--query` filters the CLI response; `--output text/json` controls its format. The app's local boto3 session explicitly selects `novamind`; deployed `task-role` mode filters botocore credential providers to `container-role` only. GitHub's runner obtains short-lived AWS credentials from OIDC `AssumeRoleWithWebIdentity`, separate from the local profile.

**Interview answer:** “My local CLI profile signed provisioning requests. The running task had a separate task role, and GitHub Actions federated into a deployment role. I checked the caller identity before operating in the intended account and region.”

</details>

---

## 🌐 04 · VPC & networking

**What you will learn:** Create subnets, routes and security boundaries.

> **Remember:** Routing decides reachability; security groups allow traffic; IAM controls AWS API actions.

<details>
<summary><strong>📖 Open detailed explanation, AWS CLI commands, diagrams & interview answers</strong></summary>

**What:** a VPC is private address space; subnets live in one Availability Zone; route tables forward packets; security groups protect ENIs. **Why:** CloudFront must reach a private ALB, the ALB must reach tasks, and tasks must reach AWS APIs and optionally Groq. **How in this reconstruction:** VPC `10.20.0.0/16`; public task subnets `10.20.1.0/24` (`us-east-1a`) and `10.20.2.0/24` (`us-east-1b`); private ALB subnets `10.20.11.0/24` and `10.20.12.0/24`. Public subnets have `0.0.0.0/0 → Internet Gateway`; private ALB subnets do not. All four retain the VPC's local route. Task ENIs receive private IPs plus assigned public IPs in this example; public IP + IGW route enables outbound internet. ALB-to-task traffic still uses the task's **private** IP through the local route. The task SG accepts inbound 8501 only from the ALB SG. DNS resolves the internal ALB name privately. A route enables network traffic; it never grants IAM API authorization.

CloudFront VPC origins require an attached IGW and available IPv4 addresses in private subnet(s), although the CloudFront-to-origin path does **not** traverse that IGW. CloudFront creates a service-managed ENI and SG. [AWS prerequisites](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/private-content-vpc-origins.html).

**Reconstructed provisioning [BILLABLE], not executed:**

```powershell
$p = 'novamind'; $r = 'us-east-1'
$vpc = aws ec2 create-vpc --cidr-block 10.20.0.0/16 --profile $p --region $r --query 'Vpc.VpcId' --output text
aws ec2 modify-vpc-attribute --vpc-id $vpc --enable-dns-support Value=true --profile $p --region $r
aws ec2 modify-vpc-attribute --vpc-id $vpc --enable-dns-hostnames Value=true --profile $p --region $r
$pubA = aws ec2 create-subnet --vpc-id $vpc --availability-zone us-east-1a --cidr-block 10.20.1.0/24 --profile $p --region $r --query 'Subnet.SubnetId' --output text
$pubB = aws ec2 create-subnet --vpc-id $vpc --availability-zone us-east-1b --cidr-block 10.20.2.0/24 --profile $p --region $r --query 'Subnet.SubnetId' --output text
$privA = aws ec2 create-subnet --vpc-id $vpc --availability-zone us-east-1a --cidr-block 10.20.11.0/24 --profile $p --region $r --query 'Subnet.SubnetId' --output text
$privB = aws ec2 create-subnet --vpc-id $vpc --availability-zone us-east-1b --cidr-block 10.20.12.0/24 --profile $p --region $r --query 'Subnet.SubnetId' --output text
$igw = aws ec2 create-internet-gateway --profile $p --region $r --query 'InternetGateway.InternetGatewayId' --output text
aws ec2 attach-internet-gateway --vpc-id $vpc --internet-gateway-id $igw --profile $p --region $r
$publicRT = aws ec2 create-route-table --vpc-id $vpc --profile $p --region $r --query 'RouteTable.RouteTableId' --output text
$privateRT = aws ec2 create-route-table --vpc-id $vpc --profile $p --region $r --query 'RouteTable.RouteTableId' --output text
aws ec2 create-route --route-table-id $publicRT --destination-cidr-block 0.0.0.0/0 --gateway-id $igw --profile $p --region $r
aws ec2 associate-route-table --route-table-id $publicRT --subnet-id $pubA --profile $p --region $r
aws ec2 associate-route-table --route-table-id $publicRT --subnet-id $pubB --profile $p --region $r
aws ec2 associate-route-table --route-table-id $privateRT --subnet-id $privA --profile $p --region $r
aws ec2 associate-route-table --route-table-id $privateRT --subnet-id $privB --profile $p --region $r
```

`create-vpc` allocates CIDR; `create-subnet` places each /24; `attach-internet-gateway` adds the VPC internet boundary; `create-route` supplies public default egress; associations select each subnet's route table. A subnet name or picture is not proof that it is public. Inspect route associations and task `assignPublicIp` in a live deployment. If image pull or Groq fails, check DNS, task ENI/IP, routes, SG egress and NACLs before changing IAM. A stronger production layout moves tasks to private subnets with controlled NAT for external calls and suitable VPC endpoints for AWS services; validate costs and actual endpoints.

**Interview answer:** “The VPC local route lets a private ALB forward to a task's private ENI. In the reconstructed public-task layout, task egress uses its assigned public IP and IGW, while its SG accepts app traffic only from the ALB.”

</details>

---

## 📦 05 · Amazon ECR

**What you will learn:** Store the container image in a private registry.

> **Remember:** ECR stores the image. It does not run the application or serve users.

<details>
<summary><strong>📖 Open detailed explanation, AWS CLI commands, diagrams & interview answers</strong></summary>

**What:** ECR is a private OCI image registry. **Why:** ECS pulls a release image from it. **How:** source → `docker build` → registry login → remote image tag → `docker push`. The repository URI names a registry/repository; `:<tag>` is a pointer (the real CD uses Git SHA); `@sha256:<digest>` identifies actual content. ECR tag immutability below is a **reconstructed recommendation**, not a verified historical repository setting.

**Reconstructed [BILLABLE: ECR storage/transfer], not executed:**

```powershell
$p = 'novamind'; $r = 'us-east-1'
$account = aws sts get-caller-identity --profile $p --region $r --query Account --output text
$repo = 'novamind-chatbot-ecr'
aws ecr create-repository --repository-name $repo --image-tag-mutability IMMUTABLE --image-scanning-configuration scanOnPush=true --profile $p --region $r
$registry = "$account.dkr.ecr.$r.amazonaws.com"
$image = "$registry/$repo"
aws ecr get-login-password --profile $p --region $r | docker login --username AWS --password-stdin $registry
$sha = git rev-parse HEAD
docker build --tag "novamind-ai:$sha" .
docker tag "novamind-ai:$sha" "${image}:$sha"
docker push "${image}:$sha"
aws ecr describe-images --repository-name $repo --image-ids "imageTag=$sha" --profile $p --region $r --query 'imageDetails[0].{Digest:imageDigest,Tags:imageTags}'
```

`get-login-password` derives a temporary registry token from local AWS credentials; `--password-stdin` avoids a command-argument password. `docker tag` gives the existing image its ECR name; push uploads layers. The *publisher* needs ECR upload permission; the later ECS *execution role* needs separate pull permission. The actual CD workflow checks for a valid existing digest and reuses that SHA tag or builds/pushes it. It does not deploy `latest`.

**Interview answer:** “I tagged the Linux image with the Git SHA and ECR repository URI, authenticated Docker with a short-lived ECR token, and pushed it. ECS later pulled the referenced artifact using its execution role.”

</details>

---

## ⚙️ 06 · ECS Fargate

**What you will learn:** Run the image as a managed container service.

> **Remember:** Task definition says HOW to run; ECS service keeps tasks running.

<details>
<summary><strong>📖 Open detailed explanation, AWS CLI commands, diagrams & interview answers</strong></summary>

**What:** ECS stores the desired deployment; Fargate runs its tasks without EC2 host management. **Why:** Streamlit needs a long-running process and WebSocket connection. **How:** a cluster groups services; a task definition specifies image/CPU/memory/ports/roles/config/logs; a service maintains task count and ALB target registration. Each task has its own ENI. The **execution role** authorizes ECR pull, CloudWatch `awslogs`, and ECS secret injection. The **application task role** authorizes code's Bedrock and optional DynamoDB/S3 calls. The `task-role` SDK credential filter requires ECS container credentials. [AWS execution role guide](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task_execution_IAM_role.html).

**Reconstructed [BILLABLE: running tasks/logs], not executed:**

```powershell
aws ecs create-cluster --cluster-name novamind-chatbot-cluster --profile novamind --region us-east-1
aws logs create-log-group --log-group-name /ecs/novamind-chatbot --profile novamind --region us-east-1
aws logs put-retention-policy --log-group-name /ecs/novamind-chatbot --retention-in-days 7 --profile novamind --region us-east-1
aws ecs register-task-definition --cli-input-json file://task-definition.json --profile novamind --region us-east-1
aws ecs describe-task-definition --task-definition novamind-chatbot-task --profile novamind --region us-east-1 --query 'taskDefinition.{Arn:taskDefinitionArn,Image:containerDefinitions[0].image}'
```

For a later rebuild, place the following **illustrative** JSON in `task-definition.json` (outside this documentation task). Replace every `<...>`. CPU `1024` and memory `2048` are **example sizes**, not recovered historical values. The log group name and screenshot retention are historical evidence only.

```json
{
  "family":"novamind-chatbot-task", "requiresCompatibilities":["FARGATE"],
  "networkMode":"awsvpc", "cpu":"1024", "memory":"2048",
  "runtimePlatform":{"operatingSystemFamily":"LINUX","cpuArchitecture":"X86_64"},
  "executionRoleArn":"<execution-role-arn>", "taskRoleArn":"<application-task-role-arn>",
  "containerDefinitions":[{
    "name":"novamind-chatbot", "essential":true,
    "image":"<account>.dkr.ecr.us-east-1.amazonaws.com/novamind-chatbot-ecr:<git-sha>",
    "portMappings":[{"containerPort":8501,"hostPort":8501,"protocol":"tcp"}],
    "environment":[
      {"name":"NOVAMIND_AWS_MODE","value":"task-role"},
      {"name":"AWS_DEFAULT_REGION","value":"us-east-1"},
      {"name":"COGNITO_USER_POOL_ID","value":"<pool-id>"},
      {"name":"COGNITO_APP_CLIENT_ID","value":"<public-client-id>"},
      {"name":"NOVAMIND_AI_PROVIDER","value":"bedrock"},
      {"name":"BEDROCK_MODEL_ID","value":"amazon.nova-pro-v1:0"}
    ],
    "secrets":[{"name":"GROQ_API_KEY","valueFrom":"<secret-arn>"}],
    "logConfiguration":{"logDriver":"awslogs","options":{
      "awslogs-group":"/ecs/novamind-chatbot","awslogs-region":"us-east-1","awslogs-stream-prefix":"ecs"
    }}
  }]
}
```

Omit `secrets` if Groq is not configured. The public Cognito client ID and pool ID are identifiers; do not place user passwords or Groq key values in plaintext task environment. Do **not** set AWS profile or static access-key variables on the task. Fargate first allocates an ENI; the execution identity authenticates to ECR and downloads layers (which also requires working network/S3 layer access), retrieves any ECS-injected secret, and configures logging. Then the non-root container starts and Python obtains temporary **task-role** credentials for runtime SDK requests. Image pull occurs before Python can run. [Fargate networking](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/fargate-task-networking.html).

After target-group creation (§7), `create-service` binds it to the service (§13). For a later release, register a new task-definition revision and run `aws ecs update-service --task-definition <new-arn>`; ECS starts new tasks, waits for health, and drains old targets. A healthy process is not proof of model access or authenticated UI behavior.

**Interview answer:** “The ECS service kept my Fargate tasks running. Fargate's execution role pulled the ECR image and set up logs/secrets; my app's distinct task role authorized Bedrock calls. ECS registered each task's private IP with the load balancer.”

</details>

---

## 🔀 07 · Application Load Balancer

**What you will learn:** Send requests to healthy task IPs.

> **Remember:** ALB listener → target group → Fargate private IP:8501.

<details>
<summary><strong>📖 Open detailed explanation, AWS CLI commands, diagrams & interview answers</strong></summary>

**What:** ALB is HTTP layer-7 routing and health checking. **Why:** it gives changing Fargate task IPs a stable internal front door. **How:** `Scheme=internal` gives private-facing ALB addresses. In the reconstructed layout it spans private subnets in two AZs, listens HTTP/80, forwards to an IP-type target group on 8501, and checks `/_stcore/health`. Fargate `awsvpc` targets are **IP** targets, not instance targets. ECS registers/deregisters task IPs. An unhealthy target stops receiving new requests and ECS may replace the task; inspect target reason codes and ECS events.

**Reconstructed [BILLABLE: ALB], not executed:**

```powershell
$albSG = aws ec2 create-security-group --group-name novamind-alb-sg --description 'VPC origin to ALB' --vpc-id $vpc --profile $p --region $r --query GroupId --output text
$taskSG = aws ec2 create-security-group --group-name novamind-task-sg --description 'ALB to Streamlit' --vpc-id $vpc --profile $p --region $r --query GroupId --output text
aws ec2 authorize-security-group-ingress --group-id $taskSG --protocol tcp --port 8501 --source-group $albSG --profile $p --region $r
$albArn = aws elbv2 create-load-balancer --name novamind-chatbot-alb --type application --scheme internal --subnets $privA $privB --security-groups $albSG --profile $p --region $r --query 'LoadBalancers[0].LoadBalancerArn' --output text
$tgArn = aws elbv2 create-target-group --name novamind-chatbot-tg --protocol HTTP --port 8501 --target-type ip --vpc-id $vpc --health-check-path '/_stcore/health' --health-check-protocol HTTP --matcher HttpCode=200 --profile $p --region $r --query 'TargetGroups[0].TargetGroupArn' --output text
aws elbv2 create-listener --load-balancer-arn $albArn --protocol HTTP --port 80 --default-actions "Type=forward,TargetGroupArn=$tgArn" --profile $p --region $r
aws elbv2 describe-target-health --target-group-arn $tgArn --profile $p --region $r
```

The ALB SG's inbound HTTP/80 rule from CloudFront's **service-managed** VPC-origin SG is added only after that SG exists (§8). The task SG rule allows ALB→task/8501 only; restrict task outbound to needed destinations after validating egress. SGs are stateful, while custom NACLs require attention to return/ephemeral ports. Check ALB idle timeout and target stickiness if Streamlit WebSocket sessions disconnect or hit different replicas. The screenshot confirms internal ALB and HTTP/80, but target health policy, SG rules and listener settings must be verified in a live resource.

**Interview answer:** “CloudFront reaches the internal ALB. Its listener forwards to healthy private task IPs on 8501; ECS updates those IP registrations as tasks roll.”

</details>

---

## 🔒 08 · CloudFront & HTTPS

**What you will learn:** Expose the private app through a public URL.

> **Remember:** User → CloudFront → VPC Origin → internal ALB → ECS task.

<details>
<summary><strong>📖 Open detailed explanation, AWS CLI commands, diagrams & interview answers</strong></summary>

**What:** a CloudFront distribution publishes a public HTTPS hostname. **Why:** the ALB stays internal. **How:** CloudFront VPC origin references the ALB ARN and creates managed private network interfaces/security group. A distribution origin references that VPC-origin ID and ALB DNS; a cache behavior forwards dynamic Streamlit traffic. Viewer TLS terminates at CloudFront. In the reconstructed example, CloudFront then uses HTTP/80 to the ALB inside the VPC-origin path. End-to-end TLS would require a certificate/HTTPS listener and `https-only` origin policy. CloudFront is delivery, not Cognito authentication.

**Reconstructed [BILLABLE: distribution traffic], not executed:**

```powershell
$albDns = aws elbv2 describe-load-balancers --load-balancer-arns $albArn --profile $p --region $r --query 'LoadBalancers[0].DNSName' --output text
$vpcOrigin = aws cloudfront create-vpc-origin --vpc-origin-endpoint-config "Name=novamind-alb-origin,Arn=$albArn,HTTPPort=80,HTTPSPort=443,OriginProtocolPolicy=http-only" --profile $p --query 'VpcOrigin.Id' --output text
aws cloudfront get-vpc-origin --id $vpcOrigin --profile $p --query 'VpcOrigin.{Status:Status,Arn:Arn}'
# After VPC origin reports Deployed and the ALB SG is allowed to receive from its managed SG:
aws cloudfront create-distribution --distribution-config file://cloudfront-distribution.json --profile $p
aws cloudfront list-distributions --profile $p --query 'DistributionList.Items[].{Id:Id,Domain:DomainName,Status:Status}'
```

Place this **illustrative** config in `cloudfront-distribution.json` only when rebuilding; replace placeholders. The policy IDs are AWS-managed. CachingDisabled protects dynamic/user-specific content; AllViewer forwards headers/cookies/query strings and enables the WebSocket handshake. Review the accepted CLI schema at deployment time.

```json
{
  "CallerReference":"novamind-unique-release-001", "Comment":"NovaMind AI reconstructed distribution", "Enabled":true,
  "Origins":{"Quantity":1,"Items":[{"Id":"novamind-private-alb","DomainName":"<internal-alb-dns-name>","VpcOriginConfig":{"VpcOriginId":"<vpc-origin-id>"}}]},
  "DefaultCacheBehavior":{
    "TargetOriginId":"novamind-private-alb","ViewerProtocolPolicy":"redirect-to-https",
    "AllowedMethods":{"Quantity":7,"Items":["GET","HEAD","OPTIONS","PUT","POST","PATCH","DELETE"],"CachedMethods":{"Quantity":2,"Items":["GET","HEAD"]}},
    "CachePolicyId":"4135ea2d-6df8-44a3-9df3-4b5a84be39ad",
    "OriginRequestPolicyId":"216adef6-5c7f-47e4-b989-5492eafa07d3"
  },
  "Restrictions":{"GeoRestriction":{"RestrictionType":"none","Quantity":0}},
  "ViewerCertificate":{"CloudFrontDefaultCertificate":true}
}
```

Discover the VPC-origin service SG after origin creation (it has a `CloudFront-VPCOrigins-Service-SG` naming pattern), then allow it into the ALB SG on 80; never edit that managed SG. AWS documents [VPC origins](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/private-content-vpc-origins.html), [CachingDisabled](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/using-managed-cache-policies.html), [AllViewer](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/using-managed-origin-request-policies.html) and [WebSockets](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/distribution-working-with.websockets.html). Test WebSocket upgrade, cookies, query strings and Streamlit `Origin`/XSRF behavior through the public hostname. `GET /` returning 200 does not prove interaction works. Avoid caching authenticated pages.

**Traffic:** browser HTTPS/443 → CloudFront → VPC-origin private connection → internal ALB HTTP/80 → healthy task private IP:8501 → Streamlit. HTML and WebSocket updates return through the same chain in reverse. Bedrock/Groq responses first arrive at Python in the task; the browser does not call those providers directly.

**Interview answer:** “CloudFront was my public HTTPS boundary. A VPC origin let it reach the internal ALB; the ALB forwarded to Streamlit. I preserved WebSocket/session traffic and disabled dynamic caching.”

</details>

---

## 🔗 09 · AWS service connections

**What you will learn:** Understand every individual connection.

> **Remember:** Ask: who calls whom, over which protocol, with which permission?

<details>
<summary><strong>📖 Open detailed explanation, AWS CLI commands, diagrams & interview answers</strong></summary>

The three gates are different: **network connectivity** asks whether a TCP/HTTPS packet can reach an endpoint; **IAM authorization** asks whether an AWS principal may call an AWS API; **application authentication** asks whether a human user may access a chat session. A successful `curl`/DNS lookup does not grant `bedrock:InvokeModelWithResponseStream`; an IAM allow cannot repair a missing IGW route; a valid task role does not sign in a Cognito user. Resource wiring is established by IDs/ARNs in task definitions, services, listeners, origin configs, security groups and environment variables—not by services magically “finding” one another.

For each service below: **what/why → configuration → caller/mechanism → CLI → security → interview phrasing**. Creation commands are reconstructed; historical CLI transcripts are **Not verified**.

### Amazon ECR

**What/why:** private image repository for versioned releases. **Configuration:** repo `novamind-chatbot-ecr` is named in `cd.yml`; SHA tag and digest identify release; immutability/scanning settings are **Not verified**. **Caller/mechanism:** GitHub runner uses an OIDC-assumed IAM role plus Docker registry HTTPS to push; Fargate's execution identity later fetches the image. ECR does not call Streamlit. **CLI:** `aws ecr describe-repositories --repository-names novamind-chatbot-ecr` and `aws ecr describe-images --repository-name novamind-chatbot-ecr`; create/push commands in §5. **Security:** separate push/pull permissions, private repo, image scanning/lifecycle as future hardening. **Interview:** “ECR stores the exact image Fargate starts; the application code does not run inside ECR.”

### Amazon ECS Fargate

**What/why:** managed long-running container compute. **Configuration:** task family `novamind-chatbot-task`, container `novamind-chatbot`, cluster/service names from `cd.yml`; actual historical CPU, memory, subnet and roles are **Not verified**. **Caller/mechanism:** ECS service scheduler launches task ENIs, uses execution role to pull image/inject secret/write logs, registers task IPs with target group. Python uses the task role separately. **CLI:** `aws ecs describe-services --cluster novamind-chatbot-cluster --services novamind-chatbot-service`; §6/§13 creation. **Security:** distinct least-privilege roles, task SG, no static keys, non-root image. **Interview:** “Fargate runs the container; ECS maintains count and handles rollout.”

### Application Load Balancer

**What/why:** internal HTTP listener and health-based routing. **Configuration:** screenshot shows internal scheme and HTTP/80; reconstructed target group uses IP/8501/`/_stcore/health`. **Caller/mechanism:** CloudFront VPC origin sends HTTP to ALB; ALB picks a healthy private task IP registered by ECS. **CLI:** `aws elbv2 describe-load-balancers`, `describe-listeners`, `describe-target-health`; §7. **Security:** origin-managed SG → ALB/80; ALB SG → task/8501. **Interview:** “The ALB routes an incoming request to a healthy Fargate task without exposing a task's changing IP as the public URL.”

### Amazon CloudFront

**What/why:** public HTTPS edge and VPC-origin bridge. **Configuration:** VPC-origin ID points to internal ALB; distribution behavior should forward Streamlit headers/cookies/query strings and avoid dynamic caching. Exact historic policy IDs are **Not verified**. **Caller/mechanism:** browser HTTPS DNS resolves distribution name; CloudFront uses service-managed private ENIs to reach ALB. **CLI:** `aws cloudfront list-distributions`, `get-vpc-origin`, `get-distribution`; §8. **Security:** HTTPS viewer policy, restricted ALB SG, consider WAF and logs; public URL alone does not authenticate users. **Interview:** “CloudFront is the public door; VPC origin gives it a private path to the ALB.”

### Amazon VPC

**What/why:** IP space, subnet placement, routing and SG boundaries. **Configuration:** diagram's `10.20.0.0/16` and four /24 CIDRs; exact live route tables/ENIs are **Not verified**. **Caller/mechanism:** packet routing, VPC DNS and SG checks enable each hop; IAM is unrelated to packet forwarding. **CLI:** `aws ec2 describe-vpcs`, `describe-subnets`, `describe-route-tables`, `describe-network-interfaces`, `describe-security-groups`; §4. **Security:** minimize exposed ports, review egress and NACL return traffic. **Interview:** “I can trace every packet: CloudFront-managed ENI to ALB, then ALB to private task IP, with distinct outbound path from task to service APIs.”

### IAM roles and policies

**What/why:** service API authorization. **Configuration:** execution role trusts `ecs-tasks.amazonaws.com` for bootstrap; task role trusts the same principal but grants runtime Bedrock and optional storage; GitHub deployment role trusts the GitHub OIDC issuer with repo/ref conditions. Actual historical policy JSON is **Not verified**. **Caller/mechanism:** AWS STS supplies temporary credentials; SigV4 signs AWS SDK/CLI calls. Cognito public user APIs in this code are explicitly unsigned and use user credentials/tokens, not task IAM. **CLI:** `aws iam get-role --role-name <name>` and `list-attached-role-policies`; §13 examples. **Security:** resource-scoped permissions, separate trust/permission policies, no long-lived CI keys. **Interview:** “An IAM trust policy says who may assume a role; an identity policy says what that role may do.”

### Amazon Cognito

**What/why:** user pool authenticates people. **Configuration:** app reads `COGNITO_USER_POOL_ID` and `COGNITO_APP_CLIENT_ID`; a public client without client secret must permit `USER_PASSWORD_AUTH` and relevant user scope. **Caller/mechanism:** the Streamlit server makes HTTPS calls to `cognito-idp.us-east-1.amazonaws.com` for `InitiateAuth`, `RespondToAuthChallenge`, `GetUser` and `GlobalSignOut`; bearer access token is checked online. It is **not** an ALB/CloudFront auth integration. **CLI:** `aws cognito-idp describe-user-pool --user-pool-id <id>` and `describe-user-pool-client`; §13. **Security:** TLS, MFA where configured, token expiry/idle checks, no client secret in public app. **Interview:** “The app itself asks Cognito to authenticate and verify the human; network access to Cognito is needed, but the user-token APIs do not use the ECS task role.”

### Amazon Bedrock

**What/why:** managed foundation-model inference. **Configuration:** code fixes region and defaults to Nova Pro, while UI supports additional configured models; live model entitlement is **Not verified**. **Caller/mechanism:** after auth/request validation, Python's boto3 `bedrock-runtime` client signs HTTPS `ConverseStream` using ECS task-role credentials. **CLI:** `aws bedrock list-foundation-models --region us-east-1` can inspect catalog; permission to invoke a model is a separate check. **Security:** scoped `bedrock:InvokeModelWithResponseStream` on approved model or inference-profile resources; capability/input limits and safe logs. **Interview:** “Bedrock is the inference API, not my hosting layer. The task calls it with its IAM role, then streams result chunks back through Streamlit.”

### AWS Secrets Manager

**What/why:** stores the external Groq API key outside code/image. **Configuration:** screenshots show a historical secret entry; exact current ARN/key value is **Not verified**. Reconstructed task definition references its ARN under `secrets`. **Caller/mechanism:** ECS/Fargate retrieves the secret with the **execution role** before starting the container, then exposes `GROQ_API_KEY` as an environment variable. The Python Groq adapter reads that variable; it does **not** call Secrets Manager directly. **CLI:** `aws secretsmanager describe-secret --secret-id <name-or-arn>`; avoid `get-secret-value` in documentation or diagnostics. **Security:** execution-role `GetSecretValue` scoped to ARN, KMS permission if using customer-managed key, rotation/redeployment planning; environment variables can still be read by code in the task. **Interview:** “ECS injects the key at startup from Secrets Manager. My app reads only its runtime variable.”

### Amazon CloudWatch

**What/why:** central ECS container logs and operational metrics. **Configuration:** `awslogs` task-definition driver writes to `/ecs/novamind-chatbot`; screenshot shows one-week retention at capture time. Alarms/dashboards are **Not verified**. **Caller/mechanism:** Fargate log driver sends container stdout/stderr via execution role; [`services/observability.py`](services/observability.py) writes sanitized JSON events to stderr. **CLI:** `aws logs describe-log-groups --log-group-name-prefix /ecs/novamind-chatbot` and `aws logs tail /ecs/novamind-chatbot --since 1h`. **Security:** avoid prompts/tokens/secrets in logs, limit retention/readers, use alarms for availability. **Interview:** “CloudWatch lets me correlate ECS task failures and application error categories without logging user content.”

### External Groq API

**What/why:** optional text-only inference provider; it is **not** an AWS service. **Configuration:** `NOVAMIND_AI_PROVIDER`, configured Groq model, and `GROQ_API_KEY` at runtime. **Caller/mechanism:** Python `urllib.request` sends a bearer-authenticated HTTPS POST to `https://api.groq.com/openai/v1/chat/completions` and parses event-stream chunks. This is an alternative to Bedrock for one request, not a sequential Bedrock→Groq hop. **CLI:** no AWS CLI creates Groq; AWS CLI only configures secret/network resources supporting it. **Security:** controlled outbound HTTPS/DNS, keep key outside image, enforce text-only model policy. **Interview:** “Selecting Groq switches the provider adapter; the container calls Groq directly over HTTPS, using a key injected by ECS.”

### GitHub Actions OIDC

**What/why:** short-lived deployment identity without repository AWS access keys. **Configuration:** `cd.yml` requests `id-token: write` and assumes `novamind-chatbot-github-actions-role`; actual role trust document is **Not verified**. **Caller/mechanism:** GitHub issues an OIDC token; AWS STS validates issuer/audience/subject and returns temporary role credentials to `configure-aws-credentials@v4`; the runner then calls ECR/ECS APIs. **CLI:** `aws iam get-open-id-connect-provider --open-id-connect-provider-arn <arn>` and `aws iam get-role --role-name novamind-chatbot-github-actions-role`; §13. **Security:** trust condition restricted to exact repository and `refs/heads/main`, least-privilege ECR/ECS/`iam:PassRole`. **Interview:** “GitHub never stores a permanent AWS key; each approved CD run exchanges its OIDC token for a temporary deployment role.”

### Optional DynamoDB and Amazon S3

**What/why:** DynamoDB can hold owner-scoped saved conversation snapshots; S3 can hold saved attachment bytes. These are **optional code paths**, not verified historical deployed resources. **Configuration:** `NOVAMIND_DYNAMODB_TABLE` and `NOVAMIND_S3_BUCKET` must name existing resources; no auto-provisioning in Python. **Caller/mechanism:** the authenticated task calls regional DynamoDB/S3 APIs over HTTPS using its task role; saving/loading is independent of CloudFront ingress and Bedrock inference. **CLI:** read-only `aws dynamodb describe-table --table-name <name>` and `aws s3api head-bucket --bucket <name>`; do not create them merely because modules exist. **Security:** task-role permissions restricted to the table/bucket and owner-scoped object keys; private bucket, encryption and lifecycle. **Interview:** “Optional saved history is separate from live Streamlit session memory and was not proved active by source alone.”

</details>

---

## 🧠 10 · Auth & AI providers

**What you will learn:** Connect Cognito, Bedrock, Groq and secrets.

> **Remember:** Cognito validates users; Bedrock/Groq answer prompts; secrets are injected at startup.

<details>
<summary><strong>📖 Open detailed explanation, AWS CLI commands, diagrams & interview answers</strong></summary>

**Cognito:** A user enters credentials into the Streamlit form. The server calls `InitiateAuth` with `USER_PASSWORD_AUTH` and its app client ID. If Cognito asks for SMS/TOTP MFA, the server calls `RespondToAuthChallenge`. It checks access-token context/expiry locally as a rejection filter, then calls `GetUser` with the exact token to verify identity online. [`AuthSession`](services/auth_service.py) holds the token, subject and timestamps in server session state; inactivity/absolute limits and the UI watchdog clear it. This is not a Cognito Hosted UI redirect or ALB authentication. The task must reach Cognito's public HTTPS endpoint in this reconstructed network. No user password or token should be logged.

**Bedrock:** An authenticated session selects a model in the UI. The app validates text, file type/size and model capability, builds content blocks and a bounded history, then `bedrock-runtime.converse_stream` sends a SigV4-signed HTTPS request. Stream events yield text chunks to Streamlit. [`novamind/ui/chat.py`](novamind/ui/chat.py) displays partial output but commits a turn to AI history only after successful completion. Nova Micro is text-only in local policy; Groq is text-only. A visible model option does not prove the AWS account has current model access. `bedrock:InvokeModelWithResponseStream` must cover the actual model/inference-profile resource being invoked.

[`novamind/config/settings.py`](novamind/config/settings.py) offers Nova Pro, Nova Lite, Nova Micro, Claude 3.5 Sonnet, and one configured Groq model in the UI. [`services/provider_config.py`](services/provider_config.py) restricts that Groq choice to the configured Llama 3.3 70B or GPT-OSS 120B identifier. Availability, model access, pricing and provider support can change; verify them in the intended account before a new deployment.

**Secrets Manager and Groq:** The secret is fetched at task startup by ECS using the execution role, not during each chat turn. If a user selects the configured Groq option, `services/groq_service.py` reads the injected key, sends text-only messages to Groq over HTTPS/443, and yields streamed chunks. It does not send image/document blocks to Groq. Groq requires outbound internet/DNS in the task network. Bedrock and Groq are alternative provider branches; Cognito is the prior user-auth gate and Secrets Manager is a startup dependency. Optional saved conversations use DynamoDB/S3 as another independent path only when configured.

**Practical checks (read-only; do not retrieve secret values):**

```powershell
aws cognito-idp describe-user-pool-client --user-pool-id <pool-id> --client-id <client-id> --profile novamind --region us-east-1
aws iam get-role --role-name <application-task-role-name> --profile novamind
aws secretsmanager describe-secret --secret-id <groq-secret-name-or-arn> --profile novamind --region us-east-1
aws logs tail /ecs/novamind-chatbot --since 1h --profile novamind --region us-east-1
```

**Interview answer:** “Cognito verifies the human user. For an authenticated chat, the task chooses either the AWS-authorized Bedrock streaming API or bearer-authenticated Groq HTTPS API. ECS gets the Groq key from Secrets Manager at startup; the browser never receives that key.”

</details>

---

## 🚀 11 · GitHub Actions CI/CD

**What you will learn:** Move a tested code change into the running app.

> **Remember:** Push → tests/build → manually start CD → ECR → new ECS revision.

<details>
<summary><strong>📖 Open detailed explanation, AWS CLI commands, diagrams & interview answers</strong></summary>

**Original provisioning vs later deployment:** The historical VPC, ALB, CloudFront, IAM, Cognito, ECR and ECS service had to be created first by CLI/console or another method; the exact provisioning transcript is **Not verified**. [`cd.yml`](.github/workflows/cd.yml) assumes those resources already exist and only publishes an image, registers a task revision and updates an ECS service. Running CD against a cleaned-up account will fail until infrastructure is rebuilt.

**Automatic CI:** On pushes to `main` and PRs targeting `main`, a `windows-latest` job installs Python `3.14.6`, `requirements.txt`, runs `pip check` and `python -B -m tests.run_offline`. The suite guards against network/AWS calls. A dependent Ubuntu job runs `docker build -t novamind-ai:ci .`. This proves a controlled offline code check and Linux image build on GitHub runners; it does not prove real AWS credentials, live Bedrock/Cognito, a browser/WebSocket path, or deployability of missing infrastructure.

**Manual CD:** `workflow_dispatch` only. It refuses non-`main` refs, queries the GitHub API for a successful **push-triggered** CI run for the exact `github.sha` (the workflow uses the currently hard-coded CI workflow ID `383313071`), then federates via `aws-actions/configure-aws-credentials@v4`. It logs in to ECR, reuses an existing valid SHA-tag digest or builds/pushes the image, copies the active ECS task definition, changes only the `novamind-chatbot` image, registers a revision, updates `novamind-chatbot-service`, waits for `services-stable`, and verifies primary rollout `COMPLETED`, task ARN and image URI. Concurrency serializes deployment jobs. Manual dispatch is a deliberate human promotion step after CI; fully automatic CD would start after every eligible push.

**The demonstrated chain:** commit `50a5d3f` changed `Welcome back` → `Welcome back folk` in the login renderer → push to GitHub → automatic CI success → manual CD success → user verified updated text at public CloudFront URL. Source/Git prove the line change; the user report and screenshots support the historical live verification. Current public URL/resources are **Not verified**.

**Local command examples only, not executed here:**

```powershell
git status --short
git add novamind/ui/auth.py
git commit -m 'demo: update welcome message for CI CD testing'
git push origin main
gh run list --workflow ci.yml --branch main --limit 10
gh workflow run cd.yml --ref main
gh run list --workflow cd.yml --branch main --limit 10
aws ecs describe-services --cluster novamind-chatbot-cluster --services novamind-chatbot-service --profile novamind --region us-east-1 --query 'services[0].{Task:taskDefinition,Deployments:deployments}'
aws ecs describe-task-definition --task-definition novamind-chatbot-task --profile novamind --region us-east-1 --query 'taskDefinition.containerDefinitions[?name==`novamind-chatbot`].image'
```

The `gh workflow run` and `git push` examples would trigger external work; they are here to explain history, **not instructions to run now**. The CD workflow does not create or verify an ECS deployment circuit breaker. If the service was created with circuit breaker + rollback, ECS can revert a failed rolling deployment; that historical setting is **Not verified**. `services-stable` and revision checks verify ECS state, not an authenticated CloudFront smoke test. A true live verification opens the URL, signs in, tests WebSocket/chat, and checks the expected heading and deployed SHA.

**Interview answer:** “CI runs automatically on main and PRs. CD is a separate manual promotion: it insists on successful CI for that exact SHA, assumes AWS through OIDC, deploys a SHA-tagged image, and checks the ECS rollout. I demonstrated it with the login-heading change.”

</details>

---

## 👤 12 · One user request

**What you will learn:** Follow a real user from login to model answer.

> **Remember:** The browser reaches the app through CloudFront and ALB; Python calls AI providers.

<details>
<summary><strong>📖 Open detailed explanation, AWS CLI commands, diagrams & interview answers</strong></summary>

1. Browser resolves the CloudFront distribution DNS and connects over HTTPS/443. CloudFront forwards the initial GET and later Streamlit WebSocket upgrade through the VPC origin; its managed ENI reaches the internal ALB. ALB SG allows the CloudFront-managed SG; listener HTTP/80 forwards to a healthy private task IP:8501. The task SG accepts only the ALB SG.
2. Streamlit returns the login UI. The browser enters credentials into the app; the server calls Cognito HTTPS. Cognito may challenge for MFA, then returns user tokens. The app verifies the access token with `GetUser` and stores a bounded authenticated session server-side. CloudFront/ALB merely transport this traffic; they do not make the Cognito decision.
3. For a text prompt, the app checks the session and request budget. The selected provider decides the branch: task-role-signed Bedrock `ConverseStream`, or Groq HTTPS with runtime API key. The selected model receives bounded conversation history. Output chunks return to Streamlit and travel back over the existing browser connection.
4. For an image/document upload, bytes travel browser → CloudFront → ALB → Streamlit task. Code validates extension, size and actual content (`services/image_service.py`, `services/document_service.py`), then checks selected model capability. Supported images include JPEG/PNG/GIF/WebP (max 3.75 MiB); supported docs include PDF/TXT/MD/HTML/CSV/DOC/DOCX/XLS/XLSX (max 4.5 MiB). Bedrock receives compatible content blocks; Groq is text-only. Optional persistence may write owner-scoped snapshots/attachments to configured DynamoDB/S3, but is not required for a live response.
5. Logs go to CloudWatch independently. ECR is not involved in each user request: it supplied the image at task start. Secrets Manager is not called by the Python Groq adapter per request: ECS injected the key at start. Responses return model → task → ALB → VPC origin → CloudFront → browser. Auth failures stop before inference.

### Infrastructure architecture

```mermaid
flowchart LR
  U[Public browser] -->|HTTPS 443 + WebSocket| CF[CloudFront distribution]
  CF --> VO[VPC origin managed ENI]
  subgraph VPC[Reconstructed VPC 10.20.0.0/16]
    VO -->|HTTP 80| ALB[Internal ALB in private subnets]
    ALB -->|IP target 8501| ECS[ECS Fargate Streamlit tasks in public subnets]
  end
  ECS -->|HTTPS user token APIs| C[Cognito]
  ECS -->|HTTPS SigV4 task role| B[Bedrock]
  ECS -->|HTTPS bearer key| G[Groq]
  ECS -. optional .-> D[DynamoDB and S3]
  ECS --> CW[CloudWatch Logs]
  ECR[ECR image] -->|pull at startup: execution role| ECS
  SM[Secrets Manager] -->|injection at startup: execution role| ECS
```

### Network topology and trust boundaries

```mermaid
flowchart TB
  Internet[Internet users] --> CF[CloudFront HTTPS]
  subgraph V[VPC 10.20.0.0/16: reconstruction]
    IGW[Internet Gateway]
    subgraph Private[Private ALB subnets: 10.20.11/24 + 10.20.12/24]
      ENI[CloudFront-managed ENI/SG] -->|SG rule 80| ALB[Internal ALB]
    end
    subgraph Public[Public task subnets: 10.20.1/24 + 10.20.2/24]
      Task[Task ENI private + public IP]
    end
    ALB -->|VPC local route; SG rule 8501| Task
    Task -->|default route; outbound 443| IGW
  end
  CF --> ENI
  IGW --> APIs[Regional AWS APIs and optional Groq]
```

### Service integration and deployment pipeline

```mermaid
flowchart LR
  Dev[Windows source] -->|commit/push| GH[GitHub main]
  GH -->|automatic| CI[Offline Python CI then Docker build]
  CI -->|manual dispatch + same-SHA check| CD[GitHub CD]
  CD -->|OIDC STS| IAM[Deployment role]
  CD -->|SHA image push| ECR[ECR]
  CD -->|new task revision + service update| ECS[ECS]
  ECR -->|execution-role pull| ECS
  ECS --> ALB[ALB healthy target]
  ALB --> CF[CloudFront public check]
```

### One authenticated chat request

```mermaid
sequenceDiagram
  participant User as Browser
  participant Edge as CloudFront/VPC origin
  participant ALB as Internal ALB
  participant App as Streamlit task
  participant Auth as Cognito
  participant AI as Bedrock or Groq
  User->>Edge: HTTPS page + WebSocket
  Edge->>ALB: Private HTTP/80
  ALB->>App: Healthy IP target:8501
  App-->>User: Login UI via same path
  User->>App: Credentials through edge/ALB
  App->>Auth: InitiateAuth; optional MFA; GetUser
  Auth-->>App: Tokens + verified user
  User->>App: Prompt / validated upload through edge/ALB
  App->>AI: Selected provider HTTPS request
  AI-->>App: Stream or response
  App-->>User: Streamlit chunks through ALB/edge
```

These diagrams show the **reconstructed private-ALB/public-task placement**. The committed architecture picture has different visual tier placement; neither proves the actual deleted service's `awsvpcConfiguration`.

</details>

---

## 🛠️ 13 · AWS CLI deployment recipe

**What you will learn:** See the infrastructure-creation order.

> **Remember:** Treat commands as historical reconstructions, not instructions to run now.

<details>
<summary><strong>📖 Open detailed explanation, AWS CLI commands, diagrams & interview answers</strong></summary>

This is a **reconstructed example from an empty account**, not the historical command transcript. Run only after selecting the correct AWS account, checking service quotas/model access and accepting charges. `<...>` means an actual ID/ARN/value obtained from an earlier response; do not copy it literally. PowerShell variables are session-local. AWS CLI v2 may change input schemas; use `aws <service> <operation> help` at execution time. The account/region/profile must be checked at each new terminal session. Steps 4–11 can incur ongoing charges. For each step, the expected result and troubleshooting cue are given so the command is teachable rather than a spell to memorize.

### Step 1 — Local project preparation

**Purpose/prerequisite:** establish the correct source, entry point and working tree before packaging; no AWS resource yet. **Command (read-only example):**

```powershell
Set-Location 'E:\codex-projetc\Chatbot_text_image'
git status --short
git rev-parse HEAD
Get-Content .\Dockerfile -TotalCount 12
Get-Content .\.github\workflows\ci.yml -TotalCount 20
```

**Parameters/output/connection:** `git rev-parse HEAD` prints the commit whose SHA will become the image tag. A clean tree makes that tag traceable; uncommitted source can otherwise produce an image different from the named commit. **Common error:** wrong directory or dirty tree. **Interview line:** “I identify the exact source revision before building.”

### Step 2 — Docker build and local test

**Purpose/prerequisite:** Docker Desktop Linux engine available. **Command (local, not AWS-billable; not executed):**

```powershell
docker build --tag novamind-ai:local .
docker run --detach --name novamind-local --publish 8502:8501 novamind-ai:local
Invoke-WebRequest 'http://localhost:8502/_stcore/health'
docker logs novamind-local
```

**Parameters/output/connection:** `.` is build context; `--publish` maps host 8502 to container 8501; expect a built image and health HTTP 200. This proves image startup before ECR upload. **Errors:** missing Linux wheel/import, Docker engine stopped, occupied 8502, Cognito config absent for login. **Interview line:** “I validated the exact Linux container independently of AWS.”

### Step 3 — AWS CLI authentication

**Purpose/prerequisite:** approved human credentials/profile. **Read-only command:**

```powershell
$p = 'novamind'; $r = 'us-east-1'
aws sts get-caller-identity --profile $p --region $r
$account = aws sts get-caller-identity --profile $p --region $r --query Account --output text
```

**Parameters/output/connection:** account and principal ARN identify where later API calls would go. `--profile` does not become task runtime auth. **Errors:** expired SSO/session, wrong profile, no AWS CLI. **Interview line:** “I checked who my CLI was before creating resources.”

### Step 4 — VPC and networking **[BILLABLE for related IP/traffic; commands not executed]**

**Purpose/prerequisite:** account/region checked; two supported AZs. **Command:** run the explicit `create-vpc`, four `create-subnet`, IGW, route-table and association sequence in §4; verify with:

```powershell
aws ec2 describe-vpcs --vpc-ids $vpc --profile $p --region $r --query 'Vpcs[0].{Id:VpcId,Cidr:CidrBlock}'
aws ec2 describe-subnets --filters "Name=vpc-id,Values=$vpc" --profile $p --region $r --query 'Subnets[].{Id:SubnetId,AZ:AvailabilityZone,Cidr:CidrBlock}'
aws ec2 describe-route-tables --filters "Name=vpc-id,Values=$vpc" --profile $p --region $r --query 'RouteTables[].{Id:RouteTableId,Routes:Routes,Associations:Associations}'
```

**Parameters/output/connection:** IDs from creation become ALB/task subnet and SG inputs; public route table must show IGW default route and private ALB route table must not. **Errors:** CIDR overlap, AZ unavailable, quota, no available IPs. **Interview line:** “I created the address space and two-AZ routes before attaching compute.”

### Step 5 — Security groups and IAM **[BILLABLE only indirectly; commands not executed]**

**Purpose/prerequisite:** VPC exists. **Command:** create ALB/task SGs and task inbound 8501 rule in §7. Then create *separate* ECS execution/task roles. Save the following common ECS trust document as `ecs-task-trust.json` when provisioning (not during this documentation task):

```json
{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"ecs-tasks.amazonaws.com"},"Action":"sts:AssumeRole"}]}
```

```powershell
aws iam create-role --role-name novamind-ecs-execution-role --assume-role-policy-document file://ecs-task-trust.json --profile $p
aws iam create-role --role-name novamind-ecs-task-role --assume-role-policy-document file://ecs-task-trust.json --profile $p
aws iam attach-role-policy --role-name novamind-ecs-execution-role --policy-arn arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy --profile $p
aws iam get-role --role-name novamind-ecs-task-role --profile $p --query 'Role.Arn' --output text
```

**Parameters/output/connection:** role ARN goes in `taskRoleArn` or `executionRoleArn` of the task definition. The AWS-managed execution policy covers baseline ECR pull/CloudWatch logging; add a *separate resource-scoped* execution-role inline policy for `secretsmanager:GetSecretValue` on the exact secret ARN and `kms:Decrypt` if its CMK requires it. Add a *separate* task-role policy for `bedrock:InvokeModelWithResponseStream` on approved foundation-model/inference-profile ARNs; optional DynamoDB/S3 permissions only if those stores are actually enabled. The deploy principal also needs constrained `iam:PassRole` for the two roles. Use `aws iam put-role-policy --role-name <role> --policy-name <name> --policy-document file://<reviewed-policy.json> --profile $p` after reviewing the JSON; no historical policy is available. IAM propagation may require waiting before registering the task. **Errors:** `AccessDenied`/`PassRole`, wrong trust principal, too-broad `Resource:*`, SG source points to wrong SG. **Interview line:** “The execution role boots the task; the task role authorizes my Python code; SGs control packets, not API permissions.”

For clarity, these **reconstructed** policy bodies show the boundary; replace ARNs and save each as a separate reviewed JSON file only for a future deployment. A customer-managed KMS key may require an additional scoped `kms:Decrypt` statement on the execution role. A selected Bedrock inference profile may require permission on additional underlying resources, so inspect the exact approved model/profile before finalizing the task policy.

```json
{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Action":"secretsmanager:GetSecretValue","Resource":"<groq-secret-arn>"}]}
```

```json
{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Action":"bedrock:InvokeModelWithResponseStream","Resource":"<approved-model-or-inference-profile-arn>"}]}
```

```powershell
aws iam put-role-policy --role-name novamind-ecs-execution-role --policy-name NovaMindSecretRead --policy-document file://execution-secret-policy.json --profile $p
aws iam put-role-policy --role-name novamind-ecs-task-role --policy-name NovaMindBedrockInvoke --policy-document file://task-bedrock-policy.json --profile $p
```

### Step 6 — Amazon ECR **[BILLABLE: storage/transfer; not executed]**

**Purpose/prerequisite:** Docker image and AWS publishing permission. **Command:** run the `create-repository`, `get-login-password`, `docker tag`, `docker push`, `describe-images` sequence in §5. **Parameters/output/connection:** `novamind-chatbot-ecr:<git-sha>` becomes task `image`; expect a `sha256:` digest. **Errors:** expired Docker registry token, wrong account/region, ECR push denied, immutable tag already exists, build architecture mismatch. **Interview line:** “ECR is the handoff between my image build and Fargate start.”

### Step 7 — ECS task definition **[BILLABLE once tasks run; not executed]**

**Purpose/prerequisite:** ECR image, roles, log group, Cognito IDs, and optional secret ARN. **Command:** save the reviewed JSON from §6 with real ARNs/IDs, then:

```powershell
$taskArn = aws ecs register-task-definition --cli-input-json file://task-definition.json --profile $p --region $r --query 'taskDefinition.taskDefinitionArn' --output text
aws ecs describe-task-definition --task-definition $taskArn --profile $p --region $r --query 'taskDefinition.{Family:family,Revision:revision,Image:containerDefinitions[0].image,Execution:executionRoleArn,Task:taskRoleArn}'
```

**Parameters/output/connection:** expect family revision/ARN; `image` must match uploaded SHA. CPU/memory must be a valid Fargate pair. Port 8501 must match Docker/target group. **Errors:** invalid Fargate CPU/memory combination, malformed ARN/JSON, missing `iam:PassRole`, inaccessible secret. **Interview line:** “The task definition is the versioned blueprint for the running container.”

### Step 8 — ALB and target group **[BILLABLE: ALB-hours/LCUs; not executed]**

**Purpose/prerequisite:** VPC/private subnets and SGs. **Command:** run `create-load-balancer`, `create-target-group --target-type ip`, and `create-listener` in §7. **Parameters/output/connection:** expect `albArn`, `tgArn`, ALB DNS; listener's forward action binds ALB → target group. Targets remain empty until ECS service registers tasks. **Errors:** ALB subnet IP shortage, duplicate name, target type `instance`, wrong VPC, SG/port mismatch. **Interview line:** “The listener routes HTTP/80 into an IP target group checking Streamlit on 8501.”

### Step 9 — ECS Fargate service **[BILLABLE: running Fargate; not executed]**

**Purpose/prerequisite:** task definition, target group, task public subnets/SG, execution/network egress. **PowerShell-compatible illustrative JSON:** save as `ecs-service.json` after replacing `<...>`; `desiredCount=1` is example capacity, not historic count.

```json
{
  "cluster":"novamind-chatbot-cluster", "serviceName":"novamind-chatbot-service",
  "taskDefinition":"<task-definition-arn>", "desiredCount":1, "launchType":"FARGATE",
  "deploymentController":{"type":"ECS"},
  "deploymentConfiguration":{"deploymentCircuitBreaker":{"enable":true,"rollback":true}},
  "networkConfiguration":{"awsvpcConfiguration":{
    "subnets":["<public-subnet-a>","<public-subnet-b>"],
    "securityGroups":["<task-sg>"], "assignPublicIp":"ENABLED"
  }},
  "loadBalancers":[{"targetGroupArn":"<target-group-arn>","containerName":"novamind-chatbot","containerPort":8501}],
  "healthCheckGracePeriodSeconds":60
}
```

```powershell
aws ecs create-service --cli-input-json file://ecs-service.json --profile $p --region $r
aws ecs wait services-stable --cluster novamind-chatbot-cluster --services novamind-chatbot-service --profile $p --region $r
aws ecs describe-services --cluster novamind-chatbot-cluster --services novamind-chatbot-service --profile $p --region $r --query 'services[0].{Desired:desiredCount,Running:runningCount,Events:events[:5].message,Deployment:deploymentConfiguration}'
aws elbv2 describe-target-health --target-group-arn $tgArn --profile $p --region $r
```

**Parameters/output/connection:** `awsvpcConfiguration` creates task ENIs in **public** subnets in this reconstruction; `assignPublicIp=ENABLED` plus IGW route enables outbound HTTPS. `loadBalancers` tells ECS which task IP/port to register. Expect `runningCount=desiredCount` and healthy targets. Circuit breaker/rollback is **enabled in this example**, but historical setting is **Not verified**. **Errors:** `ResourceInitializationError` (ECR/secret/log network or IAM), unhealthy targets, tasks stopped, denied task-role calls after startup. **Interview line:** “The service maintained my tasks and attached them to the target group; its ENI placement determined outbound connectivity.”

### Step 10 — CloudFront VPC Origin **[BILLABLE when used; not executed]**

**Purpose/prerequisite:** active internal ALB, attached IGW, private subnet free IPs, CloudFront service-linked role. **Command:** run §8 `create-vpc-origin`, wait for status `Deployed`, then discover its service-managed SG and allow it to ALB/80:

```powershell
aws cloudfront get-vpc-origin --id $vpcOrigin --profile $p --query 'VpcOrigin.Status' --output text
aws ec2 describe-security-groups --filters "Name=vpc-id,Values=$vpc" 'Name=group-name,Values=CloudFront-VPCOrigins-Service-SG*' --profile $p --region $r --query 'SecurityGroups[].{Id:GroupId,Name:GroupName}'
# Set $cfServiceSG to the verified GroupId from the response, then:
aws ec2 authorize-security-group-ingress --group-id $albSG --protocol tcp --port 80 --source-group $cfServiceSG --profile $p --region $r
```

**Parameters/output/connection:** VPC origin binds CloudFront-managed private networking to ALB ARN; the SG rule permits its traffic. Expect `Deployed` and one service SG in the VPC. **Errors:** origin still `InProgress`, no IGW/private IPs, insufficient CloudFront service-linked-role permissions, SG not yet created. **Interview line:** “CloudFront VPC origin is the private bridge to an internal ALB; I allowed its managed SG into the ALB.”

### Step 11 — Public CloudFront distribution **[BILLABLE: requests/transfer; not executed]**

**Purpose/prerequisite:** deployed VPC origin and working ALB target. **Command:** use the JSON/CLI in §8, then:

```powershell
aws cloudfront list-distributions --profile $p --query 'DistributionList.Items[].{Id:Id,Domain:DomainName,Status:Status}'
aws cloudfront get-distribution --id <distribution-id> --profile $p --query 'Distribution.{Status:Status,DomainName:DomainName}'
```

**Parameters/output/connection:** config `VpcOriginId` wires the origin; `TargetOriginId` wires the default behavior; viewer certificate gives a `cloudfront.net` HTTPS URL. Expect distribution `Deployed`; wait for propagation. **Errors:** invalid/missing origin ID or JSON, origin SG blocked, wrong Host/WebSocket behavior, 502/504 from unhealthy ALB target. **Interview line:** “The distribution exposed the private app publicly through CloudFront HTTPS, not through an internet-facing ALB.”

### Step 12 — Cognito and AI integrations **[BILLABLE for Cognito/secret/model use; not executed]**

**Purpose/prerequisite:** user pool/client and approved model; task network egress. Historical Cognito IDs/secret values are **Not verified** and must not be recovered by reading secrets. **Reconstructed commands:**

```powershell
$poolId = aws cognito-idp create-user-pool --pool-name NovaMind-Users --profile $p --region $r --query 'UserPool.Id' --output text
$clientId = aws cognito-idp create-user-pool-client --user-pool-id $poolId --client-name novamind-public-client --no-generate-secret --explicit-auth-flows ALLOW_USER_PASSWORD_AUTH ALLOW_REFRESH_TOKEN_AUTH --profile $p --region $r --query 'UserPoolClient.ClientId' --output text
aws cognito-idp describe-user-pool-client --user-pool-id $poolId --client-id $clientId --profile $p --region $r --query 'UserPoolClient.{Id:ClientId,Flows:ExplicitAuthFlows}'
aws bedrock list-foundation-models --profile $p --region $r --query 'modelSummaries[].modelId'
aws secretsmanager describe-secret --secret-id <groq-secret-name-or-arn> --profile $p --region $r
```

**Parameters/output/connection:** set pool/client IDs as ordinary task config. A pool does not contain a user automatically; approved account enrollment and MFA/recovery policy are separate tasks. Select a currently available model and scope the task role to its actual resources. A Groq secret must be created by an approved secure process; if using CLI, use `aws secretsmanager create-secret --name <name> --secret-string file://<approved-secure-local-path> --profile $p --region $r` and never paste the value in command history, logs or this guide. Reference its ARN in task `secrets`; create a new task revision/service deployment when these settings change because running tasks do not automatically reload injected secrets. **Errors:** Cognito client lacks `USER_PASSWORD_AUTH`, `GetUser` token scope/context mismatch, Bedrock model access/role denied, no outbound HTTPS, Groq key missing. **Interview line:** “Cognito authenticated users; my task role invoked Bedrock; ECS injected the optional external API secret before app startup.”

### Step 13 — GitHub Actions CI/CD **[BILLABLE on deployment; not executed]**

**Purpose/prerequisite:** base infrastructure exists; exact repo is `aamir490/Use--Case--25--NovaMind-AI-Multimodal-GenAI-Chatbot-AWS` from Git remote; CI workflow ID/trust subject should be rechecked. **Reconstructed IAM trust:** create an OIDC provider for `https://token.actions.githubusercontent.com` with audience `sts.amazonaws.com` if absent (verify current AWS IAM OIDC-provider setup); create a deployment role whose trust restricts `aud` and `sub` to `repo:aamir490/Use--Case--25--NovaMind-AI-Multimodal-GenAI-Chatbot-AWS:ref:refs/heads/main`:

If no suitable provider exists, an illustrative `github-oidc-provider.json` is `{"Url":"https://token.actions.githubusercontent.com","ClientIDList":["sts.amazonaws.com"]}`. AWS IAM retrieves a thumbprint when the optional `ThumbprintList` is omitted; confirm the current IAM requirements and do not duplicate a provider already shared by other repositories. Create it with `aws iam create-open-id-connect-provider --cli-input-json file://github-oidc-provider.json --profile $p`; the returned ARN becomes `<github-oidc-provider-arn>` below. This is **[MUTATING]** and was not executed.

```json
{
  "Version":"2012-10-17",
  "Statement":[{"Effect":"Allow","Principal":{"Federated":"<github-oidc-provider-arn>"},
    "Action":"sts:AssumeRoleWithWebIdentity",
    "Condition":{"StringEquals":{
      "token.actions.githubusercontent.com:aud":"sts.amazonaws.com",
      "token.actions.githubusercontent.com:sub":"repo:aamir490/Use--Case--25--NovaMind-AI-Multimodal-GenAI-Chatbot-AWS:ref:refs/heads/main"
    }}}]
}
```

```powershell
aws iam list-open-id-connect-providers --profile $p
aws iam create-role --role-name novamind-chatbot-github-actions-role --assume-role-policy-document file://github-oidc-trust.json --profile $p
aws iam get-role --role-name novamind-chatbot-github-actions-role --profile $p --query 'Role.Arn' --output text
gh run list --workflow ci.yml --branch main --limit 10
gh workflow run cd.yml --ref main
```

**Parameters/output/connection:** role ARN must match `cd.yml`; give only ECR repository publish, ECS describe/register/update, and constrained `iam:PassRole` permissions. The workflow obtains short-lived credentials; CI must succeed on the exact SHA before manual CD. `gh workflow run` would actually dispatch CD; **do not run for this documentation task**. **Errors:** OIDC `sub` mismatch, audience/trust denial, ECR push denied, `iam:PassRole` denied, hard-coded CI workflow ID changed, ECS service absent after cleanup. **Interview line:** “CI tests every push; I manually promote a tested commit through OIDC and verify ECS deployed its exact image.”

The checked-in `cd.yml` also hard-codes its original AWS role ARN and ECR repository URI. A rebuild in a different account must update those workflow values in a separately authorized code change before CD can run; the file is deliberately untouched in this documentation-only task. The original role trust and permissions are **Not verified** merely because the workflow names that role.

### Step 14 — Testing and verification

**Purpose/prerequisite:** distribution deployed; test user/model access approved; billable inference only with consent. **Read-only inspection commands:**

```powershell
aws ecs describe-services --cluster novamind-chatbot-cluster --services novamind-chatbot-service --profile $p --region $r --query 'services[0].{Desired:desiredCount,Running:runningCount,Events:events[:5].message}'
aws elbv2 describe-target-health --target-group-arn $tgArn --profile $p --region $r
aws logs tail /ecs/novamind-chatbot --since 1h --profile $p --region $r
aws cloudfront get-distribution --id <distribution-id> --profile $p --query 'Distribution.{Status:Status,Domain:DomainName}'
Invoke-WebRequest 'https://<distribution-domain>/_stcore/health'
```

**Expected/connection:** task count equals desired; targets healthy; distribution deployed; HTTPS health responds. Then **manually** load the login page, verify Cognito/MFA, inspect browser WebSocket status, send approved text and supported image/document prompts to an allowed model, and verify streamed chunks. Test a Groq text prompt only if configured. Compare ECS task image SHA and public heading. **Errors:** a healthy endpoint can coexist with broken auth, WebSocket, provider IAM, or secret egress. **Interview line:** “I verified from infrastructure inward and then exercised the public user path, not merely a green task count.”

</details>

---

## 🧯 14 · Troubleshooting & production

**What you will learn:** Find which connection failed before changing anything.

> **Remember:** Check failing hop: container → ECS → ALB → CloudFront → app service.

<details>
<summary><strong>📖 Open detailed explanation, AWS CLI commands, diagrams & interview answers</strong></summary>

Start with the **failing hop**, not a broad permission change. The following checks are examples, not actions taken for this guide.

| Symptom | Project-specific likely cause | Check → repair |
|---|---|
| Docker fails to start | Linux dependency/import problem; wrong command; missing config; occupied host port | `docker logs novamind-local`, `docker inspect ... .State.Health`; rebuild from `requirements-linux.txt`, verify `8502:8501`. App login can fail while health stays green. |
| ECR push denied | Docker logged into wrong registry/region, expired token, IAM lacks upload, immutable tag exists | Recheck `sts get-caller-identity`, repository URI, `aws ecr describe-images`, rerun `get-login-password` through correct profile; never overwrite a SHA tag. |
| ECS cannot pull image | Wrong image URI/tag, execution role lacks ECR permission, task ENI lacks ECR/S3 route or DNS | `aws ecs describe-tasks` stopped reason/service events; inspect task ENI/public IP/routes, role, ECR image digest. Application task role does not fix image pull. |
| ECS task stops | Startup exception, CPU/memory pressure, invalid task config, secret/log setup failure | ECS `describe-tasks` `stoppedReason`, CloudWatch log stream, task definition image/env/secret ARNs; increase capacity only with evidence. |
| ALB target unhealthy | Container not listening on 0.0.0.0:8501; wrong target type/port/path; SG/NACL blocked | `describe-target-health`, task logs, `/_stcore/health`, SG source ALB→task; verify target type `ip` and task private IP. |
| CloudFront 403/502/504 | Distribution not deployed, VPC origin not deployed, origin SG/ALB blocked, unhealthy targets, wrong protocol/port | `get-distribution`, `get-vpc-origin`, `describe-target-health`; trace in that order. Distinguish CloudFront error from Cognito login rejection. |
| UI loads then disconnects | WebSocket upgrade headers/cookies/query strings, XSRF/Origin mismatch, ALB idle timeout or cross-replica state | Browser network tab for `101 Switching Protocols`, managed AllViewer policy, Streamlit logs, ALB timeout, sticky-session strategy; test via actual CloudFront URL. |
| Cognito sign-in fails | Pool/client IDs wrong, `USER_PASSWORD_AUTH` absent, user state/MFA issue, token context mismatch, no HTTPS egress | `describe-user-pool-client`, sanitized auth error category and network; do not dump password/token. Remember code calls Cognito unsigned user APIs. |
| Bedrock denied | Task role lacks streaming invocation on actual model/profile, model access unavailable, wrong region or network | Inspect task role, model ID, `us-east-1`, safe log category; a catalog listing alone does not prove invocation. Do not give wildcard permissions as first repair. |
| Secrets Manager/Groq fails | Secret ARN absent, execution role `GetSecretValue`/KMS denied, secret only injected on old task, Groq internet egress absent | ECS startup events for injection; task definition `secrets` reference; deploy a new task revision after secret change; check Groq HTTPS path separately. Never print key value. |
| CI fails | Windows Python/pinned package issue, offline regression, Docker build on Ubuntu | Inspect exact job/step in `gh run view <run-id> --log`; fix source/lock and rerun CI before CD. |
| CD fails | No successful push CI for exact SHA; non-main dispatch; OIDC trust/audience; ECR/ECS/PassRole denied; deleted infrastructure | Check CD step, `gh run view`, `sts` role identity, exact SHA, named ECS/ECR resources. The workflow's fixed CI ID is a maintenance risk. |
| Rollout does not stabilize | New task pull/start/health failure; no healthy baseline; circuit breaker not enabled | `describe-services` events/deployments and target health. Check actual `deploymentConfiguration`; the repository does not prove rollback was enabled. |

**Useful read-only commands:**

```powershell
aws ecs list-tasks --cluster novamind-chatbot-cluster --service-name novamind-chatbot-service --profile novamind --region us-east-1
aws ecs describe-services --cluster novamind-chatbot-cluster --services novamind-chatbot-service --profile novamind --region us-east-1
aws elbv2 describe-target-health --target-group-arn <target-group-arn> --profile novamind --region us-east-1
aws logs tail /ecs/novamind-chatbot --since 1h --profile novamind --region us-east-1
aws ec2 describe-route-tables --filters Name=vpc-id,Values=<vpc-id> --profile novamind --region us-east-1
aws ec2 describe-network-interfaces --filters Name=vpc-id,Values=<vpc-id> --profile novamind --region us-east-1
```

**Monitoring actually in source/evidence:** Docker/Streamlit health path; sanitized JSON application events with request ID, provider, duration, status and safe error category; ECS `awslogs` reference in the reconstructed task definition and CloudWatch screenshot; workflow ECS stability/revision/image checks. **Not verified historically:** CloudWatch alarms, Container Insights, CloudFront access logs, tracing, authenticated smoke tests, WAF, autoscaling rules, VPC flow logs and SLOs. Add alarms for ECS running count, ALB unhealthy targets/5xx/latency, CloudFront 5xx, application error categories and deployment failures; retain logs deliberately without prompt/credential contents.

**Scaling/availability:** two AZ subnets allow scheduling diversity, but `desiredCount=1` in the example still has one app task. Raise desired count or autoscale only after testing Streamlit WebSocket affinity and process-local session state. A reconnect to another replica can lose active chat/session state. Optional DynamoDB/S3 persistence saves selected conversations/attachments; it does not by itself externalize live Streamlit state. Test failure/reconnect behavior and request concurrency before claiming high availability. Fargate CPU/memory, ALB capacity, model throughput and CloudFront limits all need measurement.

**Security and cost:** already source-implemented controls include non-root container, `.dockerignore` secret exclusions, local/task-role credential separation, Cognito online token verification, upload/request validation, and sanitized logs. Reconstructed/recommended controls include least-privilege role policies, locked SG egress, private task subnets with NAT/endpoints, TLS to origin where required, WAF/rate limits, ECR scanning/retention, secret rotation, CloudWatch alarms, authenticated post-deploy checks, and IaC. Do not call those historical facts. Main cost drivers: Fargate runtime, ALB hours/LCUs, CloudFront requests/transfer, Bedrock inference, Groq usage, ECR storage, CloudWatch logs, Secrets Manager, Cognito users, optional S3/DynamoDB and possible NAT. `docker system df` is local disk, not AWS cost. The app's token-cost estimates are not an AWS bill.

**Rollback:** If the live ECS service has deployment circuit breaker `enable=true, rollback=true`, a failed rolling deployment can return to the last completed revision; historical setting is **Not verified**. Otherwise a reviewed manual rollback updates the service to a previously known-good task-definition ARN: `aws ecs update-service --cluster novamind-chatbot-cluster --service novamind-chatbot-service --task-definition <known-good-task-arn> --profile novamind --region us-east-1`. This is a **[BILLABLE/MUTATING] example only**. Rollback restores code, not in-memory sessions, already changed external data, or revoked credentials.

</details>

---

## 🧹 15 · AWS cleanup

**What you will learn:** Understand dependencies and cost after a demo.

> **Remember:** Delete dependencies safely; old billing charges can remain visible.

<details>
<summary><strong>📖 Open detailed explanation, AWS CLI commands, diagrams & interview answers</strong></summary>

The user reports that the infrastructure was already deleted. These commands document **dependencies only** and must not be run for this task. First identify resources by actual IDs/tags and verify they belong to the intended account; never delete a similarly named shared resource. CloudFront distribution must release the VPC origin before the VPC origin/ALB can be removed. ECS service must release target registrations and task ENIs before target group, SG, subnet and VPC deletion. A referenced secret may be shared; inspect before scheduling deletion. CloudFront and IAM are global APIs; VPC/ECS/ECR/Cognito/Logs are regional.

**Read-only preflight (not executed):**

```powershell
$p = 'novamind'; $r = 'us-east-1'
aws sts get-caller-identity --profile $p --region $r
aws cloudfront list-distributions --profile $p
aws cloudfront list-vpc-origins --profile $p
aws ecs list-clusters --profile $p --region $r
aws elbv2 describe-load-balancers --profile $p --region $r
aws ecr describe-repositories --profile $p --region $r
aws cognito-idp list-user-pools --max-results 60 --profile $p --region $r
aws logs describe-log-groups --log-group-name-prefix /ecs/novamind-chatbot --profile $p --region $r
aws ec2 describe-vpcs --filters Name=cidr,Values=10.20.0.0/16 --profile $p --region $r
```

**Illustrative deletion order [DESTRUCTIVE], not executed:**

1. **CloudFront distribution:** fetch complete distribution config and ETag with `aws cloudfront get-distribution-config --id <distribution-id> --profile $p`. Save a copy, change only `Enabled` to `false`, then `aws cloudfront update-distribution --id <distribution-id> --if-match <etag> --distribution-config file://disabled-distribution.json --profile $p`; wait until status `Deployed`, get a **fresh ETag**, then `aws cloudfront delete-distribution --id <distribution-id> --if-match <fresh-etag> --profile $p`. A `PreconditionFailed` means your ETag is stale; a distribution in use cannot be deleted. Do not hand-edit a partial config; CloudFront update needs the full config.
2. **CloudFront VPC origin:** after the distribution no longer references it, `aws cloudfront get-vpc-origin --id <vpc-origin-id> --profile $p` to obtain its ETag, then `aws cloudfront delete-vpc-origin --id <vpc-origin-id> --if-match <etag> --profile $p`. Wait for CloudFront-managed ENIs/SG to disappear before VPC cleanup. `CannotDeleteEntityWhileInUse` means a distribution still references it.
3. **ECS:** `aws ecs update-service --cluster novamind-chatbot-cluster --service novamind-chatbot-service --desired-count 0 --profile $p --region $r`; wait for running count 0 and drained targets. Then `aws ecs delete-service --cluster novamind-chatbot-cluster --service novamind-chatbot-service --profile $p --region $r`; `aws ecs delete-cluster --cluster novamind-chatbot-cluster --profile $p --region $r`. Deregister every task-definition revision only if no other service needs it: `aws ecs deregister-task-definition --task-definition <family:revision> --profile $p --region $r` (newer ECS revisions may also have delete operations with separate conditions). Expect task ENIs to disappear asynchronously.
4. **ALB:** inspect listener ARNs and target health; `aws elbv2 delete-listener --listener-arn <listener-arn> --profile $p --region $r`; `aws elbv2 delete-load-balancer --load-balancer-arn <alb-arn> --profile $p --region $r`; wait until gone; `aws elbv2 delete-target-group --target-group-arn <target-group-arn> --profile $p --region $r`. If dependency errors occur, check whether listener/service still references target group.
5. **ECR and log group:** after retaining any required release evidence/log exports, `aws ecr delete-repository --repository-name novamind-chatbot-ecr --force --profile $p --region $r` and `aws logs delete-log-group --log-group-name /ecs/novamind-chatbot --profile $p --region $r`. `--force` deletes all images. Log deletion loses troubleshooting evidence.
6. **Cognito and secret:** only if project-owned and no users/other apps depend on them, `aws cognito-idp delete-user-pool --user-pool-id <pool-id> --profile $p --region $r` and `aws secretsmanager delete-secret --secret-id <secret-id> --recovery-window-in-days 7 --profile $p --region $r`. Secret deletion is scheduled and may still incur cost during recovery. Do not retrieve or expose secret values.
7. **IAM:** detach managed policies (`aws iam detach-role-policy --role-name <role> --policy-arn <arn> --profile $p`), list/delete each inline policy (`aws iam list-role-policies`, `aws iam delete-role-policy`), then `aws iam delete-role --role-name <role> --profile $p`. Apply to execution, task, and GitHub deployment roles only if dedicated to NovaMind. Delete the GitHub OIDC provider only if no other repository/role uses it; it is often shared.
8. **VPC networking:** list ENIs and SG references first. Remove ALB/task SG rules referencing one another (`aws ec2 revoke-security-group-ingress ...`), then `aws ec2 delete-security-group --group-id <sg-id> --profile $p --region $r`. Disassociate **non-main** route table associations (`aws ec2 disassociate-route-table --association-id <rtbassoc-id> ...`), delete custom route tables, detach/delete IGW, delete four subnets, then delete VPC. Example end commands: `aws ec2 detach-internet-gateway --internet-gateway-id <igw-id> --vpc-id <vpc-id> --profile $p --region $r`; `aws ec2 delete-internet-gateway --internet-gateway-id <igw-id> --profile $p --region $r`; `aws ec2 delete-subnet --subnet-id <subnet-id> --profile $p --region $r`; `aws ec2 delete-vpc --vpc-id <vpc-id> --profile $p --region $r`. If deletion reports `DependencyViolation`, inspect ENIs, endpoints, NAT, ALB, SG references, associations and allocated public IPs rather than forcing unrelated resources away.

**Read-only post-check/cost history:** repeat preflight listings until project resources are absent, then use Cost Explorer (which can lag) for historical service charges. Billing data is independent of current resource existence. Example read-only query (dates must be chosen for the actual deployment period):

```powershell
aws ce get-cost-and-usage --time-period Start=2026-10-01,End=2026-11-01 --granularity MONTHLY --metrics UnblendedCost --group-by Type=DIMENSION,Key=SERVICE --profile novamind --region us-east-1
```

Expect per-service charges, not proof that a particular NovaMind resource caused every charge. Reconcile tags, invoices, CloudTrail/resource records if needed. CloudFront, ALB, Fargate, logs, secrets and ECR can have different billing timing.

</details>

---

## 🎤 16 · Interview practice

**What you will learn:** Practice speaking about what you actually built.

> **Remember:** Explain the flow first, then show your reason for every design choice.

<details>
<summary><strong>📖 Open detailed explanation, AWS CLI commands, diagrams & interview answers</strong></summary>

Use these as *understanding prompts*, not lines to memorize. Each answer states what the repository proves and names uncertainty when needed. Spoken answers are written in a natural first-person style; pause and draw the relevant hop when asked. A 30–60 second answer can be shortened for a rapid interview.

### 1. What happens between typing `localhost:8501` and seeing the app?

**Testing:** client/server and port basics. **Concept:** `localhost` resolves to the laptop loopback address; TCP 8501 identifies the Streamlit process. **NovaMind:** `mod_chatbot_frontend.py` calls the UI app, which renders the login gate. **Spoken answer:** “When I open localhost on port 8501, my browser connects to the Streamlit Python server running on my own laptop. Streamlit sends the initial page and keeps an interactive connection for widget updates. The UI and request handling are both implemented in Python modules. This is local only: nobody on the internet reaches my loopback address, which is why I later needed container hosting and a public edge.” **Follow-up:** What changes when binding `0.0.0.0`?

### 2. Why use Docker here?

**Testing:** packaging versus hosting. **Concept:** image bundles runtime and app; container runs it. **NovaMind:** Linux Python 3.14.6 image with pinned runtime dependencies and Streamlit. **Spoken answer:** “Docker gave me a Linux artifact containing the exact Python runtime, dependencies and NovaMind code that Fargate could start. It reduced differences between local packaging and the cloud runtime. Docker itself did not make the app public or manage users; those required ECR, Fargate, networking and CloudFront. I used Docker Desktop on Windows to build and inspect the image before publishing it.” **Follow-up:** What is still injected at runtime?

### 3. Explain image versus container and `8502:8501`.

**Testing:** Docker fundamentals. **Concept:** image is a stored template; container is a process instance; port publish maps host to container. **NovaMind:** Dockerfile exposes 8501. **Spoken answer:** “The image is the packaged NovaMind filesystem and startup instruction. A container is one running copy of that image. For local testing, `-p 8502:8501` made my Windows port 8502 forward to Streamlit's port 8501 inside the container. Nothing about the application's listening port changed. In ECS, an ALB target group routed to the task's port 8501 instead of my laptop port.” **Follow-up:** Does `EXPOSE` publish a port?

### 4. What does the Dockerfile protect, and what can it not protect?

**Testing:** image security. **Concept:** build context and runtime permissions. **NovaMind:** `.dockerignore` excludes local secrets; image runs non-root UID 10001. **Spoken answer:** “The Dockerfile builds only the runtime files, runs an import check, and starts Streamlit as a non-root user. `.dockerignore` keeps local credentials, virtual environments and uploads out of the image context. That reduces accidental leakage and privilege, but it does not replace AWS IAM, network rules or secret management. Runtime credentials and configuration must be supplied to ECS, not copied into image layers.” **Follow-up:** Can an environment variable still leak through logs?

### 5. How did your laptop authenticate to AWS?

**Testing:** CLI identity. **Concept:** profile selects credentials; SigV4 signs API calls; STS confirms caller. **NovaMind:** profile `novamind`, region `us-east-1`. **Spoken answer:** “I used AWS CLI with a named local profile and specified `us-east-1`. Before provisioning, I checked `aws sts get-caller-identity` to verify the principal and account. That profile is only for my laptop's administrative calls. The deployed application was designed to use ECS task-role credentials, while GitHub CD used OIDC; neither needed my laptop's credential file inside Docker.” **Follow-up:** Why prefer temporary credentials?

### 6. What is the difference between an IAM user, role and policy?

**Testing:** IAM model. **Concept:** user is an identity, role is assumable temporary identity, policy grants actions/resources. **NovaMind:** human CLI, ECS roles, GitHub role. **Spoken answer:** “An IAM user can have long-lived credentials; a role is assumed by a trusted principal and supplies temporary credentials. The trust policy says who can assume the role, while permission policies say which API actions it may perform on which resources. NovaMind needed distinct roles for task bootstrap, application Bedrock calls and GitHub deployment. Keeping them separate means an image pull grant does not automatically grant model inference.” **Follow-up:** What is `iam:PassRole`?

### 7. What makes a subnet public?

**Testing:** routing, not labels. **Concept:** subnet route-table default path to IGW; public IP also needed for a task to use that path. **NovaMind:** reconstructed public task subnets in `10.20.1.0/24` and `.2.0/24`. **Spoken answer:** “A subnet is public when its associated route table can send internet-bound IPv4 traffic to an Internet Gateway. For a Fargate task to use that route directly, it also needs a public IP and outbound security-group permission. The repository diagram has public/private labels but no exported route tables, so I would inspect the live associations before claiming historical task placement.” **Follow-up:** Why is a public IP alone insufficient?

### 8. How can an internal ALB be reached by CloudFront?

**Testing:** private origin design. **Concept:** CloudFront VPC origin creates managed private connectivity/ENI. **NovaMind:** screenshots depict VPC origin and internal ALB. **Spoken answer:** “The ALB's internal scheme means it is not a normal public internet origin. CloudFront VPC origin is the bridge: it uses managed networking inside the VPC to send origin requests to the ALB. The ALB security group must allow the CloudFront VPC-origin service security group on its listener port. The browser only sees CloudFront's HTTPS hostname, not a public ALB address.” **Follow-up:** What VPC prerequisites does a VPC origin have?

### 9. Why can a private ALB reach public-subnet ECS tasks?

**Testing:** VPC local routing and ENIs. **Concept:** every subnet in the VPC has local CIDR route; task retains private IP even with public IP. **NovaMind:** reconstructed placement; historical assignment is **Not verified**. **Spoken answer:** “In my reconstructed layout, both ALB and tasks are inside `10.20.0.0/16`. Each task has a private ENI address, and the VPC local route lets the ALB contact that private address on 8501. The public IP is only for the task's outbound internet path; the ALB does not route through the internet to reach it. The task SG accepts only the ALB SG.” **Follow-up:** How would private tasks obtain external egress?

### 10. What are an Internet Gateway, NAT and VPC endpoint?

**Testing:** egress choices. **Concept:** IGW routes public-IP traffic; NAT provides private-subnet outbound internet; endpoint reaches supported AWS services privately. **NovaMind:** actual historical egress is **Not verified**. **Spoken answer:** “The IGW is the internet route for resources with public addresses. A NAT gateway can let private tasks make outbound internet calls without giving them public IPs. VPC endpoints can carry selected AWS API traffic without NAT, but they do not automatically reach an external service such as Groq. The repository does not contain routes or endpoint exports, so I distinguish a tested reconstruction from historical fact.” **Follow-up:** Which path would Cognito/Groq need in your design?

### 11. How is a Docker image pushed to ECR?

**Testing:** artifact path and auth. **Concept:** build/tag/login/push, ECR URI and digest. **NovaMind:** SHA tags in `cd.yml`. **Spoken answer:** “I build the image, give it the full ECR repository URI plus the Git commit SHA, get a temporary ECR login token through AWS credentials, and push the image layers. ECR returns a content digest, which I can inspect. The actual CD workflow checks for a valid image with that SHA and reuses it, otherwise builds and pushes. That keeps the deployment tied to a particular source revision.” **Follow-up:** Why is a digest stronger than a tag?

### 12. How does Fargate pull an ECR image?

**Testing:** task bootstrap and execution role. **Concept:** execution role authorizes ECR pull; task ENI provides network route. **NovaMind:** task definition points at ECR image. **Spoken answer:** “When ECS starts a task, Fargate allocates the task's network interface, uses the task execution role for ECR authorization, downloads the image, configures logging and any ECS-injected secrets, then starts the container. The image pull happens before my Python code executes. Both permission and connectivity must work: an execution-role policy cannot repair a missing route to ECR or its image layers.” **Follow-up:** Which role does Python use after startup?

### 13. What is the difference between ECS cluster, task definition and service?

**Testing:** ECS model. **Concept:** cluster groups capacity/workloads; task definition is versioned blueprint; service maintains desired running tasks. **NovaMind:** all three names appear in CD workflow. **Spoken answer:** “The cluster is the logical ECS workspace. The task definition records the container image, port 8501, CPU/memory, roles, environment, secrets and logs. The service chooses that revision, keeps a desired number of tasks running, and associates them with the ALB target group. Deploying a new version means registering a new task-definition revision and telling the service to roll to it.” **Follow-up:** What happens if a task exits?

### 14. Why is the ALB target type `ip`?

**Testing:** Fargate networking. **Concept:** `awsvpc` task gets ENI private IP; no customer EC2 instance target. **NovaMind:** target group forwards to Streamlit 8501. **Spoken answer:** “Fargate tasks use `awsvpc` networking, so each task has its own private IP. The ALB registers that IP and container port as a target. `instance` target type would be appropriate for routing to EC2 instances, not this Fargate service. ECS manages registration as tasks start, become healthy, drain and stop, so the ALB always routes to current healthy task IPs.” **Follow-up:** Who unregisters an old task during deployment?

### 15. What does an ALB health check prove?

**Testing:** health scope. **Concept:** path/status check is shallow readiness signal. **NovaMind:** `/_stcore/health` on 8501. **Spoken answer:** “The ALB periodically requests Streamlit's health path and considers a target routable when it returns the configured success status. This tells me the web process is answering on the expected port. It cannot prove a user can complete Cognito MFA, a WebSocket stays connected, or Bedrock inference is permitted. I therefore pair target health with public, authenticated functional checks and task logs.” **Follow-up:** What do you inspect if targets are unhealthy?

### 16. What does CloudFront do that the ALB does not?

**Testing:** edge versus origin routing. **Concept:** CloudFront publishes a global HTTPS endpoint; ALB routes within VPC. **NovaMind:** CloudFront VPC origin reaches internal ALB. **Spoken answer:** “CloudFront gives public users an HTTPS distribution URL and can apply edge policies. Its VPC origin carries those requests to my internal ALB. The ALB then performs application-layer target routing and health checks to Fargate tasks. CloudFront does not start containers or authenticate Cognito users in this architecture, and the internal ALB is not directly reachable as a public endpoint.” **Follow-up:** Where does viewer TLS terminate?

### 17. Why do Streamlit, WebSockets and cache policy matter?

**Testing:** stateful web delivery. **Concept:** Streamlit uses WebSocket; interactive/user-specific traffic should not be cached. **NovaMind:** CloudFront must forward upgrade headers, cookies and query strings. **Spoken answer:** “Streamlit renders an initial page but relies on a long-lived WebSocket for interaction and streamed updates. I therefore need CloudFront's behavior to preserve required headers and session information, and I should disable caching for dynamic authenticated responses. A 200 response for the home page is insufficient: I test the WebSocket upgrade, login, chat and reconnection through the public URL. ALB idle timeouts and multi-task session routing also matter.” **Follow-up:** What would a browser show if WebSocket upgrade failed?

### 18. How does Cognito authenticate users here?

**Testing:** authentication flow versus IAM. **Concept:** user pool/app client and token verification. **NovaMind:** server calls `USER_PASSWORD_AUTH`, MFA, `GetUser`. **Spoken answer:** “The user submits credentials to my Streamlit form. The server calls Cognito `InitiateAuth` with the configured public app client, handles SMS or authenticator challenges if required, and receives an access token. The code checks token context and expiration, then calls Cognito `GetUser` using that exact token before trusting the identity. This is application-level sign-in, separate from the ECS task role.” **Follow-up:** Why does local JWT decoding alone not authenticate?

### 19. Does Cognito use the ECS task IAM role in this code?

**Testing:** precise service-call mechanism. **Concept:** Cognito public user APIs accept user credentials/tokens, not AWS SigV4 on this path. **NovaMind:** `create_cognito_client` uses `UNSIGNED` and explicit regional endpoint. **Spoken answer:** “No. My code intentionally creates an unsigned Cognito IDP client for the user authentication APIs. It sends the user's credentials for `InitiateAuth` and the user's access token for `GetUser`. The task still needs network access to the Cognito HTTPS endpoint. Its IAM role is used for AWS-authorized calls such as Bedrock and optional storage, not as a substitute for the person's login.” **Follow-up:** Which Cognito operations might require IAM in an admin workflow?

### 20. How does Bedrock inference work?

**Testing:** SDK, model authorization and streaming. **Concept:** boto3 signs Bedrock Runtime HTTPS request with task credentials. **NovaMind:** `converse_stream`, model choice and content validation. **Spoken answer:** “After Cognito has verified the user and the app has validated the prompt/attachment, a boto3 Bedrock Runtime client sends a `ConverseStream` request in `us-east-1`. The task role signs it; the policy must cover the selected model or inference profile. The app receives events, renders text chunks in Streamlit, and only commits a successful turn to model history. Bedrock hosts inference; Fargate hosts my app.” **Follow-up:** Why might model catalog listing succeed while invocation fails?

### 21. How do image and document uploads reach the model?

**Testing:** multimodal path and validation. **Concept:** upload bytes first reach the app; provider request carries supported content blocks. **NovaMind:** image/document validators, limits and model policies. **Spoken answer:** “The browser uploads bytes through CloudFront and ALB to Streamlit. My Python code checks file name, extension, size and actual content, then checks whether the selected model accepts that content type. For compatible Bedrock models it creates image or document content blocks in the Converse request. Nova Micro and Groq are treated as text-only by the local policy. Optional S3 saving is a separate persistence action, not required for immediate analysis.” **Follow-up:** Why validate inside the app if Streamlit has a size limit?

### 22. How is the Groq API key handled?

**Testing:** secret boundary. **Concept:** ECS secret reference uses execution role; app gets runtime env var. **NovaMind:** `GROQ_API_KEY` is read by `groq_service.py`; no direct Secrets Manager SDK call. **Spoken answer:** “The deployment design stores the external key in Secrets Manager and references its ARN in the ECS task definition. Before the container starts, ECS uses the execution role to retrieve it and injects it as `GROQ_API_KEY`. The Groq adapter then sends a bearer-authenticated HTTPS request. The key is never part of source code, an image layer or a task plaintext environment value; after rotation I need a new task rollout to receive the updated injection.” **Follow-up:** Which role needs `secretsmanager:GetSecretValue`?

### 23. When does the app use Bedrock versus Groq?

**Testing:** provider branching. **Concept:** providers are alternatives, not sequential hops. **NovaMind:** UI model/provider mapping and text-only Groq adapter. **Spoken answer:** “The user's selected model determines the provider. For a Bedrock model, the task uses boto3 and its task IAM role to call AWS. For the configured Groq model, it sends text through a separate HTTPS adapter with a bearer API key. The prompt does not travel Bedrock then Groq. The app validates capabilities first, so image/document requests are not treated as Groq multimodal calls.” **Follow-up:** What network path is needed for Groq?

### 24. What is the difference between execution role and task role?

**Testing:** least-privilege boundary. **Concept:** bootstrap/agent versus application code. **NovaMind:** ECR/logs/secrets versus Bedrock/storage. **Spoken answer:** “Fargate uses the execution role before and around container startup to pull ECR images, set up CloudWatch logging and inject Secrets Manager references. My Python application receives separate task-role credentials from the container provider, which it uses for Bedrock and optionally DynamoDB or S3. If the image cannot pull, I inspect execution-role permissions and network. If model invocation is denied after startup, I inspect the task role and model access.” **Follow-up:** Does the container code normally receive execution-role credentials?

### 25. Explain the CI pipeline.

**Testing:** test/build gates. **Concept:** automatic checks on source changes. **NovaMind:** `ci.yml` Windows tests then Ubuntu Docker build. **Spoken answer:** “A push to main or a PR targeting main runs CI. The first job installs the pinned Windows Python environment, checks dependency consistency and runs the guarded offline suite, so tests cannot quietly call AWS or the network. Only after that passes does an Ubuntu job build the Linux Docker image. This checks source behavior and container build, but it is not a live deployment or real Cognito/Bedrock integration test.” **Follow-up:** Why build on Ubuntu after Windows tests?

### 26. Explain the manual CD pipeline and OIDC.

**Testing:** deployment trust and provenance. **Concept:** manual promotion, same-SHA gate, OIDC temporary role. **NovaMind:** `cd.yml` changes only task image. **Spoken answer:** “I manually dispatch CD after CI. The workflow allows only main and queries for a successful push-triggered CI run for its exact commit SHA. GitHub's OIDC token is exchanged for temporary AWS role credentials. The job publishes or reuses the SHA-tagged ECR image, registers a task revision changing only that image, updates ECS, waits for stability and verifies the deployed image. That is a deliberate promotion boundary, not automatic deployment after every push.” **Follow-up:** Which claims must the AWS trust policy restrict?

### 27. What did the ‘Welcome back folk’ change prove?

**Testing:** evidence quality. **Concept:** end-to-end release demonstration, but limited test scope. **NovaMind:** commit `50a5d3f` and workflow/public verification reported by user. **Spoken answer:** “I changed one visible login heading, committed and pushed it. Automatic CI passed, then I manually ran CD and verified the changed text through the public CloudFront URL. That showed the source-to-image-to-ECS-to-edge release chain for that change. It did not by itself prove every security group, MFA case, model entitlement or rollback configuration, so I describe those separately and only claim what the evidence supports.” **Follow-up:** How would you verify the deployed SHA independently?

### 28. What if deployment starts but never stabilizes?

**Testing:** fault isolation and rollback. **Concept:** inspect task stopped reason, logs, ALB health, service events. **NovaMind:** CD waiter checks stability; circuit breaker historical setting unknown. **Spoken answer:** “I first inspect ECS service events and deployment state, then stopped-task reasons and CloudWatch logs. If a container starts but the target is unhealthy, I check `/_stcore/health`, port 8501 and SG path. If it never starts, I check ECR pull, secret injection, execution role and network. The workflow reports failure; automatic rollback occurs only if the ECS service was configured for it, which the repository does not prove.” **Follow-up:** What would you roll back manually?

### 29. How would you scale and secure the production version?

**Testing:** architecture trade-offs. **Concept:** replicas, session state, private egress, controls and observability. **NovaMind:** active Streamlit sessions are process-local; optional persistence is separate. **Spoken answer:** “I would first measure CPU, memory, concurrent WebSockets and model latency. Then I would increase task count across AZs, but only after testing session affinity or externalizing active state because a reconnect to another task can lose in-memory context. I would move tasks to private subnets with reviewed NAT/endpoints, scope IAM and egress, add WAF/rate limits, alarms, image scanning and authenticated smoke tests. These are improvements, not claims that all were already configured.” **Follow-up:** Would DynamoDB snapshots alone solve live session routing?

### 30. How did you control cost and clean up?

**Testing:** operational ownership. **Concept:** ongoing runtime charges and deletion dependencies. **NovaMind:** user reports infrastructure removal; current absence not independently checked. **Spoken answer:** “I treated Fargate, ALB, CloudFront traffic, inference, logs, ECR storage, Secrets Manager and optional NAT as cost drivers. After the demonstration, I removed project-owned resources in dependency order: disable/delete CloudFront, release VPC origin, scale down/delete ECS, remove ALB/target group, then registry/logs/secrets/IAM and VPC networking. I would verify with read-only listings and Cost Explorer, because billing history remains even after infrastructure is gone.” **Follow-up:** Why must CloudFront be removed before its VPC origin?

### One-minute deployment summary

“I built NovaMind AI as a Python Streamlit chatbot on my Windows laptop and tested it on localhost port 8501. I packaged it in a non-root Linux Docker image and published a commit-tagged release to Amazon ECR. On AWS, ECS Fargate ran the container; an internal ALB routed healthy task IPs on port 8501; and a CloudFront VPC origin exposed the app at a public HTTPS URL without making the ALB internet-facing. Cognito handled user sign-in, the task role authorized Bedrock streaming, and ECS injected an optional Groq key from Secrets Manager. CloudWatch collected safe application logs. GitHub Actions ran automatic offline CI and a manually triggered OIDC-based deployment. I demonstrated the pipeline by changing ‘Welcome back’ to ‘Welcome back folk’ and checking the public app, then removed the infrastructure to control cost.”

### Three-minute technical explanation

“I started with a Streamlit app, so localhost meant a Python server on my own laptop, not a separate public web site. The launcher calls the UI module; browser chat, uploads and login cause Python to run on the server. The Dockerfile built a Linux image with pinned dependencies, copied only runtime files, used a non-root user and listened on port 8501. I tested it with Docker Desktop, mapping my laptop's 8502 to the container's 8501. That image became the release artifact.

“For AWS, the source-verified CD workflow names an ECR repository, ECS task family, cluster and service. A repository URI plus Git SHA identifies the image. Fargate uses the task execution role and task networking to pull it. The application itself uses a separate task role for AWS SDK calls. In the network design, CloudFront gives the public HTTPS hostname, its VPC origin reaches an internal ALB, and the ALB forwards HTTP requests to healthy Fargate task private IPs on 8501. Streamlit also needs WebSocket upgrades and session information forwarded. The application is not sitting in ECR or CloudFront; it runs inside the ECS task.

“On login, Streamlit calls Cognito user APIs, handles MFA if requested, checks token context and verifies the exact access token with `GetUser`. On a chat turn, it validates text or upload content and model capability. Bedrock uses a task-role-signed `ConverseStream` call. Groq is a separate text-only HTTPS path with a runtime key injected from Secrets Manager by ECS. CloudWatch receives sanitized events. CI runs offline tests and a Linux Docker build on every main push/PR. Manual CD checks successful CI for the exact SHA, exchanges GitHub OIDC identity for temporary AWS credentials, publishes or reuses the image, registers a new ECS task revision, rolls the service and checks stability plus deployed image. The visible heading change demonstrated that path. The historical screenshots prove key resources existed, but the repo does not export exact subnet assignments, routes, IAM policies or circuit-breaker settings, so I label those as reconstruction rather than claiming to know them.”

### Five-minute architecture walkthrough

1. **Start with the user and trust boundary.** “A user opens a CloudFront HTTPS distribution. DNS resolves the edge hostname and TLS protects the viewer connection. CloudFront is a delivery layer, not my login decision.” Draw browser → CloudFront.
2. **Explain the private ingress.** “The distribution's VPC origin uses service-managed private networking to reach an internal ALB. The origin security group is allowed on ALB port 80. The ALB listener forwards to an IP-based target group on Streamlit port 8501.” Draw VPC origin → internal ALB → IP target group. Note that source/screenshots establish the internal ALB and VPC-origin design, while exact historical SG rules are not exported.
3. **Explain task execution.** “The ECS service keeps Fargate tasks running. Each task gets an ENI/private IP, and ECS registers it with the target group. The execution role pulls the SHA-tagged image from ECR, configures `awslogs`, and injects any referenced secret before Python starts. My Python SDK sees only the task role credentials.” Draw ECR, execution role, task role as separate arrows to the task.
4. **Explain network route choices.** “The worked reconstruction has `10.20.0.0/16`, public task subnets with public-IP/IGW egress, and private ALB subnets across two AZs. ALB-to-task uses the VPC local route and private task IP. A future production variant can put tasks in private subnets with NAT/endpoints. The repository's diagram depicts another tier arrangement; actual deleted service subnet settings are unknown.” This earns credibility: placement must be proved from ECS `awsvpcConfiguration` and route tables.
5. **Trace auth.** “Streamlit receives user credentials, calls Cognito `USER_PASSWORD_AUTH`, handles MFA and verifies the token online using `GetUser`. A valid IAM task role does not sign a person in. An authenticated browser session remains in Streamlit process memory.” Draw task → Cognito HTTPS.
6. **Trace model work.** “A prompt/upload is validated against type, size and selected model capability. Bedrock receives a SigV4-signed `ConverseStream` call from the task role. Groq is an alternative text-only HTTPS call using an injected secret. Chunks return to Python, then through ALB/CloudFront WebSocket to the browser. ECR and Secrets Manager are startup/deployment dependencies, not per-chat hops.” Draw the two provider branches and reverse response arrows.
7. **Trace delivery and operations.** “GitHub push triggers offline Python CI and Docker build. A manual CD checks the same SHA, uses OIDC to assume a deployment role, publishes the image, registers a task revision, updates ECS and verifies rollout. CloudWatch logs, ECS events, ALB target health and public authenticated testing narrow failures. The UI heading change was my release demonstration; cleanup followed to avoid idle charges.” Draw a second, separate CI/CD lane rather than mixing it into user traffic.

### Whiteboard order and mistakes to avoid

Draw two lanes: **runtime** (browser → CloudFront → VPC origin → internal ALB → Fargate task → Cognito or Bedrock/Groq; logs separately) and **delivery** (GitHub push → CI → manual OIDC CD → ECR image/task revision → ECS rollout). Label ports **443 → 80 → 8501**, private task IP, and which role acts at startup versus runtime. Mark subnet placement and circuit breaker as **Not verified historically**. Explain return traffic and WebSocket.

Avoid saying “CloudFront authenticates Cognito users,” “ECR runs containers,” “the task role pulls the image,” “the app fetches the Groq secret on every request,” or “Bedrock always calls Groq.” Do not claim that a green `/health` proves inference, that offline CI proves live AWS access, or that the diagram proves subnet routes. Do not claim automatic rollback unless the actual ECS service configuration confirms it. Name the demonstrated facts, identify the unknown historical settings, and describe the reconstructed commands as a way to reproduce and test the architecture.

### Source map and current AWS references

Primary project evidence: [`README.md`](README.md), [`Dockerfile`](Dockerfile), [`.dockerignore`](.dockerignore), [`services/aws_config.py`](services/aws_config.py), [`services/auth_service.py`](services/auth_service.py), [`services/bedrock_service.py`](services/bedrock_service.py), [`services/groq_service.py`](services/groq_service.py), [`services/observability.py`](services/observability.py), [CI](.github/workflows/ci.yml), [CD](.github/workflows/cd.yml), [architecture diagram](project-pic/NovaMind-AI-AWS-Architecture-Blueprint-with-cicd.png) and tracked AWS/GitHub screenshots. Older [`deployment.md`](deployment.md) describes pre-deployment requirements and is not a live AWS configuration export.

AWS primary references checked for the reconstructed commands: [CloudFront VPC origins](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/private-content-vpc-origins.html), [CloudFront VPC-origin CLI](https://docs.aws.amazon.com/cli/latest/reference/cloudfront/create-vpc-origin.html), [CloudFront WebSockets](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/distribution-working-with.websockets.html), [CloudFront managed request policies](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/using-managed-origin-request-policies.html), [CloudFront managed cache policies](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/using-managed-cache-policies.html), [Fargate task networking](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/fargate-task-networking.html), [ECS execution role](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task_execution_IAM_role.html), [ECS task role](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task-iam-roles.html), and [ECS deployment circuit breaker](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/deployment-circuit-breaker.html). These explain service behavior; they do not establish which deleted resources the historical account actually had.

</details>

---

## 🎯 Final interview cheat sheet

**Question:** “How did you deploy this application from your localhost to a public AWS URL?”

> “I developed the Python Streamlit chatbot locally, built a Docker image and tested the container. Using AWS CLI, I set up IAM and networking, published the image to Amazon ECR, and configured ECS Fargate to run it. An internal Application Load Balancer forwarded traffic to the ECS task's private IP on port 8501. CloudFront VPC Origin connected the public CloudFront HTTPS endpoint to that internal load balancer. The app used Cognito for user sign-in and Bedrock or Groq for inference. GitHub Actions ran automatic CI and manually triggered CD using temporary AWS credentials through OIDC. I proved the pipeline by deploying a visible login-page text change, then cleaned up the deployed infrastructure to avoid costs.”

**If the interviewer asks a follow-up:** Say which resource initiated the call, which endpoint or port it used, what security/permission enabled it, and how you verified it. You can find the commands and details by expanding the matching chapter above.

**Honesty rule:** Describe reconstructed configurations as examples, and distinguish them from items confirmed by the repository, user-shared AWS CLI history, or screenshots.
