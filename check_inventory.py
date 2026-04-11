import httpx, time, json
time.sleep(3)
r = httpx.post('http://localhost:8001/api/auth/login',
    json={'email':'e2e_agent_v2@test.com','password':'TestPass123!'}, timeout=15)
if r.status_code != 200:
    print('Login failed:', r.status_code, r.text[:100])
    exit()
token = r.json()['token']
h = {'Authorization': f'Bearer {token}'}
r2 = httpx.get('http://localhost:8001/api/inventory', headers=h, timeout=10)
data = r2.json()
groups = data.get('groups', {})
print('Groups:', list(groups.keys()))
for gname, cats in list(groups.items())[:4]:
    print(f'  {gname}: {len(cats)} cats')
    for c in cats[:2]:
        print(f'    name={c.get("name")} count={c.get("count")} id={c.get("id")}')

# Also check graph query
r3 = httpx.post('http://localhost:8001/api/graph/query', headers={**h,'Content-Type':'application/json'},
    json={'cypher': 'MATCH (f:File) RETURN f LIMIT 3'}, timeout=15)
print('Graph query:', r3.status_code, str(r3.json())[:300])
