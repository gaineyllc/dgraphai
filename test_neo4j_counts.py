import asyncio
from neo4j import AsyncGraphDatabase

async def main():
    d = AsyncGraphDatabase.driver('bolt://localhost:7687', auth=('neo4j','fsgraph-local'))
    tid = 'c414b40a-97db-4664-a010-e253e7928d63'
    async with d.session() as s:
        r = await s.run(
            'MATCH (f:File) WHERE f.file_category = $cat AND f.tenant_id = $tid RETURN count(f) AS total',
            {'cat': 'code', 'tid': tid}
        )
        rec = await r.single()
        print('Code count:', rec['total'])
        r2 = await s.run(
            'MATCH (f:File) WHERE f.file_category = $cat AND f.tenant_id = $tid RETURN count(f) AS total',
            {'cat': 'image', 'tid': tid}
        )
        rec2 = await r2.single()
        print('Image count:', rec2['total'])

asyncio.run(main())
