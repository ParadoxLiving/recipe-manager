# REST API reference

Base URL: `http://<host>:8807`. JSON in, JSON out. Errors are FastAPI's usual
`{"detail": "..."}` with the matching HTTP status.

## No authentication needed

Reading, searching, and saving/importing a *new* recipe are open on the home LAN (same trust
level as `sophia-kiosk`'s read routes) -- this is also what makes importing and the LLM proposal
step easy for Sophia to call without holding a token.

| Method & path | Body | Behavior |
| --- | --- | --- |
| `GET /api/health` | - | `{"ok": true}` |
| `GET /api/recipes?q=&tag=&favorite=&limit=&offset=` | - | Paginated list of summaries (no ingredients/steps body) |
| `GET /api/recipes/{id}` | - | Full recipe; 404 if absent |
| `GET /api/recipes/{id}/variations` | - | Direct children (summaries) |
| `GET /api/recipes/{id}/lineage` | - | Ancestor chain, closest first (summaries) |
| `POST /api/recipes` | `{title, ingredients[], steps[], servings?, notes?, tags[]?, favorite?, source_url?, source_name?}` | Create a new recipe from scratch; 201 |
| `GET /api/sources/themealdb/search?q=` | - | `{"items": [{"id","title","thumbnail"}]}` from TheMealDB |
| `POST /api/import/themealdb/{meal_id}` | - | Fetch that TheMealDB recipe and save it; 201 |
| `POST /api/import/url` | `{"url"}` | Scrape a recipe site via `recipe-scrapers` (schema.org `Recipe` JSON-LD) and save it; 201; 502 if the page has no parseable recipe |
| `POST /api/recipes/{id}/improve` | `{"instructions"}` | Ask the LLM to propose a revised version (e.g. "make it healthier", "scale to 8 servings"). **Nothing is saved.** Returns `{"parent_id", "proposal": {title, ingredients[], steps[], servings, notes}}`; 503 if no Nexus token is configured, 502 if the job fails |
| `POST /api/recipes/{id}/variations` | `{title, ingredients[], steps[], servings?, notes?, tags[]?, variation_kind?}` | Save a proposal (or a hand-edited one) as a new recipe with `parent_id = id`; 201 |
| `POST /api/merge/propose` | `{"recipe_ids": [id, id, ...], "instructions"?}` | Ask the LLM to combine 2+ recipes. **Nothing is saved.** Returns `{"merged_from", "proposal": {...}}` |
| `POST /api/merge` | `{recipe_ids[], title, ingredients[], steps[], servings?, notes?, tags[]?}` | Save a merge proposal (or hand-edited one) as a new recipe with `merged_from = recipe_ids`; 201 |

## Bearer token required (`Authorization: Bearer <RECIPE_MANAGER_TOKEN>`)

Only these two change or remove a recipe that's already saved:

| Method & path | Body | Behavior |
| --- | --- | --- |
| `PUT /api/recipes/{id}` | Any subset of `{title, ingredients[], steps[], servings, notes, tags[], favorite, source_url, source_name}` | Update an existing recipe in place (e.g. toggling `favorite`, fixing a typo); 404 if absent |
| `DELETE /api/recipes/{id}` | - | Delete a recipe; 404 if absent |

Unauthenticated or wrong-token requests to these two get 401. Everything above them never
returns 401.

## Adding another recipe source

`recipe_manager/sources/` is a small plug-in point: each module normalizes to
`{"title", "ingredients": [str], "steps": [str], "servings": str|None, "source_url", "source_name"}`.
`themealdb.py` and `scraper.py` (for `recipe-scrapers`, arbitrary site URLs) are the two built in.
A paid API (Spoonacular, Edamam) can be added the same way, gated behind its own optional env-var
key, without touching the API or database layer.
