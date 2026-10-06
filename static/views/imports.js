import { html, useState } from '../vendor/preact-htm.js';
import { api, useAsync, useStore, Loading, ErrorBox, Empty, Field, Select, toast, errMsg, nav, fmtDate } from '../ui.js';
import { loadProjects } from '../app.js';

const STATUS = { previewed: 'Preview — nothing imported yet', committed: 'Imported', undone: 'Undone', discarded: 'Discarded', failed: 'Failed' };
const MEDIA_STATUS = {
  matched: 'Matched to a supplied file', missing: 'Not found in the supplied files', ambiguous: 'Several possible files — needs your choice',
  remote_not_fetched: 'Online reference — not downloaded', unsupported_type: 'File type not accepted', not_supplied: 'No media files were supplied',
  not_in_export: 'Held on Ancestry — file not in the export',
};

export function SnapshotNote() {
  return html`<div class="callout tone-info"><strong>A snapshot, not a sync.</strong> Importing copies what is in the exported file at the moment you
    exported it. Nothing here is connected to Ancestry: edits on either side do not flow to the other. To bring in later changes, export again and run a
    repeat import of the same tree — earlier imports are recognised and your local edits are kept.</div>`;
}

export function GedcomLines({ lines, max = 60 }) {
  if (!lines || !lines.length) return html`<p class="muted small">No original lines recorded.</p>`;
  return html`<div class="gedcom" role="region" aria-label="Original GEDCOM lines" tabindex="0">${lines.slice(0, max).map(([n, t]) => html`<div class="gl"><span class="ln">${String(n).padStart(5, '\u00a0')}</span>${'\u00a0'}${t}</div>`)}${lines.length > max ? html`<div class="gl muted">… ${lines.length - max} more lines</div>` : ''}</div>`;
}

function flatLines(nodes) {
  const out = [];
  const walk = (n) => { (n.raw || []).forEach((r) => out.push(r)); (n.children || []).forEach(walk); };
  (nodes || []).forEach(walk);
  return out.sort((a, b) => a[0] - b[0]);
}

export function Imports() {
  const s = useStore();
  const { data, error, loading, reload } = useAsync(() => api.get('/imports'), []);
  const [busy, setBusy] = useState(false);
  const [target, setTarget] = useState('');
  const [projectName, setProjectName] = useState('');
  const submit = async (e) => {
    e.preventDefault();
    const f = e.target;
    const ged = f.gedcom.files[0];
    if (!ged) { toast('Choose a GEDCOM file', 'bad'); return; }
    const fd = new FormData();
    fd.append('gedcom', ged);
    for (const file of f.media_folder.files) { fd.append('media', file); fd.append('media_path', file.webkitRelativePath || file.name); }
    for (const file of f.media_zip.files) { fd.append('media', file); fd.append('media_path', file.name); }
    if (target) fd.append('lineage_id', target);
    if (projectName) fd.append('project_name', projectName);
    setBusy(true);
    try { const b = await api.form('/imports', fd); nav(`#/import/${b.id}`); } catch (x) { toast(errMsg(x), 'bad'); }
    setBusy(false);
  };
  const lineages = (data && data.lineages) || [];
  return html`<div class="page">
    <header class="page-head"><div><h1>Import a family tree</h1>
      <p class="lede">Bring in research from Ancestry, Family Tree Maker, RootsMagic or any GEDCOM file. You'll see a full preview before anything is imported,
      and the first import goes into its own separate project that you can undo.</p></div></header>
    <${SnapshotNote} />
    <div class="grid-2">
      <section class="panel"><h2>1. Choose files</h2>
        <form class="stack" onSubmit=${submit}>
          <${Field} label="GEDCOM export (.ged), or a ZIP containing one (.zip, .gdz)"><input name="gedcom" type="file" accept=".ged,.gedcom,.zip,.gdz" required /><//>
          <${Field} label="Media folder (optional)" hint="Pick the folder your desktop program exported with the tree, e.g. “Ferris Media”. Only files the GEDCOM refers to are attached.">
            <input name="media_folder" type="file" webkitdirectory multiple /><//>
          <${Field} label="…or a media ZIP (optional)"><input name="media_zip" type="file" accept=".zip" multiple /><//>
          <${Field} label="Import as">
            <${Select} value=${target} onChange=${(v) => setTarget(v || '')} empty="A new, separate project (first import of this tree)"
              options=${lineages.map((l) => [l.id, `Update of earlier import: ${l.tree_label} (${l.project_name})`])} /><//>
          ${!target && html`<${Field} label="Project name (optional)"><input value=${projectName} onInput=${(e) => setProjectName(e.target.value)} placeholder="Imported: <tree name> (<date> snapshot)" /><//>`}
          <div class="row end"><button type="submit" disabled=${busy}>${busy ? 'Reading file…' : 'Preview import'}</button></div>
          <p class="small muted">Files stay on this computer. Online media links in the file are listed but never downloaded.</p>
        </form></section>
      <section class="panel"><h2>Exporting from Ancestry</h2><${AncestryHelp} /></section>
    </div>
    <section class="panel"><h2>Import history</h2>
      <${ErrorBox} error=${error} retry=${reload} />
      ${loading && !data ? html`<${Loading} />` : !data.imports.length ? html`<p class="muted">No imports yet.</p>` :
        html`<div class="table-wrap"><table class="table"><thead><tr><th>File</th><th>From</th><th>Status</th><th>Project</th><th>When</th><th>Review</th></tr></thead><tbody>
          ${data.imports.map((b) => html`<tr><td><a href=${`#/import/${b.id}`}>${b.original_filename}</a></td><td>${b.product || '—'}${b.tree_label ? ' · ' + b.tree_label : ''}</td>
            <td>${STATUS[b.status] || b.status}</td><td>${b.project_name || '—'}</td><td>${fmtDate(b.committed_at || b.created_at)}</td>
            <td>${b.review_pending ? html`<span class="badge tone-warn">${b.review_pending} to review</span>` : ''}</td></tr>`)}</tbody></table></div>`}
    </section>
  </div>`;
}

function AncestryHelp() {
  return html`<ol class="small steps">
    <li>On Ancestry: <strong>Trees</strong> → choose the tree → <strong>More (⋯)</strong> → <strong>Tree Settings</strong> → <strong>Export tree</strong> →
      <strong>Export</strong>, then <strong>Download Your GEDCOM File</strong>. Only the tree owner can export.</li>
    <li>Ancestry delivers the GEDCOM <strong>inside a ZIP</strong>. You can import the ZIP directly.</li>
    <li>The export contains people, names, facts, relationships (including adopted and step), notes, sources and citations with Ancestry record references.
      <strong>It does not contain your photos, documents or stories</strong> — only their Ancestry media ids. Ancestry has no "download all media" option; you can
      save items one by one, or sync the tree to Family Tree Maker or RootsMagic and export from there with a media folder, then supply that folder here.</li>
    <li>DNA results are not in a tree export. Raw DNA data is a separate download (DNA Settings); Ancestry says DNA match lists cannot be exported.</li>
    <li>The export has no privacy option, so living people are included. This app keeps anyone without a recorded death private by default.</li>
  </ol><p class="small muted">Sources: Ancestry help pages and real exports — see docs/ancestry-import.md.</p>`;
}

function Counts({ c }) {
  const items = [['people', 'People'], ['families', 'Families'], ['relationships_parent_child', 'Parent–child links'], ['relationships_partner', 'Partnerships'],
    ['events_and_facts', 'Events & facts'], ['names', 'Names'], ['sources', 'Sources'], ['citations', 'Citations'], ['repositories', 'Repositories'],
    ['notes', 'Notes'], ['media_references', 'Media references'], ['media_remote_refs', '…of which online only (not in the file)'], ['supplied_files', 'Media files supplied'],
    ['ancestry_record_ids', 'Ancestry record references'], ['parse_failures', 'Lines that could not be parsed']];
  return html`<div class="count-grid">${items.map(([k, l]) => html`<div class=${'count' + (k === 'parse_failures' && c[k] ? ' bad' : '')}><span class="stat-n">${c[k] ?? 0}</span><span class="small">${l}</span></div>`)}</div>`;
}

function Profile({ p, personId }) {
  return html`<article class="panel profile">
    <div class="panel-head"><h3>${p.name} <span class="muted small">${p.xref}</span></h3>
      ${personId && html`<a class="button small secondary" href=${`#/person/${personId}`}>Open imported person</a>`}</div>
    <p class="small"><strong>Why shown:</strong> ${p.why}</p>
    <div class="side-by-side">
      <div><h4>As it will be imported</h4>
        <ul class="small">${p.names.map((n) => html`<li>Name (${n.type}): ${n.text}</li>`)}
          ${p.facts.map((f) => html`<li>${f.label}: <strong>${f.date || 'no date'}</strong> <span class="muted">(${f.qualifier})</span>${f.place ? ' · ' + f.place : ''}${f.value ? ' · ' + f.value : ''}${f.citations ? ` · ${f.citations} citation(s)` : ''}</li>`)}
          ${p.parents.map((r) => html`<li>Child of ${r.parent} (${r.role}) — <strong>${r.qualifier}</strong>${r.raw ? ` (file says “${r.raw}”)` : ''}</li>`)}
          ${p.partners ? html`<li>${p.partners} partnership(s)</li>` : ''}${p.media ? html`<li>${p.media} media reference(s)</li>` : ''}</ul></div>
      <div><h4>Original lines in the file</h4><${GedcomLines} lines=${p.original_lines} /></div>
    </div></article>`;
}

function ReviewItem({ it, onDone }) {
  const [choice, setChoice] = useState('');
  const d = it.detail || {};
  const decide = async (accept) => {
    try { await api.post(`/imports/review/${it.id}/decide`, { accept, choice: choice || null }); onDone(); } catch (x) { toast(errMsg(x), 'bad'); }
  };
  const labels = {
    uncertain_match: ['Same person — move these facts onto the earlier person', 'Different people — keep separate'],
    conflicting_change: ['Use the exported value', 'Keep my local value'],
    removed_in_source: ['Mark the claim as rejected (kept for the record)', 'Keep it unchanged'],
    ambiguous_media: ['Attach the chosen file', 'Leave unattached'],
  }[it.kind] || ['Accept', 'Reject'];
  return html`<li class="review-item"><div><span class="badge tone-warn">${it.kind.replace(/_/g, ' ')}</span> ${it.summary}</div>
    ${d.reasons && html`<div class="small muted">${d.reasons.join('; ')}</div>`}
    ${it.kind === 'conflicting_change' && html`<div class="small">Yours: <code>${String(d.local)}</code> · Earlier import: <code>${String(d.previous_import)}</code> · New export: <code>${String(d.new_import)}</code></div>`}
    ${it.entity_type === 'person' && it.entity_id && it.status === 'pending' && it.kind !== 'ambiguous_media' && html`<a class="small" href=${`#/person/${it.entity_id}`}>Open person</a>`}
    ${it.kind === 'ambiguous_media' && it.status === 'pending' && html`<${Field} label="Which file?"><${Select} value=${choice} onChange=${(v) => setChoice(v || '')} empty="Choose…" options=${d.candidates.map((c) => [c, c])} /><//>`}
    ${it.status === 'pending' ? html`<div class="row"><button class="small" onClick=${() => decide(true)} disabled=${it.kind === 'ambiguous_media' && !choice}>${labels[0]}</button>
      <button class="small secondary" onClick=${() => decide(false)}>${labels[1]}</button></div>` : html`<p class="small"><strong>${it.status}</strong> — ${it.resolution}</p>`}
  </li>`;
}

export function ImportBatch({ id }) {
  const { data: b, error, loading, reload } = useAsync(() => api.get(`/imports/${id}`), [id]);
  const lin = useAsync(() => api.get('/imports'), []);
  const [busy, setBusy] = useState(null);
  if (loading && !b) return html`<div class="page"><${Loading} /></div>`;
  if (error) return html`<div class="page"><${ErrorBox} error=${error} retry=${reload} /></div>`;
  const p = b.plan || {};
  const r = b.report || {};
  const d = p.detection || {};
  const act = async (name, fn) => { setBusy(name); try { await fn(); } catch (x) { toast(errMsg(x), 'bad'); } setBusy(null); reload(); };
  const commit = () => act('commit', async () => {
    if (!confirm(b.lineage_id ? 'Import into the existing project for this tree? A backup is made first; local edits are kept.' :
      'Import into a new, separate project? A backup is made first and you can undo the import afterwards.')) return;
    const out = await api.post(`/imports/${b.id}/commit`);
    await loadProjects(out.project_id);
    toast('Imported — now check the report and the representative profiles');
  });
  const undo = () => act('undo', async () => {
    if (!confirm(b.created_project ? 'Undo this import? The imported project and its attachments are deleted (a backup is made first).' :
      'Undo this repeat import? Rows it added are removed and rows it changed are restored, except anything you edited since.')) return;
    const out = await api.post(`/imports/${b.id}/undo`);
    await loadProjects();
    toast(out.kept_because_edited.length ? `Undone. ${out.kept_because_edited.length} row(s) kept because you edited them.` : 'Import undone');
  });
  const addMedia = (e) => act('media', async () => {
    const fd = new FormData();
    for (const file of e.target.files) { fd.append('media', file); fd.append('media_path', file.webkitRelativePath || file.name); }
    await api.form(`/imports/${b.id}/media`, fd);
    e.target.value = '';
  });
  const media = (b.status === 'committed' ? null : p.media) || {};
  const reportMedia = r.media || [];
  const pending = (b.review || []).filter((x) => x.status === 'pending');
  return html`<div class="page">
    <nav class="crumbs"><a href="#/import">Import</a> / ${b.original_filename}</nav>
    <header class="page-head"><div><h1>${b.original_filename}</h1>
      <p class="muted">${d.product_label || ''}${d.tree_name ? ' · tree “' + d.tree_name + '”' : ''} · ${STATUS[b.status] || b.status}${b.committed_at ? ' ' + fmtDate(b.committed_at) : ''}</p></div>
      <div class="row wrap">
        ${b.status === 'previewed' && html`<button onClick=${commit} disabled=${busy}>${busy === 'commit' ? 'Importing…' : b.lineage_id ? 'Import as repeat import' : 'Import into a new project'}</button>
          <button class="secondary" onClick=${() => act('discard', async () => { await api.post(`/imports/${b.id}/discard`); nav('#/import'); })}>Discard</button>`}
        ${b.status === 'committed' && b.project_id && html`<button class="secondary" onClick=${async () => { await loadProjects(b.project_id); nav('#/people'); }}>Open project</button>`}
        ${b.status === 'committed' && html`<button class="danger" disabled=${!b.can_undo || busy} title=${b.can_undo ? '' : 'Undo the later import of this tree first'} onClick=${undo}>Undo import</button>`}
        <a class="button secondary" href=${`/api/imports/${b.id}/report.json`} download>Download report</a>
        <a class="button secondary" href=${`/api/imports/${b.id}/original`} download>Original file</a></div></header>
    <${SnapshotNote} />

    ${b.status === 'committed' && html`<section class=${'panel ' + (r.checked_at ? '' : 'attention')}>
      <h2>Is the migration complete?</h2>
      <p>${r.checked_at ? html`You checked this import on ${fmtDate(r.checked_at)}.` :
        html`<strong>Not yet confirmed.</strong> Review the report below and open each representative profile to compare it with the original lines before treating this migration as complete.`}</p>
      ${pending.length > 0 && html`<p class="callout tone-warn small">${pending.length} item(s) still need your review.</p>`}
      <label class="check"><input type="checkbox" checked=${!!r.checked_at} onChange=${(e) => act('check', () => api.post(`/imports/${b.id}/checked`, { checked: e.target.checked }))} />
        I have checked the import report and the representative profiles</label></section>`}

    <section class="panel"><h2>What was detected</h2>
      <table class="kv small"><tbody>
        <tr><th scope="row">Exported by</th><td>${d.source || 'not stated'}${d.source_version ? ' ' + d.source_version : ''}</td></tr>
        <tr><th scope="row">Tree</th><td>${d.tree_name || '—'}${d.tree_id ? ` (id ${d.tree_id})` : ''}</td></tr>
        <tr><th scope="row">GEDCOM version</th><td>${d.gedcom_version}</td></tr>
        <tr><th scope="row">Character set</th><td>${d.declared_charset || 'not declared'} → read as ${d.encoding}</td></tr>
        <tr><th scope="row">Lines</th><td>${d.lines}${d.trailer ? '' : ' (no end-of-file marker!)'}</td></tr>
        ${d.gedcom_member && html`<tr><th scope="row">File inside ZIP</th><td>${(d.archive_members || []).length > 1 && b.status === 'previewed' ?
          html`<${Select} value=${d.gedcom_member} onChange=${(v) => act('member', () => api.post(`/imports/${b.id}/member`, { member: v }))} options=${d.archive_members.map((m) => [m, m])} />
            <div class="small muted">The archive contains ${d.archive_members.length} GEDCOM files — choose the one to import.</div>` : d.gedcom_member}</td></tr>`}
        <tr><th scope="row">Original file</th><td>stored unchanged (SHA-256 <code>${b.sha256.slice(0, 16)}…</code>)</td></tr></tbody></table></section>

    <section class="panel"><h2>${b.status === 'committed' ? 'Import report' : 'Preview'}</h2>
      <${Counts} c=${p.counts || {}} />
      ${p.relationship_qualifiers && Object.keys(p.relationship_qualifiers).length > 0 && html`<p class="small">Parent–child relationship types: ${Object.entries(p.relationship_qualifiers).map(([k, v]) => `${k} ${v}`).join(' · ')}</p>`}
      ${b.status === 'committed' && r.stats && html`<h3>What happened</h3><ul class="small stats-list">${Object.entries(r.stats).map(([k, v]) => html`<li>${k.replace(/_/g, ' ')}: <strong>${v}</strong></li>`)}</ul>
        <p class="small muted">Safety backup: ${r.safety_backup}. Took ${r.elapsed_seconds}s.</p>`}
    </section>

    ${p.repeat && html`<section class="panel"><h2>Repeat import of “${p.repeat.lineage_label}”</h2>
      ${!p.repeat.tree_key_matches && html`<p class="callout tone-warn small">This file's header does not look like the same tree as the earlier import. Check you chose the right one.</p>`}
      <p class="small">${p.repeat.note}</p>
      <p>Unchanged ${p.repeat.stats.unchanged} · changed ${p.repeat.stats.changed} · new ${p.repeat.stats.new} · uncertain ${p.repeat.stats.uncertain} · no longer in export ${p.repeat.missing_count}</p>
      ${p.repeat.uncertain.length > 0 && html`<h3>Uncertain matches (imported separately, then reviewed)</h3><ul class="small">${p.repeat.uncertain.map((u) => html`<li>${u.name} (${u.xref}) ↔ ${u.candidate}: ${u.reasons.join('; ')}</li>`)}</ul>`}</section>`}
    ${b.status === 'previewed' && !p.repeat && lin.data && lin.data.lineages.length > 0 && html`<section class="panel subtle small">
      <${Field} label="Is this a newer export of a tree you imported before?"><${Select} value=${b.lineage_id} empty="No — import as a new, separate project"
        onChange=${(v) => act('lineage', () => api.post(`/imports/${b.id}/lineage`, { lineage_id: v }))}
        options=${lin.data.lineages.map((l) => [l.id, `${l.tree_label} (${l.project_name})`])} /><//></section>`}

    ${(b.review || []).length > 0 && html`<section class="panel"><h2>Review (${pending.length} pending)</h2>
      <p class="small muted">Nothing here was merged or overwritten automatically. Your decision is recorded.</p>
      <ul class="review-list">${b.review.map((it) => html`<${ReviewItem} it=${it} onDone=${reload} />`)}</ul></section>`}

    <section class="panel"><h2>Representative profiles to check</h2>
      <p class="small muted">Chosen to cover the harder cases. Compare what the app will store (left) with the original file (right).</p>
      ${((b.status === 'committed' ? r.profiles : p.profiles) || []).map((pr) => html`<${Profile} p=${pr} personId=${pr.person_id} />`)}</section>

    <section class="panel"><h2>Media</h2>
      ${b.status === 'previewed' && html`<p class="small">Supplied: ${(media.sources || []).map((x) => `${x.kind} “${x.name}” (${x.files} files)`).join('; ') || 'none'}.
        <label class="button small secondary file-btn">Add media folder…<input type="file" class="sr-only" webkitdirectory multiple onChange=${addMedia} /></label>
        <label class="button small secondary file-btn">Add media ZIP…<input type="file" class="sr-only" accept=".zip" onChange=${addMedia} /></label></p>`}
      <p class="small">${Object.entries(b.status === 'committed' ? (r.media_summary || {}) : (media.summary || {})).map(([k, v]) => `${MEDIA_STATUS[k] || k}: ${v}`).join(' · ') || 'No media references in this file.'}</p>
      ${(b.status === 'committed' ? reportMedia.length : (media.items || []).length) > 0 && html`<details><summary>All media references</summary><div class="table-wrap"><table class="table small"><thead><tr><th>Reference in file</th><th>Belongs to</th><th>Result</th><th>Details</th></tr></thead><tbody>
        ${(b.status === 'committed' ? reportMedia.map((m) => ({ file_ref: m.file_ref, owner: `${m.owner_type} ${m.owner_xref || ''}`, status: m.status, how: m.matched_path || m.note }))
          : media.items.map((m) => ({ file_ref: m.file_ref, owner: `${m.owner_kind} ${m.owner_xref || ''}`, status: m.status, how: m.path ? `${m.path} — ${m.how}` : m.how })))
          .map((m) => html`<tr><td><code>${m.file_ref}</code></td><td>${m.owner}</td><td>${MEDIA_STATUS[m.status] || m.status}</td><td>${m.how}</td></tr>`)}</tbody></table></div></details>`}
      ${(media.unreferenced_count || 0) > 0 && html`<p class="small muted">${media.unreferenced_count} supplied file(s) are not referenced by the GEDCOM and will not be attached to anyone.</p>`}
      ${(media.skipped || []).length > 0 && html`<p class="small callout tone-warn">Skipped for safety: ${media.skipped.map((x) => `${x.name} (${x.reason})`).join('; ')}</p>`}
    </section>

    <section class="panel"><h2>Unsupported content (kept in the original record, not discarded)</h2>
      ${(p.unsupported || []).length === 0 ? html`<p class="small muted">Every tag in this file was mapped.</p>` :
        html`<div class="table-wrap"><table class="table small"><thead><tr><th>Tag path</th><th>Count</th><th>Example (line)</th></tr></thead><tbody>
          ${p.unsupported.map((u) => html`<tr><td><code>${u.path}</code></td><td>${u.count}</td><td><code>${u.example && u.example.text}</code> (${u.example && u.example.line})</td></tr>`)}</tbody></table></div>`}
      ${(p.vendor_tags_mapped || []).length > 0 && html`<details><summary>Program-specific tags that were understood</summary><ul class="small">${p.vendor_tags_mapped.map((v) => html`<li>${v.mapping}: ${v.count}</li>`)}</ul></details>`}
    </section>

    ${((p.warnings || []).length > 0 || (p.failures || []).length > 0) && html`<section class="panel"><h2>Warnings & parsing problems</h2>
      ${(p.failures || []).length > 0 && html`<h3>Lines that could not be parsed (${p.failures.length})</h3><ul class="small">${p.failures.slice(0, 100).map((f) => html`<li>Line ${f.line}: <code>${f.text}</code> — ${f.reason}</li>`)}</ul>`}
      ${(p.warnings || []).length > 0 && html`<details open=${p.warnings.length < 6}><summary>${p.warnings.length} warning(s)</summary><ul class="small">${p.warnings.map((w) => html`<li>${w}</li>`)}</ul></details>`}</section>`}

    ${p.export_contents && html`<section class="panel"><h2>What this file contains — and what it doesn't</h2>
      <p class="small">Present in this export: ${p.export_contents.present.map((k) => ({ events_and_facts: 'events & facts', media_references: 'media references' }[k] || k)).join(', ') || 'nothing recognisable'}. Media files supplied: ${p.export_contents.local_media_files_in_export};
        online media references (not downloaded): ${p.export_contents.remote_media_references}.</p>
      ${p.export_contents.not_in_export && html`<h3>Not included in an Ancestry tree export — needs a separate transfer</h3><ul class="small">${p.export_contents.not_in_export.map((x) => html`<li>${x}</li>`)}</ul>`}</section>`}
  </div>`;
}

export function ImportedDataPanel({ personId }) {
  const { data } = useAsync(() => api.get(`/imports/provenance/person/${personId}`), [personId]);
  if (!data || (!data.record && !data.items.length)) return null;
  return html`<section class="panel"><details><summary><h2 class="inline">Imported data — side by side with the original file</h2></summary>
    ${data.record && html`<p class="small">From the ${{ ancestry: 'Ancestry', ftm: 'Family Tree Maker', rootsmagic: 'RootsMagic' }[data.record.product] || 'GEDCOM'} tree
      “${data.record.tree_label}”, record <code>${data.record.xref}</code>${(data.record.stable_keys || []).filter((k) => !k.startsWith('distinct:')).length ? html`, identifiers <code>${data.record.stable_keys.filter((k) => !k.startsWith('distinct:')).join(', ')}</code>` : ''}.
      These identifiers are only meaningful within this tree's import history.</p>`}
    <p class="small muted">Imported facts are working claims recorded in the tree — not independently verified.</p>
    ${data.items.map((it) => html`<div class="side-by-side prov"><div><strong>${it.entity_type === 'name' ? `Name: ${it.entity.full_text || [it.entity.given, it.entity.surname].join(' ')}` :
      `${it.entity.claim_type}${it.entity.relationship_qualifier ? ' (' + it.entity.relationship_qualifier + ')' : ''}: ${it.entity.date_text || ''} ${it.entity.value_text || ''}`}</strong>
      <div class="small muted">${it.entity.statement || ''}</div><div class="small">Imported ${fmtDate(it.links[0].committed_at)} from ${it.links[0].original_filename}</div></div>
      <div><${GedcomLines} lines=${flatLines(it.links[0].gedcom)} max=${25} /></div></div>`)}
    ${data.record && html`<h3>Complete original record</h3><${GedcomLines} lines=${flatLines([data.record.raw])} max=${400} />`}
  </details></section>`;
}
