import { html, useState } from '../vendor/preact-htm.js';
import { api, useAsync, useStore, Loading, ErrorBox, Empty, Field, Select, Modal, PlaceFields, L, fmtDate, years, toast, errMsg, nav } from '../ui.js';
import { AIAction } from './ai.js';
import { ClaimEvidence } from './evidence.js';
import { ImportedDataPanel } from './imports.js';
import { ResearchButtons } from './research.js';

export function PersonForm({ onClose, onSaved }) {
  const s = useStore();
  const [v, setV] = useState({ given: '', surname: '', living_status: 'deceased', date_text: '', claim_type: 'birth', place: {} });
  const set = (k) => (e) => setV({ ...v, [k]: e.target ? e.target.value : e });
  const save = async (e) => {
    e.preventDefault();
    const claims = [];
    if (v.date_text || Object.values(v.place).some(Boolean)) claims.push({ claim_type: v.claim_type, date_text: v.date_text, place: v.place, status: 'working' });
    try {
      const p = await api.post(`/projects/${s.projectId}/persons`, {
        names: [{ name_type: 'birth', given: v.given, surname: v.surname }], living_status: v.living_status, claims });
      toast('Person added'); onSaved(p);
    } catch (x) { toast(errMsg(x), 'bad'); }
  };
  return html`<${Modal} title="Add a person" onClose=${onClose} wide>
    <form class="stack" onSubmit=${save}>
      <p class="small muted">Start with what you know — a name and one approximate date and place is enough. You can add more names, conflicting dates, and relationships later.</p>
      <div class="row wrap"><${Field} label="Given name(s)"><input value=${v.given} onInput=${set('given')} /><//>
        <${Field} label="Surname (as recorded)"><input value=${v.surname} onInput=${set('surname')} /><//>
        <${Field} label="Living?" hint="Possibly-living people are kept private"><${Select} value=${v.living_status} onChange=${set('living_status')} options=${{ deceased: 'Deceased', living: 'Living', unknown: 'Unknown' }} /><//></div>
      <fieldset><legend>One known fact (optional)</legend>
        <div class="row wrap"><${Field} label="Event"><${Select} value=${v.claim_type} onChange=${set('claim_type')} options=${{ birth: 'Birth', baptism: 'Baptism', marriage: 'Marriage', residence: 'Residence', immigration: 'Immigration', death: 'Death' }} /><//>
          <${Field} label="Date (approximate is fine)" hint="e.g. 1852, abt 1852, bef 1860, bet 1850 and 1855"><input value=${v.date_text} onInput=${set('date_text')} /><//></div>
        <${PlaceFields} value=${v.place} onChange=${(p) => setV({ ...v, place: p })} /></fieldset>
      <div class="row end"><button type="button" class="secondary" onClick=${onClose}>Cancel</button><button type="submit">Add person</button></div>
    </form><//>`;
}

export function People() {
  const s = useStore();
  const { data, error, loading, reload } = useAsync(() => api.get(`/projects/${s.projectId}/persons`), [s.projectId]);
  const [adding, setAdding] = useState(false);
  const [q, setQ] = useState('');
  const shown = (data || []).filter((p) => !q || (p.display_name + ' ' + p.summary.places.join(' ')).toLowerCase().includes(q.toLowerCase()));
  return html`<div class="page">
    <header class="page-head"><div><h1>People</h1>
      <p class="lede">${data ? `${data.length} people.` : ''} Open anyone to see their record checklist and what to search next.</p></div>
      <button onClick=${() => setAdding(true)}>Add a person</button></header>
    <${ErrorBox} error=${error} retry=${reload} />
    ${data && data.length > 0 && html`<div class="searchbar"><label class="sr-only" for="people-q">Find a person</label>
      <input id="people-q" type="search" placeholder="Find by name or place…" value=${q} onInput=${(e) => setQ(e.target.value)} /></div>`}
    ${loading && !data ? html`<${Loading} />` : data && data.length === 0 ? html`<${Empty} title="No people yet">Import a family tree (More → Import a tree), or add someone with an approximate date and place.<p><button onClick=${() => setAdding(true)}>Add a person</button></p><//>` :
      data && html`<div class="cards">${shown.map((p) => html`<a class="card person-card" href=${`#/person/${p.id}`}>
        <strong>${p.display_name}</strong>
        <span class="muted small">${[p.summary.birth && 'b. ' + p.summary.birth, p.summary.death && 'd. ' + p.summary.death].filter(Boolean).join(' · ') || 'No dates yet'}</span>
        <span class="small">${p.summary.places.join(' · ')}</span></a>`)}</div>`}
    ${data && q && shown.length === 0 && html`<p class="muted">Nobody matches “${q}”.</p>`}
    ${adding && html`<${PersonForm} onClose=${() => setAdding(false)} onSaved=${(p) => { setAdding(false); nav(`#/person/${p.id}`); }} />`}
  </div>`;
}

function ClaimForm({ person, claim, people, onClose, onSaved }) {
  const s = useStore();
  const [v, setV] = useState(() => claim ? { ...claim, place: claim.place_id ? { id: claim.place_id } : {} } :
    { claim_type: 'birth', date_text: '', status: 'working', place: {}, statement: '' });
  const set = (k) => (e) => setV({ ...v, [k]: e && e.target ? e.target.value : e });
  const save = async (e) => {
    e.preventDefault();
    const body = { claim_type: v.claim_type, date_text: v.date_text, status: v.status, statement: v.statement, status_note: v.status_note,
      value_text: v.value_text, related_person_id: v.related_person_id || null, relationship_type: v.relationship_type || null,
      relationship_qualifier: v.relationship_qualifier || null };
    if (v.place && !v.place.id && Object.values(v.place).some(Boolean)) body.place = v.place;
    try {
      claim ? await api.patch(`/claims/${claim.id}`, body) : await api.post(`/projects/${s.projectId}/claims`, { ...body, person_id: person.id });
      onSaved();
    } catch (x) { toast(errMsg(x), 'bad'); }
  };
  const V = s.meta.vocab;
  return html`<${Modal} title=${claim ? 'Edit claim' : 'Add a claim'} onClose=${onClose} wide>
    <form class="stack" onSubmit=${save}>
      <p class="small muted">A claim is something asserted about ${person.display_name}. Conflicting claims are kept side by side — adding one never replaces another.</p>
      <div class="row wrap">
        <${Field} label="Type"><${Select} value=${v.claim_type} onChange=${set('claim_type')} options=${V.claim_types} /><//>
        <${Field} label="Date as known" hint="abt 1852 · bef 1860 · bet 1850 and 1855 · 1850s"><input value=${v.date_text || ''} onInput=${set('date_text')} /><//>
        <${Field} label="Status"><${Select} value=${v.status} onChange=${set('status')} options=${V.claim_statuses} /><//>
      </div>
      ${v.claim_type === 'relationship' && html`<div class="row wrap">
        <${Field} label="Relationship"><${Select} value=${v.relationship_type} onChange=${set('relationship_type')} empty="Choose…" options=${V.relationship_types} required /><//>
        <${Field} label="Related person"><${Select} value=${v.related_person_id} onChange=${set('related_person_id')} empty="Choose…"
          options=${people.filter((p) => p.id !== person.id).map((p) => [p.id, p.display_name])} /><//>
        ${['child', 'parent'].includes(v.relationship_type) && html`<${Field} label="Kind of relationship"><${Select} value=${v.relationship_qualifier}
          onChange=${set('relationship_qualifier')} empty="Not stated" options=${V.relationship_qualifiers} /><//>`}
        <p class="small muted">Relationships start as tentative. People are never merged automatically.</p></div>`}
      ${!claim || !claim.place_id ? html`<fieldset><legend>Place</legend><${PlaceFields} value=${v.place} onChange=${(p) => setV({ ...v, place: p })} /></fieldset>` :
        html`<p class="small">Place: ${claim.place_label}</p>`}
      ${['occupation', 'name', 'religion', 'other'].includes(v.claim_type) && html`<${Field} label="Value"><input value=${v.value_text || ''} onInput=${set('value_text')} /><//>`}
      <${Field} label="Statement / reasoning"><textarea rows="2" value=${v.statement || ''} onInput=${set('statement')} /><//>
      ${v.status === 'confirmed' && html`<${Field} label="Why you consider this confirmed" hint="Required when the only support is a contributed tree or memorial"><textarea rows="2" value=${v.status_note || ''} onInput=${set('status_note')} /><//>`}
      <div class="row end"><button type="button" class="secondary" onClick=${onClose}>Cancel</button><button type="submit">Save claim</button></div>
    </form><//>`;
}

function QuestionForm({ person, onClose, onSaved }) {
  const s = useStore();
  const [v, setV] = useState({ question: '', question_type: 'identify_parents', year_from: '', year_to: '', place: {} });
  const set = (k) => (e) => setV({ ...v, [k]: e && e.target ? e.target.value : e });
  const save = async (e) => {
    e.preventDefault();
    try {
      const body = { question: v.question, question_type: v.question_type, person_id: person.id,
        year_from: v.year_from ? +v.year_from : null, year_to: v.year_to ? +v.year_to : null };
      if (Object.values(v.place).some(Boolean)) body.place = v.place;
      const q = await api.post(`/projects/${s.projectId}/questions`, body);
      onSaved(q);
    } catch (x) { toast(errMsg(x), 'bad'); }
  };
  return html`<${Modal} title="Add a research question" onClose=${onClose} wide>
    <form class="stack" onSubmit=${save}>
      <${Field} label="Question"><input required value=${v.question} onInput=${set('question')} placeholder=${`e.g. Who were ${person.display_name}'s parents?`} /><//>
      <${Field} label="Kind of question" hint="Used to choose relevant record types"><${Select} value=${v.question_type} onChange=${set('question_type')} options=${s.meta.vocab.question_types} /><//>
      <p class="small muted">Optional: narrow the place and years. If left empty, the person's claims are used.</p>
      <div class="row"><${Field} label="Years from"><input inputmode="numeric" value=${v.year_from} onInput=${set('year_from')} /><//><${Field} label="to"><input inputmode="numeric" value=${v.year_to} onInput=${set('year_to')} /><//></div>
      <${PlaceFields} value=${v.place} onChange=${(p) => setV({ ...v, place: p })} />
      <div class="row end"><button type="button" class="secondary" onClick=${onClose}>Cancel</button><button type="submit">Add question</button></div>
    </form><//>`;
}

function NameForm({ person, onClose, onSaved }) {
  const s = useStore();
  const [v, setV] = useState({ name_type: 'married', given: '', surname: '', full_text: '', script: '', language: '' });
  const set = (k) => (e) => setV({ ...v, [k]: e && e.target ? e.target.value : e });
  const save = async (e) => { e.preventDefault(); try { await api.post(`/persons/${person.id}/names`, v); onSaved(); } catch (x) { toast(errMsg(x), 'bad'); } };
  return html`<${Modal} title="Add a name" onClose=${onClose}>
    <form class="stack" onSubmit=${save}>
      <${Field} label="Kind of name"><${Select} value=${v.name_type} onChange=${set('name_type')} options=${s.meta.vocab.name_types} /><//>
      <div class="row"><${Field} label="Given"><input value=${v.given} onInput=${set('given')} /><//><${Field} label="Surname"><input value=${v.surname} onInput=${set('surname')} /><//></div>
      <${Field} label="Full name as written" hint="Use this for original-script names (e.g. Cyrillic, Hebrew, Chinese)"><input value=${v.full_text} onInput=${set('full_text')} lang=${v.language || undefined} /><//>
      <div class="row"><${Field} label="Script"><input value=${v.script} onInput=${set('script')} placeholder="e.g. Cyrillic" /><//><${Field} label="Language"><input value=${v.language} onInput=${set('language')} /><//></div>
      <div class="row end"><button type="button" class="secondary" onClick=${onClose}>Cancel</button><button type="submit">Add name</button></div>
    </form><//>`;
}

export function PersonPage({ id }) {
  const s = useStore();
  const { data: p, error, loading, reload } = useAsync(() => api.get(`/persons/${id}`), [id]);
  const people = useAsync(() => p ? api.get(`/projects/${p.project_id}/persons`) : Promise.resolve([]), [p && p.project_id]);
  const variants = useAsync(() => api.get(`/persons/${id}/name-variants`), [id]);
  const [modal, setModal] = useState(null);
  if (loading && !p) return html`<div class="page"><${Loading} /></div>`;
  if (error) return html`<div class="page"><${ErrorBox} error=${error} retry=${reload} /></div>`;
  const V = s.meta.vocab;
  const conflictIds = new Set(p.conflicts.flatMap((c) => c.claim_ids));
  const byType = {};
  p.claims.forEach((c) => { (byType[c.claim_type] = byType[c.claim_type] || []).push(c); });
  const close = () => { setModal(null); reload(); };
  const setLiving = async (val) => { await api.patch(`/persons/${p.id}`, { living_status: val }); reload(); };
  const delClaim = async (c) => { if (confirm('Delete this claim? Its evidence links are removed; sources are kept.')) { await api.del(`/claims/${c.id}`); reload(); } };
  return html`<div class="page">
    <nav class="crumbs"><a href=${`#/person/${p.id}`}>← ${p.display_name}: checklist</a> · Facts, sources & research questions</nav>
    <header class="page-head"><div><h1>${p.display_name}</h1>
      <div class="row wrap small"><label>Living status: <select value=${p.living_status} onChange=${(e) => setLiving(e.target.value)}>
        <option value="deceased">Deceased</option><option value="living">Living (private)</option><option value="unknown">Unknown</option></select></label>
        ${p.living_status !== 'deceased' && html`<span class="badge tone-muted" title="Not sent to AI providers unless you allow it">Treated as possibly living — private</span>`}</div></div>
      <div class="row wrap"><${ResearchButtons} person=${p} questions=${p.questions} /><a class="button secondary" href=${`#/next?person=${p.id}`}>Suggest next searches</a>
        <${AIAction} task="research_planning" inputs=${{ person_id: p.id }} label="AI: plan research" />
        <${AIAction} task="evidence_comparison" inputs=${{ person_id: p.id }} label="AI: compare evidence" />
        <${AIAction} task="summarization" inputs=${{ person_id: p.id }} label="AI: draft summary" /></div></header>

    <section class="panel"><div class="panel-head"><h2>Names</h2><button class="small secondary" onClick=${() => setModal('name')}>Add name</button></div>
      <ul class="chips">${p.names.map((n) => html`<li class="chip"><span class="muted small">${V.name_types[n.name_type]}:</span>
        ${[n.given, n.surname].filter(Boolean).join(' ') || n.full_text}${n.full_text && (n.given || n.surname) && n.full_text.replace(/\s+/g, ' ').trim() !== [n.given, n.surname].filter(Boolean).join(' ') ? html` <span lang=${n.language}>(${n.full_text})</span>` : ''}
        ${n.note && html` <span class="muted small" title=${n.note}>ⓘ</span>`}
        <button class="icon small" aria-label="Remove name" onClick=${async () => { await api.del(`/names/${n.id}`); reload(); }}>✕</button></li>`)}</ul>
      ${variants.data && variants.data.groups.length > 0 && html`<details><summary>Search variants to try</summary>
        <ul>${variants.data.groups.map((g) => html`<li><span class="small muted">${g.reason}:</span> ${g.variants.map((x) => html`<span class=${'variant' + (g.tried.includes(x) ? ' tried' : '')}>${x}${g.tried.includes(x) ? ' ✓' : ''}</span> `)}</li>`)}</ul>
        <p class="small muted">✓ = already used in a logged search. Variants describe spelling patterns only; they say nothing about origin or identity.</p>
        <${AIAction} task="query_expansion" inputs=${{ person_id: p.id }} label="AI: more variants (multilingual)" /></details>`}
    </section>

    ${p.conflicts.length > 0 && html`<div class="callout tone-warn" role="note"><strong>Conflicting claims (kept, not resolved):</strong>
      <ul>${p.conflicts.map((c) => html`<li>${V.claim_types[c.claim_type]}: ${c.reason}</li>`)}</ul>
      Compare the evidence for each claim below; record your reasoning in each claim's status.</div>`}

    <section class="panel"><div class="panel-head"><h2>Claims & evidence</h2><button class="small" onClick=${() => setModal({ claim: null })}>Add claim</button></div>
      ${p.claims.length === 0 && html`<p class="muted">No claims yet. Add an approximate birth, residence, or death — dates like “abt 1850” are fine.</p>`}
      ${Object.entries(byType).map(([t, cs]) => html`<div class="claim-group"><h3>${V.claim_types[t]}${cs.length > 1 ? ` (${cs.length})` : ''}</h3>
        ${cs.map((c) => html`<div class=${'claim' + (conflictIds.has(c.id) ? ' conflict' : '') + (c.status === 'rejected' ? ' rejected' : '')}>
          <div class="claim-head"><div><strong>${c.date_text || (c.claim_type === 'relationship' ? '' : 'date unknown')}</strong>${c.year_from != null ? html` <span class="muted small">(search window ${years(c.year_from, c.year_to)})</span>` : ''}
            ${c.place_label && html` · ${c.place_label}`}${c.to_place_label && html` → ${c.to_place_label}`}
            ${c.related_person_name && html` · ${V.relationship_types[c.relationship_type]} <a href=${`#/person/${c.related_person_id}`}>${c.related_person_name}</a>`}
            ${c.relationship_qualifier && html` <span class="badge tone-info">${V.relationship_qualifiers[c.relationship_qualifier] || c.relationship_qualifier}</span>`}
            ${c.origin === 'import' && html` <span class="badge tone-muted" title="Imported from a family tree file; not independently verified">imported</span>`}
            ${c.value_text && html` · ${c.value_text}`}</div>
            <span class=${'status s-' + c.status}>${V.claim_statuses[c.status]}</span></div>
          ${c.statement && html`<p class="small">${c.statement}</p>`}
          ${c.status_note && html`<p class="small muted">Status note: ${c.status_note}</p>`}
          <${ClaimEvidence} claim=${c} onChange=${reload} />
          <div class="row"><button class="small secondary" onClick=${() => setModal({ claim: c })}>Edit</button><button class="small link danger" onClick=${() => delClaim(c)}>Delete</button></div>
        </div>`)}</div>`)}
      ${p.incoming_relationships.length > 0 && html`<h3>Named as related by others</h3><ul>${p.incoming_relationships.map((r) => html`<li>
        <a href=${`#/person/${r.person_id}`}>${r.person_name}</a> — ${V.relationship_types[r.relationship_type]} ${p.display_name} (${V.claim_statuses[r.status]})</li>`)}</ul>`}
    </section>

    <section class="panel"><div class="panel-head"><h2>Research questions</h2><button class="small" onClick=${() => setModal('question')}>Add question</button></div>
      ${p.questions.length === 0 ? html`<p class="muted">What do you want to find out about ${p.display_name}?</p>` :
        html`<ul class="list">${p.questions.map((q) => html`<li><div class="list-main"><strong>${q.question}</strong><div class="muted small">${V.question_types[q.question_type]} · ${q.status}</div></div>
          <a class="button small" href=${`#/next?question=${q.id}`}>Suggest searches</a>
          <select aria-label="Question status" value=${q.status} onChange=${async (e) => { await api.patch(`/questions/${q.id}`, { status: e.target.value }); reload(); }}>
            <option value="open">Open</option><option value="answered">Answered</option><option value="on_hold">On hold</option></select></li>`)}</ul>`}
    </section>

    <section class="panel"><div class="panel-head"><h2>Searches logged for ${p.display_name}</h2><a class="small" href=${`#/log?person=${p.id}`}>Open in research log</a></div>
      ${p.log.length === 0 ? html`<p class="muted">None yet.</p>` : html`<ul class="list">${p.log.map((e) => html`<li><div class="list-main">
        <span class=${'outcome o-' + e.outcome}>${L('log_outcomes', e.outcome)}</span> <strong>${e.collection_name || e.resource_text}</strong>
        <div class="muted small">${fmtDate(e.searched_on)} · ${e.query_text}</div></div></li>`)}</ul>`}
    </section>
    ${p.origin === 'import' && html`<${ImportedDataPanel} personId=${p.id} />`}
    <section class="panel"><h2>Notes</h2><p class="prewrap">${p.notes || html`<span class="muted">No notes.</span>`}</p></section>

    ${modal === 'name' && html`<${NameForm} person=${p} onClose=${() => setModal(null)} onSaved=${close} />`}
    ${modal === 'question' && html`<${QuestionForm} person=${p} onClose=${() => setModal(null)} onSaved=${(q) => { setModal(null); nav(`#/next?question=${q.id}`); }} />`}
    ${modal && modal.claim !== undefined && html`<${ClaimForm} person=${p} claim=${modal.claim} people=${people.data || []} onClose=${() => setModal(null)} onSaved=${close} />`}
  </div>`;
}
