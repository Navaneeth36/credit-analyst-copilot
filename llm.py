import hashlib
import json
import os
import re

import openai

import config

# some models put reasoning in <think> tags, strip it
THINKING = re.compile(r"<think>.*?</think>", re.DOTALL)


def settings():
    return config.PROVIDERS[config.PROVIDER]


def get_client():
    s = settings()
    # ollama doesn't need a key but the client wants one
    key = os.environ.get(s["key_env"]) if s["key_env"] else "not-needed"
    if not key:
        raise RuntimeError(f"Set {s['key_env']} before running (see README).")
    # groq and ollama are both openai-compatible
    return openai.OpenAI(base_url=s["base_url"], api_key=key, max_retries=5)


# cache: temperature is 0 so same prompt = same answer

def cache_file(kind, prompt):
    fingerprint = hashlib.sha256((settings()["model"] + kind + prompt).encode()).hexdigest()
    return os.path.join(config.CACHE_DIR, fingerprint + ".json")


def read_cache(path):
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f)


def write_cache(path, value):
    os.makedirs(config.CACHE_DIR, exist_ok=True)
    with open(path, "w") as f:
        json.dump(value, f)


def send(prompt, client, want_json):
    request = {
        "model": settings()["model"],
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
    }
    if want_json:
        request["response_format"] = {"type": "json_object"}

    try:
        response = client.chat.completions.create(**request)
    except openai.BadRequestError:
        # some models don't support json mode
        if not want_json:
            raise
        del request["response_format"]
        response = client.chat.completions.create(**request)

    answer = response.choices[0].message.content or ""
    return THINKING.sub("", answer).strip()


def parse_json(text):
    text = THINKING.sub("", text or "")
    # in case there's text around the json
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return {}
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return {}


def call_json(prompt, client):
    path = cache_file("json", prompt)
    saved = read_cache(path)
    if saved is not None:
        return saved

    data = parse_json(send(prompt, client, want_json=True))
    if data:  # don't cache failures
        write_cache(path, data)
    return data


def call_text(prompt, client):
    path = cache_file("text", prompt)
    saved = read_cache(path)
    if saved is not None:
        return saved

    answer = send(prompt, client, want_json=False)
    if answer:
        write_cache(path, answer)
    return answer


def format_sources(found):
    return "\n\n".join(f"[page {chunk['page']}]\n{chunk['text']}" for chunk in found)
