"""Pluggable recipe sources. Each source normalizes to the same shape:
{"title", "ingredients": [str], "steps": [str], "servings": str|None, "source_url", "source_name"}
so the API and database never need to know which source a recipe came from.
"""
from . import scraper, themealdb

SOURCES = {
    'themealdb': themealdb,
    'url': scraper,
}
