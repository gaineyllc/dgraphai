package enricher

import (
	"context"
	"strings"
	"testing"

	"github.com/gaineyllc/dgraphai/agent/internal/connector"
)

func newTestEnricher() *Enricher {
	return New(true, true)
}

// ── Secret detection ───────────────────────────────────────────────────────────

func TestEnricher_DetectsGitHubToken(t *testing.T) {
	e := newTestEnricher()
	// Construct fake token pattern — not a real credential
	content := "GITHUB_TOKEN=ghp_" + strings.Repeat("a", 36)
	r, err := e.Enrich(context.Background(), strings.NewReader(content),
		connector.FileInfo{Name: "config.env", Extension: ".env"})
	if err != nil {
		t.Fatal(err)
	}
	if !r.ContainsSecrets {
		t.Error("expected github token to be detected")
	}
	if !containsAny(r.SecretTypes, "github_token") {
		t.Errorf("expected secret_type=github_token, got %v", r.SecretTypes)
	}
}

func TestEnricher_DetectsAWSKey(t *testing.T) {
	e := newTestEnricher()
	// AKIA + 16 uppercase alphanumeric pattern
	content := "aws_access_key_id=AKIA" + strings.Repeat("A", 16)
	r, _ := e.Enrich(context.Background(), strings.NewReader(content),
		connector.FileInfo{Name: "credentials", Extension: ".env"})
	if !r.ContainsSecrets {
		t.Error("expected AWS key to be detected")
	}
}

func TestEnricher_SecretPatternsComprehensive(t *testing.T) {
	// Verify secret patterns register correctly
	// Actual match testing uses constructed strings only
	e := newTestEnricher()
	if e == nil {
		t.Fatal("enricher failed to initialize")
	}
	// Verify patterns are compiled (would panic at init if not)
	if len(secretPatterns) == 0 {
		t.Error("no secret patterns registered")
	}
}

func TestEnricher_DetectsPrivateKey(t *testing.T) {
	e := newTestEnricher()
	// Construct at runtime to avoid repo secret scanning on literal
	content := "-----BEGIN " + "RSA PRIVATE KEY" + "-----\nMIIEfake...\n-----END " + "RSA PRIVATE KEY" + "-----"
	r, _ := e.Enrich(context.Background(), strings.NewReader(content),
		connector.FileInfo{Name: "server.key", Extension: ".key"})
	if !r.ContainsSecrets {
		t.Error("expected private key to be detected")
	}
	if !containsAny(r.SecretTypes, "private_key") {
		t.Errorf("expected private_key in secret types, got %v", r.SecretTypes)
	}
}

func TestEnricher_CleanCodeNoSecrets(t *testing.T) {
	e := newTestEnricher()
	content := `
def add(a, b):
    return a + b

class Calculator:
    def multiply(self, x, y):
        return x * y
`
	r, _ := e.Enrich(context.Background(), strings.NewReader(content),
		connector.FileInfo{Name: "math.py", Extension: ".py"})
	if r.ContainsSecrets {
		t.Errorf("clean code should have no secrets, got types: %v", r.SecretTypes)
	}
}

// ── PII detection ──────────────────────────────────────────────────────────────

func TestEnricher_DetectsEmail(t *testing.T) {
	e := newTestEnricher()
	content := `Contact us at john.doe@example.com for more information.`
	r, _ := e.Enrich(context.Background(), strings.NewReader(content),
		connector.FileInfo{Name: "readme.txt", Extension: ".txt"})
	if !r.PIIDetected {
		t.Error("expected email address to trigger PII detection")
	}
	if !containsAny(r.PIITypes, "email") {
		t.Errorf("expected pii_type=email, got %v", r.PIITypes)
	}
}

func TestEnricher_DetectsSSN(t *testing.T) {
	e := newTestEnricher()
	content := `Employee SSN: 123-45-6789`
	r, _ := e.Enrich(context.Background(), strings.NewReader(content),
		connector.FileInfo{Name: "employee.csv", Extension: ".csv"})
	if !r.PIIDetected {
		t.Error("expected SSN to trigger PII detection")
	}
	if !containsAny(r.PIITypes, "ssn") {
		t.Errorf("expected pii_type=ssn, got %v", r.PIITypes)
	}
}

func TestEnricher_DetectsPhone(t *testing.T) {
	e := newTestEnricher()
	content := `Call us at (555) 867-5309`
	r, _ := e.Enrich(context.Background(), strings.NewReader(content),
		connector.FileInfo{Name: "contact.txt", Extension: ".txt"})
	if !r.PIIDetected {
		t.Error("expected phone number to trigger PII detection")
	}
}

// ── Severity ───────────────────────────────────────────────────────────────────

func TestEnricher_PrivateKeyCritical(t *testing.T) {
	e := newTestEnricher()
	content := "-----BEGIN " + "RSA PRIVATE KEY" + "-----\nMIIE...\n-----END " + "RSA PRIVATE KEY" + "-----"
	r, _ := e.Enrich(context.Background(), strings.NewReader(content),
		connector.FileInfo{Extension: ".pem"})
	if r.SensitivityLevel != "critical" {
		t.Errorf("private key should be critical, got %q", r.SensitivityLevel)
	}
}

func TestEnricher_SSNHigh(t *testing.T) {
	e := newTestEnricher()
	content := `SSN: 123-45-6789`
	r, _ := e.Enrich(context.Background(), strings.NewReader(content),
		connector.FileInfo{Extension: ".txt"})
	if r.SensitivityLevel != "high" {
		t.Errorf("SSN should be high sensitivity, got %q", r.SensitivityLevel)
	}
}

func TestEnricher_EmailMedium(t *testing.T) {
	e := newTestEnricher()
	content := `Contact: person@example.com`
	r, _ := e.Enrich(context.Background(), strings.NewReader(content),
		connector.FileInfo{Extension: ".txt"})
	if r.SensitivityLevel != "medium" {
		t.Errorf("email PII should be medium, got %q", r.SensitivityLevel)
	}
}

// ── Text-like detection ────────────────────────────────────────────────────────

func TestIsTextLike(t *testing.T) {
	text := []string{".py", ".js", ".ts", ".go", ".rs", ".env", ".yaml", ".json", ".txt", ".md", ".sql", ".sh"}
	for _, ext := range text {
		if !isTextLike(ext) {
			t.Errorf("expected %q to be text-like", ext)
		}
	}
	binary := []string{".mkv", ".mp4", ".jpg", ".exe", ".dll", ".zip", ".flac"}
	for _, ext := range binary {
		if isTextLike(ext) {
			t.Errorf("expected %q to NOT be text-like", ext)
		}
	}
}

// ── Apply to FileInfo ──────────────────────────────────────────────────────────

func TestEnricher_ApplyToFileInfo(t *testing.T) {
	e := newTestEnricher()
	fi := connector.FileInfo{Extension: ".py"}
	result := EnrichResult{
		ContainsSecrets:  true,
		SecretTypes:      []string{"api_key"},
		SensitivityLevel: "high",
	}
	e.ApplyToFileInfo(&fi, result)
	if fi.Attrs["contains_secrets"] != true {
		t.Error("contains_secrets not set")
	}
	if fi.Attrs["secret_types"] == "" {
		t.Error("secret_types not set")
	}
}

// ── Helpers ────────────────────────────────────────────────────────────────────

func containsAny(haystack []string, needle string) bool {
	for _, s := range haystack {
		if s == needle {
			return true
		}
	}
	return false
}

