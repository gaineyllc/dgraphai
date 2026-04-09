//! PII scanner — detects personally identifiable information.
//! RE2-compatible patterns, linear time guaranteed.

use regex::Regex;
use std::sync::LazyLock;

pub struct ScanResult {
    pub findings: Vec<String>,
}

pub struct PIIScanner {
    patterns: &'static [(&'static str, LazyLock<Regex>)],
}

static PATTERNS: &[(&str, LazyLock<Regex>)] = &[
    // US Social Security Number
    ("ssn",         LazyLock::new(|| Regex::new(r"\b\d{3}-\d{2}-\d{4}\b").unwrap())),

    // Credit card numbers (Visa, Mastercard, Amex, Discover)
    ("credit_card", LazyLock::new(|| Regex::new(
        r"\b(?:4[0-9]{12}(?:[0-9]{3})?|5[1-5][0-9]{14}|3[47][0-9]{13}|6(?:011|5[0-9]{2})[0-9]{12})\b"
    ).unwrap())),

    // Email addresses
    ("email",       LazyLock::new(|| Regex::new(
        r"\b[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}\b"
    ).unwrap())),

    // US phone numbers (various formats)
    ("phone_us",    LazyLock::new(|| Regex::new(
        r"\b(?:\+?1[-.\s]?)?\(?[0-9]{3}\)?[-.\s][0-9]{3}[-.\s][0-9]{4}\b"
    ).unwrap())),

    // UK phone numbers
    ("phone_uk",    LazyLock::new(|| Regex::new(
        r"\b(?:\+44|0)7[0-9]{3}[-.\s]?[0-9]{3}[-.\s]?[0-9]{3}\b"
    ).unwrap())),

    // IP addresses (potential PII in access logs)
    ("ip_address",  LazyLock::new(|| Regex::new(
        r"\b(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\b"
    ).unwrap())),

    // IBAN (international bank account numbers)
    ("iban",        LazyLock::new(|| Regex::new(
        r"\b[A-Z]{2}[0-9]{2}[A-Z0-9]{4}[0-9]{7}(?:[A-Z0-9]?){0,16}\b"
    ).unwrap())),

    // US passport numbers
    ("passport_us", LazyLock::new(|| Regex::new(r"\b[A-Z][0-9]{8}\b").unwrap())),

    // Dates of birth patterns (common formats)
    ("date_of_birth", LazyLock::new(|| Regex::new(
        r"\bDOB[:\s]+\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b"
    ).unwrap())),

    // Medical record numbers (common pattern)
    ("medical_record", LazyLock::new(|| Regex::new(
        r"\b(?i)(?:mrn|medical[-_\s]?record[-_\s]?(?:number|no|#))[:\s]+[A-Z0-9]{5,15}\b"
    ).unwrap())),
];

impl PIIScanner {
    pub fn new() -> Self {
        for (_, p) in PATTERNS { let _ = &**p; }
        Self { patterns: PATTERNS }
    }

    pub fn scan(&self, content: &str) -> ScanResult {
        let mut findings = Vec::new();
        for (name, pattern) in self.patterns {
            if pattern.is_match(content) {
                findings.push((*name).to_string());
            }
        }
        ScanResult { findings }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn s() -> PIIScanner { PIIScanner::new() }

    #[test]
    fn detects_ssn() {
        assert!(s().scan("SSN: 123-45-6789").findings.contains(&"ssn".into()));
    }

    #[test]
    fn detects_email() {
        assert!(s().scan("user@example.com").findings.contains(&"email".into()));
    }

    #[test]
    fn detects_us_phone() {
        assert!(s().scan("Call (555) 867-5309").findings.contains(&"phone_us".into()));
    }

    #[test]
    fn detects_credit_card_visa() {
        // Luhn-valid Visa test number
        assert!(s().scan("Card: 4111111111111111").findings.contains(&"credit_card".into()));
    }

    #[test]
    fn detects_ip_address() {
        assert!(s().scan("192.168.1.100 requested /api").findings.contains(&"ip_address".into()));
    }

    #[test]
    fn clean_text_no_pii() {
        let text = "The quick brown fox jumps over the lazy dog.";
        let r = s().scan(text);
        // IP pattern shouldn't match "dog." and similar
        assert!(r.findings.is_empty(), "unexpected: {:?}", r.findings);
    }

    #[test]
    fn multiple_types_detected() {
        let text = "Email: alice@example.com, SSN: 123-45-6789";
        let r = s().scan(text);
        assert!(r.findings.contains(&"email".into()));
        assert!(r.findings.contains(&"ssn".into()));
        assert_eq!(r.findings.len(), 2);
    }
}
