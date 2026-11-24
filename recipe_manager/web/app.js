// Vanilla JS, no build step. Talks to /api/* described in README.md.
const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => Array.from(document.querySelectorAll(sel));

function token() { return $('#token').value.trim(); }
function authHeaders() { const t = token(); return t ? { Authorization: 'Bearer ' + t } : {}; }

async function api(path, options = {}) {
  const response = await fetch(path, options);
  if (!response.ok) {
    let detail = response.statusText;
    try { detail = (await response.json()).detail || detail; } catch (e) { /* ignore */ }
    throw new Error(`${response.status}: ${detail}`);
  }
  if (response.status === 204) return null;
  return response.json();
}

function esc(s) { return (s ?? '').toString().replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])); }

// ---- List view ----

async function loadList() {
  const q = $('#search').value.trim();
  const favorite = $('#favorite-only').checked;
  const params = new URLSearchParams();
  if (q) params.set('q', q);
  if (favorite) params.set('favorite', 'true');
  const data = await api('/api/recipes?' + params.toString());
  const grid = $('#recipe-list');
  grid.innerHTML = '';
  if (data.items.length === 0) {
    grid.innerHTML = '<p class="notice">No recipes yet. Try importing one.</p>';
    return;
  }
  for (const r of data.items) {
    const card = document.createElement('div');
    card.className = 'recipe-card';
    const kind = r.variation_kind ? `<span class="tag">${esc(r.variation_kind)}</span>` : '';
    const thumb = r.image_url ? `<img class="thumb" src="${esc(r.image_url)}" alt="" loading="lazy" referrerpolicy="no-referrer">` : '';
    card.innerHTML = `${thumb}<h3>${esc(r.title)}${r.favorite ? ' ★' : ''}</h3>
      <div class="meta">${esc(r.source_name || '')} ${kind}</div>
      <div>${(r.tags || []).map((t) => `<span class="tag">${esc(t)}</span>`).join('')}</div>`;
    card.onclick = () => showDetail(r.id);
    grid.appendChild(card);
  }
}

$('#search').addEventListener('input', debounce(loadList, 250));
$('#favorite-only').addEventListener('change', loadList);
function debounce(fn, ms) { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; }

// ---- Detail view ----

let currentRecipe = null;

async function showDetail(id) {
  currentRecipe = await api(`/api/recipes/${id}`);
  $('#list-view').classList.add('hidden');
  $('#detail-view').classList.remove('hidden');
  renderDetail();
}

async function renderDetail() {
  const r = currentRecipe;
  const [lineage, variations] = await Promise.all([
    api(`/api/recipes/${r.id}/lineage`).catch(() => ({ items: [] })),
    api(`/api/recipes/${r.id}/variations`).catch(() => ({ items: [] })),
  ]);
  let lineageHtml = '';
  if (lineage.items.length) {
    lineageHtml = '<div class="lineage">Derived from: ' +
      lineage.items.map((l) => `<a href="#" data-goto="${l.id}">${esc(l.title)}</a>`).reverse().join(' &rarr; ') + '</div>';
  }
  if (r.merged_from) {
    lineageHtml += `<div class="lineage">Merged from ${r.merged_from.length} recipes</div>`;
  }
  let variationsHtml = '';
  if (variations.items.length) {
    variationsHtml = '<div class="lineage">Variations: ' +
      variations.items.map((v) => `<a href="#" data-goto="${v.id}">${esc(v.title)} (${esc(v.variation_kind || '')})</a>`).join(', ') + '</div>';
  }
  $('#detail-content').innerHTML = `
    <h2>${esc(r.title)} ${r.favorite ? '★' : ''}</h2>
    <div class="meta">${esc(r.source_name || '')} ${r.source_url ? `&middot; <a href="${esc(r.source_url)}" target="_blank">source</a>` : ''}
      ${r.servings ? `&middot; serves ${esc(r.servings)}` : ''}</div>
    ${r.image_url ? `<img class="hero" src="${esc(r.image_url)}" alt="" referrerpolicy="no-referrer">` : ''}
    ${lineageHtml}${variationsHtml}
    <div class="actions">
      <button id="fav-btn">${r.favorite ? 'Unfavorite' : 'Favorite'}</button>
      <button id="edit-btn">Edit</button>
      <button id="improve-btn">Improve with LLM</button>
      <button id="merge-btn">Merge with another...</button>
      <button id="delete-btn">Delete</button>
    </div>
    <h3>Ingredients</h3>
    <ul>${r.ingredients.map((i) => `<li>${esc(i)}</li>`).join('')}</ul>
    <h3>Steps</h3>
    <ol>${r.steps.map((s) => `<li>${esc(s)}</li>`).join('')}</ol>
    ${r.notes ? `<h3>Notes</h3><p class="notes">${esc(r.notes)}</p>` : ''}
  `;
  $$('#detail-content [data-goto]').forEach((a) => a.onclick = (e) => { e.preventDefault(); showDetail(a.dataset.goto); });
  $('#fav-btn').onclick = () => toggleFavorite(r);
  $('#edit-btn').onclick = () => openEdit(r);
  $('#improve-btn').onclick = () => openLlm('improve', r);
  $('#merge-btn').onclick = () => openMerge(r);
  $('#delete-btn').onclick = () => deleteRecipe(r);
}

$('#back-btn').onclick = () => {
  $('#detail-view').classList.add('hidden');
  $('#list-view').classList.remove('hidden');
  loadList();
};

async function toggleFavorite(r) {
  try {
    await api(`/api/recipes/${r.id}`, { method: 'PUT', headers: { 'Content-Type': 'application/json', ...authHeaders() },
      body: JSON.stringify({ favorite: !r.favorite }) });
    showDetail(r.id);
  } catch (e) { alert('Could not update: ' + e.message); }
}

async function deleteRecipe(r) {
  if (!confirm(`Delete "${r.title}"? This cannot be undone.`)) return;
  try {
    await api(`/api/recipes/${r.id}`, { method: 'DELETE', headers: authHeaders() });
    $('#back-btn').click();
  } catch (e) { alert('Could not delete: ' + e.message); }
}

// ---- New recipe ----

$('#new-recipe-btn').onclick = () => openEdit(null);

function openEdit(recipe) {
  $('#edit-title').textContent = recipe ? 'Edit recipe' : 'New recipe';
  $('#edit-field-title').value = recipe?.title || '';
  $('#edit-field-servings').value = recipe?.servings || '';
  $('#edit-field-tags').value = (recipe?.tags || []).join(', ');
  $('#edit-field-ingredients').value = (recipe?.ingredients || []).join('\n');
  $('#edit-field-steps').value = (recipe?.steps || []).join('\n');
  $('#edit-field-notes').value = recipe?.notes || '';
  const dialog = $('#edit-dialog');
  dialog.dataset.editingId = recipe ? recipe.id : '';
  dialog.showModal();
}

$('#edit-cancel-btn').onclick = () => $('#edit-dialog').close();

$('#edit-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const id = $('#edit-dialog').dataset.editingId;
  const body = {
    title: $('#edit-field-title').value.trim(),
    servings: $('#edit-field-servings').value.trim() || null,
    tags: $('#edit-field-tags').value.split(',').map((t) => t.trim()).filter(Boolean),
    ingredients: $('#edit-field-ingredients').value.split('\n').map((s) => s.trim()).filter(Boolean),
    steps: $('#edit-field-steps').value.split('\n').map((s) => s.trim()).filter(Boolean),
    notes: $('#edit-field-notes').value.trim() || null,
  };
  try {
    if (id) {
      await api(`/api/recipes/${id}`, { method: 'PUT', headers: { 'Content-Type': 'application/json', ...authHeaders() }, body: JSON.stringify(body) });
      $('#edit-dialog').close();
      showDetail(id);
    } else {
      const created = await api('/api/recipes', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
      $('#edit-dialog').close();
      showDetail(created.id);
    }
  } catch (err) { alert('Could not save: ' + err.message); }
});

// ---- Import ----

$('#import-btn').onclick = () => $('#import-dialog').showModal();
$('#import-close-btn').onclick = () => $('#import-dialog').close();

$$('.tab').forEach((btn) => btn.onclick = () => {
  $$('.tab').forEach((b) => b.classList.remove('active'));
  btn.classList.add('active');
  $$('[data-tab-panel]').forEach((p) => p.classList.toggle('hidden', p.dataset.tabPanel !== btn.dataset.tab));
});

$('#import-url-btn').onclick = async () => {
  const url = $('#import-url').value.trim();
  if (!url) return;
  try {
    const created = await api('/api/import/url', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ url }) });
    $('#import-dialog').close();
    showDetail(created.id);
  } catch (e) { alert('Import failed: ' + e.message); }
};

$('#themealdb-search-btn').onclick = async () => {
  const q = $('#themealdb-query').value.trim();
  const results = $('#themealdb-results');
  results.innerHTML = 'Searching...';
  try {
    const data = await api('/api/sources/themealdb/search?q=' + encodeURIComponent(q));
    if (!data.items.length) { results.innerHTML = '<p class="notice">No results.</p>'; return; }
    results.innerHTML = '';
    for (const m of data.items) {
      const row = document.createElement('div');
      row.className = 'result-item';
      row.innerHTML = `<span>${esc(m.title)}</span>`;
      const btn = document.createElement('button');
      btn.textContent = 'Import';
      btn.onclick = async () => {
        try {
          const created = await api(`/api/import/themealdb/${m.id}`, { method: 'POST' });
          $('#import-dialog').close();
          showDetail(created.id);
        } catch (e) { alert('Import failed: ' + e.message); }
      };
      row.appendChild(btn);
      results.appendChild(row);
    }
  } catch (e) { results.innerHTML = `<p class="error">${esc(e.message)}</p>`; }
};

// ---- LLM improve / merge ----

let llmContext = null; // { mode: 'improve'|'merge', recipe or recipes }

function openLlm(mode, recipeOrList) {
  llmContext = { mode, subject: recipeOrList };
  $('#llm-title').textContent = mode === 'improve' ? 'Improve this recipe' : 'Merge recipes';
  $('#llm-instructions-label').firstChild.textContent = mode === 'improve'
    ? 'What would you like changed? ' : 'How should they be combined? (optional) ';
  $('#llm-instructions').value = '';
  $('#llm-proposal').classList.add('hidden');
  $('#llm-proposal').innerHTML = '';
  $('#llm-dialog').showModal();
}

$('#llm-close-btn').onclick = () => $('#llm-dialog').close();

$('#llm-propose-btn').onclick = async () => {
  const instructions = $('#llm-instructions').value.trim();
  if (llmContext.mode === 'improve' && !instructions) { alert('Say what you want changed.'); return; }
  const proposalBox = $('#llm-proposal');
  proposalBox.classList.remove('hidden');
  proposalBox.innerHTML = '<p class="notice">Asking the LLM...</p>';
  try {
    let data;
    if (llmContext.mode === 'improve') {
      data = await api(`/api/recipes/${llmContext.subject.id}/improve`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ instructions }) });
    } else {
      data = await api('/api/merge/propose', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ recipe_ids: llmContext.subject, instructions: instructions || undefined }) });
    }
    renderProposal(data.proposal);
  } catch (e) { proposalBox.innerHTML = `<p class="error">${esc(e.message)}</p>`; }
};

function renderProposal(p) {
  const box = $('#llm-proposal');
  box.innerHTML = `
    <h3>${esc(p.title)}</h3>
    ${p.servings ? `<p>Serves ${esc(p.servings)}</p>` : ''}
    <h4>Ingredients</h4><ul>${p.ingredients.map((i) => `<li>${esc(i)}</li>`).join('')}</ul>
    <h4>Steps</h4><ol>${p.steps.map((s) => `<li>${esc(s)}</li>`).join('')}</ol>
    ${p.notes ? `<p class="notice">${esc(p.notes)}</p>` : ''}
    <div class="dialog-actions">
      <button id="llm-save-btn">Save as new recipe</button>
      <button id="llm-discard-btn">Discard</button>
    </div>`;
  $('#llm-discard-btn').onclick = () => $('#llm-dialog').close();
  $('#llm-save-btn').onclick = async () => {
    try {
      let created;
      if (llmContext.mode === 'improve') {
        created = await api(`/api/recipes/${llmContext.subject.id}/variations`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(p) });
      } else {
        created = await api('/api/merge', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ ...p, recipe_ids: llmContext.subject }) });
      }
      $('#llm-dialog').close();
      showDetail(created.id);
    } catch (e) { alert('Could not save: ' + e.message); }
  };
}

function openMerge(recipe) {
  const otherId = prompt('Enter the ID of another saved recipe to merge with ' + recipe.title + ':\n'
    + '(open it from the list and copy its id from the URL bar\'s address, or use the API to find ids)');
  if (!otherId) return;
  openLlm('merge', [recipe.id, otherId.trim()]);
}

// ---- Init ----

loadList();
