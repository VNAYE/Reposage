import { useEffect, useRef, useState } from "react";
import Message from "./Message.jsx";
import { useChatStream } from "../hooks/useChatStream.js";

const EXAMPLES = [
  "How does authentication work?",
  "Where is the database connection created?",
  "What happens when a request fails?",
];

export default function ChatWindow({ repo, onAnswered }) {
  const { messages, streaming, send, stop } = useChatStream();
  const [question, setQuestion] = useState("");
  const bottomRef = useRef(null);
  const answeredCount = messages.filter((message) => message.usage).length;

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: "end", behavior: "smooth" });
  }, [messages]);

  useEffect(() => {
    if (answeredCount > 0) onAnswered?.();
  }, [answeredCount, onAnswered]);

  const submit = (event) => {
    event.preventDefault();
    if (!question.trim() || !repo || streaming) return;
    send({ repo, question });
    setQuestion("");
  };

  const handleKeyDown = (event) => {
    if (event.key === "Enter" && !event.shiftKey) submit(event);
  };

  return (
    <section className="panel chat">
      <div className="messages">
        {messages.length === 0 ? (
          <div className="empty">
            <h2>Ask the codebase</h2>
            <p>
              {repo
                ? `Answers cite files from ${repo}.`
                : "Index a repository on the left, then ask a question."}
            </p>
            <div className="examples">
              {EXAMPLES.map((example) => (
                <button key={example} type="button" className="ghost" onClick={() => setQuestion(example)}>
                  {example}
                </button>
              ))}
            </div>
          </div>
        ) : (
          messages.map((message) => <Message key={message.id} message={message} />)
        )}
        <div ref={bottomRef} />
      </div>

      <form className="composer" onSubmit={submit}>
        <textarea
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={repo ? `Ask about ${repo}…` : "Index a repository first"}
          rows={2}
          disabled={!repo}
          aria-label="Question"
        />
        {streaming ? (
          <button type="button" className="secondary" onClick={stop}>
            Stop
          </button>
        ) : (
          <button type="submit" disabled={!repo || !question.trim()}>
            Send
          </button>
        )}
      </form>
    </section>
  );
}
