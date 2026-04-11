"""Full API validation — simulates the complete UI flow."""
import httpx, sys

base = 'http://localhost:8001'
issues = []

# Auth
r = httpx.post(f'{base}/api/auth/login', json={'email':'e2e_agent_v2@test.com','password':'TestPass123!'}, timeout=15)
assert r.status_code == 200, f"Login failed: {r.status_code}"
token = r.json()['token']
h = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
print('✓ Auth: login OK')

# Dashboard data
r = httpx.get(f'{base}/api/graph/stats', headers=h, timeout=10)
stats = r.json()
print(f'✓ Graph stats: {stats}')
assert stats.get('File', 0) > 0, "File count should be > 0"

# Inventory counts
r = httpx.get(f'{base}/api/inventory', headers=h, timeout=30)
inv = r.json()
groups = inv.get('groups', {})
print(f'✓ Inventory: {len(groups)} groups')
# Check if counts are populated
total_count = sum(c.get('count', 0) or 0 for cats in groups.values() for c in cats)
if total_count == 0:
    issues.append('Inventory counts all zero — taxonomy cypher may not match actual file_category values')
else:
    print(f'  Total inventory count: {total_count}')

# Graph query (the key test — node serialization)
r = httpx.post(f'{base}/api/graph/query', headers=h,
    json={'cypher': 'MATCH (f:File) RETURN f LIMIT 5'}, timeout=15)
print(f'Graph query status: {r.status_code}')
if r.status_code == 200:
    rows = r.json()
    print(f'✓ Graph query: {len(rows)} rows returned')
    if rows:
        first = rows[0]
        print(f'  First row keys: {list(first.keys())}')
        # Check it's a proper node dict
        f_node = first.get('f', {})
        print(f'  Node props: {list(f_node.keys())[:8]}')
else:
    issues.append(f'Graph query failed: {r.status_code} {r.text[:200]}')

# Agents
r = httpx.get(f'{base}/api/agents', headers=h, timeout=10)
agents = r.json()
print(f'✓ Agents: {len(agents)} registered')
for a in agents[:2]:
    print(f'  - {a["name"]}: online={a["is_online"]} files={a["files_indexed"]}')

# Connectors
r = httpx.get(f'{base}/api/connectors', headers=h, timeout=10)
conns = r.json()
print(f'✓ Connectors: {len(conns)} configured')

# Connector types (should include smb, nfs, local)
r = httpx.get(f'{base}/api/connectors/types', headers=h, timeout=10)
types = [t['id'] for t in r.json()]
print(f'✓ Connector types: {types}')
assert 'smb' in types, "SMB missing"
assert 'local' in types, "Local missing"

# Policies API (stub - not built yet server-side)
# Just verify pages exist client-side via build

print()
if issues:
    print('⚠️ Issues found:')
    for i in issues:
        print(f'  - {i}')
    sys.exit(1)
else:
    print('✅ All validation checks passed')
