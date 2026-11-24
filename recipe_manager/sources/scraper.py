"""Arbitrary recipe site URLs via recipe-scrapers (https://pypi.org/project/recipe-scrapers/), which
reads the schema.org Recipe JSON-LD that most recipe sites embed and already supports hundreds of sites."""
from recipe_scrapers import scrape_me

NAME = 'web'


def fetch(url):
    scraper = scrape_me(url)
    try:
        servings = str(scraper.yields())
    except Exception:
        servings = None
    try:
        steps = scraper.instructions_list()
    except Exception:
        steps = [s.strip() for s in (scraper.instructions() or '').split('\n') if s.strip()]
    return {
        'title': scraper.title(),
        'ingredients': list(scraper.ingredients()),
        'steps': steps,
        'servings': servings,
        'source_url': url,
        'source_name': NAME,
    }
