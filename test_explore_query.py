import httpx

base = 'http://localhost:8001'
r = httpx.post(f'{base}/api/auth/login', json={'email':'e2e_agent_v2@test.com','password':'TestPass123!'}, timeout=10)
token = r.json()['token']
h = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}

# Test exactly what ExplorePage sends (no params, inline values)
cypher = "MATCH (f:File)\nWHERE f.file_category = 'code'\nRETURN f LIMIT 100"
r2 = httpx.post(f'{base}/api/graph/query', headers=h,
    json={'cypher': cypher},
    timeout=20)
print('Status:', r2.status_code)
if r2.status_code == 200:
    rows = r2.json()
    print('Rows:', len(rows))
    if rows:
        print('First row keys:', list(rows[0].keys()))
        f = rows[0].get('f', {})
        print('Node has id:', 'id' in f)
        print('Node keys:', list(f.keys())[:10])
else:
    print('Error:', r2.text[:400])

# Also test simple query without WHERE
cypher2 = "MATCH (f:File) RETURN f LIMIT 5"
r3 = httpx.post(f'{base}/api/graph/query', headers=h, json={'cypher': cypher2}, timeout=15)
print()
print('Simple query status:', r3.status_code)
if r3.status_code == 200:
    rows3 = r3.json()
    print('Rows:', len(rows3))
else:
    print('Error:', r3.text[:300])
