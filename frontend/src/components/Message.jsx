import SourceList from "./SourceList.jsx";
import VerificationBadge from "./VerificationBadge.jsx";

function renderContent(content) {
  return content.split(/(\[S\d+\])/g).map((part, index) =>
    /^\[S\d+\]$/.test(part) ? (
      <span className="cite" key={index}>
        {part}
      </span>
    ) : (
      <span key={index}>{part}</span>
    ),
  );
}

export default function Message({ message }) {
  if (message.role === "user") {
    return (
      <article className="message user">
        <div className="bubble">{message.content}</div>
      </article>
    );
  }

  const hasBody = Boolean(message.content);

  return (
    <article className="message assistant">
      <div className="bubble">
        {hasBody ? <div className="answer">{renderContent(message.content)}</div> : null}
        {message.pending && !hasBody ? (
          <div className="thinking">
            <span />
            <span />
            <span />
          </div>
        ) : null}
        {message.error ? <div className="error">{message.error}</div> : null}
        <VerificationBadge verification={message.verification} />
        <SourceList sources={message.sources} citations={message.citations} />
        {message.usage ? (
          <footer className="usage">
            {message.usage.total_tokens.toLocaleString()} tokens · $
            {message.usage.cost_usd.toFixed(5)} · {Math.round(message.usage.latency_ms)} ms ·{" "}
            {message.usage.model}
          </footer>
        ) : null}
      </div>
    </article>
  );
}
