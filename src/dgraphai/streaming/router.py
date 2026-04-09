"""
Data stream source router.

When a training job requests a dataset, this router selects the optimal
scanner agent to stream from based on:
  1. Data availability — which agents have indexed the relevant data
  2. Network proximity — agent-reported latency to common cloud regions
  3. Bandwidth capacity — available throughput from heartbeat stats
  4. Fallback chain — next-best source if primary is unavailable

This implements a simplified version of data gravity-aware routing.
No anycast/BGP required — pure application-level routing based on
agent metadata.

Agent topology metadata (registered at agent startup):
  region:          AWS/GCP/Azure region slug or "on-prem"
  datacenter:      Datacenter name/location string
  latency_matrix:  {region: avg_rtt_ms} — measured to cloud regions
  bandwidth_mbps:  Measured upload bandwidth

Example:
  Training job in us-east-1 requests file data tagged "env:production"
  Router finds 3 agents with that data:
    - Agent A: on-prem NYC, latency to us-east-1 = 12ms, bw = 1000 Mbps
    - Agent B: on-prem London, latency to us-east-1 = 85ms, bw = 500 Mbps
    - Agent C: AWS eu-west-1, latency to us-east-1 = 90ms, bw = 10000 Mbps
  → Agent A selected (lowest latency * bandwidth score)
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentTopology:
    """Network topology metadata for a scanner agent."""
    agent_id:       str
    region:         str = "unknown"
    datacenter:     str = "unknown"
    latency_matrix: dict[str, float] = field(default_factory=dict)
    # {"us-east-1": 12.5, "eu-west-1": 85.0, "ap-southeast-1": 220.0}
    bandwidth_mbps: float = 100.0
    is_online:      bool = True
    indexed_connectors: list[str] = field(default_factory=list)
    # connector IDs indexed by this agent

    def latency_to(self, region: str) -> float:
        """Estimated RTT to a cloud region. Returns 999 if unknown."""
        if self.region == region:
            return 1.0  # same region = ~1ms
        return self.latency_matrix.get(region, 999.0)

    def routing_score(self, target_region: str) -> float:
        """
        Lower is better.
        Score = latency_ms / log2(bandwidth_mbps + 1)
        Penalizes high latency heavily; rewards bandwidth logarithmically.
        """
        latency  = self.latency_to(target_region)
        bw_bonus = math.log2(self.bandwidth_mbps + 1)
        return latency / max(bw_bonus, 1.0)


class StreamRouter:
    """
    Routes data stream requests to the optimal scanner agent.
    Maintains an in-memory topology map updated from agent heartbeats.
    """

    def __init__(self) -> None:
        self._topology: dict[str, AgentTopology] = {}

    def register_agent(self, topology: AgentTopology) -> None:
        self._topology[topology.agent_id] = topology

    def update_from_heartbeat(self, agent_id: str, health: dict[str, Any]) -> None:
        """Update agent topology from a heartbeat payload."""
        topo = self._topology.get(agent_id)
        if not topo:
            return
        topo.is_online      = True
        topo.bandwidth_mbps = health.get("bandwidth_mbps", topo.bandwidth_mbps)
        latency             = health.get("latency_matrix")
        if latency:
            topo.latency_matrix.update(latency)

    def mark_offline(self, agent_id: str) -> None:
        topo = self._topology.get(agent_id)
        if topo:
            topo.is_online = False

    def select_source(
        self,
        connector_ids: list[str],
        requester_region: str,
        exclude_agents: list[str] | None = None,
    ) -> AgentTopology | None:
        """
        Select the best agent to stream data from.

        Args:
            connector_ids:     Which connectors contain the requested data
            requester_region:  Cloud region of the requesting training job
                               (e.g. "us-east-1", "eu-west-1", "gcp-us-central1")
            exclude_agents:    Agents to skip (for fallback routing)

        Returns:
            Best AgentTopology, or None if no suitable agent found.
        """
        exclude = set(exclude_agents or [])
        candidates: list[AgentTopology] = []

        for topo in self._topology.values():
            if not topo.is_online:
                continue
            if topo.agent_id in exclude:
                continue
            # Check if agent has any of the requested connectors
            if connector_ids and not any(
                c in topo.indexed_connectors for c in connector_ids
            ):
                continue
            candidates.append(topo)

        if not candidates:
            return None

        # Sort by routing score (lower = better)
        candidates.sort(key=lambda t: t.routing_score(requester_region))
        return candidates[0]

    def ranked_sources(
        self,
        connector_ids: list[str],
        requester_region: str,
    ) -> list[tuple[AgentTopology, float]]:
        """
        Return all viable sources ranked by routing score.
        Used to build fallback chains.
        """
        results = []
        for topo in self._topology.values():
            if not topo.is_online:
                continue
            if connector_ids and not any(
                c in topo.indexed_connectors for c in connector_ids
            ):
                continue
            score = topo.routing_score(requester_region)
            results.append((topo, score))
        results.sort(key=lambda x: x[1])
        return results


# Application singleton
_router = StreamRouter()


def get_stream_router() -> StreamRouter:
    return _router
