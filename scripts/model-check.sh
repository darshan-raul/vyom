#!/usr/bin/env bash
# Live checks of the reasoning adapter against the configured OpenAI-compatible endpoint.
# Sends a few small requests to the provider, which costs a little.
# The API key comes from one of, in this order:
#   OPENROUTER_API_KEY   environment variable in the terminal that runs this script
#   VYOM_MODEL_KEY_FILE  file holding the key (default: .local/model-api-key, ignored by Git)
#   VYOM_MODEL_PROVIDER  short provider label (default: openrouter)
#   VYOM_MODEL_BASE_URL  endpoint (default: https://openrouter.ai/api/v1)
#   VYOM_MODEL           model ID (default: anthropic/claude-haiku-5.5)
# The backend reads the key through a credential reference; this script never prints it.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export VYOM_MODEL_KEY_FILE="${VYOM_MODEL_KEY_FILE:-$root/.local/model-api-key}"
export VYOM_MODEL_PROVIDER="${VYOM_MODEL_PROVIDER:-openrouter}"
export VYOM_MODEL_BASE_URL="${VYOM_MODEL_BASE_URL:-https://openrouter.ai/api/v1}"
export VYOM_MODEL="${VYOM_MODEL:-anthropic/claude-haiku-5.5}"

pass() { echo "PASS  $*"; }
fail() { echo "FAIL  $*" >&2; exit 1; }

for tool in uv git npm; do
  command -v "$tool" >/dev/null || fail "missing required tool: $tool"
done
if [[ -n "${OPENROUTER_API_KEY:-}" ]]; then
  export VYOM_MODEL_CREDENTIAL_REF=env:OPENROUTER_API_KEY
  key="$OPENROUTER_API_KEY"
  pass "key taken from the OPENROUTER_API_KEY environment variable"
else
  [[ -s "$VYOM_MODEL_KEY_FILE" ]] ||
    fail "no key: export OPENROUTER_API_KEY in this terminal, or create $VYOM_MODEL_KEY_FILE with mode 600 (see README)"
  [[ "$(stat -c %a "$VYOM_MODEL_KEY_FILE")" == 600 ]] ||
    fail "the key file must have mode 600: chmod 600 $VYOM_MODEL_KEY_FILE"
  git -C "$root" check-ignore --quiet "$VYOM_MODEL_KEY_FILE" ||
    fail "the key file is not ignored by Git; keep it under .local/"
  export VYOM_MODEL_CREDENTIAL_REF="file:$VYOM_MODEL_KEY_FILE"
  key="$(tr -d '[:space:]' <"$VYOM_MODEL_KEY_FILE")"
  pass "key file present, mode 600, ignored by Git"
fi

uv run --project "$root/backend" --locked python "$root/scripts/model_live_check.py"

# -- The key is in no file Git would take, and not in the browser bundle -------------------
cd "$root"
if git ls-files -z --cached --others --exclude-standard | xargs -0 grep --files-with-matches --fixed-strings -- "$key" >/dev/null 2>&1; then
  fail "the key appears in a tracked or untracked file that Git does not ignore"
fi
pass "the key is in no tracked or committable file"
(cd frontend && npm run build >/dev/null 2>&1) || fail "frontend build failed"
if grep --recursive --quiet --fixed-strings -- "$key" frontend/dist; then
  fail "the key is in the frontend bundle"
fi
if grep --recursive --quiet --ignore-case --extended-regexp 'openrouter|sk-or-|api[_-]?key' frontend/dist frontend/src; then
  fail "the frontend mentions a model provider or an API key"
fi
pass "fresh frontend bundle holds no key and no model provider reference"
echo "all model checks passed"
