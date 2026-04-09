// dgraph-proxy — local air-gappable graph store and sync agent.
//
// What it does:
//   - Runs on-premises alongside dgraph scout (filesystem indexer)
//   - Stores graph data locally in BadgerDB (no outbound connections required)
//   - Exposes a local HTTP API compatible with dgraph.ai cloud API subset
//   - Syncs delta changes to dgraph.ai cloud when a network connection exists
//   - In air-gapped mode: stores everything locally, never phones home
//   - Survives network outages: buffers all changes, syncs when reconnected
//
// Usage:
//
//	DGPROXY_TENANT_ID=acme DGPROXY_DATA_DIR=/var/lib/dgraph-proxy \
//	  dgraph-proxy
//
// Air-gapped mode:
//
//	DGPROXY_AIR_GAPPED=true DGPROXY_TENANT_ID=acme \
//	  dgraph-proxy
package main

import (
	"context"
	"errors"
	"fmt"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"go.uber.org/zap"
	"go.uber.org/zap/zapcore"

	"github.com/gaineyllc/dgraphai/dgraph-proxy/internal/api"
	"github.com/gaineyllc/dgraphai/dgraph-proxy/internal/config"
	"github.com/gaineyllc/dgraphai/dgraph-proxy/internal/query"
	"github.com/gaineyllc/dgraphai/dgraph-proxy/internal/store"
	proxysync "github.com/gaineyllc/dgraphai/dgraph-proxy/internal/sync"
)

const version = "0.1.0"

func main() {
	if err := run(); err != nil {
		fmt.Fprintf(os.Stderr, "dgraph-proxy: fatal: %v\n", err)
		os.Exit(1)
	}
}

func run() error {
	// ── Load config ──────────────────────────────────────────────────────────
	cfg, err := config.Load()
	if err != nil {
		return fmt.Errorf("load config: %w", err)
	}

	// ── Build logger ─────────────────────────────────────────────────────────
	log, err := buildLogger(cfg.LogLevel, cfg.LogFormat)
	if err != nil {
		return fmt.Errorf("build logger: %w", err)
	}
	defer log.Sync()

	log.Info("dgraph-proxy starting",
		zap.String("version", version),
		zap.String("tenant_id", cfg.TenantID),
		zap.String("proxy_id", cfg.ProxyID),
		zap.String("data_dir", cfg.DataDir),
		zap.Bool("air_gapped", cfg.AirGapped),
	)

	// ── Open local store ─────────────────────────────────────────────────────
	s, err := store.Open(cfg.DataDir, cfg.TenantID, log)
	if err != nil {
		return fmt.Errorf("open store: %w", err)
	}
	defer s.Close()

	// ── Build query engine ───────────────────────────────────────────────────
	eng := query.New(s)

	// ── Build syncer ─────────────────────────────────────────────────────────
	syncer := proxysync.New(cfg, s, log)

	// ── Build API server ─────────────────────────────────────────────────────
	srv := api.New(cfg, s, eng, syncer, log)

	// ── Shutdown handling ─────────────────────────────────────────────────────
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	sigCh := make(chan os.Signal, 1)
	signal.Notify(sigCh, syscall.SIGINT, syscall.SIGTERM)

	// ── Start sync loop ───────────────────────────────────────────────────────
	syncDone := make(chan struct{})
	go func() {
		defer close(syncDone)
		syncer.Run(ctx)
	}()

	// ── Start API server ──────────────────────────────────────────────────────
	serverErr := make(chan error, 1)
	go func() {
		if err := srv.Start(); err != nil && !errors.Is(err, http.ErrServerClosed) {
			serverErr <- err
		}
	}()

	log.Info("dgraph-proxy ready",
		zap.String("listen", cfg.ListenAddr),
		zap.String("metrics", cfg.MetricsAddr),
	)

	// ── Wait for signal or error ──────────────────────────────────────────────
	select {
	case sig := <-sigCh:
		log.Info("received signal, shutting down", zap.String("signal", sig.String()))
	case err := <-serverErr:
		log.Error("API server error", zap.Error(err))
		cancel()
	}

	// ── Graceful shutdown ─────────────────────────────────────────────────────
	log.Info("shutting down...")
	cancel()

	shutdownCtx, shutdownCancel := context.WithTimeout(context.Background(), 15*time.Second)
	defer shutdownCancel()

	if err := srv.Shutdown(shutdownCtx); err != nil {
		log.Error("API server shutdown error", zap.Error(err))
	}

	// Wait for sync loop
	select {
	case <-syncDone:
	case <-time.After(10 * time.Second):
		log.Warn("sync loop did not stop in time")
	}

	log.Info("dgraph-proxy stopped")
	return nil
}

func buildLogger(level, format string) (*zap.Logger, error) {
	lvl, err := zapcore.ParseLevel(level)
	if err != nil {
		lvl = zapcore.InfoLevel
	}

	var cfg zap.Config
	if format == "text" {
		cfg = zap.NewDevelopmentConfig()
	} else {
		cfg = zap.NewProductionConfig()
	}
	cfg.Level = zap.NewAtomicLevelAt(lvl)
	return cfg.Build()
}
