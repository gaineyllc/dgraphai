"""
Graph node deduplication for dgraph.ai.

The problem:
  Multiple agents may scan the same file (e.g. a NAS share mounted on 3 machines).
  Without deduplication, the graph gets 3 File nodes for the same content.

The solution:
  SHA-256 hash is the deduplication key.
  A single File node in the graph represents unique content.
  Every path that leads to that content is stored in a paths[] array attribute.

Dedup rules:
  1. PRIMARY KEY = sha256 hash (content-addressable identity)
     - Same hash = same file content = same node
     - Different hash always = different node
  2. SECONDARY KEY = (connector_type, host, share, relative_path) tuple
     - Used when sha256 is not available (large files skipped, binary, etc.)
     - Falls back to path-based identity
  3. paths[] array:
     - Every connector path that can reach this content
     - Format: protocol://host/share/path  (e.g. smb://192.168.1.10/Media/movie.mkv)
     - Updated on each scan — stale paths removed after TTL (default: 7 days)
  4. agent_ids[] array:
     - All agent IDs that have scanned this node
     - Used for load-balanced access routing in fleet mode

Cypher merge strategy:
  MERGE (f:File {sha256: $sha256, tenant_id: $tid})
  ON CREATE SET f = $props, f.paths = [$path], f.agent_ids = [$agent_id]
  ON MATCH SET
    f.paths = CASE
      WHEN $path IN f.paths THEN f.paths
      ELSE f.paths + [$path]
    END,
    f.agent_ids = CASE
      WHEN $agent_id IN coalesce(f.agent_ids, []) THEN f.agent_ids
      ELSE coalesce(f.agent_ids, []) + [$agent_id]
    END,
    f.last_seen_at = $now,
    f.name = $name,
    f.size = $size,
    f.modified_at = $modified_at,
    f.file_category = $file_category,
    f.mime_type = $mime_type,
    f.extension = $extension

For files without sha256 (too large or binary):
  MERGE (f:File {id: $path_id, tenant_id: $tid})
  where path_id = sha256(connector_id + ':' + path)
"""
from __future__ import annotations

import hashlib
from typing import Any


def make_node_id(props: dict[str, Any]) -> str:
    """
    Generate the canonical node ID for a file.

    Priority:
      1. sha256 hash (content-addressable — best dedup)
      2. Deterministic hash of (connector_id, path) — path-based fallback
    """
    sha = props.get("sha256", "")
    if sha and len(sha) == 64:  # valid SHA-256
        return f"sha256:{sha}"

    # Fallback: hash of connector + path
    connector_id = props.get("connector_id", "")
    path         = props.get("path", "")
    key          = f"{connector_id}:{path}"
    return "path:" + hashlib.sha256(key.encode()).hexdigest()


def make_canonical_path(props: dict[str, Any]) -> str:
    """
    Build a canonical path string for the paths[] array.
    Format: protocol://host/share/path  or  local://hostname/path
    """
    protocol = props.get("protocol", "local")
    host     = props.get("host", "")
    share    = props.get("share", "")
    path     = props.get("path", "")

    if protocol == "smb" and host:
        return f"smb://{host}/{share}{path}"
    if protocol == "nfs" and host:
        return f"nfs://{host}{path}"
    if protocol in ("s3", "aws-s3"):
        bucket = props.get("bucket", "")
        key    = props.get("key", path)
        return f"s3://{bucket}/{key}"
    if protocol in ("azure-blob", "azure"):
        account   = props.get("account_name", "")
        container = props.get("container", "")
        return f"azure://{account}/{container}{path}"

    hostname = props.get("hostname", host or "localhost")
    return f"local://{hostname}{path}"


def upsert_cypher(props: dict[str, Any], agent_id: str, tenant_id: str) -> tuple[str, dict]:
    """
    Generate the Cypher MERGE statement for deduplication upsert.
    Returns (cypher, params).

    The returned Cypher merges on content identity (sha256 or path hash),
    then appends this path to paths[] and this agent to agent_ids[] if new.
    """
    node_id   = make_node_id(props)
    canon_path = make_canonical_path(props)

    # Scalar properties to set on CREATE (won't overwrite on MATCH)
    create_props = {
        "node_id":      node_id,
        "tenant_id":    tenant_id,
        "sha256":       props.get("sha256", ""),
        "name":         props.get("name", ""),
        "extension":    props.get("extension", ""),
        "file_category":props.get("file_category", "unknown"),
        "mime_type":    props.get("mime_type", ""),
        "protocol":     props.get("protocol", "local"),
        "connector_id": props.get("connector_id", ""),
    }

    # Properties updated on every MATCH
    update_props = {
        "size":         props.get("size", 0),
        "modified_at":  props.get("modified_at", ""),
        "indexed_at":   props.get("indexed_at", ""),
        "file_category":props.get("file_category", "unknown"),
        "mime_type":    props.get("mime_type", ""),
    }

    cypher = """
MERGE (f:File {id: $node_id, tenant_id: $tenant_id})
ON CREATE SET
  f = $create_props,
  f.paths     = [$canon_path],
  f.agent_ids = [$agent_id],
  f.created_at = datetime()
ON MATCH SET
  f += $update_props,
  f.last_seen_at = datetime(),
  f.paths = CASE
    WHEN $canon_path IN coalesce(f.paths, []) THEN f.paths
    ELSE coalesce(f.paths, []) + [$canon_path]
  END,
  f.agent_ids = CASE
    WHEN $agent_id IN coalesce(f.agent_ids, []) THEN f.agent_ids
    ELSE coalesce(f.agent_ids, []) + [$agent_id]
  END
RETURN f.id AS id, size(f.paths) AS path_count
""".strip()

    params = {
        "node_id":      node_id,
        "tenant_id":    tenant_id,
        "create_props": create_props,
        "update_props": update_props,
        "canon_path":   canon_path,
        "agent_id":     agent_id,
    }

    return cypher, params


def prune_stale_paths_cypher(tenant_id: str, ttl_days: int = 7) -> tuple[str, dict]:
    """
    Remove paths that haven't been seen in ttl_days.
    Run periodically (e.g. weekly) as a maintenance task.
    """
    cypher = """
MATCH (f:File {tenant_id: $tid})
WHERE f.path_updated_at IS NOT NULL
  AND datetime() > f.path_updated_at + duration({days: $ttl})
SET f.paths = [p IN f.paths WHERE p <> f.stale_path]
RETURN count(f) AS pruned
""".strip()
    return cypher, {"tid": tenant_id, "ttl": ttl_days}


def bulk_upsert_query(nodes: list[dict], agent_id: str, tenant_id: str) -> tuple[str, dict]:
    """
    Batch upsert using UNWIND for efficiency.
    Called by the scanner/sync API endpoint.
    """
    rows = []
    for node_props in nodes:
        props = node_props.get("props", node_props)
        rows.append({
            "node_id":      make_node_id(props),
            "canon_path":   make_canonical_path(props),
            "sha256":       props.get("sha256", ""),
            "name":         props.get("name", ""),
            "extension":    props.get("extension", ""),
            "file_category":props.get("file_category", "unknown"),
            "mime_type":    props.get("mime_type", ""),
            "size":         props.get("size", 0),
            "modified_at":  props.get("modified_at", ""),
            "protocol":     props.get("protocol", "local"),
            "connector_id": props.get("connector_id", ""),
        })

    cypher = """
UNWIND $rows AS row
MERGE (f:File {id: row.node_id, tenant_id: $tid})
ON CREATE SET
  f = row,
  f.tenant_id  = $tid,
  f.paths      = [row.canon_path],
  f.agent_ids  = [$agent_id],
  f.created_at = datetime()
ON MATCH SET
  f.size         = row.size,
  f.modified_at  = row.modified_at,
  f.file_category= row.file_category,
  f.mime_type    = row.mime_type,
  f.last_seen_at = datetime(),
  f.paths = CASE
    WHEN row.canon_path IN coalesce(f.paths, []) THEN f.paths
    ELSE coalesce(f.paths, []) + [row.canon_path]
  END,
  f.agent_ids = CASE
    WHEN $agent_id IN coalesce(f.agent_ids, []) THEN f.agent_ids
    ELSE coalesce(f.agent_ids, []) + [$agent_id]
  END
RETURN count(f) AS merged
""".strip()

    return cypher, {"rows": rows, "tid": tenant_id, "agent_id": agent_id}
