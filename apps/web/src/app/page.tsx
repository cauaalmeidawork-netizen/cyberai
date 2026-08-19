import { StatusPanel } from "@/components/status-panel";

export default function Home() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-8 p-6">
      <div className="max-w-2xl text-center space-y-4">
        <h1 className="text-4xl font-bold tracking-tight sm:text-6xl">
          CYBER AI
        </h1>
        <p className="text-lg text-muted">
          Modular, multi-tenant cybersecurity AI platform.
        </p>
      </div>
      <StatusPanel />
    </main>
  );
}
