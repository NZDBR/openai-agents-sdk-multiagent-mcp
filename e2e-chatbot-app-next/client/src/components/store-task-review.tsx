// Store Operations extension of the official Databricks chat interface.
import { useEffect, useState } from 'react';

type Proposal = {
  id: string;
  payload: { title: string; store_id: string; assignee: string; due_date: string };
  approval_state: string;
  execution_state: string;
  action_type: string;
  created_at: string;
  expires_at: string;
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
    if (refreshKey !== 'ready') return;
    let active = true;
    const poll = () => { if (active) refresh().catch((e) => setError(e.message)); };
    poll();
    const timer = setInterval(poll, 10000);
    return () => { active = false; clearInterval(timer); };
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
      <p className="text-sm">Action: Create task · Created: {new Date(p.created_at).toLocaleString()} · Expires: {new Date(p.expires_at).toLocaleString()}</p>
      <p className="text-sm">Approval: {p.approval_state.replaceAll('_', ' ')} · Approval ID: {p.id}</p>
      {p.approval_state === 'APPROVED' && <p className="text-sm">Execution: {({ QUEUED: 'Queued', EXECUTING: 'Executing', EXECUTED: 'Completed', RETRYABLE_FAILURE: 'Retryable failure', FAILED: 'Failed' } as Record<string, string>)[p.execution_state] ?? p.execution_state}</p>}
      <details><summary>View details</summary><pre className="whitespace-pre-wrap">{JSON.stringify(p.payload, null, 2)}</pre></details>
      {p.approval_state === 'PENDING_APPROVAL' && Date.parse(p.expires_at) > Date.now() && <div className="flex gap-4 mt-2">
        <button disabled={busy} onClick={() => decide(p.id, true)}>Approve task creation</button>
        <button disabled={busy} onClick={() => decide(p.id, false)}>Reject</button>
      </div>}
      {p.execution_state === 'FAILED' && <p>Contact support with the approval ID before proposing a replacement task.</p>}
    </article>)}
  </section>;
}
