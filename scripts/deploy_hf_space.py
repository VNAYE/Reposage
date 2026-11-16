"""Create (or reuse) the RepoSage Space, upload the bundle, add secrets, wait, test.

Token lookup order:
  1. ``HF_TOKEN`` in the environment
  2. ``HF_TOKEN=...`` in ``.env``
  3. ``.hf_token`` file at the repo root
  4. the token cached by ``huggingface_hub``

The Gemini key is read from ``.env`` and written with ``add_space_secret``; it is
never printed and never passed through a shell argument.

    python scripts/deploy_hf_space.py
    python scripts/deploy_hf_space.py --repo <user>/reposage --no-test
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUNDLE = ROOT / "dist" / "hf_space_gradio"


def read_env() -> dict[str, str]:
    values: dict[str, str] = {}
    for name in (ROOT / ".env", ROOT / ".env.example"):
        if not name.exists():
            continue
        for line in name.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            values.setdefault(key.strip(), value.strip().strip('"').strip("'"))
    return values


def read_token(env: dict[str, str]) -> str:
    for candidate in (
        os.getenv("HF_TOKEN"),
        os.getenv("HUGGINGFACE_TOKEN"),
        env.get("HF_TOKEN"),
        env.get("HUGGINGFACE_TOKEN"),
    ):
        if candidate:
            return candidate.strip()
    token_file = ROOT / ".hf_token"
    if token_file.exists():
        token = token_file.read_text().strip()
        if token:
            return token
    try:
        from huggingface_hub import get_token

        cached = get_token()
        if cached:
            return cached
    except Exception:
        pass
    raise SystemExit(
        "No Hugging Face token found. Put `HF_TOKEN=hf_...` in .env, or paste the token "
        "into .hf_token, then rerun this script."
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default="", help="owner/space-name (default: <you>/reposage)")
    parser.add_argument("--hardware", default="", help="zero-a10g | cpu-basic | ...")
    parser.add_argument("--timeout", type=int, default=1200, help="build wait in seconds")
    parser.add_argument("--no-test", action="store_true", help="skip the live Gradio test")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not BUNDLE.is_dir():
        raise SystemExit("Run ./scripts/package_hf_space.sh gradio first.")

    env = read_env()
    token = read_token(env)

    from huggingface_hub import HfApi
    from huggingface_hub.utils import HfHubHTTPError

    api = HfApi(token=token)
    try:
        who = api.whoami()
    except Exception as exc:
        raise SystemExit(
            f"Hugging Face authentication failed: {exc}. Check the token in .env or .hf_token."
        ) from exc
    username = who.get("name")
    plan = who.get("plan", "unknown")
    print(f"authenticated as {username} (plan: {plan})")

    repo_id = args.repo or f"{username}/reposage"
    hardware = args.hardware
    if not hardware:
        hardware = "zero-a10g" if str(plan).lower() in {"free", "none"} else "cpu-basic"

    try:
        existing = api.repo_info(repo_id, repo_type="space")
        print(f"reusing existing Space: {existing.id}")
    except HfHubHTTPError as exc:
        if getattr(exc.response, "status_code", None) != 404:
            raise
        print(f"creating Space {repo_id} (sdk=gradio, hardware={hardware})")
        try:
            api.create_repo(
                repo_id=repo_id,
                repo_type="space",
                space_sdk="gradio",
                space_hardware=hardware,
                private=False,
                exist_ok=True,
            )
        except HfHubHTTPError as create_error:
            raise SystemExit(
                f"Space creation failed: {create_error}\n"
                "Free accounts can only create Gradio Spaces on ZeroGPU (--hardware zero-a10g). "
                "Docker Spaces require a paid plan."
            ) from create_error

    gemini_key = os.getenv("GEMINI_API_KEY") or env.get("GEMINI_API_KEY", "")
    if not gemini_key:
        raise SystemExit("GEMINI_API_KEY is missing from .env")
    api.add_space_secret(repo_id=repo_id, key="GEMINI_API_KEY", value=gemini_key)
    api.add_space_variable(
        repo_id=repo_id, key="MAX_CHUNKS", value=os.getenv("MAX_CHUNKS", "40")
    )
    api.add_space_variable(
        repo_id=repo_id,
        key="CHAT_MODEL",
        value=env.get("CHAT_MODEL", "gemini-3.5-flash-lite"),
    )
    api.add_space_variable(
        repo_id=repo_id,
        key="CHAT_FALLBACK_MODELS",
        value=env.get("CHAT_FALLBACK_MODELS", "gemini-3.1-flash-lite"),
    )
    print("secrets and variables configured")

    print("uploading bundle…")
    api.upload_folder(
        repo_id=repo_id,
        repo_type="space",
        folder_path=str(BUNDLE),
        commit_message="Deploy RepoSage",
        ignore_patterns=[".env", ".hf_token", "__pycache__/*", "*.pyc"],
    )

    space_url = f"https://{repo_id.replace('/', '-')}.hf.space"
    print(f"waiting for build: {space_url}")
    deadline = time.time() + args.timeout
    stage = "UNKNOWN"
    while time.time() < deadline:
        info = api.space_info(repo_id)
        runtime = info.runtime
        stage = runtime.stage if runtime else "PENDING"
        print(f"[{time.strftime('%H:%M:%S')}] {stage}", flush=True)
        if stage == "RUNNING":
            break
        if stage in {"BUILD_ERROR", "CONFIG_ERROR", "RUNTIME_ERROR", "STOPPED"}:
            raw = getattr(runtime, "raw", None)
            raise SystemExit(f"Space failed to start ({stage}): {raw}")
        time.sleep(10)

    if stage != "RUNNING":
        raise SystemExit(f"Space did not reach RUNNING within {args.timeout}s (last: {stage})")
    print(f"Space is live: {space_url}")

    if args.no_test:
        return

    try:
        import truststore

        truststore.inject_into_ssl()
    except ImportError:
        pass

    from gradio_client import Client

    print("running live test: index pallets/click and ask a question")
    client = Client(space_url, verbose=False)
    print(client.predict("pallets/click", "main", api_name="/index_repository"))
    history, _ = client.predict(
        "How are command line options parsed?",
        [],
        "pallets/click",
        "main",
        api_name="/chat",
    )
    answer = history[-1]["content"]
    print(answer[:1200] if isinstance(answer, str) else answer)
    print("live test passed")


if __name__ == "__main__":
    sys.exit(main())
