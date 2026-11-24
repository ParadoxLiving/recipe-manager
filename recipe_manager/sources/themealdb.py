"""TheMealDB (https://www.themealdb.com/api.php): free, keyless tier used as the zero-config default."""
import httpx

BASE = 'https://www.themealdb.com/api/json/v1/1'
NAME = 'TheMealDB'


def search(query):
    response = httpx.get(f'{BASE}/search.php', params={'s': query}, timeout=15)
    response.raise_for_status()
    meals = response.json().get('meals') or []
    return [{'id': m['idMeal'], 'title': m['strMeal'], 'thumbnail': m.get('strMealThumb')} for m in meals]


def fetch(meal_id):
    response = httpx.get(f'{BASE}/lookup.php', params={'i': meal_id}, timeout=15)
    response.raise_for_status()
    meals = response.json().get('meals')
    if not meals:
        raise ValueError(f'No TheMealDB recipe with id {meal_id}')
    meal = meals[0]
    ingredients = []
    for n in range(1, 21):
        name, measure = (meal.get(f'strIngredient{n}') or '').strip(), (meal.get(f'strMeasure{n}') or '').strip()
        if name:
            ingredients.append(f'{measure} {name}'.strip())
    steps = [s.strip() for s in (meal.get('strInstructions') or '').replace('\r\n', '\n').split('\n') if s.strip()]
    return {
        'title': meal['strMeal'],
        'ingredients': ingredients,
        'steps': steps,
        'servings': None,
        'image_url': meal.get('strMealThumb'),
        'source_url': meal.get('strSource') or f'https://www.themealdb.com/meal/{meal_id}',
        'source_name': NAME,
    }
