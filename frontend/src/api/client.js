const API_BASE = import.meta.env.VITE_API_BASE || "/api";

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `request failed (${response.status})`);
  }
  return response.json();
}

export const listRepos = () => request("/repos");
export const getMetrics = (hours = 24) => request(`/metrics?hours=${hours}`);
export const getJob = (jobId) => request(`/repos/jobs/${jobId}`);
export const deleteRepo = (slug) => request(`/repos/${slug}`, { method: "DELETE" });

export const indexRepo = ({ owner, name, ref }) =>
  request("/repos", {
    method: "POST",
    body: JSON.stringify({ owner, name, ref }),
  });

function parseFrame(frame) {
  let event = "message";
  let data = "";
  for (const line of frame.split("\n")) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) data += line.slice(5).trim();
  }
  if (!data) return null;
  try {
    return { event, data: JSON.parse(data) };
  } catch {
    return null;
  }
}

export async function* streamChat({ repo, question, signal }) {
  const response = await fetch(`${API_BASE}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ repo, question }),
    signal,
  });
  if (!response.ok || !response.body) {
    throw new Error(`chat request failed (${response.status})`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let boundary = buffer.indexOf("\n\n");
    while (boundary !== -1) {
      const parsed = parseFrame(buffer.slice(0, boundary));
      buffer = buffer.slice(boundary + 2);
      if (parsed) yield parsed;
      boundary = buffer.indexOf("\n\n");
    }
  }
  if (buffer.trim()) {
    const parsed = parseFrame(buffer);
    if (parsed) yield parsed;
  }
}
