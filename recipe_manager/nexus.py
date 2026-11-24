"""LLM calls via Nexus-Compute's job API (inference.generate), for the improve/merge flows.
Blocking; call from a thread (FastAPI runs sync route functions in a thread pool already)."""
import json
import re
import time

import httpx

TERMINAL = {'succeeded', 'failed', 'cancelled', 'canceled', 'expired'}

RECIPE_JSON_INSTRUCTIONS = (
    'Respond with ONLY a single JSON object, no commentary, no markdown fences, with exactly these keys: '
    '"title" (string), "ingredients" (array of strings, one per ingredient line, with quantity and unit '
    'included in the string), "steps" (array of strings, one per step), "servings" (string or null), '
    '"notes" (string or null, a short note on what changed and why).'
)


class NexusError(RuntimeError):
    pass


class NexusClient:
    def __init__(self, url, token, model=None, target_node=None, timeout=180):
        self.client = httpx.Client(base_url=url.rstrip('/'), headers={'Authorization': 'Bearer ' + token}, timeout=30)
        self.model, self.target_node, self.timeout = model, target_node, timeout

    def _run(self, messages, max_tokens=2048, temperature=0.4):
        # think: false -- a reasoning model may otherwise spend the whole token budget thinking
        # and return no text at all (see Nexus-Compute docs/INFERENCE.md).
        input_ = {'messages': messages, 'options': {'max_tokens': max_tokens, 'temperature': temperature, 'think': False}}
        if self.model:
            input_['model'] = self.model
        body = {'tool': 'inference.generate', 'input': input_}
        if self.target_node:
            body['target_node'] = self.target_node
        response = self.client.post('/v1/jobs', json=body)
        if response.status_code == 422:
            raise NexusError(f'Nexus refused the inference job: {response.text[:300]}')
        response.raise_for_status()
        job = response.json()
        deadline = time.monotonic() + self.timeout
        while job.get('state') not in TERMINAL:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                self.client.post(f'/v1/jobs/{job["id"]}/cancel')
                raise NexusError(f'inference.generate took longer than {self.timeout} seconds')
            reply = self.client.get(f'/v1/jobs/{job["id"]}/wait', params={'timeout': min(25, remaining)},
                                     timeout=min(25, remaining) + 5)
            reply.raise_for_status()
            job = reply.json()
        if job['state'] != 'succeeded':
            raise NexusError(f'inference.generate {job["state"]}: {job.get("error") or "no reason given"}')
        result = job.get('result') or {}
        return (result.get('text') or '').strip()

    @staticmethod
    def _parse_recipe_json(text):
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if not match:
            raise NexusError(f'The model did not return JSON: {text[:300]}')
        try:
            data = json.loads(match.group(0))
        except ValueError as exc:
            raise NexusError(f'The model returned invalid JSON: {exc}') from None
        for key in ('title', 'ingredients', 'steps'):
            if key not in data:
                raise NexusError(f'The model\'s JSON is missing "{key}"')
        return {
            'title': str(data['title']),
            'ingredients': [str(i) for i in data['ingredients']],
            'steps': [str(s) for s in data['steps']],
            'servings': str(data['servings']) if data.get('servings') else None,
            'notes': str(data['notes']) if data.get('notes') else None,
        }

    def improve(self, recipe, instructions):
        prompt = (
            f'Here is a recipe:\n\nTitle: {recipe["title"]}\n'
            f'Servings: {recipe.get("servings") or "unspecified"}\n'
            f'Ingredients:\n' + '\n'.join(f'- {i}' for i in recipe['ingredients']) + '\n'
            f'Steps:\n' + '\n'.join(f'{n}. {s}' for n, s in enumerate(recipe['steps'], 1)) + '\n\n'
            f'The user wants this change: {instructions}\n\n'
            f'Produce a revised version of the full recipe reflecting that request. {RECIPE_JSON_INSTRUCTIONS}'
        )
        text = self._run([{'role': 'user', 'content': prompt}])
        return self._parse_recipe_json(text)

    def merge(self, recipes, instructions=None):
        parts = []
        for n, recipe in enumerate(recipes, 1):
            parts.append(
                f'Recipe {n}: {recipe["title"]}\n'
                f'Ingredients:\n' + '\n'.join(f'- {i}' for i in recipe['ingredients']) + '\n'
                f'Steps:\n' + '\n'.join(f'{m}. {s}' for m, s in enumerate(recipe['steps'], 1)))
        ask = instructions or 'Combine them into the best single version, keeping what works from each.'
        prompt = (
            'Here are several recipes that are variations of the same dish:\n\n' + '\n\n'.join(parts) +
            f'\n\n{ask}\n\nProduce one merged recipe. {RECIPE_JSON_INSTRUCTIONS}'
        )
        text = self._run([{'role': 'user', 'content': prompt}])
        return self._parse_recipe_json(text)
