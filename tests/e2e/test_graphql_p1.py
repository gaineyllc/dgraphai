"""
E2E tests — GraphQL API (P1).
Tests: introspection, inventory query, raw Cypher, stats.
"""
import pytest
from httpx import AsyncClient

pytestmark = [pytest.mark.e2e, pytest.mark.p1]

GQL = "/graphql"


async def gql(client: AsyncClient, query: str, variables: dict = None) -> dict:
    r = await client.post(GQL, json={"query": query, "variables": variables or {}})
    assert r.status_code == 200, f"GraphQL HTTP error: {r.status_code} {r.text[:200]}"
    return r.json()


@pytest.mark.asyncio
async def test_graphql_introspection(client: AsyncClient):
    data = await gql(client, "{ __schema { queryType { name } } }")
    assert "errors" not in data
    assert data["data"]["__schema"]["queryType"]["name"] == "Query"


@pytest.mark.asyncio
async def test_graphql_inventory_query(client: AsyncClient):
    data = await gql(client, """
    {
      inventory {
        name
        categories {
          id
          name
          color
          icon
          cypher
          queryUrl
        }
      }
    }
    """)
    assert "errors" not in data, f"GraphQL errors: {data.get('errors')}"
    groups = data["data"]["inventory"]
    assert len(groups) > 0
    # Flatten all categories
    all_cats = [c for g in groups for c in g["categories"]]
    assert len(all_cats) > 0
    cat_ids = [c["id"] for c in all_cats]
    assert "video" in cat_ids
    assert "pii"   in cat_ids


@pytest.mark.asyncio
async def test_graphql_stats_query(client: AsyncClient):
    data = await gql(client, """
    {
      stats {
        totalFiles
        totalNodes
      }
    }
    """)
    assert "errors" not in data
    stats = data["data"]["stats"]
    assert "totalFiles" in stats
    assert "totalNodes" in stats
    assert stats["totalNodes"] >= 0


@pytest.mark.asyncio
async def test_graphql_connector_types(client: AsyncClient):
    data = await gql(client, """
    {
      connectorTypes {
        id
        name
        icon
        color
      }
    }
    """)
    assert "errors" not in data
    types = data["data"]["connectorTypes"]
    ids = [t["id"] for t in types]
    assert "aws-s3"     in ids
    assert "smb"        in ids
    assert "sharepoint" in ids


@pytest.mark.asyncio
async def test_graphql_graph_query(client: AsyncClient):
    data = await gql(client, """
    {
      graphQuery(cypher: "MATCH (f:File) WHERE f.tenant_id = $tid RETURN f LIMIT 5") {
        count
        cypher
        queryUrl
      }
    }
    """)
    assert "errors" not in data
    result = data["data"]["graphQuery"]
    assert "count"    in result
    assert "cypher"   in result
    assert "queryUrl" in result
    assert "/query" in result["queryUrl"]
