"""Registers all tools exactly once, on import."""
from app.tools.data_lookup import register_data_tools
from app.tools.document_search import register_document_tools
from app.tools.actions import register_action_tools
from app.tools.insights_tool import register_insights_tool

_REGISTERED = False


def register_all_tools() -> None:
    global _REGISTERED
    if _REGISTERED:
        return
    register_document_tools()
    register_data_tools()
    register_action_tools()
    register_insights_tool()
    _REGISTERED = True
