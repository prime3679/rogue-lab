# Rogue Lab Agent Guide

## Precedence

1. User brief and task constraints
2. This file
3. `docs/zero-context-contribution.md`
4. `.agent/contribution-contract.json`
5. `REVIEW.md`

## What This Repo Is

`rogue-lab` is a Cloudflare Workers site with static assets in `public/`, a Worker entry at `src/worker.ts`, scheduled generation for Morning Edition, and a D1 binding declared in `wrangler.toml`.

## Zero-Context Default

- Read the doctrine doc and contract before editing.
- Keep work local and deterministic unless the brief explicitly authorizes otherwise.
- Prefer docs, tests, and bounded automation over speculative product changes.

## Cloudflare And Lab Boundaries

- Treat `wrangler.toml`, D1 migrations, routes, bindings, cron config, and auth surfaces as infrastructure knowledge, not guesswork.
- Do not deploy, publish, run `wrangler dev`, or hit remote Cloudflare resources for routine verification.
- Do not mutate D1, KV, R2, Queues, cron state, or secrets as part of agent verification.
- Do not print credentials or copy values from local env files.

## Verification

- Truthful local verification for this repo is compile and static-check based: contribution gate audit/verify, gate tests, TypeScript `check`, and `verify:leaks`.
- If a requested change needs stronger proof than the repo can currently provide without product changes or cloud mutation, escalate instead of faking confidence.
