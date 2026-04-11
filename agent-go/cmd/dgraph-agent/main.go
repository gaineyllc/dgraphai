// dgraph-agent — on-premises scanner agent for dgraph.ai
//
// Single Go binary. Zero inbound ports. Outbound HTTPS only.
//
// Quick start:
//   Windows: set DGRAPH_AGENT_API_KEY=dga_xxx && dgraph-agent.exe
//   Linux:   DGRAPH_AGENT_API_KEY=dga_xxx ./dgraph-agent
//
// The agent will:
//   1. Connect to the platform using your API key
//   2. Fetch which connectors to scan from the platform
//   3. Scan the assigned connectors and upload metadata
//   4. Send a heartbeat every 30s so the platform shows "Online"
//   5. Re-fetch config every 5 minutes (picks up new connectors instantly)
package main

import (
	"context"
	"fmt"
	"net/http"
	"os"
	"os/signal"
	"runtime"
	"sync/atomic"
	"syscall"
	"time"

	"github.com/spf13/cobra"
	"go.uber.org/zap"
	"go.uber.org/zap/zapcore"

	"github.com/gaineyllc/dgraphai/agent/internal/config"
	"github.com/gaineyllc/dgraphai/agent/internal/connector"
	"github.com/gaineyllc/dgraphai/agent/internal/enricher"
	"github.com/gaineyllc/dgraphai/agent/internal/platform"
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
		RunE:  run,
	}

	root.PersistentFlags().String("config", "", "config file path")
	root.AddCommand(versionCmd(), testCmd(), statusCmd())

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

	// Set version in platform client
	platform.SetVersion(version)

	log.Info("dgraph-agent starting",
		zap.String("version", version),
		zap.String("commit", commit),
		zap.String("os", runtime.GOOS),
		zap.String("arch", runtime.GOARCH),
		zap.String("api_endpoint", cfg.APIEndpoint),
	)

	if cfg.APIKey == "" {
		return fmt.Errorf("DGRAPH_AGENT_API_KEY is required — generate one in the dgraph.ai UI under Connectors → Install Agent")
	}

	ctx, cancel := signal.NotifyContext(context.Background(),
		syscall.SIGINT, syscall.SIGTERM)
	defer cancel()

	// Health server
	go startHealthServer(cfg.HealthBind, log)

	// Platform control plane client (config + heartbeat)
	pc := platform.New(cfg.APIEndpoint, cfg.APIKey, log)

	// Data plane client (file metadata sync)
	syncClient := agentsync.New(cfg.APIEndpoint, cfg.APIKey, cfg.TenantID, cfg.AgentID, log, nil)

	// Enricher
	subEnrich := enricher.NewSubprocessEnricher("", cfg.EnableSecretScan, cfg.EnablePIIScan)

	// Stats counters for heartbeat
	var (
		totalIndexed atomic.Int64
		lastError    atomic.Value
	)

	// ── Fetch initial config from platform ────────────────────────────────────
	log.Info("fetching connector config from platform...")
	platConfig, err := pc.FetchConfig(ctx)
	if err != nil {
		log.Warn("could not fetch config from platform — check API key and endpoint",
			zap.Error(err),
			zap.String("endpoint", cfg.APIEndpoint),
		)
		// Fall back to static config if set
		if len(cfg.Connectors) == 0 {
			return fmt.Errorf("no connector config available: %w", err)
		}
		log.Info("using static connector config from config file/env",
			zap.Int("connectors", len(cfg.Connectors)),
		)
	} else {
		// Merge platform config into static config
		cfg.TenantID = platConfig.TenantID
		cfg.AgentID = platConfig.AgentID
		mergeConnectors(cfg, platConfig)
		// Update IDs now that platform has assigned them
		syncClient.SetIDs(platConfig.TenantID, platConfig.AgentID)
		log.Info("loaded connector config from platform",
			zap.Int("connectors", len(platConfig.Connectors)),
			zap.String("agent_id", platConfig.AgentID),
		)
	}

	// ── Send initial heartbeat ────────────────────────────────────────────────
	hostname, _ := os.Hostname()
	sendHeartbeat(ctx, pc, cfg, hostname, int(totalIndexed.Load()), lastError, log)

	// ── Tickers ───────────────────────────────────────────────────────────────
	heartbeatTicker := time.NewTicker(30 * time.Second)
	configTicker    := time.NewTicker(5 * time.Minute)
	scanTicker      := time.NewTicker(cfg.SyncInterval)
	defer heartbeatTicker.Stop()
	defer configTicker.Stop()
	defer scanTicker.Stop()

	// Run first scan immediately
	go func() {
		n, err := runAllScans(ctx, cfg, syncClient, subEnrich, log)
		totalIndexed.Add(int64(n))
		if err != nil {
			lastError.Store(err.Error())
		}
	}()

	log.Info("agent running",
		zap.Duration("scan_interval", cfg.SyncInterval),
		zap.String("health", cfg.HealthBind),
	)

	for {
		select {
		case <-ctx.Done():
			log.Info("shutting down gracefully")
			return nil

		case <-heartbeatTicker.C:
			sendHeartbeat(ctx, pc, cfg, hostname, int(totalIndexed.Load()), lastError, log)

		case <-configTicker.C:
			// Re-fetch config to pick up newly assigned connectors
			if platConfig, err := pc.FetchConfig(ctx); err != nil {
				log.Warn("config refresh failed", zap.Error(err))
			} else {
				mergeConnectors(cfg, platConfig)
				log.Info("config refreshed",
					zap.Int("connectors", len(cfg.Connectors)),
				)
			}

		case <-scanTicker.C:
			n, err := runAllScans(ctx, cfg, syncClient, subEnrich, log)
			totalIndexed.Add(int64(n))
			if err != nil {
				lastError.Store(err.Error())
			}
		}
	}
}

// mergeConnectors updates cfg.Connectors from the platform config.
// Platform config takes precedence over static config for the same connector ID.
func mergeConnectors(cfg *config.Config, platConfig *platform.AgentConfig) {
	// Build map of platform connectors
	platMap := make(map[string]platform.ConnectorConfig, len(platConfig.Connectors))
	for _, c := range platConfig.Connectors {
		platMap[c.ID] = c
	}

	// Convert platform connectors to internal config format
	var merged []config.ConnectorConfig
	for _, pc := range platConfig.Connectors {
		if !pc.Enabled {
			continue
		}
		merged = append(merged, config.ConnectorConfig{
			ID:       pc.ID,
			Type:     pc.ConnectorType,
			Name:     pc.Name,
			Enabled:  pc.Enabled,
			Settings: pc.Config,
		})
	}

	// Keep any static connectors not in platform config
	for _, sc := range cfg.Connectors {
		if _, inPlat := platMap[sc.ID]; !inPlat {
			merged = append(merged, sc)
		}
	}

	cfg.Connectors = merged
}

// runAllScans runs all enabled connectors and returns total files indexed.
func runAllScans(ctx context.Context, cfg *config.Config, client *agentsync.Client, enrich *enricher.SubprocessEnricher, log *zap.Logger) (int, error) {
	if len(cfg.Connectors) == 0 {
		log.Info("no connectors configured — waiting for platform assignment")
		return 0, nil
	}

	total := 0
	var lastErr error

	for _, connCfg := range cfg.Connectors {
		if !connCfg.Enabled {
			continue
		}

		conn, err := connector.New(connCfg.Type, connCfg.Settings)
		if err != nil {
			log.Error("connector init failed",
				zap.String("id", connCfg.ID),
				zap.String("type", connCfg.Type),
				zap.Error(err),
			)
			lastErr = err
			continue
		}

		log.Info("starting scan",
			zap.String("id", connCfg.ID),
			zap.String("type", connCfg.Type),
			zap.String("name", connCfg.Name),
		)

		result, err := client.Sync(ctx, conn, connCfg.ID)
		if err != nil {
			log.Error("scan failed",
				zap.String("id", connCfg.ID),
				zap.Error(err),
			)
			lastErr = err
		} else {
			log.Info("scan complete",
				zap.String("id", connCfg.ID),
				zap.Int("files", result.FilesIndexed),
				zap.Duration("duration", result.Duration),
			)
			total += result.FilesIndexed
		}
	}

	return total, lastErr
}

// sendHeartbeat sends a heartbeat to the platform. Non-fatal on error.
func sendHeartbeat(ctx context.Context, pc *platform.Client, cfg *config.Config,
	hostname string, indexed int, lastError atomic.Value, log *zap.Logger,
) {
	statuses := make(map[string]string, len(cfg.Connectors))
	for _, c := range cfg.Connectors {
		statuses[c.ID] = "idle"
	}

	errStr := ""
	if v := lastError.Load(); v != nil {
		errStr = v.(string)
	}

	hb := platform.HeartbeatRequest{
		AgentID:           cfg.AgentID,
		Version:           version,
		OS:                runtime.GOOS,
		Hostname:          hostname,
		FilesIndexed:      indexed,
		LastError:         errStr,
		ConnectorStatuses: statuses,
	}

	if _, err := pc.Heartbeat(ctx, hb); err != nil {
		log.Debug("heartbeat failed", zap.Error(err))
	} else {
		log.Debug("heartbeat sent", zap.Int("indexed", indexed))
	}
}

func startHealthServer(bind string, log *zap.Logger) {
	mux := http.NewServeMux()
	mux.HandleFunc("/health", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		fmt.Fprintf(w, `{"status":"ok","version":"%s"}`, version)
	})
	srv := &http.Server{Addr: bind, Handler: mux, ReadTimeout: 5 * time.Second}
	if err := srv.ListenAndServe(); err != nil {
		log.Warn("health server stopped", zap.Error(err))
	}
}

func buildLogger(level string) *zap.Logger {
	lvl := zapcore.InfoLevel
	_ = lvl.UnmarshalText([]byte(level))

	cfg := zap.NewProductionConfig()
	cfg.Level = zap.NewAtomicLevelAt(lvl)
	cfg.EncoderConfig.TimeKey = "time"
	cfg.EncoderConfig.EncodeTime = zapcore.ISO8601TimeEncoder

	// Use console format on Windows for readability
	if runtime.GOOS == "windows" {
		cfg.Encoding = "console"
		cfg.EncoderConfig.EncodeLevel = zapcore.CapitalColorLevelEncoder
	}

	l, _ := cfg.Build()
	return l
}

func versionCmd() *cobra.Command {
	return &cobra.Command{
		Use:   "version",
		Short: "Print version information",
		Run: func(cmd *cobra.Command, args []string) {
			fmt.Printf("dgraph-agent %s (commit: %s, built: %s)\n", version, commit, date)
			fmt.Printf("  OS/Arch: %s/%s\n", runtime.GOOS, runtime.GOARCH)
		},
	}
}

func testCmd() *cobra.Command {
	return &cobra.Command{
		Use:   "test",
		Short: "Test connectivity to the platform",
		RunE: func(cmd *cobra.Command, args []string) error {
			cfgFile, _ := cmd.Flags().GetString("config")
			cfg, err := config.Init(cfgFile)
			if err != nil {
				return err
			}
			log := buildLogger("info")
			pc := platform.New(cfg.APIEndpoint, cfg.APIKey, log)
			ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
			defer cancel()

			fmt.Printf("Testing connection to %s ...\n", cfg.APIEndpoint)
			platCfg, err := pc.FetchConfig(ctx)
			if err != nil {
				fmt.Printf("FAIL: %v\n", err)
				return err
			}
			fmt.Printf("OK — tenant: %s, connectors assigned: %d\n",
				platCfg.TenantID, len(platCfg.Connectors))
			for _, c := range platCfg.Connectors {
				fmt.Printf("  - [%s] %s (%s)\n", c.ConnectorType, c.Name, c.ID)
			}
			return nil
		},
	}
}

func statusCmd() *cobra.Command {
	return &cobra.Command{
		Use:   "status",
		Short: "Show current agent status",
		RunE: func(cmd *cobra.Command, args []string) error {
			resp, err := http.Get("http://127.0.0.1:9090/health")
			if err != nil {
				fmt.Println("Agent is not running (health endpoint unreachable)")
				return nil
			}
			defer resp.Body.Close()
			fmt.Printf("Agent is running (health: %d)\n", resp.StatusCode)
			return nil
		},
	}
}

func buildHealthReport(cfg *config.Config, _ *enricher.SubprocessEnricher) map[string]any {
	return map[string]any{
		"version":    version,
		"os":         runtime.GOOS,
		"connectors": len(cfg.Connectors),
	}
}
