// Package fleet manages agent fleet membership and inter-agent telemetry.
//
// Fleet enables:
//   - Grouping multiple agents for load-balanced scanning of large NFS/SMB shares
//   - Bandwidth and latency mesh tests between fleet members
//   - Coordinated deduplication (same file scanned by multiple agents → one graph node)
//   - Health telemetry aggregation across all fleet members
//
// Architecture:
//   - Fleet coordinator is elected from the platform (cloud or on-prem instance)
//   - Each agent reports its fleet membership and capabilities in heartbeats
//   - The platform assigns scan shards to agents based on capacity + latency mesh
//   - Agents run ping/bandwidth tests between themselves via fleet.PeerProbe()
package fleet

import (
	"context"
	"fmt"
	"net"
	"net/http"
	"sync"
	"time"

	"go.uber.org/zap"
)

// Member represents another agent in the same fleet.
type Member struct {
	AgentID   string    `json:"agent_id"`
	Name      string    `json:"name"`
	Hostname  string    `json:"hostname"`
	OS        string    `json:"os"`
	PeerAddr  string    `json:"peer_addr"`  // host:port for inter-agent comms
	Version   string    `json:"version"`
	Capacity  int       `json:"capacity"`   // max concurrent connectors
	JoinedAt  time.Time `json:"joined_at"`
}

// ProbResult is the result of a latency/bandwidth probe to a peer.
type ProbeResult struct {
	PeerAgentID   string        `json:"peer_agent_id"`
	PeerAddr      string        `json:"peer_addr"`
	LatencyMs     float64       `json:"latency_ms"`
	BandwidthMbps float64       `json:"bandwidth_mbps"`
	Reachable     bool          `json:"reachable"`
	ProbeAt       time.Time     `json:"probe_at"`
	Error         string        `json:"error,omitempty"`
}

// FleetTelemetry is sent to the platform with each heartbeat when in a fleet.
type FleetTelemetry struct {
	FleetID     string        `json:"fleet_id"`
	AgentID     string        `json:"agent_id"`
	Members     []Member      `json:"members"`
	Probes      []ProbeResult `json:"probes"`
	IsCoord     bool          `json:"is_coordinator"`
	AssignedConnectors []string `json:"assigned_connectors"`
}

// Manager handles fleet state for this agent.
type Manager struct {
	mu        sync.RWMutex
	agentID   string
	fleetID   string
	members   []Member
	probes    []ProbeResult
	isCoord   bool
	peerPort  int
	log       *zap.Logger
	http      *http.Client
}

// New creates a fleet manager. Call JoinFleet to activate.
func New(agentID string, peerPort int, log *zap.Logger) *Manager {
	return &Manager{
		agentID:  agentID,
		peerPort: peerPort,
		log:      log,
		http:     &http.Client{Timeout: 5 * time.Second},
	}
}

// JoinFleet sets the fleet ID and member list from platform config.
func (m *Manager) JoinFleet(fleetID string, members []Member, isCoordinator bool) {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.fleetID  = fleetID
	m.members  = members
	m.isCoord  = isCoordinator
	m.log.Info("joined fleet",
		zap.String("fleet_id", fleetID),
		zap.Int("members", len(members)),
		zap.Bool("coordinator", isCoordinator),
	)
}

// InFleet returns true if this agent is currently part of a fleet.
func (m *Manager) InFleet() bool {
	m.mu.RLock()
	defer m.mu.RUnlock()
	return m.fleetID != ""
}

// ProbeAll runs latency + bandwidth tests to all fleet peers concurrently.
// Results are stored and included in the next heartbeat.
func (m *Manager) ProbeAll(ctx context.Context) []ProbeResult {
	m.mu.RLock()
	members := make([]Member, len(m.members))
	copy(members, m.members)
	agentID := m.agentID
	m.mu.RUnlock()

	if len(members) == 0 {
		return nil
	}

	type result struct {
		idx int
		res ProbeResult
	}
	results := make([]ProbeResult, 0, len(members))
	ch := make(chan result, len(members))

	for i, peer := range members {
		if peer.AgentID == agentID {
			continue // skip self
		}
		go func(idx int, p Member) {
			ch <- result{idx: idx, res: m.probePeer(ctx, p)}
		}(i, peer)
	}

	timeout := time.After(10 * time.Second)
	for i := 0; i < len(members)-1; i++ { // -1 for self
		select {
		case r := <-ch:
			results = append(results, r.res)
		case <-timeout:
			m.log.Warn("fleet probe timed out")
			break
		case <-ctx.Done():
			break
		}
	}

	m.mu.Lock()
	m.probes = results
	m.mu.Unlock()

	return results
}

// probePeer measures latency and rough bandwidth to a single peer.
func (m *Manager) probePeer(ctx context.Context, peer Member) ProbeResult {
	res := ProbeResult{
		PeerAgentID: peer.AgentID,
		PeerAddr:    peer.PeerAddr,
		ProbeAt:     time.Now(),
	}

	if peer.PeerAddr == "" {
		res.Error = "no peer address"
		return res
	}

	// ── Latency: TCP connect time ────────────────────────────────────
	start := time.Now()
	conn, err := net.DialTimeout("tcp", peer.PeerAddr, 3*time.Second)
	if err != nil {
		res.Error = err.Error()
		return res
	}
	res.LatencyMs = float64(time.Since(start).Microseconds()) / 1000.0
	res.Reachable = true
	conn.Close()

	// ── Bandwidth: GET /fleet/probe?bytes=N, measure throughput ──────
	probeURL := fmt.Sprintf("http://%s/fleet/probe?bytes=65536", peer.PeerAddr)
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, probeURL, nil)
	if err == nil {
		bwStart := time.Now()
		resp, err := m.http.Do(req)
		if err == nil {
			var n int64
			buf := make([]byte, 4096)
			for {
				nn, rerr := resp.Body.Read(buf)
				n += int64(nn)
				if rerr != nil {
					break
				}
			}
			resp.Body.Close()
			elapsed := time.Since(bwStart).Seconds()
			if elapsed > 0 {
				res.BandwidthMbps = float64(n) / elapsed / 1024 / 1024 * 8
			}
		}
	}

	return res
}

// Telemetry returns the current fleet telemetry for the heartbeat.
func (m *Manager) Telemetry() *FleetTelemetry {
	m.mu.RLock()
	defer m.mu.RUnlock()
	if m.fleetID == "" {
		return nil
	}
	probes := make([]ProbeResult, len(m.probes))
	copy(probes, m.probes)
	return &FleetTelemetry{
		FleetID: m.fleetID,
		AgentID: m.agentID,
		Members: m.members,
		Probes:  probes,
		IsCoord: m.isCoord,
	}
}

// PeerHandler returns an http.Handler for the /fleet/* endpoints.
// Other agents call these for probe tests.
func (m *Manager) PeerHandler() http.Handler {
	mux := http.NewServeMux()

	// Latency/bandwidth probe endpoint — returns N random bytes
	mux.HandleFunc("/fleet/probe", func(w http.ResponseWriter, r *http.Request) {
		bytesStr := r.URL.Query().Get("bytes")
		n := 65536 // default 64KB
		fmt.Sscanf(bytesStr, "%d", &n)
		if n > 10*1024*1024 { n = 10 * 1024 * 1024 } // cap at 10MB

		w.Header().Set("Content-Type", "application/octet-stream")
		w.Header().Set("Content-Length", fmt.Sprintf("%d", n))
		buf := make([]byte, min(n, 4096))
		remaining := n
		for remaining > 0 {
			chunk := min(remaining, len(buf))
			w.Write(buf[:chunk])
			remaining -= chunk
		}
	})

	// Health + telemetry for other fleet members
	mux.HandleFunc("/fleet/health", func(w http.ResponseWriter, r *http.Request) {
		m.mu.RLock()
		defer m.mu.RUnlock()
		fmt.Fprintf(w, `{"agent_id":%q,"fleet_id":%q,"ok":true}`, m.agentID, m.fleetID)
	})

	return mux
}

func min(a, b int) int {
	if a < b { return a }
	return b
}
