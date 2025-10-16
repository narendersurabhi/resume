import os
import sys
import requests


API_BASE = "https://api.openai.com/v1"
TIMEOUT = 20


def get_headers() -> dict:
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        sys.exit("Missing OPENAI_API_KEY.")
    headers = {"Authorization": f"Bearer {key}"}
    proj = os.getenv("OPENAI_PROJECT") or "proj_rHvrAwby02gARWlZwjSSbHvV"
    print(proj)
    if proj:
        headers["OpenAI-Project"] = proj
    return headers


def list_gpt5_models(sess: requests.Session, headers: dict) -> list[str]:
    resp = sess.get(f"{API_BASE}/models", headers=headers, timeout=TIMEOUT)
    resp.raise_for_status()
    data = resp.json() or {}
    return [
        m["id"] for m in data.get("data", [])
        if isinstance(m, dict) and str(m.get("id", "")).startswith("gpt-5")
    ]


def say_ok(sess: requests.Session, headers: dict) -> str:
    payload = {
        "model": "gpt-5-mini",
        "input": [{"role": "user", "content": "Say OK"}],
    }
    resp = sess.post(
        f"{API_BASE}/responses",
        headers={**headers, "Content-Type": "application/json"},
        json=payload,
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    j = resp.json() or {}
    # Prefer 'output_text', fall back to raw object.
    return j.get("output_text") or str(j)


def main() -> None:
    headers = get_headers()
    with requests.Session() as sess:
        try:
            models = list_gpt5_models(sess, headers)
            print("gpt-5 models:", models)
        except requests.HTTPError as e:
            print("Model list error:", e.response.status_code, e.response.text, file=sys.stderr)

        try:
            out = say_ok(sess, headers)
            print("response:", out)
        except requests.HTTPError as e:
            print("Responses error:", e.response.status_code, e.response.text, file=sys.stderr)


if __name__ == "__main__":
    main()
