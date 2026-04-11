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

	"github.com/gaineyllc/dgraphai/agent/internal/classify"
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
			return nil // skip permission errors
		}
		select {
		case <-ctx.Done():
			return ctx.Err()
		default:
		}

		if d.IsDir() {
			name := d.Name()
			for _, ex := range c.excludeDirs {
				if name == ex {
					return filepath.SkipDir
				}
			}
			return nil
		}

		if !d.Type().IsRegular() {
			return nil
		}

		info, err := d.Info()
		if err != nil {
			return nil
		}

		ext := strings.ToLower(filepath.Ext(d.Name()))
		mimeType, fileCategory := classify.ClassifyFile(ext)

		rel, _ := filepath.Rel(c.root, path)
		fileInfo := FileInfo{
			Path:         "/" + filepath.ToSlash(rel),
			Name:         d.Name(),
			Extension:    ext,
			Size:         info.Size(),
			ModifiedAt:   info.ModTime().UTC(),
			IndexedAt:    time.Now().UTC(),
			Protocol:     "local",
			MIMEType:     mimeType,
			FileCategory: fileCategory,
		}

		if info.Size() < 500*1024*1024 {
			if hash, err := hashFile(path); err == nil {
				fileInfo.SHA256 = hash
			}
		}

		return fn(ctx, fileInfo)
	})
}

func (c *localConnector) Open(ctx context.Context, path string) (io.ReadCloser, error) {
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
