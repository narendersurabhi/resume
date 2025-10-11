import os
import json
import boto3
import logging

log = logging.getLogger()
log.setLevel(logging.INFO)

BEDROCK_MODEL_ID = os.environ["BEDROCK_MODEL_ID"]
REGION = os.environ.get("CDK_DEFAULT_REGION", "us-east-1")
bedrock = boto3.client("bedrock-runtime", region_name=REGION)

log.info(f"BEDROCK_MODEL_ID: {BEDROCK_MODEL_ID}")
log.info(f"REGION: {REGION}")
print("Start")

CF_DIST_ID = os.getenv("CF_DIST_ID")
frontend_domain = f"https://{CF_DIST_ID}.cloudfront.net"  # put your CF URL here

def _cors_headers(origin="*"):
    return {
        "Access-Control-Allow-Origin": origin,   # use your exact CF origin in prod
        "Access-Control-Allow-Headers": "*",
        "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
    }

def _invoke_bedrock(prompt: str) -> str:

    print("Invoke started")
    log.info("prompt: " + prompt)
    body = {
        "messages": [
            {"role": "user", "content": [{"type": "text", "text": prompt}]}
        ],
        "max_tokens": 256,
        "temperature": 0.2
    }
    log.info("body: " + body)
    try:
        resp = bedrock.invoke_model(
            modelId=BEDROCK_MODEL_ID,
            body=json.dumps(body),
            contentType="application/json",
            accept="application/json",
        )
    except Exception as e:
        print(e)

    log.info("Response: " + resp)
    out = json.loads(resp["body"].read())
    log.info("Output: " + out["output"]["message"]["content"][0]["text"])
    print("Invoke ended.")
    return out["output"]["message"]["content"][0]["text"]

def handler(event, context):
    # Expect a JSON body with a 'prompt' field. Adjust if your API contract differs.
    print("beginning of handler")
    body = json.loads(event.get("body") or "{}")
    resume = body.get("resumeText", "")
    job = body.get("jobDesc", "")

    if not resume or not job:
        print("No resume or job")
        return {"statusCode": 400, "headers": _cors_headers(frontend_domain), "body": json.dumps({"message": "resumeText and jobDesc required"})}

    prompt = f"Tailor the following resume to this job.\n\nResume:\n{resume}\n\nJob:\n{job}\n\nReturn improved resume text."

    try:
        log.info("Invoking Bedrock via inference profile")
        print("Before invoke")
        improved = _invoke_bedrock(prompt)
        print("Afte invoke")
        log.info(improved)
        return {"statusCode": 200, "headers": _cors_headers(frontend_domain), "body": json.dumps({"result": improved})}
    except Exception as e:
        return {"statusCode": 500, "headers": _cors_headers(frontend_domain), "body": json.dumps({"error": str(e)})}
