import { html, useState, useEffect } from '../vendor/preact-htm.js';
import { api, useAsync, useStore, Loading, ErrorBox, Field, Select, Modal, toast, errMsg, nav } from '../ui.js';

const REL = { spouse: 'Spouse', child: 'Child', parent: 'Parent', sibling: 'Brother/sister' };

// Step 2 of capturing: review what was read from the record and choose what to add.
export function Review({ personId, pv, text, onDone, onBack, onSave, extra }) {
  const [src, setSrc] = useState(pv.source);
  const [facts, setFacts] = useState(pv.facts);
  const [people, setPeople] = useState(pv.people);
  const [busy, setBusy] = useState(false);
  const setFact = (i, patch) => setFacts(facts.map((f, j) => (j === i ? { ...f, ...patch } : f)));
  const setPerson = (i, patch) => setPeople(people.map((p, j) => (j === i ? { ...p, ...patch } : p)));
  const save = async () => {
    setBusy(true);
    try {
      const r = onSave ? await onSave({ source: src, facts, people }) : await api.post(`/persons/${personId}/capture/save`, { source: src, facts, people, text });
      const st = r.saved || r;
      toast(`Saved: ${st.facts} fact${st.facts === 1 ? '' : 's'}, ${st.people_added} new ${st.people_added === 1 ? 'person' : 'people'}, ${st.people_linked} linked`);
      onDone(r);
    } catch (x) { toast(errMsg(x), 'bad'); }
    setBusy(false);
  };
  return html`<div class="stack capture-review">
    <section><h3>Source</h3>
      <div class="row wrap"><${Field} label="Record"><input value=${src.title} onInput=${(e) => setSrc({ ...src, title: e.target.value })} /><//>
        <${Field} label="Website"><input value=${src.repository || ''} onInput=${(e) => setSrc({ ...src, repository: e.target.value })} /><//></div>
      <${Field} label="Link to the record"><input value=${src.url || ''} onInput=${(e) => setSrc({ ...src, url: e.target.value })} placeholder="Paste the record page's address" /><//>
      <${Field} label="Citation"><textarea rows="2" value=${src.citation} onInput=${(e) => setSrc({ ...src, citation: e.target.value })} /><//>
    </section>
    <section><h3>Facts about ${pv.person.name}</h3>
      ${facts.length === 0 ? html`<p class="muted small">No dates or places were recognised. You can still save the source.</p>` :
        html`<ul class="capture-list">${facts.map((f, i) => html`<li>
          <label class="check"><input type="checkbox" checked=${f.checked} onChange=${(e) => setFact(i, { checked: e.target.checked })} /> <strong>${f.label}</strong></label>
          <input class="small-input" aria-label="Date" value=${f.date_text || ''} onInput=${(e) => setFact(i, { date_text: e.target.value })} placeholder="date" />
          ${f.claim_type === 'occupation' ? html`<input class="small-input wide" aria-label="Occupation" value=${f.value_text || ''} onInput=${(e) => setFact(i, { value_text: e.target.value })} />` :
            html`<input class="small-input wide" aria-label="Place" value=${f.place || ''} onInput=${(e) => setFact(i, { place: e.target.value })} placeholder="place" />`}
        </li>`)}</ul>`}
    </section>
    ${people.length > 0 && html`<section><h3>Other people in the record</h3>
      <ul class="capture-list">${people.map((p, i) => html`<li>
        <div class="cap-person"><strong>${p.name}</strong> <span class="muted small">${[p.relation_in_record, p.age && `age ${p.age}`, p.birth_place].filter(Boolean).join(' · ')}</span></div>
        <select aria-label=${`What to do with ${p.name}`} value=${p.action} onChange=${(e) => setPerson(i, { action: e.target.value })}>
          ${p.match && html`<option value="link">Same as ${p.match.name} (in your tree)</option>`}
          <option value="add">Add to the tree</option>
          <option value="skip">Skip</option>
        </select>
        ${p.action === 'add' && html`<label class="small">as ${pv.person.name}'s <select value=${p.relationship || ''} onChange=${(e) => setPerson(i, { relationship: e.target.value || null })}>
          <option value="">choose…</option>${Object.entries(REL).map(([k, v]) => html`<option value=${k}>${v.toLowerCase()}</option>`)}</select></label>`}
        ${p.relationship_inferred && p.action !== 'skip' && html`<span class="badge tone-warn small" title="The record doesn't say; same surname and a generation younger in the household">relationship not stated — probably ${REL[p.relationship] && REL[p.relationship].toLowerCase()}</span>`}
      </li>`)}</ul>
      <p class="small muted">New people and relationships are added as tentative, with this record as their source.</p></section>`}
    ${extra || null}
    <div class="row end">${onBack && html`<button class="secondary" onClick=${onBack}>Back</button>`}
      <button disabled=${busy || people.some((p) => p.action === 'add' && !p.relationship)} onClick=${save}>${busy ? 'Saving…' : 'Save to the tree'}</button></div>
  </div>`;
}

// "I found it": paste a record (or receive a clipped page) and add it to a person.
export function CaptureDialog({ person, item, initial, onClose, onDone }) {
  const [text, setText] = useState((initial && initial.text) || '');
  const [url, setUrl] = useState((initial && initial.url) || '');
  const [pv, setPv] = useState(null);
  const [busy, setBusy] = useState(false);
  const read = async () => {
    setBusy(true);
    try { setPv(await api.post(`/persons/${person.id}/capture/preview`, { text, url, title: (initial && initial.title) || (item && item.title) || '' })); }
    catch (x) { toast(errMsg(x), 'bad'); }
    setBusy(false);
  };
  useEffect(() => { if (initial && initial.text) read(); }, []);
  return html`<${Modal} title=${`Add a record you found — ${person.name}`} onClose=${onClose} wide>
    ${!pv ? html`<div class="stack">
      <p class="small">${item ? html`Found the <strong>${item.title}</strong>? ` : ''}On the record page (Ancestry, FamilySearch, American Ancestors…),
        select the record's details — from the title down through the household list — copy, and paste them here. Then copy the page's address into the link box.</p>
      <${Field} label="Record details"><textarea rows="10" value=${text} onInput=${(e) => setText(e.target.value)}
        placeholder=${'Name\tOscar Lindqvist\nAge\t42\nHome in 1920\tFitchburg, Worcester, Massachusetts\n…\nHousehold Members\tName\tAge\n…'} /><//>
      <${Field} label="Link to the record (optional)"><input value=${url} onInput=${(e) => setUrl(e.target.value)} placeholder="https://www.ancestry.com/…" /><//>
      <p class="small muted">Tip: the <a href="#/clip">Clip to Kindred Compass</a> bookmark button does this in one click from the record page.</p>
      <div class="row end"><button class="secondary" onClick=${onClose}>Cancel</button><button disabled=${busy || text.trim().length < 5} onClick=${read}>${busy ? 'Reading…' : 'Read record'}</button></div>
    </div>` : html`<${Review} personId=${person.id} pv=${pv} text=${text} onBack=${() => setPv(null)} onDone=${(r) => { onDone && onDone(r); onClose(); }} />`}
  <//>`;
}

function bookmarklet(origin) {
  const code = `(function(){var f=document.createElement('form');f.method='POST';f.action='${origin}/clip';f.target='_blank';f.acceptCharset='UTF-8';`
    + `[['url',location.href],['title',document.title],['text',(String(window.getSelection())||document.body.innerText).slice(0,150000)]].forEach(function(p){`
    + `var i=document.createElement('textarea');i.name=p[0];i.value=p[1];f.appendChild(i);});f.style.display='none';document.body.appendChild(f);f.submit();f.remove();})();`;
  return 'javascript:' + code;
}

// The page the bookmark button opens: choose who the record is about, then review and save.
export function Clip({ id }) {
  const s = useStore();
  const clip = useAsync(() => (id ? api.get(`/clips/${id}`) : Promise.resolve(null)), [id]);
  const who = useAsync(() => (clip.data ? api.post(`/projects/${s.projectId}/capture/who`, { text: clip.data.text, url: clip.data.url, title: clip.data.title }) : Promise.resolve(null)), [clip.data, s.projectId]);
  const people = useAsync(() => api.get(`/projects/${s.projectId}/persons`), [s.projectId]);
  const [personId, setPersonId] = useState('');
  const [done, setDone] = useState(null);
  useEffect(() => { if (who.data && who.data.candidates.length === 1) setPersonId(who.data.candidates[0].id); }, [who.data]);
  const href = bookmarklet(location.origin);
  const person = (people.data || []).find((p) => p.id === personId);
  return html`<div class="page narrow-page">
    <header class="page-head"><div><h1>Clip a record</h1>
      <p class="lede">Bring a record you're viewing on Ancestry, FamilySearch, American Ancestors or any other site into your tree.</p></div></header>
    ${!id && html`<section class="panel"><h2>Set up the bookmark button (once)</h2>
      <ol>
        <li>Show your browser's bookmarks bar (Chrome/Edge: ⌘⇧B; Safari: View → Show Favorites Bar).</li>
        <li>Drag this button onto the bookmarks bar: <a class="button bookmarklet" href=${href} onClick=${(e) => { e.preventDefault(); toast('Drag the button to your bookmarks bar — clicking it here does nothing'); }}>Clip to Kindred Compass</a></li>
        <li>On a record page, click it. (To clip only part of a page, select that part first.) This app must be running.</li>
      </ol>
      <p class="small muted">The button sends the text of the page you're viewing to this app on your computer — nowhere else — and nothing is added to your tree until you review and save it.
        It only reads what you can already see; it doesn't log in or search for you. If a site blocks it, copy and paste the record instead (“I found it” on a person's checklist).</p></section>`}
    ${id && html`<section class="panel">
      ${clip.loading && !clip.data ? html`<${Loading} />` : clip.error ? html`<${ErrorBox} error=${clip.error} />` : html`
        <p class="small">From <strong>${clip.data.title || clip.data.url}</strong>${who.data && who.data.parsed.fields.name ? html` — about <strong>${who.data.parsed.fields.name}</strong>` : ''}.</p>
        ${done ? html`<div class="callout tone-good">Saved to ${person && person.display_name}. <a href=${`#/person/${personId}`}>Open their page</a></div>` : html`
          <${Field} label="Who is this record about?"><select value=${personId} onChange=${(e) => setPersonId(e.target.value)}>
            <option value="">Choose a person…</option>
            ${who.data && who.data.candidates.length > 0 && html`<optgroup label="Likely matches">${who.data.candidates.map((c) => html`<option value=${c.id}>${c.name} ${c.lifespan || ''}</option>`)}</optgroup>`}
            <optgroup label="Everyone">${(people.data || []).map((p) => html`<option value=${p.id}>${p.display_name}</option>`)}</optgroup></select><//>
          <p class="small muted">Not in your tree yet? Add the person first (People → Add a person), then clip again — or use Search to add them from a record.</p>
          ${person && html`<${CaptureDialog} person=${{ id: person.id, name: person.display_name }} initial=${clip.data} onClose=${() => setPersonId('')} onDone=${(r) => setDone(r)} />`}`}`}
    </section>`}
  </div>`;
}
