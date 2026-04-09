# dgraph-enricher — local content analysis

## Current implementation (Go)

The enricher in `local_enricher.go` runs inside dgraph-agent and scans
file content for secrets and PII before data leaves the customer network.

It uses Go's RE2-backed `regexp` package — linear time guaranteed,
no backtracking attacks possible. All patterns are reviewed against
adversarial input.

## Planned: Rust subprocess model

For production deployments handling untrusted/adversarial files,
the content scanner will move to a separate Rust binary (`dgraph-enricher`)
called by the Go agent as a subprocess.

Architecture:
```
dgraph-agent (Go) ──subprocess──> dgraph-enricher (Rust)
                       stdin: file path + size limit
                       stdout: JSON findings
                       timeout: 5s hard limit
                       memory: 256MB rlimit
```

Why Rust for this specific component:
- Parses untrusted file content (PDFs, executables, images)
- Borrow checker prevents buffer overruns at compile time
- No GC pauses when processing large files
- `serde_json`, `regex` crates are battle-hardened against adversarial input
- Can be compiled with address sanitizer for testing

The Go enricher is production-ready for typical deployments.
The Rust enricher is the target for air-gapped/government/classified deployments
where the attack surface of content parsing needs formal guarantees.

## RE2 safety of current patterns

All patterns in `local_enricher.go` use Go's `regexp` (RE2 semantics):
- Linear time O(n) regardless of input
- No backtracking
- Safe against ReDoS

Verified: none of the current patterns contain nested quantifiers
that would be dangerous even under PCRE.
