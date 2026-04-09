"""
SharePoint / OneDrive for Business connector.
Uses Microsoft Graph API (OAuth2 app-only auth).
Config: {tenant_id, client_id, client_secret, site_url, drive_name}
"""
from __future__ import annotations
from pathlib import PurePosixPath
from typing import AsyncIterator
from .sdk import BaseConnector, ConnectorFileRecord, ConnectorManifest


class SharePointConnector(BaseConnector):
    manifest = ConnectorManifest(
        id          = "sharepoint",
        name        = "SharePoint / OneDrive",
        description = "Index files from SharePoint sites or OneDrive for Business",
        version     = "1.0.0",
        author      = "dgraph.ai",
        icon_url    = "https://dgraph.ai/icons/sharepoint.svg",
        config_schema = {
            "type": "object",
            "properties": {
                "tenant_id":     {"type": "string", "title": "Azure Tenant ID"},
                "client_id":     {"type": "string", "title": "App (client) ID"},
                "client_secret": {"type": "string", "title": "Client secret", "format": "password"},
                "site_url":      {"type": "string", "title": "SharePoint site URL",
                                  "placeholder": "https://contoso.sharepoint.com/sites/IT"},
                "drive_name":    {"type": "string", "title": "Drive/library name", "default": "Documents"},
                "path":          {"type": "string", "title": "Folder path (optional)", "default": "/"},
            },
            "required": ["tenant_id", "client_id", "client_secret", "site_url"],
        },
        capabilities = ["read", "stream"],
    )

    async def _get_token(self) -> str:
        import httpx
        tenant_id     = self.config["tenant_id"]
        client_id     = self.config["client_id"]
        client_secret = self.config["client_secret"]
        async with httpx.AsyncClient() as client:
            r = await client.post(
                f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token",
                data={
                    "grant_type":    "client_credentials",
                    "client_id":     client_id,
                    "client_secret": client_secret,
                    "scope":         "https://graph.microsoft.com/.default",
                },
                timeout=15,
            )
            r.raise_for_status()
            return r.json()["access_token"]

    async def walk(self) -> AsyncIterator[ConnectorFileRecord]:
        import httpx
        token     = await self._get_token()
        site_url  = self.config["site_url"].rstrip("/")
        drive_name = self.config.get("drive_name", "Documents")
        start_path = self.config.get("path", "/").strip("/")

        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}

        # Get site ID
        async with httpx.AsyncClient(timeout=30) as client:
            site_host = site_url.split("/")[2]
            site_path = "/" + "/".join(site_url.split("/")[3:])
            r = await client.get(
                f"https://graph.microsoft.com/v1.0/sites/{site_host}:{site_path}",
                headers=headers,
            )
            r.raise_for_status()
            site_id = r.json()["id"]

            # Get drive
            r = await client.get(
                f"https://graph.microsoft.com/v1.0/sites/{site_id}/drives",
                headers=headers,
            )
            drives = r.json().get("value", [])
            drive = next((d for d in drives if d["name"] == drive_name), None)
            if not drive:
                return
            drive_id = drive["id"]

            # Walk items
            endpoint = (
                f"https://graph.microsoft.com/v1.0/drives/{drive_id}/root:/{start_path}:/children"
                if start_path else
                f"https://graph.microsoft.com/v1.0/drives/{drive_id}/root/children"
            )
            async for item in self._paginate(client, endpoint, headers):
                is_dir = "folder" in item
                yield ConnectorFileRecord(
                    path       = item.get("parentReference", {}).get("path", "") + "/" + item["name"],
                    name       = item["name"],
                    size_bytes = item.get("size", 0),
                    modified   = _parse_ms_datetime(item.get("lastModifiedDateTime")),
                    is_dir     = is_dir,
                    suffix     = PurePosixPath(item["name"]).suffix.lower() if not is_dir else "",
                    extra      = {
                        "sharepoint_id":  item["id"],
                        "web_url":        item.get("webUrl", ""),
                        "mime_type":      item.get("file", {}).get("mimeType", ""),
                    },
                )

    async def _paginate(self, client, url, headers):
        while url:
            r = await client.get(url, headers=headers, timeout=30)
            r.raise_for_status()
            data = r.json()
            for item in data.get("value", []):
                yield item
            url = data.get("@odata.nextLink")

    async def test_connection(self):
        try:
            await self._get_token()
            return {"success": True, "message": f"Connected to {self.config.get('site_url')}"}
        except Exception as e:
            return {"success": False, "message": str(e)}


def _parse_ms_datetime(dt_str: str | None) -> float:
    if not dt_str:
        return 0.0
    from datetime import datetime, timezone
    try:
        return datetime.fromisoformat(dt_str.replace("Z", "+00:00")).timestamp()
    except Exception:
        return 0.0
