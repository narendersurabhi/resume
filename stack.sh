#!/bin/bash
set -euo pipefail

ACCOUNT_ID="${ACCOUNT_ID:?ERROR: ACCOUNT_ID environment variable not set}"
REGION="${REGION:?ERROR: REGION environment variable not set}"

ACTION="${1:-}"
FORCE="${2:-}"

echo "Using ACCOUNT_ID=$ACCOUNT_ID REGION=$REGION"

# --- Sanity checks ---
if ! command -v aws >/dev/null 2>&1; then
  echo "ERROR: aws CLI not found. Make sure AWS CLI v2 is installed."
  exit 1
fi

if ! aws sts get-caller-identity >/dev/null 2>&1; then
  echo "ERROR: Cannot validate AWS credentials from environment variables"
  exit 1
fi

case "$ACTION" in
  up)
    echo "=== Step 1: Install CDK Python dependencies ==="
    pip install -r cdk/requirements.txt

    echo "=== Step 2: Build frontend ==="
    cd frontend
    npm install
    npm run build
    cd ..

    echo "=== Step 3: Bootstrap CDK environment (if needed) ==="
    if aws cloudformation describe-stacks \
           --stack-name CDKToolkit \
           --region "$REGION" >/dev/null 2>&1; then
        echo "CDKToolkit stack already exists in $ACCOUNT_ID/$REGION. Skipping bootstrap."
    else
        echo "Bootstrapping CDK in $ACCOUNT_ID/$REGION..."
        cdk bootstrap aws://$ACCOUNT_ID/$REGION \
          --cloudformation-execution-policies arn:aws:iam::aws:policy/AdministratorAccess
    fi

    echo "=== Step 4: Deploy stacks ==="
    for stack in ResumeAuthStack ResumeBackendStack ResumeFrontendStack; do
      if [ "$FORCE" == "--force" ]; then
        echo "Forcing redeploy of $stack..."
        cdk deploy --app "python3.11 -m cdk.app" "$stack"
      else
        if aws cloudformation describe-stacks \
              --stack-name "$stack" \
              --region "$REGION" >/dev/null 2>&1; then
          echo "$stack already exists. Skipping."
        else
          echo "Deploying $stack..."
          cdk deploy --app "python3.11 -m cdk.app" "$stack"
        fi
      fi
    done
    ;;

  down)
    echo "=== Step 1: Destroy all deployed stacks ==="
    cdk destroy --app "python3.11 -m cdk.app" --all --force

    echo "=== Step 2: Skipping deletion of CDKToolkit (keeps bootstrap bucket) ==="
    ;;

  status)
    echo "=== CloudFormation stacks in $ACCOUNT_ID/$REGION ==="
    aws cloudformation list-stacks \
        --stack-status-filter CREATE_IN_PROGRESS CREATE_COMPLETE UPDATE_IN_PROGRESS UPDATE_COMPLETE ROLLBACK_COMPLETE \
        --region "$REGION" \
        --query "StackSummaries[].{Name:StackName,Status:StackStatus}" \
        --output table

    echo
    for stack in ResumeAuthStack ResumeBackendStack ResumeFrontendStack; do
      echo "=== Outputs for $stack ==="
      if aws cloudformation describe-stacks \
             --stack-name "$stack" \
             --region "$REGION" >/dev/null 2>&1; then
          aws cloudformation describe-stacks \
              --stack-name "$stack" \
              --region "$REGION" \
              --query "Stacks[0].Outputs" \
              --output table
      else
          echo "Stack $stack not found."
      fi
      echo
    done

    echo "=== All CloudFormation Exports (cross-stack values) ==="
    aws cloudformation list-exports \
        --region "$REGION" \
        --query "Exports[?starts_with(Name,'Resume')].[Name,Value]" \
        --output table

    echo
    echo "=== Frontend URLs (if deployed) ==="
    BUCKET=$(aws cloudformation describe-stacks \
      --stack-name ResumeFrontendStack \
      --region "$REGION" \
      --query "Stacks[0].Outputs[?OutputKey=='FrontendBucket'].OutputValue" \
      --output text 2>/dev/null || echo "")

    CLOUDFRONT=$(aws cloudformation describe-stacks \
      --stack-name ResumeFrontendStack \
      --region "$REGION" \
      --query "Stacks[0].Outputs[?OutputKey=='CloudFrontDomain'].OutputValue" \
      --output text 2>/dev/null || echo "")

    if [[ -n "$BUCKET" && "$BUCKET" != "None" ]]; then
      echo "config.json: https://$BUCKET.s3.$REGION.amazonaws.com/config.json"
    else
      echo "Frontend bucket not found."
    fi

    if [[ -n "$CLOUDFRONT" && "$CLOUDFRONT" != "None" ]]; then
      echo "CloudFront: https://$CLOUDFRONT/"
    else
      echo "CloudFront distribution not found."
    fi
    ;;

  *)
    echo "Usage: $0 {up|down|status} [--force]"
    exit 1
    ;;
esac
