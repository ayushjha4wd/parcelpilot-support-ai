import React, { useEffect, useRef, useState } from "react";

const API = ""; // same origin (FastAPI serves this build)

async function api(path, opts = {}) {
  const res = await fetch(API + path, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  if (!res.ok) {
    const t = await res.text();
    throw new Error(t || res.statusText);
  }
  return res.json();
}

const TOOL_LABELS = {
  search_documents: "📄 Document search",
  get_document: "📄 Read document",
  get_account: "🏢 Account lookup",
  get_order: "📦 Order lookup",
  list_orders: "📦 List orders",
  get_ticket: "🎫 Ticket lookup",
  list_tickets: "🎫 List tickets",
  get_snapshot_time: "🕒 Snapshot time",
  time_between: "🧮 Time calc",
  detect_issues: "🔎 Issue detection",
  create_escalation: "🚨 Create escalation",
  update_ticket: "✏️ Update ticket",
  create_followup_task: "✅ Follow-up task",
};
const toolLabel = (t) => TOOL_LABELS[t] || `🔧 ${t}`;

function Login({ config, accounts, onStart }) {
  const [tab, setTab] = useState("customer");
  const [accountId, setAccountId] = useState(accounts[0]?.account_id || "");
  const [role, setRole] = useState("ops");

  return (
    <div className="login-wrap">
      <div className="login-card">
        <h1>ParcelPilot Support AI</h1>
        <p className="sub">
          Choose an identity to start. Access control is enforced server-side —
          customers only ever see their own account.
        </p>
        <div className="seg">
          <button className={tab === "customer" ? "on" : ""} onClick={() => setTab("customer")}>
            Customer
          </button>
          <button className={tab === "internal" ? "on" : ""} onClick={() => setTab("internal")}>
            Internal staff
          </button>
        </div>

        {tab === "customer" ? (
          <div className="field">
            <label>Account</label>
            <select value={accountId} onChange={(e) => setAccountId(e.target.value)}>
              {accounts.map((a) => (
                <option key={a.account_id} value={a.account_id}>
                  {a.name} ({a.account_id}) · {a.plan}
                </option>
              ))}
            </select>
          </div>
        ) : (
          <div className="field">
            <label>Role</label>
            <select value={role} onChange={(e) => setRole(e.target.value)}>
              <option value="support_agent">Support agent</option>
              <option value="ops">Ops (insights access)</option>
              <option value="admin">Admin</option>
            </select>
          </div>
        )}

        <button
          className="primary"
          onClick={() =>
            onStart(
              tab === "customer"
                ? { principal: "customer", account_id: accountId }
                : { principal: "internal", internal_role: role }
            )
          }
        >
          Start chat →
        </button>

        <div className="config-line">
          Model: <b>{config?.model}</b> via <b>{config?.provider}</b>
          {config && !config.has_api_key && <span className="warn"> · no API key set</span>}
          {config?.data?.snapshot_time && (
            <> · snapshot <b>{config.data.snapshot_time.replace("T", " ")}</b></>
          )}
          {config && !config.data?.loaded && <span className="warn"> · data not loaded</span>}
        </div>
      </div>
    </div>
  );
}

function ToolChips({ events }) {
  if (!events?.length) return null;
  return (
    <div className="chips">
      {events.map((e, i) => (
        <span key={i} className={"chip" + (e.ok ? "" : " chip-err")} title={e.summary}>
          {toolLabel(e.tool)}
          {e.meta?.prepared ? " · prepared" : ""}
        </span>
      ))}
    </div>
  );
}

function Insights({ sessionId }) {
  const [items, setItems] = useState(null);
  const [err, setErr] = useState(null);
  const [snap, setSnap] = useState(null);

  const load = () => {
    setErr(null);
    api(`/api/insights?session_id=${sessionId}`)
      .then((d) => {
        setItems(d.insights);
        setSnap(d.snapshot_time);
      })
      .catch((e) => setErr(String(e.message || e)));
  };
  useEffect(load, [sessionId]);

  return (
    <div className="insights">
      <div className="insights-head">
        <h3>Proactive issue detection</h3>
        <button onClick={load}>↻ Refresh</button>
      </div>
      {snap && <div className="snap">As of snapshot {snap.replace("T", " ")}</div>}
      {err && <div className="err">{err}</div>}
      {items && items.length === 0 && <div className="muted">No issues detected.</div>}
      {items?.map((it, i) => (
        <div key={i} className={"insight sev-" + it.severity}>
          <div className="insight-top">
            <span className="badge">{it.severity}</span>
            <span className="kind">{it.kind.replace("_", " ")}</span>
          </div>
          <div className="insight-title">{it.title}</div>
          <div className="insight-detail">{it.detail}</div>
          {it.refs?.length > 0 && <div className="refs">{it.refs.join(", ")}</div>}
        </div>
      ))}
    </div>
  );
}

export default function App() {
  const [config, setConfig] = useState(null);
  const [accounts, setAccounts] = useState([]);
  const [session, setSession] = useState(null);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [pending, setPending] = useState(null);
  const [view, setView] = useState("chat");
  const scroller = useRef(null);

  useEffect(() => {
    api("/api/config").then(setConfig).catch(() => {});
    api("/api/accounts").then((d) => setAccounts(d.accounts || [])).catch(() => {});
  }, []);

  useEffect(() => {
    if (scroller.current) scroller.current.scrollTop = scroller.current.scrollHeight;
  }, [messages, loading]);

  const start = async (identity) => {
    const s = await api("/api/session", { method: "POST", body: JSON.stringify(identity) });
    setSession(s);
    setMessages([
      {
        role: "system",
        text:
          s.identity.principal === "customer"
            ? `You're chatting as ${s.identity.account_name || s.identity.account_id}. Ask about your orders, cancellations, credits, or SLAs.`
            : `You're chatting as internal ${s.identity.role}. You can investigate across accounts and see proactive insights.`,
      },
    ]);
  };

  const applyTurn = (turn) => {
    setMessages((m) => [
      ...m,
      { role: "assistant", text: turn.assistant_text, events: turn.events },
    ]);
    setPending(turn.pending_action || null);
  };

  const send = async () => {
    const text = input.trim();
    if (!text || loading) return;
    setInput("");
    setMessages((m) => [...m, { role: "user", text }]);
    setLoading(true);
    try {
      const turn = await api("/api/chat", {
        method: "POST",
        body: JSON.stringify({ session_id: session.session_id, message: text }),
      });
      applyTurn(turn);
    } catch (e) {
      setMessages((m) => [...m, { role: "error", text: String(e.message || e) }]);
    } finally {
      setLoading(false);
    }
  };

  const confirm = async (approved) => {
    setLoading(true);
    try {
      const turn = await api("/api/confirm", {
        method: "POST",
        body: JSON.stringify({ session_id: session.session_id, approved }),
      });
      applyTurn(turn);
    } catch (e) {
      setMessages((m) => [...m, { role: "error", text: String(e.message || e) }]);
    } finally {
      setLoading(false);
    }
  };

  if (!session) return <Login config={config} accounts={accounts} onStart={start} />;

  const id = session.identity;
  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">ParcelPilot Support AI</div>
        <div className="identity">
          <span className={"pill " + (id.principal === "customer" ? "cust" : "staff")}>
            {id.principal === "customer"
              ? `${id.account_name || id.account_id}`
              : `Staff · ${id.role}`}
          </span>
          {config?.data?.snapshot_time && (
            <span className="snaptag">now: {config.data.snapshot_time.replace("T", " ")}</span>
          )}
          <span className="modeltag">{config?.model}</span>
          <button className="ghost" onClick={() => { setSession(null); setMessages([]); setPending(null); }}>
            Switch identity
          </button>
        </div>
      </header>

      {id.can_view_insights && (
        <div className="tabs">
          <button className={view === "chat" ? "on" : ""} onClick={() => setView("chat")}>Chat</button>
          <button className={view === "insights" ? "on" : ""} onClick={() => setView("insights")}>
            Insights
          </button>
        </div>
      )}

      {view === "insights" && id.can_view_insights ? (
        <Insights sessionId={session.session_id} />
      ) : (
        <>
          <div className="chat" ref={scroller}>
            {messages.map((m, i) => (
              <div key={i} className={"msg " + m.role}>
                {m.role === "assistant" && <ToolChips events={m.events} />}
                <div className="bubble">{m.text}</div>
              </div>
            ))}
            {loading && (
              <div className="msg assistant">
                <div className="bubble typing">…thinking & using tools</div>
              </div>
            )}
            {pending && (
              <div className="confirm-banner">
                <div>
                  <b>Confirmation required</b>
                  <div className="mono">{toolLabel(pending.tool)} → {JSON.stringify(pending.arguments)}</div>
                </div>
                <div className="confirm-actions">
                  <button className="primary" onClick={() => confirm(true)} disabled={loading}>Confirm</button>
                  <button className="ghost" onClick={() => confirm(false)} disabled={loading}>Cancel</button>
                </div>
              </div>
            )}
          </div>

          <div className="composer">
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && send()}
              placeholder={
                id.principal === "customer"
                  ? "e.g. Can I cancel ORD-1001 without a fee?"
                  : "e.g. What issues need attention right now?"
              }
              disabled={loading}
            />
            <button className="primary" onClick={send} disabled={loading || !input.trim()}>Send</button>
          </div>
        </>
      )}
    </div>
  );
}
