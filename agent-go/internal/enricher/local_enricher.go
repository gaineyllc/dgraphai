// Package enricher performs local analysis BEFORE data leaves the network.
// Sensitive findings (secrets, PII) are computed here so only
// boolean flags and metadata travel to the cloud — never the actual content.
package enricher

import (
	"bufio"
	"context"
	"io"
	"regexp"
	"strings"

	"github.com/gaineyllc/dgraphai/agent/internal/connector"
)

// SecretPattern defines a secret detection rule.
type SecretPattern struct {
	Name    string
	Pattern *regexp.Regexp
}

// Built-in secret patterns (entropy-based detection happens separately)
var secretPatterns = []SecretPattern{
	{Name: "aws_key",        Pattern: regexp.MustCompile(`(?i)aws[_\-]?(access[_\-]?key[_\-]?id|secret)[^\w][\w+/]{20,40}`)},
	{Name: "github_token",   Pattern: regexp.MustCompile(`ghp_[a-zA-Z0-9]{36}|github_pat_[a-zA-Z0-9_]{82}`)},
	{Name: "stripe_key",     Pattern: regexp.MustCompile(`sk_(live|test)_[a-zA-Z0-9]{24,}`)},
	{Name: "private_key",    Pattern: regexp.MustCompile(`-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----`)},
	{Name: "google_api",     Pattern: regexp.MustCompile(`AIza[0-9A-Za-z\-_]{35}`)},
	{Name: "slack_token",    Pattern: regexp.MustCompile(`xox[baprs]-[0-9a-zA-Z]{10,48}`)},
	{Name: "jwt",            Pattern: regexp.MustCompile(`eyJ[a-zA-Z0-9_\-]{4,}\.eyJ[a-zA-Z0-9_\-]{4,}\.[a-zA-Z0-9_\-]{4,}`)},
	{Name: "generic_secret", Pattern: regexp.MustCompile(`(?i)(secret[_\-]?key|api[_\-]?key|auth[_\-]?token|access[_\-]?token)\s*[=:]\s*["']?[a-zA-Z0-9+/=_\-]{16,}`)},
	{Name: "password_in_code", Pattern: regexp.MustCompile(`(?i)(password|passwd|pwd)\s*[=:]\s*["'][^"']{8,}["']`)},
}

var piiPatterns = []SecretPattern{
	{Name: "email",  Pattern: regexp.MustCompile(`[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}`)},
	{Name: "phone",  Pattern: regexp.MustCompile(`\b(\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b`)},
	{Name: "ssn",    Pattern: regexp.MustCompile(`\b\d{3}-\d{2}-\d{4}\b`)},
	{Name: "cc",     Pattern: regexp.MustCompile(`\b(?:4[0-9]{12}(?:[0-9]{3})?|5[1-5][0-9]{14}|3[47][0-9]{13})\b`)},
}

// Enricher runs local analysis on file content.
type Enricher struct {
	enableSecrets bool
	enablePII     bool
}

func New(enableSecrets, enablePII bool) *Enricher {
	return &Enricher{enableSecrets: enableSecrets, enablePII: enablePII}
}

// EnrichResult is the output of local analysis — no content, just findings.
type EnrichResult struct {
	ContainsSecrets bool
	SecretTypes     []string
	PIIDetected     bool
	PIITypes        []string
	SensitivityLevel string // low | medium | high | critical
}

// Enrich reads up to maxBytes of a file and returns findings.
// It NEVER returns the actual content — only metadata about what was found.
func (e *Enricher) Enrich(ctx context.Context, r io.Reader, info connector.FileInfo) (EnrichResult, error) {
	result := EnrichResult{}

	// Only scan text-like files (skip binary media)
	if !isTextLike(info.Extension) {
		return result, nil
	}

	// Read up to 1MB for scanning (enough to catch most secrets)
	const maxBytes = 1024 * 1024
	lr := &io.LimitedReader{R: r, N: maxBytes}

	scanner := bufio.NewScanner(lr)
	scanner.Buffer(make([]byte, 64*1024), 64*1024)

	var lines []string
	for scanner.Scan() {
		lines = append(lines, scanner.Text())
		if len(lines) > 10000 {
			break
		}
	}

	text := strings.Join(lines, "\n")

	if e.enableSecrets {
		for _, p := range secretPatterns {
			if p.Pattern.MatchString(text) {
				result.ContainsSecrets = true
				result.SecretTypes = append(result.SecretTypes, p.Name)
			}
		}
	}

	if e.enablePII {
		for _, p := range piiPatterns {
			if p.Pattern.MatchString(text) {
				result.PIIDetected = true
				result.PIITypes = append(result.PIITypes, p.Name)
			}
		}
	}

	// Compute severity
	result.SensitivityLevel = computeSeverity(result)

	return result, nil
}

// ApplyToFileInfo adds enrichment findings to a FileInfo attrs map.
func (e *Enricher) ApplyToFileInfo(info *connector.FileInfo, result EnrichResult) {
	if info.Attrs == nil {
		info.Attrs = make(map[string]any)
	}
	if result.ContainsSecrets {
		info.Attrs["contains_secrets"] = true
		info.Attrs["secret_types"]     = strings.Join(result.SecretTypes, ",")
	}
	if result.PIIDetected {
		info.Attrs["pii_detected"]     = true
		info.Attrs["pii_types"]        = strings.Join(result.PIITypes, ",")
		info.Attrs["sensitivity_level"]= result.SensitivityLevel
	}
}

func computeSeverity(r EnrichResult) string {
	if r.ContainsSecrets {
		for _, t := range r.SecretTypes {
			if strings.Contains(t, "private_key") || strings.Contains(t, "aws") {
				return "critical"
			}
		}
		return "high"
	}
	if r.PIIDetected {
		for _, t := range r.PIITypes {
			if t == "ssn" || t == "cc" {
				return "high"
			}
		}
		return "medium"
	}
	return "low"
}

// isTextLike returns true for file extensions that contain scannable text.
func isTextLike(ext string) bool {
	textExts := map[string]bool{
		".py": true, ".js": true, ".ts": true, ".go": true, ".rs": true,
		".java": true, ".cs": true, ".cpp": true, ".c": true, ".h": true,
		".rb": true, ".php": true, ".sh": true, ".bash": true, ".ps1": true,
		".env": true, ".yaml": true, ".yml": true, ".toml": true, ".ini": true,
		".json": true, ".xml": true, ".conf": true, ".cfg": true, ".config": true,
		".txt": true, ".md": true, ".csv": true, ".sql": true, ".properties": true,
		".tf": true, ".hcl": true, ".dockerfile": true, ".pem": true, ".key": true,
	}
	return textExts[strings.ToLower(ext)]
}
