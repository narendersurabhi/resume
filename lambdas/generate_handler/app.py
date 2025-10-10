import os
import json
import boto3
import logging

log = logging.getLogger()
log.setLevel(logging.INFO)

# Ensure region is set; Lambda sets AWS_REGION automatically
# bedrock = boto3.client("bedrock-runtime", region_name=os.environ.get("AWS_REGION", "us-east-2"))
# PROFILE_ARN = os.environ["BEDROCK_INFERENCE_PROFILE_ARN"]

BEDROCK_MODEL_ID = os.environ["BEDROCK_MODEL_ID"] # os.environ["BEDROCK_MODEL_ID"]  # profile ARN
REGION = os.environ.get("AWS_REGION", "us-east-1")
bedrock = boto3.client("bedrock-runtime", region_name=REGION)

log.info(f"BEDROCK_MODEL_ID: {BEDROCK_MODEL_ID}")
log.info(f"REGION: {REGION}")

frontend_domain = "https://dbeuad68389xx.cloudfront.net"  # put your CF URL here

def _cors_headers(origin="*"):
    return {
        "Access-Control-Allow-Origin": origin,   # use your exact CF origin in prod
        "Access-Control-Allow-Headers": "*",
        "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
    }

def _invoke_bedrock(prompt: str) -> str:
    body = json.dumps({
        "inputText": prompt,
        "textGenerationConfig": {"maxTokenCount": 1024, "temperature": 0.2, "topP": 0.9}
    })
    resp = bedrock.invoke_model(
        modelId=BEDROCK_MODEL_ID,          # <- use profile ARN here
        body=body,
        contentType="application/json",
        accept="application/json",
    )
    payload = json.loads(resp["body"].read())
    # adjust parsing to your model output
    return payload.get("results", [{}])[0].get("outputText", "")

def handler(event, context):
    # Expect a JSON body with a 'prompt' field. Adjust if your API contract differs.
    try:
        body = event.get("body") or "{}"
        if isinstance(body, str):
            body = json.loads(body)
        prompt = body.get("prompt") or "Summarize: Hello"
    except Exception:
        prompt = "Summarize: Hello"

    log.info("Invoking Bedrock via inference profile")
    output = _invoke_bedrock(prompt)

    return {
        "statusCode": 200,
        "headers": _cors_headers("https://dbeuad68389xx.cloudfront.net"),
        "body": json.dumps({"text": output}),
    }
