# Reconstructed demo MCP contracts

This is a functional reconstruction from the recorded specification, not recovery of lost source. All results identify `mode=demo`, `synthetic=true`, `source=<capability>`, and contain typed `data`. Dates use ISO YYYY-MM-DD. Identifiers are nonblank strings; unknown stores/documents/tasks and reversed date ranges fail. Unknown tool arguments are rejected. Streamable HTTP is `/mcp`; public `/health` checks liveness and `/ready` checks backing data/storage.

## StoreTime — read credential only

- `get_schedules(store_id, start_date, end_date)` → `data.schedules`: employee shift records.
- `get_training_blocks(store_id, start_date, end_date)` → `data.blocks`: protected blocks with scheduled/completed/converted hours.
- `get_training_hours(store_id, start_date, end_date)` → `data.hours`: scheduled/protected/completed/converted totals.
- `get_coverage_reasons(store_id, start_date, end_date)` → `data.reasons`: recorded reasons and converted hours.
- `diagnose_training_gap(store_id, start_date, end_date)` → `data.diagnostic`: hours, completion gap, reasons, evidence block IDs and limitations.

All windows are inclusive. No mutation, scheduling update or task tool exists.

## OpsTask — separate read and write credentials

- `list_followups(store_id, status='all', limit=50, cursor=None)` → `data.tasks`, `data.next_cursor`. Status: all/open/in_progress/completed; limit 1–100; opaque cursor bound to store and status.
- `get_task(task_id)` → `data.task`.
- `create_task(title, store_id, assignee, due_date, idempotency_key)` → `data.task`, `data.task_id`, `data.replayed`.

Read credentials cannot discover or call create_task. Write credentials can. Approval remains application-owned: the server trusts the separate writer credential and does not look up approval records. An ID is not approval proof. Same key and canonical payload returns the original task ID; conflicting payload fails atomically. No root-cause tool exists.

## Confluence — read credential only

- `search_company_context(query, limit=5)` → `data.documents` (limit 1–20).
- `get_policy_document(source_id)` → `data.document`.

Documents include source_id, document_id, title, source_url, section, text and synthetic=true. Text is returned verbatim from the stored synthetic corpus; no model or policy synthesis is used. A search with no lexical match returns an empty list; unknown document retrieval fails.

`contracts.json` contains complete machine-readable input/output schemas and annotations. Export with `uv run python -m scripts.export_demo_contracts`; compare against real running servers using the validation harness. Schema regeneration is not itself runtime validation.
