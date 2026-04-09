// subprocess.go — calls dgraph-enricher (Rust binary) as a subprocess.
//
// The Rust enricher runs in a sandboxed subprocess with:
//   - Hard 5-second timeout (context deadline)
//   - 256MB memory limit (caller sets via ulimit before exec)
//   - Reads from stdin, writes to stdout — no filesystem writes
//   - Logs to stderr only
//
// This file wraps the subprocess protocol so the Go agent
// can call it transparently via the Enricher interface.
package enricher

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"time"

	"github.com/gaineyllc/dgraphai/agent/internal/connector"
)

const (
	subprocessTimeout = 5 * time.Second
	maxContentBytes   = 1024 * 1024 // 1MB
)

// SubprocessEnricher calls the Rust dgraph-enricher binary.
// Falls back to the pure-Go enricher if the binary is not found.
type SubprocessEnricher struct {
	binaryPath string
	fallback   *Enricher
}

// SubprocessRequest is sent to the enricher via stdin.
type SubprocessRequest struct {
	Path      string `json:"path"`
	Category  string `json:"category"`
	MaxBytes  int    `json:"max_bytes"`
	TenantID  string `json:"tenant_id,omitempty"`
	NodeID    string `json:"node_id,omitempty"`
}

// SubprocessResponse is received from the enricher via stdout.
type SubprocessResponse struct {
	NodeID           string   `json:"node_id,omitempty"`
	Path             string   `json:"path"`
	ContainsSecrets  bool     `json:"contains_secrets"`
	SecretTypes      []string `json:"secret_types,omitempty"`
	PIIDetected      bool     `json:"pii_detected"`
	PIITypes         []string `json:"pii_types,omitempty"`
	SensitivityLevel string   `json:"sensitivity_level"`
	BinaryFormat     *string  `json:"binary_format,omitempty"`
	Entropy          *float64 `json:"entropy,omitempty"`
	IsPacked         *bool    `json:"is_packed,omitempty"`
	IsSigned         *bool    `json:"is_signed,omitempty"`
	Architecture     *string  `json:"architecture,omitempty"`
	BytesRead        int      `json:"bytes_read"`
	DurationMS       int64    `json:"duration_ms"`
	Error            *string  `json:"error,omitempty"`
}

// BinaryPath returns the resolved path to the dgraph-enricher binary.
func (e *SubprocessEnricher) BinaryPath() string { return e.binaryPath }

// NewSubprocessEnricher creates an enricher that calls the Rust binary.
// Falls back to Go enricher if the binary path doesn't exist.
func NewSubprocessEnricher(binaryPath string, enableSecrets, enablePII bool) *SubprocessEnricher {
	if binaryPath == "" {
		binaryPath = defaultBinaryPath()
	}
	return &SubprocessEnricher{
		binaryPath: binaryPath,
		fallback:   New(enableSecrets, enablePII),
	}
}

// EnrichViaSubprocess calls the Rust binary and returns enrichment results
// merged into the FileInfo attrs map.
func (e *SubprocessEnricher) EnrichViaSubprocess(
	ctx context.Context,
	info *connector.FileInfo,
) error {
	// Check if binary exists
	if _, err := os.Stat(e.binaryPath); os.IsNotExist(err) {
		// Fall back to Go enricher
		if !isTextLike(info.Extension) {
			return nil
		}
		rc, err := openFileForEnrichment(info)
		if err != nil {
			return nil // skip — file may not be accessible
		}
		defer rc.Close()
		result, err := e.fallback.Enrich(ctx, rc, *info)
		if err != nil {
			return err
		}
		e.fallback.ApplyToFileInfo(info, result)
		return nil
	}

	// Use Rust subprocess
	req := SubprocessRequest{
		Path:     resolvePath(info),
		Category: info.FileCategory,
		MaxBytes: maxContentBytes,
		NodeID:   info.Path, // use path as node identifier
	}

	reqJSON, err := json.Marshal(req)
	if err != nil {
		return fmt.Errorf("enricher: marshal request: %w", err)
	}

	// Run with timeout
	ctx, cancel := context.WithTimeout(ctx, subprocessTimeout)
	defer cancel()

	cmd := exec.CommandContext(ctx, e.binaryPath, "scan")
	cmd.Stdin  = bytes.NewReader(reqJSON)
	cmd.Stderr = nil // discard — enricher logs to stderr

	var stdout bytes.Buffer
	cmd.Stdout = &stdout

	if err := cmd.Run(); err != nil {
		if ctx.Err() == context.DeadlineExceeded {
			return fmt.Errorf("enricher: timeout after %v for %s", subprocessTimeout, info.Path)
		}
		return fmt.Errorf("enricher: subprocess error: %w", err)
	}

	var resp SubprocessResponse
	if err := json.Unmarshal(stdout.Bytes(), &resp); err != nil {
		return fmt.Errorf("enricher: parse response: %w", err)
	}

	// Apply results to FileInfo attrs
	applySubprocessResponse(info, &resp)
	return nil
}

func applySubprocessResponse(info *connector.FileInfo, resp *SubprocessResponse) {
	if info.Attrs == nil {
		info.Attrs = make(map[string]any)
	}
	if resp.ContainsSecrets {
		info.Attrs["contains_secrets"] = true
		info.Attrs["secret_types"]     = joinStrings(resp.SecretTypes)
	}
	if resp.PIIDetected {
		info.Attrs["pii_detected"]      = true
		info.Attrs["pii_types"]         = joinStrings(resp.PIITypes)
		info.Attrs["sensitivity_level"] = resp.SensitivityLevel
	}
	if resp.BinaryFormat != nil {
		info.Attrs["binary_format"] = *resp.BinaryFormat
	}
	if resp.Entropy != nil {
		info.Attrs["entropy"] = *resp.Entropy
	}
	if resp.IsPacked != nil {
		info.Attrs["is_packed"] = *resp.IsPacked
	}
	if resp.IsSigned != nil {
		info.Attrs["signed"] = *resp.IsSigned
	}
	if resp.Architecture != nil {
		info.Attrs["architecture"] = *resp.Architecture
	}
}

func defaultBinaryPath() string {
	// Look for dgraph-enricher next to the agent binary
	exe, err := os.Executable()
	if err != nil {
		return "dgraph-enricher"
	}
	dir := filepath.Dir(exe)
	name := "dgraph-enricher"
	if runtime.GOOS == "windows" {
		name += ".exe"
	}
	candidate := filepath.Join(dir, name)
	if _, err := os.Stat(candidate); err == nil {
		return candidate
	}
	// Fall back to PATH
	if path, err := exec.LookPath(name); err == nil {
		return path
	}
	return name
}

func resolvePath(info *connector.FileInfo) string {
	// For local files, return the full filesystem path
	// For remote files, the enricher can't access them directly
	return info.Path
}

func openFileForEnrichment(info *connector.FileInfo) (interface{ Read([]byte) (int, error); Close() error }, error) {
	if info.Protocol == "local" {
		return os.Open(info.Path)
	}
	return nil, fmt.Errorf("cannot open remote file for Go enricher")
}

func joinStrings(ss []string) string {
	if len(ss) == 0 {
		return ""
	}
	result := ss[0]
	for _, s := range ss[1:] {
		result += "," + s
	}
	return result
}
