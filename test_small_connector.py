import httpx

base = 'http://localhost:8001'
key = open('agent_test_key.txt').read().strip()

# Login
r = httpx.post(f'{base}/api/auth/login',
    json={'email':'e2e_agent_v2@test.com','password':'TestPass123!'}, timeout=10)
token = r.json()['token']
h = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}

# Delete old connectors
old = httpx.get(f'{base}/api/connectors', headers=h, timeout=10).json()
for c in old:
    httpx.delete(f'{base}/api/connectors/{c["id"]}', headers=h, timeout=5)
print(f'Deleted {len(old)} old connectors')

# Get agent ID
cfg = httpx.get(f'{base}/api/agent/config', headers={'X-Scanner-Key': key}, timeout=10).json()
agent_id = cfg['agent_id']
print(f'Agent ID: {agent_id}')

# Create a small connector (the workspace dir — only ~50 files)
r = httpx.post(f'{base}/api/connectors', headers=h, json={
    'name': 'Workspace Test',
    'connector_type': 'local',
    'config': {'path': 'C:/Users/User/.openclaw/workspace'},
    'routing_mode': 'agent',
    'scanner_agent_id': agent_id,
}, timeout=10)
print(f'Connector: {r.status_code} - {r.json().get("name","?")}')

# Verify it shows in agent config
cfg2 = httpx.get(f'{base}/api/agent/config', headers={'X-Scanner-Key': key}, timeout=10).json()
print(f'Connectors for agent: {len(cfg2["connectors"])}')
for c in cfg2['connectors']:
    print(f'  [{c["connector_type"]}] {c["name"]} path={c["config"].get("path","?")}')
