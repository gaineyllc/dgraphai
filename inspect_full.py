import asyncio
from neo4j import AsyncGraphDatabase

async def main():
    driver = AsyncGraphDatabase.driver('bolt://localhost:7687', auth=('neo4j', 'fsgraph-local'))
    async with driver.session() as s:
        # Get ALL properties of first 5 File nodes
        r = await s.run('MATCH (f:File) RETURN f LIMIT 5')
        print('=== FULL node properties ===')
        async for row in r:
            node = dict(row['f'])
            print()
            for k in sorted(node.keys()):
                print(f'  {k}: {repr(node[k])[:80]}')
            print()
        
        # Specifically look for files with extensions
        r2 = await s.run('MATCH (f:File) WHERE f.extension <> "" RETURN f LIMIT 3')
        print('\n=== Files WITH extension ===')
        found = False
        async for row in r2:
            found = True
            node = dict(row['f'])
            for k in sorted(node.keys()):
                print(f'  {k}: {repr(node[k])[:80]}')
            print()
        if not found:
            print('  (none found)')
        
        # Count by file_category
        r3 = await s.run('MATCH (f:File) RETURN f.file_category as cat, count(f) as cnt ORDER BY cnt DESC LIMIT 10')
        print('\n=== Files by category ===')
        async for row in r3:
            print(f'  {row["cat"]}: {row["cnt"]}')

        # Count by mime_type (top 10)
        r4 = await s.run('MATCH (f:File) RETURN f.mime_type as mime, count(f) as cnt ORDER BY cnt DESC LIMIT 15')
        print('\n=== Files by MIME type ===')
        async for row in r4:
            print(f'  {row["mime"]}: {row["cnt"]}')

asyncio.run(main())
