export default function VerificationBadge({ verification }) {
  if (!verification) return null;
  const supported = verification.supported;
  const claims = verification.unsupported_claims || [];

  return (
    <div className={`verification ${supported ? "ok" : "warn"}`}>
      <strong>{supported ? "Verified against sources" : "Needs review"}</strong>
      <span>
        {Math.round((verification.score || 0) * 100)}% support · {verification.verifier}
      </span>
      {claims.length > 0 ? (
        <ul>
          {claims.map((claim) => (
            <li key={claim}>{claim}</li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
