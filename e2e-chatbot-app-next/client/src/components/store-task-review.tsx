// Store Operations extension of the official Databricks chat interface.
import { useEffect, useState } from 'react';

type Proposal = {
  id: string;
  payload: { title: string; store_id: string; assignee: string; due_date: string };
  status: string;
};

export function StoreTaskReview({ conversation, refreshKey }: { conversation: string; refreshKey: string }) {
  const [proposals, setProposals] = useState<Proposal[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  async function action(command: Record<string, unknown>) {
    const res = await fetch('/invocations', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ input: [{ role: 'user', content: 'Review task proposal' }], stream: false,
        custom_inputs: { ...command, session_id: conversation } }),
    });
    if (!res.ok) throw new Error('Task review failed. Refresh before trying again; do not create a second proposal.');
    return res.json();
  }
  async function refresh() {
    const result = await action({ action: 'pending_proposals' });
    setProposals(result.custom_outputs?.proposals ?? []);
  }
  useEffect(() => {
    if (refreshKey === 'ready') refresh().catch((e) => setError(e.message));
  }, [conversation, refreshKey]);
  async function decide(id: string, approve: boolean) {
    setBusy(true); setError('');
    try {
      await action({ action: 'task_decision', approval_id: id, approve });
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Approval outcome requires review.');
      await refresh().catch(() => {});
    } finally { setBusy(false); }
  }
  if (!proposals.length && !error) return null;
  return <section className="mx-auto w-full max-w-3xl border rounded-lg p-4" aria-label="Task review">
    <h2 className="font-semibold">OpsTask · human review</h2>
    {error && <p role="alert">{error}</p>}
    {proposals.map((p) => <article key={p.id} className="border-t py-3">
      <p>{p.payload.title}</p>
      <p className="text-sm">Store: {p.payload.store_id} · Assignee: {p.payload.assignee} · Due: {p.payload.due_date}</p>
      <p className="text-sm">Status: {p.status} · Approval ID: {p.id}</p>
      {p.status === 'pending' && <div className="flex gap-4 mt-2">
        <button disabled={busy} onClick={() => decide(p.id, true)}>Approve task creation</button>
        <button disabled={busy} onClick={() => decide(p.id, false)}>Reject</button>
      </div>}
      {['executing', 'needs_reconciliation'].includes(p.status) && <p>Reconcile this approval ID with OpsTask before any new attempt.</p>}
    </article>)}
  </section>;
}
