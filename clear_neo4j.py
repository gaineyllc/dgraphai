import asyncio
from neo4j import AsyncGraphDatabase

async def main():
    driver = AsyncGraphDatabase.driver('bolt://localhost:7687', auth=('neo4j', 'fsgraph-local'))
    async with driver.session() as s:
        r = await s.run('MATCH (n) DETACH DELETE n')
        await r.consume()
        r2 = await s.run('MATCH (n) RETURN count(n) as cnt')
        rec = await r2.single()
        print('Nodes after clear:', rec['cnt'])

asyncio.run(main())
