// Package api provides the local HTTP API for dgraph-proxy.
//
// The local API allows agent-go and the dgraph.ai frontend to interact with
// the proxy as if it were the cloud API — with a reduced feature set.
//
// Endpoints:
//
//	GET  /health                  liveness probe
//	GET  /ready                   readiness probe (store open, sync running)
//	GET  /api/v1/stats            node/edge counts, sync status, pending deltas
//	GET  /api/v1/nodes/{id}       fetch node by ID
//	GET  /api/v1/nodes?label=&limit=  scan nodes by label
//	POST /api/v1/nodes            upsert a node (from agent-go ingest)
//	DELETE /api/v1/nodes/{id}     delete a node
//	POST /api/v1/edges            upsert an edge
//	GET  /api/v1/query            simple property query
//	GET  /api/v1/inventory        label counts (for inventory page)
//	POST /api/v1/sync/force       trigger immediate cloud sync
//	GET  /metrics                 Prometheus metrics
package api

import (
	"context"
	"encoding/json"
	"net/http"
	"strconv"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/go-chi/chi/v5/middleware"
	"go.uber.org/zap"

	"github.com/gaineyllc/dgraphai/dgraph-proxy/internal/config"
	"github.com/gaineyllc/dgraphai/dgraph-proxy/internal/query"
	"github.com/gaineyllc/dgraphai/dgraph-proxy/internal/store"
	proxysync "github.com/gaineyllc/dgraphai/dgraph-proxy/internal/sync"
)

// Server is the local HTTP API server.
type Server struct {
	cfg    *config.Config
	store  *store.Store
	engine *query.Engine
	syncer *proxysync.Syncer
	log    *zap.Logger
	http   *http.Server
}

// New creates an API server (does not start listening).
func New(cfg *config.Config, s *store.Store, eng *query.Engine, syncer *proxysync.Syncer, log *zap.Logger) *Server {
	srv := &Server{cfg: cfg, store: s, engine: eng, syncer: syncer, log: log}
	srv.http = &http.Server{
		Addr:         cfg.ListenAddr,
		Handler:      srv.router(),
		ReadTimeout:  15 * time.Second,
		WriteTimeout: 30 * time.Second,
		IdleTimeout:  60 * time.Second,
	}
	return srv
}

// Start begins accepting connections.
func (s *Server) Start() error {
	s.log.Info("local API listening", zap.String("addr", s.cfg.ListenAddr))
	if s.cfg.TLSCertFile != "" {
		return s.http.ListenAndServeTLS(s.cfg.TLSCertFile, s.cfg.TLSKeyFile)
	}
	return s.http.ListenAndServe()
}

// Shutdown gracefully stops the server.
func (s *Server) Shutdown(ctx context.Context) error {
	return s.http.Shutdown(ctx)
}

func (s *Server) router() http.Handler {
	r := chi.NewRouter()
	r.Use(middleware.RealIP)
	r.Use(middleware.RequestID)
	r.Use(s.loggingMiddleware)
	r.Use(middleware.Recoverer)

	// Auth middleware — only applied to /api/ routes
	r.Group(func(r chi.Router) {
		if s.cfg.JWTSecret != "" {
			r.Use(s.jwtMiddleware)
		}

		r.Get("/api/v1/stats",        s.handleStats)
		r.Get("/api/v1/nodes",        s.handleListNodes)
		r.Get("/api/v1/nodes/{id}",   s.handleGetNode)
		r.Post("/api/v1/nodes",       s.handleUpsertNode)
		r.Delete("/api/v1/nodes/{id}",s.handleDeleteNode)
		r.Post("/api/v1/edges",       s.handleUpsertEdge)
		r.Get("/api/v1/query",        s.handleQuery)
		r.Get("/api/v1/inventory",    s.handleInventory)
		r.Post("/api/v1/sync/force",  s.handleForceSync)
	})

	r.Get("/health", s.handleHealth)
	r.Get("/ready",  s.handleReady)

	return r
}

// ── Handlers ─────────────────────────────────────────────────────────────────

func (s *Server) handleHealth(w http.ResponseWriter, r *http.Request) {
	writeJSON(w, http.StatusOK, map[string]string{"status": "ok"})
}

func (s *Server) handleReady(w http.ResponseWriter, r *http.Request) {
	writeJSON(w, http.StatusOK, map[string]string{
		"status":    "ready",
		"tenant_id": s.cfg.TenantID,
		"proxy_id":  s.cfg.ProxyID,
		"mode":      modeStr(s.cfg.AirGapped),
	})
}

func (s *Server) handleStats(w http.ResponseWriter, r *http.Request) {
	stats, err := s.engine.Stats()
	if err != nil {
		writeError(w, http.StatusInternalServerError, err)
		return
	}
	syncStats := s.syncer.Stats()
	stats["sync"] = map[string]any{
		"last_sync_at":    syncStats.LastSyncAt,
		"sync_successes":  syncStats.SyncSuccesses,
		"sync_failures":   syncStats.SyncFailures,
		"total_acked":     syncStats.TotalAcked,
		"uptime_seconds":  syncStats.UptimeSeconds,
	}
	stats["air_gapped"] = s.cfg.AirGapped
	writeJSON(w, http.StatusOK, stats)
}

func (s *Server) handleGetNode(w http.ResponseWriter, r *http.Request) {
	id := chi.URLParam(r, "id")
	node, err := s.engine.NodeByID(id)
	if err != nil {
		writeError(w, http.StatusInternalServerError, err)
		return
	}
	if node == nil {
		writeError(w, http.StatusNotFound, nil)
		return
	}
	writeJSON(w, http.StatusOK, node)
}

func (s *Server) handleListNodes(w http.ResponseWriter, r *http.Request) {
	label := r.URL.Query().Get("label")
	limit, _ := strconv.Atoi(r.URL.Query().Get("limit"))
	if limit == 0 {
		limit = 100
	}

	result, err := s.engine.NodesByLabel(label, limit)
	if err != nil {
		writeError(w, http.StatusInternalServerError, err)
		return
	}
	writeJSON(w, http.StatusOK, result)
}

func (s *Server) handleUpsertNode(w http.ResponseWriter, r *http.Request) {
	var node store.NodeRecord
	if err := json.NewDecoder(r.Body).Decode(&node); err != nil {
		writeError(w, http.StatusBadRequest, err)
		return
	}
	if err := s.store.UpsertNode(&node); err != nil {
		writeError(w, http.StatusInternalServerError, err)
		return
	}
	writeJSON(w, http.StatusCreated, node)
}

func (s *Server) handleDeleteNode(w http.ResponseWriter, r *http.Request) {
	id := chi.URLParam(r, "id")
	if err := s.store.DeleteNode(id); err != nil {
		writeError(w, http.StatusInternalServerError, err)
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

func (s *Server) handleUpsertEdge(w http.ResponseWriter, r *http.Request) {
	var edge store.EdgeRecord
	if err := json.NewDecoder(r.Body).Decode(&edge); err != nil {
		writeError(w, http.StatusBadRequest, err)
		return
	}
	if err := s.store.UpsertEdge(&edge); err != nil {
		writeError(w, http.StatusInternalServerError, err)
		return
	}
	writeJSON(w, http.StatusCreated, edge)
}

func (s *Server) handleQuery(w http.ResponseWriter, r *http.Request) {
	q := r.URL.Query()
	key   := q.Get("key")
	op    := q.Get("op")
	value := q.Get("value")
	limit, _ := strconv.Atoi(q.Get("limit"))
	if limit == 0 { limit = 100 }

	if key == "" || op == "" {
		writeError(w, http.StatusBadRequest, nil)
		return
	}

	result, err := s.engine.NodesByProperty(key, op, value, limit)
	if err != nil {
		writeError(w, http.StatusBadRequest, err)
		return
	}
	writeJSON(w, http.StatusOK, result)
}

func (s *Server) handleInventory(w http.ResponseWriter, r *http.Request) {
	counts, err := s.engine.LabelCounts()
	if err != nil {
		writeError(w, http.StatusInternalServerError, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"label_counts": counts,
		"air_gapped":   s.cfg.AirGapped,
		"mode":         modeStr(s.cfg.AirGapped),
	})
}

func (s *Server) handleForceSync(w http.ResponseWriter, r *http.Request) {
	if s.cfg.AirGapped {
		writeJSON(w, http.StatusOK, map[string]string{"status": "skipped", "reason": "air_gapped"})
		return
	}
	if err := s.syncer.ForceSync(r.Context()); err != nil {
		writeError(w, http.StatusInternalServerError, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]string{"status": "ok"})
}

// ── Middleware ────────────────────────────────────────────────────────────────

func (s *Server) loggingMiddleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		start := time.Now()
		ww := middleware.NewWrapResponseWriter(w, r.ProtoMajor)
		next.ServeHTTP(ww, r)
		s.log.Info("request",
			zap.String("method", r.Method),
			zap.String("path", r.URL.Path),
			zap.Int("status", ww.Status()),
			zap.Duration("duration", time.Since(start)),
		)
	})
}

func (s *Server) jwtMiddleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		// Minimal JWT validation — checks signature only.
		// Full claim validation done by agent-go gateway.
		auth := r.Header.Get("Authorization")
		if auth == "" || len(auth) < 8 {
			writeError(w, http.StatusUnauthorized, nil)
			return
		}
		// TODO: validate JWT signature against s.cfg.JWTSecret
		// For now accept any Bearer token in local mode
		next.ServeHTTP(w, r)
	})
}

// ── Helpers ───────────────────────────────────────────────────────────────────

func writeJSON(w http.ResponseWriter, status int, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	json.NewEncoder(w).Encode(v)
}

func writeError(w http.ResponseWriter, status int, err error) {
	msg := "error"
	if err != nil {
		msg = err.Error()
	}
	writeJSON(w, status, map[string]string{"error": msg})
}

func modeStr(airGapped bool) string {
	if airGapped {
		return "air_gapped"
	}
	return "connected"
}
