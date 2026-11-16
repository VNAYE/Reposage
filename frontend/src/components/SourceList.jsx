export default function SourceList({ sources, citations }) {
  if (!sources || sources.length === 0) return null;
  const cited = new Set((citations || []).map((citation) => citation.source_id));

  return (
    <details className="sources">
      <summary>
        {sources.length} retrieved sources
        {cited.size > 0 ? ` · ${cited.size} cited` : ""}
      </summary>
      <ol>
        {sources.map((source, index) => {
          const id = `S${index + 1}`;
          return (
            <li key={source.id} className={cited.has(id) ? "source cited" : "source"}>
              <div className="source-head">
                <span className="source-id">{id}</span>
                <code>
                  {source.path}:{source.start_line}-{source.end_line}
                </code>
                <span className="muted">
                  {source.symbol || source.language} · {source.score.toFixed(3)} ·{" "}
                  {source.origins.join("+")}
                </span>
              </div>
              <pre>{source.content}</pre>
            </li>
          );
        })}
      </ol>
    </details>
  );
}
