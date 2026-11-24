"""Optional JSON configuration (python -m recipe_manager run --config config.json). Secrets are never
in the file: it names the environment variable that holds each one.

{
  "db_path": "data/recipes.db",
  "nexus": {"url": "http://127.0.0.1:8790", "token_env": "RECIPE_NEXUS_TOKEN", "model": null,
            "target_node": null, "timeout": 180}
}
"""
import json
import os
from pathlib import Path

DEFAULTS = {
    'db_path': 'data/recipes.db',
    'nexus': {'url': 'http://127.0.0.1:8790', 'token_env': 'RECIPE_NEXUS_TOKEN', 'model': None,
              'target_node': None, 'timeout': 180},
}

SECTIONS = {'nexus': {'url', 'token_env', 'model', 'target_node', 'timeout'}}


def load(path):
    value = dict(DEFAULTS)
    value['nexus'] = dict(DEFAULTS['nexus'])
    if path:
        p = Path(path)
        if p.stat().st_size > 65536:
            raise ValueError('Configuration exceeds 64 KiB')
        loaded = json.loads(p.read_text(encoding='utf-8'))
        if not isinstance(loaded, dict) or set(loaded) - set(DEFAULTS):
            raise ValueError('Configuration sections are: ' + ', '.join(DEFAULTS))
        if 'db_path' in loaded:
            if not isinstance(loaded['db_path'], str):
                raise ValueError('db_path must be a string')
            value['db_path'] = loaded['db_path']
        if 'nexus' in loaded:
            section = loaded['nexus']
            if not isinstance(section, dict) or set(section) - SECTIONS['nexus']:
                raise ValueError('nexus: allowed keys are ' + ', '.join(sorted(SECTIONS['nexus'])))
            value['nexus'].update(section)
    return value


def secret(name):
    return os.environ.get(name) if name else None
