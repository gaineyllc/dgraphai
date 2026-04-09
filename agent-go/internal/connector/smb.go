package connector

import (
	"context"
	"fmt"
	"io"
	"net"
	"strings"
	"time"

	"github.com/hirochachacha/go-smb2"
)

// smbConnector indexes files over SMB/CIFS.
type smbConnector struct {
	host     string
	port     string
	share    string
	username string
	password string // SENSITIVE — never logged
	domain   string
	basePath string
}

func newSMB(settings map[string]string) (Connector, error) {
	host := settings["host"]
	if host == "" {
		return nil, fmt.Errorf("smb connector: 'host' is required")
	}
	share := settings["share"]
	if share == "" {
		return nil, fmt.Errorf("smb connector: 'share' is required")
	}
	port := settings["port"]
	if port == "" {
		port = "445"
	}

	return &smbConnector{
		host:     host,
		port:     port,
		share:    share,
		username: settings["username"],
		password: settings["password"],
		domain:   settings["domain"],
		basePath: settings["base_path"],
	}, nil
}

func (c *smbConnector) Type() string { return "smb" }

func (c *smbConnector) dial() (*smb2.Session, error) {
	conn, err := net.DialTimeout("tcp", net.JoinHostPort(c.host, c.port), 10*time.Second)
	if err != nil {
		return nil, fmt.Errorf("smb: dial %s:%s: %w", c.host, c.port, err)
	}

	d := &smb2.Dialer{
		Initiator: &smb2.NTLMInitiator{
			User:     c.username,
			Password: c.password,
			Domain:   c.domain,
		},
	}
	session, err := d.Dial(conn)
	if err != nil {
		conn.Close()
		return nil, fmt.Errorf("smb: auth to %s: %w", c.host, err)
	}
	return session, nil
}

func (c *smbConnector) Test(ctx context.Context) error {
	session, err := c.dial()
	if err != nil {
		return err
	}
	defer session.Logoff()

	fs, err := session.Mount(c.share)
	if err != nil {
		return fmt.Errorf("smb: mount %s: %w", c.share, err)
	}
	defer fs.Umount()
	return nil
}

func (c *smbConnector) Walk(ctx context.Context, fn WalkFunc) error {
	session, err := c.dial()
	if err != nil {
		return err
	}
	defer session.Logoff()

	fs, err := session.Mount(c.share)
	if err != nil {
		return fmt.Errorf("smb: mount %s: %w", c.share, err)
	}
	defer fs.Umount()

	root := c.basePath
	if root == "" {
		root = "."
	}

	return walkSMB(ctx, fs, root, c.share, c.host, fn)
}

func walkSMB(ctx context.Context, fs *smb2.Share, dir, share, host string, fn WalkFunc) error {
	select {
	case <-ctx.Done():
		return ctx.Err()
	default:
	}

	entries, err := fs.ReadDir(dir)
	if err != nil {
		return nil // permission denied — skip, don't fail
	}

	for _, entry := range entries {
		path := dir + "/" + entry.Name()
		if path[:2] == "./" {
			path = path[2:]
		}

		if entry.IsDir() {
			if err := walkSMB(ctx, fs, path, share, host, fn); err != nil {
				return err
			}
			continue
		}

		info, err := entry.Info()
		if err != nil {
			continue
		}

		modTime := info.ModTime().UTC()
		fileInfo := FileInfo{
			Path:       "/" + path,
			Name:       entry.Name(),
			Extension:  strings.ToLower(ext(entry.Name())),
			Size:       info.Size(),
			ModifiedAt: modTime,
			IndexedAt:  time.Now().UTC(),
			Protocol:   "smb",
			Host:       host,
			Share:      share,
		}

		if err := fn(ctx, fileInfo); err != nil {
			return err
		}
	}
	return nil
}

func (c *smbConnector) Open(ctx context.Context, path string) (io.ReadCloser, error) {
	session, err := c.dial()
	if err != nil {
		return nil, err
	}

	share, err := session.Mount(c.share)
	if err != nil {
		session.Logoff()
		return nil, err
	}

	cleanPath := strings.TrimPrefix(path, "/")
	f, err := share.Open(cleanPath)
	if err != nil {
		share.Umount()
		session.Logoff()
		return nil, err
	}

	// Return a ReadCloser that cleans up the session on close
	return &smbReadCloser{file: f, share: share, session: session}, nil
}

type smbReadCloser struct {
	file    *smb2.File
	share   *smb2.Share
	session *smb2.Session
}

func (r *smbReadCloser) Read(p []byte) (int, error) { return r.file.Read(p) }
func (r *smbReadCloser) Close() error {
	r.file.Close()
	r.share.Umount()
	r.session.Logoff()
	return nil
}

func ext(name string) string {
	for i := len(name) - 1; i >= 0; i-- {
		if name[i] == '.' {
			return name[i:]
		}
		if name[i] == '/' || name[i] == '\\' {
			break
		}
	}
	return ""
}
