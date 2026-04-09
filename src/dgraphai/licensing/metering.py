"""
Usage metering — tracks node counts by type and enrichment status.

Node types are grouped into billing tiers:

  Tier 1 — Standard (raw metadata only, no AI enrichment possible):
    Directory, Tag, Collection, Event, Vendor, License, Topic
    Rate: $0.10 / 1,000 nodes / month

  Tier 2 — Enrichable (raw metadata extracted, AI enrichment available):
    File (not enriched), Application, Dependency, Certificate, FaceCluster
    Rate: $0.40 / 1,000 nodes / month

  Tier 3 — AI Enriched (LLM/vision/code/binary analysis completed):
    File (with summary IS NOT NULL), Person (face recognition)
    Rate: $1.20 / 1,000 nodes / month

  Tier 4 — Relationship Intelligence (graph edges computed):
    Every 10,000 relationships (SIMILAR_TO, MENTIONS, MATCHED_TO, etc.)
    Rate: $2.00 / 10,000 relationships / month

  Tier 5 — Identity (face clusters matched to named Person nodes):
    Person (known=true)
    Rate: $5.00 / 1,000 identified people / month

This mirrors how compute is actually consumed:
  - Raw indexing: cheap (filesystem walk + metadata)
  - AI enrichment: expensive (GPU/LLM time per node)
  - Relationship inference: most expensive (cross-node reasoning)

Usage is snapshotted daily. Billing is based on the peak usage
within the billing period (watermark model, like Snowflake).
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


# ── Pricing ───────────────────────────────────────────────────────────────────

# Tier definitions — node types and their billing category
TIER_STANDARD    = "standard"    # $0.10 / 1K
TIER_ENRICHABLE  = "enrichable"  # $0.40 / 1K
TIER_AI_ENRICHED = "ai_enriched" # $1.20 / 1K
TIER_IDENTITY    = "identity"    # $5.00 / 1K identified people
TIER_GRAPH_EDGES = "graph_edges" # $2.00 / 10K relationships

# Rate per 1,000 units (USD)
TIER_RATES: dict[str, float] = {
    TIER_STANDARD:    0.10,
    TIER_ENRICHABLE:  0.40,
    TIER_AI_ENRICHED: 1.20,
    TIER_IDENTITY:    5.00,
    TIER_GRAPH_EDGES: 0.20,   # per 1K relationships (= $2/10K)
}

# Node type → base tier (before enrichment status)
NODE_TYPE_TIER: dict[str, str] = {
    # Always standard (no AI enrichment path)
    "Directory":    TIER_STANDARD,
    "Tag":          TIER_STANDARD,
    "Collection":   TIER_STANDARD,
    "Event":        TIER_STANDARD,
    "Vendor":       TIER_STANDARD,
    "License":      TIER_STANDARD,
    "Topic":        TIER_STANDARD,
    "Organization": TIER_STANDARD,

    # Enrichable — split into two sub-tiers based on enrichment status
    "File":         TIER_ENRICHABLE,     # overridden to TIER_AI_ENRICHED if summary IS NOT NULL
    "Application":  TIER_ENRICHABLE,
    "Dependency":   TIER_ENRICHABLE,
    "Certificate":  TIER_ENRICHABLE,
    "FaceCluster":  TIER_ENRICHABLE,     # upgraded when SAME_PERSON_AS resolved
    "Binary":       TIER_ENRICHABLE,
    "MediaItem":    TIER_ENRICHABLE,
    "Version":      TIER_STANDARD,
    "Product":      TIER_STANDARD,

    # Always AI Enriched tier
    "Person":       TIER_IDENTITY,       # split: known=false → enrichable, known=true → identity
    "Vulnerability":TIER_STANDARD,       # just CVE data, no per-tenant AI
    "Location":     TIER_STANDARD,
}

# Relationship types billed at TIER_GRAPH_EDGES
BILLED_RELATIONSHIP_TYPES = {
    "SIMILAR_TO",       # AI-computed semantic similarity
    "MENTIONS",         # entity extraction
    "CONTAINS_FACE",    # face recognition
    "SAME_PERSON_AS",   # identity resolution
    "MATCHED_TO",       # media matching
    "DEPICTS",          # vision model
    "OCCURRED_DURING",  # temporal inference
}

# Relationship types NOT billed (structural, cheap to compute)
FREE_RELATIONSHIP_TYPES = {
    "CHILD_OF", "DUPLICATE_OF", "PART_OF", "REFERENCES",
    "TAGGED_WITH", "LOCATED_AT", "IS_APPLICATION", "IS_BINARY",
    "MADE_BY", "IS_VERSION_OF", "DEPENDS_ON", "LICENSED_UNDER",
    "HAS_VULNERABILITY", "SIGNED_BY", "OWNS", "HAS_VERSION",
    "SUPERSEDES", "WITHIN",
}


@dataclass
class UsageSnapshot:
    """Point-in-time usage measurement for a single tenant."""
    tenant_id:         str
    snapshot_at:       datetime

    # Node counts by billing tier
    standard_nodes:    int = 0     # Directory, Tag, Collection, etc.
    enrichable_nodes:  int = 0     # Files/apps without AI enrichment
    ai_enriched_nodes: int = 0     # Files/apps with AI summary
    identified_people: int = 0     # Person nodes where known=true
    unknown_people:    int = 0     # FaceCluster/Person not yet identified

    # Relationship counts
    billed_relationships: int = 0  # SIMILAR_TO, MENTIONS, etc.
    free_relationships:   int = 0  # structural edges

    # Per-node-type breakdown
    node_counts: dict[str, int] = field(default_factory=dict)

    # Enrichment breakdown for File nodes
    files_raw:      int = 0   # file_category set, no summary
    files_enriched: int = 0   # summary IS NOT NULL
    files_vision:   int = 0   # scene_type IS NOT NULL (LLaVA)
    files_code:     int = 0   # code_quality IS NOT NULL
    files_binary:   int = 0   # risk_assessment IS NOT NULL

    @property
    def total_nodes(self) -> int:
        return (self.standard_nodes + self.enrichable_nodes +
                self.ai_enriched_nodes + self.identified_people + self.unknown_people)

    def compute_monthly_cost(self, plan: "BillingPlan") -> "CostBreakdown":
        """Compute estimated monthly cost for this snapshot."""
        return CostBreakdown.from_snapshot(self, plan)


@dataclass
class CostBreakdown:
    """Itemized cost breakdown for a usage snapshot."""
    standard_cost:    float = 0.0
    enrichable_cost:  float = 0.0
    ai_enriched_cost: float = 0.0
    identity_cost:    float = 0.0
    graph_edge_cost:  float = 0.0
    platform_fee:     float = 0.0   # base monthly fee from plan

    discount_pct:     float = 0.0
    discount_reason:  str   = ""

    @property
    def subtotal(self) -> float:
        return (self.standard_cost + self.enrichable_cost +
                self.ai_enriched_cost + self.identity_cost +
                self.graph_edge_cost + self.platform_fee)

    @property
    def total(self) -> float:
        return self.subtotal * (1 - self.discount_pct / 100)

    @classmethod
    def from_snapshot(cls, snap: "UsageSnapshot", plan: "BillingPlan") -> "CostBreakdown":
        def per_k(count: int, rate: float) -> float:
            return (count / 1000) * rate

        breakdown = cls(
            standard_cost    = per_k(snap.standard_nodes,    TIER_RATES[TIER_STANDARD]),
            enrichable_cost  = per_k(snap.enrichable_nodes,  TIER_RATES[TIER_ENRICHABLE]),
            ai_enriched_cost = per_k(snap.ai_enriched_nodes, TIER_RATES[TIER_AI_ENRICHED]),
            identity_cost    = per_k(snap.identified_people, TIER_RATES[TIER_IDENTITY]),
            graph_edge_cost  = per_k(snap.billed_relationships, TIER_RATES[TIER_GRAPH_EDGES]),
            platform_fee     = plan.base_monthly_fee,
            discount_pct     = plan.volume_discount_pct(snap.total_nodes),
        )
        if breakdown.discount_pct > 0:
            breakdown.discount_reason = f"Volume discount ({snap.total_nodes:,} nodes)"
        return breakdown

    def to_dict(self) -> dict:
        return {
            "line_items": [
                {"label": "Standard nodes",       "amount": round(self.standard_cost, 2),    "tier": TIER_STANDARD},
                {"label": "Enrichable nodes",      "amount": round(self.enrichable_cost, 2),  "tier": TIER_ENRICHABLE},
                {"label": "AI-enriched nodes",     "amount": round(self.ai_enriched_cost, 2), "tier": TIER_AI_ENRICHED},
                {"label": "Identified people",     "amount": round(self.identity_cost, 2),    "tier": TIER_IDENTITY},
                {"label": "Graph relationships",   "amount": round(self.graph_edge_cost, 2),  "tier": TIER_GRAPH_EDGES},
                {"label": "Platform fee",          "amount": round(self.platform_fee, 2),     "tier": "platform"},
            ],
            "subtotal":        round(self.subtotal, 2),
            "discount_pct":    self.discount_pct,
            "discount_reason": self.discount_reason,
            "total":           round(self.total, 2),
        }


@dataclass
class BillingPlan:
    """A billing plan with base fee, included allowances, and volume discounts."""
    id:               str
    name:             str
    base_monthly_fee: float

    # Included in base fee before usage charges kick in
    included_standard_nodes:    int = 0
    included_enrichable_nodes:  int = 0
    included_ai_enriched_nodes: int = 0
    included_relationships:     int = 0

    # Volume discount tiers (node count threshold → discount %)
    volume_discount_tiers: list[tuple[int, float]] = field(default_factory=list)

    # Feature gates
    features: dict[str, bool] = field(default_factory=dict)

    def volume_discount_pct(self, total_nodes: int) -> float:
        """Return the applicable volume discount percentage."""
        pct = 0.0
        for threshold, discount in sorted(self.volume_discount_tiers, reverse=True):
            if total_nodes >= threshold:
                pct = discount
                break
        return pct


# ── Standard plans ─────────────────────────────────────────────────────────────

PLANS: dict[str, BillingPlan] = {

    "starter": BillingPlan(
        id   = "starter",
        name = "Starter",
        base_monthly_fee = 0.0,
        included_standard_nodes    = 50_000,
        included_enrichable_nodes  = 10_000,
        included_ai_enriched_nodes = 0,
        included_relationships     = 100_000,
        volume_discount_tiers = [],
        features = {
            "graph_visualization":  True,
            "saved_queries":        True,
            "approval_workflows":   False,
            "ai_enrichment":        False,
            "face_recognition":     False,
            "sso_oidc":             False,
            "custom_roles":         False,
            "audit_log_stream":     False,
            "api_access":           False,
            "compliance_reports":   False,
            "ai_training_export":   False,
            "scanner_agents":       1,
        },
    ),

    "pro": BillingPlan(
        id   = "pro",
        name = "Pro",
        base_monthly_fee = 299.0,
        included_standard_nodes    = 500_000,
        included_enrichable_nodes  = 200_000,
        included_ai_enriched_nodes = 50_000,
        included_relationships     = 2_000_000,
        volume_discount_tiers = [
            (1_000_000, 10.0),   # 10% off over 1M nodes
            (5_000_000, 15.0),   # 15% off over 5M
        ],
        features = {
            "graph_visualization":  True,
            "saved_queries":        True,
            "approval_workflows":   True,
            "ai_enrichment":        True,
            "face_recognition":     False,
            "sso_oidc":             False,
            "custom_roles":         True,
            "audit_log_stream":     False,
            "api_access":           True,
            "compliance_reports":   True,
            "ai_training_export":   False,
            "scanner_agents":       3,
        },
    ),

    "business": BillingPlan(
        id   = "business",
        name = "Business",
        base_monthly_fee = 999.0,
        included_standard_nodes    = 5_000_000,
        included_enrichable_nodes  = 2_000_000,
        included_ai_enriched_nodes = 500_000,
        included_relationships     = 20_000_000,
        volume_discount_tiers = [
            (5_000_000,  15.0),
            (20_000_000, 20.0),
            (50_000_000, 25.0),
        ],
        features = {
            "graph_visualization":  True,
            "saved_queries":        True,
            "approval_workflows":   True,
            "ai_enrichment":        True,
            "face_recognition":     True,
            "sso_oidc":             True,
            "custom_roles":         True,
            "audit_log_stream":     True,
            "api_access":           True,
            "compliance_reports":   True,
            "ai_training_export":   False,
            "scanner_agents":       10,
        },
    ),

    "enterprise": BillingPlan(
        id   = "enterprise",
        name = "Enterprise",
        base_monthly_fee = 0.0,   # custom contract
        included_standard_nodes    = -1,   # unlimited
        included_enrichable_nodes  = -1,
        included_ai_enriched_nodes = -1,
        included_relationships     = -1,
        volume_discount_tiers = [
            (10_000_000,  20.0),
            (50_000_000,  30.0),
            (100_000_000, 40.0),
        ],
        features = {
            "graph_visualization":  True,
            "saved_queries":        True,
            "approval_workflows":   True,
            "ai_enrichment":        True,
            "face_recognition":     True,
            "sso_oidc":             True,
            "custom_roles":         True,
            "audit_log_stream":     True,
            "api_access":           True,
            "compliance_reports":   True,
            "ai_training_export":   True,
            "scanner_agents":       -1,    # unlimited
        },
    ),
}


def get_plan(plan_id: str) -> BillingPlan:
    return PLANS.get(plan_id, PLANS["starter"])
