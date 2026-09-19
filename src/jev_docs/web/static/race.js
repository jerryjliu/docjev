'use strict';

const $ = (id) => document.getElementById(id);
const engines = ['jev', 'openai'];
const colors = ['#9270df', '#77bcb7', '#ed9cbb', '#d8ae6d', '#7e9cca', '#a3b86d'];
const state = {
  task: new URLSearchParams(window.location.search).get('task') === 'split' ? 'split' : 'classify',
  samples: [], rules: {}, selected: null, demoSet: 'real', phase: 'loading',
  preparation: null, race: null, generation: 0, timer: null, page: 1,
  coloredEngine: null, signatures: {}, consumed: false,
};

function element(tag, className, text) {
  const item = document.createElement(tag);
  if (className) item.className = className;
  if (text != null) item.textContent = text;
  return item;
}
const title = (value) => String(value || '').replaceAll('_', ' ').replace(/^./, (letter) => letter.toUpperCase());
const measured = (value) => typeof value === 'number' && Number.isFinite(value) && value >= 0;
function duration(ms) {
  if (!measured(ms)) return 'Unavailable';
  return ms < 1000 ? `${Math.round(ms)} ms` : `${(ms / 1000).toFixed(ms < 10000 ? 2 : 1)} s`;
}
function errorMessage(error) { return error instanceof Error ? error.message : String(error); }
function showError(message = '') {
  $('error').textContent = message;
  $('error').hidden = !message;
}
async function request(path, payload) {
  const response = await fetch(path, payload === undefined ? {cache: 'no-store'} : {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload),
  });
  let data;
  try { data = await response.json(); }
  catch { throw new Error('The local server returned an unreadable response.'); }
  if (!response.ok) {
    const detail = typeof data.detail === 'string' ? data.detail : 'Please check the local setup and category rules.';
    throw new Error(detail);
  }
  return data;
}
function racing() { return state.phase === 'running' || state.phase === 'starting'; }
function controls() {
  const busy = racing();
  $('task').disabled = busy || state.phase === 'loading';
  $('sample').disabled = busy || state.phase === 'loading';
  $('rules-button').disabled = busy || !state.rules[state.task];
  $('prepare-again').disabled = busy || state.phase === 'preparing' || !state.selected;
  const button = $('run-both');
  button.disabled = busy || state.phase === 'preparing' || !state.selected;
  if (state.phase === 'loading') button.disabled = true;
  const label = state.phase === 'starting' || state.phase === 'running' ? 'Running…'
    : state.phase === 'preparing' ? 'Preparing document…'
    : state.consumed ? 'Prepare another run'
    : state.phase === 'error' ? 'Prepare again' : 'Run both models';
  button.replaceChildren(document.createTextNode(label));
  if (!busy && state.phase !== 'preparing') button.append(element('span', '', '↗'));
}
function resetCards() {
  state.race = null;
  state.signatures = {};
  state.coloredEngine = null;
  $('result-download').hidden = true;
  $('result-download').removeAttribute('href');
  engines.forEach((engine) => renderEngine(engine, {status: 'waiting'}));
  paintPages();
}
function provenance(source = state.selected?.provenance) {
  const kind = source?.kind || (state.demoSet === 'synthetic' ? 'synthetic' : 'original');
  $('source-kind').textContent = kind === 'synthetic' ? 'SYNTHETIC TEST FIXTURE'
    : kind === 'excerpt' ? 'ORIGINAL DOCUMENT EXCERPT'
    : ['assembled', 'packet', 'concatenated'].includes(kind) ? 'PACKET OF ORIGINAL DOCUMENTS'
    : 'ORIGINAL PUBLIC DOCUMENT';
  $('source-links').replaceChildren();
  for (const sourceLink of source?.sources || []) {
    let url;
    try { url = new URL(sourceLink.url); } catch { continue; }
    if (url.protocol !== 'https:') continue;
    const link = element('a', '', `${sourceLink.title || 'Original source'} ↗`);
    link.href = url.href;
    link.target = '_blank';
    link.rel = 'noopener noreferrer';
    $('source-links').append(link);
  }
  if (!$('source-links').children.length) {
    $('source-links').append(element('p', '', kind === 'synthetic'
      ? 'First-party synthetic example. No real person or transaction.' : 'Source details are recorded with this sample.'));
  }
  const note = [source?.issuer, source?.note].filter(Boolean).join(' · ');
  $('source-note').textContent = note;
  $('source-note').hidden = !note;
  const independence = $('sources-dialog').querySelector('.independence');
  independence.textContent = kind === 'synthetic'
    ? 'Generated fixture for a repeatable demonstration.' : 'Independent demo; no government endorsement.';
}
function setTask(task) {
  if (racing()) return;
  state.task = task === 'split' ? 'split' : 'classify';
  $('task').value = state.task;
  const url = new URL(window.location.href);
  url.searchParams.set('task', state.task);
  history.replaceState(null, '', url);
  const samples = state.samples.filter((sample) => sample.task === state.task);
  $('sample').replaceChildren();
  for (const sample of samples) {
    const option = element('option', '', sample.title);
    option.value = sample.id;
    $('sample').append(option);
  }
  const selected = (state.task === 'classify' && samples.find((sample) => sample.id === 'r04')) || samples[0];
  if (!selected) {
    ++state.generation;
    clearTimeout(state.timer);
    state.selected = null;
    state.preparation = null;
    state.phase = 'error';
    resetCards();
    $('page-image').hidden = true;
    $('page-buttons').replaceChildren();
    $('preview-message').hidden = false;
    $('preview-message').textContent = 'No source documents are available for this task.';
    showError('No source documents are available for this task.');
    controls();
    return;
  }
  $('sample').value = selected.id;
  selectSample(selected);
}
function selectSample(sample) {
  if (racing()) return;
  state.selected = sample;
  $('source-title').textContent = sample.title;
  $('comparison-title').textContent = state.task === 'classify' ? 'Two models. One category.' : 'Two models. Every boundary.';
  provenance();
  prepare();
}
function selectedSegments() {
  return state.race?.engines?.[state.coloredEngine]?.result?.segments || [];
}
function paintPages() {
  const segments = selectedSegments();
  for (const button of $('page-buttons').children) {
    const page = Number(button.dataset.page);
    const index = segments.findIndex((segment) => segment.pages.includes(page));
    button.style.removeProperty('--segment-color');
    if (index >= 0) button.style.setProperty('--segment-color', colors[index % colors.length]);
    button.classList.toggle('active', page === state.page);
    button.setAttribute('aria-current', page === state.page ? 'page' : 'false');
    const description = index >= 0 ? `, ${title(segments[index].category)}, document ${index + 1}` : '';
    button.setAttribute('aria-label', `View page ${page}${description}`);
    button.title = `Page ${page}${description}`;
  }
  for (const engine of engines) {
    for (const button of $(`${engine}-card`).querySelectorAll('.segment-button')) {
      const segment = state.race?.engines?.[engine]?.result?.segments?.[Number(button.dataset.segment)];
      const active = engine === state.coloredEngine && segment?.pages.includes(state.page);
      button.classList.toggle('active', Boolean(active));
      button.setAttribute('aria-pressed', String(Boolean(active)));
    }
  }
}
function showPage(number) {
  const preview = state.preparation?.preview?.pages?.find((page) => page.number === number);
  if (!preview) return;
  state.page = number;
  const image = $('page-image');
  image.hidden = false;
  $('preview-message').hidden = true;
  image.src = preview.image;
  image.alt = `Original page ${number} of ${state.preparation.title}`;
  $('document-view').scrollTop = 0;
  paintPages();
}
function showPreview() {
  $('page-buttons').replaceChildren();
  for (const page of state.preparation.preview?.pages || []) {
    const button = element('button', 'page-button', String(page.number));
    button.type = 'button';
    button.dataset.page = String(page.number);
    button.addEventListener('click', () => showPage(page.number));
    $('page-buttons').append(button);
  }
  showPage(1);
}
function showPreparation(preparation) {
  state.preparation = preparation;
  $('ocr-label').textContent = preparation.stage || 'Preparing OCR';
  if (preparation.status === 'ready') {
    state.consumed = preparation.can_start === false;
    state.phase = state.consumed ? 'complete' : 'ready';
    $('ocr-label').textContent = 'OCR ready';
    $('ocr-dot').classList.add('ready');
    const metrics = preparation.ocr_metrics || {};
    const elapsed = measured(metrics.ocr_ms) && measured(metrics.conversion_ms)
      ? duration(metrics.ocr_ms + metrics.conversion_ms) : 'Timing unavailable';
    $('ocr-time').textContent = `LiteParse · ${elapsed} conversion + OCR · ${metrics.ocr_cache_hit ? 'cached OCR' : 'fresh OCR'}`;
    $('run-note').textContent = state.consumed
      ? 'This preparation has already been used. Prepare another run to compare both models again.'
      : 'Both models will receive the same prepared page text and category rules.';
    provenance(preparation.provenance);
    showPreview();
  } else if (preparation.status === 'error') {
    state.phase = 'error';
    $('ocr-label').textContent = 'Preparation failed';
    $('preview-message').textContent = 'The document could not be prepared.';
    showError(preparation.error || 'The document could not be prepared.');
  }
  controls();
}
async function pollPreparation(id, generation) {
  if (generation !== state.generation) return;
  try {
    const preparation = await request(`/api/race/preparations/${encodeURIComponent(id)}`);
    if (generation !== state.generation) return;
    showPreparation(preparation);
    if (preparation.status === 'preparing') {
      state.timer = setTimeout(() => pollPreparation(id, generation), 100);
    }
  } catch (error) {
    if (generation !== state.generation) return;
    state.phase = 'error';
    $('ocr-label').textContent = 'Preparation unavailable';
    showError(errorMessage(error));
    controls();
  }
}
async function prepare() {
  if (racing() || !state.selected) return;
  const generation = ++state.generation;
  clearTimeout(state.timer);
  state.phase = 'preparing';
  state.preparation = null;
  state.consumed = false;
  state.page = 1;
  resetCards();
  showError();
  $('ocr-dot').classList.remove('ready');
  $('ocr-label').textContent = 'Preparing OCR';
  $('ocr-time').textContent = 'LiteParse · local';
  $('run-note').textContent = 'Reading the source once for both models. No classification or splitting has started.';
  $('page-image').hidden = true;
  $('page-image').removeAttribute('src');
  $('page-buttons').replaceChildren();
  $('preview-message').hidden = false;
  $('preview-message').textContent = 'Reading your original document…';
  controls();
  try {
    const preparation = await request('/api/race/prepare', {
      task: state.task, sample_id: state.selected.id, use_cache: false,
    });
    if (generation !== state.generation) return;
    showPreparation(preparation);
    if (preparation.status === 'preparing') {
      state.timer = setTimeout(() => pollPreparation(preparation.id, generation), 100);
    }
  } catch (error) {
    if (generation !== state.generation) return;
    state.phase = 'error';
    $('ocr-label').textContent = 'Preparation failed';
    showError(errorMessage(error));
    controls();
  }
}
function addWarnings(result, body) {
  if (result.needs_review) body.append(element('p', 'result-note', 'Review suggested. Check this result against the original document.'));
  for (const warning of result.warnings || []) body.append(element('p', 'result-note', warning));
}
function renderEngine(engine, engineState) {
  const signature = JSON.stringify([engineState.status, engineState.model, engineState.result, engineState.error]);
  if (state.signatures[engine] === signature) return;
  state.signatures[engine] = signature;
  const card = $(`${engine}-card`);
  const result = engineState.result;
  const status = engineState.status;
  const complete = status === 'complete' && result;
  const running = ['queued', 'running'].includes(status);
  const heading = element('div', 'model-heading');
  heading.append(element('h3', '', engine === 'jev' ? 'Jev' : 'GPT-5.6 Luna'));
  const label = complete ? 'COMPLETE' : status === 'error' ? 'ERROR' : running ? 'RUNNING' : 'READY TO RUN';
  heading.append(element('span', `model-state ${complete ? 'complete' : status === 'error' ? 'error' : running ? 'running' : ''}`, label));
  const model = element('p', 'model-id', result?.model || engineState.model || 'Model ID appears when started');
  const timing = element('div', 'decision-time');
  timing.append(element('span', '', 'Decision time'));
  const value = element('strong');
  if (complete && measured(result.metrics?.decision_ms)) {
    const [number, unit] = duration(result.metrics.decision_ms).split(' ');
    value.append(document.createTextNode(number), element('small', '', unit));
  } else value.textContent = running ? '…' : '—';
  timing.append(value);
  const body = element('div', 'result-body');
  if (complete && state.task === 'classify') {
    body.append(element('p', 'result-label', 'PREDICTED CATEGORY'));
    const category = element('div', 'category-result');
    category.append(element('h4', '', title(result.category)));
    body.append(category, element('p', 'result-note', 'One document. One category, using your shared rules.'));
    addWarnings(result, body);
  } else if (complete && state.task === 'split') {
    const segments = result.segments || [];
    body.append(element('p', 'result-label', 'DOCUMENT SEGMENTS'));
    body.append(element('h4', '', `${segments.length} documents`));
    body.append(element('p', 'result-detail', `${result.document?.page_count || state.preparation.preview.pages.length} pages · Select a segment to inspect it.`));
    const list = element('div', 'segment-list');
    segments.forEach((segment, index) => {
      if (index > 0 && segments[index - 1].category === segment.category) {
        list.append(element('p', 'boundary-note', 'SAME CATEGORY · SEPARATE DOCUMENT'));
      }
      const button = element('button', 'segment-button');
      button.type = 'button';
      button.dataset.segment = String(index);
      button.style.setProperty('--segment-color', colors[index % colors.length]);
      const copy = element('span', 'segment-copy');
      const pages = segment.pages.length === 1 ? `Page ${segment.pages[0]}` : `Pages ${segment.pages[0]}–${segment.pages.at(-1)}`;
      copy.append(element('strong', '', title(segment.category)), element('small', '', `${pages}${segment.needs_review ? ' · review suggested' : ''}`));
      button.append(element('span', 'segment-number', String(index + 1).padStart(2, '0')), copy, element('span', 'segment-arrow', '↗'));
      button.setAttribute('aria-label', `${engine === 'jev' ? 'Jev' : 'GPT-5.6 Luna'} document ${index + 1}: ${title(segment.category)}, ${pages.toLowerCase()}`);
      button.addEventListener('click', () => {
        state.coloredEngine = engine;
        showPage(segment.pages[0]);
        updateRunNote();
      });
      list.append(button);
    });
    body.append(list);
    addWarnings(result, body);
    if (!state.coloredEngine) state.coloredEngine = engine;
  } else if (status === 'error') {
    body.append(element('h4', 'waiting-title', 'This model could not finish.'));
    body.append(element('p', 'model-error', engineState.error || 'No result was returned.'));
  } else {
    body.append(element('h4', 'waiting-title', running ? 'Running…' : 'Ready when you are.'));
    body.append(element('p', '', running
      ? 'Applying the shared rules to the prepared document.'
      : state.task === 'classify' ? 'Classify the original document with your category rules.' : 'Find each source document, including adjacent documents of the same category.'));
  }
  card.replaceChildren(heading, model, timing, body);
}
function updateRunNote() {
  if (!state.race) return;
  const coloring = state.task === 'split' && state.coloredEngine
    ? ` Page colors show ${state.coloredEngine === 'jev' ? 'Jev' : 'GPT-5.6 Luna'} segments.` : '';
  $('run-note').textContent = (state.race.status === 'complete'
    ? 'One live run. Decision time excludes OCR; results are model predictions.'
    : 'Both models are running independently on identical OCR text and rules.') + coloring;
}
function showRace(race) {
  state.race = race;
  for (const engine of engines) renderEngine(engine, race.engines?.[engine] || {status: 'queued'});
  paintPages();
  updateRunNote();
  if (race.status === 'complete') {
    state.phase = 'complete';
    if (race.download) {
      $('result-download').href = `${race.download}?download=true`;
      $('result-download').hidden = false;
    }
  }
  controls();
}
async function pollRace(id, generation) {
  if (generation !== state.generation) return;
  try {
    const race = await request(`/api/race/runs/${encodeURIComponent(id)}`);
    if (generation !== state.generation) return;
    showError();
    showRace(race);
    if (race.status !== 'complete') state.timer = setTimeout(() => pollRace(id, generation), 50);
  } catch (error) {
    if (generation !== state.generation) return;
    showError(`${errorMessage(error)} Waiting to reconnect to this run; no new inference will be started.`);
    // A lost polling response must never submit a second paid run.
    state.timer = setTimeout(() => pollRace(id, generation), 1000);
  }
}
async function startRace() {
  if (racing() || state.phase === 'preparing') return;
  if (state.consumed || state.phase === 'error') { prepare(); return; }
  if (state.phase !== 'ready' || !state.preparation) return;
  state.phase = 'starting';
  state.consumed = true;
  const generation = state.generation;
  showError();
  resetCards();
  engines.forEach((engine) => renderEngine(engine, {status: 'queued'}));
  controls();
  try {
    const race = await request('/api/race/start', {
      preparation_id: state.preparation.id, rules: state.rules[state.task],
    });
    if (generation !== state.generation) return;
    state.phase = 'running';
    showRace(race);
    if (race.status !== 'complete') state.timer = setTimeout(() => pollRace(race.id, generation), 50);
  } catch (error) {
    state.phase = 'error';
    engines.forEach((engine) => renderEngine(engine, {status: 'error', error: 'Start could not be confirmed. No result has been substituted.'}));
    showError(`${errorMessage(error)} The start response was not confirmed. Check the local server before preparing another run.`);
    controls();
  }
}
function addRule(rule = {id: '', description: ''}) {
  const row = element('div', 'rule-row');
  const id = element('input');
  id.value = rule.id;
  id.placeholder = 'category_id';
  id.required = true;
  id.pattern = '[a-z][a-z0-9_]*';
  id.maxLength = 80;
  id.setAttribute('aria-label', 'Category name: lowercase letters, numbers, and underscores');
  const description = element('textarea');
  description.value = rule.description;
  description.placeholder = 'Describe the documents that belong in this category…';
  description.required = true;
  description.rows = 2;
  description.maxLength = 4000;
  description.setAttribute('aria-label', 'Category description');
  const remove = element('button', '', '×');
  remove.type = 'button';
  remove.setAttribute('aria-label', 'Remove category');
  remove.addEventListener('click', () => row.remove());
  if (rule.id === 'other') { id.readOnly = true; remove.disabled = true; }
  row.append(id, description, remove);
  $('rules-list').append(row);
}
function openRules() {
  if (racing() || !state.rules[state.task]) return;
  const rules = state.rules[state.task];
  $('rules-list').replaceChildren();
  rules.categories.forEach(addRule);
  $('instructions').value = rules.instructions || '';
  $('boundary-instructions').value = rules.splitting_instructions || '';
  $('instructions').maxLength = $('boundary-instructions').maxLength = 8000;
  $('boundary-fields').hidden = state.task !== 'split';
  $('rules-error').textContent = '';
  $('rules-dialog').showModal();
}
$('rules-form').addEventListener('submit', (event) => {
  event.preventDefault();
  if (racing()) return;
  const categories = Array.from($('rules-list').children).map((row) => ({
    id: row.querySelector('input').value.trim(), description: row.querySelector('textarea').value.trim(),
  }));
  if (!categories.length || categories.length > 255) { $('rules-error').textContent = 'Use between 1 and 255 categories.'; return; }
  if (categories.some((category) => !category.description || !/^[a-z][a-z0-9_]*$/.test(category.id))) {
    $('rules-error').textContent = 'Give each category a lowercase name and a description.'; return;
  }
  if (new Set(categories.map((category) => category.id)).size !== categories.length) {
    $('rules-error').textContent = 'Each category needs a unique name.'; return;
  }
  if (!categories.some((category) => category.id === 'other') && categories.length === 255) {
    $('rules-error').textContent = 'Leave one category slot for the Other fallback.'; return;
  }
  state.rules[state.task] = {
    schema_version: '1', categories, instructions: $('instructions').value.trim(),
    splitting_instructions: $('boundary-instructions').value.trim(),
  };
  $('rules-dialog').close();
  resetCards();
  $('run-note').textContent = state.consumed
    ? 'Rules updated for both models. Prepare another run when you are ready.'
    : 'Rules updated for both models. The prepared OCR text is unchanged.';
  controls();
});
$('task').addEventListener('change', () => setTask($('task').value));
$('sample').addEventListener('change', () => {
  const sample = state.samples.find((entry) => entry.id === $('sample').value && entry.task === state.task);
  if (sample) selectSample(sample);
});
$('run-both').addEventListener('click', startRace);
$('prepare-again').addEventListener('click', prepare);
$('rules-button').addEventListener('click', openRules);
$('close-rules').addEventListener('click', () => $('rules-dialog').close());
$('add-rule').addEventListener('click', () => addRule());
$('source-button').addEventListener('click', () => $('sources-dialog').showModal());
$('close-sources').addEventListener('click', () => $('sources-dialog').close());
$('fit-button').addEventListener('click', () => {
  const fit = $('document-view').classList.toggle('fit-page');
  $('fit-button').setAttribute('aria-pressed', String(fit));
  $('fit-button').textContent = fit ? 'Fit width' : 'Fit page';
});
$('page-image').addEventListener('error', () => {
  $('page-image').hidden = true;
  $('preview-message').hidden = false;
  $('preview-message').textContent = 'This page preview could not load. Select the page again to retry.';
});
window.addEventListener('beforeunload', () => clearTimeout(state.timer));

async function init() {
  resetCards();
  controls();
  try {
    const data = await request('/api/samples');
    state.samples = data.samples || [];
    state.rules = data.rules || {};
    state.demoSet = data.demo_set?.id || 'synthetic';
    setTask(state.task);
  } catch (error) {
    state.phase = 'error';
    showError(errorMessage(error));
    $('ocr-label').textContent = 'Samples unavailable';
    controls();
  }
}
init();
