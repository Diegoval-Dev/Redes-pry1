from chatbot.mcp_runtime import MCPFleet
from chatbot.config import FS_ROOT

fleet = MCPFleet(enabled={"fs"})
print("Launching FS…")
fleet.start_all()
print("Started. Listing tools…")
print([t.get("name") for t in fleet.fs.list_tools()])
print("Calling list_directory…")
res = fleet.fs.tools_call("list_directory", {"path": FS_ROOT})
print(type(res), res.keys() if isinstance(res, dict) else res)
