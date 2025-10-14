# Automated CI/CD and Containerized Backend Overview

## Summary of Repository Changes
- Added a top-level `buildspec.yml` that drives CodeBuild to install CDK/front-end dependencies, produce the Vite build artifacts, build and push three Lambda container images, and deploy the CDK stacks with image tag parameters.  
- Introduced a comprehensive `PipelineStack` CDK construct that provisions the CodeConnections source, artifact storage, IAM roles/policies, a privileged CodeBuild project, and the CodePipeline v2 stages to automate deployments.  
- Converted backend Lambdas to `DockerImageFunction`s fed by ECR image parameters, replacing inline ZIP packaging and enabling shared container configuration while preserving API Gateway wiring and environment variables.  
- Added Dockerfiles (and supporting dependency manifests) for the `download_handler`, `generate_handler`, and `upload_handler` Lambda directories so each image builds from the Python 3.12 base with required libraries bundled.  
- Updated the CDK app bootstrap (`cdk/app.py`) to instantiate the new pipeline stack and enforce deployment order relative to auth, backend, and frontend stacks.  
- Expanded the project README with setup guidance, pipeline deployment instructions, IAM requirements, and environment variable expectations for running CDK commands locally.

