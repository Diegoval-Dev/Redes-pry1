from typing import Dict, Any, List, Callable
from .sum_tool import DEF as SUM_DEF, IMPL as SUM_IMPL
from .grep_tool import DEF as GREP_DEF, IMPL as GREP_IMPL
from .sha256_tool import DEF as SHA_DEF, IMPL as SHA_IMPL
from .timeseries_stats import DEF as TS_DEF, IMPL as TS_IMPL
from .json_validate import DEF as JV_DEF, IMPL as JV_IMPL

TOOLS: List[dict] = [SUM_DEF, GREP_DEF, SHA_DEF, TS_DEF, JV_DEF]

TOOL_IMPL: Dict[str, Callable[[dict], Dict[str, Any]]] = {
    "sum": SUM_IMPL,
    "grep_lines": GREP_IMPL,
    "sha256": SHA_IMPL,
    "timeseries_stats": TS_IMPL,
    "json_validate": JV_IMPL
}