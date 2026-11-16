export default function RepoBar({ value, onChange, refValue, onRefChange, onIndex, busy, status }) {
  return (
    <section className="panel repobar">
      <div className="fields">
        <label>
          <span>Repository</span>
          <input
            value={value}
            onChange={(event) => onChange(event.target.value)}
            placeholder="owner/name"
            spellCheck="false"
            autoCapitalize="none"
          />
        </label>
        <label className="ref">
          <span>Ref</span>
          <input
            value={refValue}
            onChange={(event) => onRefChange(event.target.value)}
            placeholder="main"
            spellCheck="false"
            autoCapitalize="none"
          />
        </label>
        <button type="button" onClick={onIndex} disabled={busy}>
          {busy ? "Indexing…" : "Index repository"}
        </button>
      </div>
      <p className="status" role="status">
        {status}
      </p>
    </section>
  );
}
