// Package config handles all agent configuration.
// Sources (in priority order): env vars > config file > defaults.
// Sensitive values (API key, credentials) are NEVER logged.
package config

import (
	"fmt"
	"strings"
	"time"

	"github.com/spf13/viper"
)

// Config is the complete agent configuration.
// All fields are read-only after Init().
type Config struct {
	// Identity
	TenantID  string `mapstructure:"tenant_id"`
	AgentID   string `mapstructure:"agent_id"`
	AgentName string `mapstructure:"agent_name"`

	// Cloud endpoint
	APIEndpoint  string        `mapstructure:"api_endpoint"`
	APIKey       string        `mapstructure:"api_key"`        // SENSITIVE — never log
	TLSSkipVerify bool         `mapstructure:"tls_skip_verify"` // false in production
	SyncInterval time.Duration `mapstructure:"sync_interval"`
	HTTPTimeout  time.Duration `mapstructure:"http_timeout"`

	// Connectors to index
	Connectors []ConnectorConfig `mapstructure:"connectors"`

	// Local queue (for offline/air-gapped operation)
	QueuePath    string `mapstructure:"queue_path"`    // SQLite path for offline queue
	QueueMaxMB   int    `mapstructure:"queue_max_mb"`  // max disk usage before blocking

	// Enrichment (local, before data leaves)
	EnableSecretScan bool `mapstructure:"enable_secret_scan"`
	EnableBinaryScan bool `mapstructure:"enable_binary_scan"`
	EnablePIIScan    bool `mapstructure:"enable_pii_scan"`

	// Health server
	HealthBind string `mapstructure:"health_bind"` // default: 127.0.0.1:9090

	// Observability
	MetricsBind string `mapstructure:"metrics_bind"` // Prometheus, default: 127.0.0.1:9091
	LogLevel    string `mapstructure:"log_level"`    // debug|info|warn|error

	// Air-gapped mode
	AirGapped    bool   `mapstructure:"air_gapped"`
	LocalGraphDB string `mapstructure:"local_graph_db"` // SQLite path for local graph
}

// ConnectorConfig defines a single data source to index.
type ConnectorConfig struct {
	ID       string            `mapstructure:"id"`
	Type     string            `mapstructure:"type"`     // local|smb|s3|nfs
	Name     string            `mapstructure:"name"`
	Enabled  bool              `mapstructure:"enabled"`
	Settings map[string]string `mapstructure:"settings"` // type-specific, SENSITIVE
}

func Init(cfgFile string) (*Config, error) {
	v := viper.New()

	// Defaults
	v.SetDefault("api_endpoint",       "https://api.dgraph.ai")
	v.SetDefault("sync_interval",      "5m")
	v.SetDefault("http_timeout",       "30s")
	v.SetDefault("health_bind",        "127.0.0.1:9090")
	v.SetDefault("metrics_bind",       "127.0.0.1:9091")
	v.SetDefault("log_level",          "info")
	v.SetDefault("queue_max_mb",       512)
	v.SetDefault("queue_path",         "/var/lib/dgraph-agent/queue.db")
	v.SetDefault("enable_secret_scan", true)
	v.SetDefault("enable_pii_scan",    true)
	v.SetDefault("enable_binary_scan", false)
	v.SetDefault("tls_skip_verify",    false)
	v.SetDefault("air_gapped",         false)

	// Env var override (DGRAPH_AGENT_*)
	// DGRAPH_AGENT_API_KEY → api_key, DGRAPH_AGENT_API_ENDPOINT → api_endpoint
	v.SetEnvPrefix("DGRAPH_AGENT")
	v.SetEnvKeyReplacer(strings.NewReplacer(".", "_"))
	v.AutomaticEnv()
	// Explicit binds for common env vars (viper AutomaticEnv can miss these)
	v.BindEnv("api_key", "DGRAPH_AGENT_API_KEY")           //nolint:errcheck
	v.BindEnv("api_endpoint", "DGRAPH_AGENT_API_ENDPOINT") //nolint:errcheck
	v.BindEnv("tenant_id", "DGRAPH_AGENT_TENANT_ID")       //nolint:errcheck
	v.BindEnv("agent_id", "DGRAPH_AGENT_ID")               //nolint:errcheck
	v.BindEnv("log_level", "DGRAPH_AGENT_LOG_LEVEL")       //nolint:errcheck

	// Config file
	if cfgFile != "" {
		v.SetConfigFile(cfgFile)
	} else {
		v.AddConfigPath("/etc/dgraph-agent")
		v.AddConfigPath("$HOME/.dgraph-agent")
		v.AddConfigPath(".")
		v.SetConfigName("config")
	}

	if err := v.ReadInConfig(); err != nil {
		if _, ok := err.(viper.ConfigFileNotFoundError); !ok {
			return nil, fmt.Errorf("reading config: %w", err)
		}
	}

	cfg := &Config{}
	if err := v.Unmarshal(cfg); err != nil {
		return nil, fmt.Errorf("unmarshaling config: %w", err)
	}

	if err := validate(cfg); err != nil {
		return nil, err
	}

	return cfg, nil
}

func validate(cfg *Config) error {
	// TenantID is optional at startup — fetched from platform on first connect
	// APIKey is required (unless air-gapped with local config)
	if cfg.APIKey == "" && !cfg.AirGapped {
		return fmt.Errorf("api_key is required (set DGRAPH_AGENT_API_KEY)")
	}
	// Connectors are optional at startup — fetched from platform on first connect
	_ = cfg.Connectors // suppresses linter; populated after FetchConfig
	for i, c := range cfg.Connectors {
		if c.Type == "" {
			return fmt.Errorf("connector[%d]: type is required", i)
		}
		if c.ID == "" {
			cfg.Connectors[i].ID = fmt.Sprintf("%s-%d", c.Type, i)
		}
		if !c.Enabled {
			// Default to enabled
			cfg.Connectors[i].Enabled = true
		}
	}
	return nil
}

// Redacted returns a copy of Config safe for logging (secrets removed).
func (c *Config) Redacted() map[string]interface{} {
	return map[string]interface{}{
		"tenant_id":     c.TenantID,
		"agent_id":      c.AgentID,
		"agent_name":    c.AgentName,
		"api_endpoint":  c.APIEndpoint,
		"api_key":       "[REDACTED]",
		"sync_interval": c.SyncInterval.String(),
		"connectors":    len(c.Connectors),
		"air_gapped":    c.AirGapped,
		"log_level":     c.LogLevel,
	}
}
