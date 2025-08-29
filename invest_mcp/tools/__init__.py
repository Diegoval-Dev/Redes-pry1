# invest_mcp/tools/__init__.py
from typing import Dict, Any, List, Callable
from .price_quote import DEF as PQ_DEF, IMPL as PQ_IMPL
from .risk_metrics import DEF as RM_DEF, IMPL as RM_IMPL
from .build_portfolio import DEF as BP_DEF, IMPL as BP_IMPL
from .rebalance_plan import DEF as RB_DEF, IMPL as RB_IMPL

TOOLS: List[dict] = [PQ_DEF, RM_DEF, BP_DEF, RB_DEF]

TOOL_IMPL: Dict[str, Callable[[dict], Dict[str, Any]]] = {
    "price_quote": PQ_IMPL,
    "risk_metrics": RM_IMPL,
    "build_portfolio": BP_IMPL,
    "rebalance_plan": RB_IMPL,
}
