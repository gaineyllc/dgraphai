# DEPRECATED

This Python scanner agent is superseded by \gent-go/\ (the Go implementation).

## Why it was replaced

The Python scanner agent was the original reference implementation.
It has been replaced by a Go binary (\dgraph-agent\) for on-premises deployments:

- Ships as a single signed binary — no Python runtime on customer machines
- 10x lower memory footprint (~15MB vs ~150MB idle)
- Auditable supply chain — 8 Go deps vs 300+ pip dependencies
- Stronger deployment security posture for enterprise customers

## What to use instead

Install the Go agent via Helm, Docker, or binary download.
See \gent-go/\ and \charts/dgraph-agent/\ for the canonical implementation.

## This code

Kept for reference and integration test purposes only.
Do NOT deploy this to customer infrastructure.

