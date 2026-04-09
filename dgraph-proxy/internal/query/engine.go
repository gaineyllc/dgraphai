// Package query provides a simple in-memory graph query engine for dgraph-proxy.
//
// This is NOT a full Cypher engine — it's a safe subset that covers the
// queries the dgraph.ai frontend actually uses in air-gapped mode:
//
//   - Node lookup by ID
//   - Node scan with label filter
//   - Node scan with property filter (=, !=, contains, starts_with)
//   - Edge traversal (1 hop: MATCH (a)-[r:TYPE]->(b))
//   - Aggregate counts (COUNT, GROUP BY label)
//   - LIMIT / OFFSET
//
// For anything more complex, the proxy returns a QueryTooComplex error
// and the caller should display a "connect to cloud for full query support"
// message.
package query

import (
	"fmt"
	"strings"

	"github.com/gaineyllc/dgraphai/dgraph-proxy/internal/store"
)

// ErrQueryTooComplex is returned when the query exceeds local engine capabilities.
var ErrQueryTooComplex = fmt.Errorf("query too complex for local engine — connect to cloud")

// Result holds query results.
type Result struct {
	Columns []string         `json:"columns"`
	Rows    []map[string]any `json:"rows"`
	Count   int              `json:"count"`
	Capped  bool             `json:"capped"` // true if results were limited
}

// Engine executes queries against the local store.
type Engine struct {
	store *store.Store
}

// New creates a new query engine.
func New(s *store.Store) *Engine {
	return &Engine{store: s}
}

// NodesByLabel returns all nodes matching the given label.
func (e *Engine) NodesByLabel(label string, limit int) (*Result, error) {
	if limit <= 0 || limit > 10000 {
		limit = 1000
	}
	var rows []map[string]any
	capped := false

	err := e.store.ScanNodes(func(n *store.NodeRecord) error {
		if !hasLabel(n.Labels, label) {
			return nil
		}
		if len(rows) >= limit {
			capped = true
			return fmt.Errorf("limit reached") // sentinel to stop scan
		}
		rows = append(rows, nodeToRow(n))
		return nil
	})
	if err != nil && err.Error() != "limit reached" {
		return nil, err
	}

	return &Result{
		Columns: []string{"id", "labels", "properties", "created_at", "updated_at"},
		Rows:    rows,
		Count:   len(rows),
		Capped:  capped,
	}, nil
}

// NodeByID returns a single node by ID.
func (e *Engine) NodeByID(id string) (*store.NodeRecord, error) {
	return e.store.GetNode(id)
}

// NodesByProperty returns nodes where properties[key] matches the given value.
func (e *Engine) NodesByProperty(key, op, value string, limit int) (*Result, error) {
	if limit <= 0 || limit > 10000 {
		limit = 1000
	}
	if !isAllowedOp(op) {
		return nil, fmt.Errorf("unsupported operator %q", op)
	}

	var rows []map[string]any
	capped := false

	err := e.store.ScanNodes(func(n *store.NodeRecord) error {
		v, ok := n.Properties[key]
		if !ok {
			return nil
		}
		if !matchOp(fmt.Sprintf("%v", v), op, value) {
			return nil
		}
		if len(rows) >= limit {
			capped = true
			return fmt.Errorf("limit reached")
		}
		rows = append(rows, nodeToRow(n))
		return nil
	})
	if err != nil && err.Error() != "limit reached" {
		return nil, err
	}

	return &Result{
		Columns: []string{"id", "labels", "properties"},
		Rows:    rows,
		Count:   len(rows),
		Capped:  capped,
	}, nil
}

// LabelCounts returns a map of label → node count (for inventory page).
func (e *Engine) LabelCounts() (map[string]int, error) {
	counts := make(map[string]int)
	err := e.store.ScanNodes(func(n *store.NodeRecord) error {
		for _, l := range n.Labels {
			counts[l]++
		}
		return nil
	})
	return counts, err
}

// EdgesByNode returns all edges from or to the given node ID.
func (e *Engine) EdgesByNode(nodeID string, direction string) (*Result, error) {
	var rows []map[string]any
	err := e.store.ScanEdges(func(edge *store.EdgeRecord) error {
		switch direction {
		case "out":
			if edge.FromID != nodeID {
				return nil
			}
		case "in":
			if edge.ToID != nodeID {
				return nil
			}
		default: // "both"
			if edge.FromID != nodeID && edge.ToID != nodeID {
				return nil
			}
		}
		rows = append(rows, edgeToRow(edge))
		return nil
	})
	return &Result{Rows: rows, Count: len(rows)}, err
}

// Stats returns aggregate statistics about the local store.
func (e *Engine) Stats() (map[string]any, error) {
	labelCounts, err := e.LabelCounts()
	if err != nil {
		return nil, err
	}

	nodeCount, _ := e.store.NodeCount()
	pendingDeltas, _ := e.store.PendingDeltaCount()

	return map[string]any{
		"node_count":     nodeCount,
		"pending_deltas": pendingDeltas,
		"label_counts":   labelCounts,
	}, nil
}

// ── Helpers ───────────────────────────────────────────────────────────────────

func hasLabel(labels []string, label string) bool {
	for _, l := range labels {
		if l == label {
			return true
		}
	}
	return false
}

func isAllowedOp(op string) bool {
	switch op {
	case "=", "!=", "contains", "starts_with", "ends_with":
		return true
	}
	return false
}

func matchOp(actual, op, value string) bool {
	switch op {
	case "=":
		return actual == value
	case "!=":
		return actual != value
	case "contains":
		return strings.Contains(strings.ToLower(actual), strings.ToLower(value))
	case "starts_with":
		return strings.HasPrefix(strings.ToLower(actual), strings.ToLower(value))
	case "ends_with":
		return strings.HasSuffix(strings.ToLower(actual), strings.ToLower(value))
	}
	return false
}

func nodeToRow(n *store.NodeRecord) map[string]any {
	return map[string]any{
		"id":         n.ID,
		"labels":     n.Labels,
		"properties": n.Properties,
		"created_at": n.CreatedAt,
		"updated_at": n.UpdatedAt,
		"synced_at":  n.SyncedAt,
	}
}

func edgeToRow(e *store.EdgeRecord) map[string]any {
	return map[string]any{
		"id":         e.ID,
		"type":       e.Type,
		"from_id":    e.FromID,
		"to_id":      e.ToID,
		"properties": e.Properties,
		"created_at": e.CreatedAt,
	}
}
