#!/bin/bash
set -euo pipefail

ACCOUNT_ID="${ACCOUNT_ID:?ERROR: ACCOUNT_ID environment variable not set}"
REGION="${REGION:?ERROR: REGION environment variable not set}"

ACTION="${1:-}"

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
    if ! aws cloudformation describe-stacks \
           --stack-name CDKToolkit \
           --region "$REGION" >/dev/null 2>&1; then
        echo "Bootstrapping CDK in $ACCOUNT_ID/$REGION..."
        cdk bootstrap --app "python3.11 cdk/app.py" aws://$ACCOUNT_ID/$REGION
    else
        echo "CDK already bootstrapped in $ACCOUNT_ID/$REGION. Skipping."
    fi

    echo "=== Step 4: Deploy stacks ==="
    cdk deploy --app "python3.11 cdk/app.py" --all
    ;;

  down)
    echo "=== Step 1: Destroy all deployed stacks ==="
    cdk destroy --app "python3.11 cdk/app.py" --all --force

    echo "=== Step 2: Delete CDK bootstrap stack (CDKToolkit) ==="
    if aws cloudformation describe-stacks \
           --stack-name CDKToolkit \
           --region "$REGION" >/dev/null 2>&1; then
        echo "Deleting bootstrap stack CDKToolkit..."
        aws cloudformation delete-stack \
            --stack-name CDKToolkit \
            --region "$REGION"
        aws cloudformation wait stack-delete-complete \
            --stack-name CDKToolkit \
            --region "$REGION"
        echo "Bootstrap stack deleted."
    else
        echo "No bootstrap stack found in $ACCOUNT_ID/$REGION. Skipping."
    fi
    echo "=== Cleanup complete ==="
    ;;

  status)
    echo "=== CloudFormation stacks in $ACCOUNT_ID/$REGION ==="
    aws cloudformation list-stacks \
        --stack-status-filter CREATE_IN_PROGRESS CREATE_COMPLETE UPDATE_IN_PROGRESS UPDATE_COMPLETE ROLLBACK_COMPLETE \
        --region "$REGION" \
        --query "StackSummaries[].{Name:StackName,Status:StackStatus}" \
        --output table

    echo "=== CDKToolkit stack status ==="
    if aws cloudformation describe-stacks \
           --stack-name CDKToolkit \
           --region "$REGION" >/dev/null 2>&1; then
        aws cloudformation describe-stacks \
            --stack-name CDKToolkit \
            --region "$REGION" \
            --query "Stacks[0].{Name:StackName,Status:StackStatus}" \
            --output table
    else
        echo "CDKToolkit stack not found in $ACCOUNT_ID/$REGION"
    fi
    ;;

  *)
    echo "Usage: $0 {up|down|status}"
    exit 1
    ;;
esac
