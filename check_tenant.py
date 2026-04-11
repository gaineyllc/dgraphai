import asyncio
from neo4j import AsyncGraphDatabase
async def main():
    d = AsyncGraphDatabase.driver('bolt://localhost:7687', auth=('neo4j','fsgraph-local'))
    async with d.session() as s:
        r = await s.run('MATCH (f:File) RETURN DISTINCT f.tenant_id as tid, count(f) as cnt ORDER BY cnt DESC LIMIT 5')
        async for row in r:
            print('tenant=' + str(row['tid']) + ' files=' + str(row['cnt']))
asyncio.run(main())
