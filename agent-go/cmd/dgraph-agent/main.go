// dgraph-agent — on-premises scanner agent for dgraph.ai
//
// Single Go binary. Zero inbound ports. Outbound HTTPS only.
// Shipped as a signed binary for Windows/Linux/macOS.
// Deployed via Helm, Docker, or direct install.
//
// Usage:
//   dgraph-agent --config /etc/dgraph-agent/config.yaml
//   dgraph-agent --help
//
// All sensitive config via env vars (DGRAPH_AGENT_*) or config file.
// NEVER log API keys, passwords, or file content.
package main

import (
	"context"
	"fmt"
	"net/http"
	"os"
	"os/signal"
	"runtime"
	"syscall"
	"time"

	"github.com/spf13/cobra"
	"go.uber.org/zap"
	"go.uber.org/zap/zapcore"

	"github.com/gaineyllc/dgraphai/agent/internal/config"
	"github.com/gaineyllc/dgraphai/agent/internal/connector"
	"github.com/gaineyllc/dgraphai/agent/internal/enricher"
	agentsync "github.com/gaineyllc/dgraphai/agent/internal/sync"
)

// Build-time variables injected by goreleaser
var (
	version = "dev"
	commit  = "none"
	date    = "unknown"
)

func main() {
	root := &cobra.Command{
		Use:   "dgraph-agent",
		Short: "dgraph.ai on-premises scanner agent",
		Long: `dgraph-agent indexes your local filesystems and syncs
metadata to the dgraph.ai knowledge graph.

Only metadata leaves your network — file content never leaves.
Credentials are read from environment variables or config file.`,
		RunE: run,
	}

	root.PersistentFlags().String("config", "", "config file path (default: /etc/dgraph-agent/config.yaml)")
	root.PersistentFlags().Bool("version", false, "print version and exit")

	// Sub-commands
	root.AddCommand(
		versionCmd(),
		testCmd(),
		statusCmd(),
	)

	if err := root.Execute(); err != nil {
		fmt.Fprintf(os.Stderr, "Error: %v\n", err)
		os.Exit(1)
	}
}

func run(cmd *cobra.Command, args []string) error {
	cfgFile, _ := cmd.Flags().GetString("config")
	cfg, err := config.Init(cfgFile)
	if err != nil {
		return fmt.Errorf("config: %w", err)
	}

	log := buildLogger(cfg.LogLevel)
	defer log.Sync() //nolint:errcheck

	log.Info("dgraph-agent starting",
		zap.String("version", version),
		zap.String("commit",  commit),
		zap.String("os",      runtime.GOOS),
		zap.String("arch",    runtime.GOARCH),
	)
	log.Info("Configuration loaded", zap.Any("config", cfg.Redacted()))

	ctx, cancel := signal.NotifyContext(context.Background(),
		syscall.SIGINT, syscall.SIGTERM)
	defer cancel()

	// Start health server (loopback only)
	go startHealthServer(cfg.HealthBind, log)

	// Build components — use Rust subprocess enricher if available,
	// fall back to pure Go enricher
	subEnrich := enricher.NewSubprocessEnricher("", cfg.EnableSecretScan, cfg.EnablePIIScan)
	client := agentsync.New(cfg.APIEndpoint, cfg.APIKey, cfg.TenantID, cfg.AgentID, log, nil)

	// Announce agent registration
	if err := client.Heartbeat(ctx, buildHealthReport(cfg, subEnrich)); err != nil {
		log.Warn("Initial heartbeat failed", zap.Error(err))
	}

	// Main scan loop
	ticker := time.NewTicker(cfg.SyncInterval)
	defer ticker.Stop()

	runAllScans(ctx, cfg, client, subEnrich, log)

	for {
		select {
		case <-ctx.Done():
			log.Info("Shutting down gracefully")
			return nil
		case <-ticker.C:
			runAllScans(ctx, cfg, client, subEnrich, log)
		}
	}
}

func runAllScans(ctx context.Context, cfg *config.Config, client *agentsync.Client, enrich *enricher.SubprocessEnricher, log *zap.Logger) {
	for _, connCfg := range cfg.Connectors {
		if !connCfg.Enabled {
			continue
		}

		conn, err := connector.New(connCfg.Type, connCfg.Settings)
		if err != nil {
			log.Error("Failed to create connector",
				zap.String("connector", connCfg.ID),
				zap.String("type", connCfg.Type),
				zap.Error(err),
			)
			continue
		}

		log.Info("Starting scan", zap.String("connector", connCfg.ID))

		result, err := client.Sync(ctx, conn, connCfg.ID)
		if err != nil {
			log.Error("Scan failed",
				zap.String("connector", connCfg.ID),
				zap.Error(err),
			)
		} else {
			log.Info("Scan complete",
				zap.String("connector", connCfg.ID),
				zap.Int("files", result.FilesIndexed),
				zap.Duration("duration", result.Duration),
			)
		}
	}
}

func startHealthServer(bind string, log *zap.Logger) {
	mux := http.NewServeMux()
	mux.HandleFunc("/health", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		fmt.Fprintf(w, `{"status":"ok","version":"%s"}`, version)
	})
	mux.HandleFunc("/ready", func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	})

	srv := &http.Server{Addr: bind, Handler: mux, ReadTimeout: 5 * time.Second}
	log.Info("Health server listening", zap.String("bind", bind))
	if err := srv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
		log.Warn("Health server error", zap.Error(err))
	}
}

func buildHealthReport(cfg *config.Config, enrich *enricher.SubprocessEnricher) map[string]any {
	_, enricherAvail := os.Stat(enrich.BinaryPath())
	return map[string]any{
		"version":           version,
		"os":                runtime.GOOS,
		"arch":              runtime.GOARCH,
		"connectors":        len(cfg.Connectors),
		"air_gapped":        cfg.AirGapped,
		"enricher_available": enricherAvail == nil,
	}
}

func buildLogger(level string) *zap.Logger {
	lvl := zapcore.InfoLevel
	lvl.UnmarshalText([]byte(level)) //nolint:errcheck

	cfg := zap.NewProductionConfig()
	cfg.Level = zap.NewAtomicLevelAt(lvl)
	cfg.EncoderConfig.TimeKey = "ts"
	cfg.EncoderConfig.EncodeTime = zapcore.ISO8601TimeEncoder
	log, _ := cfg.Build()
	return log
}

func versionCmd() *cobra.Command {
	return &cobra.Command{
		Use:   "version",
		Short: "Print version information",
		Run: func(cmd *cobra.Command, args []string) {
			fmt.Printf("dgraph-agent %s (%s) built %s\n", version, commit, date)
			fmt.Printf("Go %s %s/%s\n", runtime.Version(), runtime.GOOS, runtime.GOARCH)
		},
	}
}

func testCmd() *cobra.Command {
	return &cobra.Command{
		Use:   "test",
		Short: "Test all configured connectors",
		RunE: func(cmd *cobra.Command, args []string) error {
			cfgFile, _ := cmd.Flags().GetString("config")
			cfg, err := config.Init(cfgFile)
			if err != nil {
				return err
			}
			log := buildLogger(cfg.LogLevel)
			allOK := true
			for _, connCfg := range cfg.Connectors {
				conn, err := connector.New(connCfg.Type, connCfg.Settings)
				if err != nil {
					fmt.Printf("✗ %s: create error: %v\n", connCfg.ID, err)
					allOK = false
					continue
				}
				ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
				err = conn.Test(ctx)
				cancel()
				if err != nil {
					fmt.Printf("✗ %s (%s): %v\n", connCfg.ID, connCfg.Type, err)
					allOK = false
				} else {
					fmt.Printf("✓ %s (%s): OK\n", connCfg.ID, connCfg.Type)
				}
				_ = log
			}
			if !allOK {
				return fmt.Errorf("one or more connectors failed")
			}
			return nil
		},
	}
}

func statusCmd() *cobra.Command {
	return &cobra.Command{
		Use:   "status",
		Short: "Print agent status (calls health endpoint)",
		RunE: func(cmd *cobra.Command, args []string) error {
			resp, err := http.Get("http://127.0.0.1:9090/health")
			if err != nil {
				return fmt.Errorf("agent not running: %w", err)
			}
			defer resp.Body.Close()
			fmt.Printf("Agent is running (HTTP %d)\n", resp.StatusCode)
			return nil
		},
	}
}
