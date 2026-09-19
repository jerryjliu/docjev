'use strict';
const $ = (id) => document.getElementById(id);
const palette = ['#9270df', '#ed9cbb', '#77bcb7', '#d8ae6d', '#7e9cca', '#a3b86d', '#b08fbc'];
const state = { demoSet: {id:'synthetic',label:'Synthetic test fixtures'}, task: 'classify', samples: [], rules: {}, selected: null, file: null, run: null, page: 1, busy: false, poll: null, rendered: '', previewId: '' };
const pretty = (name) => String(name).replaceAll('_', ' ').replace(/\b\w/g, (c) => c.toUpperCase());
const time = (ms) => ms < 1000 ? `${Math.round(ms)} ms` : `${(ms / 1000).toFixed(ms < 10000 ? 2 : 1)} s`;
function node(tag, className, text) { const n = document.createElement(tag); if (className) n.className = className; if (text != null) n.textContent = text; return n; }
function toast(message) { $('toast').textContent = message; $('toast').hidden = false; clearTimeout(toast.timer); toast.timer = setTimeout(() => { $('toast').hidden = true; }, 6000); }
function resetResults() {
  state.run = null; state.page = 1; state.rendered = ''; state.previewId = '';
  $('metrics-panel').hidden = true; $('result-downloads').hidden = true; $('page-strip').hidden = true;
  $('page-preview').hidden = true; $('preview-label').hidden = true;
  $('previous-page').disabled = true; $('next-page').disabled = true; $('page-info').textContent = 'Original document';
  const empty = node('div', 'result-empty');
  empty.append(node('div', 'result-symbol', '↗'));
  const title = node('h2', '', state.task === 'classify' ? 'A little intelligence. A lot of clarity.' : 'Find the documents inside.');
  title.id = 'result-heading'; empty.append(title);
  empty.append(node('p', '', state.task === 'classify' ? 'Run a document to see its category, the category probabilities, and measured speed.' : 'See where one document ends and the next begins. Even when they share the same category.'));
  const chips = node('div', 'empty-rule-chips');
  (state.rules[state.task]?.categories || []).slice(0, 5).forEach((rule) => chips.append(node('span', '', pretty(rule.id))));
  empty.append(chips, node('span', 'empty-footnote', 'YOUR RULES. JEV’S DECISION.'));
  $('result-content').replaceChildren(empty);
}
function sampleList() {
  const list = state.samples.filter((s) => s.task === state.task);
  $('sample-count').textContent = `${list.length} SAMPLES`;
  $('sample-list').replaceChildren();
  list.forEach((sample) => {
    const button = node('button', `sample-card${state.selected?.id === sample.id ? ' selected' : ''}`);
    button.type = 'button'; button.disabled = state.busy; button.title = sample.title;
    button.setAttribute('aria-pressed', String(state.selected?.id === sample.id));
    button.append(node('span', 'file-icon', sample.format));
    const text = node('span', 'sample-text'); text.append(node('strong', '', sample.title), node('small', '', sample.filename));
    button.append(text, node('span', 'sample-check', '✓'));
    button.addEventListener('click', () => selectSample(sample)); $('sample-list').append(button);
  });
  if (!list.length) $('sample-list').append(node('p', 'panel-intro', 'Upload a document to get started.'));
}
function showProvenance(sample) {
  const provenance = sample?.provenance;
  const provenanceKind = provenance?.kind || (state.demoSet.id === 'real' ? 'original' : 'synthetic');
  $('source-provenance').hidden = !sample;
  $('source-details').open = false;
  if (!sample) return;
  $('source-kind').textContent = provenanceKind === 'synthetic' ? 'SYNTHETIC TEST FIXTURE' : provenanceKind === 'excerpt' ? 'ORIGINAL DOCUMENT EXCERPT' : ['assembled', 'packet', 'concatenated'].includes(provenanceKind) ? 'PACKET OF ORIGINAL DOCUMENTS' : 'ORIGINAL PUBLIC DOCUMENT';
  const sources = provenance?.sources || [];
  $('source-details').hidden = !sources.length && !provenance?.note;
  $('source-links').replaceChildren();
  sources.forEach((source) => { const link = node('a', '', `${source.title} ↗`); link.href = source.url; link.target = '_blank'; link.rel = 'noopener noreferrer'; $('source-links').append(link); });
  $('source-note').textContent = provenance?.note || '';
  $('source-note').hidden = !provenance?.note;
}
function previewSource(name, pdfUrl) {
  $('document-title').textContent = name || 'Choose a document';
  $('document-format').textContent = (name?.split('.').at(-1) || 'PDF').toUpperCase();
  $('pdf-preview').hidden = !pdfUrl; $('preview-empty').hidden = !!pdfUrl;
  if (pdfUrl) $('pdf-preview').src = `${pdfUrl}#toolbar=0&navpanes=0&view=FitH`;
  else $('pdf-preview').removeAttribute('src');
}
function selectSample(sample) {
  if (state.busy) return;
  state.selected = sample; state.file = null; $('file-upload').value = ''; resetResults(); sampleList();
  previewSource(sample.filename, sample.format === 'PDF' ? `/api/samples/${encodeURIComponent(sample.id)}/pdf` : null); $('document-title').textContent = sample.title; showProvenance(sample);
  $('run-button').disabled = false;
}
function updateRuleCount() { $('rule-count').textContent = String(state.rules[state.task]?.categories.length || 0); }
function switchTask(task) {
  if (state.busy) return;
  state.task = task; state.selected = null; state.file = null; const real = state.demoSet.id === 'real';
  document.querySelectorAll('[data-task]').forEach((tab) => { tab.classList.toggle('active', tab.dataset.task === task); tab.setAttribute('aria-pressed', String(tab.dataset.task === task)); });
  $('hero-title').replaceChildren();
  $('hero-title').append(document.createTextNode(task === 'classify' ? 'Documents in.' : 'One packet.'), document.createElement('br'), node('span', '', task === 'classify' ? 'Decisions out.' : 'Every document.'));
  $('hero-description').replaceChildren(document.createTextNode(task === 'classify' ? real ? 'Organize financial reports, economic releases, and tax forms.' : 'Explore classification with synthetic test fixtures.' : real ? 'Recover the original documents inside a combined PDF.' : 'Explore splitting with synthetic test fixtures.'), document.createElement('br'), document.createTextNode(task === 'classify' ? 'Read with LiteParse. Classify with Jev.' : 'Read every page. Let Jev find the boundaries.'));
  $('tab-note').textContent = task === 'classify' ? 'One document. One category.' : 'Every page. Every boundary.';
  $('input-title').textContent = task === 'classify' ? real ? 'Public finance inbox' : 'The test document inbox' : real ? 'Finance & policy packet' : 'The test packet';
  $('input-description').textContent = task === 'classify' ? real ? 'Financial and regulatory originals.' : 'Generated examples for repeatable testing.' : real ? 'Original PDFs combined, with pages unchanged.' : 'Generated documents in one source file.';
  $('demo-set-label').textContent = state.demoSet.label;
  $('run-label').textContent = task === 'classify' ? 'Classify document' : 'Split document';
  updateRuleCount(); resetResults(); sampleList(); renderComparison();
  const sample = state.samples.find((s) => s.task === task);
  if (sample) selectSample(sample); else { previewSource(null, null); showProvenance(null); $('run-button').disabled = true; }
}
function setBusy(busy) {
  state.busy = busy; $('run-button').disabled = busy;
  $('run-label').textContent = busy ? 'Working…' : state.task === 'classify' ? 'Classify document' : 'Split document';
  ['edit-rules', 'file-upload', 'ocr-provider'].forEach((id) => { $(id).disabled = busy; });
  document.querySelectorAll('[data-task]').forEach((b) => { b.disabled = busy; }); sampleList();
}
function progress(run) {
  if (state.rendered !== run.status) {
    const view = node('div', 'progress-view'); view.append(node('div', 'progress-spinner'));
    const title = node('h2', '', run.stage); title.id = 'result-heading'; view.append(title);
    view.append(node('p', '', run.status === 'parsing' ? 'Preparing the canonical pages and reading their content.' : 'The document is ready. Jev is applying your rules to its content.'));
    const steps = node('div', 'progress-steps');
    ['Read the document', state.task === 'classify' ? 'Choose its category' : 'Find each document', 'Validate the result'].forEach((text, index) => {
      const current = ['parsing', 'queued'].includes(run.status) ? 0 : 1;
      const step = node('div', `progress-step ${index === current ? 'current' : index < current ? 'done' : ''}`);
      step.append(node('b', '', index < current ? '✓' : String(index + 1)), document.createTextNode(text)); steps.append(step);
    }); view.append(steps); const elapsed = node('div', 'progress-time'); elapsed.id = 'progress-time'; view.append(elapsed); $('result-content').replaceChildren(view); state.rendered = run.status;
  }
  if ($('result-heading')) $('result-heading').textContent = run.stage;
  if ($('progress-time')) $('progress-time').textContent = `${time(run.elapsed_ms)} elapsed · live run`;
}
function segmentFor(page) { return state.run?.result?.segments?.find((segment) => segment.pages.includes(page)); }
function segmentColor(segment) { const index = state.run?.result?.segments?.findIndex((s) => s.id === segment?.id) || 0; return palette[index % palette.length]; }
function showPage(number) {
  if (!state.run?.preview) return;
  state.page = number;
  const page = state.run.preview.pages.find((p) => p.number === number); if (!page) return;
  $('pdf-preview').hidden = true; $('preview-empty').hidden = true; $('page-preview').hidden = false; $('preview-label').hidden = false;
  $('page-preview').src = page.image; $('page-preview').alt = `Page ${number} of ${state.run.name}`;
  const segment = segmentFor(number);
  $('page-info').textContent = `Page ${number} / ${state.run.preview.pages.length}${segment ? ` · ${pretty(segment.category)}` : ''}`;
  $('previous-page').disabled = number <= 1; $('next-page').disabled = number >= state.run.preview.pages.length;
  document.querySelectorAll('.page-thumb').forEach((n) => { n.classList.toggle('active', Number(n.dataset.page) === number); n.setAttribute('aria-current', Number(n.dataset.page) === number ? 'page' : 'false'); });
  document.querySelectorAll('.segment-card').forEach((n) => n.classList.toggle('active', n.dataset.segment === segment?.id));
}
function displayPreview(run) {
  if (!run.preview) return;
  const signature = `${run.id}-${run.status === 'complete'}`;
  if (state.previewId === signature) return;
  state.previewId = signature; $('page-strip').replaceChildren(); $('page-strip').hidden = false;
  run.preview.pages.forEach((page) => {
    const segment = segmentFor(page.number);
    const boundary = segment && segment.pages[0] === page.number && page.number > 1;
    const button = node('button', `page-thumb${boundary ? ' boundary' : ''}`); button.dataset.page = String(page.number);
    button.setAttribute('aria-label', `View page ${page.number}${segment ? `, ${pretty(segment.category)}, ${segment.id}` : ''}`);
    if (segment) button.style.setProperty('--segment-color', segmentColor(segment));
    const img = node('img'); img.src = page.image; img.alt = ''; img.loading = 'lazy'; button.append(img, node('span', '', String(page.number)));
    button.addEventListener('click', () => showPage(page.number)); $('page-strip').append(button);
  }); showPage(state.page);
}
function showMetrics(result) {
  const m = result.metrics; if (!m) return;
  $('metrics-panel').hidden = false;
  $('metric-ocr').textContent = time(m.ocr_ms + m.conversion_ms);
  $('metric-decision').textContent = time(m.decision_ms);
  $('metric-total').textContent = time(m.total_ms);
  $('decision-metric-label').textContent = result.engine === 'jev' ? 'Jev decision' : 'LLM decision';
  $('cache-label').textContent = m.ocr_cache_hit ? 'OCR CACHE HIT' : 'FRESH OCR';
  $('metric-note').textContent = m.ocr_cache_hit ? 'OCR reused a cached result. Decision time is measured live. Full pipeline excludes preview rendering.' : 'Conversion + OCR, all decisions, and full processing time. Preview rendering is excluded.';
}
function warnings(result, container) {
  if (result.needs_review) container.append(node('p', 'review-note', 'Review suggested. Check the source and category probabilities.'));
  (result.warnings || []).forEach((warning) => container.append(node('p', 'warning-note', warning)));
}
function classification(result) {
  const fragment = document.createDocumentFragment();
  const eyebrow = node('p', 'result-eyebrow'); eyebrow.append(node('span', 'check', '✓'), document.createTextNode('CLASSIFICATION COMPLETE')); fragment.append(eyebrow);
  const card = node('div', 'category-card'); card.append(node('small', '', 'THIS DOCUMENT IS A'));
  const title = node('h2', '', pretty(result.category)); title.id = 'result-heading'; card.append(title);
  const probability = result.category_probability;
  card.append(node('div', 'score', probability == null ? `Decision from ${result.model}` : `${(probability * 100).toFixed(1)}% category probability`)); fragment.append(card);
  if (result.probabilities) {
    fragment.append(node('p', 'result-subtitle', 'CATEGORY PROBABILITIES'));
    const bars = node('div', 'distribution');
    Object.entries(result.probabilities).sort((a,b) => b[1] - a[1]).slice(0,6).forEach(([category, score]) => {
      const row = node('div', 'distribution-row'); const label = node('div', 'distribution-label');
      label.append(node('span', '', pretty(category)), node('small', '', `${(score * 100).toFixed(1)}%`));
      const track = node('div', 'distribution-track'); const fill = node('i'); fill.style.width = `${Math.max(0, Math.min(100, score * 100))}%`; track.append(fill); row.append(label, track); bars.append(row);
    }); fragment.append(bars, node('p', 'score-note', 'Native Jev scores; not a guarantee of correctness.'));
  }
  warnings(result, fragment); $('result-content').replaceChildren(fragment);
}
function splitting(result) {
  const fragment = document.createDocumentFragment();
  const eyebrow = node('p', 'result-eyebrow'); eyebrow.append(node('span', 'check', '✓'), document.createTextNode('SPLITTING COMPLETE')); fragment.append(eyebrow);
  const title = node('h2', 'split-title', `${result.segments.length} documents found.`); title.id = 'result-heading'; fragment.append(title);
  fragment.append(node('p', 'split-summary', `${result.document.page_count} pages accounted for. Select a segment to inspect it.`));
  const list = node('div', 'segments-list');
  result.segments.forEach((segment, index) => {
    if (index > 0 && result.segments[index - 1].category === segment.category) list.append(node('p', 'segment-boundary-label', 'SAME CATEGORY · SEPARATE DOCUMENT'));
    const card = node('div', 'segment-card'); card.setAttribute('role', 'button'); card.tabIndex = 0; card.dataset.segment = segment.id; card.style.setProperty('--segment-color', palette[index % palette.length]);
    card.setAttribute('aria-label', `${pretty(segment.category)}, segment ${index + 1}, pages ${segment.pages.join(', ')}`);
    card.append(node('span', 'segment-number', String(index + 1).padStart(2,'0')));
    const label = node('div'); label.append(node('strong', '', pretty(segment.category)));
    const pages = segment.pages.length === 1 ? `Page ${segment.pages[0]}` : `Pages ${segment.pages[0]}–${segment.pages.at(-1)}`;
    label.append(node('small', '', `${pages}${segment.needs_review ? ' · review suggested' : ''}`)); card.append(label);
    const download = state.run.downloads.find((d) => d.segment_id === segment.id);
    if (download) { const link = node('a', 'segment-download', '↓'); link.href = `${download.url}?download=true`; link.title = `Download ${pretty(segment.category)} PDF`; link.addEventListener('click',(event) => event.stopPropagation()); card.append(link); }
    card.addEventListener('click', () => showPage(segment.pages[0])); card.addEventListener('keydown', (event) => { if (event.target === card && ['Enter',' '].includes(event.key)) { event.preventDefault(); showPage(segment.pages[0]); } }); list.append(card);
  }); fragment.append(list); warnings(result,fragment); $('result-content').replaceChildren(fragment);
}
function complete(run) {
  if (state.rendered === 'complete') return;
  state.rendered = 'complete'; run.result.task === 'classify' ? classification(run.result) : splitting(run.result);
  showMetrics(run.result); $('result-downloads').replaceChildren(); $('result-downloads').hidden = false;
  run.downloads.filter((d) => d.kind === 'json').forEach((download) => { const a = node('a', 'download-link', '↓ Result JSON'); a.href = `${download.url}?download=true`; $('result-downloads').append(a); });
  if (run.preview) { const a = node('a', 'download-link', '↗ Source PDF'); a.href = run.preview.pdf; a.target = '_blank'; a.rel = 'noopener'; $('result-downloads').append(a); }
  setBusy(false); showPage(state.page);
}
function showError(message) {
  const view = node('div', 'error-view'); const heading = node('h2', '', 'This run needs attention.'); heading.id = 'result-heading';
  view.append(heading, node('p','',message), node('p','score-note','No prediction was substituted. Resolve the issue, then run the document again.')); $('result-content').replaceChildren(view); setBusy(false);
}
async function pollRun(id) {
  try {
    const response = await fetch(`/api/runs/${encodeURIComponent(id)}`); if (!response.ok) throw new Error('The local server could not return this run.');
    const run = await response.json(); state.run = run; displayPreview(run);
    if (run.status === 'complete') { complete(run); return; }
    if (run.status === 'error') { showError(run.error); return; }
    progress(run); state.poll = setTimeout(() => pollRun(id), 350);
  } catch (error) { showError(error.message); }
}
async function startRun() {
  if (state.busy || (!state.selected && !state.file)) return;
  resetResults(); setBusy(true); progress({status:'queued',stage:'Starting the run',elapsed_ms:0});
  const form = new FormData(); form.append('task', state.task); form.append('rules', JSON.stringify(state.rules[state.task]));
  if (state.file) form.append('file',state.file); else form.append('sample_id', state.selected.id);
  const mode = $('ocr-provider').value; form.append('ocr', mode === 'liteparse' ? 'liteparse' : 'llamaparse'); form.append('tier', mode === 'liteparse' ? 'agentic' : mode);
  try {
    const response = await fetch('/api/runs',{method:'POST',body:form}); const data = await response.json();
    if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Please check your document and category rules.');
    state.run = data; await pollRun(data.id);
  } catch(error) { showError(error.message); }
}
function addRuleRow(rule = {id:'',description:''}) {
  const row = node('div','rule-row'); const id = node('input'); id.value = rule.id; id.placeholder = 'category_id'; id.setAttribute('aria-label','Category ID'); id.required = true; id.pattern = '[a-z][a-z0-9_]*';
  const description = node('textarea'); description.value = rule.description; description.placeholder = 'Describe the documents that belong here…'; description.setAttribute('aria-label', `${pretty(rule.id || 'New category')} description`); description.rows = 2; description.required = true;
  const remove = node('button','', '×'); remove.type='button'; remove.setAttribute('aria-label',`Remove ${pretty(rule.id || 'category')}`); remove.addEventListener('click',()=>row.remove());
  if (rule.id === 'other') { id.readOnly = true; remove.disabled = true; } row.append(id,description,remove); $('rules-list').append(row);
}
function openRules() {
  const rules = state.rules[state.task]; if (!rules) return;
  $('rules-list').replaceChildren(); rules.categories.forEach(addRuleRow); $('rule-instructions').value = rules.instructions || '';
  $('split-instructions').value = rules.splitting_instructions || ''; $('split-instructions-row').hidden = state.task !== 'split'; $('rules-error').textContent = ''; $('rules-dialog').showModal();
}
$('rules-form').addEventListener('submit',(event) => {
  event.preventDefault(); const categories = Array.from(document.querySelectorAll('.rule-row')).map((row) => ({id:row.querySelector('input').value.trim(),description:row.querySelector('textarea').value.trim()}));
  if (new Set(categories.map((c)=>c.id)).size !== categories.length) { $('rules-error').textContent = 'Each category needs a unique ID.'; return; }
  if (!categories.length || categories.length > 255) { $('rules-error').textContent = 'Use between 1 and 255 categories.'; return; }
  state.rules[state.task] = {schema_version:'1',categories,instructions:$('rule-instructions').value.trim(),splitting_instructions:$('split-instructions').value.trim()};
  $('rules-dialog').close(); updateRuleCount(); resetResults(); toast('Rules saved for the next run.');
});
$('file-upload').addEventListener('change',(event)=>{
  const file=event.target.files[0]; if(!file) return;
  if(file.size>30*1024*1024) {toast('Please choose a document smaller than 30 MB.');event.target.value='';return;}
  if(state.objectUrl) URL.revokeObjectURL(state.objectUrl);
  state.file=file; state.selected=null; resetResults(); sampleList(); state.objectUrl=file.name.toLowerCase().endsWith('.pdf')?URL.createObjectURL(file):null;
  previewSource(file.name,state.objectUrl);showProvenance(null);$('run-button').disabled=false;
});
$('ocr-provider').addEventListener('change',()=>{$('privacy-note').textContent=$('ocr-provider').value==='liteparse'?'OCR runs locally. Page text is sent to Jev.':'LlamaParse reads the document. Jev receives its text.';});
$('run-button').addEventListener('click',startRun);$('edit-rules').addEventListener('click',openRules);$('close-rules').addEventListener('click',()=>$('rules-dialog').close());$('add-rule').addEventListener('click',()=>addRuleRow());
$('previous-page').addEventListener('click',()=>showPage(state.page-1));$('next-page').addEventListener('click',()=>showPage(state.page+1));
document.querySelectorAll('[data-task]').forEach((tab)=>tab.addEventListener('click',()=>switchTask(tab.dataset.task)));
function renderComparison() {
  const groups = (state.comparison?.groups || []).filter((group) => group.task === state.task && group.concurrency === 1 && Number.isFinite(group.decision_p50_ms));
  const jev = groups.find((group) => group.engine === 'jev' && groups.some((other) => other.engine !== 'jev' && other.scope === group.scope));
  const baseline = jev && groups.find((group) => group.engine !== 'jev' && group.scope === jev.scope);
  if (!jev || !baseline) { $('comparison-panel').hidden = true; return; }
  $('comparison-panel').hidden = false; $('comparison-rows').replaceChildren();
  $('comparison-eyebrow').textContent = state.comparison.demo_set === 'real' ? 'REAL-DOCUMENT PILOT · SAVED RUNS' : 'SYNTHETIC EVALUATION · SAVED RUNS';
  const max = Math.max(jev.decision_p50_ms, baseline.decision_p50_ms, 1);
  [jev, baseline].forEach((group) => {
    const row = node('div','comparison-row');
    const label = node('div','comparison-model'); label.append(node('strong','',group.engine === 'jev' ? 'Jev' : 'Small LLM baseline'),node('span','',group.model));
    const meter = node('div','comparison-meter'); const fill = node('i',group.engine === 'jev' ? 'jev-meter' : ''); fill.style.width = `${group.decision_p50_ms / max * 100}%`; meter.append(fill);
    const timing = node('div','comparison-time'); timing.append(node('strong','',time(group.decision_p50_ms)),node('span','','median decision time'));
    const score = node('div','comparison-quality'); const quality = state.task === 'classify' ? group.accuracy : group.packet_exact_match;
    const qualityLabel = Number.isFinite(quality) ? group.planned_unique <= 5 ? `${Math.round(quality * group.planned_unique)}/${group.planned_unique}` : `${(quality * 100).toFixed(0)}%` : '—';
    score.append(node('strong','',qualityLabel),node('span','',state.task === 'classify' ? 'documents correct' : 'packets exactly correct'));
    row.append(label,meter,timing,score);$('comparison-rows').append(row);
  });
  $('comparison-scope').textContent = `${jev.planned_unique} ${state.comparison.demo_set === 'real' ? 'original ' : 'synthetic '}${state.task === 'classify' ? 'document' : 'packet'}${jev.planned_unique === 1 ? '' : 's'} · ${jev.latency_samples} Jev timed runs · concurrency 1`;
  $('comparison-note').textContent = `${state.comparison.dataset_label || 'Saved evaluation'}, separate from the live run above. Scope: ${pretty(jev.scope)}. Jev: ${jev.planned_unique} unique inputs / ${jev.latency_samples} timed completions; baseline: ${baseline.planned_unique} / ${baseline.latency_samples}. Decision times exclude OCR. Results describe this dataset and do not establish general production accuracy.`;
}
async function init(){
  try{const response=await fetch('/api/samples');if(!response.ok)throw new Error('The local server could not load the samples.');const data=await response.json();state.samples=data.samples;state.rules=data.rules;state.demoSet=data.demo_set || state.demoSet;switchTask('classify');
    const comparison = await fetch('/api/comparison'); if (comparison.ok) { state.comparison = await comparison.json(); renderComparison(); }}
  catch(error){toast(error.message);$('run-button').disabled=true;}
}
init();
