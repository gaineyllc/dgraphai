"""
Tests for enterprise sales blocker systems:
  SCIM 2.0, SAML 2.0, Settings/Stripe, Observability, Reliable Webhooks
"""
import pytest
import hashlib
import hmac
import json
import uuid
from unittest.mock import MagicMock, AsyncMock, patch

pytestmark = pytest.mark.unit


# ── SCIM ───────────────────────────────────────────────────────────────────────

class TestSCIM:
    def test_scim_routes_defined(self):
        from src.dgraphai.auth.scim import router, mgmt_router
        paths = {r.path for r in router.routes}
        assert any("Users" in p for p in paths)
        assert any("Groups" in p for p in paths)
        assert any("ServiceProviderConfig" in p for p in paths)

    def test_user_to_scim_format(self):
        from src.dgraphai.auth.scim import _user_to_scim
        user = MagicMock()
        user.id          = uuid.uuid4()
        user.email       = "alice@example.com"
        user.display_name = "Alice Smith"
        user.name        = "Alice Smith"
        user.external_id = "ext123"
        user.is_active   = True

        result = _user_to_scim(user, "tenant-abc")
        assert result["schemas"] == ["urn:ietf:params:scim:schemas:core:2.0:User"]
        assert result["userName"] == "alice@example.com"
        assert result["active"]   is True
        assert result["emails"][0]["value"] == "alice@example.com"
        assert "Users" in result["meta"]["location"]

    def test_extract_email_from_username(self):
        from src.dgraphai.auth.scim import _extract_email
        assert _extract_email({"userName": "bob@example.com"}) == "bob@example.com"

    def test_extract_email_from_emails_array(self):
        from src.dgraphai.auth.scim import _extract_email
        body = {"emails": [{"value": "carol@example.com", "type": "work"}]}
        assert _extract_email(body) == "carol@example.com"

    def test_extract_email_empty(self):
        from src.dgraphai.auth.scim import _extract_email
        assert _extract_email({}) == ""

    def test_extract_name_formatted(self):
        from src.dgraphai.auth.scim import _extract_name
        assert _extract_name({"name": {"formatted": "Dave Jones"}}) == "Dave Jones"

    def test_extract_name_given_family(self):
        from src.dgraphai.auth.scim import _extract_name
        assert _extract_name({"name": {"givenName": "Eve", "familyName": "Chen"}}) == "Eve Chen"

    def test_extract_role_from_groups(self):
        from src.dgraphai.auth.scim import _extract_role
        assert _extract_role({"groups": [{"display": "admin"}]}) == "admin"
        assert _extract_role({"groups": [{"display": "analyst"}]}) == "analyst"
        assert _extract_role({}) == "analyst"  # default

    def test_role_to_scim_group(self):
        from src.dgraphai.auth.scim import _role_to_scim_group
        role = MagicMock()
        role.id   = uuid.uuid4()
        role.name = "analyst"
        result = _role_to_scim_group(role, "t123")
        assert result["schemas"] == ["urn:ietf:params:scim:schemas:core:2.0:Group"]
        assert result["displayName"] == "analyst"
        assert "Groups" in result["meta"]["location"]

    def test_scim_db_model_exists(self):
        from src.dgraphai.db.models import SCIMConfig
        cols = {c.key for c in SCIMConfig.__table__.columns}
        assert {"tenant_id","token_hash","is_active","last_used_at"} <= cols


# ── SAML ───────────────────────────────────────────────────────────────────────

class TestSAML:
    def test_saml_routes_defined(self):
        from src.dgraphai.auth.saml import router
        paths = {r.path for r in router.routes}
        assert any("login"    in p for p in paths)
        assert any("acs"      in p for p in paths)
        assert any("metadata" in p for p in paths)

    def test_saml_db_model_exists(self):
        from src.dgraphai.db.models import SAMLConfig
        cols = {c.key for c in SAMLConfig.__table__.columns}
        assert {"tenant_id","idp_entity_id","idp_sso_url",
                "idp_certificate","role_mappings","is_active"} <= cols

    def test_build_saml_settings_structure(self):
        from src.dgraphai.auth.saml import _build_saml_settings
        config = MagicMock()
        config.idp_entity_id   = "https://idp.example.com"
        config.idp_sso_url     = "https://idp.example.com/sso"
        config.idp_certificate = "CERT123"

        settings = _build_saml_settings("acme", config)
        assert settings["strict"] is True
        assert settings["sp"]["entityId"].endswith("/metadata")
        assert settings["idp"]["entityId"] == "https://idp.example.com"
        assert settings["security"]["wantAssertionsSigned"] is True

    def test_map_groups_to_role(self):
        from src.dgraphai.auth.saml import _map_groups_to_role
        config = MagicMock()
        config.role_mappings = {"engineering-admins": "admin", "security-team": "analyst"}

        assert _map_groups_to_role(["engineering-admins"], config) == "admin"
        assert _map_groups_to_role(["security-team"],     config) == "analyst"
        assert _map_groups_to_role(["unknown-group"],     config) == "viewer"
        assert _map_groups_to_role([],                   config) == "viewer"

    def test_first_attr_extraction(self):
        from src.dgraphai.auth.saml import _first_attr
        attrs = {"emailaddress": ["alice@example.com"], "displayname": ["Alice"]}
        assert _first_attr(attrs, "emailaddress") == "alice@example.com"
        assert _first_attr(attrs, "missing",  "default") == "default"


# ── Settings + Stripe ──────────────────────────────────────────────────────────

class TestSettings:
    def test_settings_routes_defined(self):
        from src.dgraphai.api.settings import router
        paths = {r.path for r in router.routes}
        assert "/api/settings/tenant"        in paths
        assert "/api/settings/billing"       in paths
        assert "/api/settings/notifications" in paths
        assert "/api/settings/danger/delete-tenant" in paths

    def test_stripe_not_required_for_import(self):
        """Settings module loads fine without STRIPE_SECRET_KEY set."""
        import os
        old = os.environ.pop("STRIPE_SECRET_KEY", None)
        try:
            import importlib
            import src.dgraphai.api.settings as s
            importlib.reload(s)
        finally:
            if old: os.environ["STRIPE_SECRET_KEY"] = old

    def test_tenant_model_has_stripe_fields(self):
        from src.dgraphai.db.models import Tenant
        cols = {c.key for c in Tenant.__table__.columns}
        assert "stripe_customer_id"   in cols
        assert "subscription_status"  in cols
        assert "current_period_end"   in cols
        assert "notification_config"  in cols
        assert "timezone"             in cols

    def test_notification_settings_model(self):
        from src.dgraphai.api.settings import NotificationSettingsRequest
        req = NotificationSettingsRequest(
            email_alerts=True,
            slack_webhook="https://hooks.slack.com/xxx",
            alert_severity_threshold="critical",
        )
        assert req.email_alerts is True
        assert req.alert_severity_threshold == "critical"


# ── Observability ──────────────────────────────────────────────────────────────

class TestObservability:
    def test_metrics_module_importable(self):
        from src.dgraphai.observability.metrics import setup_metrics
        assert callable(setup_metrics)

    def test_custom_metrics_importable(self):
        from src.dgraphai.observability.custom_metrics import (
            GRAPH_QUERY_DURATION, INDEXING_JOBS, AUTH_EVENTS,
            ENRICHMENT_JOBS, CELERY_QUEUE_DEPTH, GDPR_ERASURE_JOBS,
        )
        # Must exist even if prometheus_client not installed (no-ops)
        assert GRAPH_QUERY_DURATION is not None
        assert AUTH_EVENTS is not None

    def test_noop_metrics_dont_raise(self):
        from src.dgraphai.observability.custom_metrics import AUTH_EVENTS, INDEXING_JOBS
        # Should not raise whether real prometheus or no-op
        try:
            AUTH_EVENTS.labels(event="login").inc()
            INDEXING_JOBS.labels(status="completed").inc()
        except Exception as e:
            pytest.fail(f"Metrics raised: {e}")


# ── Webhooks ───────────────────────────────────────────────────────────────────

class TestWebhooks:
    def test_webhook_routes_defined(self):
        from src.dgraphai.webhooks.outbound import webhook_router
        paths = {r.path for r in webhook_router.routes}
        assert "/api/webhooks"            in paths
        assert "/api/webhooks/{webhook_id}/test" in paths

    def test_signature_hmac_sha256(self):
        from src.dgraphai.webhooks.outbound import _sign_payload
        body   = '{"type":"test","data":{}}'
        secret = "mysecret"
        sig    = _sign_payload(body, secret)

        expected = hmac.new(
            secret.encode(), body.encode(), hashlib.sha256
        ).hexdigest()
        assert sig == expected

    def test_signature_different_per_secret(self):
        from src.dgraphai.webhooks.outbound import _sign_payload
        body = '{"type":"test"}'
        s1   = _sign_payload(body, "secret1")
        s2   = _sign_payload(body, "secret2")
        assert s1 != s2

    def test_signature_different_per_body(self):
        from src.dgraphai.webhooks.outbound import _sign_payload
        secret = "mysecret"
        s1     = _sign_payload('{"type":"a"}', secret)
        s2     = _sign_payload('{"type":"b"}', secret)
        assert s1 != s2

    def test_valid_event_types(self):
        from src.dgraphai.webhooks.outbound import VALID_EVENTS
        required = {
            "connector.scan.complete", "finding.created",
            "alert.fired", "user.provisioned", "gdpr.erasure.complete", "*",
        }
        assert required <= VALID_EVENTS

    def test_retry_delays_schedule(self):
        from src.dgraphai.webhooks.outbound import RETRY_DELAYS
        assert len(RETRY_DELAYS) == 3
        assert RETRY_DELAYS[0] == 0       # immediate first attempt
        assert RETRY_DELAYS[1] > 0        # wait before retry 2
        assert RETRY_DELAYS[2] > RETRY_DELAYS[1]  # longer wait for retry 3

    def test_webhook_db_models_exist(self):
        from src.dgraphai.db.models import WebhookEndpoint, WebhookDelivery
        ep_cols = {c.key for c in WebhookEndpoint.__table__.columns}
        dl_cols = {c.key for c in WebhookDelivery.__table__.columns}
        assert {"tenant_id","url","secret","event_types","failure_count"} <= ep_cols
        assert {"endpoint_id","event_type","attempts","delivered","status"} <= dl_cols

    def test_webhook_delivery_has_index(self):
        from src.dgraphai.db.models import WebhookDelivery
        index_names = {i.name for i in WebhookDelivery.__table__.indexes}
        assert "ix_webhook_deliveries_tenant" in index_names

    def test_dispatch_webhook_calls_celery(self):
        from src.dgraphai.webhooks import outbound
        with patch.object(outbound, "deliver_webhook_event") as mock_task:
            mock_task.apply_async = MagicMock()
            outbound.dispatch_webhook("t-123", "alert.fired", {"severity": "critical"})
            mock_task.apply_async.assert_called_once()
            args = mock_task.apply_async.call_args
            assert "t-123"       in args[1].get("args", args[0][0] if args[0] else [])
            assert "alert.fired" in str(args)
