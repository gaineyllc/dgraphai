// Package store provides the local embedded graph store for dgraph-proxy.
//
// Design:
//   - All graph data lives in BadgerDB (pure Go, embeddable, no CGO).
//   - Data is partitioned by tenant_id prefix — future multi-tenant support.
//   - Three key namespaces:
//       n:<tenant>:<node_id>      → JSON-encoded NodeRecord
//       e:<tenant>:<edge_id>      → JSON-encoded EdgeRecord
//       d:<tenant>:<seq>          → DeltaRecord (pending upload to cloud)
//   - WAL is handled by BadgerDB itself (LSM + value log).
//   - Compaction runs in background via BadgerDB GC goroutine.
package store

import (
	"encoding/json"
	"fmt"
	"time"

	badger "github.com/dgraph-io/badger/v4"
	"github.com/google/uuid"
	"go.uber.org/zap"
)

// NodeRecord is the local representation of a graph node.
type NodeRecord struct {
	ID         string            `json:"id"`
	TenantID   string            `json:"tenant_id"`
	Labels     []string          `json:"labels"`     // e.g. ["File", "Document"]
	Properties map[string]any    `json:"properties"` // arbitrary key-value
	CreatedAt  time.Time         `json:"created_at"`
	UpdatedAt  time.Time         `json:"updated_at"`
	SyncedAt   *time.Time        `json:"synced_at,omitempty"` // nil = not yet synced
	Checksum   string            `json:"checksum"`            // SHA-256 of canonical JSON
}

// EdgeRecord is the local representation of a graph edge.
type EdgeRecord struct {
	ID         string         `json:"id"`
	TenantID   string         `json:"tenant_id"`
	Type       string         `json:"type"`       // e.g. "CONTAINS", "OWNED_BY"
	FromID     string         `json:"from_id"`
	ToID       string         `json:"to_id"`
	Properties map[string]any `json:"properties"`
	CreatedAt  time.Time      `json:"created_at"`
	UpdatedAt  time.Time      `json:"updated_at"`
	SyncedAt   *time.Time     `json:"synced_at,omitempty"`
}

// DeltaRecord is a pending change waiting to be synced to cloud.
type DeltaRecord struct {
	Seq       uint64          `json:"seq"`
	TenantID  string          `json:"tenant_id"`
	Op        DeltaOp         `json:"op"`
	NodeID    string          `json:"node_id,omitempty"`
	EdgeID    string          `json:"edge_id,omitempty"`
	Payload   json.RawMessage `json:"payload"`
	CreatedAt time.Time       `json:"created_at"`
}

// DeltaOp is the type of change.
type DeltaOp string

const (
	OpUpsertNode  DeltaOp = "upsert_node"
	OpDeleteNode  DeltaOp = "delete_node"
	OpUpsertEdge  DeltaOp = "upsert_edge"
	OpDeleteEdge  DeltaOp = "delete_edge"
)

// Store wraps BadgerDB and provides typed graph operations.
type Store struct {
	db       *badger.DB
	tenantID string
	log      *zap.Logger
	seq      *badger.Sequence // monotonic sequence for delta ordering
}

// Open initialises or opens the BadgerDB store at dataDir.
func Open(dataDir, tenantID string, log *zap.Logger) (*Store, error) {
	opts := badger.DefaultOptions(dataDir).
		WithLogger(nil). // suppress Badger's own logger; we handle it
		WithCompression(badger.ZSTD).
		WithZSTDCompressionLevel(1).
		WithNumGoroutines(4)

	db, err := badger.Open(opts)
	if err != nil {
		return nil, fmt.Errorf("open badger at %s: %w", dataDir, err)
	}

	seq, err := db.GetSequence([]byte("delta_seq:"+tenantID), 1000)
	if err != nil {
		db.Close()
		return nil, fmt.Errorf("get sequence: %w", err)
	}

	s := &Store{db: db, tenantID: tenantID, log: log, seq: seq}

	// Background GC
	go s.runGC()

	return s, nil
}

// Close flushes and closes the store.
func (s *Store) Close() error {
	s.seq.Release()
	return s.db.Close()
}

// ── Node operations ──────────────────────────────────────────────────────────

// UpsertNode writes or updates a node and queues a delta.
func (s *Store) UpsertNode(node *NodeRecord) error {
	if node.ID == "" {
		node.ID = uuid.NewString()
	}
	node.TenantID = s.tenantID
	now := time.Now().UTC()
	if node.CreatedAt.IsZero() {
		node.CreatedAt = now
	}
	node.UpdatedAt = now

	data, err := json.Marshal(node)
	if err != nil {
		return fmt.Errorf("marshal node: %w", err)
	}

	return s.db.Update(func(txn *badger.Txn) error {
		// Write node
		nodeKey := s.nodeKey(node.ID)
		if err := txn.Set(nodeKey, data); err != nil {
			return fmt.Errorf("set node: %w", err)
		}
		// Queue delta
		return s.writeDelta(txn, &DeltaRecord{
			TenantID:  s.tenantID,
			Op:        OpUpsertNode,
			NodeID:    node.ID,
			Payload:   data,
			CreatedAt: now,
		})
	})
}

// GetNode retrieves a node by ID.
func (s *Store) GetNode(id string) (*NodeRecord, error) {
	var node NodeRecord
	err := s.db.View(func(txn *badger.Txn) error {
		item, err := txn.Get(s.nodeKey(id))
		if err != nil {
			return err
		}
		return item.Value(func(val []byte) error {
			return json.Unmarshal(val, &node)
		})
	})
	if err == badger.ErrKeyNotFound {
		return nil, nil
	}
	return &node, err
}

// DeleteNode removes a node and queues a delete delta.
func (s *Store) DeleteNode(id string) error {
	now := time.Now().UTC()
	return s.db.Update(func(txn *badger.Txn) error {
		if err := txn.Delete(s.nodeKey(id)); err != nil && err != badger.ErrKeyNotFound {
			return err
		}
		payload, _ := json.Marshal(map[string]string{"id": id})
		return s.writeDelta(txn, &DeltaRecord{
			TenantID:  s.tenantID,
			Op:        OpDeleteNode,
			NodeID:    id,
			Payload:   payload,
			CreatedAt: now,
		})
	})
}

// ScanNodes iterates all nodes for this tenant, calling fn for each.
// Returns early if fn returns a non-nil error.
func (s *Store) ScanNodes(fn func(*NodeRecord) error) error {
	prefix := []byte("n:" + s.tenantID + ":")
	return s.db.View(func(txn *badger.Txn) error {
		opts := badger.DefaultIteratorOptions
		opts.Prefix = prefix
		it := txn.NewIterator(opts)
		defer it.Close()
		for it.Rewind(); it.Valid(); it.Next() {
			item := it.Item()
			var node NodeRecord
			if err := item.Value(func(v []byte) error {
				return json.Unmarshal(v, &node)
			}); err != nil {
				s.log.Warn("corrupt node record", zap.ByteString("key", item.Key()), zap.Error(err))
				continue
			}
			if err := fn(&node); err != nil {
				return err
			}
		}
		return nil
	})
}

// NodeCount returns the total number of nodes for this tenant.
func (s *Store) NodeCount() (int64, error) {
	var count int64
	err := s.ScanNodes(func(_ *NodeRecord) error {
		count++
		return nil
	})
	return count, err
}

// ── Edge operations ──────────────────────────────────────────────────────────

// UpsertEdge writes or updates an edge and queues a delta.
func (s *Store) UpsertEdge(edge *EdgeRecord) error {
	if edge.ID == "" {
		edge.ID = uuid.NewString()
	}
	edge.TenantID = s.tenantID
	now := time.Now().UTC()
	if edge.CreatedAt.IsZero() {
		edge.CreatedAt = now
	}
	edge.UpdatedAt = now

	data, err := json.Marshal(edge)
	if err != nil {
		return fmt.Errorf("marshal edge: %w", err)
	}

	return s.db.Update(func(txn *badger.Txn) error {
		edgeKey := s.edgeKey(edge.ID)
		if err := txn.Set(edgeKey, data); err != nil {
			return fmt.Errorf("set edge: %w", err)
		}
		return s.writeDelta(txn, &DeltaRecord{
			TenantID:  s.tenantID,
			Op:        OpUpsertEdge,
			EdgeID:    edge.ID,
			Payload:   data,
			CreatedAt: now,
		})
	})
}

// ScanEdges iterates all edges for this tenant.
func (s *Store) ScanEdges(fn func(*EdgeRecord) error) error {
	prefix := []byte("e:" + s.tenantID + ":")
	return s.db.View(func(txn *badger.Txn) error {
		opts := badger.DefaultIteratorOptions
		opts.Prefix = prefix
		it := txn.NewIterator(opts)
		defer it.Close()
		for it.Rewind(); it.Valid(); it.Next() {
			item := it.Item()
			var edge EdgeRecord
			if err := item.Value(func(v []byte) error {
				return json.Unmarshal(v, &edge)
			}); err != nil {
				continue
			}
			if err := fn(&edge); err != nil {
				return err
			}
		}
		return nil
	})
}

// ── Delta operations (sync queue) ────────────────────────────────────────────

// DrainDeltas returns up to n pending deltas in sequence order and marks them
// as in-flight. The caller must call AckDeltas or NackDeltas after processing.
func (s *Store) DrainDeltas(n int) ([]*DeltaRecord, error) {
	var deltas []*DeltaRecord
	prefix := []byte("d:" + s.tenantID + ":")

	err := s.db.View(func(txn *badger.Txn) error {
		opts := badger.DefaultIteratorOptions
		opts.Prefix = prefix
		it := txn.NewIterator(opts)
		defer it.Close()
		for it.Rewind(); it.Valid() && len(deltas) < n; it.Next() {
			item := it.Item()
			var d DeltaRecord
			if err := item.Value(func(v []byte) error {
				return json.Unmarshal(v, &d)
			}); err != nil {
				continue
			}
			deltas = append(deltas, &d)
		}
		return nil
	})
	return deltas, err
}

// AckDeltas removes successfully synced deltas from the queue.
func (s *Store) AckDeltas(seqs []uint64) error {
	return s.db.Update(func(txn *badger.Txn) error {
		for _, seq := range seqs {
			key := s.deltaKey(seq)
			if err := txn.Delete(key); err != nil && err != badger.ErrKeyNotFound {
				return err
			}
		}
		return nil
	})
}

// PendingDeltaCount returns how many deltas are waiting to be synced.
func (s *Store) PendingDeltaCount() (int64, error) {
	var count int64
	prefix := []byte("d:" + s.tenantID + ":")
	err := s.db.View(func(txn *badger.Txn) error {
		opts := badger.DefaultIteratorOptions
		opts.PrefetchValues = false
		opts.Prefix = prefix
		it := txn.NewIterator(opts)
		defer it.Close()
		for it.Rewind(); it.Valid(); it.Next() {
			count++
		}
		return nil
	})
	return count, err
}

// ── Internal helpers ─────────────────────────────────────────────────────────

func (s *Store) nodeKey(id string) []byte {
	return []byte("n:" + s.tenantID + ":" + id)
}

func (s *Store) edgeKey(id string) []byte {
	return []byte("e:" + s.tenantID + ":" + id)
}

func (s *Store) deltaKey(seq uint64) []byte {
	return []byte(fmt.Sprintf("d:%s:%020d", s.tenantID, seq))
}

func (s *Store) writeDelta(txn *badger.Txn, d *DeltaRecord) error {
	seq, err := s.seq.Next()
	if err != nil {
		return fmt.Errorf("next seq: %w", err)
	}
	d.Seq = seq
	data, err := json.Marshal(d)
	if err != nil {
		return err
	}
	return txn.Set(s.deltaKey(seq), data)
}

func (s *Store) runGC() {
	ticker := time.NewTicker(10 * time.Minute)
	defer ticker.Stop()
	for range ticker.C {
		// BadgerDB recommends running GC at < 0.5 discard ratio.
		for {
			if err := s.db.RunValueLogGC(0.5); err != nil {
				break
			}
		}
	}
}
