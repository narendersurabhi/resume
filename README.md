# Resume Tailoring Platform

A reference implementation scaffold for a serverless resume tailoring application leveraging AWS-native services, AWS CDK, and a React + Tailwind CSS frontend.

## Architecture Overview

### Frontend
- React (Vite) single page application styled with Tailwind CSS.
- Hosted from Amazon S3 and distributed via Amazon CloudFront.
- Fetches runtime configuration (`config.json`) generated during CDK deployment.
- Uses AWS Amplify libraries for Cognito-authenticated API access.
- Provides upload forms, dashboard view, resume generation trigger, and download links.

### Backend
- Amazon API Gateway routing to Python 3.12 AWS Lambda functions.
- Lambda functions:
  - `upload_handler`: Stores files in S3 under tenant-aware prefixes and persists metadata in DynamoDB.
  - `generate_handler`: Retrieves assets, invokes Amazon Bedrock, produces DOCX/PDF outputs, and saves metadata.
  - `download_handler`: Issues secure pre-signed S3 URLs for generated outputs.
- Amazon DynamoDB maintains metadata for uploads and generated artifacts.
- Amazon Comprehend (optional) surfaces PII detection results in logs.
- Amazon S3 bucket stores all tenant-segregated assets (`/{tenant-id}/approved|template|jobs|generated/`).

### Authentication
- Amazon Cognito User Pool for end-user sign-in.
- Amazon Cognito Identity Pool for obtaining AWS credentials in the browser.

## Project Layout

```
root/
├── cdk/
│   ├── app.py                 # CDK app entrypoint
│   ├── backend_stack.py       # API Gateway, Lambdas, DynamoDB, S3
│   ├── frontend_stack.py      # S3 website hosting + CloudFront distribution
│   ├── auth_stack.py          # Cognito User & Identity pools
│   └── requirements.txt       # Python dependencies for CDK app
├── frontend/                  # React + Tailwind source
│   ├── package.json
│   ├── index.html
│   ├── vite.config.js
│   ├── tailwind.config.js
│   ├── postcss.config.js
│   ├── public/
│   │   └── config.json        # Local dev runtime config (overwritten in deploy)
│   └── src/
│       ├── App.jsx
│       ├── main.jsx
│       ├── styles.css
│       ├── components/
│       │   ├── UploadForm.jsx
│       │   ├── ResumeList.jsx
│       │   └── GenerateButton.jsx
│       └── pages/
│           └── Dashboard.jsx
├── lambdas/
│   ├── upload_handler/app.py
│   ├── generate_handler/app.py
│   └── download_handler/app.py
├── storage/                   # Local-only scratch space (S3 in production)
└── README.md
```

## Prerequisites

- Node.js >= 18.x (for frontend build tooling)
- Python >= 3.11 (for CDK execution)
- AWS CDK v2 CLI (`npm install -g aws-cdk`)
- AWS credentials configured with sufficient permissions to deploy the stacks

## Setup Instructions

1. **Install CDK dependencies**
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

3. **Bootstrap CDK environment (once per account/region)**
   ```bash
   cdk bootstrap --app "python -m cdk.app" aws://ACCOUNT_ID/REGION
   ```

4. **Deploy the stacks**
   ```bash
   cdk deploy --app "python -m cdk.app" --all
   ```

   The deployment outputs include the CloudFront distribution domain and Cognito identifiers.

## CI/CD Pipeline Deployment

- The `PipelineStack` defines the push-triggered CodePipeline/CodeBuild automation. Deploy it once to provision the
  infrastructure and then allow the pipeline to react to subsequent GitHub pushes:
  ```bash
  cdk deploy --app "python -m cdk.app" ResumePipelineStack
  ```
- After the pipeline stack succeeds you do **not** need to redeploy it on every commit—the pipeline is infrastructure that
  listens to repository events and launches CodeBuild automatically.
- When you change the pipeline itself (for example, editing `buildspec.yml` or `cdk/pipeline_stack.py`), commit the updates
  and let the existing pipeline run. If the infrastructure definition changed, re-run the command above once to apply the
  new configuration.

### IAM permissions required to deploy `ResumePipelineStack`

Ensure the AWS credentials configured in your local environment map to an IAM principal that can perform the following on
account `026654547457` in `us-east-1`:

- Launch CDK/CloudFormation stacks and create/update the resources defined in `cdk/pipeline_stack.py`, including IAM
  roles/policies, CodeBuild projects, CodePipeline pipelines, the artifact S3 bucket, and the CodeStar Connections link to
  GitHub (`cloudformation:*`, `iam:*`, `codebuild:*`, `codepipeline:*`, `s3:*`).
- Create and later authorize the GitHub connection resource that the pipeline uses
  (`codestar-connections:CreateConnection`/`codestar-connections:UseConnection`).
- Pass roles on behalf of managed services during deployment (for example, letting CodePipeline use the CodeBuild service
  role) via `iam:PassRole`.

The credentials can be supplied through any supported AWS SDK mechanism (for example, an `AWS_PROFILE` defined by the AWS
CLI, or `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` environment variables). The account must also be bootstrapped for CDK
v2 using the same credentials before running the deployment command.

### Environment variables and secrets to set before running CDK

When you execute CDK commands (for example, `cdk deploy --app "python -m cdk.app" ResumePipelineStack`), ensure the
following runtime configuration is present:

| Name | Required | Purpose |
|------|----------|---------|
| `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN` (if using temporary credentials) | ✅ | Authenticate the CDK CLI against your AWS account. |
| `AWS_PROFILE` (alternative to the keys above) | ⚪️ | Select a named profile from your local AWS config instead of exporting keys directly. |
| `AWS_REGION` / `AWS_DEFAULT_REGION` | ✅ | Match the region expected by the stacks (`us-east-1` by default via `cdk/cdk.json`). |
| `CDK_DEFAULT_ACCOUNT`, `CDK_DEFAULT_REGION` | ⚪️ | Automatically populated by the CDK CLI, but you can set them explicitly when assuming roles or scripting deployments. |
| `CF_DIST_ID` | ⚪️ | Optional CloudFront distribution ID propagated to the backend Lambda environment; leave empty on the first deploy and update later if you map an existing distribution. |

These variables align with the stack definitions. For example, `cdk/cdk.json` pins the default account and region, while
`cdk/backend_stack.py` reads `CF_DIST_ID` and region settings when defining Lambda environment variables. Exporting the
values (or configuring an AWS profile) before running `cdk deploy` prevents credential or region resolution errors.

## Local Development

- Update `frontend/public/config.json` with local API endpoints or mocked values for development.
- Run the React development server:
  ```bash
  cd frontend
  npm run dev
  ```
- Use tools such as [LocalStack](https://www.localstack.cloud/) or AWS SAM to emulate backend services if desired.

## Extending the Scaffold

- Replace the placeholder PDF generation routine with a production-ready DOCX-to-PDF conversion (for example, leveraging AWS Lambda container images with LibreOffice or AWS Step Functions).
- Harden IAM policies by scoping resources to tenant prefixes and required actions only.
- Integrate Amazon EventBridge or Step Functions for asynchronous generation workflows.
- Instrument logging, tracing (AWS X-Ray), and metrics (Amazon CloudWatch) as needed.
- Expand the frontend with Cognito-hosted UI flows or federated identity providers.

## Cleanup

To remove all deployed resources:
```bash
cdk destroy --app "python -m cdk.app" --all
```

> **Note:** S3 buckets are retained to preserve uploaded/generated documents. Empty or delete buckets manually before destroying stacks if full cleanup is required.
