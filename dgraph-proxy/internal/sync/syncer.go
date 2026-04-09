// Package sync manages the background sync loop between dgraph-proxy and the cloud.
//
// Sync loop behaviour:
//   - Runs every cfg.SyncInterval (default 5 minutes).
//   - If AirGapped=true, the loop runs but only sends heartbeats locally (no network).
//   - On each tick: drain pending deltas → batch → POST → ack confirmed seqs.
//   - Exponential backoff on HTTP failures (max 30m).
//   - On reconnect after disconnect: immediate flush of accumulated deltas.
package sync

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"math"
	"net/http"
	"sync/atomic"
	"time"

	"go.uber.org/zap"

	"github.com/gaineyllc/dgraphai/dgraph-proxy/internal/config"
	"github.com/gaineyllc/dgraphai/dgraph-proxy/internal/delta"
	"github.com/gaineyllc/dgraphai/dgraph-proxy/internal/store"
)

// Syncer runs the background sync loop.
type Syncer struct {
	cfg       *config.Config
	store     *store.Store
	log       *zap.Logger
	client    *http.Client
	startedAt time.Time
	batchSeq  atomic.Uint64

	// metrics
	lastSyncAt    atomic.Pointer[time.Time]
	syncSuccesses atomic.Int64
	syncFailures  atomic.Int64
	totalAcked    atomic.Int64
}

// New creates a Syncer. Call Run to start the background loop.
func New(cfg *config.Config, s *store.Store, log *zap.Logger) *Syncer {
	return &Syncer{
		cfg:       cfg,
		store:     s,
		log:       log,
		client:    &http.Client{Timeout: 30 * time.Second},
		startedAt: time.Now(),
	}
}

// Run starts the sync loop and blocks until ctx is cancelled.
func (sy *Syncer) Run(ctx context.Context) {
	if sy.cfg.AirGapped {
		sy.log.Info("air-gapped mode: sync disabled, running in local-only mode")
		<-ctx.Done()
		return
	}

	sy.log.Info("sync loop starting",
		zap.String("cloud_url", sy.cfg.CloudURL),
		zap.Duration("interval", sy.cfg.SyncInterval),
		zap.Int("batch_size", sy.cfg.SyncBatchSize),
	)

	// Initial sync immediately on startup
	sy.sync(ctx)

	ticker := time.NewTicker(sy.cfg.SyncInterval)
	defer ticker.Stop()

	backoff := sy.cfg.SyncInterval
	const maxBackoff = 30 * time.Minute

	for {
		select {
		case <-ctx.Done():
			sy.log.Info("sync loop shutting down")
			return
		case <-ticker.C:
			if err := sy.sync(ctx); err != nil {
				sy.syncFailures.Add(1)
				// Exponential backoff
				backoff = time.Duration(math.Min(float64(backoff*2), float64(maxBackoff)))
				sy.log.Warn("sync failed, backing off",
					zap.Error(err),
					zap.Duration("next_retry", backoff),
				)
				ticker.Reset(backoff)
			} else {
				sy.syncSuccesses.Add(1)
				backoff = sy.cfg.SyncInterval // reset on success
				ticker.Reset(backoff)
			}
		}
	}
}

// ForceSync triggers an immediate sync outside the normal interval.
func (sy *Syncer) ForceSync(ctx context.Context) error {
	return sy.sync(ctx)
}

// Stats returns current sync metrics.
type Stats struct {
	LastSyncAt    *time.Time
	SyncSuccesses int64
	SyncFailures  int64
	TotalAcked    int64
	UptimeSeconds int64
}

func (sy *Syncer) Stats() Stats {
	return Stats{
		LastSyncAt:    sy.lastSyncAt.Load(),
		SyncSuccesses: sy.syncSuccesses.Load(),
		SyncFailures:  sy.syncFailures.Load(),
		TotalAcked:    sy.totalAcked.Load(),
		UptimeSeconds: int64(time.Since(sy.startedAt).Seconds()),
	}
}

// ── Internal ─────────────────────────────────────────────────────────────────

func (sy *Syncer) sync(ctx context.Context) error {
	// Drain pending deltas
	pending, err := sy.store.DrainDeltas(sy.cfg.SyncBatchSize)
	if err != nil {
		return fmt.Errorf("drain deltas: %w", err)
	}

	nodeCount, _ := sy.store.NodeCount()
	pendingCount, _ := sy.store.PendingDeltaCount()

	stats := delta.ProxyStats{
		NodeCount:     nodeCount,
		PendingDeltas: pendingCount,
		UptimeSeconds: int64(time.Since(sy.startedAt).Seconds()),
	}

	// Always send at least a heartbeat even if no deltas
	if len(pending) == 0 {
		return sy.heartbeat(ctx, stats)
	}

	// Build batch
	items := make([]delta.DeltaItem, 0, len(pending))
	seqs := make([]uint64, 0, len(pending))
	for _, d := range pending {
		items = append(items, delta.DeltaItem{
			Seq:       d.Seq,
			Op:        string(d.Op),
			NodeID:    d.NodeID,
			EdgeID:    d.EdgeID,
			Payload:   d.Payload,
			Timestamp: d.CreatedAt,
		})
		seqs = append(seqs, d.Seq)
	}

	batch := delta.DeltaBatch{
		ProxyID:  sy.cfg.ProxyID,
		TenantID: sy.cfg.TenantID,
		AgentID:  sy.cfg.AgentID,
		Deltas:   items,
		BatchSeq: sy.batchSeq.Add(1),
		SentAt:   time.Now().UTC(),
		Stats:    stats,
	}

	resp, err := sy.postBatch(ctx, batch)
	if err != nil {
		return fmt.Errorf("post batch: %w", err)
	}

	// Ack confirmed seqs
	if len(resp.AckedSeqs) > 0 {
		if err := sy.store.AckDeltas(resp.AckedSeqs); err != nil {
			sy.log.Error("failed to ack deltas locally", zap.Error(err))
		}
		sy.totalAcked.Add(int64(len(resp.AckedSeqs)))
	}

	// Process server commands
	for _, cmd := range resp.Commands {
		sy.handleCommand(cmd)
	}

	now := time.Now()
	sy.lastSyncAt.Store(&now)

	sy.log.Info("sync complete",
		zap.Int("deltas_sent", len(items)),
		zap.Int("acked", len(resp.AckedSeqs)),
		zap.Int("commands", len(resp.Commands)),
	)
	return nil
}

func (sy *Syncer) heartbeat(ctx context.Context, stats delta.ProxyStats) error {
	hb := delta.HeartbeatRequest{
		ProxyID:   sy.cfg.ProxyID,
		TenantID:  sy.cfg.TenantID,
		AgentID:   sy.cfg.AgentID,
		Stats:     stats,
		Version:   "0.1.0",
		Timestamp: time.Now().UTC(),
	}

	body, err := json.Marshal(hb)
	if err != nil {
		return err
	}

	url := sy.cfg.CloudURL + "/api/v1/proxy/heartbeat"
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, url, bytes.NewReader(body))
	if err != nil {
		return err
	}
	sy.setHeaders(req)

	resp, err := sy.client.Do(req)
	if err != nil {
		return fmt.Errorf("heartbeat request: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode >= 400 {
		return fmt.Errorf("heartbeat returned %d", resp.StatusCode)
	}

	var hbResp delta.HeartbeatResponse
	if err := json.NewDecoder(resp.Body).Decode(&hbResp); err == nil {
		for _, cmd := range hbResp.Commands {
			sy.handleCommand(cmd)
		}
	}

	now := time.Now()
	sy.lastSyncAt.Store(&now)
	return nil
}

func (sy *Syncer) postBatch(ctx context.Context, batch delta.DeltaBatch) (*delta.SyncResponse, error) {
	body, err := json.Marshal(batch)
	if err != nil {
		return nil, err
	}

	url := sy.cfg.CloudURL + "/api/v1/proxy/sync"
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, url, bytes.NewReader(body))
	if err != nil {
		return nil, err
	}
	sy.setHeaders(req)

	resp, err := sy.client.Do(req)
	if err != nil {
		return nil, fmt.Errorf("http post: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode >= 400 {
		return nil, fmt.Errorf("cloud returned %d", resp.StatusCode)
	}

	var syncResp delta.SyncResponse
	if err := json.NewDecoder(resp.Body).Decode(&syncResp); err != nil {
		return nil, fmt.Errorf("decode response: %w", err)
	}
	return &syncResp, nil
}

func (sy *Syncer) setHeaders(req *http.Request) {
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Authorization", "Bearer "+sy.cfg.CloudToken)
	req.Header.Set("X-Proxy-ID", sy.cfg.ProxyID)
	req.Header.Set("X-Tenant-ID", sy.cfg.TenantID)
}

func (sy *Syncer) handleCommand(cmd delta.Command) {
	sy.log.Info("received command from cloud",
		zap.String("id", cmd.ID),
		zap.String("type", string(cmd.Type)),
	)
	// Commands are logged and can be acted on by command handlers
	// registered at startup. For now, log and continue.
	switch cmd.Type {
	case delta.CmdFlushDeltas:
		sy.log.Info("flush_deltas command received (will sync on next tick)")
	case delta.CmdReindex:
		sy.log.Info("reindex command received (trigger via agent-go)")
	case delta.CmdPurge:
		sy.log.Warn("purge command received — requires manual confirmation")
	case delta.CmdUpdateConfig:
		sy.log.Info("update_config command received")
	}
}
