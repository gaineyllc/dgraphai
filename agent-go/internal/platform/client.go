// Package platform handles communication with the dgraph.ai cloud API.
// This is the control plane connection — fetching connector config,
// reporting heartbeats, receiving commands.
//
// Separate from the sync client (data plane) which handles file metadata upload.
package platform

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"runtime"
	"time"

	"go.uber.org/zap"
)

// Client talks to the dgraph.ai platform control plane.
type Client struct {
	endpoint string
	apiKey   string
	http     *http.Client
	log      *zap.Logger

	// Cached config from last successful poll
	lastConfig *AgentConfig
}

// New creates a platform client.
func New(endpoint, apiKey string, log *zap.Logger) *Client {
	return &Client{
		endpoint: endpoint,
		apiKey:   apiKey,
		http: &http.Client{
			Timeout: 15 * time.Second,
		},
		log: log,
	}
}

// ── Config types (mirror of Python AgentConfig) ───────────────────────────────

// ConnectorConfig is one connector assignment from the platform.
type ConnectorConfig struct {
	ID                  string            `json:"id"`
	Name                string            `json:"name"`
	ConnectorType       string            `json:"connector_type"`
	Config              map[string]string `json:"config"`
	ScanIntervalMinutes int               `json:"scan_interval_minutes"`
	Enabled             bool              `json:"enabled"`
}

// AgentConfig is returned by GET /api/agent/config.
type AgentConfig struct {
	AgentID            string            `json:"agent_id"`
	TenantID           string            `json:"tenant_id"`
	CloudURL           string            `json:"cloud_url"`
	Connectors         []ConnectorConfig `json:"connectors"`
	EnrichmentEnabled  bool              `json:"enrichment_enabled"`
	LogLevel           string            `json:"log_level"`
	MaxConcurrentScans int               `json:"max_concurrent_scans"`
	VersionCheckURL    string            `json:"version_check_url"`
	FetchedAt          time.Time
}

// ── Heartbeat types ───────────────────────────────────────────────────────────

// HeartbeatRequest matches the Python HeartbeatRequest model.
type HeartbeatRequest struct {
	AgentID          string            `json:"agent_id"`
	Version          string            `json:"version"`
	OS               string            `json:"os"`
	Hostname         string            `json:"hostname"`
	FilesIndexed     int               `json:"files_indexed"`
	FilesPending     int               `json:"files_pending"`
	LastError        string            `json:"last_error,omitempty"`
	ConnectorStatuses map[string]string `json:"connector_statuses"`
}

// HeartbeatResponse is returned by POST /api/agent/heartbeat.
type HeartbeatResponse struct {
	OK       bool              `json:"ok"`
	Commands []map[string]any  `json:"commands"`
}

// Command types the platform can send.
const (
	CmdReindex  = "reindex"
	CmdPause    = "pause"
	CmdResume   = "resume"
	CmdUpgrade  = "upgrade"
)

// ── API methods ───────────────────────────────────────────────────────────────

// FetchConfig retrieves the agent's connector config from the platform.
// Returns cached config if the platform is unreachable and cache is fresh.
func (c *Client) FetchConfig(ctx context.Context) (*AgentConfig, error) {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet,
		c.endpoint+"/api/agent/config", nil)
	if err != nil {
		return nil, err
	}
	c.setHeaders(req)

	resp, err := c.http.Do(req)
	if err != nil {
		if c.lastConfig != nil {
			c.log.Warn("platform unreachable, using cached config",
				zap.Error(err),
				zap.Time("cached_at", c.lastConfig.FetchedAt),
			)
			return c.lastConfig, nil
		}
		return nil, fmt.Errorf("fetch config: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode == http.StatusUnauthorized {
		return nil, fmt.Errorf("invalid API key — check DGRAPH_AGENT_API_KEY")
	}
	if resp.StatusCode >= 400 {
		body, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("config endpoint returned %d: %s", resp.StatusCode, string(body))
	}

	var cfg AgentConfig
	if err := json.NewDecoder(resp.Body).Decode(&cfg); err != nil {
		return nil, fmt.Errorf("decode config: %w", err)
	}
	cfg.FetchedAt = time.Now()
	c.lastConfig = &cfg

	c.log.Info("fetched config from platform",
		zap.Int("connectors", len(cfg.Connectors)),
		zap.String("tenant_id", cfg.TenantID),
	)
	return &cfg, nil
}

// Heartbeat sends a liveness ping with current stats.
// Returns any commands the platform wants the agent to execute.
func (c *Client) Heartbeat(ctx context.Context, hb HeartbeatRequest) (*HeartbeatResponse, error) {
	// Fill OS/hostname if not set
	if hb.OS == "" {
		hb.OS = runtime.GOOS
	}

	body, err := json.Marshal(hb)
	if err != nil {
		return nil, err
	}

	req, err := http.NewRequestWithContext(ctx, http.MethodPost,
		c.endpoint+"/api/agent/heartbeat", bytes.NewReader(body))
	if err != nil {
		return nil, err
	}
	c.setHeaders(req)
	req.Header.Set("Content-Type", "application/json")

	resp, err := c.http.Do(req)
	if err != nil {
		// Heartbeat failure is non-fatal
		return nil, fmt.Errorf("heartbeat: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode >= 400 {
		body, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("heartbeat returned %d: %s", resp.StatusCode, string(body))
	}

	var hbResp HeartbeatResponse
	if err := json.NewDecoder(resp.Body).Decode(&hbResp); err != nil {
		return nil, fmt.Errorf("decode heartbeat response: %w", err)
	}
	return &hbResp, nil
}

// VersionCheck checks if a newer agent version is available.
func (c *Client) VersionCheck(ctx context.Context, currentVersion string) (string, bool, error) {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet,
		"https://api.github.com/repos/gaineyllc/dgraphai/releases/latest", nil)
	if err != nil {
		return "", false, err
	}
	req.Header.Set("User-Agent", "dgraph-agent/"+currentVersion)

	resp, err := c.http.Do(req)
	if err != nil {
		return "", false, nil // non-fatal
	}
	defer resp.Body.Close()

	var release struct {
		TagName string `json:"tag_name"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&release); err != nil {
		return "", false, nil
	}

	latest := release.TagName
	isNewer := latest != "" && latest != currentVersion && latest != "dev"
	return latest, isNewer, nil
}

func (c *Client) setHeaders(req *http.Request) {
	req.Header.Set("X-Scanner-Key", c.apiKey)
	req.Header.Set("User-Agent", "dgraph-agent/"+version)
}

// version is set at build time
var version = "dev"

func SetVersion(v string) { version = v }
