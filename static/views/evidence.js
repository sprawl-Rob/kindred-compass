import { html, useState } from '../vendor/preact-htm.js';
import { api, useAsync, useStore, Loading, ErrorBox, Empty, Field, Select, Modal, ExtLink, CopyButton, Tabs, L, fmtDate, toast, errMsg, nav } from '../ui.js';
import { AIAction } from './ai.js';

const today = () => new Date().toISOString().slice(0, 10);

export function SourceForm({ source, initial = {}, onClose, onSaved, linkClaim }) {
  const s = useStore();
  const V = s.meta.vocab;
  const [v, setV] = useState(source ? { ...source } : { record_format: 'unknown', informant_knowledge: 'undetermined', accessed_on: today(), ...initial });
  const [link, setLink] = useState({ stance: 'supports', identity_match: 'uncertain', assessment: 'unassessed', interpretation_note: '' });
  const [dups, setDups] = useState(null);
  const set = (k) => (e) => setV({ ...v, [k]: e && e.target ? e.target.value : e });
  const submit = async (extra = {}) => {
    try {
      let out;
      if (source) out = await api.patch(`/sources/${source.id}`, { ...v, regenerate_citation: !!v.regen });
      else out = await api.post(`/projects/${s.projectId}/sources`, { ...v, ...extra, ...(linkClaim ? { link_claim_id: linkClaim.id, link } : {}) });
      toast('Source saved'); onSaved(out);
    } catch (x) {
      if (x.status === 409 && x.body.code === 'possible_duplicate') setDups(x.body.matches);
      else toast(errMsg(x), 'bad');
    }
  };
  if (dups) {
    return html`<${Modal} title="Possible duplicate source" onClose=${() => setDups(null)}>
      <p>A source with the same URL, or the same title, repository and page, already exists:</p>
      <ul>${dups.map((d) => html`<li><strong>${d.title}</strong> ${d.repository ? '— ' + d.repository : ''} ${d.page_ref ? '(' + d.page_ref + ')' : ''}</li>`)}</ul>
      <p class="small">Nothing is merged automatically. You can keep both and record that this one duplicates the existing source (both keep their own provenance), or save it as a separate source.</p>
      <div class="row end wrap"><button class="secondary" onClick=${() => setDups(null)}>Back</button>
        <button class="secondary" onClick=${() => submit({ allow_duplicate: true })}>Save as separate source</button>
        <button onClick=${() => submit({ duplicate_of_id: dups[0].id })}>Keep both, mark as duplicate</button></div><//>`;
  }
  return html`<${Modal} title=${source ? 'Edit source' : linkClaim ? 'Add evidence for this claim' : 'Add a source'} onClose=${onClose} wide>
    <form class="stack" onSubmit=${(e) => { e.preventDefault(); submit(); }}>
      <div class="grid-2 tight">
        <${Field} label="Title — what the record is" wide><input required value=${v.title || ''} onInput=${set('title')} placeholder="e.g. Death register entry for Josiah Whitcomb, 1903" /><//>
        <${Field} label="Creator / author / informant body"><input value=${v.creator || ''} onInput=${set('creator')} /><//>
        <${Field} label="Repository"><input value=${v.repository || ''} onInput=${set('repository')} /><//>
        <${Field} label="Collection"><input value=${v.collection_name || ''} onInput=${set('collection_name')} /><//>
        <${Field} label="Record date"><input value=${v.record_date_text || ''} onInput=${set('record_date_text')} /><//>
        <${Field} label="Page / image / entry"><input value=${v.page_ref || ''} onInput=${set('page_ref')} /><//>
        <${Field} label="URL"><input type="url" value=${v.url || ''} onInput=${set('url')} placeholder="https://" /><//>
        <${Field} label="Accessed on"><input type="date" value=${v.accessed_on || ''} onInput=${set('accessed_on')} /><//>
        <${Field} label="Record format" hint="Format says nothing about accuracy on its own"><${Select} value=${v.record_format} onChange=${set('record_format')} options=${V.record_formats} /><//>
        <${Field} label="Informant"><input value=${v.informant || ''} onInput=${set('informant')} placeholder="Who supplied the information" /><//>
        <${Field} label="Informant's knowledge"><${Select} value=${v.informant_knowledge} onChange=${set('informant_knowledge')} options=${V.informant_knowledge} /><//>
        <${Field} label="Transcription" wide><textarea rows="4" value=${v.transcription || ''} onInput=${set('transcription')} /><//>
        <${Field} label="Excerpt / abstract" wide><textarea rows="2" value=${v.excerpt || ''} onInput=${set('excerpt')} /><//>
        <${Field} label="Citation" hint="Leave empty to generate one" wide><textarea rows="2" value=${v.citation_text || ''} onInput=${set('citation_text')} /><//>
      </div>
      ${source && html`<label class="check"><input type="checkbox" checked=${!!v.regen} onChange=${(e) => setV({ ...v, regen: e.target.checked })} /> Regenerate citation from fields</label>`}
      ${V.clue_only_formats.includes(v.record_format) && html`<p class="callout tone-warn small">Contributed trees and cemetery memorials are useful clues but are never treated as proof of a relationship.</p>`}
      ${linkClaim && html`<fieldset><legend>How this source bears on the claim</legend><${LinkFields} v=${link} set=${setLink} /></fieldset>`}
      <div class="row end"><button type="button" class="secondary" onClick=${onClose}>Cancel</button><button type="submit">Save source</button></div>
    </form><//>`;
}

function LinkFields({ v, set }) {
  const s = useStore(); const V = s.meta.vocab;
  return html`<div class="row wrap">
    <${Field} label="Stance"><${Select} value=${v.stance} onChange=${(x) => set({ ...v, stance: x })} options=${V.stances} /><//>
    <${Field} label="Is it the same person?"><${Select} value=${v.identity_match} onChange=${(x) => set({ ...v, identity_match: x })} options=${V.identity_match} /><//>
    <${Field} label="Your assessment"><${Select} value=${v.assessment} onChange=${(x) => set({ ...v, assessment: x })} options=${V.assessments} /><//>
    <${Field} label="Interpretation note" wide><textarea rows="2" value=${v.interpretation_note || ''} onInput=${(e) => set({ ...v, interpretation_note: e.target.value })} /><//></div>`;
}

function LinkExisting({ claim, onClose, onSaved }) {
  const s = useStore();
  const srcs = useAsync(() => api.get(`/projects/${s.projectId}/sources`), [s.projectId]);
  const [sid, setSid] = useState('');
  const [v, setV] = useState({ stance: 'supports', identity_match: 'uncertain', assessment: 'unassessed', interpretation_note: '' });
  const save = async (e) => { e.preventDefault(); try { await api.post(`/claims/${claim.id}/evidence`, { source_id: sid, ...v }); onSaved(); } catch (x) { toast(errMsg(x), 'bad'); } };
  return html`<${Modal} title="Link an existing source" onClose=${onClose} wide>
    <form class="stack" onSubmit=${save}>
      <${Field} label="Source"><${Select} required value=${sid} onChange=${setSid} empty="Choose a source…" options=${(srcs.data || []).map((x) => [x.id, x.title])} /><//>
      <${LinkFields} v=${v} set=${setV} />
      <div class="row end"><button type="button" class="secondary" onClick=${onClose}>Cancel</button><button type="submit" disabled=${!sid}>Link source</button></div>
    </form><//>`;
}

export function ClaimEvidence({ claim, onChange }) {
  const s = useStore(); const V = s.meta.vocab;
  const [modal, setModal] = useState(null);
  const sum = claim.evidence_summary;
  const done = () => { setModal(null); onChange(); };
  return html`<div class="evidence">
    ${claim.evidence.length > 0 && html`<ul class="evidence-list">${claim.evidence.map((e) => html`<li class=${'ev ev-' + e.stance}>
      <span class=${'stance st-' + e.stance}>${V.stances[e.stance]}</span>
      <a href=${`#/source/${e.source_id}`}>${e.source_title}</a>
      <span class="muted small"> · ${V.record_formats[e.record_format]} · informant: ${V.informant_knowledge[e.informant_knowledge]} · ${V.identity_match[e.identity_match]} · assessment: ${V.assessments[e.assessment]}</span>
      ${e.interpretation_note && html`<div class="small">${e.interpretation_note}</div>`}
      <button class="small link" onClick=${() => setModal({ edit: e })}>Edit</button>
      <button class="small link danger" onClick=${async () => { await api.del(`/evidence/${e.id}`); onChange(); }}>Unlink</button></li>`)}</ul>`}
    ${sum.warnings.length > 0 && html`<ul class="warnings small">${sum.warnings.map((w) => html`<li>${w}</li>`)}</ul>`}
    <div class="row"><button class="small secondary" onClick=${() => setModal('new')}>Add source as evidence</button>
      <button class="small secondary" onClick=${() => setModal('link')}>Link existing source</button></div>
    ${modal === 'new' && html`<${SourceForm} linkClaim=${claim} onClose=${() => setModal(null)} onSaved=${done} />`}
    ${modal === 'link' && html`<${LinkExisting} claim=${claim} onClose=${() => setModal(null)} onSaved=${done} />`}
    ${modal && modal.edit && html`<${EditLink} link=${modal.edit} onClose=${() => setModal(null)} onSaved=${done} />`}
  </div>`;
}

function EditLink({ link, onClose, onSaved }) {
  const [v, setV] = useState({ ...link });
  const save = async (e) => { e.preventDefault(); try { await api.patch(`/evidence/${link.id}`, v); onSaved(); } catch (x) { toast(errMsg(x), 'bad'); } };
  return html`<${Modal} title="Edit evidence link" onClose=${onClose} wide><form class="stack" onSubmit=${save}><${LinkFields} v=${v} set=${setV} />
    <div class="row end"><button type="button" class="secondary" onClick=${onClose}>Cancel</button><button type="submit">Save</button></div></form><//>`;
}

export function Evidence({ params }) {
  const s = useStore(); const V = s.meta.vocab;
  const [tab, setTab] = useState(params.get('tab') || 'claims');
  const claims = useAsync(() => api.get(`/projects/${s.projectId}/claims`), [s.projectId]);
  const sources = useAsync(() => api.get(`/projects/${s.projectId}/sources`), [s.projectId]);
  const people = useAsync(() => api.get(`/projects/${s.projectId}/persons`), [s.projectId]);
  const [adding, setAdding] = useState(false);
  const names = Object.fromEntries((people.data || []).map((p) => [p.id, p.display_name]));
  return html`<div class="page">
    <header class="page-head"><div><h1>Evidence & citations</h1>
      <p class="lede">Claims (what is asserted) and sources (where it comes from) are kept separate and linked with your assessment. Nothing is decided by record format alone.</p></div>
      <button onClick=${() => setAdding(true)}>Add a source</button></header>
    <${Tabs} tabs=${[['claims', 'Claims'], ['sources', 'Sources']]} active=${tab} onChange=${setTab} />
    ${tab === 'claims' && html`<section class="panel">
      ${claims.loading && !claims.data ? html`<${Loading} />` : (claims.data || []).length === 0 ? html`<${Empty} title="No claims yet">Add claims from a person's page.<//>` :
        html`<table class="table"><thead><tr><th>Person</th><th>Claim</th><th>Status</th><th>Supports</th><th>Contradicts</th><th>Notes</th></tr></thead><tbody>
          ${claims.data.map((c) => html`<tr><td><a href=${`#/person/${c.person_id}`}>${names[c.person_id] || '—'}</a></td>
            <td>${V.claim_types[c.claim_type]}: ${c.date_text || ''} ${c.place_label || ''} ${c.related_person_name ? '· ' + c.related_person_name : ''}</td>
            <td><span class=${'status s-' + c.status}>${V.claim_statuses[c.status]}</span></td>
            <td>${c.evidence_summary.supports}</td><td>${c.evidence_summary.contradicts}</td>
            <td class="small">${c.evidence_summary.warnings.join(' ')}</td></tr>`)}</tbody></table>`}</section>`}
    ${tab === 'sources' && html`<section class="panel">
      ${sources.loading && !sources.data ? html`<${Loading} />` : (sources.data || []).length === 0 ? html`<${Empty} title="No sources yet">Save the records you find, with a citation, then link them to claims.<//>` :
        html`<ul class="list">${sources.data.map((x) => html`<li><div class="list-main"><a href=${`#/source/${x.id}`}><strong>${x.title}</strong></a>
          ${x.duplicate_of_id && html` <span class="badge tone-muted">duplicate of another source</span>`}
          <div class="muted small">${V.record_formats[x.record_format]} · ${x.repository || 'repository not recorded'} · linked to ${x.claim_count} claim(s)</div>
          <div class="small citation">${x.citation_text}</div></div></li>`)}</ul>`}</section>`}
    ${adding && html`<${SourceForm} onClose=${() => setAdding(false)} onSaved=${(src) => { setAdding(false); nav(`#/source/${src.id}`); }} />`}
  </div>`;
}

export function SourcePage({ id }) {
  const s = useStore(); const V = s.meta.vocab;
  const { data: x, error, loading, reload } = useAsync(() => api.get(`/sources/${id}`), [id]);
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState(false);
  if (loading && !x) return html`<div class="page"><${Loading} /></div>`;
  if (error) return html`<div class="page"><${ErrorBox} error=${error} retry=${reload} /></div>`;
  const upload = async (e) => {
    const file = e.target.files[0]; if (!file) return;
    const fd = new FormData(); fd.append('owner_type', 'source'); fd.append('owner_id', x.id); fd.append('file', file);
    setBusy(true);
    try { await api.form(`/projects/${x.project_id}/attachments`, fd); toast('Attachment saved'); reload(); } catch (err) { toast(errMsg(err), 'bad'); }
    setBusy(false); e.target.value = '';
  };
  return html`<div class="page">
    <nav class="crumbs"><a href="#/evidence?tab=sources">Sources</a> / ${x.title}</nav>
    <header class="page-head"><div><h1>${x.title}</h1><p class="muted">${V.record_formats[x.record_format]} · informant knowledge: ${V.informant_knowledge[x.informant_knowledge]}</p></div>
      <div class="row wrap"><button class="secondary" onClick=${() => setEditing(true)}>Edit</button>
        <${AIAction} task="transcription_extraction" inputs=${{ source_id: x.id, attachment_ids: x.attachments.filter((a) => a.mime_type.startsWith('image/') || a.mime_type === 'application/pdf').map((a) => a.id) }} label="AI: transcribe / extract" />
        <button class="link danger" onClick=${async () => { if (confirm('Delete this source? Claim links to it will be removed.')) { await api.del(`/sources/${x.id}`); nav('#/evidence?tab=sources'); } }}>Delete</button></div></header>
    ${x.provenance_note && html`<div class="callout tone-warn">${x.provenance_note}</div>`}
    <section class="panel"><h2>Citation</h2><p class="citation">${x.citation_text}</p><${CopyButton} text=${x.citation_text || ''} label="Copy citation" /></section>
    <div class="grid-2">
      <section class="panel"><h2>Details</h2><table class="kv"><tbody>
        ${[['Creator', x.creator], ['Repository', x.repository], ['Collection', x.collection_name], ['Record date', x.record_date_text], ['Page / image', x.page_ref],
          ['Informant', x.informant], ['Accessed', x.accessed_on]].map(([k, v]) => html`<tr><th scope="row">${k}</th><td>${v || '—'}</td></tr>`)}
        <tr><th scope="row">URL</th><td>${x.url ? html`<${ExtLink} href=${x.url}>${x.url}<//>` : '—'}</td></tr></tbody></table></section>
      <section class="panel"><h2>Claims this source bears on</h2>
        ${x.claims.length === 0 ? html`<p class="muted">Not linked to any claim yet. Link it from a person's claim.</p>` :
          html`<ul>${x.claims.map((c) => html`<li><span class=${'stance st-' + c.stance}>${V.stances[c.stance]}</span> ${c.person_name}: ${V.claim_types[c.claim_type]} ${c.date_text || ''}
            <span class="muted small">(${V.identity_match[c.identity_match]}, ${V.assessments[c.assessment]})</span></li>`)}</ul>`}</section>
    </div>
    ${(x.transcription || x.excerpt) && html`<section class="panel"><h2>Transcription / excerpt</h2><pre class="transcription">${x.transcription}</pre>${x.excerpt && html`<p>${x.excerpt}</p>`}</section>`}
    <section class="panel"><h2>Attachments</h2>
      ${x.attachments.length === 0 && html`<p class="muted small">No attachments. Images, PDFs and text files are stored on this computer.</p>`}
      <ul>${x.attachments.map((a) => html`<li><a href=${`/api/attachments/${a.id}/download`}>${a.original_name}</a> <span class="muted small">${Math.round(a.size_bytes / 1024)} KB · sha256 ${a.sha256.slice(0, 10)}…</span>
        <button class="small link danger" onClick=${async () => { if (confirm('Delete this attachment file?')) { await api.del(`/attachments/${a.id}`); reload(); } }}>Delete</button></li>`)}</ul>
      <label class="button secondary small file-btn">${busy ? 'Uploading…' : 'Attach a file'}<input type="file" class="sr-only" onChange=${upload}
        accept=".pdf,.jpg,.jpeg,.png,.gif,.webp,.tif,.tiff,.txt,.md,.csv,.ged,.docx,.odt,.mp3,.m4a,.wav" /></label></section>
    ${x.possible_duplicates.length > 0 && html`<section class="panel"><h2>Possible duplicates</h2><p class="small">Same URL or same title/repository/page. Both are kept with their own provenance.</p>
      <ul>${x.possible_duplicates.map((d) => html`<li><a href=${`#/source/${d.id}`}>${d.title}</a> <span class="muted small">added ${fmtDate(d.created_at)}</span></li>`)}</ul></section>`}
    ${editing && html`<${SourceForm} source=${x} onClose=${() => setEditing(false)} onSaved=${() => { setEditing(false); reload(); }} />`}
  </div>`;
}
