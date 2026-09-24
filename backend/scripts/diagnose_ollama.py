import urllib.request
import json
import sys

def test_ollama():
    print("Checking Ollama availability on http://localhost:11434...")
    try:
        with urllib.request.urlopen("http://localhost:11434/") as res:
            print(f"Ollama is running: {res.read().decode().strip()}")
    except Exception as e:
        print(f"ERROR: Cannot connect to Ollama. Is it running? Details: {e}")
        return

    print("\nListing installed models in Ollama...")
    try:
        with urllib.request.urlopen("http://localhost:11434/api/tags") as res:
            data = json.loads(res.read().decode())
            models = [m['name'] for m in data.get('models', [])]
            print(f"Installed models: {models}")
    except Exception as e:
        print(f"ERROR: Failed to list models: {e}")
        return

    # Check for qwen2.5-vl or qwen2.5vl
    target_models = ["qwen2.5-vl:latest", "qwen2.5-vl", "qwen2.5vl:latest", "qwen2.5vl"]
    found_model = None
    for m in models:
        if any(target in m for target in target_models):
            found_model = m
            break

    if not found_model:
        print(f"\nWARNING: No Qwen 2.5 VL model tag found in your Ollama tags. You have: {models}")
        print("Please pull the model first using: ollama pull qwen2.5-vl")
        return
    else:
        print(f"\nFound Qwen model: {found_model}")

    print(f"\nTesting chat completion with model '{found_model}'...")
    payload = {
        "model": found_model,
        "messages": [
            {"role": "user", "content": "say hi in 1 word"}
        ],
        "stream": False,
        "format": "json" # Test if JSON format mode works
    }
    
    try:
        req = urllib.request.Request(
            "http://localhost:11434/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            res_data = json.loads(response.read().decode("utf-8"))
            content = res_data.get("message", {}).get("content", "")
            print(f"Response success! Content: {content}")
    except Exception as e:
        print(f"ERROR: Chat completion failed with JSON formatting mode: {e}")
        print("Retrying without JSON format constraint...")
        
        payload.pop("format", None)
        try:
            req = urllib.request.Request(
                "http://localhost:11434/api/chat",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=10) as response:
                res_data = json.loads(response.read().decode("utf-8"))
                content = res_data.get("message", {}).get("content", "")
                print(f"Response success (without JSON format): {content}")
        except Exception as retry_e:
            print(f"ERROR: Chat completion failed: {retry_e}")

if __name__ == "__main__":
    test_ollama()
