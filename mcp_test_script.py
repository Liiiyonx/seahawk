import asyncio, json, sys
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

async def main():
    url = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8100/mcp"
    token = "8209924139f1955081c8ff8903589ef51072bad8"
    headers = {"Authorization": f"Bearer {token}"}
    
    async with streamablehttp_client(url, headers=headers) as (read, write, _):
        async with ClientSession(read, write) as session:
            init = await session.initialize()
            print(f"Server: {init.serverInfo.name} v{init.serverInfo.version}")
            print(f"Protocol: {init.protocolVersion}")
            
            tools = await session.list_tools()
            print(f"Tools loaded: {len(tools.tools)}")
            
            # Call dashboard_get
            dash = await session.call_tool("dashboard_get", {})
            print(f"\ndashboard_get isError={dash.isError}")
            for c in dash.content:
                data = json.loads(c.text) if hasattr(c, 'text') and c.text else c
                print(json.dumps(data, ensure_ascii=False, indent=2)[:800])
            
            # Call agent_runtime_status  
            status = await session.call_tool("agent_runtime_status", {})
            print(f"\nagent_runtime_status isError={status.isError}")
            for c in status.content:
                data = json.loads(c.text) if hasattr(c, 'text') and c.text else c
                print(json.dumps(data, ensure_ascii=False, indent=2)[:800])

asyncio.run(main())
