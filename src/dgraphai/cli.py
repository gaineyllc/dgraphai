"""
dgraph.ai CLI — administrative commands.
Run: uv run python -m src.dgraphai.cli <command>
"""
from __future__ import annotations
import asyncio
import sys

import click


@click.group()
def cli():
    """dgraph.ai administrative CLI."""
    pass


@cli.command("create-admin")
@click.option("--email",    required=True, help="Admin email address")
@click.option("--password", default=None,  help="Password (prompted if not given)")
@click.option("--name",     default="Admin", help="Display name")
@click.option("--company",  default="",    help="Company name")
def create_admin(email: str, password: str | None, name: str, company: str):
    """Create the first admin user and tenant."""
    if not password:
        import getpass
        password = getpass.getpass("Password: ")
        confirm  = getpass.getpass("Confirm:  ")
        if password != confirm:
            click.echo("Passwords don't match.", err=True)
            sys.exit(1)

    asyncio.run(_create_admin(email, password, name, company))


async def _create_admin(email: str, password: str, name: str, company: str):
    from src.dgraphai.db.session import create_tables, async_session
    from src.dgraphai.db.models import Tenant, User, LocalCredential, Role, RoleAssignment
    from sqlalchemy import select
    import uuid
    import bcrypt as _bcrypt
    from datetime import datetime, timezone

    class _PwdCtx:
    def hash(self, password: str) -> str:
        return _bcrypt.hashpw(password.encode()[:72], _bcrypt.gensalt(rounds=12)).decode()
    def verify(self, password: str, hashed: str) -> bool:
        try: return _bcrypt.checkpw(password.encode()[:72], hashed.encode())
        except: return False
pwd_ctx = _PwdCtx()

    await create_tables()

    async with async_session() as db:
        # Check if already exists
        existing = await db.execute(select(User).where(User.email == email))
        if existing.scalar_one_or_none():
            click.echo(f"✗ User {email} already exists.")
            return

        # Create tenant
        slug = company.lower().replace(" ", "-")[:32] or email.split("@")[0][:32]
        tenant = Tenant(name=company or name, slug=slug, plan="pro", is_active=True)
        db.add(tenant)
        await db.flush()

        # Create user
        user = User(
            tenant_id      = tenant.id,
            email          = email,
            display_name   = name,
            name           = name,
            role           = "admin",
            is_active      = True,
            email_verified = True,
        )
        db.add(user)
        await db.flush()

        # Credential
        cred = LocalCredential(
            user_id       = user.id,
            password_hash = pwd_ctx.hash(password),
        )
        db.add(cred)

        # Admin role
        from src.dgraphai.rbac.engine import assign_builtin_role
        await assign_builtin_role(user.id, tenant.id, "admin", db)

        click.echo(f"✓ Created admin user: {email}")
        click.echo(f"  Tenant: {tenant.name} ({tenant.slug})")
        click.echo(f"  Plan:   {tenant.plan}")
        click.echo(f"  Login:  {email} / [your password]")


@cli.command("migrate")
def migrate():
    """Run database migrations (alembic upgrade head)."""
    import subprocess
    result = subprocess.run(["uv", "run", "alembic", "upgrade", "head"], check=False)
    sys.exit(result.returncode)


@cli.command("generate-key")
@click.option("--type", "key_type", default="jwt", type=click.Choice(["jwt", "encryption", "scim"]))
def generate_key(key_type: str):
    """Generate a cryptographic key for use in .env."""
    import secrets, base64
    if key_type == "jwt":
        click.echo(secrets.token_hex(32))
    elif key_type == "encryption":
        click.echo(base64.b64encode(secrets.token_bytes(32)).decode())
    elif key_type == "scim":
        click.echo(f"dg_scim_{secrets.token_urlsafe(32)}")


@cli.command("health")
def health():
    """Check health of all services."""
    asyncio.run(_health())


async def _health():
    import httpx, os
    url = os.getenv("APP_URL", "http://localhost:8000")
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(f"{url}/api/health")
            data = r.json()
            status = data.get("status", "unknown")
            version = data.get("version", "?")
            icon = "✓" if status == "ok" else "⚠"
            click.echo(f"{icon} API: {status} (v{version})")
            for tid, breaker in data.get("graph_circuit_breakers", {}).items():
                click.echo(f"  Graph ({tid[:8]}…): {breaker['state']}")
    except Exception as e:
        click.echo(f"✗ API unreachable: {e}", err=True)
        sys.exit(1)


if __name__ == "__main__":
    cli()

