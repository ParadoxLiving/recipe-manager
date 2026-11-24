# Roadmap

What shipped is in [CHANGELOG.md](CHANGELOG.md).

## Shipped

- [x] Core app: FastAPI + SQLite, saved recipes with variation/merge lineage
- [x] Import from TheMealDB (keyless) and arbitrary recipe URLs via `recipe-scrapers`
- [x] LLM-backed improve/merge via Nexus-Compute, propose-then-explicitly-save (never
      auto-overwrites)
- [x] REST API with a no-auth read/search/save-new vs. bearer-token
      update/delete split
- [x] Vanilla-JS web UI (list, search, detail, lineage, edit, improve, merge)
- [x] Registered with Process-Deck as a managed service
- [x] Sophia adapter (`sophia.adapters.recipe_manager`) so Sophia can search, import and
      propose/save recipes by voice/chat -- see the `sophia` repo
- [x] Git repo, docs/ split, roadmap

## Next

- [ ] LAN-accessible via an nginx subdomain (reverse proxy in front of `127.0.0.1:8807`),
      matching how Sophia/other household apps are published on the LAN
- [ ] Built-in "scale this recipe" operation (servings multiplier, with ingredient-quantity
      parsing) instead of doing it by hand via the LLM each time
- [ ] Shopping list: combine ingredients across one or more selected recipes into one
      deduplicated list

## Later

- [ ] Recipe photos (upload/display an image per recipe)
- [ ] Meal planning: assign saved recipes to days of a week/calendar view
- [ ] Additional import sources (e.g. Spoonacular/Edamam, gated behind their own optional
      API key), reusing the existing `recipe_manager/sources/` plug-in point
- [ ] Print/export view (clean single-page printout of one recipe)
- [ ] Multi-user support (currently single shared household collection)

## Known limitations

- Some recipe sites block `recipe-scrapers`' requests outright (e.g. allrecipes.com returns
  403); there's no workaround besides trying a different source for that recipe.
- The LLM improve/merge flow depends on Nexus-Compute being reachable and a valid
  `RECIPE_NEXUS_TOKEN`; without it those two endpoints return 503 but everything else still
  works.
