package connector

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"io"
	"io/fs"
	"os"
	"path/filepath"
	"strings"
	"time"
)

// localConnector walks a local filesystem path.
type localConnector struct {
	root        string
	excludeDirs []string
}

func newLocal(settings map[string]string) (Connector, error) {
	root := settings["path"]
	if root == "" {
		return nil, fmt.Errorf("local connector: 'path' setting is required")
	}
	if _, err := os.Stat(root); err != nil {
		return nil, fmt.Errorf("local connector: path %q: %w", root, err)
	}

	exclude := []string{}
	if ex := settings["exclude"]; ex != "" {
		for _, p := range strings.Split(ex, ",") {
			exclude = append(exclude, strings.TrimSpace(p))
		}
	}

	return &localConnector{root: root, excludeDirs: exclude}, nil
}

func (c *localConnector) Type() string { return "local" }

func (c *localConnector) Test(ctx context.Context) error {
	_, err := os.Stat(c.root)
	return err
}

func (c *localConnector) Walk(ctx context.Context, fn WalkFunc) error {
	return filepath.WalkDir(c.root, func(path string, d fs.DirEntry, err error) error {
		if err != nil {
			// Log permission errors but continue
			return nil
		}
		select {
		case <-ctx.Done():
			return ctx.Err()
		default:
		}

		// Skip excluded dirs
		if d.IsDir() {
			name := d.Name()
			for _, ex := range c.excludeDirs {
				if name == ex {
					return filepath.SkipDir
				}
			}
			return nil
		}

		// Only process regular files
		if !d.Type().IsRegular() {
			return nil
		}

		info, err := d.Info()
		if err != nil {
			return nil
		}

		rel, _ := filepath.Rel(c.root, path)
		fileInfo := FileInfo{
			Path:       "/" + filepath.ToSlash(rel),
			Name:       d.Name(),
			Extension:  strings.ToLower(filepath.Ext(d.Name())),
			Size:       info.Size(),
			ModifiedAt: info.ModTime().UTC(),
			IndexedAt:  time.Now().UTC(),
			Protocol:   "local",
		}

		// Compute SHA-256 for deduplication (stream, don't load into memory)
		if info.Size() < 500*1024*1024 { // Skip files >500MB
			if hash, err := hashFile(path); err == nil {
				fileInfo.SHA256 = hash
			}
		}

		return fn(ctx, fileInfo)
	})
}

func (c *localConnector) Open(ctx context.Context, path string) (io.ReadCloser, error) {
	// Reconstruct absolute path from relative path
	abs := filepath.Join(c.root, filepath.FromSlash(strings.TrimPrefix(path, "/")))
	return os.Open(abs)
}

func hashFile(path string) (string, error) {
	f, err := os.Open(path)
	if err != nil {
		return "", err
	}
	defer f.Close()

	h := sha256.New()
	if _, err := io.Copy(h, f); err != nil {
		return "", err
	}
	return hex.EncodeToString(h.Sum(nil)), nil
}
