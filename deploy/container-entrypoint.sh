#!/bin/sh
set -eu

mkdir -p "$CODEX_HOME"
python - <<'PY'
import json
import os
from pathlib import Path

home = Path(os.environ['CODEX_HOME'])
model = os.environ.get('CODEX_MODEL_NAME', 'gpt-6-sol')
base_url = os.environ.get('CODEX_MODEL_BASE_URL')
if base_url:
    lines = [
        'model_provider = "custom"',
        f'model = {json.dumps(model)}',
        '',
        '[model_providers.custom]',
        'name = "Coolify provider"',
        f'base_url = {json.dumps(base_url)}',
        'wire_api = "responses"',
        'requires_openai_auth = false',
    ]
    if os.environ.get('CODEX_PROVIDER_API_KEY'):
        lines.append('env_key = "CODEX_PROVIDER_API_KEY"')
    path = home / 'config.toml'
    path.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    path.chmod(0o600)
PY

exec "$@"
