import os
import json
import boto3
import logging

log = logging.getLogger()
log.setLevel(logging.INFO)

# Ensure region is set; Lambda sets AWS_REGION automatically
bedrock = boto3.client("bedrock-runtime", region_name=os.environ.get("AWS_REGION", "us-east-2"))
PROFILE_ARN = os.environ["BEDROCK_INFERENCE_PROFILE_ARN"]

frontend_domain = "https://dbeuad68389xx.cloudfront.net"  # put your CF URL here

def _cors_headers(origin="*"):
    return {
        "Access-Control-Allow-Origin": origin,   # use your exact CF origin in prod
        "Access-Control-Allow-Headers": "*",
        "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
    }

def _invoke_bedrock(prompt: str) -> str:
    # Anthropic on Bedrock schema
    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 800,
        "temperature": 0.3,
        "messages": [
            {"role": "user", "content": [{"type": "text", "text": prompt}]}
        ],
    }
    payload = json.dumps(body)

    # Prefer the newer signature with inferenceProfileArn. Fallback if SDK is older.
    try:
        resp = bedrock.invoke_model(
            inferenceProfileArn=PROFILE_ARN,
            body=payload,
            contentType="application/json",
            accept="application/json",
        )
    except TypeError:
        resp = bedrock.invoke_model(
            modelId=PROFILE_ARN,  # fallback path
            body=payload,
            contentType="application/json",
            accept="application/json",
        )

    result = json.loads(resp["body"].read())

    # Extract text from Anthropic output
    text_chunks = []
    content = result.get("output", {}).get("content", [])
    for block in content:
        if block.get("type") == "text":
            text_chunks.append(block.get("text", ""))
    text = "".join(text_chunks).strip()

    return text or json.dumps(result)


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
