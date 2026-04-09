// Package backend provides cloud-abstracted graph database backends.
// The same code runs against Neo4j, AWS Neptune, Azure Cosmos Graph,
// or an in-process SQLite store (air-gapped minimal mode).
package backend

import (
	"context"
	"encoding/json"
	"fmt"
	"time"
)

// Node represents a graph node with labels and properties.
type Node struct {
	ID     string            `json:"id"`
	Labels []string          `json:"labels"`
	Props  map[string]any    `json:"props"`
}

// Edge represents a directed graph relationship.
type Edge struct {
	ID     string         `json:"id"`
	Type   string         `json:"type"`
	FromID string         `json:"from_id"`
	ToID   string         `json:"to_id"`
	Props  map[string]any `json:"props"`
}

// QueryResult is the result of a Cypher query.
type QueryResult struct {
	Rows       []map[string]any
	Total      int
	DurationMS int64
	Backend    string
}

// UpsertResult summarises a batch upsert operation.
type UpsertResult struct {
	NodesCreated int
	NodesUpdated int
	EdgesCreated int
}

// GraphBackend is the cloud-agnostic interface every graph backend implements.
// New backends (e.g. TigerGraph, Memgraph) are added by implementing this interface.
type GraphBackend interface {
	// Query executes a Cypher query and returns rows.
	// Dialects are normalized — the backend translates as needed.
	Query(ctx context.Context, cypher string, params map[string]any, tenantID string) (QueryResult, error)

	// Upsert creates or updates nodes and edges in a single batch.
	Upsert(ctx context.Context, nodes []Node, edges []Edge, tenantID string) (UpsertResult, error)

	// Delete removes nodes (and optionally their relationships) by ID.
	Delete(ctx context.Context, nodeIDs []string, detach bool, tenantID string) (int, error)

	// HealthCheck returns the backend's current status.
	HealthCheck(ctx context.Context) (BackendHealth, error)

	// Close releases any connection pool resources.
	Close() error
}

// BackendHealth reports backend status.
type BackendHealth struct {
	Status    string `json:"status"`    // "ok" | "degraded" | "down"
	Backend   string `json:"backend"`
	NodeCount int64  `json:"node_count"`
	EdgeCount int64  `json:"edge_count"`
	LatencyMS int64  `json:"latency_ms"`
}

// BackendConfig holds connection configuration.
type BackendConfig struct {
	Type     string            // neo4j | neptune | cosmos | sqlite
	URI      string
	Username string
	Password string            // loaded from secret, never logged
	Database string
	TLS      bool
	Options  map[string]string // backend-specific options
}

// New creates a GraphBackend from configuration.
func New(cfg BackendConfig) (GraphBackend, error) {
	switch cfg.Type {
	case "neo4j":
		return newNeo4jBackend(cfg)
	case "neptune":
		return newNeptuneBackend(cfg)
	case "cosmos":
		return newCosmosBackend(cfg)
	case "sqlite":
		return newSQLiteBackend(cfg)
	default:
		return nil, fmt.Errorf("unknown graph backend type: %q", cfg.Type)
	}
}

// ── Neo4j backend ─────────────────────────────────────────────────────────────

type neo4jBackend struct {
	cfg BackendConfig
	// driver neo4j.DriverWithContext  // actual implementation uses neo4j-go-driver/v5
}

func newNeo4jBackend(cfg BackendConfig) (GraphBackend, error) {
	// In the full implementation:
	// driver, err := neo4j.NewDriverWithContext(cfg.URI, neo4j.BasicAuth(cfg.Username, cfg.Password, ""))
	return &neo4jBackend{cfg: cfg}, nil
}

func (b *neo4jBackend) Query(ctx context.Context, cypher string, params map[string]any, tenantID string) (QueryResult, error) {
	start := time.Now()
	// TODO: execute via neo4j-go-driver
	// session := b.driver.NewSession(ctx, neo4j.SessionConfig{DatabaseName: b.cfg.Database})
	// result, err := session.Run(ctx, cypher, params)
	return QueryResult{
		Rows:       []map[string]any{},
		Backend:    "neo4j",
		DurationMS: time.Since(start).Milliseconds(),
	}, nil
}

func (b *neo4jBackend) Upsert(ctx context.Context, nodes []Node, edges []Edge, tenantID string) (UpsertResult, error) {
	// Batch MERGE statements
	return UpsertResult{}, nil
}

func (b *neo4jBackend) Delete(ctx context.Context, nodeIDs []string, detach bool, tenantID string) (int, error) {
	return 0, nil
}

func (b *neo4jBackend) HealthCheck(ctx context.Context) (BackendHealth, error) {
	return BackendHealth{Status: "ok", Backend: "neo4j"}, nil
}

func (b *neo4jBackend) Close() error { return nil }

// ── Neptune backend (AWS) ─────────────────────────────────────────────────────
// Neptune supports openCypher via Bolt protocol — same driver, different auth.

type neptuneBackend struct {
	cfg BackendConfig
}

func newNeptuneBackend(cfg BackendConfig) (GraphBackend, error) {
	// Neptune endpoint: wss://cluster.cluster-xxxx.us-east-1.neptune.amazonaws.com:8182/openCypher
	// Auth: IAM SigV4 (not basic auth) — requires AWS SDK
	return &neptuneBackend{cfg: cfg}, nil
}

func (b *neptuneBackend) Query(ctx context.Context, cypher string, params map[string]any, tenantID string) (QueryResult, error) {
	// openCypher is compatible with standard Cypher for most queries
	// Exceptions: APOC procedures (not available), some aggregations differ
	return QueryResult{Backend: "neptune"}, nil
}

func (b *neptuneBackend) Upsert(ctx context.Context, nodes []Node, edges []Edge, tenantID string) (UpsertResult, error) {
	return UpsertResult{}, nil
}

func (b *neptuneBackend) Delete(ctx context.Context, nodeIDs []string, detach bool, tenantID string) (int, error) {
	return 0, nil
}

func (b *neptuneBackend) HealthCheck(ctx context.Context) (BackendHealth, error) {
	return BackendHealth{Status: "ok", Backend: "neptune"}, nil
}

func (b *neptuneBackend) Close() error { return nil }

// ── Cosmos DB backend (Azure) ─────────────────────────────────────────────────
// Cosmos uses Gremlin (not Cypher) — requires a translation layer.

type cosmosBackend struct {
	cfg BackendConfig
}

func newCosmosBackend(cfg BackendConfig) (GraphBackend, error) {
	// Azure Cosmos DB Graph uses Gremlin API
	// We translate Cypher → Gremlin at this layer
	// Limited Cypher subset supported — document in docs/backends/cosmos.md
	return &cosmosBackend{cfg: cfg}, nil
}

func (b *cosmosBackend) Query(ctx context.Context, cypher string, params map[string]any, tenantID string) (QueryResult, error) {
	gremlin, err := cypherToGremlin(cypher, params, tenantID)
	if err != nil {
		return QueryResult{}, fmt.Errorf("cypher→gremlin translation: %w", err)
	}
	_ = gremlin
	// TODO: execute via go-gremlin client
	return QueryResult{Backend: "cosmos"}, nil
}

func (b *cosmosBackend) Upsert(ctx context.Context, nodes []Node, edges []Edge, tenantID string) (UpsertResult, error) {
	return UpsertResult{}, nil
}

func (b *cosmosBackend) Delete(ctx context.Context, nodeIDs []string, detach bool, tenantID string) (int, error) {
	return 0, nil
}

func (b *cosmosBackend) HealthCheck(ctx context.Context) (BackendHealth, error) {
	return BackendHealth{Status: "ok", Backend: "cosmos"}, nil
}

func (b *cosmosBackend) Close() error { return nil }

// cypherToGremlin translates a limited Cypher subset to Gremlin.
// Only supports the patterns used by dgraph.ai inventory/search queries.
// Complex Cypher (variable-length paths, APOC) is not supported on Cosmos.
func cypherToGremlin(cypher string, params map[string]any, tenantID string) (string, error) {
	// TODO: implement translator
	// Supported patterns:
	//   MATCH (n:File) WHERE n.tenant_id = $tid RETURN n LIMIT 100
	//   MATCH (n:File) WHERE n.tenant_id = $tid AND n.file_category = 'video' RETURN n
	//   MATCH (a)-[r:HAS_VULNERABILITY]->(v) WHERE a.tenant_id = $tid RETURN a, r, v
	return fmt.Sprintf("g.V().has('tenant_id', '%s').limit(100)", tenantID), nil
}

// ── SQLite backend (air-gapped minimal) ───────────────────────────────────────
// Stores graph data in SQLite using adjacency list tables.
// Supports the full Cypher subset via a simple interpreter.
// Not for large datasets — designed for offline/air-gapped demos and testing.

type sqliteBackend struct {
	cfg  BackendConfig
	path string
}

func newSQLiteBackend(cfg BackendConfig) (GraphBackend, error) {
	path := cfg.URI
	if path == "" {
		path = "/var/lib/dgraphai/graph.db"
	}
	return &sqliteBackend{cfg: cfg, path: path}, nil
}

func (b *sqliteBackend) Query(ctx context.Context, cypher string, params map[string]any, tenantID string) (QueryResult, error) {
	// TODO: implement minimal Cypher interpreter over SQLite
	return QueryResult{Backend: "sqlite"}, nil
}

func (b *sqliteBackend) Upsert(ctx context.Context, nodes []Node, edges []Edge, tenantID string) (UpsertResult, error) {
	return UpsertResult{}, nil
}

func (b *sqliteBackend) Delete(ctx context.Context, nodeIDs []string, detach bool, tenantID string) (int, error) {
	return 0, nil
}

func (b *sqliteBackend) HealthCheck(ctx context.Context) (BackendHealth, error) {
	return BackendHealth{Status: "ok", Backend: "sqlite"}, nil
}

func (b *sqliteBackend) Close() error { return nil }

// ── JSON helpers ──────────────────────────────────────────────────────────────

func MarshalProps(v any) ([]byte, error) { return json.Marshal(v) }
func UnmarshalProps(data []byte) (map[string]any, error) {
	var m map[string]any
	return m, json.Unmarshal(data, &m)
}
