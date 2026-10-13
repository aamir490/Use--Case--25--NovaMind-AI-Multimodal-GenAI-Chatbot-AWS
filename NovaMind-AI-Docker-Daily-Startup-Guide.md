# NovaMind AI — Daily Docker Startup & Shutdown Guide

**Question:** Whenever I return after sleeping or restarting my laptop, how do I start NovaMind AI on localhost?

**Project:** `E:\codex-projetc\Chatbot_text_image`  
**Local app:** http://localhost:8502  
**Docker image:** `novamind-ai:local`  
**Container name:** `novamind-ai-local`  
**Port mapping:** Windows `8502` → container `8501`  
**AWS account:** `357001292388` · **Region:** `us-east-1` · **CLI profile:** `novamind`  
**Cognito pool:** `us-east-1_VZoudZtLR` · **App client:** `44ghth3pj53orqtabj9d2lbp07`  
**Groq model:** `openai/gpt-oss-120b`

## A. Quick startup after sleeping or restarting Windows

1. **Open Docker Desktop.** Wait until Docker Engine is running.
2. **Open PowerShell** in `E:\codex-projetc\Chatbot_text_image`.
3. **Check your container:**

   ```powershell
   docker ps -a --filter "name=novamind-ai-local"
   ```

4. If the container exists but is stopped (`Exited`), **start it**:

   ```powershell
   docker start novamind-ai-local
   ```

   If it is already `Up`, you do not need to start it again.

5. **Check health:**

   ```powershell
   docker ps --filter "name=novamind-ai-local"
   ```

   Wait until `STATUS` says `(healthy)`.

6. **Open the app:** **http://localhost:8502**.

> **Important:** A stopped container retains the environment variables supplied when it was created. You do **not** need to re-enter `GROQ_API_KEY` every day if you use `docker start` and the container was created with the key. Docker stores container environment variables in its configuration, which locally privileged Docker users can inspect. Do not share or publish this container configuration.

## B. If the container is missing, or you need to update the Groq API key

Use this procedure **only if the container does not exist or needs new configuration**. A `docker restart` or `docker start` does **not** import newly set PowerShell environment variables.

1. Open PowerShell. Set the Groq key privately. Avoid printing it:

   ```powershell
   $env:GROQ_API_KEY = Read-Host "Enter your Groq API key"
   ```

2. Confirm the key exists without printing it:

   ```powershell
   if ([string]::IsNullOrWhiteSpace($env:GROQ_API_KEY)) {
       Write-Host "Groq key: MISSING"
   } else {
       Write-Host "Groq key: PRESENT"
   }
   ```

3. If an old container exists, **stop and remove it** (this does not delete your image or project files):

   ```powershell
   docker stop novamind-ai-local
   docker rm novamind-ai-local
   ```

   If the container does not exist, skip these two commands.

4. **Create the container** from the existing image:

   ```powershell
   docker run --detach `
     --name novamind-ai-local `
     --publish 8502:8501 `
     --mount "type=bind,source=$env:USERPROFILE\.aws,target=/home/appuser/.aws,readonly" `
     --env AWS_SHARED_CREDENTIALS_FILE=/home/appuser/.aws/credentials `
     --env AWS_CONFIG_FILE=/home/appuser/.aws/config `
     --env AWS_PROFILE=novamind `
     --env AWS_REGION=us-east-1 `
     --env COGNITO_USER_POOL_ID=us-east-1_VZoudZtLR `
     --env COGNITO_APP_CLIENT_ID=44ghth3pj53orqtabj9d2lbp07 `
     --env NOVAMIND_AI_PROVIDER=groq `
     --env GROQ_MODEL=openai/gpt-oss-120b `
     --env GROQ_API_KEY `
     novamind-ai:local
   ```

   **Local development only:** This mounts your `.aws` directory read-only so the app can use the local `novamind` profile. Read-only prevents modification but **does not stop the container reading credentials**. For ECS, use an IAM task role and AWS Secrets Manager instead. The Groq environment variable is not baked into the image, but Docker administrators can inspect container environment settings.

5. **Verify settings without disclosing secrets:**

   ```powershell
   docker exec novamind-ai-local python -c "import os; print('Groq key:', 'PRESENT' if os.getenv('GROQ_API_KEY', '').strip() else 'MISSING'); print('Model:', os.getenv('GROQ_MODEL', 'not set')); print('AWS profile:', os.getenv('AWS_PROFILE', 'not set'))"
   ```

6. **Check health and open the app:**

   ```powershell
   docker ps --filter "name=novamind-ai-local"
   ```

   http://localhost:8502

## C. Shut down when finished

Stop only the container (keep it for tomorrow):

```powershell
docker stop novamind-ai-local
```

Tomorrow run `docker start novamind-ai-local`, **not** `docker run` again. Stop Docker Desktop if you want after the container has stopped.

## D. Troubleshooting

| Problem | What to do |
|---|---|
| `Conflict. The container name ... is already in use` | Run `docker ps -a --filter "name=novamind-ai-local"`. Use `docker start` for a stopped container instead of `docker run`. |
| Docker command cannot connect to daemon | Start Docker Desktop and wait until Engine is ready; try `docker info`. |
| `localhost:8502` does not open | Run `docker ps -a --filter "name=novamind-ai-local"` and `docker logs --tail 40 novamind-ai-local`. Confirm the port mapping `8502->8501`. |
| `Groq is not configured` | Verify container environment (see B.5). If missing, recreate it using section B; a restart alone will not inject the key. |
| Bedrock fails | Check that local profile `novamind` is valid (`aws sts get-caller-identity --profile novamind --region us-east-1`), the read-only `.aws` mount is accessible to UID 10001, and permissions/model access are available. |
| Cognito configuration error | Verify the container was created with `COGNITO_USER_POOL_ID`, `COGNITO_APP_CLIENT_ID` and `AWS_REGION`. |
| Streamlit shows an import error | Build a fresh image after code changes: `docker build --tag novamind-ai:local .`, then recreate the container using section B. |
| Browser opens but chat fails | Review `docker logs --tail 40 novamind-ai-local` and provider settings; health status alone does not prove AI inference works. |

## E. Helpful commands

```powershell
# List all matching containers (running or stopped)
docker ps -a --filter "name=novamind-ai-local"

# Start existing stopped container
docker start novamind-ai-local

# Stop container after work
docker stop novamind-ai-local

# Inspect status and localhost port
docker ps --filter "name=novamind-ai-local"
docker port novamind-ai-local

# Read recent application logs
docker logs --tail 40 novamind-ai-local

# Rebuild image only when application/Dockerfile code changes
docker build --tag novamind-ai:local .
```

**Remember:** `docker start` = reuse existing configured container. `docker run` = create a new container. `docker restart` = restart with the **old** configuration. None of these creates AWS infrastructure; live Bedrock, Cognito and Groq API calls may still have usage costs.

**Built by Aamir — NovaMind AI**
