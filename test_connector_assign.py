import httpx

base = 'http://localhost:8001'
key = open('agent_test_key.txt').read().strip()

# Get agent info via config endpoint
cfg = httpx.get(f'{base}/api/agent/config', headers={'X-Scanner-Key': key}, timeout=10).json()
tenant_id = cfg['tenant_id']
agent_id  = cfg['agent_id']
print(f'Agent tenant: {tenant_id}')
print(f'Agent ID:     {agent_id}')
print(f'Connectors:   {len(cfg["connectors"])}')

# Login as the agent's tenant
r = httpx.post(f'{base}/api/auth/login',
    json={'email':'e2e_agent_v2@test.com','password':'TestPass123!'}, timeout=10)
token = r.json()['token']
h = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}

# Assign a local connector to this agent
r = httpx.post(f'{base}/api/connectors', headers=h, json={
    'name':             'My Windows C Drive',
    'connector_type':   'local',
    'config':           {'path': 'C:\\Users'},
    'routing_mode':     'agent',
    'scanner_agent_id': agent_id,
}, timeout=10)
print(f'Create connector: {r.status_code}')
if r.status_code not in (200, 201):
    print('ERROR:', r.text[:300])
else:
    conn = r.json()
    print(f'  Created: {conn["name"]} ({conn["id"]})')

# Now fetch config as agent - should see the connector
cfg2 = httpx.get(f'{base}/api/agent/config', headers={'X-Scanner-Key': key}, timeout=10).json()
count = len(cfg2['connectors'])
print(f'Connectors now: {count}')
for c in cfg2['connectors']:
    print(f'  [{c["connector_type"]}] {c["name"]} — enabled: {c["enabled"]}')
    print(f'    config: {c["config"]}')
