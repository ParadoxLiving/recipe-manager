"""HTTP API and web UI for the recipe manager.

Auth split (see README): reading, searching, and saving/importing a *new* recipe need no
bearer token (home-LAN trust level, same as sophia-kiosk's read routes). Changing or deleting
an already-saved recipe needs `Authorization: Bearer <RECIPE_MANAGER_TOKEN>`.
"""
import hmac
import os
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import config as configuration
from .db import RecipeStore
from .nexus import NexusClient, NexusError
from .sources import scraper, themealdb

WEB_DIR = Path(__file__).parent / 'web'


def summary(recipe):
    """The list view: no ingredients/steps body, to keep listings light."""
    return {k: recipe[k] for k in (
        'id', 'title', 'servings', 'tags', 'favorite', 'source_url', 'source_name',
        'parent_id', 'variation_kind', 'merged_from', 'created_at', 'updated_at')}


def create_app(config_path=None, token=None):
    config = configuration.load(config_path)
    store = RecipeStore(config['db_path'])
    nexus_cfg = config['nexus']
    nexus_token = configuration.secret(nexus_cfg.get('token_env'))
    nexus = NexusClient(nexus_cfg['url'], nexus_token, nexus_cfg.get('model'), nexus_cfg.get('target_node'),
                         nexus_cfg.get('timeout', 180)) if nexus_token else None
    app_token = token if token is not None else os.environ.get('RECIPE_MANAGER_TOKEN')

    app = FastAPI(title='Recipe Manager')

    def require_auth(request: Request):
        if app_token and not hmac.compare_digest(request.headers.get('authorization', ''), 'Bearer ' + app_token):
            raise HTTPException(401, 'Missing or invalid bearer token')

    guard = [Depends(require_auth)]

    def need_nexus():
        if nexus is None:
            raise HTTPException(503, 'No Nexus client token configured (set nexus.token_env and the matching '
                                      'environment variable); LLM-backed improve/merge is unavailable')
        return nexus

    def not_found(recipe_id):
        raise HTTPException(404, f'No recipe with id {recipe_id}')

    @app.get('/api/health')
    def health():
        return {'ok': True}

    # ---- Reading and searching (no auth) ----

    @app.get('/api/recipes')
    def list_recipes(q: str | None = None, tag: str | None = None, favorite: bool | None = None,
                      limit: int = 100, offset: int = 0):
        limit = max(1, min(limit, 500))
        items, total = store.list(query=q, tag=tag, favorite=favorite, limit=limit, offset=offset)
        return {'items': [summary(r) for r in items], 'total': total, 'limit': limit, 'offset': offset}

    @app.get('/api/recipes/{recipe_id}')
    def get_recipe(recipe_id: str):
        recipe = store.get(recipe_id)
        if not recipe:
            not_found(recipe_id)
        return recipe

    @app.get('/api/recipes/{recipe_id}/variations')
    def get_variations(recipe_id: str):
        if not store.get(recipe_id):
            not_found(recipe_id)
        return {'items': [summary(r) for r in store.variations(recipe_id)]}

    @app.get('/api/recipes/{recipe_id}/lineage')
    def get_lineage(recipe_id: str):
        if not store.get(recipe_id):
            not_found(recipe_id)
        return {'items': [summary(r) for r in store.lineage(recipe_id)]}

    # ---- Saving/importing a new recipe (no auth) ----

    @app.post('/api/recipes', status_code=201)
    def create_recipe(body: dict):
        title, ingredients, steps = body.get('title'), body.get('ingredients'), body.get('steps')
        if not isinstance(title, str) or not title.strip():
            raise HTTPException(422, 'title is required')
        if not isinstance(ingredients, list) or not all(isinstance(i, str) for i in ingredients):
            raise HTTPException(422, 'ingredients must be a list of strings')
        if not isinstance(steps, list) or not all(isinstance(s, str) for s in steps):
            raise HTTPException(422, 'steps must be a list of strings')
        return store.create(title.strip(), ingredients, steps, servings=body.get('servings'),
                             notes=body.get('notes'), tags=body.get('tags'), favorite=body.get('favorite', False),
                             source_url=body.get('source_url'), source_name=body.get('source_name', 'manual'))

    @app.get('/api/sources/themealdb/search')
    def themealdb_search(q: str):
        try:
            return {'items': themealdb.search(q)}
        except Exception as exc:
            raise HTTPException(502, f'TheMealDB lookup failed: {exc}') from None

    @app.post('/api/import/themealdb/{meal_id}', status_code=201)
    def import_themealdb(meal_id: str):
        try:
            data = themealdb.fetch(meal_id)
        except ValueError as exc:
            raise HTTPException(404, str(exc)) from None
        except Exception as exc:
            raise HTTPException(502, f'TheMealDB lookup failed: {exc}') from None
        return store.create(data['title'], data['ingredients'], data['steps'], servings=data['servings'],
                             source_url=data['source_url'], source_name=data['source_name'])

    @app.post('/api/import/url', status_code=201)
    def import_url(body: dict):
        url = body.get('url')
        if not isinstance(url, str) or not url.startswith(('http://', 'https://')):
            raise HTTPException(422, 'url must be an http(s) URL')
        try:
            data = scraper.fetch(url)
        except Exception as exc:
            raise HTTPException(502, f"Couldn't read a recipe from that page: {exc}") from None
        return store.create(data['title'], data['ingredients'], data['steps'], servings=data['servings'],
                             source_url=data['source_url'], source_name=data['source_name'])

    # ---- LLM-backed improve/merge: propose (no auth, nothing saved), then save explicitly ----

    @app.post('/api/recipes/{recipe_id}/improve')
    def propose_improvement(recipe_id: str, body: dict):
        recipe = store.get(recipe_id)
        if not recipe:
            not_found(recipe_id)
        instructions = body.get('instructions')
        if not isinstance(instructions, str) or not instructions.strip():
            raise HTTPException(422, 'instructions is required, e.g. "make it healthier" or "scale to 8 servings"')
        try:
            proposal = need_nexus().improve(recipe, instructions.strip())
        except NexusError as exc:
            raise HTTPException(502, str(exc)) from None
        return {'parent_id': recipe_id, 'proposal': proposal}

    @app.post('/api/recipes/{recipe_id}/variations', status_code=201)
    def save_variation(recipe_id: str, body: dict):
        """Save a proposed (or hand-edited) improvement as a new recipe, keeping the original intact."""
        if not store.get(recipe_id):
            not_found(recipe_id)
        title, ingredients, steps = body.get('title'), body.get('ingredients'), body.get('steps')
        if not isinstance(title, str) or not title.strip():
            raise HTTPException(422, 'title is required')
        if not isinstance(ingredients, list) or not isinstance(steps, list):
            raise HTTPException(422, 'ingredients and steps must be lists of strings')
        return store.create(title.strip(), ingredients, steps, servings=body.get('servings'),
                             notes=body.get('notes'), tags=body.get('tags'), parent_id=recipe_id,
                             variation_kind=body.get('variation_kind', 'improvement'),
                             source_name=body.get('source_name', 'variation'))

    @app.post('/api/merge/propose')
    def propose_merge(body: dict):
        ids = body.get('recipe_ids')
        if not isinstance(ids, list) or len(ids) < 2:
            raise HTTPException(422, 'recipe_ids must be a list of at least two recipe IDs')
        recipes = [store.get(i) for i in ids]
        missing = [i for i, r in zip(ids, recipes) if not r]
        if missing:
            raise HTTPException(404, f'No recipe with id(s): {", ".join(missing)}')
        try:
            proposal = need_nexus().merge(recipes, body.get('instructions'))
        except NexusError as exc:
            raise HTTPException(502, str(exc)) from None
        return {'merged_from': ids, 'proposal': proposal}

    @app.post('/api/merge', status_code=201)
    def save_merge(body: dict):
        """Save a proposed (or hand-edited) merge as a new recipe, recording which recipes it came from."""
        ids = body.get('recipe_ids')
        if not isinstance(ids, list) or len(ids) < 2:
            raise HTTPException(422, 'recipe_ids must be a list of at least two recipe IDs')
        missing = [i for i in ids if not store.get(i)]
        if missing:
            raise HTTPException(404, f'No recipe with id(s): {", ".join(missing)}')
        title, ingredients, steps = body.get('title'), body.get('ingredients'), body.get('steps')
        if not isinstance(title, str) or not title.strip():
            raise HTTPException(422, 'title is required')
        if not isinstance(ingredients, list) or not isinstance(steps, list):
            raise HTTPException(422, 'ingredients and steps must be lists of strings')
        return store.create(title.strip(), ingredients, steps, servings=body.get('servings'),
                             notes=body.get('notes'), tags=body.get('tags'), merged_from=ids,
                             variation_kind='merge', source_name=body.get('source_name', 'merge'))

    # ---- Changing or deleting an existing saved recipe (bearer token required) ----

    @app.put('/api/recipes/{recipe_id}', dependencies=guard)
    def update_recipe(recipe_id: str, body: dict):
        if not store.get(recipe_id):
            not_found(recipe_id)
        if 'ingredients' in body and not isinstance(body['ingredients'], list):
            raise HTTPException(422, 'ingredients must be a list of strings')
        if 'steps' in body and not isinstance(body['steps'], list):
            raise HTTPException(422, 'steps must be a list of strings')
        return store.update(recipe_id, **body)

    @app.delete('/api/recipes/{recipe_id}', dependencies=guard)
    def delete_recipe(recipe_id: str):
        if not store.delete(recipe_id):
            not_found(recipe_id)
        return {'id': recipe_id, 'deleted': True}

    # ---- Web UI ----

    if WEB_DIR.is_dir():
        app.mount('/static', StaticFiles(directory=str(WEB_DIR)), name='static')

        @app.get('/')
        def index():
            return FileResponse(WEB_DIR / 'index.html')

    return app
