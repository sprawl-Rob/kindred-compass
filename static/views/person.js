import { html, useState } from '../vendor/preact-htm.js';
import { api, useAsync, useStore, Loading, ErrorBox, ExtLink, toast, errMsg, nav } from '../ui.js';
import { ResearchButtons, LeadCard } from './research.js';

const ICON = { found: ['✓', 'Found in your tree'], missing: ['○', 'Not in your tree yet'], maybe: ['?', 'Possibly expected — dates or residence uncertain'], lost: ['✕', 'Records do not survive'] };
const EVENT = { birth: 'Born', baptism: 'Baptised', death: 'Died', burial: 'Buried', marriage: 'Married', residence: 'Lived', immigration: 'Arrived',
  emigration: 'Emigrated', naturalization: 'Naturalized', occupation: 'Occupation', military: 'Military', divorce: 'Divorced', religion: 'Religion',
  property: 'Property', other: 'Other', migration: 'Moved', name: 'Name' };

export function PersonLink({ p, cls }) {
  if (!p) return null;
  return html`<a class=${'person-chip ' + (cls || '')} href=${`#/person/${p.id}`}><span class="pc-name">${p.name}</span>
    ${p.lifespan && html`<span class="pc-life">${p.lifespan}</span>`}</a>`;
}

function Family({ fam, name }) {
  const row = (label, list, empty) => html`<div class="fam-row"><span class="fam-label">${label}</span>
    <div class="fam-list">${list.length ? list.map((p) => html`<${PersonLink} p=${p} />`) : html`<span class="muted small">${empty}</span>`}</div></div>`;
  return html`<div class="family">
    ${row('Parents', fam.parents, 'Not in your tree — see “Finding parents” below')}
    ${row(fam.spouses.length > 1 ? 'Spouses' : 'Spouse', fam.spouses, 'None recorded')}
    ${row('Children', fam.children, 'None recorded')}
    ${fam.siblings.length > 0 && row('Siblings', fam.siblings, '')}
  </div>`;
}

function SearchLinks({ links }) {
  const main = links.filter((l) => !l.alt);
  const alt = links.filter((l) => l.alt);
  return html`<div class="search-links">
    ${main.map((l) => html`<a class=${'button small ' + (l.free ? '' : 'secondary')} href=${l.url} target="_blank" rel="noopener noreferrer"
      title=${(l.collection === false ? 'All collections (no verified collection ID). ' : '') + (l.login ? `Needs a ${l.login}` : 'Free')}>${l.site} ↗</a>`)}
    ${alt.length > 0 && html`<details class="alt-searches"><summary class="small">If it isn't found</summary>
      <ul class="small">${alt.map((l) => html`<li><${ExtLink} href=${l.url}>${l.label}<//></li>`)}</ul></details>`}
  </div>`;
}

export function AutoSearch({ auto, personId, label }) {
  const s = useStore();
  const [busy, setBusy] = useState(false);
  const go = async () => {
    setBusy(true);
    try {
      const r = await api.post(`/projects/${s.projectId}/research/runs`, { person_id: personId, options: { adapters: auto.adapters, auto_save: true } });
      nav(`#/research/${r.id}`);
    } catch (x) { toast(errMsg(x), 'bad'); setBusy(false); }
  };
  return html`<button class="small" disabled=${busy} onClick=${go} title="The app runs this search itself and checks each result against what you know">${busy ? 'Starting…' : (label || auto.label)}</button>`;
}

function ChecklistItem({ it, personId }) {
  const [open, setOpen] = useState(false);
  const [icon, tip] = ICON[it.status];
  const e = it.expect || {};
  return html`<li class=${'ck-item ck-' + it.status}>
    <div class="ck-head">
      <span class="ck-icon" title=${tip} aria-label=${tip}>${icon}</span>
      <div class="ck-main">
        <button class="link ck-title" aria-expanded=${open} onClick=${() => setOpen(!open)}>${it.title}</button>
        <div class="small muted">${it.status === 'found' ? it.found.map((s) => s.title).filter((x, i, a) => a.indexOf(x) === i).join(' · ') : it.why}</div>
        ${it.status !== 'found' && (e.place || (e.household || []).length > 0) && html`<div class="small ck-expect">
          ${e.place && html`<span>Look in <strong>${e.place}</strong>${e.age ? html`, age about <strong>${e.age}</strong>` : ''}</span>`}
          ${(e.household || []).length > 0 && html`<span> · likely with ${e.household.slice(0, 4).map((h, i) => html`${i ? ', ' : ''}<a href=${`#/person/${h.id}`}>${h.name}</a>`)}</span>`}
        </div>`}
      </div>
      ${it.status === 'missing' || it.status === 'maybe' ? html`<div class="ck-actions">${it.auto && html`<${AutoSearch} auto=${it.auto} personId=${personId} />`}<${SearchLinks} links=${it.searches || []} /></div>` : null}
    </div>
    ${open && html`<div class="ck-body small">
      ${it.status === 'found' && html`<p>${it.why}</p>`}
      ${it.tells && html`<p><strong>What it tells you:</strong> ${it.tells}</p>`}
      ${it.note && html`<p>${it.note}</p>`}
      ${e.place_basis && html`<p class="muted">Place from the record ${e.place_basis}.</p>`}
      ${it.found.length > 0 && html`<ul>${it.found.map((s) => html`<li>${s.url ? html`<${ExtLink} href=${s.url}>${s.title}<//>` : s.title}</li>`)}</ul>`}
      ${it.status === 'found' && (it.searches || []).length > 0 && html`<${SearchLinks} links=${it.searches} />`}
    </div>`}
  </li>`;
}

function ParentsPath({ it, name }) {
  return html`<section class="panel brick"><h2>Finding ${name}'s parents</h2>
    <p class="small">No parents are recorded. These records usually name them — work down the list:</p>
    <ol class="path-list">${it.paths.map((p) => html`<li class=${'ck-' + p.status}><strong>${p.title}</strong>
      <span class=${'badge ' + (p.status === 'found' ? 'tone-good' : p.status === 'missing' ? 'tone-warn' : 'tone-muted')}>${p.status === 'found' ? 'in your tree — reread it for parents' : p.status === 'missing' ? 'not found yet' : p.status}</span>
      <div class="small muted">${p.why}</div></li>`)}</ol></section>`;
}

function Names({ n }) {
  return html`<section class="panel"><h2>Name variations to search</h2>
    <p class="small muted">Records often spell or abbreviate names differently. These forms are used in the searches above; try them when a record can't be found.</p>
    <dl class="kv small">
      ${n.given_variants.length > 0 && html`<dt>${n.given}</dt><dd>${n.given_variants.join(', ')}</dd>`}
      ${n.abbreviations.length > 0 && html`<dt>Initials</dt><dd>${n.abbreviations.join(', ')}</dd>`}
      ${n.surname_variants.length > 0 && html`<dt>${n.surname}</dt><dd>${n.surname_variants.join(', ')}</dd>`}
      ${n.married_surnames.length > 0 && html`<dt>Married name${n.married_surnames.length > 1 ? 's' : ''}</dt><dd>${n.married_surnames.join(', ')}</dd>`}
      ${n.soundex.length > 0 && html`<dt>Soundex</dt><dd>${n.soundex.join(', ')} <span class="muted">(how U.S. census indexes group sound-alike surnames)</span></dd>`}
    </dl></section>`;
}

function Timeline({ rows }) {
  return html`<section class="panel"><h2>Life events in your tree</h2>
    ${rows.length === 0 ? html`<p class="muted">No dated events yet.</p>` : html`<ol class="timeline">${rows.map((r) => html`<li>
      <span class="tl-year">${r.year ?? '—'}</span>
      <div><strong>${EVENT[r.type] || r.type}</strong>${r.value && r.type !== 'relationship' ? html` · ${r.value}` : ''}${r.place ? html` · ${r.place}` : ''}
        ${r.date && String(r.date) !== String(r.year) && html` <span class="muted small">(${r.date})</span>`}
        ${r.detail && html` <span class="muted small">${r.detail}</span>`}
        <div class="small muted">${r.sources.length === 0 ? 'no source' : r.sources.map((s, i) => html`${i ? ' · ' : ''}${s.url ? html`<${ExtLink} href=${s.url}>${s.title}<//>` : s.title}`)}</div></div></li>`)}</ol>`}
  </section>`;
}

export function PersonOverview({ id }) {
  const s = useStore();
  const { data: d, error, loading, reload } = useAsync(() => api.get(`/persons/${id}/overview`), [id]);
  const [filter, setFilter] = useState('todo');
  if (loading && !d) return html`<div class="page"><${Loading} /></div>`;
  if (error) return html`<div class="page"><${ErrorBox} error=${error} retry=${reload} /></div>`;
  const p = d.person;
  const parentsItem = d.items.find((i) => i.id === 'parents');
  const items = d.items.filter((i) => i.id !== 'parents');
  const shown = filter === 'todo' ? items.filter((i) => i.status === 'missing' || i.status === 'maybe') : items;
  const groups = [];
  shown.forEach((i) => { let g = groups.find((x) => x.k === i.group); if (!g) groups.push(g = { k: i.group, label: i.group_label, items: [] }); g.items.push(i); });
  const facts = [p.birth && `Born ${p.birth}${p.birth_estimated ? ' (estimated)' : ''}${p.birth_place ? ', ' + p.birth_place : ''}`,
    p.death && `Died ${p.death}${p.death_place ? ', ' + p.death_place : ''}`].filter(Boolean);
  return html`<div class="page person-page">
    <nav class="crumbs"><a href="#/tree">Family tree</a> / <a href=${`#/tree/${p.id}`}>Show in tree</a></nav>
    <header class="page-head"><div>
      <h1>${p.name}</h1>
      <p class="lede">${facts.join(' · ') || 'No dates recorded yet'}${p.birth_estimated && d.birth_basis ? html` <span class="small muted">— ${d.birth_basis}</span>` : ''}</p>
      ${p.living_status !== 'deceased' && html`<p class="small muted">Living status not recorded — the AI assistant treats this person as possibly living and won't send their details unless you allow it.</p>`}
    </div>
      <div class="row wrap"><${ResearchButtons} person=${{ id: p.id, display_name: p.name }} questions=${[]} />
        <a class="button secondary" href=${`#/person/${p.id}/edit`}>Edit facts & sources</a></div></header>

    <${Family} fam=${d.family} name=${p.name} />

    ${d.leads.length > 0 && html`<section class="panel leads-panel"><h2>Possible records found (${d.leads.length})</h2>
      <p class="small muted">Found by research runs. Is this ${p.name}?</p>
      <div class="lead-list">${d.leads.map((h) => html`<${LeadCard} h=${h} onChange=${reload} />`)}</div></section>`}

    ${parentsItem && html`<${ParentsPath} it=${parentsItem} name=${p.name.split(' ')[0]} />`}

    <section class="panel"><div class="panel-head"><h2>Record checklist</h2>
      <div class="seg" role="group" aria-label="Show">
        <button class=${filter === 'todo' ? 'on' : ''} onClick=${() => setFilter('todo')}>To find (${d.counts.missing + d.counts.maybe})</button>
        <button class=${filter === 'all' ? 'on' : ''} onClick=${() => setFilter('all')}>All (${items.length})</button></div></div>
      <p class="small muted">Records ${p.name} should appear in, based on their dates and places. ✓ already in your tree · ○ not yet · ? maybe (uncertain dates or residence).
        Search buttons open the right collection with name, birth years and place filled in.</p>
      ${groups.length === 0 && html`<p class="callout tone-good">Nothing missing from the checklist. Look at the leads above, or run research to find more.</p>`}
      ${groups.map((g) => html`<h3 class="ck-group">${g.label}</h3><ul class="checklist">${g.items.map((it) => html`<${ChecklistItem} it=${it} personId=${p.id} key=${it.id} />`)}</ul>`)}
    </section>

    <div class="grid-2">
      <${Timeline} rows=${d.timeline} />
      <${Names} n=${d.names} />
    </div>
  </div>`;
}
