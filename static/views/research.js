import { html, useState, useEffect, useRef } from '../vendor/preact-htm.js';
import { api, useAsync, useStore, Loading, ErrorBox, Empty, Field, Select, Modal, ExtLink, CopyButton, toast, errMsg, nav, fmtDate, L } from '../ui.js';

const STRENGTH = { strong: ['Strong match', 'tone-good'], possible: ['Possible match', 'tone-info'], weak: ['Weak', 'tone-muted'] };
const STATUS = { candidate: 'Not reviewed', auto_saved: 'Auto-saved — unreviewed', saved: 'Saved', maybe: 'Maybe', rejected: 'Not this person' };
const FOUND_BY = { search: 'automatic search', ai: 'AI assistant', web: 'AI web search' };

// ------------------------------------------------------------------ start dialogs

export function ResearchButtons({ person, questions }) {
  const [open, setOpen] = useState(null);
  const s = useStore();
  return html`<span class="row wrap">
    <button onClick=${() => setOpen('auto')} title="Search the archives the app can query, check each result, and log every search">Research automatically</button>
    ${s.ai && s.ai.enabled && html`<button class="secondary ai-btn" onClick=${() => setOpen('ai')}>✧ AI research assistant</button>`}
    ${open === 'auto' && html`<${AutoDialog} person=${person} questions=${questions} onClose=${() => setOpen(null)} />`}
    ${open === 'ai' && html`<${AIDialog} person=${person} questions=${questions} onClose=${() => setOpen(null)} />`}
  </span>`;
}

function QuestionPick({ questions, value, onChange }) {
  return html`<${Field} label="Research question (optional)"><${Select} value=${value} onChange=${onChange} empty="General — find records about this person"
    options=${(questions || []).map((q) => [q.id, q.question])} /><//>`;
}

function AutoDialog({ person, questions, onClose }) {
  const s = useStore();
  const [q, setQ] = useState('');
  const [opts, setOpts] = useState({ max_queries: 12, auto_save: true });
  const [busy, setBusy] = useState(false);
  const { data: pl, error, loading } = useAsync(() => api.post(`/projects/${s.projectId}/research/plan`, { person_id: person.id, question_id: q || null, options: opts }),
    [q, opts.max_queries]);
  const start = async () => {
    setBusy(true);
    try {
      const r = await api.post(`/projects/${s.projectId}/research/runs`, { person_id: person.id, question_id: q || null, options: opts });
      onClose(); nav(`#/research/${r.id}`);
    } catch (x) { toast(errMsg(x), 'bad'); }
    setBusy(false);
  };
  return html`<${Modal} title=${`Research ${person.display_name} automatically`} onClose=${onClose} wide>
    <p class="small">The app runs these searches itself against archives with public search APIs, reads the item text where allowed, checks each
      result against what you know about ${person.display_name}, and logs every search — including ones with nothing relevant. No AI is used.
      It cannot search subscription or login-only sites; the best of those are listed at the end as manual next steps.</p>
    <${QuestionPick} questions=${questions} value=${q} onChange=${(v) => setQ(v || '')} />
    <div class="row wrap">
      <${Field} label="Maximum searches"><input inputmode="numeric" size="4" value=${opts.max_queries} onChange=${(e) => setOpts({ ...opts, max_queries: +e.target.value || 12 })} /><//>
      <label class="check"><input type="checkbox" checked=${opts.auto_save} onChange=${(e) => setOpts({ ...opts, auto_save: e.target.checked })} />
        Auto-save strong matches as sources (marked “unreviewed”)</label></div>
    <${ErrorBox} error=${error} />
    ${loading && !pl ? html`<${Loading} what="Planning" />` : pl && html`
      <h3>Planned searches (${pl.queries.length}${pl.dropped ? `, ${pl.dropped} more not run` : ''})</h3>
      ${pl.queries.length === 0 ? html`<p class="callout tone-warn">No archive the app can search covers this person's places and years.</p>` :
        html`<ol class="small plan-list">${pl.queries.map((x) => html`<li><strong>${x.label}</strong>: <code>${x.query.text}</code>
          ${x.query.year_from ? ` ${x.query.year_from}–${x.query.year_to}` : ''}${x.query.state ? ` · ${x.query.state}` : ''}<div class="muted">${x.reason}</div></li>`)}</ol>`}
      ${pl.skipped_archives.length > 0 && html`<p class="small muted">Not searched: ${pl.skipped_archives.map((x) => `${x.label} (${x.reason})`).join('; ')}.
        <a href="#/settings/archives" onClick=${onClose}>Archive settings</a></p>`}
      <p class="small muted">Archives are searched politely within their published rate limits, so a run can take a few minutes.</p>`}
    <div class="row end"><button class="secondary" onClick=${onClose}>Cancel</button>
      <button disabled=${busy || !pl || !pl.queries.length} onClick=${start}>${busy ? 'Starting…' : 'Start research'}</button></div>
  <//>`;
}

function AIDialog({ person, questions, onClose }) {
  const s = useStore();
  const [q, setQ] = useState('');
  const [opts, setOpts] = useState({ web_search: false, max_tool_calls: 16, max_steps: 10, max_web_searches: 5, auto_save: true });
  const [busy, setBusy] = useState(false);
  const { data: pv, error, loading } = useAsync(() => api.post(`/projects/${s.projectId}/research/ai/preview`,
    { person_id: person.id, question_id: q || null, options: opts }), [q, JSON.stringify(opts)]);
  const start = async () => {
    setBusy(true);
    try {
      const r = await api.post(`/projects/${s.projectId}/research/ai/runs`, { person_id: person.id, question_id: q || null, options: opts,
        confirmed_model: `${pv.selection.provider}:${pv.selection.model}` });
      onClose(); nav(`#/research/${r.id}`);
    } catch (x) { toast(errMsg(x), 'bad'); }
    setBusy(false);
  };
  const set = (k) => (e) => setOpts({ ...opts, [k]: e.target.type === 'checkbox' ? e.target.checked : (+e.target.value || opts[k]) });
  return html`<${Modal} title=${`AI research assistant — ${person.display_name}`} onClose=${onClose} wide>
    <${ErrorBox} error=${error} />
    ${loading && !pv ? html`<${Loading} />` : pv && html`
      <p class="small">${pv.notice}</p>
      <${QuestionPick} questions=${questions} value=${q} onChange=${(v) => setQ(v || '')} />
      <section class="panel subtle"><h3>Model and budget</h3>
        <p class="small">Runs on <strong>${pv.provider_label || '—'}</strong> · <code>${pv.selection.model || 'no model selected'}</code> (${pv.selection.source}). Change it in Settings → AI.</p>
        <div class="row wrap">
          <${Field} label="Max tool calls"><input inputmode="numeric" size="4" value=${opts.max_tool_calls} onChange=${set('max_tool_calls')} /><//>
          <${Field} label="Max model turns"><input inputmode="numeric" size="4" value=${opts.max_steps} onChange=${set('max_steps')} /><//></div>
        <label class="check"><input type="checkbox" checked=${opts.web_search} onChange=${set('web_search')} />
          Also let the AI search the open web (uses ${pv.provider_label || 'the provider'}'s web search; names, places and years are sent to it; billed separately)</label>
        ${opts.web_search && html`<${Field} label="Max web searches"><input inputmode="numeric" size="4" value=${opts.max_web_searches} onChange=${set('max_web_searches')} /><//>`}
        <label class="check"><input type="checkbox" checked=${opts.auto_save} onChange=${set('auto_save')} /> Auto-save strong matches whose quote the app could verify (marked “unreviewed”)</label>
        ${pv.compatibility.issues.map((i) => html`<p class="callout tone-bad small">${i}</p>`)}
        ${pv.compatibility.info_source && html`<p class="small muted">Model info: ${pv.compatibility.info_source}.</p>`}
      </section>
      <section class="panel subtle"><h3>What will be sent to ${pv.provider_label || 'the provider'}</h3>
        <ul class="small">${pv.sent.map((x) => html`<li>${x.label}</li>`)}</ul>
        <p class="small muted">Archives it can search: ${pv.archives.map((a) => a.label).join(', ') || 'none'}. Cost: ${pv.cost_note}.</p></section>
      ${pv.blockers.length > 0 && html`<div class="callout tone-warn"><ul>${pv.blockers.map((b) => html`<li>${b}</li>`)}</ul><a href="#/settings/ai" onClick=${onClose}>AI settings</a></div>`}
      <div class="row end"><button class="secondary" onClick=${onClose}>Cancel</button>
        <button disabled=${!pv.can_run || busy} onClick=${start}>${busy ? 'Starting…' : `Start (sends data to ${pv.provider_label || 'provider'})`}</button></div>`}
  <//>`;
}

// ------------------------------------------------------------------ hits

function SaveToClaim({ hit, onClose, onDone }) {
  const person = useAsync(() => api.get(`/persons/${hit.person_id}`), [hit.person_id]);
  const s = useStore();
  const [v, setV] = useState({ claim_id: '', stance: 'supports', identity: 'probable' });
  const save = async () => {
    try { await api.post(`/research/hits/${hit.id}`, { action: 'save', claim_id: v.claim_id || null, stance: v.claim_id ? v.stance : 'mentions', identity: v.identity }); onDone(); }
    catch (x) { toast(errMsg(x), 'bad'); }
  };
  const V = s.meta.vocab;
  return html`<${Modal} title="Save as a source" onClose=${onClose}>
    ${!person.data ? html`<${Loading} />` : html`<div class="stack">
      <${Field} label="Link it to a claim (optional)"><${Select} value=${v.claim_id} onChange=${(x) => setV({ ...v, claim_id: x || '' })} empty="General: “records found” for this person"
        options=${person.data.claims.filter((c) => c.value_text !== 'Records found by research runs').map((c) => [c.id, `${V.claim_types[c.claim_type]} ${c.date_text || ''} ${c.place_label || ''}`])} /><//>
      ${v.claim_id && html`<${Field} label="Stance"><${Select} value=${v.stance} onChange=${(x) => setV({ ...v, stance: x })} options=${V.stances} /><//>`}
      <${Field} label="Is it the same person?"><${Select} value=${v.identity} onChange=${(x) => setV({ ...v, identity: x })} options=${V.identity_match} /><//>
      <div class="row end"><button class="secondary" onClick=${onClose}>Cancel</button><button onClick=${save}>Save source</button></div></div>`}
  <//>`;
}

export function HitCard({ h, onChange }) {
  const [saving, setSaving] = useState(false);
  const act = async (action) => { try { await api.post(`/research/hits/${h.id}`, { action }); onChange(); } catch (x) { toast(errMsg(x), 'bad'); } };
  const [label, tone] = STRENGTH[h.strength] || STRENGTH.weak;
  return html`<article class=${'card hit ' + (h.status === 'rejected' ? 'rejected' : '')}>
    <div class="card-top"><div><h3>${h.url ? html`<${ExtLink} href=${h.url}>${h.title}<//>` : h.title}</h3>
      <div class="muted small">${[h.date_text, h.place_text, h.collection].filter(Boolean).join(' · ')} · found by ${FOUND_BY[h.found_by] || h.found_by}</div></div>
      <span class="rank" title="Orders results by how well they fit. Not the probability that this is your person.">${h.score} pts</span></div>
    <div class="badges"><span class=${'badge ' + tone}>${label}</span><span class=${'badge ' + (h.status === 'auto_saved' ? 'tone-warn' : 'tone-muted')}>${STATUS[h.status]}</span>
      ${h.quote_verified === 1 && html`<span class="badge tone-good">quote verified in text</span>`}${h.quote_verified === 0 && html`<span class="badge tone-bad">quote not verified</span>`}</div>
    ${h.context && html`<blockquote class="ocr small">${h.context}</blockquote>`}
    ${h.quote && h.quote !== h.context && html`<p class="small"><span class="muted">Quoted by the assistant:</span> “${h.quote}”</p>`}
    <ul class="small reasons">${(h.reasons || []).map((r) => html`<li>${r}</li>`)}</ul>
    ${h.status !== 'rejected' && html`<div class="row wrap">
      ${h.status !== 'saved' && html`<button class="small" onClick=${() => setSaving(true)}>${h.status === 'auto_saved' ? 'Keep & link to a fact' : 'Save as source'}</button>`}
      ${h.status === 'candidate' && html`<button class="small secondary" onClick=${() => act('maybe')}>Maybe</button>`}
      <button class="small secondary" onClick=${() => act('reject')}>Not this person</button>
      ${h.source_id && html`<a class="small" href=${`#/source/${h.source_id}`}>Open saved source</a>`}</div>`}
    ${saving && html`<${SaveToClaim} hit=${h} onClose=${() => setSaving(false)} onDone=${() => { setSaving(false); onChange(); }} />`}
  </article>`;
}

// ------------------------------------------------------------------ run page

export function ResearchRun({ id }) {
  const { data: r, error, loading, reload } = useAsync(() => api.get(`/research/runs/${id}`), [id]);
  const [filter, setFilter] = useState('good');
  const timer = useRef(null);
  useEffect(() => {
    clearInterval(timer.current);
    if (r && r.status === 'running') timer.current = setInterval(reload, 1500);
    return () => clearInterval(timer.current);
  }, [r && r.status]);
  if (loading && !r) return html`<div class="page"><${Loading} /></div>`;
  if (error) return html`<div class="page"><${ErrorBox} error=${error} retry=${reload} /></div>`;
  const sm = r.summary || {};
  const st = sm.stats || {};
  const hits = (r.hits || []).filter((h) => filter === 'all' || (filter === 'good' ? h.strength !== 'weak' || h.status !== 'candidate' : h.status === filter));
  const prog = r.progress || {};
  return html`<div class="page">
    <nav class="crumbs"><a href="#/research">Research</a> / run ${fmtDate(r.started_at)}</nav>
    <header class="page-head"><div><h1>${r.mode === 'ai' ? 'AI research run' : 'Automatic research run'}</h1>
      <p class="muted">${r.status}${r.mode === 'ai' ? ` · ${r.ai_provider} · ${r.ai_model}` : ''} · started ${new Date(r.started_at).toLocaleString()}
        ${r.person_id ? html` · <a href=${`#/person/${r.person_id}`}>open person</a>` : ''}</p></div>
      ${r.status === 'running' && html`<button class="secondary" onClick=${async () => { await api.post(`/research/runs/${r.id}/cancel`); reload(); }}>Cancel run</button>`}</header>
    ${r.status === 'running' && html`<div class="callout tone-info" role="status">${r.mode === 'ai' ? `Working… ${prog.tool_calls || 0} tool calls, ${prog.findings || 0} findings so far.` :
      `Searching… ${prog.done || 0} of ${prog.total || '?'} searches done${prog.current ? ` — now: ${prog.current}` : ''}.`} Archives are queried within their rate limits.</div>`}
    ${r.error && html`<div class="callout tone-bad">${r.error}</div>`}
    ${r.status !== 'running' && html`<section class="panel"><h2>Summary</h2>
      ${r.mode === 'ai' ? html`<p>${sm.assistant_summary || html`<span class="muted">The assistant did not write a final summary.</span>`}</p>
        ${(sm.next_steps || []).length > 0 && html`<h3>Assistant's suggested next steps</h3><ul>${sm.next_steps.map((x) => html`<li>${x}</li>`)}</ul>`}
        <p class="small muted">${st.searches || 0} archive searches · ${st.tool_calls || 0} tool calls · ${st.findings || 0} findings · ${st.auto_saved || 0} auto-saved ·
          ${st.web_sources_seen || 0} web sources seen · tokens in/out ${r.input_tokens ?? '?'} / ${r.output_tokens ?? '?'} · cost ${sm.cost_note || 'unknown'}</p>` :
        html`<p class="small">${st.queries_run || 0} searches run · ${st.results_returned || 0} results returned · ${st.checked || 0} checked ·
          <strong>${st.strong || 0} strong</strong> · ${st.possible || 0} possible · ${st.weak || 0} weak · ${st.auto_saved || 0} auto-saved · ${st.already_reviewed || 0} already reviewed earlier
          ${st.errors ? ` · ${st.errors} errors` : ''}</p>`}
      ${(sm.errors || []).length > 0 && html`<ul class="small">${sm.errors.map((x) => html`<li>${x}</li>`)}</ul>`}
      ${sm.note && html`<p class="small muted">${sm.note}</p>`}
      <p class="small">Every search is in the <a href=${`#/log?person=${r.person_id}`}>research log</a>, including searches with no relevant result.</p></section>`}

    <section class="panel"><div class="panel-head"><h2>Results (${(r.hits || []).length})</h2>
      <${Select} value=${filter} onChange=${(v) => setFilter(v)} options=${[['good', 'Matches & decided'], ['all', 'Everything checked'], ['auto_saved', 'Auto-saved (unreviewed)'],
        ['candidate', 'Not reviewed'], ['saved', 'Saved'], ['maybe', 'Maybe'], ['rejected', 'Not this person']]} /></div>
      ${hits.length === 0 ? html`<p class="muted">${r.status === 'running' ? 'Results will appear here.' : 'No results in this view.'}</p>` :
        html`<div class="lead-list">${hits.map((h) => h.status === 'rejected' || h.status === 'saved' ? html`<${HitCard} h=${h} onChange=${reload} />` : html`<${LeadCard} h=${h} onChange=${reload} />`)}</div>`}</section>

    ${r.mode === 'ai' && (r.steps || []).length > 0 && html`<section class="panel"><details><summary><h2 class="inline">What the assistant did (${r.steps.length} steps)</h2></summary>
      <ol class="small steps-log">${r.steps.map((x) => html`<li><span class="badge tone-muted">${x.kind}</span> ${x.text}</li>`)}</ol></details></section>`}
    ${r.mode !== 'ai' && (r.plan || {}).queries && html`<section class="panel"><details><summary><h2 class="inline">Searches planned (${r.plan.queries.length})</h2></summary>
      <ol class="small">${r.plan.queries.map((x) => html`<li>${x.label}: <code>${x.query.text}</code> ${x.query.year_from ? `${x.query.year_from}–${x.query.year_to}` : ''} ${x.query.state || ''} — ${x.reason}</li>`)}</ol>
      ${r.plan.skipped_archives.length > 0 && html`<p class="small muted">Not searched: ${r.plan.skipped_archives.map((x) => `${x.label} (${x.reason})`).join('; ')}</p>`}</details></section>`}

    ${(sm.manual_next || []).length > 0 && html`<section class="panel"><h2>Next: searches you'll need to run yourself</h2>
      <p class="small muted">These sites can't be searched by the app (subscription, login, or no public search API). Each has a suggested query.</p>
      <ul class="list">${sm.manual_next.map((m) => html`<li><div class="list-main"><strong><a href=${`#/resource/${m.collection_id}`}>${m.name}</a></strong> <span class="muted small">${m.provider}</span>
        <div class="small">${m.next_action.label}: <code>${m.query}</code>${m.variants.length ? ` · variants: ${m.variants.join(', ')}` : ''}</div></div>
        <${CopyButton} text=${m.query} small label="Copy query" /></li>`)}</ul></section>`}
  </div>`;
}

// ------------------------------------------------------------------ research home

export function ResearchHome() {
  const s = useStore();
  const runs = useAsync(() => api.get(`/projects/${s.projectId}/research/runs`), [s.projectId]);
  const review = useAsync(() => api.get(`/projects/${s.projectId}/research/review`), [s.projectId]);
  const people = useAsync(() => api.get(`/projects/${s.projectId}/persons`), [s.projectId]);
  const names = Object.fromEntries((people.data || []).map((p) => [p.id, p.display_name]));
  return html`<div class="page">
    <header class="page-head"><div><h1>Research</h1>
      <p class="lede">Automatic searches the app runs itself, and runs of the AI research assistant. Start one from a person's page.</p></div></header>
    <div class="callout tone-info small">The app can search archives with public search APIs (see Settings → Archives). It cannot log in to Ancestry, FamilySearch or other
      subscription sites; those searches are handed back to you with ready-made queries.</div>
    <section class="panel"><h2>Waiting for your review</h2>
      ${review.loading && !review.data ? html`<${Loading} />` : (review.data || []).length === 0 ? html`<p class="muted">Nothing to review.</p>` :
        html`<div class="hit-list">${review.data.map((h) => html`<div><p class="small muted">${h.person_name}</p><${HitCard} h=${h} onChange=${review.reload} /></div>`)}</div>`}</section>
    <section class="panel"><h2>Runs</h2>
      ${(runs.data || []).length === 0 ? html`<${Empty} title="No research runs yet">Open a person and choose “Research automatically”.<//>` :
        html`<div class="table-wrap"><table class="table"><thead><tr><th>Started</th><th>Person</th><th>Kind</th><th>Status</th><th>Found</th></tr></thead><tbody>
          ${runs.data.map((r) => { const st = (r.summary || {}).stats || {};
            return html`<tr><td><a href=${`#/research/${r.id}`}>${new Date(r.started_at).toLocaleString()}</a></td><td>${names[r.person_id] || '—'}</td>
              <td>${r.mode === 'ai' ? `AI (${r.ai_model})` : 'Automatic'}</td><td>${r.status}</td>
              <td>${r.mode === 'ai' ? `${st.findings || 0} findings` : `${st.strong || 0} strong, ${st.possible || 0} possible`}</td></tr>`; })}</tbody></table></div>`}</section>
  </div>`;
}

// ------------------------------------------------------------------ archive settings

export function ArchiveSettings() {
  const { data, error, loading, reload } = useAsync(() => api.get('/archives'), []);
  const [keys, setKeys] = useState({});
  const [results, setResults] = useState({});
  if (loading && !data) return html`<${Loading} />`;
  if (error) return html`<${ErrorBox} error=${error} retry=${reload} />`;
  const test = async (a) => {
    setResults({ ...results, [a.key]: { busy: true } });
    try { const r = await api.post(`/archives/${a.key}/test`); setResults({ ...results, [a.key]: { ok: true, detail: r.detail } }); }
    catch (x) { setResults({ ...results, [a.key]: { ok: false, detail: errMsg(x) } }); }
  };
  return html`<div class="stack">
    <p class="small">These archives publish search APIs that allow user-initiated automated searches. The app uses them for automatic research runs and for
      the AI research assistant, within each archive's rate limits. Keys are stored in your system keychain, never in exports or backups.</p>
    ${data.map((a) => html`<section class="panel"><div class="panel-head"><h3>${a.label}</h3>
      <label class="check"><input type="checkbox" checked=${a.enabled} onChange=${async (e) => { await api.patch(`/archives/${a.key}`, { enabled: e.target.checked }); reload(); }} /> Use in research runs</label></div>
      <p class="small">${a.provider} · ${a.record_kind}${a.coverage && a.coverage.countries ? ` · ${a.coverage.countries.join(', ')}` : ''}${a.coverage && a.coverage.from ? ` ${a.coverage.from}–${a.coverage.to || ''}` : ''}
        · up to ${a.max_per_minute} requests/minute${a.supports_text ? ' · reads item text' : ''}</p>
      <p class="small muted">${a.terms_note} <${ExtLink} href=${a.documentation_url}>API documentation<//></p>
      <p class="small">${a.verified_live ? html`<span class="badge tone-good">Tested against the live API ${a.verified_live}</span>` :
        html`<span class="badge tone-warn">Not yet tested live — use “Test connection” after adding your key</span>`}</p>
      ${(a.requires_key || a.optional_key) && html`<div class="stack">
        <p class="small">${a.has_key ? 'API key saved in the keychain.' : a.requires_key ? 'Needs a free API key.' : 'Works without a key; a free key is recommended.'} ${a.key_signup ? html`How to get one: ${a.key_signup}` : ''}</p>
        <form class="row wrap" onSubmit=${async (e) => { e.preventDefault(); try { await api.put(`/archives/${a.key}/key`, { api_key: keys[a.key] }); setKeys({ ...keys, [a.key]: '' }); reload(); toast('Key saved'); } catch (x) { toast(errMsg(x), 'bad'); } }}>
          <label class="sr-only" for=${'ak-' + a.key}>${a.label} API key</label>
          <input id=${'ak-' + a.key} type="password" autocomplete="off" value=${keys[a.key] || ''} onInput=${(e) => setKeys({ ...keys, [a.key]: e.target.value })} placeholder="Paste API key" />
          <button type="submit" disabled=${!keys[a.key]}>Save key</button>
          ${a.has_key && html`<button type="button" class="secondary" onClick=${async () => { await api.del(`/archives/${a.key}/key`); reload(); }}>Remove key</button>`}</form></div>`}
      <div class="row"><button class="small secondary" disabled=${a.requires_key && !a.has_key} onClick=${() => test(a)}>${results[a.key] && results[a.key].busy ? 'Testing…' : 'Test connection'}</button>
        ${results[a.key] && !results[a.key].busy && html`<span class=${'small ' + (results[a.key].ok ? '' : 'danger')}>${results[a.key].detail}</span>`}</div>
    </section>`)}
  </div>`;
}

// ------------------------------------------------------------------ simple yes / no lead card

const AGAINST = /\b(not|outside|does not|doesn't|different person|no |mismatch|but)\b/i;

function censusRows(h) {
  if (!(h.record_kind || '').includes('census')) return null;
  const t = h.context || '';
  const hh = t.split('Household on the same census form: ')[1];
  if (hh) return hh.replace(/ …$/, '').split(' | ');
  const sp = (h.snippet || '').split('Same page: ')[1];
  return sp ? sp.split('; ') : null;
}

export function LeadCard({ h, onChange, showPerson }) {
  const [linking, setLinking] = useState(false);
  const [busy, setBusy] = useState(false);
  const act = async (action, extra) => {
    setBusy(true);
    try { await api.post(`/research/hits/${h.id}`, { action, ...(extra || {}) }); onChange && onChange(); } catch (x) { toast(errMsg(x), 'bad'); }
    setBusy(false);
  };
  const NEARBY = 'Also named nearby';
  const reasons = (h.reasons || []).filter((r) => !r.startsWith(NEARBY));
  const nearby = (h.reasons || []).find((r) => r.startsWith(NEARBY));
  const pro = reasons.filter((r) => !AGAINST.test(r) && !r.startsWith('Not marked strong'));
  const con = reasons.filter((r) => AGAINST.test(r) && !r.startsWith('Not marked strong'));
  const note = reasons.find((r) => r.startsWith('Not marked strong'));
  const [label, tone] = STRENGTH[h.strength] || STRENGTH.weak;
  return html`<article class="card lead">
    ${showPerson && h.person_id && html`<p class="lead-person">Is this <a href=${`#/person/${h.person_id}`}>${h.person_name}</a>?</p>`}
    <h3 class="lead-title">${h.url ? html`<${ExtLink} href=${h.url}>${h.title}<//>` : h.title}</h3>
    <div class="muted small">${[h.date_text, h.place_text, h.collection].filter(Boolean).join(' · ')}
      <span class=${'badge ' + tone}>${label}</span>${h.status === 'auto_saved' ? html` <span class="badge tone-warn" title="Saved automatically as an unreviewed lead">auto-saved</span>` : ''}
      ${h.found_by !== 'search' ? html` <span class="badge tone-info">${FOUND_BY[h.found_by]}</span>` : ''}</div>
    ${censusRows(h) ? html`<div class="small"><span class="muted">${(h.record_kind || '').includes('return') ? 'Household on the census form:' : 'Lines on the same census page (machine-read):'}</span>
        <ul class="household">${censusRows(h).map((x) => html`<li>${x}</li>`)}</ul></div>`
      : h.context && html`<blockquote class="ocr small">${h.context}</blockquote>`}
    ${note && html`<p class="small muted">${note}</p>`}
    ${h.quote && h.quote !== h.context && html`<p class="small"><span class="muted">Quoted:</span> “${h.quote}” ${h.quote_verified === 1 ? html`<span class="badge tone-good">checked in text</span>` : h.quote_verified === 0 ? html`<span class="badge tone-bad">not found in text</span>` : ''}</p>`}
    <div class="lead-why small">
      ${pro.length > 0 && html`<div><strong class="good">Fits:</strong><ul>${pro.map((r) => html`<li>${r}</li>`)}</ul></div>`}
      ${con.length > 0 && html`<div><strong class="bad">Doesn't fit:</strong><ul>${con.map((r) => html`<li>${r}</li>`)}</ul></div>`}
    </div>
    ${nearby && html`<p class="small new-names"><strong>New names to look into:</strong> ${nearby.split(': ').slice(1).join(': ')}
      <span class="muted"> — same surname, named next to this person, not in your tree. Possibly relatives.</span></p>`}
    <div class="row wrap lead-actions">
      <button class="small" disabled=${busy} onClick=${() => act('save', { identity: 'probable' })}>Yes, it's them</button>
      <button class="small secondary" disabled=${busy} onClick=${() => act('reject')}>Not them</button>
      ${h.status !== 'maybe' && html`<button class="small secondary" disabled=${busy} onClick=${() => act('maybe')}>Not sure</button>`}
      <button class="small link" onClick=${() => setLinking(true)}>Save & link to a fact…</button>
    </div>
    ${linking && html`<${SaveToClaim} hit=${h} onClose=${() => setLinking(false)} onDone=${() => { setLinking(false); onChange && onChange(); }} />`}
  </article>`;
}
