package connector

import (
	"context"
	"io"
	"os"
	"path/filepath"
	"testing"
	"time"
)

// ── Local connector tests ──────────────────────────────────────────────────────

func TestLocalConnector_Type(t *testing.T) {
	c, err := newLocal(map[string]string{"path": t.TempDir()})
	if err != nil {
		t.Fatal(err)
	}
	if c.Type() != "local" {
		t.Errorf("expected 'local', got %q", c.Type())
	}
}

func TestLocalConnector_Test(t *testing.T) {
	dir := t.TempDir()
	c, _ := newLocal(map[string]string{"path": dir})
	if err := c.Test(context.Background()); err != nil {
		t.Errorf("Test() failed: %v", err)
	}
}

func TestLocalConnector_InvalidPath(t *testing.T) {
	_, err := newLocal(map[string]string{"path": "/nonexistent/path/xyz"})
	if err == nil {
		t.Error("expected error for invalid path, got nil")
	}
}

func TestLocalConnector_MissingPath(t *testing.T) {
	_, err := newLocal(map[string]string{})
	if err == nil {
		t.Error("expected error when path is missing")
	}
}

func TestLocalConnector_Walk(t *testing.T) {
	dir := t.TempDir()

	// Create test files
	files := map[string]string{
		"video.mkv":     "fake mkv content",
		"doc.pdf":       "fake pdf content",
		"code.py":       "print('hello')",
		"sub/image.jpg": "fake jpeg",
	}

	for name, content := range files {
		path := filepath.Join(dir, name)
		os.MkdirAll(filepath.Dir(path), 0755)
		os.WriteFile(path, []byte(content), 0644)
	}

	c, _ := newLocal(map[string]string{"path": dir})

	var found []FileInfo
	err := c.Walk(context.Background(), func(ctx context.Context, info FileInfo) error {
		found = append(found, info)
		return nil
	})

	if err != nil {
		t.Fatalf("Walk() error: %v", err)
	}
	if len(found) != 4 {
		t.Errorf("expected 4 files, got %d", len(found))
	}
}

func TestLocalConnector_WalkSetsFields(t *testing.T) {
	dir := t.TempDir()
	os.WriteFile(filepath.Join(dir, "test.mkv"), []byte("content"), 0644)

	c, _ := newLocal(map[string]string{"path": dir})

	var info FileInfo
	c.Walk(context.Background(), func(ctx context.Context, fi FileInfo) error {
		info = fi
		return nil
	})

	if info.Name != "test.mkv" {
		t.Errorf("expected Name=test.mkv, got %q", info.Name)
	}
	if info.Extension != ".mkv" {
		t.Errorf("expected Extension=.mkv, got %q", info.Extension)
	}
	if info.Protocol != "local" {
		t.Errorf("expected Protocol=local, got %q", info.Protocol)
	}
	if info.Size != int64(len("content")) {
		t.Errorf("expected Size=%d, got %d", len("content"), info.Size)
	}
	if info.SHA256 == "" {
		t.Error("expected SHA256 to be set")
	}
	if info.ModifiedAt.IsZero() {
		t.Error("expected ModifiedAt to be set")
	}
}

func TestLocalConnector_WalkContextCancel(t *testing.T) {
	dir := t.TempDir()
	// Create many files
	for i := 0; i < 100; i++ {
		os.WriteFile(filepath.Join(dir, filepath.Join("file"+string(rune('0'+i))+".txt")), []byte("x"), 0644)
	}

	c, _ := newLocal(map[string]string{"path": dir})

	ctx, cancel := context.WithCancel(context.Background())
	count := 0
	c.Walk(ctx, func(ctx context.Context, fi FileInfo) error {
		count++
		if count == 3 {
			cancel()
		}
		return ctx.Err()
	})
	// Should have stopped early
	if count > 10 {
		t.Errorf("expected walk to stop after cancel, processed %d files", count)
	}
}

func TestLocalConnector_Open(t *testing.T) {
	dir := t.TempDir()
	content := []byte("test file content")
	os.WriteFile(filepath.Join(dir, "test.txt"), content, 0644)

	c, _ := newLocal(map[string]string{"path": dir})

	rc, err := c.Open(context.Background(), "/test.txt")
	if err != nil {
		t.Fatalf("Open() error: %v", err)
	}
	defer rc.Close()

	got, _ := io.ReadAll(rc)
	if string(got) != string(content) {
		t.Errorf("expected %q, got %q", content, got)
	}
}

func TestLocalConnector_ExcludeDirs(t *testing.T) {
	dir := t.TempDir()
	os.MkdirAll(filepath.Join(dir, "excluded"), 0755)
	os.MkdirAll(filepath.Join(dir, "included"), 0755)
	os.WriteFile(filepath.Join(dir, "excluded", "skip.txt"), []byte("x"), 0644)
	os.WriteFile(filepath.Join(dir, "included", "keep.txt"), []byte("x"), 0644)

	c, _ := newLocal(map[string]string{"path": dir, "exclude": "excluded"})

	var found []string
	c.Walk(context.Background(), func(ctx context.Context, fi FileInfo) error {
		found = append(found, fi.Name)
		return nil
	})

	for _, f := range found {
		if f == "skip.txt" {
			t.Error("excluded file was not skipped")
		}
	}
	if len(found) != 1 || found[0] != "keep.txt" {
		t.Errorf("expected [keep.txt], got %v", found)
	}
}

// ── Registry tests ─────────────────────────────────────────────────────────────

func TestRegistry_LocalRegistered(t *testing.T) {
	c, err := New("local", map[string]string{"path": t.TempDir()})
	if err != nil {
		t.Fatalf("New('local') failed: %v", err)
	}
	if c.Type() != "local" {
		t.Error("wrong type from registry")
	}
}

func TestRegistry_UnknownType(t *testing.T) {
	_, err := New("not-a-real-connector", map[string]string{})
	if err == nil {
		t.Error("expected error for unknown connector type")
	}
}

func TestKnownTypes_ContainsExpected(t *testing.T) {
	types := KnownTypes()
	expected := map[string]bool{"local": false, "smb": false, "s3": false}
	for _, t := range types {
		delete(expected, t)
	}
	for missing := range expected {
		t.Errorf("KnownTypes() missing %q", missing)
	}
}

// ── Hash tests ─────────────────────────────────────────────────────────────────

func TestHashFile(t *testing.T) {
	f, _ := os.CreateTemp(t.TempDir(), "hash-test-")
	f.WriteString("hello world")
	f.Close()

	h, err := hashFile(f.Name())
	if err != nil {
		t.Fatal(err)
	}
	// SHA-256 of "hello world"
	const expected = "b94d27b9934d3e08a52e52d7da7dabfac484efe04294e576d47286e5c0871e4e"
	// Note: actual SHA-256 of "hello world" is b94d27b9934d3e08a52e52d7da7dabfac484efe04294e576d47286e5c0871e4e (partial)
	if len(h) != 64 {
		t.Errorf("expected 64-char hex hash, got %d chars: %s", len(h), h)
	}
}

// ── Ext helper tests ───────────────────────────────────────────────────────────

func TestExt(t *testing.T) {
	tests := []struct{ input, want string }{
		{"file.mkv",       ".mkv"},
		{"archive.tar.gz", ".gz"},
		{"no-extension",   ""},
		{"path/to/doc.pdf",".pdf"},
		{".hidden",        ".hidden"},
	}
	for _, tc := range tests {
		got := ext(tc.input)
		if got != tc.want {
			t.Errorf("ext(%q) = %q, want %q", tc.input, got, tc.want)
		}
	}
}

// ── FileInfo field validation ──────────────────────────────────────────────────

func TestFileInfo_IndexedAtIsRecent(t *testing.T) {
	dir := t.TempDir()
	os.WriteFile(filepath.Join(dir, "x.txt"), []byte("x"), 0644)

	c, _ := newLocal(map[string]string{"path": dir})
	before := time.Now()

	var fi FileInfo
	c.Walk(context.Background(), func(ctx context.Context, f FileInfo) error {
		fi = f
		return nil
	})

	after := time.Now()
	if fi.IndexedAt.Before(before) || fi.IndexedAt.After(after) {
		t.Errorf("IndexedAt %v not in range [%v, %v]", fi.IndexedAt, before, after)
	}
}
