# Zero-Context Contribution Standard

## Goal

Enable a fresh coding agent to make safe, reviewable contributions without tribal knowledge or cloud access.

## Source Of Truth

- Start at `AGENTS.md`.
- Use `.agent/contribution-contract.json` as the executable contract.
- Treat `package.json`, `wrangler.toml`, `src/worker.ts`, `scripts/leak-check.mjs`, and `migrations/` as architecture and safety references.

## Boundaries

- Stay inside this worktree.
- Do not install packages.
- Do not deploy or run workflows that require Cloudflare credentials.
- Do not mutate D1, KV, R2, Queues, cron state, bindings, routes, or auth configuration during verification.
- Do not change product content, public assets, or infrastructure configuration unless the task explicitly requires it.

## Verification Standard

- Run the local contribution gate in `audit` and `verify` mode.
- Run the gate tests.
- Run the repo’s deterministic checks from installed dependencies only.
- If `node_modules/` is absent in this worktree and the sibling main workspace has it, a temporary untracked symlink is allowed for verification and must be removed after use.

## Review Classification

- `one_off_judgment`: subjective product or copy preference without a stable repo rule.
- `repeatable_defect`: deterministic bug, broken verification, unsafe command shape, or contract drift.
- `missing_domain_knowledge`: Cloudflare, D1, routing, cron, or architecture knowledge that the repo does not document well enough to act safely.
- `agent_behavior_failure`: the agent ignored instructions, boundaries, precedence, or required evidence.

## Escalate When

- The repo cannot define a truthful verification contract without changing product code.
- Verification needs installs, secrets, external services, or cloud mutation.
- Another worktree or owner already controls a file that must change.
- Infrastructure intent is ambiguous around routes, bindings, auth, cron, or data stores.
