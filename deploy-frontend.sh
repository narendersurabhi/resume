#!/bin/bash
set -euo pipefail

# Config
BUCKET="resumefrontendstack-resumefrontendbucket1768d772-imh4yhqlilpt"
DISTRIBUTION_ID="E1WXMRQGK4R32W"
REGION="us-east-2"

echo "=== Step 1: Build frontend ==="
cd frontend
npm install
npm run build
cd ..

echo "=== Step 2: Sync files to S3 bucket $BUCKET ==="
aws s3 sync frontend/dist/ s3://$BUCKET/ --delete --region $REGION

echo "=== Step 3: Invalidate CloudFront cache ==="
aws cloudfront create-invalidation \
  --distribution-id $DISTRIBUTION_ID \
  --paths "/*"

echo "=== Deployment complete! Access site at: ==="
echo "https://d1ppugfs6b3s77.cloudfront.net/"
