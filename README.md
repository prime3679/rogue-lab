# rogue-lab

Cloudflare Worker experiments for Rogue Lab, backed by static assets in `public/`, Worker logic in `src/worker.ts`, and D1 migrations in `migrations/`.

## Local Verification

- `python3 .agent/contribution_gate.py audit`
- `python3 .agent/contribution_gate.py verify` requires dependencies that are already installed in this worktree.
- `npm run test:contribution-gate`
- `npm run check`
- `npm run verify:leaks`

The contribution contract is designed for zero-context agents. Verification stays local and must not deploy, install dependencies, mutate Cloudflare resources, or touch credentials. If this worktree does not have `node_modules/`, see `docs/zero-context-contribution.md` for the temporary sibling-worktree symlink workaround.
