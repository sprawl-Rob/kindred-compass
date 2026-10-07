import { html, useState, useEffect, useRef } from '../vendor/preact-htm.js';
import { api, useAsync, useStore, Loading, ErrorBox, Empty, Field, Select, toast, errMsg, nav } from '../ui.js';
import { Review } from './capture.js';
import { AIRunDialog, loadAIConfig } from './ai.js';

const ACCEPT = '.jpg,.jpeg,.png,.tif,.tiff,.heic,.bmp,.gif,.webp,.pdf';
const STATUS = { processing: ['Reading…', 'tone-info'], ready: ['To file', 'tone-warn'], failed: ['Text not read', 'tone-bad'], attached: ['Filed', 'tone-good'] };

export async function uploadFiles(projectId, files, personId) {
  const fd = new FormData();
  [...files].forEach((f) => fd.append('files', f, f.name));
  if (personId) fd.append('person_id', personId);
  const r = await fetch(`/api/projects/${projectId}/documents`, { method: 'POST', body: fd, headers: { 'X-Kindred': '1' } });
  const j = await r.json();
  if (!r.ok) throw new Error(j.detail || 'Upload failed');
  if (j.errors && j.errors.length) toast(j.errors.map((e) => `${e.file}: ${e.error}`).join(' · '), 'bad');
  return j.documents;
}

// A drop area that also opens a file picker when clicked.
export function DropZone({ projectId, personId, label, onUploaded, compact }) {
  const [over, setOver] = useState(false);
  const [busy, setBusy] = useState(false);
  const input = useRef(null);
  const send = async (files) => {
    if (!files || !files.length) return;
    setBusy(true);
    try { const d = await uploadFiles(projectId, files, personId); toast(`${d.length} document${d.length === 1 ? '' : 's'} added — reading the text…`); onUploaded && onUploaded(d); }
    catch (x) { toast(errMsg(x), 'bad'); }
    setBusy(false);
  };
  return html`<div class=${'dropzone' + (over ? ' over' : '') + (compact ? ' compact' : '')} role="button" tabindex="0"
      onClick=${() => input.current && input.current.click()} onKeyDown=${(e) => (e.key === 'Enter' || e.key === ' ') && input.current.click()}
      onDragOver=${(e) => { e.preventDefault(); e.stopPropagation(); setOver(true); }} onDragLeave=${() => setOver(false)}
      onDrop=${(e) => { e.preventDefault(); e.stopPropagation(); setOver(false); send(e.dataTransfer.files); }}>
    <input type="file" multiple accept=${ACCEPT} ref=${input} class="sr-only" onChange=${(e) => { send(e.target.files); e.target.value = ''; }} />
    <strong>${busy ? 'Uploading…' : label || 'Drop documents here'}</strong>
    ${!compact && html`<span class="small muted">Birth, marriage and death certificates, baptism records, letters, photos of records — JPEG, PNG, HEIC, TIFF or PDF.
      Or click to choose files. The text is read on this Mac; nothing is uploaded anywhere.</span>`}
  </div>`;
}

function Thumb({ d }) {
  return html`<div class="doc-thumb">${d.status === 'processing' ? html`<span class="small muted">Reading…</span>` :
    html`<img src=${`/api/documents/${d.id}/page/1`} alt="" loading="lazy" onError=${(e) => { e.target.style.display = 'none'; }} />`}</div>`;
}

export function DocCard({ d }) {
  const [label, tone] = STATUS[d.status] || STATUS.ready;
  const ds = d.detected_summary || {};
  return html`<a class="card doc-card" href=${`#/document/${d.id}`}>
    <${Thumb} d=${d} />
    <div class="doc-meta"><strong>${d.title || d.original_name}</strong>
      <span class="small muted">${d.type_label}${d.pages > 1 ? ` · ${d.pages} pages` : ''}</span>
      <span class=${'badge ' + tone}>${label}</span>
      ${(ds.mentioned || []).length > 0 && html`<span class="small">Names: ${ds.mentioned.join(', ')}</span>`}
      ${d.error && html`<span class="small danger">${d.error}</span>`}</div></a>`;
}

export function Documents() {
  const s = useStore();
  const [filter, setFilter] = useState('inbox');
  const { data, error, loading, reload } = useAsync(() => api.get(`/projects/${s.projectId}/documents${filter === 'inbox' ? '?status=inbox' : ''}`), [s.projectId, filter]);
  const t = useRef(null);
  useEffect(() => {
    clearTimeout(t.current);
    if (data && data.some((d) => d.status === 'processing')) t.current = setTimeout(reload, 1500);
    return () => clearTimeout(t.current);
  }, [data]);
  return html`<div class="page">
    <header class="page-head"><div><h1>Documents</h1>
      <p class="lede">Import certificates, letters and other papers. The app reads the text, works out what each document is and who it names,
        and you file it with a person — adding the facts it shows.</p></div></header>
    <${DropZone} projectId=${s.projectId} onUploaded=${() => { setFilter('inbox'); reload(); }} />
    <div class="seg" role="group" aria-label="Show">
      <button class=${filter === 'inbox' ? 'on' : ''} onClick=${() => setFilter('inbox')}>To file</button>
      <button class=${filter === 'all' ? 'on' : ''} onClick=${() => setFilter('all')}>All documents</button></div>
    <${ErrorBox} error=${error} retry=${reload} />
    ${loading && !data ? html`<${Loading} />` : data && data.length === 0 ? html`<${Empty} title=${filter === 'inbox' ? 'Nothing waiting to be filed' : 'No documents yet'}>Drop files above to start.<//>` :
      data && html`<div class="doc-grid">${data.map((d) => html`<${DocCard} d=${d} key=${d.id} />`)}</div>`}
  </div>`;
}

function AIReading({ d, reload }) {
  const s = useStore();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (!s.ai) loadAIConfig(); }, []);
  const ai = d.ai;
  const use = async () => {
    setBusy(true);
    try { await api.post(`/documents/${d.id}/ai/apply`); toast('Using the AI reading — check it against the image'); reload(); }
    catch (x) { toast(errMsg(x), 'bad'); }
    setBusy(false);
  };
  if (d.status === 'processing') return null;
  return html`<div class="panel ai-reading">
    <div class="panel-head"><h2>AI reading</h2>
      ${s.ai && s.ai.enabled ? html`<button class="small secondary ai-btn" onClick=${() => setOpen(true)}>✧ ${ai ? 'Read again with AI' : 'Read with AI'}</button>` :
        html`<a class="small" href="#/settings/ai">Turn on AI in Settings</a>`}</div>
    ${!ai ? html`<p class="small muted">For forms, faded or handwritten documents the built-in text recognition struggles with, an AI model (your OpenAI or Anthropic key)
        can read the page image. You'll see exactly what is sent before anything leaves this Mac.</p>` : html`
      <p class="small muted">Read ${new Date(ai.at).toLocaleString()}. ${ai.uncertainties && ai.uncertainties.length ? `${ai.uncertainties.length} uncertain reading(s).` : ''} Always check it against the image.</p>
      ${(ai.fields || []).length > 0 && html`<dl class="kv small">${ai.fields.map((f) => html`<dt>${f.label}</dt><dd>${f.value}</dd>`)}</dl>`}
      ${(ai.people || []).length > 0 && html`<p class="small"><strong>People:</strong> ${ai.people.map((p) => `${p.name}${p.role ? ` (${p.role})` : ''}`).join('; ')}</p>`}
      ${(ai.uncertainties || []).length > 0 && html`<details class="small"><summary>Uncertain readings</summary><ul>${ai.uncertainties.map((u) => html`<li>${u}</li>`)}</ul></details>`}
      <details class="small"><summary>AI transcription</summary><pre class="transcription">${ai.transcription}</pre></details>
      <div class="row wrap"><button class="small" disabled=${busy || d.text === ai.transcription} onClick=${use}>${d.text === ai.transcription ? 'In use' : 'Use the AI reading'}</button>
        <span class="small muted">Replaces the text below (you can still edit it) and uses the AI's fields for filing.</span></div>`}
    ${open && html`<${AIRunDialog} task="document_reading" inputs=${{ document_id: d.id }} label=${`Read “${d.title || d.original_name}” with AI`}
      onClose=${() => setOpen(false)} onFinished=${() => { toast('AI reading ready'); reload(); }} />`}
  </div>`;
}

export function DocumentPage({ id }) {
  const s = useStore();
  const { data: d, error, loading, reload } = useAsync(() => api.get(`/documents/${id}`), [id]);
  const people = useAsync(() => api.get(`/projects/${s.projectId}/persons`), [s.projectId]);
  const [text, setText] = useState(null);
  const [personId, setPersonId] = useState('');
  const [pv, setPv] = useState(null);
  const [also, setAlso] = useState({});
  const t = useRef(null);
  useEffect(() => {
    clearTimeout(t.current);
    if (d && d.status === 'processing') t.current = setTimeout(reload, 1500);
    if (d && text === null && d.status !== 'processing') setText(d.text || '');
    if (d && !personId) setPersonId((d.detected.subjects || [])[0] || d.person_ids[0] || '');
    return () => clearTimeout(t.current);
  }, [d]);
  useEffect(() => {
    setPv(null);
    if (!personId || !d || d.status === 'processing') return;
    api.get(`/documents/${id}/attach-preview?person_id=${personId}`).then((r) => {
      setPv(r); setAlso(Object.fromEntries((r.also_mentioned || []).map((m) => [m.id, false])));
    }, (x) => toast(errMsg(x), 'bad'));
  }, [personId, d && d.updated_at]);
  if (loading && !d) return html`<div class="page"><${Loading} /></div>`;
  if (error) return html`<div class="page"><${ErrorBox} error=${error} retry=${reload} /></div>`;
  const det = d.detected || {};
  const saveText = async () => {
    try { await api.patch(`/documents/${id}`, { transcription: text }); toast('Text saved — re-read the document'); reload(); }
    catch (x) { toast(errMsg(x), 'bad'); }
  };
  const setType = async (v) => { try { await api.patch(`/documents/${id}`, { doc_type: v }); reload(); } catch (x) { toast(errMsg(x), 'bad'); } };
  const setTitle = async (v) => { try { await api.patch(`/documents/${id}`, { title: v }); reload(); } catch (x) { toast(errMsg(x), 'bad'); } };
  const remove = async () => {
    if (!confirm('Delete this document? If it was filed, its source and the facts you added stay.')) return;
    await api.del(`/documents/${id}`); nav('#/documents');
  };
  const pages = Array.from({ length: Math.max(1, d.pages || 1) }, (_, i) => i + 1);
  const subjects = new Set(det.subjects || []);
  const mentioned = det.mentioned || [];
  return html`<div class="page wide-page">
    <nav class="crumbs"><a href="#/documents">Documents</a> / ${d.title || d.original_name}</nav>
    <div class="doc-layout">
      <section class="doc-view">
        ${d.status === 'processing' ? html`<p class="muted">Reading the document…</p>` :
          pages.map((n) => html`<img src=${`/api/documents/${id}/page/${n}`} alt=${`Page ${n} of ${d.title || d.original_name}`} loading="lazy" />`)}
        <p class="small"><a href=${`/api/documents/${id}/file`} target="_blank" rel="noopener">Open the original file ↗</a> · ${d.original_name}</p>
      </section>
      <section class="doc-side">
        <div class="panel">
          <${Field} label="Title"><input value=${d.title || ''} onChange=${(e) => setTitle(e.target.value)} /><//>
          <div class="row wrap">
            <${Field} label="What it is"><${Select} value=${d.doc_type || 'other'} onChange=${setType} options=${{ birth: 'Birth certificate / record', baptism: 'Baptism record',
              marriage: 'Marriage certificate / record', death: 'Death certificate / record', burial: 'Burial / cemetery record', obituary: 'Obituary / clipping',
              letter: 'Letter', naturalization: 'Naturalization papers', immigration: 'Passenger / immigration record', military: 'Military record',
              census: 'Census page', photo: 'Photograph', other: 'Other document' }} /><//>
            <span class=${'badge ' + (STATUS[d.status] || STATUS.ready)[1]}>${(STATUS[d.status] || STATUS.ready)[0]}</span></div>
          ${d.error && html`<p class="callout tone-bad small">${d.error}</p>`}
          ${(det.dates || []).length + (det.places || []).length + mentioned.length > 0 && html`<dl class="kv small">
            ${mentioned.length > 0 && html`<dt>Names in your tree</dt><dd>${mentioned.map((m, i) => html`${i ? ', ' : ''}<a href=${`#/person/${m.id}`}>${m.name}</a>`)}</dd>`}
            ${(det.dates || []).length > 0 && html`<dt>Dates</dt><dd>${det.dates.join(' · ')}</dd>`}
            ${(det.places || []).length > 0 && html`<dt>Places</dt><dd>${det.places.join(', ')}</dd>`}
          </dl>`}
        </div>
        <${AIReading} d=${d} reload=${() => { setText(null); reload(); }} />
        <div class="panel">
          <div class="panel-head"><h2>Text</h2><span class="small muted">${d.ocr_engine ? `Read by ${d.ocr_engine}${d.ocr_confidence != null && d.ocr_confidence < 0.6 ? ' — low confidence, check carefully' : ''}` : ''}</span></div>
          <textarea class="doc-text" rows="14" value=${text ?? ''} onInput=${(e) => setText(e.target.value)} placeholder=${d.status === 'processing' ? 'Reading…' : 'No text was recognised. Type what the document says, then save.'} />
          <div class="row wrap"><button class="small" disabled=${text === null || text === d.text} onClick=${saveText}>Save corrected text</button>
            <button class="small secondary" onClick=${async () => { await api.post(`/documents/${id}/reprocess`); setText(null); reload(); }}>Read again</button>
            <span class="small muted">Correcting names and dates here improves what's found below.</span></div>
        </div>
        <div class="panel">
          <h2>${d.status === 'attached' ? 'Filed with' : 'File it with a person'}</h2>
          ${d.status === 'attached' && html`<p class="small">${d.people.map((p, i) => html`${i ? ', ' : ''}<a href=${`#/person/${p.id}`}>${p.display_name}</a>`)}. You can file it with someone else too.</p>`}
          <${Field} label="Who is this document about?"><select value=${personId} onChange=${(e) => setPersonId(e.target.value)}>
            <option value="">Choose a person…</option>
            ${mentioned.length > 0 && html`<optgroup label="Named in the document">${mentioned.map((m) => html`<option value=${m.id}>${m.name} ${m.lifespan || ''}${subjects.has(m.id) ? ' — the subject' : ''}</option>`)}</optgroup>`}
            <optgroup label="Everyone">${(people.data || []).map((p) => html`<option value=${p.id}>${p.display_name}</option>`)}</optgroup></select><//>
          ${personId && !pv && html`<${Loading} what="Reading the facts" />`}
          ${pv && html`<${Review} personId=${personId} pv=${pv} text=${text}
            extra=${(pv.also_mentioned || []).length > 0 && html`<section><h3>Also note it on</h3>
              <p class="small muted">Adds this document to these people's sources as “mentions” (no facts).</p>
              ${pv.also_mentioned.map((m) => html`<label class="check"><input type="checkbox" checked=${!!also[m.id]} onChange=${(e) => setAlso({ ...also, [m.id]: e.target.checked })} /> ${m.name}</label>`)}</section>`}
            onSave=${(b) => api.post(`/documents/${id}/attach`, { person_id: personId, ...b, also: Object.keys(also).filter((k) => also[k]) })}
            onDone=${() => { reload(); }} />`}
        </div>
        <p><button class="small link danger" onClick=${remove}>Delete document</button></p>
      </section>
    </div>
  </div>`;
}
