// Package delta defines the wire protocol between dgraph-proxy and dgraph.ai cloud.
//
// The sync protocol is intentionally simple:
//
//  1. Proxy POSTs a DeltaBatch to /api/v1/proxy/sync
//  2. Cloud responds with SyncResponse (ack'd seq numbers + any commands)
//  3. Proxy removes ack'd deltas from local queue
//  4. Proxy applies any cloud commands (e.g. re-index request, config update)
//
// This design means:
//   - The proxy is the initiator — no inbound connections from cloud.
//   - Works through firewalls with outbound-only HTTPS.
//   - Air-gapped mode simply skips step 1–4 entirely.
package delta

import "time"

// DeltaBatch is posted to the cloud sync endpoint.
type DeltaBatch struct {
	ProxyID   string        `json:"proxy_id"`
	TenantID  string        `json:"tenant_id"`
	AgentID   string        `json:"agent_id"`
	Deltas    []DeltaItem   `json:"deltas"`
	BatchSeq  uint64        `json:"batch_seq"` // monotonic batch counter
	SentAt    time.Time     `json:"sent_at"`
	Stats     ProxyStats    `json:"stats"`
}

// DeltaItem is a single change in the batch.
type DeltaItem struct {
	Seq       uint64      `json:"seq"`
	Op        string      `json:"op"` // upsert_node | delete_node | upsert_edge | delete_edge
	NodeID    string      `json:"node_id,omitempty"`
	EdgeID    string      `json:"edge_id,omitempty"`
	Payload   interface{} `json:"payload"`
	Timestamp time.Time   `json:"timestamp"`
}

// ProxyStats is attached to each batch for cloud-side observability.
type ProxyStats struct {
	NodeCount         int64 `json:"node_count"`
	EdgeCount         int64 `json:"edge_count"`
	PendingDeltas     int64 `json:"pending_deltas"`
	StoreBytes        int64 `json:"store_bytes"`
	LastIndexedAt     *time.Time `json:"last_indexed_at,omitempty"`
	UptimeSeconds     int64 `json:"uptime_seconds"`
}

// SyncResponse is returned by the cloud after processing a batch.
type SyncResponse struct {
	AckedSeqs    []uint64   `json:"acked_seqs"`
	ServerTimeMs int64      `json:"server_time_ms"`
	Commands     []Command  `json:"commands,omitempty"` // optional server-push commands
}

// Command is a server-initiated instruction to the proxy.
type Command struct {
	ID   string      `json:"id"`
	Type CommandType `json:"type"`
	Args interface{} `json:"args,omitempty"`
}

// CommandType enumerates cloud → proxy command types.
type CommandType string

const (
	// CmdReindex tells the proxy to trigger a full re-index of a connector.
	CmdReindex CommandType = "reindex"
	// CmdPurge tells the proxy to delete all local data for a tenant and re-sync.
	CmdPurge CommandType = "purge"
	// CmdUpdateConfig pushes a new config fragment to the proxy.
	CmdUpdateConfig CommandType = "update_config"
	// CmdFlushDeltas asks the proxy to immediately upload any pending deltas.
	CmdFlushDeltas CommandType = "flush_deltas"
)

// ReindexArgs are the args for CmdReindex.
type ReindexArgs struct {
	ConnectorID string `json:"connector_id"`
	FullScan    bool   `json:"full_scan"`
}

// HeartbeatRequest is sent on every sync cycle, even when there are no deltas.
type HeartbeatRequest struct {
	ProxyID   string     `json:"proxy_id"`
	TenantID  string     `json:"tenant_id"`
	AgentID   string     `json:"agent_id"`
	Stats     ProxyStats `json:"stats"`
	Version   string     `json:"version"`
	Timestamp time.Time  `json:"timestamp"`
}

// HeartbeatResponse is the cloud's reply to a heartbeat.
type HeartbeatResponse struct {
	Commands     []Command `json:"commands,omitempty"`
	ConfigUpdate *ProxyConfigUpdate `json:"config_update,omitempty"`
}

// ProxyConfigUpdate carries live config changes the proxy should apply.
type ProxyConfigUpdate struct {
	SyncIntervalSeconds int    `json:"sync_interval_seconds,omitempty"`
	MaxBatchSize        int    `json:"max_batch_size,omitempty"`
	LogLevel            string `json:"log_level,omitempty"`
}
