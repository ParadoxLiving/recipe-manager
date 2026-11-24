# Recipe Manager

A personal recipe manager: saves favorite recipes, imports them from TheMealDB or by pasting a
site URL, and uses an LLM (via [Nexus-Compute](http://127.0.0.1:8790)) to propose improved or
merged versions on request. Proposals are never auto-saved -- they're returned for review and
only become a recipe when explicitly saved, as a new row that keeps the original intact.

Built like the other small single-purpose apps in this household's stack (FastAPI, SQLite,
registered with [Process-Deck](http://127.0.0.1:8780)), following `sophia-kiosk`'s layout.
Sophia can search, import and propose/save recipes through it via its own adapter
(`sophia.adapters.recipe_manager`, in the `sophia` repo).

See [docs/API.md](docs/API.md) for the REST API and [ROADMAP.md](ROADMAP.md) /
[CHANGELOG.md](CHANGELOG.md) for what's shipped and what's next.

## Running it

```powershell
.\.venv\Scripts\python.exe -m recipe_manager run --host 0.0.0.0 --port 8807 --config config.json
```

- `--config` is optional; see `recipe_manager/config.py` for the shape (Nexus URL, which env var
  holds the Nexus client token, DB path).
- `RECIPE_MANAGER_TOKEN`: bearer token required to **change or delete** an already-saved recipe.
  Reading, searching, and saving/importing a *new* recipe never need it. If unset, no token is
  required at all (fine on `127.0.0.1`; the CLI refuses to bind beyond localhost without one set).
  **This is the token Sophia should use** for any adapter that edits or deletes recipes. It lives
  in this service's Process-Deck registration (`E:\Python-Services\Process-Deck\data\services.json`,
  under this service's `env.RECIPE_MANAGER_TOKEN`) -- the same place `sophia-kiosk`'s `KIOSK_TOKEN`
  lives. Copy it from there, or from Process-Deck's dashboard (Services -> recipe-manager -> Edit).
- `RECIPE_NEXUS_TOKEN` (the env var named by `config.json`'s `nexus.token_env`): the Nexus-Compute
  client credential used for the LLM-backed `/improve` and `/merge/propose` endpoints. Without it,
  those two endpoints return 503; everything else works regardless.

## Data model

One SQLite table, `recipes` (see `recipe_manager/db.py`): `title`, `ingredients` (JSON list of
strings), `steps` (JSON list of strings), `servings`, `notes`, `tags`, `favorite`, `source_url`,
`source_name`, plus lineage:

- `parent_id`: set on a variation (an improvement, a scaled version, ...), pointing at the recipe
  it was derived from. The original is never modified.
- `variation_kind`: `improvement`, `scale`, `edit`, `merge`, or null for an original.
- `merged_from`: a JSON list of recipe IDs, set only on a recipe produced by merging several.

`GET /api/recipes/{id}/lineage` walks `parent_id` back to the original; `GET
/api/recipes/{id}/variations` lists direct children.

## REST API

See [docs/API.md](docs/API.md) for the full route reference (the no-auth vs. bearer-token
split, request/response shapes, and how to add another recipe source).

## Web UI

`GET /` serves a small vanilla-JS single page (`recipe_manager/web/`) for browsing, searching,
adding, importing, editing and merging recipes. It asks for the bearer token only when you use
Edit/Favorite/Delete.
