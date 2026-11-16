#!/usr/bin/env bash
# Assemble self-contained Hugging Face Space bundles.
#   ./scripts/package_hf_space.sh            # both
#   ./scripts/package_hf_space.sh gradio     # free-tier Gradio SDK Space
#   ./scripts/package_hf_space.sh docker     # Docker Space (paid plan)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SDK="${1:-both}"

case "$SDK" in
  docker|gradio|both) ;;
  *) echo "usage: $0 [docker|gradio|both]" >&2; exit 1 ;;
esac

reset_dir() {
  local out="$1"
  case "$out" in
    "$ROOT"/dist/hf_space_*) rm -rf "$out" ;;
    *) echo "refusing to write outside dist/hf_space_*" >&2; exit 1 ;;
  esac
  mkdir -p "$out"
}

package_docker() {
  local out="$ROOT/dist/hf_space_docker"
  reset_dir "$out"
  mkdir -p "$out/backend" "$out/gradio_app"
  rsync -a --exclude '__pycache__' --exclude '*.pyc' \
    "$ROOT/backend/reposage/" "$out/backend/reposage/"
  cp "$ROOT/backend/requirements.txt" "$out/backend/requirements.txt"
  cp "$ROOT/gradio_app/app.py" "$out/gradio_app/app.py"
  cp "$ROOT/gradio_app/requirements.txt" "$out/gradio_app/requirements.txt"
  cp "$ROOT/deploy/huggingface/Dockerfile" "$out/Dockerfile"
  cp "$ROOT/deploy/huggingface/README.md" "$out/README.md"
  echo "Docker Space bundle: $out"
}

package_gradio() {
  local out="$ROOT/dist/hf_space_gradio"
  reset_dir "$out"
  rsync -a --exclude '__pycache__' --exclude '*.pyc' \
    "$ROOT/backend/reposage/" "$out/reposage/"
  cp "$ROOT/gradio_app/app.py" "$out/app.py"
  cat "$ROOT/backend/requirements.txt" "$ROOT/gradio_app/requirements.txt" > "$out/requirements.txt"
  cp "$ROOT/deploy/huggingface/README.gradio.md" "$out/README.md"
  echo "Gradio SDK Space bundle: $out"
}

case "$SDK" in
  docker) package_docker ;;
  gradio) package_gradio ;;
  both) package_docker; package_gradio ;;
esac

echo "Push with: hf upload <namespace>/<space> <bundle-dir> --repo-type space"
