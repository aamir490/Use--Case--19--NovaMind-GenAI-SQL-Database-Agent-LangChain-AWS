# Simple AWS Deployment Guide

## 1. Project and AWS Requirements

Make sure these are installed:

- Python 3.11
- AWS CLI v2
- Docker Desktop
- Git with Git Bash

Project directory:

```text
E:\GenAi-Project-Cloudage\Ai_Agent\Ai_Agent
```

AWS configuration:

```text
Account: 637423369471
Region: us-east-1
IAM user: mlops-user
```

---

## 2. Create Python Virtual Environment

Run in **Kiro PowerShell**:

```powershell
# Create virtual environment
python -m venv .venv

# Activate virtual environment
.venv\Scripts\Activate.ps1

# Install project dependencies
.venv\Scripts\pip install -r requirements.txt
```

### Checkpoint

```powershell
python --version
```

The virtual environment should be active and the prompt should show:

```text
(.venv)
```

---

## 3. Verify AWS Login

Run in **Kiro PowerShell**:

```powershell
# Verify AWS identity
aws sts get-caller-identity
```

Confirm that the account is:

```text
637423369471
```

Confirm the project uses:

```text
us-east-1
```

---

## 4. Verify Docker

Run in **Kiro PowerShell**:

```powershell
# Check Docker
docker version

# Check Docker Buildx
docker buildx version

# Quick check
docker ps
```

Docker Desktop must be running.

---

## 5. Prepare the Cars Data

Run in **Kiro PowerShell**:

```powershell
# Set source path
$env:PYTHONPATH="src"

# Create the normalized cars CSV
python scripts/normalize_cars.py
```

This should create:

```text
data/s3_cars_data_normalized.csv
```

---

## 6. Prepare the S3 Data

The Glue crawlers need the S3 paths to exist before CloudFormation creates the crawlers.

Bucket:

```text
langchain-637423369471-us-east-1
```

Verify the bucket:

```powershell
# Check S3 bucket
aws s3 ls s3://langchain-637423369471-us-east-1/ --region us-east-1
```

Upload the library data:

```powershell
# Upload library data
aws s3 cp data/s3_library_data.json s3://langchain-637423369471-us-east-1/library-data/s3_library_data.json --region us-east-1
```

Upload the normalized cars data:

```powershell
# Upload normalized cars data
aws s3 cp data/s3_cars_data_normalized.csv s3://langchain-637423369471-us-east-1/cars-data/s3_cars_data_normalized.csv --region us-east-1
```

Verify both locations:

```powershell
# Verify library data
aws s3 ls s3://langchain-637423369471-us-east-1/library-data/ --region us-east-1

# Verify cars data
aws s3 ls s3://langchain-637423369471-us-east-1/cars-data/ --region us-east-1
```

### Checkpoint

Both data files should be visible.

---

## 7. Configure Local `.env`

This is only required for local Streamlit/CLI use.

Create `.env`:

```powershell
# Create local environment file
Copy-Item .env.template .env
```

Make sure `.env` contains:

```env
APP_USERNAME=admin
APP_PASSWORD=cloudage

GLUE_DB_NAME=project_library_db
PROJECT_FILES_BUCKET=langchain-637423369471-us-east-1
ATHENA_WORKGROUP=project-text-to-sql
ATHENA_USE_MANAGED_RESULTS=false
AWS_REGION=us-east-1
```

**Important:** `ATHENA_USE_MANAGED_RESULTS` must be:

```env
ATHENA_USE_MANAGED_RESULTS=false
```

The `.env` file is for local execution. ECS receives its environment variables from CloudFormation.

---

# 8. Deploy CloudFormation

## Important: Bash Script

`deploy-changeset.sh` is a Bash script.

From **Kiro PowerShell**, run:

```powershell
# Create a CloudFormation change set
bash ./deploy-changeset.sh
```

The script will validate the template and create a change set.

You will see a change-set name similar to:

```text
cgs-ai-analyst-agent-project-changeset-XXXXXXXXXX
```

**Copy the NEW change-set name printed by the script.**

Do not use an old change-set name.

---

# 9. Execute the Change Set

Run in **Kiro PowerShell**:

```powershell
# Execute the NEW CloudFormation change set
aws cloudformation execute-change-set `
  --stack-name cgs-ai-analyst-agent-project `
  --change-set-name <NEW_CHANGE_SET_NAME> `
  --region us-east-1
```

Replace:

```text
<NEW_CHANGE_SET_NAME>
```

with the change-set name printed in Step 8.

A successful command may return to the PowerShell prompt without displaying a message. This is normal.

---

# 10. Wait for CloudFormation

Run:

```powershell
# Wait for CloudFormation stack creation
aws cloudformation wait stack-create-complete `
  --stack-name cgs-ai-analyst-agent-project `
  --region us-east-1
```

### Important

This command can appear to be **stuck with no output**.

That is normal.

AWS CLI is waiting and polling CloudFormation. Do not assume it failed just because nothing is displayed.

---

# 11. Check CloudFormation Status

Open another Kiro PowerShell terminal if the `wait` command is still running.

Run:

```powershell
# Check CloudFormation status
aws cloudformation describe-stacks `
  --stack-name cgs-ai-analyst-agent-project `
  --region us-east-1 `
  --query "Stacks[0].StackStatus" `
  --output text
```

Expected:

```text
CREATE_COMPLETE
```

### Status meanings

```text
CREATE_IN_PROGRESS
```

Keep waiting.

```text
CREATE_COMPLETE
```

CloudFormation deployment is successful. Continue.

```text
CREATE_FAILED
ROLLBACK_IN_PROGRESS
ROLLBACK_COMPLETE
```

```powershell
# watch CloudFormation events almost in real time from PowerShell
while ($true) {
    Clear-Host
    Write-Host "=== CloudFormation Deployment Status ===" -ForegroundColor Cyan
    Write-Host "Time: $(Get-Date)"
    Write-Host ""

    aws cloudformation describe-stack-events `
      --stack-name cgs-ai-analyst-agent-project `
      --region us-east-1 `
      --query "StackEvents[0:15].[Timestamp,ResourceStatus,ResourceType,LogicalResourceId,ResourceStatusReason]" `
      --output table

    Start-Sleep -Seconds 5
}
```

Stop and inspect the CloudFormation events before continuing.


> Yesterday we were mainly waiting for CloudFormation. 
> Today we can see that CloudFormation is actually spending time creating the **ECS/ALB/VPC-endpoint** resources.

> In particular, **EcsService** is significant because an **ECS service can remain CREATE_IN_PROGRESS** while ECS is trying to get the task(s) running and healthy.

> So don't assume it's simply "stuck" yet.
> The next thing I'd check is **ECS service/task events**, because that can tell us whether the ECS task is failing to start, failing health checks, unable to pull the ECR image, having networking problems, etc.

```powershell
# Check CloudFormation events specifically for the ECS service
# This helps identify why the ECS service is still in CREATE_IN_PROGRESS or has failed
aws cloudformation describe-stack-events `
  --stack-name cgs-ai-analyst-agent-project `
  --region us-east-1 `
  --query "StackEvents[?LogicalResourceId=='EcsService'].[Timestamp,ResourceStatus,ResourceStatusReason]" `
  --output table `
  --no-cli-pager


# Check which CloudFormation resources are still being created
# This shows only resources currently in CREATE_IN_PROGRESS status
aws cloudformation describe-stack-resources `
  --stack-name cgs-ai-analyst-agent-project `
  --region us-east-1 `
  --query "StackResources[?ResourceStatus=='CREATE_IN_PROGRESS'].[LogicalResourceId,ResourceType,ResourceStatus]" `
  --output table `
  --no-cli-pager


# Get detailed information about the ECS service CloudFormation resource
# This shows the physical resource ID, resource type, current status, and status reason
aws cloudformation describe-stack-resources `
  --stack-name cgs-ai-analyst-agent-project `
  --region us-east-1 `
  --logical-resource-id EcsService `
  --output table `
  --no-cli-pager

# Check the current ECS service status and task counts
# Shows the service name, service status, running tasks, desired tasks, and pending tasks
aws ecs describe-services `
  --cluster data-architecture-ai `
  --services data-architecture-ai `
  --region us-east-1 `
  --query "services[0].[serviceName,status,runningCount,desiredCount,pendingCount]" `
  --output table `
  --no-cli-pager

# Check the latest ECS service events
# Helps identify task placement, container startup, image-pull, health-check, or other ECS service issues
aws ecs describe-services `
  --cluster data-architecture-ai `
  --services data-architecture-ai `
  --region us-east-1 `
  --query "services[0].events[0:15].[createdAt,message]" `
  --output table `
  --no-cli-pager    

# List all currently running ECS tasks for the data-architecture-ai service
# This confirms whether the ECS service has successfully started any running tasks
aws ecs list-tasks `
  --cluster data-architecture-ai `
  --service-name data-architecture-ai `
  --region us-east-1 `
  --desired-status RUNNING `
  --output table `
  --no-cli-pager


# Check the latest ECS service events
# Helps identify why tasks are starting, stopping, or failing to launch
aws ecs describe-services `
  --cluster data-architecture-ai `
  --services data-architecture-ai `
  --region us-east-1 `
  --query "services[0].events[0:20].[createdAt,message]" `
  --output table `
  --no-cli-pager


# List stopped ECS tasks for the data-architecture-ai service
# This helps identify tasks that started but stopped due to container, image, or configuration issues
aws ecs list-tasks `
  --cluster data-architecture-ai `
  --service-name data-architecture-ai `
  --desired-status STOPPED `
  --region us-east-1 `
  --query "taskArns" `
  --output table `
  --no-cli-pager


# Check whether the ECR repository exists and retrieve its repository URI
# This confirms the repository used by the ECS service is available in us-east-1
aws ecr describe-repositories `
  --repository-names data-architecture-ai `
  --region us-east-1 `
  --query "repositories[0].[repositoryName,repositoryUri]" `
  --output table `
  --no-cli-pager

# List all Docker images and tags currently available in the ECR repository
# This verifies whether the image tag required by the ECS service, such as latest, exists
aws ecr list-images `
  --repository-name data-architecture-ai `
  --region us-east-1 `
  --output table `
  --no-cli-pager  
```


### Checkpoint

**Do not continue to ECR/ECS until the stack is `CREATE_COMPLETE`.**

---

# 12. If CloudFormation Fails

Run:

```powershell
# Show CloudFormation CREATE failures and resources still in progress
aws cloudformation describe-stack-events `
  --stack-name cgs-ai-analyst-agent-project `
  --region us-east-1 `
  --query "StackEvents[?ResourceStatus=='CREATE_IN_PROGRESS' || ResourceStatus=='CREATE_FAILED'].[LogicalResourceId,ResourceType,ResourceStatus,ResourceStatusReason]" `
  --output table
```

Read the `ResourceStatusReason`.

Do not repeatedly retry deployment without understanding the failure.

---

# 13. Build and Push the Docker Image

Only continue after:

```text
CREATE_COMPLETE
```

![AWS CloudFormation Stack](project-pic/aws-cloudformation-stack.png)

`push_ecr.sh` is also a Bash script.

From **Kiro PowerShell**:

```powershell
# Build and push the application image to ECR
bash ./scripts/push_ecr.sh
```

The script handles the ECR login, Docker build, image push, and ECS update according to the project configuration.

---

# 14. Verify ECS

Check the ECS service:

```powershell
# Check ECS service status
aws ecs describe-services `
  --cluster data-architecture-ai `
  --services data-architecture-ai `
  --region us-east-1 `
  --query "services[0].{Running:runningCount,Desired:desiredCount,Status:status}" `
  --output table

# +---------+-----------+----------+
# | Desired |  Running  | Status   |
# +---------+-----------+----------+
# |  1      |  1        |  ACTIVE  |
# +---------+-----------+----------+
```

Look for a running task.

---

# 15. Verify Glue Databases and Tables

Check the library database:

```powershell
# Check library tables
aws glue get-tables `
  --database-name project_library_db `
  --region us-east-1 `
  --query "TableList[*].Name"
```

Check the cars database:

```powershell
# Check cars tables
aws glue get-tables `
  --database-name project_cars_db `
  --region us-east-1 `
  --query "TableList[*].Name"
```

Expected application tables include:

```text
library_data
cars_data
```

If the tables are empty, check the crawler status and run the crawlers manually.

---

# 16. Run Glue Crawlers Manually if Needed

Use:

```powershell
# Start library crawler
aws glue start-crawler `
  --name project-library-crawler `
  --region us-east-1

# Start cars crawler
aws glue start-crawler `
  --name project-cars-crawler `
  --region us-east-1
```

Wait for the crawlers to finish, then check the Glue tables again.

---

# 17. Get the Application URL

Get the ALB URL from CloudFormation:

```powershell
# Get the Application Load Balancer URL
$ALB_URL = aws cloudformation describe-stacks `
  --stack-name cgs-ai-analyst-agent-project `
  --region us-east-1 `
  --query "Stacks[0].Outputs[?OutputKey=='LoadBalancerUrl'].OutputValue" `
  --output text

$ALB_URL

# output :- http://data-arch-ai-alb-59542162.us-east-1.elb.amazonaws.com
```

Save this URL.

---

# 18. Test Application Health

Run:

```powershell
# Test FastAPI health endpoint
Invoke-RestMethod -Uri "$ALB_URL/health"
```

Expected:

```text
status
------
ok
```

The ALB root URL `/` may return:

```text
{"detail":"Not Found"}
```

That is expected because the API does not define a root `/` route.

Use:

```text
/health
```

for the health check.

---

# 19. Test a Library Query

Run:

```powershell
# Test a library question
Invoke-RestMethod `
  -Uri "$ALB_URL/query" `
  -Method POST `
  -ContentType "application/json" `
  -Body '{"question":"How many books are in the library?"}'
```

---

# 20. Test a Cars Query

Run:

```powershell
# Test a cars question
Invoke-RestMethod `
  -Uri "$ALB_URL/query" `
  -Method POST `
  -ContentType "application/json" `
  -Body '{"question":"What is the average price of a car?"}'
```

Only ask questions that can be answered from the configured database data.

---

# 21. Run Streamlit Locally

Use **Kiro PowerShell**.

Do not depend on `make ui` on Windows.

Run:

```powershell
# Set Python source path
$env:PYTHONPATH="src"

# Start Streamlit
.venv\Scripts\python.exe -m streamlit run scripts/streamlit_app_new.py

Get-Content .env | Select-String "APP_USERNAME|APP_PASSWORD"

```

Then open:

```text
http://localhost:8501
```

Use the configured application login credentials.

![NovaMind Login Page 1](project-pic/Novamind-Ai-loginPage-1.png)
![NovaMind Login Page 2](project-pic/Novamind-Ai-loginPage-2.png)

![NovaMind AI Dashboard](project-pic/NovaMind-Ai-Dashboard1.png)
![NovaMind AI Dashboard 2](project-pic/NovaMind-Ai-Dashboard2.png)

For this deployment, select/use the Athena data source.

---

# 22. Optional: Aurora/RDS

Aurora/RDS is **optional**.

Do not deploy it as part of the basic Athena deployment unless you specifically need it.

If required, deploy the main CloudFormation stack first and confirm:

```text
CREATE_COMPLETE
```

Then use the project's RDS deployment script:

```powershell
# Bash script — run from Kiro PowerShell
bash ./scripts/deploy-rds.sh --auto
```

---

# 23. Optional: Other Connectors

The following connectors are not required for the basic Athena deployment:

- RDS PostgreSQL
- Redshift
- Snowflake
- Databricks

For this deployment, use:

```text
Athena (AWS)
```

The other connector configuration files contain placeholder values.

---

# 24. Deployment Complete Checklist

When everything is working:

```text
[ ] AWS account verified
[ ] Region = us-east-1
[ ] Bedrock Nova Micro access enabled
[ ] Python virtual environment created
[ ] requirements.txt installed
[ ] Cars data normalized
[ ] S3 library data uploaded
[ ] S3 cars data uploaded
[ ] CloudFormation change set created
[ ] Change set executed
[ ] CloudFormation = CREATE_COMPLETE
[ ] Docker image pushed to ECR
[ ] ECS task running
[ ] Glue databases/tables available
[ ] ALB URL obtained
[ ] /health returns OK
[ ] Library query works
[ ] Cars query works
[ ] Streamlit UI works
```

# 25. Important Rules

1. **Never execute an old change set.** Create a new one if the stack was deleted or rolled back.
2. **S3 data must exist before CloudFormation creates the Glue crawlers.**
3. **Do not proceed to ECR/ECS until CloudFormation is `CREATE_COMPLETE`.**
4. `.sh` files are Bash scripts. From Kiro PowerShell, use `bash ./script.sh`.
5. `aws cloudformation wait` can show no output while waiting. This is normal.
6. If CloudFormation fails, inspect stack events before retrying.
7. `ATHENA_USE_MANAGED_RESULTS=false` is required for the configured Athena workgroup.
8. `.env` is for local execution; ECS gets its environment from CloudFormation.
