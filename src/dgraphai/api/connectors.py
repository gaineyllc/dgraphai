"""Connector registry and management API."""
from __future__ import annotations
from typing import Any
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from src.dgraphai.auth.oidc import get_auth_context, AuthContext
from src.dgraphai.connectors.sdk import list_connectors, get_connector

router = APIRouter(prefix="/api/connectors", tags=["connectors"])


@router.get("/types")
async def list_connector_types(
    auth: AuthContext = Depends(get_auth_context),
) -> list[dict[str, Any]]:
    """List all available connector types with their config schemas."""
    return [
        {
            "id":           m.id,
            "name":         m.name,
            "description":  m.description,
            "version":      m.version,
            "author":       m.author,
            "icon_url":     m.icon_url,
            "config_schema": m.config_schema,
            "capabilities": m.capabilities,
        }
        for m in list_connectors()
    ]


class TestConnectionRequest(BaseModel):
    connector_type: str
    config:         dict[str, Any]


@router.post("/test")
async def test_connection(
    req:  TestConnectionRequest,
    auth: AuthContext = Depends(get_auth_context),
) -> dict[str, Any]:
    """
    Test a connector configuration before saving it.
    Returns {success, message}.
    Credentials are used only for the test and not persisted.
    """
    cls = get_connector(req.connector_type)
    if not cls:
        raise HTTPException(status_code=400, detail=f"Unknown connector type: {req.connector_type!r}")

    connector = cls(connector_id="test", config=req.config)
    return await connector.test_connection()
