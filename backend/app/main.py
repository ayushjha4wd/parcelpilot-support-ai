"""FastAPI app: chat API + session/identity + insights + static frontend.

Sessions are held in memory (fine for a demo). Each session stores the trusted
UserContext and the running message list, so the confirmation flow and
multi-turn context work correctly. The client NEVER supplies the account it can
see -- it supplies an identity, which the server resolves and trusts.
"""
from __future__ import annotations

import os
import uuid
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.agent.agent import PendingAction, agent
from app.auth.context import (
    InternalRole,
    Principal,
    UserContext,
    build_customer_context,
    build_internal_context,
)
from app.config import settings
from app.data.loader import DATA, reload_data
from app.insights.detector import compute_insights
from app.tools import register_all_tools
from app.tools.registry import registry

register_all_tools()

app = FastAPI(title="ParcelPilot Support AI")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# --------------------------- session store ----------------------------------
class Session:
    def __init__(self, ctx: UserContext):
        self.ctx = ctx
        self.messages: list[dict[str, Any]] = []
        self.pending: PendingAction | None = None


SESSIONS: dict[str, Session] = {}


def _account_name(account_id: str) -> str | None:
    df = DATA.df("accounts")
    idc = DATA.col("accounts", "account_id")
    namec = DATA.col("accounts", "name")
    if df is None or idc is None or namec is None:
        return None
    m = df[df[idc].astype(str) == str(account_id)]
    return None if m.empty else str(m.iloc[0][namec])


# --------------------------- request models ---------------------------------
class StartSessionReq(BaseModel):
    principal: str                    # "customer" | "internal"
    account_id: str | None = None     # for customer
    internal_role: str | None = "ops" # for internal


class ChatReq(BaseModel):
    session_id: str
    message: str


class ConfirmReq(BaseModel):
    session_id: str
    approved: bool


# --------------------------- helpers ----------------------------------------
def _turn_payload(turn) -> dict[str, Any]:
    return {
        "assistant_text": turn.assistant_text,
        "events": [
            {"tool": e.tool, "arguments": e.arguments, "ok": e.ok,
             "summary": e.summary, "meta": e.meta}
            for e in turn.events
        ],
        "pending_action": (
            {"id": turn.pending_action.id, "tool": turn.pending_action.tool,
             "arguments": turn.pending_action.arguments,
             "description": turn.pending_action.description}
            if turn.pending_action else None
        ),
    }


# --------------------------- endpoints --------------------------------------
@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/api/config")
def get_config():
    return {
        "provider": settings.provider,
        "model": settings.model,
        "has_api_key": bool(settings.api_key),
        "data": {
            "loaded": DATA.loaded,
            "error": DATA.load_error,
            "snapshot_time": DATA.snapshot_time.isoformat() if DATA.snapshot_time else None,
            "sheets": list(DATA.sheets.keys()),
        },
    }


@app.get("/api/accounts")
def list_accounts():
    """For the demo identity switcher only."""
    df = DATA.df("accounts")
    if df is None:
        return {"accounts": []}
    idc = DATA.col("accounts", "account_id")
    namec = DATA.col("accounts", "name")
    tierc = DATA.col("accounts", "tier")
    out = []
    for _, r in df.iterrows():
        out.append({
            "account_id": str(r[idc]) if idc else None,
            "name": str(r[namec]) if namec else None,
            "plan": str(r[tierc]) if tierc else None,
        })
    return {"accounts": out}


@app.post("/api/session")
def start_session(req: StartSessionReq):
    if req.principal == Principal.CUSTOMER.value:
        if not req.account_id:
            raise HTTPException(400, "account_id required for a customer session.")
        ctx = build_customer_context(req.account_id)
        ctx.account_name = _account_name(req.account_id)
    else:
        try:
            role = InternalRole(req.internal_role or "ops")
        except ValueError:
            role = InternalRole.OPS
        ctx = build_internal_context(role=role)
    sid = str(uuid.uuid4())
    SESSIONS[sid] = Session(ctx)
    return {
        "session_id": sid,
        "identity": {
            "principal": ctx.principal.value,
            "account_id": ctx.account_id,
            "account_name": ctx.account_name,
            "role": ctx.role.value if ctx.role else None,
            "can_view_insights": ctx.can_view_insights,
            "scope": ctx.scope_label(),
        },
        "available_tools": [t.name for t in registry.available_for(ctx)],
    }


@app.post("/api/chat")
def chat(req: ChatReq):
    sess = SESSIONS.get(req.session_id)
    if sess is None:
        raise HTTPException(404, "Unknown session. Start a session first.")
    turn = agent.step(sess.ctx, sess.messages, req.message)
    sess.messages = turn.messages
    sess.pending = turn.pending_action
    return _turn_payload(turn)


@app.post("/api/confirm")
def confirm(req: ConfirmReq):
    sess = SESSIONS.get(req.session_id)
    if sess is None:
        raise HTTPException(404, "Unknown session.")
    if sess.pending is None:
        raise HTTPException(400, "No action awaiting confirmation.")
    pending = sess.pending
    turn = agent.confirm_action(sess.ctx, sess.messages, pending, req.approved)
    sess.messages = turn.messages
    sess.pending = turn.pending_action
    return _turn_payload(turn)


@app.get("/api/insights")
def insights(session_id: str):
    sess = SESSIONS.get(session_id)
    if sess is None:
        raise HTTPException(404, "Unknown session.")
    if not sess.ctx.can_view_insights:
        raise HTTPException(403, "Insights are for internal ops/admin users only.")
    return {"insights": [i.to_dict() for i in compute_insights()],
            "snapshot_time": DATA.snapshot_time.isoformat() if DATA.snapshot_time else None}


@app.post("/api/reload-data")
def reload_data_endpoint():
    pack = reload_data()
    # Rebuild the document index too (in case docs changed).
    from app.tools.document_search import rebuild_index
    rebuild_index()
    return {"loaded": pack.loaded, "error": pack.load_error,
            "snapshot_time": pack.snapshot_time.isoformat() if pack.snapshot_time else None}


# --------------------------- static frontend --------------------------------
_STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
if os.path.isdir(_STATIC_DIR):
    app.mount("/assets", StaticFiles(directory=os.path.join(_STATIC_DIR, "assets")), name="assets")

    @app.get("/")
    def index():
        return FileResponse(os.path.join(_STATIC_DIR, "index.html"))

    @app.get("/{full_path:path}")
    def spa(full_path: str):
        # SPA fallback for client-side routing.
        candidate = os.path.join(_STATIC_DIR, full_path)
        if os.path.isfile(candidate):
            return FileResponse(candidate)
        return FileResponse(os.path.join(_STATIC_DIR, "index.html"))
