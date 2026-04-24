# Legacy - do not add files here

`frontend/src/components/hooks/` is a legacy directory per `NBB-105`. New hooks must not land here.

- App-level shared hooks live in `frontend/src/hooks/`.
- Feature-local hooks live under their owning feature subtree (for example `frontend/src/components/<feature>/`).

The full placement contract is in `frontend/STRUCTURE.md`. The repo-root `STRUCTURE.md` lists this path as a frozen destination; `NBB-103` enforces it in CI. `NBB-602` migrates the remaining files out.
