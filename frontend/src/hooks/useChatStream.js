import { useCallback, useRef, useState } from "react";
import { streamChat } from "../api/client.js";

let sequence = 0;

export function useChatStream() {
  const [messages, setMessages] = useState([]);
  const [streaming, setStreaming] = useState(false);
  const abortRef = useRef(null);

  const stop = useCallback(() => abortRef.current?.abort(), []);

  const reset = useCallback(() => setMessages([]), []);

  const send = useCallback(async ({ repo, question }) => {
    if (!repo || !question.trim() || abortRef.current) return;

    sequence += 1;
    const assistantId = `assistant-${sequence}`;
    setMessages((previous) => [
      ...previous,
      { id: `user-${sequence}`, role: "user", content: question.trim() },
      {
        id: assistantId,
        role: "assistant",
        content: "",
        sources: [],
        citations: [],
        verification: null,
        usage: null,
        error: "",
        pending: true,
      },
    ]);

    const controller = new AbortController();
    abortRef.current = controller;
    setStreaming(true);

    const patch = (changes) =>
      setMessages((previous) =>
        previous.map((message) => (message.id === assistantId ? { ...message, ...changes } : message)),
      );

    try {
      for await (const { event, data } of streamChat({
        repo,
        question: question.trim(),
        signal: controller.signal,
      })) {
        if (event === "sources") patch({ sources: data.sources || [] });
        else if (event === "token") {
          setMessages((previous) =>
            previous.map((message) =>
              message.id === assistantId
                ? { ...message, content: message.content + (data.text || "") }
                : message,
            ),
          );
        } else if (event === "verification") patch({ verification: data.verification });
        else if (event === "done") patch({ usage: data.usage, citations: data.citations || [] });
        else if (event === "error") patch({ error: data.message || "request failed" });
      }
    } catch (error) {
      if (error.name !== "AbortError") patch({ error: error.message });
    } finally {
      patch({ pending: false });
      setStreaming(false);
      abortRef.current = null;
    }
  }, []);

  return { messages, streaming, send, stop, reset };
}
