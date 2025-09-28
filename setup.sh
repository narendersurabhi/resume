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
       --region "$REGION" \
       --profile "$PROFILE" >/dev/null 2>&1; then
    echo "Bootstrapping CDK in $ACCOUNT_ID/$REGION..."
    cdk bootstrap --app "python3.11 cdk/app.py" aws://$ACCOUNT_ID/$REGION --profile "$PROFILE"
else
    echo "CDK already bootstrapped in $ACCOUNT_ID/$REGION. Skipping."
fi

echo "=== Step 4: Deploy stacks ==="
cdk deploy --app "python3.11 cdk/app.py" --all --profile "$PROFILE"
