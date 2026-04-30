# `backend/app/studio/`

Studio domain root. Owns category-owned content-generation items and the studio job/tool/run layer.

Read these in order when placing studio work:

1. [`__init__.py`](./__init__.py) — import/dependency charter (NBB-104).
2. [`CHARTER.md`](./CHARTER.md) — data-bearing charter: tables, buckets, RLS, access guard (NBB-204).
3. [`TAXONOMY.md`](./TAXONOMY.md) — canonical categories and item names (NBB-501A). Consumers: NBB-501B registry, NBB-502 layer map, NBB-503 pilot, NBB-504–507 migrations.
4. [`REGISTRY.md`](./REGISTRY.md) — final item registry mapping current routes, historical service/executor sources, jobs, prompts, typed tool specs, and tests per item (NBB-501B).
5. [`LAYER_MAP.md`](./LAYER_MAP.md) — five-file per-item runtime shape (`<verb>.py`, `job.py`, `tool.py`, `run.py`, `schema.py`), executable naming rule, `studio/export/` charter note, and contract links (NBB-502).

Cross-references:

- Tool-schema owners: `docs/tickets/epics/NBB-002.md#nbb-207c`; live tool contracts are typed specs after `NBB-1104`.
- Prompt ownership: `docs/tickets/epics/NBB-002.md#nbb-207b` (studio prompts deferred there; targets tracked in `TAXONOMY.md`).
- Studio job status/progress/result contract: `NBB-205` + `NBB-502`.
- Background lifecycle: `NBB-210` (`background/` ownership).

No item code lives here yet. `NBB-501B` produces the full file-level registry; `NBB-502` locks the per-item layer shape; slice migrations (`NBB-504`–`NBB-507`) land the implementations.
