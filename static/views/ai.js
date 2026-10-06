import { html, useState, useEffect, useRef } from '../vendor/preact-htm.js';
import { api, useAsync, useStore, store, setStore, Loading, ErrorBox, Field, Select, Modal, toast, errMsg, fmtDate } from '../ui.js';

export async function loadAIConfig() {
  try { setStore({ ai: await api.get('/ai/config') }); } catch (e) { /* AI config unavailable */ }
}

function modelOptions(cfg, provider, cache) {
  const list = (cache && cache.models) || [];
  const manual = ((cfg.providers[provider] || {}).manual_models || []).filter((m) => m.ok);
  const seen = new Set();
  const out = [];
  [...manual.map((m) => [m.id, `${m.id} (validated manually)`]), ...list.map((m) => [m.id, m.display_name && m.display_name !== m.id ? `${m.display_name} — ${m.id}` : m.id + (m.likely_text_model === false ? ' (likely not text)' : '')])]
    .forEach(([k, v]) => { if (!seen.has(k)) { seen.add(k); out.push([k, v]); } });
  return out;
}

function useModels(provider) {
  return useAsync(() => (provider ? api.get(`/ai/models/${provider}`) : Promise.resolve(null)), [provider]);
}

// ------------------------------------------------------------------ AI action (preview → run → review)
export function AIAction({ task, inputs, label }) {
  const s = useStore();
  const [open, setOpen] = useState(false);
  if (!s.ai) { loadAIConfig(); return null; }
  if (!s.ai.enabled) return null;
  return html`<button class="secondary ai-btn" onClick=${() => setOpen(true)} title="Optional AI assistance — you'll see exactly what is sent first">✧ ${label}</button>
    ${open && html`<${AIRunDialog} task=${task} inputs=${inputs} label=${label} onClose=${() => setOpen(false)} />`}`;
}

function AIRunDialog({ task, inputs, label, onClose }) {
  const s = useStore();
  const [override, setOverride] = useState({});
  const [pv, setPv] = useState(null);
  const [err, setErr] = useState(null);
  const [run, setRun] = useState(null);
  const [starting, setStarting] = useState(false);
  const models = useModels(override.provider || (pv && pv.selection.provider));
  const poll = useRef(null);
  useEffect(() => {
    setErr(null);
    api.post('/ai/preview', { task, inputs, override }).then(setPv, setErr);
  }, [JSON.stringify(override)]);
  useEffect(() => () => clearInterval(poll.current), []);
  const start = async () => {
    if (starting) return; // guard against double submission
    setStarting(true);
    try {
      const r = await api.post('/ai/runs', { task, inputs, override, confirmed_model: `${pv.selection.provider}:${pv.selection.model}` });
      setRun(r);
      poll.current = setInterval(async () => {
        const x = await api.get(`/ai/runs/${r.id}`);
        setRun(x);
        if (x.status !== 'running') clearInterval(poll.current);
      }, 1200);
    } catch (x) { setErr(x); }
    setStarting(false);
  };
  const cancel = async () => { setRun(await api.post(`/ai/runs/${run.id}/cancel`)); };
  const sel = pv && pv.selection;
  return html`<${Modal} title=${label} onClose=${onClose} wide>
    <${ErrorBox} error=${err} />
    ${!pv ? html`<${Loading} what="Preparing preview" />` : !run ? html`
      <p class="small">${pv.notice}</p>
      <section class="panel subtle"><h3>Provider and model for this run</h3>
        <div class="row wrap">
          <${Field} label="Provider"><${Select} value=${override.provider || sel.provider} onChange=${(p) => setOverride({ ...override, provider: p, model: null, effort: null })} empty="Choose…"
            options=${Object.entries(s.ai.providers).map(([k, p]) => [k, p.label + (p.configured ? '' : ' (no key)')])} /><//>
          <${Field} label="Model"><${Select} value=${override.model || sel.model} onChange=${(m) => setOverride({ ...override, provider: override.provider || sel.provider, model: m })} empty="Choose…"
            options=${modelOptions(s.ai, override.provider || sel.provider, models.data)} /><//>
          ${pv.compatibility.controls.effort_levels && pv.compatibility.controls.effort_levels.length > 0 && html`<${Field} label="Effort"><${Select} value=${override.effort || sel.effort}
            onChange=${(x) => setOverride({ ...override, effort: x })} empty="Model default" options=${pv.compatibility.controls.effort_levels.map((e) => [e, e])} /><//>`}
          ${sel.provider === 'openai' && html`<${Field} label="Reasoning effort" hint="Not reported by OpenAI; rejected if unsupported"><${Select} value=${override.effort || sel.effort}
            onChange=${(x) => setOverride({ ...override, effort: x })} empty="Don't send" options=${['minimal', 'low', 'medium', 'high'].map((e) => [e, e])} /><//>`}
          <${Field} label="Output limit (tokens)" hint=${pv.compatibility.controls.max_output_tokens ? `Model max ${pv.compatibility.controls.max_output_tokens}` : ''}>
            <input inputmode="numeric" size="7" value=${override.max_output_tokens || sel.max_output_tokens} onInput=${(e) => setOverride({ ...override, max_output_tokens: +e.target.value || null })} /><//>
        </div>
        <p class="small">Will run on <strong>${pv.provider_label || '—'}</strong> · <code>${sel.model || 'no model selected'}</code> (${sel.source}).
          ${pv.compatibility.info_source && html` Model info: ${pv.compatibility.info_source}${pv.compatibility.refreshed_at ? ', ' + fmtDate(pv.compatibility.refreshed_at) : ''}.`}</p>
        ${pv.fallback && html`<p class="small callout tone-warn">Cross-provider fallback is ON: if this provider fails temporarily, the same data will be sent to ${pv.fallback.provider} · ${pv.fallback.model}.</p>`}
        ${pv.compatibility.issues.map((i) => html`<p class="callout tone-bad small">${i}</p>`)}
        ${pv.compatibility.unverified.map((i) => html`<p class="small muted">⚠ ${i}</p>`)}
      </section>
      <section class="panel subtle"><h3>What will be sent to ${pv.sent.destination}</h3>
        <ul class="small sent-list">${pv.sent.items.map((it) => html`<li>${it.ref ? html`<code>${it.ref}</code> ` : ''}${it.type}: ${it.label}${it.chars ? html` <span class="muted">(${it.chars} chars)</span>` : ''}${it.bytes ? html` <span class="muted">(${Math.round(it.bytes / 1024)} KB file)</span>` : ''}</li>`)}</ul>
        <p class="small muted">${pv.sent.total_chars} characters of text${pv.sent.images ? `, ${pv.sent.images} image(s)` : ''}${pv.sent.pdfs ? `, ${pv.sent.pdfs} PDF(s)` : ''}. Cost: ${pv.cost_note}.</p>
        ${pv.sent.warnings.map((w) => html`<p class="small">${w}</p>`)}
      </section>
      ${pv.blockers.length > 0 && html`<div class="callout tone-warn"><ul>${pv.blockers.map((b) => html`<li>${b}</li>`)}</ul><a href="#/settings/ai" onClick=${onClose}>Open AI Settings</a></div>`}
      <div class="row end"><button class="secondary" onClick=${onClose}>Cancel</button>
        <button disabled=${!pv.can_run || starting} onClick=${start}>${starting ? 'Starting…' : `Send to ${pv.provider_label || 'provider'}`}</button></div>
    ` : html`<${RunView} run=${run} onCancel=${cancel} />`}
  <//>`;
}

function RunView({ run, onCancel }) {
  const s = useStore();
  const people = useAsync(() => (s.projectId ? api.get(`/projects/${s.projectId}/persons`) : Promise.resolve([])), [s.projectId]);
  const [decided, setDecided] = useState({});
  const [edits, setEdits] = useState({});
  const decide = async (p, accept) => {
    try {
      const r = await api.post(`/ai/proposals/${p.id}/decide`, { accept, edits: edits[p.id] });
      setDecided({ ...decided, [p.id]: r.status }); toast(accept ? 'Accepted — saved to your research' : 'Rejected');
    } catch (x) { toast(errMsg(x), 'bad'); }
  };
  return html`<div aria-live="polite">
    <p><strong>Status:</strong> ${run.status}${run.status === 'running' ? '…' : ''} · ${run.provider} · <code>${run.model}</code>
      ${run.fallback_from ? html` <span class="badge tone-warn">fallback from ${run.fallback_from}</span>` : ''}</p>
    ${run.status === 'running' && html`<button class="secondary" onClick=${onCancel}>Cancel run</button>`}
    ${run.error_message && html`<div class="callout tone-bad">${run.error_message}</div>`}
    ${run.status === 'succeeded' && html`<p class="small muted">Took ${(run.duration_ms / 1000).toFixed(1)}s · tokens in ${run.input_tokens ?? '?'} / out ${run.output_tokens ?? '?'} · cost ${run.cost_note}</p>
      <p class="small">Review each suggestion. Nothing has changed in your research yet. <span class="badge tone-info">Extracted</span> = stated in a supplied document;
        <span class="badge tone-muted">Inference</span> = the model's reasoning.</p>
      <ul class="proposals">${run.proposals.map((p) => html`<li class="proposal">
        <div><span class=${'badge ' + (p.basis === 'extracted' ? 'tone-info' : 'tone-muted')}>${p.basis === 'extracted' ? 'Extracted' : 'Inference'}</span>
          <span class="muted small">${p.kind.replace('_', ' ')}</span></div>
        <${ProposalBody} p=${p} />
        ${(p.source_refs || []).length > 0 && html`<div class="small muted">Based on: ${p.source_refs.map((r) => `${r.ref || ''} ${r.label}`).join('; ')}</div>`}
        ${p.kind === 'extracted_fact' && p.status === 'pending' && !decided[p.id] && html`<div class="row wrap">
          <${Field} label="About which person?"><${Select} value=${(edits[p.id] || {}).person_id} onChange=${(v) => setEdits({ ...edits, [p.id]: { ...(edits[p.id] || {}), person_id: v } })} empty="Choose…" options=${(people.data || []).map((x) => [x.id, x.display_name])} /><//>
          <${Field} label="Claim type"><${Select} value=${(edits[p.id] || {}).claim_type || 'other'} onChange=${(v) => setEdits({ ...edits, [p.id]: { ...(edits[p.id] || {}), claim_type: v } })} options=${s.meta.vocab.claim_types} /><//></div>`}
        ${p.status !== 'pending' || decided[p.id] ? html`<p class="small"><strong>${decided[p.id] || p.status}</strong></p>` :
          html`<div class="row"><button class="small" onClick=${() => decide(p, true)}>Accept</button><button class="small secondary" onClick=${() => decide(p, false)}>Reject</button></div>`}
      </li>`)}</ul>`}
  </div>`;
}

function ProposalBody({ p }) {
  const x = p.payload;
  if (p.kind === 'research_step') return html`<p><strong>${x.title}</strong>${x.collection_name ? ` — ${x.collection_name}` : ''}<br /><span class="small">${x.rationale}</span></p>`;
  if (p.kind === 'query_variant') return html`<p><strong>${x.text}</strong> <span class="muted small">(${x.kind})</span><br /><span class="small">${x.explanation}</span></p>`;
  if (p.kind === 'extracted_fact') return html`<p><strong>${x.field}:</strong> ${x.value}<br /><span class="small">Quote: “${x.quote}” ${x.quote_found ? '✓ found in text' : ''}</span>
    ${x.downgraded && html`<br /><span class="small callout tone-warn">${x.downgraded}</span>`}</p>`;
  return html`<p class="prewrap">${x.text || x.title}</p>`;
}

// ------------------------------------------------------------------ AI settings
function ProviderCard({ pkey, p, onChange, defaultModel }) {
  const [key, setKey] = useState('');
  const [busy, setBusy] = useState(null);
  const [result, setResult] = useState(null);
  const [manual, setManual] = useState('');
  const [testModel, setTestModel] = useState('');
  const models = useModels(pkey);
  const act = async (name, fn) => { setBusy(name); setResult(null); try { setResult(await fn()); } catch (x) { setResult({ ok: false, detail: errMsg(x) }); } setBusy(null); onChange(); models.reload(); };
  const list = (models.data && models.data.models) || [];
  return html`<section class="panel"><h3>${p.label}</h3>
    <p class="small">${p.configured ? html`API key configured (${p.key_hint}) — stored in ${p.key_source}.` : 'No API key configured.'}${' '}Keys are kept in your system keychain, never in the browser, exports, backups, or logs.</p>
    <form class="row wrap" onSubmit=${async (e) => { e.preventDefault(); await act('key', async () => { await api.put(`/ai/keys/${pkey}`, { api_key: key }); setKey(''); return { ok: true, detail: 'Key saved to keychain' }; }); }}>
      <label class="sr-only" for=${'key-' + pkey}>${p.label} API key</label>
      <input id=${'key-' + pkey} type="password" autocomplete="off" value=${key} onInput=${(e) => setKey(e.target.value)} placeholder="Paste API key" disabled=${!p.keychain_available} />
      <button type="submit" disabled=${!key}>Save key</button>
      ${p.configured && p.key_source === 'system keychain' && html`<button type="button" class="secondary" onClick=${() => act('del', async () => { await api.del(`/ai/keys/${pkey}`); return { ok: true, detail: 'Key removed' }; })}>Remove key</button>`}
    </form>
    ${!p.keychain_available && html`<p class="small callout tone-warn">No system keychain available. Set the environment variable instead before starting the app.</p>`}
    <div class="row wrap">
      <button class="secondary" disabled=${!p.configured || busy} onClick=${() => act('test', () => api.post(`/ai/test/${pkey}`))}>${busy === 'test' ? 'Checking…' : 'Check connection & refresh models'}</button>
    </div>
    <p class="small muted">Model list: ${models.data && models.data.refreshed_at ? `cached from ${fmtDate(models.data.refreshed_at)} (${list.length} models) — this is the last successful refresh, not a live check` : 'never refreshed'}.</p>
    ${result && html`<p class=${'small callout ' + (result.ok === false ? 'tone-bad' : 'tone-good')}>${result.detail}${result.charges ? ' · ' + result.charges : ''}</p>`}
    ${list.length > 0 && html`<details><summary>Available models (${list.length})</summary>
      <p class="small muted">Rows come from the cached list (${fmtDate(models.data.refreshed_at)}). “Check now” asks ${p.label} about that model right now; listing a model
        does not guarantee it supports every task — each run also checks compatibility.</p>
      <div class="table-wrap"><table class="table small"><thead><tr><th>Provider · model ID</th><th>JSON output</th><th>Images</th><th>PDF</th><th>Effort</th><th>Context</th><th>Status</th></tr></thead><tbody>
      ${list.map((m) => { const c = m.capabilities; const yn = (v) => (v === true ? 'yes' : v === false ? 'no' : 'not reported');
        const v = (p.manual_models || []).find((x) => x.id === m.id);
        return html`<tr><td>${p.label} · <code>${m.id}</code>${m.likely_text_model === false ? html` <span class="muted">(likely not text)</span>` : ''}</td><td>${yn(c.structured_outputs)}</td><td>${yn(c.image_input)}</td><td>${yn(c.pdf_input)}</td>
          <td>${c.effort_levels == null ? 'not reported' : c.effort_levels.join(', ') || 'no'}</td><td>${c.max_input_tokens || '—'}</td>
          <td>${v ? html`<span class=${'badge ' + (v.ok ? 'tone-good' : 'tone-bad')} title=${v.detail}>${v.ok ? 'verified' : 'not usable'} ${fmtDate(v.validated_at)}</span>` : html`<span class="badge tone-muted">cached list</span>`}
            <button class="small link" disabled=${!!busy} onClick=${() => act('validate', () => api.post(`/ai/models/${pkey}/validate`, { model_id: m.id }))}>Check now</button></td></tr>`; })}</tbody></table></div>
      ${list[0] && list[0].note && html`<p class="small muted">${list[0].note}</p>`}</details>`}
    <form class="row wrap" onSubmit=${(e) => { e.preventDefault(); act('validate', () => api.post(`/ai/models/${pkey}/validate`, { model_id: manual })); }}>
      <${Field} label="Model ID not listed? Enter it to validate"><input value=${manual} onInput=${(e) => setManual(e.target.value)} disabled=${!p.configured} /><//>
      <button type="submit" class="secondary" disabled=${!manual || !p.configured}>Validate model</button></form>
    ${p.manual_models.length > 0 && html`<ul class="small">${p.manual_models.map((m) => html`<li><code>${m.id}</code> — ${m.ok ? 'valid' : 'not usable'} (${m.detail}, ${fmtDate(m.validated_at)})</li>`)}</ul>`}
    <details><summary>Minimal live test (sends a tiny prompt)</summary>
      <p class="small">Sends “Connection test.” and asks for a one-word reply (≤16 output tokens). <strong>This API call may incur a small charge.</strong></p>
      <div class="row wrap"><${Select} value=${testModel || defaultModel} onChange=${setTestModel} empty="Choose model" options=${list.map((m) => [m.id, m.id])} />
        <button class="secondary" disabled=${!p.configured || !(testModel || defaultModel) || busy} onClick=${() => act('gen', () => api.post(`/ai/test/${pkey}/generate`, { model: testModel || defaultModel, acknowledge_charges: true }))}>
          ${busy === 'gen' ? 'Testing…' : 'Send test prompt'}</button></div></details>
  </section>`;
}

export function AISettings() {
  const s = useStore();
  const { data: cfg, error, loading, reload } = useAsync(() => api.get('/ai/config'), []);
  const runs = useAsync(() => api.get('/ai/runs'), []);
  const openaiModels = useModels('openai');
  const anthropicModels = useModels('anthropic');
  if (loading && !cfg) return html`<${Loading} />`;
  if (error) return html`<${ErrorBox} error=${error} retry=${reload} />`;
  const refresh = () => { reload(); loadAIConfig(); openaiModels.reload(); anthropicModels.reload(); };
  const patch = async (b) => { try { await api.patch('/ai/config', b); refresh(); } catch (x) { toast(errMsg(x), 'bad'); } };
  const consent = async (b) => { await api.post('/ai/consent', { acknowledge: !!cfg.consent.acknowledged_at, ...b }); refresh(); };
  const modelsFor = (p) => modelOptions(cfg, p, p === 'openai' ? openaiModels.data : p === 'anthropic' ? anthropicModels.data : null);
  const providers = Object.entries(cfg.providers).map(([k, p]) => [k, p.label]);
  return html`<div class="stack">
    <section class="panel"><h2>AI assistance</h2>
      <p>The directory, research log, evidence, and next-search recommendations all work without AI. AI can optionally suggest query variants, propose research steps,
        extract facts from documents you supply, compare evidence, and draft summaries — always as proposals you review.</p>
      <p class="small">A model connection does <strong>not</strong> give access to genealogy websites, subscription records, or live web search.</p>
      <fieldset class="row"><legend class="sr-only">AI mode</legend>
        <label class="radio"><input type="radio" name="aimode" checked=${!cfg.enabled} onChange=${() => patch({ enabled: false })} /> <strong>AI disabled</strong></label>
        <label class="radio"><input type="radio" name="aimode" checked=${cfg.enabled} onChange=${() => patch({ enabled: true })} /> <strong>AI enabled</strong></label></fieldset>
    </section>
    <section class="panel"><h2>Consent & privacy</h2>
      <p class="small">When you run an AI action, the research data shown in its preview (names, claims, dates, places, source transcriptions you choose) is sent to the selected
        provider under that provider's terms. Nothing is sent automatically or in the background.</p>
      <label class="check"><input type="checkbox" checked=${!!cfg.consent.acknowledged_at} onChange=${async (e) => { await api.post('/ai/consent', { acknowledge: e.target.checked }); refresh(); }} />
        I understand and opt in to sending previewed research data to the AI provider I choose${cfg.consent.acknowledged_at ? ` (since ${fmtDate(cfg.consent.acknowledged_at)})` : ''}</label>
      <label class="check"><input type="checkbox" checked=${cfg.consent.allow_possibly_living} onChange=${(e) => consent({ allow_possibly_living: e.target.checked })} />
        Allow sending people who may be living (off by default)</label>
      <label class="check"><input type="checkbox" checked=${cfg.consent.allow_attachments} onChange=${(e) => consent({ allow_attachments: e.target.checked })} />
        Allow sending attached images/PDFs for transcription (off by default)</label>
    </section>
    ${Object.entries(cfg.providers).map(([k, p]) => html`<${ProviderCard} pkey=${k} p=${p} onChange=${refresh} defaultModel=${cfg.default.provider === k ? cfg.default.model : ''} />`)}
    <section class="panel"><h2>Model selection</h2>
      <div class="row wrap"><${Field} label="Default provider"><${Select} value=${cfg.default.provider} onChange=${(v) => patch({ default: { provider: v, model: null } })} empty="None" options=${providers} /><//>
        <${Field} label="Default model"><${Select} value=${cfg.default.model} onChange=${(v) => patch({ default: { provider: cfg.default.provider, model: v } })} empty="None"
          options=${cfg.default.provider ? modelsFor(cfg.default.provider) : []} /><//></div>
      <h3>Per-task overrides (optional)</h3>
      <div class="table-wrap"><table class="table small"><thead><tr><th>Task</th><th>Provider</th><th>Model</th><th>Effort</th><th>Output limit</th></tr></thead><tbody>
        ${Object.entries(cfg.tasks_available).map(([t, label]) => { const o = cfg.tasks[t] || {}; const setT = (patchO) => patch({ tasks: { ...cfg.tasks, [t]: { ...o, ...patchO } } });
          return html`<tr><td>${label}</td>
            <td><${Select} value=${o.provider} onChange=${(v) => setT({ provider: v, model: null })} empty="Default" options=${providers} /></td>
            <td><${Select} value=${o.model} onChange=${(v) => setT({ model: v })} empty="Default" options=${o.provider ? modelsFor(o.provider) : []} /></td>
            <td><${Select} value=${o.effort} onChange=${(v) => setT({ effort: v })} empty="Model default" options=${['low', 'medium', 'high', 'xhigh', 'max'].map((x) => [x, x])} /></td>
            <td><input aria-label=${label + ' output limit'} inputmode="numeric" size="6" value=${o.max_output_tokens || ''} onChange=${(e) => setT({ max_output_tokens: +e.target.value || null })} /></td></tr>`; })}
      </tbody></table></div>
      <p class="small muted">Effort values are checked against the selected model before each run; unsupported combinations are shown as incompatibilities, never silently changed.</p>
    </section>
    <section class="panel"><h2>Cross-provider fallback</h2>
      <p class="small">Off by default. If enabled, when the selected provider is temporarily unavailable (rate limit, outage, timeout), the <em>same data</em> is sent to the fallback below. The run records that this happened.</p>
      <label class="check"><input type="checkbox" checked=${cfg.fallback.enabled} onChange=${(e) => patch({ fallback: { enabled: e.target.checked } })} /> Enable fallback</label>
      ${cfg.fallback.enabled && html`<div class="row wrap"><${Field} label="Fallback provider"><${Select} value=${cfg.fallback.provider} onChange=${(v) => patch({ fallback: { provider: v, model: null } })} empty="Choose" options=${providers} /><//>
        <${Field} label="Fallback model"><${Select} value=${cfg.fallback.model} onChange=${(v) => patch({ fallback: { model: v } })} empty="Choose" options=${cfg.fallback.provider ? modelsFor(cfg.fallback.provider) : []} /><//></div>`}
      <${Field} label="Request timeout (seconds)"><input inputmode="numeric" size="5" value=${cfg.timeout_seconds} onChange=${(e) => patch({ timeout_seconds: +e.target.value || 120 })} /><//>
    </section>
    <section class="panel"><h2>AI run history</h2>
      ${(runs.data || []).length === 0 ? html`<p class="muted small">No AI runs yet.</p>` : html`<div class="table-wrap"><table class="table small"><thead><tr><th>When</th><th>Task</th><th>Provider · model</th><th>Status</th><th>Time</th><th>Tokens in/out</th><th>Cost</th></tr></thead><tbody>
        ${runs.data.map((r) => html`<tr><td>${fmtDate(r.started_at)}</td><td>${r.task}</td><td>${r.provider} · <code>${r.model}</code>${r.fallback_from ? ' (fallback)' : ''}</td>
          <td>${r.status}${r.error_code ? ` (${r.error_code})` : ''}</td><td>${r.duration_ms ? (r.duration_ms / 1000).toFixed(1) + 's' : '—'}</td>
          <td>${r.input_tokens ?? '—'} / ${r.output_tokens ?? '—'}</td><td>unknown</td></tr>`)}</tbody></table></div>`}
    </section>
  </div>`;
}
