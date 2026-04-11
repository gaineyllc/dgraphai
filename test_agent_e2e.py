import httpx

base = 'http://localhost:8001'

# 1. Signup
r = httpx.post(f'{base}/api/auth/signup', json={
    'email':'e2e_agent_v2@test.com','password':'TestPass123!','name':'Neil','company':'dgraph.ai'
}, timeout=10)
token = r.json()['token']
h = {'Authorization': f'Bearer {token}'}
print(f'Signup: {r.status_code}')

# 2. Generate agent API key
r = httpx.post(f'{base}/api/agent/token?name=my-windows-agent', headers=h, timeout=10)
print(f'Token gen: {r.status_code}')
if r.status_code not in (200, 201):
    print('ERROR:', r.text[:300])
    exit(1)
data = r.json()
api_key = data['api_key']
agent_id = data['agent_id']
print(f'Agent ID: {agent_id}')
print(f'API Key: {api_key[:20]}...')

# 3. Agent fetches config
sk = {'X-Scanner-Key': api_key}
r = httpx.get(f'{base}/api/agent/config', headers=sk, timeout=10)
print(f'Config fetch: {r.status_code}')
if r.status_code == 200:
    cfg = r.json()
    print(f'  tenant_id: {cfg["tenant_id"]}')
    print(f'  connectors assigned: {len(cfg["connectors"])}')
else:
    print('ERROR:', r.text[:300])

# 4. Send heartbeat
r = httpx.post(f'{base}/api/agent/heartbeat',
    headers={**sk, 'Content-Type': 'application/json'},
    json={
        'agent_id': agent_id,
        'version': '0.1.0',
        'os': 'windows',
        'hostname': 'GAME',
        'files_indexed': 0,
        'files_pending': 0,
        'connector_statuses': {},
    }, timeout=10)
print(f'Heartbeat: {r.status_code} - {r.json()}')

# 5. Verify online status
r = httpx.get(f'{base}/api/agents/{agent_id}', headers=h, timeout=10)
print(f'Agent status: {r.status_code}')
if r.status_code == 200:
    s = r.json()
    print(f'  is_online:  {s["is_online"]}')
    print(f'  version:    {s["version"]}')
    print(f'  hostname:   {s["hostname"]}')
    print(f'  os:         {s["os"]}')

print()
print('=== To run the agent on Windows ===')
print(f'$env:DGRAPH_AGENT_API_KEY="{api_key}"')
print(f'$env:DGRAPH_AGENT_API_ENDPOINT="http://localhost:8001"')
print(r'F:\projects\dgraphai\agent-go\dist\dgraph-agent.exe test')
print()
with open('agent_test_key.txt', 'w') as f:
    f.write(api_key)
print('Key saved to agent_test_key.txt')
