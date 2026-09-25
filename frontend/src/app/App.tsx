import { useEffect, useState } from "react";

type Health = { status: string; database: string };

export function App() {
  const [health, setHealth] = useState<"checking" | "ready" | "unavailable">("checking");

  useEffect(() => {
    const controller = new AbortController();
    fetch("/api/v1/health", { signal: controller.signal, credentials: "same-origin" })
      .then((response) => {
        if (!response.ok) throw new Error("Health check failed");
        return response.json() as Promise<Health>;
      })
      .then((body) => setHealth(body.status === "ok" ? "ready" : "unavailable"))
      .catch((error: unknown) => {
        if (!(error instanceof DOMException && error.name === "AbortError")) {
          setHealth("unavailable");
        }
      });
    return () => controller.abort();
  }, []);

  return (
    <main className="mx-auto flex min-h-screen max-w-3xl items-center px-6 py-16">
      <section className="w-full rounded-2xl border border-slate-200 bg-white p-8 shadow-sm">
        <p className="text-sm font-semibold uppercase tracking-widest text-charity-600">Foundation</p>
        <h1 className="mt-3 text-4xl font-bold tracking-tight text-charity-950">CharityOS</h1>
        <p className="mt-4 text-slate-600">The application shell is running.</p>
        <p className="mt-6 text-sm text-slate-500" role="status">
          Backend: {health}
        </p>
      </section>
    </main>
  );
}

