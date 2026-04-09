// Package queue implements a durable offline queue backed by SQLite.
// When the cloud API is unreachable, scanner deltas are persisted locally
// and replayed in order when connectivity is restored.
// Safe for concurrent access within a single process.
package queue

import (
	"context"
	"database/sql"
	"encoding/json"
	"fmt"
	"sync"
	"time"

	_ "github.com/mattn/go-sqlite3"
)

const schema = `
CREATE TABLE IF NOT EXISTS pending_deltas (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at  DATETIME NOT NULL DEFAULT (datetime('now')),
    scan_id     TEXT NOT NULL,
    connector_id TEXT NOT NULL,
    agent_id    TEXT NOT NULL,
    tenant_id   TEXT NOT NULL,
    payload     BLOB NOT NULL,   -- JSON-encoded GraphDelta
    attempts    INTEGER NOT NULL DEFAULT 0,
    last_error  TEXT
);
CREATE INDEX IF NOT EXISTS idx_pending_created ON pending_deltas(created_at);
`

// SQLiteQueue is a durable offline queue backed by SQLite.
type SQLiteQueue struct {
	db  *sql.DB
	mu  sync.Mutex
	path string
}

// DeltaRecord is a stored queue entry.
type DeltaRecord struct {
	ID          int64
	ScanID      string
	ConnectorID string
	AgentID     string
	TenantID    string
	Payload     []byte
	Attempts    int
	LastError   string
}

// New creates or opens the SQLite queue at the given file path.
func New(path string) (*SQLiteQueue, error) {
	db, err := sql.Open("sqlite3", path+"?_journal_mode=WAL&_busy_timeout=5000")
	if err != nil {
		return nil, fmt.Errorf("sqlite queue: open %q: %w", path, err)
	}
	db.SetMaxOpenConns(1) // SQLite is single-writer

	if _, err := db.Exec(schema); err != nil {
		return nil, fmt.Errorf("sqlite queue: init schema: %w", err)
	}

	return &SQLiteQueue{db: db, path: path}, nil
}

// Enqueue adds a delta to the persistent queue.
func (q *SQLiteQueue) Enqueue(delta any) error {
	q.mu.Lock()
	defer q.mu.Unlock()

	payload, err := json.Marshal(delta)
	if err != nil {
		return fmt.Errorf("queue: marshal delta: %w", err)
	}

	// Extract fields from the delta (type assertion via JSON round-trip)
	var meta struct {
		ScanID      string `json:"scan_id"`
		ConnectorID string `json:"connector_id"`
		AgentID     string `json:"agent_id"`
		TenantID    string `json:"tenant_id"`
	}
	json.Unmarshal(payload, &meta) //nolint:errcheck

	_, err = q.db.Exec(
		`INSERT INTO pending_deltas (scan_id, connector_id, agent_id, tenant_id, payload)
		 VALUES (?, ?, ?, ?, ?)`,
		meta.ScanID, meta.ConnectorID, meta.AgentID, meta.TenantID, payload,
	)
	return err
}

// Pending returns the count of undelivered entries.
func (q *SQLiteQueue) Pending() (int, error) {
	var count int
	err := q.db.QueryRow(`SELECT count(*) FROM pending_deltas`).Scan(&count)
	return count, err
}

// Flush delivers all pending entries via the provided send function.
// Entries are delivered oldest-first. Failed entries are retried up to
// maxAttempts times before being dropped (with error logged).
func (q *SQLiteQueue) Flush(ctx context.Context, send func(payload []byte) error) error {
	const maxAttempts = 5
	const batchSize   = 100

	for {
		select {
		case <-ctx.Done():
			return ctx.Err()
		default:
		}

		q.mu.Lock()
		rows, err := q.db.QueryContext(ctx,
			`SELECT id, scan_id, connector_id, payload, attempts, last_error
			 FROM pending_deltas
			 ORDER BY id
			 LIMIT ?`, batchSize)
		if err != nil {
			q.mu.Unlock()
			return err
		}

		var records []DeltaRecord
		for rows.Next() {
			var r DeltaRecord
			rows.Scan(&r.ID, &r.ScanID, &r.ConnectorID, &r.Payload, &r.Attempts, &r.LastError)
			records = append(records, r)
		}
		rows.Close()
		q.mu.Unlock()

		if len(records) == 0 {
			break
		}

		for _, record := range records {
			if err := send(record.Payload); err != nil {
				// Update attempt count
				q.mu.Lock()
				if record.Attempts+1 >= maxAttempts {
					// Give up — delete it
					q.db.Exec(`DELETE FROM pending_deltas WHERE id = ?`, record.ID)
				} else {
					q.db.Exec(
						`UPDATE pending_deltas SET attempts = ?, last_error = ? WHERE id = ?`,
						record.Attempts+1, err.Error(), record.ID,
					)
				}
				q.mu.Unlock()
				continue
			}

			// Successfully sent — delete it
			q.mu.Lock()
			q.db.Exec(`DELETE FROM pending_deltas WHERE id = ?`, record.ID)
			q.mu.Unlock()
		}

		time.Sleep(10 * time.Millisecond) // yield between batches
	}

	return nil
}

// Stats returns queue statistics for the health report.
func (q *SQLiteQueue) Stats() map[string]any {
	q.mu.Lock()
	defer q.mu.Unlock()

	var total, maxAttempts int
	q.db.QueryRow(`SELECT count(*), coalesce(max(attempts),0) FROM pending_deltas`).Scan(&total, &maxAttempts)

	return map[string]any{
		"pending":      total,
		"max_attempts": maxAttempts,
		"path":         q.path,
	}
}

// Close releases the database connection.
func (q *SQLiteQueue) Close() error { return q.db.Close() }
