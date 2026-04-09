// Package sync handles the outbound sync protocol to the dgraph.ai cloud API.
// Only metadata leaves the network — never file content.
// Implements GraphDelta chunked sync with offline queue fallback.
package sync

import (
	"bytes"
	"compress/gzip"
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"time"

	"go.uber.org/zap"

	"github.com/gaineyllc/dgraphai/agent/internal/connector"
)

const (
	batchSize     = 500           // nodes per HTTP request
	maxRetries    = 3
	retryBackoff  = 5 * time.Second
)

// Client syncs file metadata to the cloud API.
type Client struct {
	endpoint  string
	apiKey    string
	tenantID  string
	agentID   string
	http      *http.Client
	log       *zap.Logger
	queue     Queue // offline queue — non-nil when air-gapped
}

// GraphDelta is a batch of file metadata changes.
type GraphDelta struct {
	AgentID     string                 `json:"agent_id"`
	TenantID    string                 `json:"tenant_id"`
	ConnectorID string                 `json:"connector_id"`
	ScanID      string                 `json:"scan_id"`
	ChunkIndex  int                    `json:"chunk_index"`
	TotalChunks int                    `json:"total_chunks,omitempty"`
	Files       []connector.FileInfo   `json:"files"`
	DeletedPaths []string              `json:"deleted_paths,omitempty"`
	Timestamp   time.Time              `json:"timestamp"`
}

// ScanResult is the outcome of a complete scan.
type ScanResult struct {
	ScanID       string
	ConnectorID  string
	FilesIndexed int
	FilesDeleted int
	Errors       int
	Duration     time.Duration
}

// Queue is the interface for offline queuing (SQLite-backed).
type Queue interface {
	Enqueue(delta GraphDelta) error
	Flush(ctx context.Context, send func(GraphDelta) error) error
	Pending() (int, error)
}

func New(endpoint, apiKey, tenantID, agentID string, log *zap.Logger, q Queue) *Client {
	return &Client{
		endpoint: endpoint,
		apiKey:   apiKey,
		tenantID: tenantID,
		agentID:  agentID,
		log:      log,
		queue:    q,
		http: &http.Client{
			Timeout: 30 * time.Second,
			Transport: &http.Transport{
				MaxIdleConnsPerHost: 4,
				IdleConnTimeout:     90 * time.Second,
			},
		},
	}
}

// Sync runs a complete scan of a connector and syncs to cloud.
func (c *Client) Sync(ctx context.Context, conn connector.Connector, connID string) (ScanResult, error) {
	scanID    := fmt.Sprintf("%s-%d", connID, time.Now().UnixNano())
	result    := ScanResult{ScanID: scanID, ConnectorID: connID}
	startTime := time.Now()

	// Register scan start
	if err := c.sendScanEvent(ctx, scanID, connID, "started"); err != nil {
		c.log.Warn("Failed to register scan start", zap.Error(err))
	}

	batch := make([]connector.FileInfo, 0, batchSize)
	chunkIdx := 0

	flush := func() error {
		if len(batch) == 0 {
			return nil
		}
		delta := GraphDelta{
			AgentID:     c.agentID,
			TenantID:    c.tenantID,
			ConnectorID: connID,
			ScanID:      scanID,
			ChunkIndex:  chunkIdx,
			Files:       batch,
			Timestamp:   time.Now().UTC(),
		}
		if err := c.sendDelta(ctx, delta); err != nil {
			result.Errors++
			return err
		}
		chunkIdx++
		result.FilesIndexed += len(batch)
		batch = batch[:0]
		return nil
	}

	err := conn.Walk(ctx, func(ctx context.Context, info connector.FileInfo) error {
		info.ConnectorID = connID
		batch = append(batch, info)
		if len(batch) >= batchSize {
			return flush()
		}
		return nil
	})

	// Flush remaining
	if ferr := flush(); ferr != nil && err == nil {
		err = ferr
	}

	result.Duration = time.Since(startTime)

	// Register scan completion
	status := "completed"
	if err != nil {
		status = "failed"
	}
	c.sendScanEvent(ctx, scanID, connID, status) //nolint:errcheck

	c.log.Info("Scan complete",
		zap.String("connector", connID),
		zap.Int("files", result.FilesIndexed),
		zap.Duration("duration", result.Duration),
		zap.String("status", status),
	)

	return result, err
}

// sendDelta sends a GraphDelta to the cloud, falling back to offline queue.
func (c *Client) sendDelta(ctx context.Context, delta GraphDelta) error {
	// Attempt live send with retries
	var lastErr error
	for attempt := 0; attempt < maxRetries; attempt++ {
		if attempt > 0 {
			select {
			case <-ctx.Done():
				return ctx.Err()
			case <-time.After(retryBackoff * time.Duration(attempt)):
			}
		}

		if err := c.postJSON(ctx, "/api/scanner/delta", delta); err != nil {
			lastErr = err
			c.log.Warn("Delta send failed, will retry",
				zap.Int("attempt", attempt+1),
				zap.Error(err),
			)
			continue
		}
		return nil
	}

	// All retries exhausted — enqueue for later if queue available
	if c.queue != nil {
		c.log.Warn("Queuing delta for offline delivery", zap.Error(lastErr))
		return c.queue.Enqueue(delta)
	}

	return fmt.Errorf("failed to send delta after %d attempts: %w", maxRetries, lastErr)
}

// FlushQueue sends any queued deltas now that we're back online.
func (c *Client) FlushQueue(ctx context.Context) error {
	if c.queue == nil {
		return nil
	}
	pending, _ := c.queue.Pending()
	if pending == 0 {
		return nil
	}
	c.log.Info("Flushing offline queue", zap.Int("pending", pending))
	return c.queue.Flush(ctx, func(d GraphDelta) error {
		return c.postJSON(ctx, "/api/scanner/delta", d)
	})
}

func (c *Client) sendScanEvent(ctx context.Context, scanID, connID, status string) error {
	return c.postJSON(ctx, "/api/scanner/scan-event", map[string]string{
		"scan_id":      scanID,
		"connector_id": connID,
		"agent_id":     c.agentID,
		"tenant_id":    c.tenantID,
		"status":       status,
		"timestamp":    time.Now().UTC().Format(time.RFC3339),
	})
}

func (c *Client) postJSON(ctx context.Context, path string, body any) error {
	data, err := json.Marshal(body)
	if err != nil {
		return fmt.Errorf("marshal: %w", err)
	}

	// Gzip compress payloads >1KB
	var buf bytes.Buffer
	var contentEncoding string
	if len(data) > 1024 {
		gz := gzip.NewWriter(&buf)
		gz.Write(data)
		gz.Close()
		contentEncoding = "gzip"
	} else {
		buf.Write(data)
	}

	req, err := http.NewRequestWithContext(ctx, "POST", c.endpoint+path, &buf)
	if err != nil {
		return err
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Authorization", "Bearer "+c.apiKey)
	req.Header.Set("X-Agent-ID", c.agentID)
	req.Header.Set("X-Tenant-ID", c.tenantID)
	if contentEncoding != "" {
		req.Header.Set("Content-Encoding", contentEncoding)
	}

	resp, err := c.http.Do(req)
	if err != nil {
		return fmt.Errorf("POST %s: %w", path, err)
	}
	defer resp.Body.Close()

	if resp.StatusCode >= 400 {
		return fmt.Errorf("POST %s: HTTP %d", path, resp.StatusCode)
	}
	return nil
}

// Heartbeat sends an agent health report to the cloud.
func (c *Client) Heartbeat(ctx context.Context, health map[string]any) error {
	health["agent_id"]  = c.agentID
	health["tenant_id"] = c.tenantID
	health["timestamp"] = time.Now().UTC().Format(time.RFC3339)
	return c.postJSON(ctx, "/api/scanner/heartbeat", health)
}
