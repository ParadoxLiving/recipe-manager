"""Arbitrary recipe site URLs via recipe-scrapers (https://pypi.org/project/recipe-scrapers/), which
reads the schema.org Recipe JSON-LD that most recipe sites embed and already supports hundreds of sites."""
import requests
from recipe_scrapers import WebsiteNotImplementedError, scrape_html, scrape_me

NAME = 'web'


def _load(url):
    try:
        return scrape_me(url)
    except WebsiteNotImplementedError:
        # Site has no dedicated scraper: fall back to its schema.org Recipe data (any site that embeds it).
        response = requests.get(url, headers={'User-Agent': 'Mozilla/5.0 (recipe-manager)'}, timeout=30)
        response.raise_for_status()
        return scrape_html(response.text, org_url=url, supported_only=False)


def _minutes(label, fn):
    try:
        m = fn()
    except Exception:
        return None
    if not m:
        return None
    return f'{label} {m // 60} h {m % 60} min' if m >= 60 and m % 60 else (f'{label} {m // 60} h' if m >= 60 else f'{label} {m} min')


def _notes(scraper):
    """Times, equipment and the recipe card's own Notes (tips, make-ahead, storage) when the page has them."""
    parts = []
    times = [t for t in (_minutes('Prep', scraper.prep_time), _minutes('Cook', scraper.cook_time),
                         _minutes('Total', scraper.total_time)) if t]
    if times:
        parts.append(' · '.join(times))
    try:
        equipment = [e.get_text(' ', strip=True) for e in scraper.soup.select('.wprm-recipe-equipment-name')]
        if equipment:
            parts.append('Equipment: ' + ', '.join(equipment))
        box = scraper.soup.select_one('.wprm-recipe-notes')
        if box:
            lines = [b.get_text(' ', strip=True) for b in box.select('span[style*="block"]')]
            if not lines:
                lines = [ln.strip() for ln in box.get_text('\n').split('\n') if ln.strip()]
            if lines:
                parts.append('Notes:\n' + '\n'.join(lines))
    except Exception:
        pass
    return '\n\n'.join(parts) or None


def fetch(url):
    scraper = _load(url)
    try:
        servings = str(scraper.yields())
    except Exception:
        servings = None
    try:
        steps = scraper.instructions_list()
    except Exception:
        steps = [s.strip() for s in (scraper.instructions() or '').split('\n') if s.strip()]
    try:
        image = scraper.image()
    except Exception:
        image = None
    return {
        'image_url': image,
        'notes': _notes(scraper),
        'title': scraper.title(),
        'ingredients': list(scraper.ingredients()),
        'steps': steps,
        'servings': servings,
        'source_url': url,
        'source_name': NAME,
    }
