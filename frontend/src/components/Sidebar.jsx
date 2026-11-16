export default function Sidebar({ repos, activeRepo, onSelect, onDelete, metrics, onRefresh }) {
  return (
    <aside className="sidebar">
      <section className="panel">
        <div className="panel-head">
          <h2>Indexed repositories</h2>
          <button type="button" className="ghost" onClick={onRefresh}>
            Refresh
          </button>
        </div>
        {repos.length === 0 ? (
          <p className="muted">Nothing indexed yet.</p>
        ) : (
          <ul className="repos">
            {repos.map((repo) => (
              <li key={repo.slug} className={repo.slug === activeRepo ? "active" : ""}>
                <button type="button" className="repo-select" onClick={() => onSelect(repo.slug)}>
                  <strong>{repo.slug}</strong>
                  <span>{repo.chunks.toLocaleString()} chunks</span>
                </button>
                <button
                  type="button"
                  className="ghost danger"
                  onClick={() => onDelete(repo.slug)}
                  aria-label={`Delete ${repo.slug}`}
                >
                  ×
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="panel">
        <h2>Last 24 hours</h2>
        {metrics ? (
          <>
            <dl className="metrics">
              <div>
                <dt>Requests</dt>
                <dd>{metrics.requests.toLocaleString()}</dd>
              </div>
              <div>
                <dt>Tokens</dt>
                <dd>{metrics.total_tokens.toLocaleString()}</dd>
              </div>
              <div>
                <dt>Cost</dt>
                <dd>${metrics.cost_usd.toFixed(4)}</dd>
              </div>
              <div>
                <dt>p95 latency</dt>
                <dd>{Math.round(metrics.p95_latency_ms)} ms</dd>
              </div>
            </dl>
            {metrics.by_model.length > 0 ? (
              <ul className="by-model">
                {metrics.by_model.map((row) => (
                  <li key={`${row.model}-${row.kind}`}>
                    <span>{row.kind}</span>
                    <span>
                      {row.requests.toLocaleString()} · ${row.cost_usd.toFixed(4)}
                    </span>
                  </li>
                ))}
              </ul>
            ) : null}
          </>
        ) : (
          <p className="muted">No metrics yet.</p>
        )}
      </section>
    </aside>
  );
}
