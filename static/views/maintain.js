import { html, useState } from '../vendor/preact-htm.js';
import { api, useAsync, useStore, Loading, ErrorBox, Field, Select, CheckboxGroup, Modal, ExtLink, Badges, L, fmtDate, toast, errMsg, nav } from '../ui.js';

const today = () => new Date().toISOString().slice(0, 10);
const csv = (a) => (a || []).join(', ');
const uncsv = (s) => (s || '').split(',').map((x) => x.trim()).filter(Boolean);

function VerifyModal({ c, onClose, onSaved }) {
  const s = useStore();
  const [v, setV] = useState({ status: 'verified', source_note: '', checked_on: today() });
  const save = async (e) => { e.preventDefault(); try { await api.post(`/directory/collections/${c.id}/verify`, v); onSaved(); } catch (x) { toast(errMsg(x), 'bad'); } };
  return html`<${Modal} title=${'Record verification: ' + c.name} onClose=${onClose}>
    <form class="stack" onSubmit=${save}>
      <p class="small">Open the <${ExtLink} href=${c.url}>official site<//>, compare it with the entry, fix anything that changed, then record what you checked.</p>
      <${Field} label="Result"><${Select} value=${v.status} onChange=${(x) => setV({ ...v, status: x })} options=${s.meta.vocab.verification_statuses} /><//>
      <${Field} label="What you checked / source"><input required value=${v.source_note} onInput=${(e) => setV({ ...v, source_note: e.target.value })} placeholder="e.g. Checked access and coverage pages on provider site" /><//>
      <${Field} label="Checked on"><input type="date" value=${v.checked_on} onInput=${(e) => setV({ ...v, checked_on: e.target.value })} /><//>
      <div class="row end"><button type="button" class="secondary" onClick=${onClose}>Cancel</button><button type="submit">Save</button></div>
    </form><//>`;
}

export function Maintain() {
  const s = useStore();
  const [showArchived, setShowArchived] = useState(false);
  const [q, setQ] = useState('');
  const [status, setStatus] = useState('');
  const { data, error, loading, reload } = useAsync(() => api.post('/directory/search', { include_archived: showArchived, project_id: s.projectId }), [showArchived]);
  const seed = useAsync(() => api.get('/directory/seed'), []);
  const [verify, setVerify] = useState(null);
  const [report, setReport] = useState(null);
  const all = data ? Object.values(data.groups).flat() : [];
  const rows = all.filter((c) => (!q || (c.name + c.provider_name).toLowerCase().includes(q.toLowerCase())) && (!status || c.verification_status === status))
    .sort((a, b) => (a.provider_name + a.name).localeCompare(b.provider_name + b.name));
  const archive = async (c) => { await api.post(`/directory/collections/${c.id}/archive`, { archived: !c.archived }); reload(); };
  const check = async (c) => { try { const r = await api.post(`/directory/collections/${c.id}/check-link`); toast(`${c.name}: ${r.link_health} — ${r.detail}`); reload(); } catch (x) { toast(errMsg(x), 'bad'); } };
  const applySeed = async () => { try { setReport(await api.post('/directory/seed/apply')); seed.reload(); reload(); } catch (x) { toast(errMsg(x), 'bad'); } };
  return html`<div class="page">
    <header class="page-head"><div><h1>Directory maintenance</h1>
      <p class="lede">Add, edit, archive and verify entries. Your edits are protected: seed updates never overwrite a field you changed.</p></div>
      <div class="row wrap"><a class="button" href="#/directory/new">Add collection</a><a class="button secondary" href="/api/directory/export.csv" download>Export CSV</a></div></header>
    <div class="callout tone-info small">Initial coverage is incomplete — especially local repositories and non-U.S. sources. Add the archives, courthouses, libraries and societies you use.</div>
    <section class="panel subtle"><h2 class="h3">Seed data</h2>
      ${seed.data && html`<p class="small">Applied version: ${seed.data.applied ? seed.data.applied.version : 'none'} (${seed.data.applied ? fmtDate(seed.data.applied.applied_at) : '—'}); available: ${seed.data.available_version}.</p>`}
      <button class="small secondary" onClick=${applySeed}>Re-apply seed (safe)</button>
      ${report && html`<p class="small">Inserted ${report.inserted.length}, updated ${report.updated.length}, unchanged ${report.unchanged}; preserved ${report.preserved_user_edits.length} of your edits.
        ${report.not_in_seed.length ? ` ${report.not_in_seed.length} seed entries no longer in the seed were kept.` : ''}</p>`}</section>
    <div class="row wrap filters-inline">
      <${Field} label="Filter"><input type="search" value=${q} onInput=${(e) => setQ(e.target.value)} /><//>
      <${Field} label="Verification"><${Select} value=${status} onChange=${(v) => setStatus(v || '')} empty="Any" options=${s.meta.vocab.verification_statuses} /><//>
      <label class="check"><input type="checkbox" checked=${showArchived} onChange=${(e) => setShowArchived(e.target.checked)} /> Include archived</label></div>
    <${ErrorBox} error=${error} retry=${reload} />
    ${loading && !data ? html`<${Loading} />` : html`<div class="table-wrap"><table class="table"><thead><tr><th>Entry</th><th>Status</th><th>Last verified</th><th>Link</th><th>Origin</th><th><span class="sr-only">Actions</span></th></tr></thead><tbody>
      ${rows.map((c) => html`<tr class=${c.archived ? 'archived' : ''}><td><a href=${`#/resource/${c.id}`}>${c.name}</a><div class="muted small">${c.provider_name}</div></td>
        <td>${L('verification_statuses', c.verification_status)}</td><td>${c.last_verified || '—'}</td><td>${c.link_health}</td>
        <td class="small">${c.origin}${(c.user_fields || []).length ? ' · edited' : ''}</td>
        <td class="actions"><a class="small" href=${`#/directory/edit/${c.id}`}>Edit</a>
          <button class="small link" onClick=${() => setVerify(c)}>Verify</button>
          <button class="small link" onClick=${() => check(c)}>Check link</button>
          <button class="small link" onClick=${() => archive(c)}>${c.archived ? 'Restore' : 'Archive'}</button></td></tr>`)}
    </tbody></table></div>`}
    ${verify && html`<${VerifyModal} c=${verify} onClose=${() => setVerify(null)} onSaved=${() => { setVerify(null); reload(); }} />`}
  </div>`;
}

function RangeEditor({ label, value, onChange }) {
  const list = value || [];
  const upd = (i, k, v) => onChange(list.map((r, j) => (j === i ? { ...r, [k]: k === 'label' ? v : v === '' ? null : +v } : r)));
  return html`<fieldset><legend>${label}</legend>
    ${list.map((r, i) => html`<div class="row tight"><input aria-label="From year" inputmode="numeric" size="5" value=${r.from ?? ''} onInput=${(e) => upd(i, 'from', e.target.value)} placeholder="from" />
      <input aria-label="To year" inputmode="numeric" size="5" value=${r.to ?? ''} onInput=${(e) => upd(i, 'to', e.target.value)} placeholder="to" />
      <input aria-label="Label" value=${r.label || ''} onInput=${(e) => upd(i, 'label', e.target.value)} placeholder="label" />
      <button type="button" class="icon small" aria-label="Remove range" onClick=${() => onChange(list.filter((_, j) => j !== i))}>✕</button></div>`)}
    <button type="button" class="small secondary" onClick=${() => onChange([...list, { from: null, to: null, label: '' }])}>Add range</button>
    ${list.length === 0 && html`<p class="hint">Empty means unknown — not “none”.</p>`}</fieldset>`;
}

function GeoEditor({ value, onChange }) {
  const list = value || [];
  const upd = (i, k, v) => onChange(list.map((g, j) => (j === i ? { ...g, [k]: v || null } : g)));
  return html`<fieldset><legend>Places covered</legend>
    ${list.map((g, i) => html`<div class="row tight wrap">${['country', 'region', 'county', 'municipality', 'historical_jurisdiction'].map((k) => html`
      <input aria-label=${k} placeholder=${k.replace('_', ' ')} value=${g[k] || ''} onInput=${(e) => upd(i, k, e.target.value)} />`)}
      <button type="button" class="icon small" aria-label="Remove place" onClick=${() => onChange(list.filter((_, j) => j !== i))}>✕</button></div>`)}
    <button type="button" class="small secondary" onClick=${() => onChange([...list, { country: '' }])}>Add place</button></fieldset>`;
}

export function CollectionEditor({ id }) {
  const s = useStore(); const V = s.meta.vocab;
  const providers = useAsync(() => api.get('/directory/providers'), []);
  const existing = useAsync(() => (id ? api.get(`/directory/collections/${id}`) : Promise.resolve(null)), [id]);
  const [v, setV] = useState(null);
  const [newProv, setNewProv] = useState(false);
  if (!v && (!id || existing.data)) {
    const c = existing.data || { entry_kind: 'repository', geo_scope: 'listed', geo: [], dates: [], date_gaps: [], access_search: ['unknown'], access_images: ['unknown'],
      access_copies: ['unknown'], integration_method: 'outbound_link', verification_status: 'needs_verification', capabilities: [], record_types: [], evidence_forms: [] };
    setV({ ...c, languages_s: csv(c.languages), terminology_s: csv(c.terminology), tags_s: csv(c.tags) });
    return null;
  }
  if (!v || !providers.data) return html`<div class="page"><${Loading} /></div>`;
  const set = (k) => (x) => setV({ ...v, [k]: x && x.target ? (x.target.type === 'checkbox' ? x.target.checked : x.target.value) : x });
  const save = async (e) => {
    e.preventDefault();
    const fields = ['provider_id', 'name', 'url', 'search_url', 'description', 'entry_kind', 'repository_type', 'geo_scope', 'geo', 'dates', 'date_gaps',
      'record_types', 'capabilities', 'evidence_forms', 'access_search', 'access_images', 'access_copies', 'access_notes', 'integration_method',
      'search_url_template', 'search_link_verified', 'search_link_notes', 'rights_notes', 'limitations', 'digitization_status', 'maintenance_notes'];
    const body = Object.fromEntries(fields.map((k) => [k, v[k] === '' ? null : v[k]]));
    body.languages = uncsv(v.languages_s); body.terminology = uncsv(v.terminology_s); body.tags = uncsv(v.tags_s);
    body.geo = (body.geo || []).filter((g) => Object.values(g).some(Boolean));
    try {
      const out = id ? await api.patch(`/directory/collections/${id}`, body) : await api.post('/directory/collections', body);
      toast('Directory entry saved'); nav(`#/resource/${out.id}`);
    } catch (x) { toast(errMsg(x), 'bad'); }
  };
  const editable = { ...V.integration_methods }; if (v.integration_method !== 'documented_api') delete editable.documented_api;
  return html`<div class="page">
    <nav class="crumbs"><a href="#/directory">Directory</a> / ${id ? 'Edit' : 'New entry'}</nav>
    <h1>${id ? `Edit: ${v.name}` : 'New directory entry'}</h1>
    ${id && v.origin === 'seed' && html`<p class="callout tone-info small">This entry came from the seed directory. Fields you change here are marked as yours and future seed updates will not overwrite them.</p>`}
    <form class="stack" onSubmit=${save}>
      <section class="panel"><h2>Basics</h2><div class="grid-2 tight">
        <${Field} label="Provider"><div class="row tight"><${Select} required value=${v.provider_id} onChange=${set('provider_id')} empty="Choose…" options=${providers.data.map((p) => [p.id, p.name])} />
          <button type="button" class="small secondary" onClick=${() => setNewProv(true)}>New provider</button></div><//>
        <${Field} label="Name"><input required value=${v.name || ''} onInput=${set('name')} /><//>
        <${Field} label="Official URL"><input type="url" required value=${v.url || ''} onInput=${set('url')} /><//>
        <${Field} label="Search page URL"><input type="url" value=${v.search_url || ''} onInput=${set('search_url')} /><//>
        <${Field} label="Kind of entry"><${Select} value=${v.entry_kind} onChange=${set('entry_kind')} options=${V.entry_kinds} /><//>
        <${Field} label="Repository type"><${Select} value=${v.repository_type} onChange=${set('repository_type')} empty="—" options=${V.repository_types} /><//>
        <${Field} label="Description" wide><textarea rows="3" value=${v.description || ''} onInput=${set('description')} /><//></div></section>
      <section class="panel"><h2>Coverage</h2>
        <${Field} label="Geographic scope"><${Select} value=${v.geo_scope} onChange=${set('geo_scope')} options=${{ listed: 'Listed places', worldwide: 'Not limited to one place', unknown: 'Unknown' }} /><//>
        ${v.geo_scope === 'listed' && html`<${GeoEditor} value=${v.geo} onChange=${set('geo')} />`}
        <div class="grid-2 tight"><${RangeEditor} label="Date coverage" value=${v.dates} onChange=${set('dates')} /><${RangeEditor} label="Known gaps" value=${v.date_gaps} onChange=${set('date_gaps')} /></div>
        <${Field} label="Record types" hint="Ctrl/⌘-click to choose several"><select multiple size="8" onChange=${(e) => set('record_types')([...e.target.selectedOptions].map((o) => o.value))}>
          ${V.record_type_groups.map((g) => html`<optgroup label=${g.label}>${g.types.map((t) => html`<option value=${t.key} selected=${(v.record_types || []).includes(t.key)}>${t.label}</option>`)}</optgroup>`)}</select><//>
        <div class="grid-2 tight"><${Field} label="Languages (comma-separated)"><input value=${v.languages_s} onInput=${set('languages_s')} /><//>
          <${Field} label="Country-specific terms (comma-separated)"><input value=${v.terminology_s} onInput=${set('terminology_s')} /><//></div></section>
      <section class="panel"><h2>Search & access</h2>
        <${CheckboxGroup} legend="Search capabilities" options=${V.search_capabilities} value=${v.capabilities} onChange=${set('capabilities')} />
        <${CheckboxGroup} legend="Evidence forms" options=${V.evidence_forms} value=${v.evidence_forms} onChange=${set('evidence_forms')} />
        <div class="grid-3"><${CheckboxGroup} legend="Access to search" options=${V.access} value=${v.access_search} onChange=${set('access_search')} />
          <${CheckboxGroup} legend="Access to images" options=${V.access} value=${v.access_images} onChange=${set('access_images')} />
          <${CheckboxGroup} legend="Access to copies" options=${V.access} value=${v.access_copies} onChange=${set('access_copies')} /></div>
        <${Field} label="Access notes"><textarea rows="2" value=${v.access_notes || ''} onInput=${set('access_notes')} /><//>
        <${Field} label="Integration method"><${Select} value=${v.integration_method} onChange=${set('integration_method')} options=${editable} /><//>
        <${Field} label="Pre-filled search URL template" hint="Placeholders: {q} {given} {surname} {year_from} {year_to} {year} {state}. Only used if you tick 'verified'."><input value=${v.search_url_template || ''} onInput=${set('search_url_template')} /><//>
        <label class="check"><input type="checkbox" checked=${!!v.search_link_verified} onChange=${set('search_link_verified')} /> I tested this template with a real query and the results matched</label>
        <${Field} label="Search link notes"><input value=${v.search_link_notes || ''} onInput=${set('search_link_notes')} /><//></section>
      <section class="panel"><h2>Limitations, rights & maintenance</h2><div class="grid-2 tight">
        <${Field} label="Known limitations, indexing gaps"><textarea rows="3" value=${v.limitations || ''} onInput=${set('limitations')} /><//>
        <${Field} label="Rights & reuse" hint="Leave empty if unknown"><textarea rows="3" value=${v.rights_notes || ''} onInput=${set('rights_notes')} /><//>
        <${Field} label="Digitization status"><${Select} value=${v.digitization_status} onChange=${set('digitization_status')} options=${{ unknown: 'Unknown', none: 'Not digitized', partial: 'Partly digitized', complete: 'Fully digitized' }} /><//>
        <${Field} label="Maintenance notes"><textarea rows="3" value=${v.maintenance_notes || ''} onInput=${set('maintenance_notes')} /><//>
        <${Field} label="Tags (comma-separated)"><input value=${v.tags_s} onInput=${set('tags_s')} /><//></div>
        <p class="small muted">Verification status is recorded with the “Verify” action in the directory list, with the date and what you checked.</p></section>
      <div class="row end"><a class="button secondary" href=${id ? `#/resource/${id}` : '#/directory'}>Cancel</a><button type="submit">Save entry</button></div>
    </form>
    ${newProv && html`<${ProviderModal} onClose=${() => setNewProv(false)} onSaved=${(p) => { setNewProv(false); providers.reload(); setV({ ...v, provider_id: p.id }); }} />`}
  </div>`;
}

function ProviderModal({ onClose, onSaved }) {
  const s = useStore();
  const [v, setV] = useState({ name: '', homepage_url: '', provider_type: 'other', country: '' });
  const save = async (e) => { e.preventDefault(); try { onSaved(await api.post('/directory/providers', v)); } catch (x) { toast(errMsg(x), 'bad'); } };
  return html`<${Modal} title="New provider" onClose=${onClose}><form class="stack" onSubmit=${save}>
    <${Field} label="Name"><input required value=${v.name} onInput=${(e) => setV({ ...v, name: e.target.value })} /><//>
    <${Field} label="Homepage"><input type="url" value=${v.homepage_url} onInput=${(e) => setV({ ...v, homepage_url: e.target.value })} /><//>
    <${Field} label="Type"><${Select} value=${v.provider_type} onChange=${(x) => setV({ ...v, provider_type: x })} options=${s.meta.vocab.repository_types} /><//>
    <${Field} label="Country"><input value=${v.country} onInput=${(e) => setV({ ...v, country: e.target.value })} /><//>
    <div class="row end"><button type="button" class="secondary" onClick=${onClose}>Cancel</button><button type="submit">Create provider</button></div></form><//>`;
}
