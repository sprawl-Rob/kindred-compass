import { html } from '../vendor/preact-htm.js';
import { api, useAsync, useStore, Loading, ErrorBox, Empty, L, fmtDate } from '../ui.js';

export function Dashboard() {
  const s = useStore();
  const { data, error, loading, reload } = useAsync(() => api.get(`/projects/${s.projectId}/dashboard`), [s.projectId]);
  if (loading && !data) return html`<div class="page"><${Loading} /></div>`;
  if (error) return html`<div class="page"><${ErrorBox} error=${error} retry=${reload} /></div>`;
  const { project, counts, questions, tasks, recent_log, people, conflicts, follow_ups } = data;
  return html`<div class="page">
    ${project.is_demo ? html`<div class="callout tone-warn"><strong>Fictional demonstration project.</strong> Everything here — people, records, citations — is invented to show how the app works. Your own projects are separate. Reset or delete it in Settings → Data.</div>` : null}
    <header class="page-head">
      <div><h1>${project.name}</h1>${project.description && html`<p class="lede">${project.description}</p>`}</div>
      <div class="row"><a class="button" href="#/people">Add a person</a><a class="button secondary" href="#/next">Next searches</a></div>
    </header>
    <div class="stat-row" aria-label="Project summary">
      <a class="stat" href="#/people"><span class="stat-n">${counts.persons}</span><span>people</span></a>
      <a class="stat" href="#/evidence"><span class="stat-n">${counts.claims}</span><span>claims</span></a>
      <a class="stat" href="#/evidence?tab=sources"><span class="stat-n">${counts.sources}</span><span>sources</span></a>
      <a class="stat" href="#/log"><span class="stat-n">${counts.searches}</span><span>searches logged</span></a>
      <a class="stat" href="#/log?outcome=no_result"><span class="stat-n">${counts.negative}</span><span>with no result</span></a>
    </div>
    <div class="grid-2">
      <section class="panel">
        <h2>Open research questions</h2>
        ${questions.length === 0 ? html`<${Empty} title="No open questions">Questions focus your searches. Add one from a person's page.<//>` :
          html`<ul class="list">${questions.map((q) => html`<li>
            <div class="list-main"><strong>${q.question}</strong>
              <div class="muted small">${L('question_types', q.question_type)}${q.person_name ? ' · ' + q.person_name : ''}</div></div>
            <a class="button small" href=${`#/next?question=${q.id}`}>Suggest searches</a></li>`)}</ul>`}
      </section>
      <section class="panel">
        <h2>Conflicts to review</h2>
        ${conflicts.length === 0 ? html`<p class="muted">No conflicting claims detected. Conflicts are flagged here, never resolved automatically.</p>` :
          html`<ul class="list">${conflicts.map((c) => html`<li><div class="list-main"><strong>${c.person_name}: ${L('claim_types', c.claim_type)}</strong>
            <div class="small">${c.reason}</div></div><a class="button small secondary" href=${`#/person/${c.person_id}`}>Review</a></li>`)}</ul>`}
      </section>
      <section class="panel">
        <h2>To do</h2>
        ${tasks.length === 0 ? html`<p class="muted">No open tasks.</p>` :
          html`<ul class="list">${tasks.map((t) => html`<li><div class="list-main">${t.title}
            <div class="muted small">${[t.person_name, t.collection_name, t.origin === 'ai_proposal' ? 'from AI suggestion' : null].filter(Boolean).join(' · ')}</div></div></li>`)}</ul>`}
      </section>
      <section class="panel">
        <h2>Recent searches</h2>
        ${recent_log.length === 0 ? html`<p class="muted">Nothing logged yet. Log every search — including ones that found nothing.</p>` :
          html`<ul class="list">${recent_log.map((e) => html`<li><div class="list-main">
            <strong>${e.collection_name || e.resource_text}</strong> <span class=${'outcome o-' + e.outcome}>${L('log_outcomes', e.outcome)}</span>
            <div class="muted small">${fmtDate(e.searched_on)} · ${e.query_text}${e.person_name ? ' · ' + e.person_name : ''}</div></div></li>`)}</ul>`}
        <a href="#/log">Open research log →</a>
      </section>
    </div>
    <section class="panel">
      <h2>People in this project</h2>
      ${people.length === 0 ? html`<${Empty} title="No people yet">You don't need a full tree. Start with one person, an approximate date, and a place.<p><a class="button" href="#/people">Add a person</a></p><//>` :
        html`<div class="cards">${people.map((p) => html`<a class="card person-card" href=${`#/person/${p.id}`}>
          <strong>${p.display_name}</strong>
          <span class="muted small">${[p.summary.birth && 'b. ' + p.summary.birth, p.summary.death && 'd. ' + p.summary.death].filter(Boolean).join(' · ') || 'No dates yet'}</span>
          <span class="small">${p.summary.places.join(' · ')}</span></a>`)}</div>`}
    </section>
    ${follow_ups.length ? html`<section class="panel"><h2>Follow-ups & possible matches</h2><ul class="list">${follow_ups.map((e) => html`<li>
      <div class="list-main"><strong>${e.collection_name || e.resource_text}</strong> — ${e.notes || e.query_text}</div></li>`)}</ul></section>` : null}
  </div>`;
}
