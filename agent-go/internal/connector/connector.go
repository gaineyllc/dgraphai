// Package connector defines the interface all data source connectors implement.
// New connector types are added by implementing this interface — no core changes needed.
package connector

import (
	"context"
	"io"
	"time"
)

// FileInfo is a normalized file record from any connector type.
// This is what gets sent to the cloud API — never raw file content.
type FileInfo struct {
	// Identity
	ConnectorID string `json:"connector_id"`
	Path        string `json:"path"`
	Name        string `json:"name"`
	Extension   string `json:"extension"`

	// Content identity (no content, just hashes)
	SHA256  string `json:"sha256,omitempty"`
	XXHash  string `json:"xxhash,omitempty"`  // fast hash for dedup
	Size    int64  `json:"size"`

	// Timestamps
	ModifiedAt time.Time  `json:"modified_at"`
	CreatedAt  *time.Time `json:"created_at,omitempty"`
	IndexedAt  time.Time  `json:"indexed_at"`

	// Classification (set by local enricher before upload)
	FileCategory string            `json:"file_category,omitempty"`
	MIMEType     string            `json:"mime_type,omitempty"`
	Attrs        map[string]any    `json:"attrs,omitempty"` // enriched metadata

	// Source location
	Host     string `json:"host,omitempty"`
	Share    string `json:"share,omitempty"`
	Protocol string `json:"protocol"`       // local|smb|s3|nfs
}

// WalkFunc is called for each file discovered during a scan.
// Return an error to stop the walk.
type WalkFunc func(ctx context.Context, info FileInfo) error

// Connector is the interface every data source must implement.
type Connector interface {
	// Type returns the connector type identifier (e.g. "smb", "local", "s3").
	Type() string

	// Test verifies connectivity and credentials before committing to a full scan.
	Test(ctx context.Context) error

	// Walk traverses the data source, calling fn for each file discovered.
	// It must handle its own retries for transient failures.
	// ctx cancellation must be respected.
	Walk(ctx context.Context, fn WalkFunc) error

	// Open returns a ReadCloser for the file at path.
	// Used by the enricher to read content for secret/PII scanning.
	// Returns nil, ErrNotSupported if content access is not available.
	Open(ctx context.Context, path string) (io.ReadCloser, error)
}

// ErrNotSupported is returned when a connector doesn't support content access.
var ErrNotSupported = fmt.Errorf("not supported by this connector")

// Registry maps type strings to constructor functions.
var registry = map[string]func(settings map[string]string) (Connector, error){}

// Register adds a connector constructor to the global registry.
func Register(connType string, fn func(map[string]string) (Connector, error)) {
	registry[connType] = fn
}

// New creates a connector from a type string and settings map.
func New(connType string, settings map[string]string) (Connector, error) {
	fn, ok := registry[connType]
	if !ok {
		return nil, fmt.Errorf("unknown connector type: %q", connType)
	}
	return fn(settings)
}

// KnownTypes returns all registered connector type names.
func KnownTypes() []string {
	types := make([]string, 0, len(registry))
	for t := range registry {
		types = append(types, t)
	}
	return types
}

// init registers built-in connectors
func init() {
	Register("local", newLocal)
	Register("smb",   newSMB)
	Register("s3",    newS3)
}
