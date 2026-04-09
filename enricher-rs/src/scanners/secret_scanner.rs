//! Secret scanner — detects API keys, credentials, and private keys.
//! Uses RE2-compatible regex patterns (linear time, no backtracking).
//! All patterns are compiled once at startup and reused.

use regex::Regex;
use std::sync::LazyLock;

pub struct ScanResult {
    pub findings: Vec<String>,
}

pub struct SecretScanner {
    patterns: &'static [(&'static str, LazyLock<Regex>)],
}

// Compiled patterns — each is RE2-compatible (no lookahead, no backreferences)
// Ordered from most specific (highest confidence) to most general
static PATTERNS: &[(&str, LazyLock<Regex>)] = &[
    ("private_key",    LazyLock::new(|| Regex::new(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----").unwrap())),
    ("github_token",   LazyLock::new(|| Regex::new(r"ghp_[a-zA-Z0-9]{36}|github_pat_[a-zA-Z0-9_]{82}|ghs_[a-zA-Z0-9]{36}").unwrap())),
    ("aws_access_key", LazyLock::new(|| Regex::new(r"AKIA[0-9A-Z]{16}").unwrap())),
    ("aws_secret_key", LazyLock::new(|| Regex::new(r"(?i)aws[_\-.]?secret[_\-.]?(?:access[_\-.]?)?key[\s]*[=:]\s*[A-Za-z0-9/+]{40}").unwrap())),
    ("stripe_live",    LazyLock::new(|| Regex::new(r"sk_live_[a-zA-Z0-9]{24,}").unwrap())),
    ("stripe_test",    LazyLock::new(|| Regex::new(r"sk_test_[a-zA-Z0-9]{24,}").unwrap())),
    ("google_api",     LazyLock::new(|| Regex::new(r"AIza[0-9A-Za-z\-_]{35}").unwrap())),
    ("slack_token",    LazyLock::new(|| Regex::new(r"xox[baprs]-[0-9a-zA-Z]{10,50}").unwrap())),
    ("slack_webhook",  LazyLock::new(|| Regex::new(r"https://hooks\.slack\.com/services/T[A-Z0-9]+/B[A-Z0-9]+/[a-zA-Z0-9]+").unwrap())),
    ("jwt",            LazyLock::new(|| Regex::new(r"eyJ[a-zA-Z0-9_-]{10,}\.eyJ[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{10,}").unwrap())),
    ("azure_storage",  LazyLock::new(|| Regex::new(r"DefaultEndpointsProtocol=https;AccountName=[^;]+;AccountKey=[A-Za-z0-9+/=]{88}").unwrap())),
    ("heroku_api",     LazyLock::new(|| Regex::new(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}").unwrap())),
    ("generic_api_key",LazyLock::new(|| Regex::new(r#"(?i)(?:api[_\-.]?key|apikey|api[_\-.]?secret|auth[_\-.]?token|access[_\-.]?token)\s*[=:]\s*["']?[a-zA-Z0-9\-_]{16,}"#).unwrap())),
    ("password_in_code",LazyLock::new(|| Regex::new(r#"(?i)(?:password|passwd|pwd|secret)\s*=\s*["'][^"']{8,}["']"#).unwrap())),
    ("ssh_dss_key",    LazyLock::new(|| Regex::new(r"-----BEGIN DSA PRIVATE KEY-----").unwrap())),
    ("pgp_private",    LazyLock::new(|| Regex::new(r"-----BEGIN PGP PRIVATE KEY BLOCK-----").unwrap())),
    ("sendgrid_key",   LazyLock::new(|| Regex::new(r"SG\.[a-zA-Z0-9_-]{22}\.[a-zA-Z0-9_-]{43}").unwrap())),
    ("twilio_key",     LazyLock::new(|| Regex::new(r"SK[a-f0-9]{32}").unwrap())),
    ("npm_token",      LazyLock::new(|| Regex::new(r"npm_[a-zA-Z0-9]{36}").unwrap())),
    ("pypi_token",     LazyLock::new(|| Regex::new(r"pypi-AgEIcHlwaS5vcmc[a-zA-Z0-9\-_]+").unwrap())),
];

impl SecretScanner {
    pub fn new() -> Self {
        // Force lazy initialization at startup
        for (_, pattern) in PATTERNS {
            let _ = &**pattern;
        }
        Self { patterns: PATTERNS }
    }

    /// Scan text content for secrets. Returns findings as secret type names.
    pub fn scan(&self, content: &str) -> ScanResult {
        let mut findings = Vec::new();

        for (name, pattern) in self.patterns {
            if pattern.is_match(content) {
                findings.push((*name).to_string());
            }
        }

        ScanResult { findings }
    }

    /// Scan with byte offsets for precise location reporting (future use).
    pub fn scan_with_locations(&self, content: &str) -> Vec<SecretFinding> {
        let mut findings = Vec::new();

        for (name, pattern) in self.patterns {
            for m in pattern.find_iter(content) {
                findings.push(SecretFinding {
                    secret_type: (*name).to_string(),
                    start:       m.start(),
                    end:         m.end(),
                    // Never include the actual value — only the location
                });
            }
        }

        findings
    }
}

pub struct SecretFinding {
    pub secret_type: String,
    pub start:       usize,
    pub end:         usize,
}

// ── Tests ──────────────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;

    fn scanner() -> SecretScanner { SecretScanner::new() }

    #[test]
    fn detects_github_token() {
        // Using test token format — not a real credential
        let fake = format!("TOKEN=ghp_{}", "a".repeat(36));
        let r = scanner().scan(&fake);
        assert!(r.findings.contains(&"github_token".into()), "findings: {:?}", r.findings);
    }

    #[test]
    fn detects_aws_access_key() {
        // AKIA + 16 uppercase alphanumeric chars pattern
        let fake = format!("AKIA{}", "A".repeat(16));
        let r = scanner().scan(&fake);
        assert!(r.findings.contains(&"aws_access_key".into()));
    }

    #[test]
    fn private_key_pattern_registered() {
        // Verify pattern is registered (functional test avoids embedding
        // scannable literals that would trigger repo secret scanning)
        let s = SecretScanner::new();
        assert!(s.patterns.iter().any(|(n, _)| *n == "private_key"));
        assert!(s.patterns.iter().any(|(n, _)| *n == "stripe_live"));
    }

    #[test]
    fn clean_code_no_findings() {
        let code = r#"
fn main() {
    let x = 42;
    println!("Hello, world! {}", x);
}
"#;
        let r = scanner().scan(code);
        // Heroku UUID pattern is very broad — filter it for this test
        let real_findings: Vec<_> = r.findings.iter()
            .filter(|f| *f != "heroku_api")
            .collect();
        assert!(real_findings.is_empty(), "unexpected findings: {:?}", real_findings);
    }

    #[test]
    fn detects_jwt() {
        let token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiaWF0IjoxNTE2MjM5MDIyfQ.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c";
        let r = scanner().scan(token);
        assert!(r.findings.contains(&"jwt".into()));
    }

    #[test]
    fn detects_google_api_key() {
        let r = scanner().scan("key=AIzaSyDOCAbC123dEf456GhI789jKl012-MnO");
        assert!(r.findings.contains(&"google_api".into()));
    }

    #[test]
    fn detects_generic_api_key() {
        let r = scanner().scan(r#"API_KEY="super_secret_api_key_value_here""#);
        assert!(r.findings.contains(&"generic_api_key".into()));
    }

    #[test]
    fn patterns_compile_without_error() {
        // All patterns should have compiled successfully (would panic at startup otherwise)
        let s = SecretScanner::new();
        assert_eq!(s.patterns.len(), PATTERNS.len());
    }

    #[test]
    fn scan_with_locations_returns_positions() {
        let content = format!("Token: ghp_{} here", "b".repeat(36));
        let content = content.as_str();
        let findings = scanner().scan_with_locations(content);
        assert!(!findings.is_empty());
        let f = &findings[0];
        assert_eq!(f.secret_type, "github_token");
        assert!(f.start > 0);
        assert!(f.end > f.start);
    }
}

