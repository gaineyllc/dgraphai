// Package config loads dgraph-proxy configuration from env + file.
package config

import (
	"fmt"
	"os"
	"strconv"
	"time"
)

// Config holds all runtime configuration for dgraph-proxy.
type Config struct {
	// Identity
	TenantID  string
	AgentID   string
	ProxyID   string

	// Local store
	DataDir   string // path to BadgerDB data directory
	StoreMode StoreMode

	// Cloud sync
	CloudURL      string        // https://api.dgraph.ai  or ""  (empty = air-gapped)
	CloudToken    string        // bearer token for cloud API
	SyncInterval  time.Duration // how often to push deltas upstream
	SyncBatchSize int           // max nodes per sync batch

	// Local API
	ListenAddr  string // e.g. "127.0.0.1:7433"
	TLSCertFile string
	TLSKeyFile  string
	JWTSecret   string // for local API auth (can be shared secret with agent-go)

	// Query
	MaxQueryResults int
	QueryTimeoutSec int

	// Observability
	MetricsAddr string // e.g. ":9090"
	LogLevel    string // debug | info | warn | error
	LogFormat   string // json | text

	// Air-gap mode
	AirGapped bool // when true, sync is disabled entirely
}

// StoreMode controls where graph data is persisted locally.
type StoreMode string

const (
	StoreBadger StoreMode = "badger" // BadgerDB — default, pure Go, embeddable
	StoreBolt   StoreMode = "bolt"   // BoltDB — simpler, single-writer
)

// Load reads config from environment variables with sensible defaults.
func Load() (*Config, error) {
	cfg := &Config{
		TenantID:        requireEnv("DGPROXY_TENANT_ID"),
		AgentID:         envOr("DGPROXY_AGENT_ID", "default"),
		ProxyID:         envOr("DGPROXY_PROXY_ID", hostname()),
		DataDir:         envOr("DGPROXY_DATA_DIR", "./data"),
		StoreMode:       StoreMode(envOr("DGPROXY_STORE_MODE", "badger")),
		CloudURL:        envOr("DGPROXY_CLOUD_URL", ""),
		CloudToken:      envOr("DGPROXY_CLOUD_TOKEN", ""),
		SyncInterval:    mustDuration(envOr("DGPROXY_SYNC_INTERVAL", "5m")),
		SyncBatchSize:   mustInt(envOr("DGPROXY_SYNC_BATCH_SIZE", "500")),
		ListenAddr:      envOr("DGPROXY_LISTEN_ADDR", "127.0.0.1:7433"),
		TLSCertFile:     envOr("DGPROXY_TLS_CERT", ""),
		TLSKeyFile:      envOr("DGPROXY_TLS_KEY", ""),
		JWTSecret:       envOr("DGPROXY_JWT_SECRET", ""),
		MaxQueryResults: mustInt(envOr("DGPROXY_MAX_QUERY_RESULTS", "10000")),
		QueryTimeoutSec: mustInt(envOr("DGPROXY_QUERY_TIMEOUT_SEC", "30")),
		MetricsAddr:     envOr("DGPROXY_METRICS_ADDR", ":9091"),
		LogLevel:        envOr("DGPROXY_LOG_LEVEL", "info"),
		LogFormat:       envOr("DGPROXY_LOG_FORMAT", "json"),
		AirGapped:       envBool("DGPROXY_AIR_GAPPED"),
	}

	if cfg.TenantID == "" {
		return nil, fmt.Errorf("DGPROXY_TENANT_ID is required")
	}
	if cfg.StoreMode != StoreBadger && cfg.StoreMode != StoreBolt {
		return nil, fmt.Errorf("unknown DGPROXY_STORE_MODE %q (badger|bolt)", cfg.StoreMode)
	}
	if !cfg.AirGapped && cfg.CloudURL == "" {
		// Not air-gapped but no cloud URL — warn, allow for local-only mode
		cfg.AirGapped = true
	}

	return cfg, nil
}

func requireEnv(key string) string {
	v := os.Getenv(key)
	return v
}

func envOr(key, def string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return def
}

func envBool(key string) bool {
	v := os.Getenv(key)
	return v == "1" || v == "true" || v == "yes"
}

func mustInt(s string) int {
	n, err := strconv.Atoi(s)
	if err != nil {
		return 0
	}
	return n
}

func mustDuration(s string) time.Duration {
	d, err := time.ParseDuration(s)
	if err != nil {
		return 5 * time.Minute
	}
	return d
}

func hostname() string {
	h, _ := os.Hostname()
	return h
}
