#!/bin/bash
set -euo pipefail

ACCOUNT_ID="${ACCOUNT_ID:?ERROR: ACCOUNT_ID environment variable not set}"
REGION="${REGION:?ERROR: REGION environment variable not set}"
PROFILE="resume-admin"

echo "Using ACCOUNT_ID=$ACCOUNT_ID REGION=$REGION PROFILE=$PROFILE"

echo "=== Step 0: Sanity check AWS CLI and credentials ==="
if ! command -v aws >/dev/null 2>&1; then
  echo "ERROR: aws CLI not found. Make sure AWS CLI v2 is installed."
  exit 1
fi

if ! aws sts get-caller-identity --profile "$PROFILE" >/dev/null 2>&1; then
  echo "ERROR: Cannot validate AWS credentials for profile $PROFILE"
  exit 1
fi

echo "=== Step 1: Destroy all deployed stacks ==="
cdk destroy --app "python3.11 cdk/app.py" --all --profile "$PROFILE" --force

echo "=== Step 2: Delete CDK bootstrap stack (CDKToolkit) ==="
if aws cloudformation describe-stacks \
       --stack-name CDKToolkit \
       --region "$REGION" \
       --profile "$PROFILE" >/dev/null 2>&1; then
    echo "Deleting bootstrap stack CDKToolkit..."
    aws cloudformation delete-stack \
        --stack-name CDKToolkit \
        --region "$REGION" \
        --profile "$PROFILE"
    aws cloudformation wait stack-delete-complete \
        --stack-name CDKToolkit \
        --region "$REGION" \
        --profile "$PROFILE"
    echo "Bootstrap stack deleted."
else
    echo "No bootstrap stack found in $ACCOUNT_ID/$REGION. Skipping."
fi

echo "=== Cleanup complete ==="
