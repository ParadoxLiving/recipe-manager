"""SQLite storage for saved recipes, with variation/merge lineage.

One table. A recipe is either an original (parent_id and merged_from both null), a variation
(parent_id set: an improvement, a scaling, a manual edit-as-copy) or a merge (merged_from set:
a list of recipe IDs it was produced from). Nothing is ever overwritten by an LLM proposal --
proposals are returned to the caller and only become rows when explicitly saved.
"""
import json
import sqlite3
import time
import uuid
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS recipes (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    ingredients TEXT NOT NULL,      -- JSON list of strings
    steps TEXT NOT NULL,            -- JSON list of strings
    servings TEXT,
    notes TEXT,
    tags TEXT NOT NULL DEFAULT '[]',   -- JSON list of strings
    favorite INTEGER NOT NULL DEFAULT 0,
    source_url TEXT,
    source_name TEXT,
    parent_id TEXT REFERENCES recipes(id),
    variation_kind TEXT,            -- 'improvement', 'scale', 'merge', 'edit', or null for an original
    merged_from TEXT,               -- JSON list of recipe IDs, only set for a merge
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_recipes_parent ON recipes(parent_id);
CREATE INDEX IF NOT EXISTS idx_recipes_title ON recipes(title);
"""

LIST_FIELDS = ('id', 'title', 'servings', 'tags', 'favorite', 'source_url', 'source_name',
               'parent_id', 'variation_kind', 'merged_from', 'created_at', 'updated_at')


class RecipeStore:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute('PRAGMA foreign_keys = ON')
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    @staticmethod
    def _row(row):
        d = dict(row)
        d['ingredients'] = json.loads(d['ingredients'])
        d['steps'] = json.loads(d['steps'])
        d['tags'] = json.loads(d['tags'])
        d['merged_from'] = json.loads(d['merged_from']) if d['merged_from'] else None
        d['favorite'] = bool(d['favorite'])
        return d

    def create(self, title, ingredients, steps, servings=None, notes=None, tags=None, favorite=False,
               source_url=None, source_name=None, parent_id=None, variation_kind=None, merged_from=None):
        recipe_id = uuid.uuid4().hex
        now = time.time()
        self.conn.execute(
            'INSERT INTO recipes (id, title, ingredients, steps, servings, notes, tags, favorite, source_url, '
            'source_name, parent_id, variation_kind, merged_from, created_at, updated_at) '
            'VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
            (recipe_id, title, json.dumps(ingredients), json.dumps(steps), servings, notes,
             json.dumps(tags or []), int(bool(favorite)), source_url, source_name, parent_id,
             variation_kind, json.dumps(merged_from) if merged_from else None, now, now))
        self.conn.commit()
        return self.get(recipe_id)

    def get(self, recipe_id):
        row = self.conn.execute('SELECT * FROM recipes WHERE id = ?', (recipe_id,)).fetchone()
        return self._row(row) if row else None

    def update(self, recipe_id, **fields):
        if not self.get(recipe_id):
            return None
        allowed = {'title', 'ingredients', 'steps', 'servings', 'notes', 'tags', 'favorite', 'source_url', 'source_name'}
        sets, values = [], []
        for key, value in fields.items():
            if key not in allowed:
                continue
            if key in ('ingredients', 'steps', 'tags'):
                value = json.dumps(value)
            elif key == 'favorite':
                value = int(bool(value))
            sets.append(f'{key} = ?')
            values.append(value)
        if not sets:
            return self.get(recipe_id)
        sets.append('updated_at = ?')
        values.append(time.time())
        values.append(recipe_id)
        self.conn.execute(f'UPDATE recipes SET {", ".join(sets)} WHERE id = ?', values)
        self.conn.commit()
        return self.get(recipe_id)

    def delete(self, recipe_id):
        cur = self.conn.execute('DELETE FROM recipes WHERE id = ?', (recipe_id,))
        self.conn.commit()
        return cur.rowcount > 0

    def list(self, query=None, tag=None, favorite=None, limit=100, offset=0):
        clauses, params = [], []
        if query:
            clauses.append('(title LIKE ? OR ingredients LIKE ?)')
            like = f'%{query}%'
            params += [like, like]
        if tag:
            clauses.append('tags LIKE ?')
            params.append(f'%"{tag}"%')
        if favorite is not None:
            clauses.append('favorite = ?')
            params.append(int(bool(favorite)))
        where = ('WHERE ' + ' AND '.join(clauses)) if clauses else ''
        rows = self.conn.execute(
            f'SELECT * FROM recipes {where} ORDER BY updated_at DESC LIMIT ? OFFSET ?',
            params + [limit, offset]).fetchall()
        total = self.conn.execute(f'SELECT COUNT(*) FROM recipes {where}', params).fetchone()[0]
        return [self._row(r) for r in rows], total

    def variations(self, recipe_id):
        rows = self.conn.execute('SELECT * FROM recipes WHERE parent_id = ? ORDER BY created_at',
                                  (recipe_id,)).fetchall()
        return [self._row(r) for r in rows]

    def lineage(self, recipe_id):
        """The chain of ancestors from this recipe back to its original, closest first."""
        chain = []
        current = self.get(recipe_id)
        seen = set()
        while current and current.get('parent_id') and current['parent_id'] not in seen:
            seen.add(current['id'])
            parent = self.get(current['parent_id'])
            if not parent:
                break
            chain.append(parent)
            current = parent
        return chain
