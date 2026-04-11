import asyncio
from neo4j import AsyncGraphDatabase

async def main():
    driver = AsyncGraphDatabase.driver('bolt://localhost:7687', auth=('neo4j', 'fsgraph-local'))
    async with driver.session() as s:

        # Labels in graph
        r = await s.run('CALL db.labels() YIELD label RETURN label ORDER BY label')
        labels = [rec['label'] async for rec in r]
        print('=== Labels in Neo4j ===')
        print(labels)

        # Total node count
        r = await s.run('MATCH (n) RETURN count(n) as cnt')
        rec = await r.single()
        print(f'\nTotal nodes: {rec["cnt"]}')

        # Node counts by label
        r = await s.run('MATCH (n) RETURN labels(n)[0] as label, count(n) as cnt ORDER BY cnt DESC')
        print('\n=== Node counts by label ===')
        async for row in r:
            print(f'  {row["label"]}: {row["cnt"]}')

        # Sample 3 File nodes - show ALL properties
        print('\n=== Sample File nodes (full properties) ===')
        r = await s.run('MATCH (f:File) RETURN f LIMIT 3')
        async for row in r:
            props = dict(row['f'])
            print()
            for k, v in sorted(props.items()):
                print(f'  {k}: {repr(v)}')

        # Check tenant_id distribution
        r = await s.run('MATCH (f:File) RETURN f.tenant_id as tid, count(f) as cnt')
        print('\n=== tenant_id distribution ===')
        async for row in r:
            print(f'  tenant_id={row["tid"]}: {row["cnt"]} nodes')

        # Any relationships?
        r = await s.run('MATCH ()-[r]->() RETURN type(r) as rel, count(r) as cnt ORDER BY cnt DESC LIMIT 10')
        print('\n=== Relationships ===')
        found = False
        async for row in r:
            print(f'  {row["rel"]}: {row["cnt"]}')
            found = True
        if not found:
            print('  (none)')

        # Check what the stats API query does
        print('\n=== Stats query test (no tenant filter) ===')
        r = await s.run('''
            MATCH (n)
            WHERE n:File OR n:Directory OR n:Person OR n:Application OR n:Vulnerability
            RETURN labels(n)[0] as label, count(n) as cnt
        ''')
        async for row in r:
            print(f'  {row["label"]}: {row["cnt"]}')

asyncio.run(main())
