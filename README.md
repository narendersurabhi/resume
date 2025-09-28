# Resume Tailoring Platform

A reference implementation scaffold for an AWS-native resume tailoring pipeline using the AWS Cloud Development Kit (CDK), Amazon Bedrock, and a React + Tailwind CSS frontend.

## Architecture Overview

### Workflow Orchestration
- Amazon API Gateway fronts Lambda functions that manage ingestion, orchestration, validation, rendering, and secure download flows.
- AWS Step Functions coordinates the end-to-end tailoring pipeline: **Ingest → Parse (Textract) → Retrieve → Generate Draft (Bedrock multi-prompt chain) → Validate → Render (python-docx & PDF placeholder) → Store metadata** in DynamoDB.
- Amazon DynamoDB persists job metadata, validation results, and download locations while Amazon S3 stores all tenant-segregated artifacts.

### AI & Document Processing
- Amazon Bedrock (Anthropic Claude by default) powers a structured, multi-prompt resume rewriting chain covering competency extraction, experience alignment, STAR-style bullet rewriting, skills harmonization, and a final formatting/consistency pass.
- Amazon Textract extracts textual content from uploaded resumes for downstream processing.
- Optional Amazon Comprehend analysis highlights potential PII in the job description to aid compliance.

### Frontend
- React (Vite) single-page application styled with Tailwind CSS.
- Hosted on Amazon S3 and delivered via Amazon CloudFront with deployment orchestrated by CDK.
- Provides upload widgets, job execution triggers, progress monitoring, validation insights, and pre-signed download links.

### Authentication
- Amazon Cognito User Pool and Identity Pool provide authenticated access patterns for future enhancements (scaffolded, not yet wired into the frontend code).

## Project Layout

```
root/
├── cdk/
│   ├── app.py                     # CDK entrypoint wiring authentication, backend, and frontend stacks
│   ├── backend_stack.py           # API Gateway, Lambda functions, Step Functions, DynamoDB, S3
│   ├── frontend_stack.py          # S3 website hosting + CloudFront distribution
│   ├── auth_stack.py              # Cognito User & Identity pool scaffolding
│   ├── requirements.txt           # CDK Python dependencies
│   └── stepfunctions_definition.json # Example ASL definition mirroring the orchestrated workflow
├── lambdas/
│   ├── download_handler/app.py    # Generates pre-signed URLs for completed jobs
│   ├── generate_handler/app.py    # Multi-step Bedrock prompting to craft resume drafts
│   ├── render_handler/app.py      # Applies style templates and produces DOCX/PDF artifacts
│   ├── status_handler/app.py      # Returns execution status and validation details
│   ├── upload_handler/app.py      # Ingests resumes, templates, and job descriptions into S3
│   ├── validate_handler/app.py    # Performs structural and keyword validation on drafts
│   └── workflow_handler/app.py    # Starts the Step Functions pipeline and tracks job metadata
├── frontend/
│   ├── package.json
│   ├── public/
│   │   └── config.json            # Runtime configuration written during deployment
│   └── src/
│       ├── App.jsx
│       ├── components/
│       │   ├── DownloadLinks.jsx
│       │   ├── GenerateButton.jsx
│       │   ├── ResumeList.jsx
│       │   └── UploadForm.jsx
│       └── pages/
│           └── Dashboard.jsx
├── storage/                       # Local-only scratch space (S3 in production)
└── README.md
```

## API Surface

| Method & Path           | Description                                    |
|-------------------------|------------------------------------------------|
| `POST /uploadResume`    | Upload an approved resume for a tenant.        |
| `POST /uploadTemplate`  | Upload a style template file.                  |
| `POST /uploadJD`        | Upload a job description artifact.             |
| `POST /tailor`          | Trigger a Step Functions execution for tailoring. |
| `GET /status/{jobId}`   | Fetch current job status & validation insights. |
| `GET /download/{jobId}` | Produce pre-signed DOCX/PDF download links.    |

All payloads expect a `tenantId` attribute to enforce logical isolation. S3 keys follow the convention: `/<tenant-id>/approved|template|jobs|generated/...`.

## Prerequisites

- Node.js ≥ 18.x (frontend tooling)
- Python ≥ 3.11 (CDK execution)
- AWS CDK v2 CLI (`npm install -g aws-cdk`)
- AWS credentials with permissions to deploy the referenced services (S3, CloudFront, Lambda, API Gateway, DynamoDB, Step Functions, Bedrock, Textract, Comprehend)

## Setup Instructions

1. **Install Python/CDK dependencies**
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -r cdk/requirements.txt
   ```

2. **Install frontend dependencies**
   ```bash
   cd frontend
   npm install
   npm run build  # produces dist/ for deployment
   cd ..
   ```

3. **Bootstrap the target AWS environment (per account/region)**
   ```bash
   cdk bootstrap --app "python -m cdk.app" aws://ACCOUNT_ID/REGION
   ```

4. **Deploy all stacks**
   ```bash
   cdk deploy --app "python -m cdk.app" --all
   ```

   Deployment outputs include the CloudFront distribution domain plus Cognito identifiers for future authentication wiring. The frontend deployment automatically writes a runtime `config.json` to S3 with API endpoints and regional details.

## Local Development Notes

- Update `frontend/public/config.json` with mock API values when running locally.
- Launch the Vite dev server for iterative UI work:
  ```bash
  cd frontend
  npm run dev
  ```
- The Lambda handlers are intentionally light-weight and avoid heavyweight dependencies so they can be tested with tools such as AWS SAM CLI or LocalStack.

## Extending the Scaffold

- Replace the placeholder PDF routine in `render_handler` with a containerized LibreOffice or similar approach for production-grade rendering.
- Integrate Cognito authentication on the frontend using Amplify or AWS SDK for JavaScript and lock down API Gateway with Cognito authorizers.
- Introduce Amazon EventBridge notifications for job completions and failures.
- Add observability (CloudWatch metrics, AWS X-Ray traces) and stricter IAM scoping per tenant prefix.
- Expand validation heuristics with ML-based hallucination detection or external compliance checks.

## Cleanup

Destroy all deployed resources when finished testing:

```bash
cdk destroy --app "python -m cdk.app" --all
```

> **Note:** S3 buckets and DynamoDB tables are retained by default for safety. Manually empty or delete them if full teardown is required.
