import { html, useState, useEffect } from '../vendor/preact-htm.js';
import { api, useAsync, useStore, store, Loading, ErrorBox, Empty, Badges, Field, Select, CheckboxGroup, ExtLink, CopyButton,
  L, years, fmtDate, toast, errMsg, safeStorage } from '../ui.js';
import { LogEntryForm } from './log.js';

const GROUPS = [
  ['match', 'Coverage matches your filters'],
  ['partial', 'Partly matches'],
  ['unknown', 'Coverage unknown — may still be relevant'],
  ['guidance', 'Research guidance & directories'],
];

function loadFilters() {
  try { return JSON.parse(safeStorage('kc.explorer') || '{}'); } catch (e) { return {}; }
}

export function Explorer({ params }) {
  const s = useStore();
  const vocab = s.meta.vocab;
  const [f, setF] = useState(() => ({ q: params.get('q') || '', ...loadFilters(), ...(params.get('q') ? { q: params.get('q') } : {}) }));
  const [res, setRes] = useState(null);
  const [err, setErr] = useState(null);
  const [showFilters, setShowFilters] = useState(false);
  const set = (k) => (v) => setF((o) => ({ ...o, [k]: v }));
  useEffect(() => {
    safeStorage('kc.explorer', JSON.stringify({ ...f, q: '' }));
    const h = setTimeout(() => {
      const body = { ...f, project_id: s.projectId, year_from: f.year_from ? +f.year_from : null, year_to: f.year_to ? +f.year_to : null };
      api.post('/directory/search', body).then((r) => { setRes(r); setErr(null); }, setErr);
    }, 200);
    return () => clearTimeout(h);
  }, [JSON.stringify(f), s.projectId]);

  const toggleSave = async (c) => {
    try { await api.post(`/projects/${s.projectId}/bookmarks/toggle`, { collection_id: c.id }); setF((o) => ({ ...o })); }
    catch (e) { toast(errMsg(e), 'bad'); }
  };
  const activeCount = ['country', 'region', 'county', 'year_from', 'year_to', 'access', 'remote_only', 'saved_only'].filter((k) => f[k]).length
    + (f.record_types || []).length + (f.capabilities || []).length + (f.entry_kinds || []).length + (f.verification || []).length;

  return html`<div class="page">
    <header class="page-head"><div><h1>Resources & collections</h1>
      <p class="lede">Searches <strong>this app's curated directory</strong> — not the providers' records. Use a resource's page to open the provider's own search.</p></div>
      <a class="button secondary" href="#/pathways">Research pathways</a></header>
    <div class="explorer">
      <aside class=${'filters' + (showFilters ? ' open' : '')} aria-label="Filters">
        <${Field} label="Place: country"><input value=${f.country || ''} onInput=${(e) => set('country')(e.target.value)} placeholder="United States" /><//>
        <${Field} label="State / province / region"><input value=${f.region || ''} onInput=${(e) => set('region')(e.target.value)} placeholder="Massachusetts" /><//>
        <${Field} label="County"><input value=${f.county || ''} onInput=${(e) => set('county')(e.target.value)} /><//>
        <div class="row tight"><${Field} label="From year"><input inputmode="numeric" value=${f.year_from || ''} onInput=${(e) => set('year_from')(e.target.value.replace(/\D/g, ''))} /><//>
          <${Field} label="To year"><input inputmode="numeric" value=${f.year_to || ''} onInput=${(e) => set('year_to')(e.target.value.replace(/\D/g, ''))} /><//></div>
        <${Field} label="Record type" hint="Hold Ctrl/⌘ to pick several">
          <select multiple size="6" onChange=${(e) => set('record_types')([...e.target.selectedOptions].map((o) => o.value))}>
            ${vocab.record_type_groups.map((g) => html`<optgroup label=${g.label}>${g.types.map((t) => html`<option value=${t.key} selected=${(f.record_types || []).includes(t.key)}>${t.label}</option>`)}</optgroup>`)}
          </select><//>
        <${Field} label="Access" hint="Narrows the list; hidden sources are counted, not lost">
          <${Select} value=${f.access} onChange=${set('access')} empty="Any access" options=${{ free: 'Free to search', free_or_account: 'Free or free account', my_access: 'Free + my subscriptions' }} /><//>
        <label class="check"><input type="checkbox" checked=${!!f.remote_only} onChange=${(e) => set('remote_only')(e.target.checked)} /> Remote access only</label>
        <label class="check"><input type="checkbox" checked=${!!f.saved_only} onChange=${(e) => set('saved_only')(e.target.checked)} /> Saved resources only</label>
        <${CheckboxGroup} legend="How it can be searched" options=${vocab.search_capabilities} value=${f.capabilities} onChange=${set('capabilities')} />
        <${CheckboxGroup} legend="Kind of entry" options=${vocab.entry_kinds} value=${f.entry_kinds} onChange=${set('entry_kinds')} />
        <${CheckboxGroup} legend="Verification" options=${vocab.verification_statuses} value=${f.verification} onChange=${set('verification')} />
        <button class="secondary small" onClick=${() => setF({ q: f.q })}>Clear filters</button>
      </aside>
      <section class="results">
        <div class="searchbar">
          <label class="sr-only" for="dir-q">Search the directory</label>
          <input id="dir-q" type="search" placeholder="Search directory: name, place, record type, terminology…" value=${f.q} onInput=${(e) => set('q')(e.target.value)} />
          <button class="secondary filters-toggle" aria-expanded=${showFilters} onClick=${() => setShowFilters(!showFilters)}>Filters${activeCount ? ` (${activeCount})` : ''}</button>
        </div>
        <${ErrorBox} error=${err} />
        ${!res ? html`<${Loading} />` : html`
          <p class="muted small" role="status">${res.total} directory entries${activeCount ? ' match your filters' : ''}.</p>
          ${res.hidden_by_preferences.length > 0 && html`<div class="callout tone-info">
            ${res.hidden_by_preferences.length} more ${res.hidden_by_preferences.length === 1 ? 'entry is' : 'entries are'} hidden by your access filters
            (e.g. ${res.hidden_by_preferences.slice(0, 3).map((h) => h.name).join('; ')}). <button class="link" onClick=${() => setF((o) => ({ ...o, access: null, remote_only: false }))}>Show them</button></div>`}
          ${res.total === 0 && html`<${Empty} title="No entries match">Try fewer filters. The directory is a starting set, not a complete list — check the FamilySearch Research Wiki for the place.<//>`}
          ${GROUPS.map(([k, label]) => res.groups[k] && res.groups[k].length ? html`<section class="result-group">
            <h2 class="group-title">${k === 'match' && !activeCount && !f.q ? 'Directory entries' : label} <span class="muted">(${res.groups[k].length})</span></h2>
            ${k === 'unknown' && html`<p class="muted small">The directory does not record full coverage for these. That is not evidence they lack your place or years.</p>`}
            <div class="cards">${res.groups[k].map((c) => html`<${ResourceCard} c=${c} onSave=${() => toggleSave(c)} />`)}</div></section>` : null)}
        `}
      </section>
    </div></div>`;
}

function ResourceCard({ c, onSave }) {
  const cv = c.coverage || {};
  return html`<article class="card resource-card">
    <div class="card-top"><div>
      <h3><a href=${`#/resource/${c.id}`}>${c.name}</a></h3>
      <div class="muted small">${c.provider_name} · ${L('entry_kinds', c.entry_kind)}${c.repository_type ? ' · ' + L('repository_types', c.repository_type) : ''}</div></div>
      <button class=${'icon save' + (c.saved ? ' on' : '')} aria-pressed=${!!c.saved} aria-label=${(c.saved ? 'Unsave ' : 'Save ') + c.name} onClick=${onSave}>${c.saved ? '★' : '☆'}</button></div>
    <${Badges} list=${c.badges} />
    <p class="small clamp">${c.description}</p>
    ${(cv.geo_why || cv.dates_why) && html`<p class="small coverage-why">${[cv.geo !== 'match' || cv.geo_why !== 'No place specified' ? cv.geo_why : null, cv.dates_why !== 'No years specified' ? cv.dates_why : null].filter(Boolean).join(' · ')}</p>`}
    <div class="row"><a class="button small secondary" href=${`#/resource/${c.id}`}>Details</a><${ExtLink} href=${c.search_url || c.url} cls="small">Open provider site<//></div>
  </article>`;
}

function AccessTable({ c }) {
  const row = (label, xs) => html`<tr><th scope="row">${label}</th><td>${(xs || []).length ? xs.map((x) => L('access', x)).join(' · ') : 'Not applicable / unknown'}</td></tr>`;
  return html`<table class="kv"><tbody>${row('Searching', c.access_search)}${row('Viewing images', c.access_images)}${row('Obtaining copies', c.access_copies)}</tbody></table>
    ${c.access_notes && html`<p class="small">${c.access_notes}</p>`}`;
}

export function ProviderSearchPanel({ c, defaultQuery }) {
  const [q, setQ] = useState(defaultQuery || {});
  const [link, setLink] = useState(null);
  useEffect(() => { api.post(`/directory/collections/${c.id}/search-link`, q).then(setLink, () => setLink(null)); }, [JSON.stringify(q)]);
  const text = q.q || [q.given, q.surname].filter(Boolean).join(' ');
  return html`<div class="panel subtle">
    <h3>Open provider search</h3>
    <p class="small muted">This opens <strong>${c.provider_name || 'the provider'}</strong>'s own website. It does not search from this app.</p>
    <div class="row wrap">
      <${Field} label="Given name"><input value=${q.given || ''} onInput=${(e) => setQ({ ...q, given: e.target.value })} /><//>
      <${Field} label="Surname"><input value=${q.surname || ''} onInput=${(e) => setQ({ ...q, surname: e.target.value })} /><//>
      <${Field} label="From"><input inputmode="numeric" size="5" value=${q.year_from || ''} onInput=${(e) => setQ({ ...q, year_from: e.target.value })} /><//>
      <${Field} label="To"><input inputmode="numeric" size="5" value=${q.year_to || ''} onInput=${(e) => setQ({ ...q, year_to: e.target.value })} /><//>
      ${(c.search_url_template || '').includes('{state}') && html`<${Field} label="U.S. state"><input value=${q.state || ''} onInput=${(e) => setQ({ ...q, state: e.target.value })} /><//>`}
    </div>
    ${link && html`<p class="small">${link.note}</p>
      <div class="row"><${ExtLink} href=${link.url} cls="button">${link.prefilled ? 'Open provider search (pre-filled)' : 'Open provider search page'}<//>
      ${text && html`<${CopyButton} text=${[text, q.year_from && q.year_to ? `${q.year_from}-${q.year_to}` : ''].filter(Boolean).join(' ')} label="Copy query" />`}</div>`}
  </div>`;
}

export function LiveSearchPanel({ c, defaultQuery }) {
  const adapter = (store.meta.adapters || []).find((a) => a.key === c.adapter_key);
  const [q, setQ] = useState({ q: '', ...defaultQuery });
  const [res, setRes] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  if (!adapter) return null;
  const run = async (e) => {
    e && e.preventDefault();
    setBusy(true); setErr(null);
    try { setRes(await api.post(`/integrations/${adapter.key}/search`, q)); } catch (x) { setErr(x); }
    setBusy(false);
  };
  return html`<div class="panel subtle">
    <h3>Live search: ${adapter.label}</h3>
    <p class="small muted">Retrieves results from the provider's documented public API. ${adapter.terms_note} Responses often take 20–60 seconds.</p>
    <form class="row wrap" onSubmit=${run}>
      <${Field} label="Words or name"><input required value=${q.q} onInput=${(e) => setQ({ ...q, q: e.target.value })} /><//>
      <${Field} label="From"><input inputmode="numeric" size="5" value=${q.year_from || ''} onInput=${(e) => setQ({ ...q, year_from: e.target.value })} /><//>
      <${Field} label="To"><input inputmode="numeric" size="5" value=${q.year_to || ''} onInput=${(e) => setQ({ ...q, year_to: e.target.value })} /><//>
      <${Field} label="U.S. state"><input value=${q.state || ''} onInput=${(e) => setQ({ ...q, state: e.target.value })} /><//>
      <button type="submit" disabled=${busy}>${busy ? 'Searching… (can take up to a minute)' : 'Search'}</button>
    </form>
    <${ErrorBox} error=${err} />
    ${res && html`<div aria-live="polite">
      <p class="small">${res.total != null ? `${res.total} results` : 'Results'} · page ${res.page} · via ${res.retrieved_via}. <${ExtLink} href=${res.query_url}>Same search on loc.gov<//></p>
      ${res.items.length === 0 ? html`<p>No results. A miss in OCR text does not mean the person was never mentioned — try spelling variants and nearby years.</p>` :
        html`<ol class="live-results">${res.items.map((it) => html`<li><${ExtLink} href=${it.url}>${it.title}<//>
          <div class="muted small">${it.date}${it.location ? ' · ' + it.location : ''}</div>
          ${it.snippet && html`<p class="small ocr">“${it.snippet}” <span class="muted">(${it.ocr_note})</span></p>`}</li>`)}</ol>`}
    </div>`}
  </div>`;
}

export function ResourceDetail({ id }) {
  const s = useStore();
  const { data: c, error, loading, reload } = useAsync(() => api.get(`/directory/collections/${id}`), [id]);
  const [logging, setLogging] = useState(false);
  if (loading && !c) return html`<div class="page"><${Loading} /></div>`;
  if (error) return html`<div class="page"><${ErrorBox} error=${error} retry=${reload} /></div>`;
  const V = s.meta.vocab;
  const save = async () => { await api.post(`/projects/${s.projectId}/bookmarks/toggle`, { collection_id: c.id }); toast('Saved list updated'); };
  return html`<div class="page">
    <nav class="crumbs"><a href="#/explore">Resources</a> / ${c.provider_name}</nav>
    <header class="page-head"><div><h1>${c.name}</h1>
      <p class="muted">${c.provider_name} · ${L('entry_kinds', c.entry_kind)}${c.repository_type ? ' · ' + L('repository_types', c.repository_type) : ''}${c.archived ? ' · ARCHIVED' : ''}</p>
      <${Badges} list=${c.badges} /></div>
      <div class="row wrap">${s.projectId && html`<button class="secondary" onClick=${save}>Save / unsave</button>`}
        ${s.projectId && html`<button onClick=${() => setLogging(true)}>Log a search here</button>`}
        <a class="button secondary" href=${`#/directory/edit/${c.id}`}>Edit entry</a></div></header>
    <p class="lede">${c.description}</p>
    <div class="grid-2">
      <section class="panel"><h2>Coverage</h2>
        <h3>Places</h3>${c.geo_scope === 'worldwide' ? html`<p>Not limited to one place (coverage by place not itemised).</p>` :
          (c.geo || []).length ? html`<ul>${c.geo.map((g) => html`<li>${[g.municipality, g.county && g.county + (g.country === 'United States' ? ' County' : ''), g.region, g.country].filter(Boolean).join(', ')}${g.historical_jurisdiction ? ` (historically ${g.historical_jurisdiction})` : ''}</li>`)}</ul>` :
          html`<p class="muted">Not recorded — unknown, not absent.</p>`}
        <h3>Dates</h3>${(c.dates || []).length ? html`<ul>${c.dates.map((r) => html`<li>${years(r.from, r.to ?? 'present')}${r.label ? ' — ' + r.label : ''}</li>`)}</ul>` : html`<p class="muted">Not recorded — unknown, not absent.</p>`}
        ${(c.date_gaps || []).length > 0 && html`<h3>Known gaps</h3><ul>${c.date_gaps.map((r) => html`<li>${years(r.from, r.to)}${r.label ? ' — ' + r.label : ''}</li>`)}</ul>`}
        <h3>Record types</h3><p>${(c.record_types || []).map((r) => L('record_types', r)).join(' · ') || html`<span class="muted">Not recorded</span>`}</p>
        ${(c.languages || []).length > 0 && html`<h3>Languages</h3><p>${c.languages.join(', ')}</p>`}
        ${(c.terminology || []).length > 0 && html`<h3>Useful terms</h3><p>${c.terminology.join(' · ')}</p>`}
      </section>
      <section class="panel"><h2>Access & how to search</h2>
        <${AccessTable} c=${c} />
        <h3>Search methods</h3><p>${(c.capabilities || []).map((x) => V.search_capabilities[x]).join(' · ') || 'Not recorded'}</p>
        <h3>Evidence forms</h3><p>${(c.evidence_forms || []).map((x) => V.evidence_forms[x]).join(' · ') || 'Not recorded'}</p>
        <h3>Integration</h3><p>${V.integration_methods[c.integration_method]}${c.search_link_notes ? html`<br /><span class="small">${c.search_link_notes}</span>` : ''}</p>
        <h3>Rights & reuse</h3><p>${c.rights_notes || html`<span class="muted">Unknown — check the provider's terms. Free viewing does not imply permission to bulk download or redistribute.</span>`}</p>
      </section>
    </div>
    ${c.limitations && html`<div class="callout tone-warn"><strong>Known limitations:</strong> ${c.limitations}</div>`}
    <${ProviderSearchPanel} c=${c} />
    <${LiveSearchPanel} c=${c} />
    <section class="panel"><h2>Verification</h2>
      <table class="kv"><tbody>
        <tr><th scope="row">Status</th><td>${V.verification_statuses[c.verification_status]}</td></tr>
        <tr><th scope="row">Last verified</th><td>${c.last_verified || 'Never'}</td></tr>
        <tr><th scope="row">Source</th><td>${c.verification_source || '—'}</td></tr>
        <tr><th scope="row">Link health</th><td>${c.link_health}${c.link_checked_at ? ` (checked ${fmtDate(c.link_checked_at)})` : ''}</td></tr>
        <tr><th scope="row">Official URL</th><td><${ExtLink} href=${c.url}>${c.url}<//></td></tr>
      </tbody></table>
      ${c.maintenance_notes && html`<p class="small"><strong>Maintenance notes:</strong> ${c.maintenance_notes}</p>`}
    </section>
    ${(c.relations || []).length > 0 && html`<section class="panel"><h2>Overlapping collections elsewhere</h2><ul>${c.relations.map((r) => html`<li>
      <a href=${`#/resource/${r.other_id}`}>${r.other_name}</a> (${r.other_provider}) — ${r.relation}${r.note ? ': ' + r.note : ''}</li>`)}</ul></section>`}
    ${(c.siblings || []).length > 0 && html`<section class="panel"><h2>Other collections from ${c.provider_name}</h2><ul>${c.siblings.map((x) => html`<li><a href=${`#/resource/${x.id}`}>${x.name}</a></li>`)}</ul></section>`}
    ${logging && html`<${LogEntryForm} initial=${{ collection_id: c.id }} onClose=${() => setLogging(false)} onSaved=${() => setLogging(false)} />`}
  </div>`;
}

export function Pathways() {
  const { data, error, loading } = useAsync(() => api.get('/directory/pathways'), []);
  if (loading) return html`<div class="page"><${Loading} /></div>`;
  if (error) return html`<div class="page"><${ErrorBox} error=${error} /></div>`;
  return html`<div class="page">
    <header class="page-head"><div><h1>Research pathways</h1>
    <p class="lede">Step-by-step starting points based on guidance from archives and libraries. Choose a pathway because your research leads there — the app never infers ancestry or identity from a name.</p></div></header>
    ${data.map((p) => html`<details class="panel pathway"><summary><h2>${p.title}</h2></summary>
      <p>${p.summary}</p>
      ${(p.cautions || []).length > 0 && html`<div class="callout tone-warn"><strong>Before you start</strong><ul>${p.cautions.map((x) => html`<li>${x}</li>`)}</ul></div>`}
      <ol class="steps">${(p.steps || []).map((st) => html`<li><strong>${st.title}</strong><p>${st.detail}</p>${st.guidance_url && html`<${ExtLink} href=${st.guidance_url} cls="small">Guidance<//>`}</li>`)}</ol>
      ${(p.collections || []).length > 0 && html`<h3>Related directory entries</h3><ul>${p.collections.map((c) => html`<li><a href=${`#/resource/${c.id}`}>${c.name}</a></li>`)}</ul>`}
      <p class="muted small">Guidance checked ${p.last_verified || 'not yet'}.</p>
    </details>`)}
  </div>`;
}
