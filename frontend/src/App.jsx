import { Suspense, lazy, useCallback, useEffect, useState } from "react";
import ChatWindow from "./components/ChatWindow.jsx";
import RepoBar from "./components/RepoBar.jsx";
import Sidebar from "./components/Sidebar.jsx";
import { deleteRepo, getJob, getMetrics, indexRepo, listRepos } from "./api/client.js";

const Background = lazy(() => import("./components/Background.jsx"));

const POLL_INTERVAL_MS = 1500;
const MAX_POLLS = 240;

export default function App() {
  const [repoInput, setRepoInput] = useState("tiangolo/fastapi");
  const [ref, setRef] = useState("main");
  const [activeRepo, setActiveRepo] = useState("");
  const [repos, setRepos] = useState([]);
  const [metrics, setMetrics] = useState(null);
  const [status, setStatus] = useState("Index a repository to begin.");
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const [repoList, summary] = await Promise.all([listRepos(), getMetrics()]);
      setRepos(repoList);
      setMetrics(summary);
      setActiveRepo((current) => current || repoList[0]?.slug || "");
    } catch (error) {
      setStatus(error.message);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const handleIndex = async () => {
    const [owner, name] = repoInput.split("/").map((part) => part.trim());
    if (!owner || !name) {
      setStatus("Use owner/name, for example tiangolo/fastapi.");
      return;
    }
    setBusy(true);
    try {
      let job = await indexRepo({ owner, name, ref: ref.trim() || "main" });
      setStatus(`Indexing ${job.repo}…`);
      for (
        let attempt = 0;
        attempt < MAX_POLLS && (job.status === "queued" || job.status === "running");
        attempt += 1
      ) {
        await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_MS));
        job = await getJob(job.job_id);
        setStatus(`Indexing ${job.repo}: ${job.status}…`);
      }
      if (job.status !== "succeeded") {
        throw new Error(job.error || "indexing did not finish");
      }
      setStatus(
        `Indexed ${job.report.chunks.toLocaleString()} chunks from ${job.report.files} files.`,
      );
      setActiveRepo(job.repo);
      await refresh();
    } catch (error) {
      setStatus(error.message);
    } finally {
      setBusy(false);
    }
  };

  const handleDelete = async (slug) => {
    try {
      await deleteRepo(slug);
      if (activeRepo === slug) setActiveRepo("");
      await refresh();
      setStatus(`Removed ${slug}.`);
    } catch (error) {
      setStatus(error.message);
    }
  };

  return (
    <div className="app">
      <Suspense fallback={null}>
        <Background />
      </Suspense>
      <header className="topbar">
        <div className="brand">
          <span className="logo">RS</span>
          <div>
            <h1>RepoSage</h1>
            <p>Cited answers about any GitHub repository</p>
          </div>
        </div>
        <span className="pill">Gemini · pgvector · hybrid search</span>
      </header>

      <main className="layout">
        <div className="main-column">
          <RepoBar
            value={repoInput}
            onChange={setRepoInput}
            refValue={ref}
            onRefChange={setRef}
            onIndex={handleIndex}
            busy={busy}
            status={status}
          />
          <ChatWindow repo={activeRepo} onAnswered={refresh} />
        </div>
        <Sidebar
          repos={repos}
          activeRepo={activeRepo}
          onSelect={setActiveRepo}
          onDelete={handleDelete}
          metrics={metrics}
          onRefresh={refresh}
        />
      </main>

      <footer className="footer">
        Answers are grounded in retrieved sources and verified before they are shown.
      </footer>
    </div>
  );
}
