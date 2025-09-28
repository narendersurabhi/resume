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
