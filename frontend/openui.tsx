import React, { Component, useEffect, useState } from "react";
import { createRoot, type Root } from "react-dom/client";
import {
  createLibrary,
  createParser,
  defineComponent,
  Renderer,
  useRenderNode,
} from "@openuidev/react-lang";
import { z } from "zod/v4";

const num = (n: any) => typeof n === "number" && Number.isFinite(n);
const count = (n: any) => (num(n) ? new Intl.NumberFormat().format(n) : "—");
const bytes = (n: any) =>
  !num(n)
    ? "—"
    : n >= 1024 ** 3
      ? `${(n / 1024 ** 3).toFixed(2)} GiB`
      : n >= 1024 ** 2
        ? `${(n / 1024 ** 2).toFixed(1)} MiB`
        : `${(n / 1024).toFixed(1)} KiB`;
const pct = (n: any) => (num(n) ? `${n.toFixed(1)}%` : "—");
const clock = (n: any) =>
  num(n)
    ? new Date(n * 1000).toLocaleTimeString([], {
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
      })
    : "Not sampled";
const short = (n: any) =>
  !num(n)
    ? "—"
    : new Intl.NumberFormat([], {
        notation: "compact",
        maximumFractionDigits: 1,
      }).format(n);
const uptime = (n: any) =>
  num(n)
    ? `${Math.floor(n / 86400)}d ${Math.floor(n / 3600) % 24}h ${Math.floor(n / 60) % 60}m`
    : "—";
const age = (n: any) =>
  !num(n)
    ? "—"
    : `${Math.max(0, Math.floor((Date.now() / 1000 - n) / 60))}m ago`;

function Sparkline({ points, field, label }: any) {
  if (!points?.length)
    return <div className="chart-empty">Waiting for real samples</div>;
  const start = points[0].at,
    span = Math.max(5, points.at(-1).at - start);
  const path = points
    .map(
      (p: any) =>
        `${(((p.at - start) / span) * 500).toFixed(1)},${(90 - Math.min(100, Math.max(0, p[field])) * 0.8).toFixed(1)}`,
    )
    .join(" ");
  return (
    <svg
      className="sparkline"
      viewBox="0 0 500 100"
      preserveAspectRatio="none"
      role="img"
      aria-label={label}
    >
      {[10, 50, 90].map((y) => (
        <line key={y} x1="0" x2="500" y1={y} y2={y} className="chart-grid" />
      ))}
      {points.length === 1 ? (
        <circle
          cx="0"
          cy={90 - points[0][field] * 0.8}
          r="2"
          fill="currentColor"
        />
      ) : (
        <polyline
          points={path}
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          vectorEffect="non-scaling-stroke"
        />
      )}
    </svg>
  );
}

function Stat({ label, value, note }: any) {
  return (
    <div className="stat">
      <dt>{label}</dt>
      <dd>{value ?? "—"}</dd>
      {note && <small>{note}</small>}
    </div>
  );
}
function Pair({ label, value }: any) {
  return (
    <div className="datum">
      <span>{label}</span>
      <strong>{value ?? "—"}</strong>
    </div>
  );
}
function Status({ children, good = true }: any) {
  return (
    <span className={"signal " + (good ? "good" : "warning")}>{children}</span>
  );
}

function ProcessTable({ data }: any) {
  const [query, setQuery] = useState(""),
    [sort, setSort] = useState("rss");
  const rows = [...(data?.processes || [])]
    .filter((p) =>
      `${p.name} ${p.pid}`.toLowerCase().includes(query.toLowerCase()),
    )
    .sort((a, b) => (b[sort] || 0) - (a[sort] || 0));
  return (
    <section className="ops-panel process-panel">
      <div className="panel-heading">
        <div>
          <span className="section-index">01 / HOST</span>
          <h2>
            Process monitor <small>{count(data?.process_count)} observed</small>
          </h2>
        </div>
        <span className="live-dot" aria-label="Live samples" />
      </div>
      <div className="table-tools">
        <input
          aria-label="Filter processes"
          placeholder="Filter by name or PID"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <select
          aria-label="Sort processes"
          value={sort}
          onChange={(e) => setSort(e.target.value)}
        >
          <option value="rss">Memory ↓</option>
          <option value="cpu_percent">CPU ↓</option>
          <option value="threads">Threads ↓</option>
        </select>
      </div>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>Process</th>
              <th>PID</th>
              <th>CPU</th>
              <th>Memory RSS</th>
              <th>Threads</th>
            </tr>
          </thead>
          <tbody>
            {rows.slice(0, 50).map((p) => (
              <tr key={p.pid}>
                <td>
                  <span className="process-name">{p.name}</span>
                  <small className="cell-note">{p.status}</small>
                </td>
                <td>{p.pid}</td>
                <td>{pct(p.cpu_percent)}</td>
                <td className="emphasis">{bytes(p.rss)}</td>
                <td>{count(p.threads)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {!rows.length && (
          <p className="empty-data">
            {data ? "No matching processes." : "Waiting for host telemetry."}
          </p>
        )}
      </div>
      <p className="data-note">
        RSS includes shared pages. Rows cannot be added together to get RAM use.
        CPU is per core; a first sample has no rate.
      </p>
    </section>
  );
}

function QuotaPanel({ data }: any) {
  const n = data?.native;
  return (
    <section className="ops-panel quota-panel">
      <div className="panel-heading">
        <div>
          <span className="section-index">03 / ACCOUNT</span>
          <h2>
            {n?.provider === "openai-codex" ? "Codex" : "Provider"} summary
          </h2>
        </div>
        <span className="subtle-tag">{n?.plan || "Waiting"}</span>
      </div>
      {n?.windows?.map((w: any) => (
        <div className="account-window" key={w.label}>
          <div className="window-heading">
            <strong>{w.label}</strong>
            <span>
              <b>{(100 - w.used_percent).toFixed(0)}%</b> remaining
            </span>
          </div>
          <progress
            max="100"
            value={w.used_percent}
            aria-label={`${w.label} quota used`}
          />
          <div className="window-meta">
            <span>{w.used_percent}% used</span>
            <span>
              {w.resets_at
                ? "Resets " + new Date(w.resets_at).toLocaleString()
                : "Reset time unavailable"}
            </span>
          </div>
        </div>
      ))}
      {!n?.available && (
        <p className="empty-data">
          {data
            ? n?.note || "Provider did not return numeric limits."
            : "Fetching native provider limits…"}
        </p>
      )}
      <div className="account-foot">
        <span>Source: Hermes {n?.source || "usage --json"}</span>
        <span>
          {n?.fetched_at
            ? new Date(n.fetched_at).toLocaleTimeString()
            : "Not fetched"}
        </span>
      </div>
      <details className="source-details">
        <summary>Aperture budgets</summary>
        <p>{data?.aperture?.note || "Not yet checked."}</p>
        <p>
          Account limits are separate from recorded tokens and per-chat usage.
          Empty budgets do not mean unlimited credit.
        </p>
      </details>
    </section>
  );
}

function ActivityPanel({ data }: any) {
  const t = data?.totals,
    g = data?.gateway,
    h = data?.hsuh;
  return (
    <section className="ops-panel activity-panel">
      <div className="panel-heading">
        <div>
          <span className="section-index">02 / EXECUTION</span>
          <h2>What’s open</h2>
        </div>
        <Status good={g?.available && !g?.stale}>
          {g?.available
            ? g.stale
              ? "Gateway stale"
              : g.state
            : "Gateway unavailable"}
        </Status>
      </div>
      <dl className="execution-stats">
        <Stat
          label="Native agents"
          value={g?.stale ? "—" : count(g?.active_agents)}
          note="Gateway observation"
        />
        <Stat
          label="Open sessions"
          value={count(t?.open)}
          note="Includes idle sessions"
        />
        <Stat
          label="Live turn leases"
          value={count(data?.turn_leases)}
          note="Unexpired native leases"
        />
        <Stat
          label="HSUH active"
          value={count(h?.active_turns)}
          note={`${h?.workers ?? "—"} / ${h?.max_workers ?? 2} worker processes`}
        />
      </dl>
      <div className="section-subhead">
        <h3>Recent Hermes sessions</h3>
        <span>{data?.available ? "Metadata only" : "Source unavailable"}</span>
      </div>
      <div className="session-scroll">
        {data?.sessions?.slice(0, 12).map((s: any) => (
          <details className="native-session" key={s.id}>
            <summary>
              <span className={"session-indicator " + s.state} />
              <span className="session-title">
                {s.title || s.source || "Untitled session"}
                <small>
                  {s.source} · {age(s.last_activity_at || s.started_at)}
                </small>
              </span>
              <span className="session-state">{s.state}</span>
            </summary>
            <div className="session-detail">
              <Pair label="Model" value={s.model || "Not recorded"} />
              <Pair
                label="API / tool calls"
                value={`${count(s.api_call_count)} / ${count(s.tool_call_count)}`}
              />
              <Pair
                label="Recorded input / output"
                value={`${short(s.input_tokens)} / ${short(s.output_tokens)}`}
              />
              <Pair label="Session" value={s.id.slice(0, 12)} />
            </div>
          </details>
        ))}
        {!data?.sessions?.length && (
          <p className="empty-data">
            {data?.available
              ? "No recorded sessions."
              : "Native metadata has not loaded. No count inferred."}
          </p>
        )}
      </div>
      <p className="data-note">
        Metadata snapshot {clock(data?.sampled_at)}. Open includes idle
        sessions. This panel observes native jobs; it does not control them.
      </p>
    </section>
  );
}

function Overview() {
  const [telemetry, setTelemetry] = useState<any>(null),
    [activity, setActivity] = useState<any>(null),
    [quota, setQuota] = useState<any>(null);
  const [failures, setFailures] = useState<Record<string, string>>({});
  const failure = Object.values(failures).join(" ");
  useEffect(() => {
    const clear = (key: string) =>
      setFailures((old) => {
        const next = { ...old };
        delete next[key];
        return next;
      });
    const t = (e: any) => {
        setTelemetry(e.detail);
        clear("host");
      },
      a = (e: any) => {
        setActivity(e.detail);
        clear("activity");
      },
      q = (e: any) => setQuota(e.detail),
      f = (e: any) =>
        setFailures((old) => ({ ...old, [e.detail.source]: e.detail.message }));
    window.addEventListener("hsuh:telemetry", t);
    window.addEventListener("hsuh:activity", a);
    window.addEventListener("hsuh:quota", q);
    window.addEventListener("hsuh:stats-error", f);
    window.dispatchEvent(new CustomEvent("hsuh:ui-ready"));
    return () => {
      window.removeEventListener("hsuh:telemetry", t);
      window.removeEventListener("hsuh:activity", a);
      window.removeEventListener("hsuh:quota", q);
      window.removeEventListener("hsuh:stats-error", f);
    };
  }, []);
  const d = telemetry,
    m = d?.memory,
    t = activity?.totals;
  return (
    <div className="operations">
      <div className="overview-heading">
        <div>
          <span className="eyebrow">HERMES / OPERATIONS</span>
          <h1>Control centre</h1>
          <p>Your server, running work and account limits. In view.</p>
        </div>
        <div className="sampling">
          <Status good={!failure && !!d}>
            {failure
              ? "Telemetry stale"
              : d
                ? "Live · 5s samples"
                : "Connecting"}
          </Status>
          <span>{clock(d?.sampled_at)}</span>
        </div>
      </div>
      {failure && (
        <p className="stats-error" role="status">
          {failure} Last successful readings are retained with their sample
          time.
        </p>
      )}
      <div className="resource-graphs">
        <section className="graph-panel cpu-graph">
          <div className="graph-heading">
            <div>
              <span>CPU utilisation</span>
              <strong>{pct(d?.cpu?.percent)}</strong>
            </div>
            <p>
              {count(d?.cpu?.logical)} logical cores
              <span>
                {d?.cpu?.load
                  ? `Load ${d.cpu.load.map((n: number) => n.toFixed(2)).join(" / ")}`
                  : "Load unavailable"}
              </span>
            </p>
          </div>
          <Sparkline
            points={d?.history}
            field="cpu"
            label="Measured CPU utilisation history"
          />
          <div className="chart-footer">
            <span>Samples retained in memory</span>
            <span>{d?.history?.length || 0} / 120</span>
          </div>
        </section>
        <section className="graph-panel memory-graph">
          <div className="graph-heading">
            <div>
              <span>RAM in use</span>
              <strong>
                {m ? bytes(m.used) : "—"} <small>/ {bytes(m?.total)}</small>
              </strong>
            </div>
            <p>
              {m ? pct((m.used / m.total) * 100) : "—"}
              <span>{bytes(m?.available)} available</span>
            </p>
          </div>
          <Sparkline
            points={d?.history}
            field="memory"
            label="Measured RAM utilisation history"
          />
          <div className="chart-footer">
            <span>
              Cache {bytes(m?.cached)} · buffers {bytes(m?.buffers)}
            </span>
            <span>
              Swap {bytes(d?.swap?.used)} / {bytes(d?.swap?.total)}
            </span>
          </div>
        </section>
      </div>
      <dl className="host-ribbon">
        <Stat label="Processes" value={count(d?.process_count)} />
        <Stat label="Threads" value={count(d?.threads)} />
        <Stat
          label="Disk free"
          value={bytes(d?.disk?.free)}
          note={`of ${bytes(d?.disk?.total)}`}
        />
        <Stat
          label="Network ↓ / ↑"
          value={`${bytes(d?.rates?.net_rx)} / ${bytes(d?.rates?.net_tx)}`}
          note="per second · all interfaces"
        />
        <Stat
          label="Disk read / write"
          value={`${bytes(d?.rates?.disk_read)} / ${bytes(d?.rates?.disk_write)}`}
          note="per second"
        />
        <Stat label="Uptime" value={uptime(d?.uptime_seconds)} />
      </dl>
      <div className="operations-grid">
        <ProcessTable data={d} />
        <ActivityPanel data={activity} />
        <QuotaPanel data={quota} />
        <section className="ops-panel totals-panel">
          <div className="panel-heading">
            <div>
              <span className="section-index">04 / RECORDED USAGE</span>
              <h2>Hermes activity ledger</h2>
            </div>
            <span className="subtle-tag">All recorded sessions</span>
          </div>
          <dl className="ledger">
            <Stat label="API calls" value={short(t?.api_calls)} />
            <Stat label="Tool calls" value={short(t?.tool_calls)} />
            <Stat label="Input tokens" value={short(t?.input_tokens)} />
            <Stat label="Output tokens" value={short(t?.output_tokens)} />
            <Stat label="Cache reads" value={short(t?.cache_read_tokens)} />
            <Stat label="Reasoning tokens" value={short(t?.reasoning_tokens)} />
            <Stat label="Total sessions" value={count(t?.total)} />
            <Stat label="Started in 24h" value={count(t?.started_24h)} />
          </dl>
          <div className="source-line">
            {activity?.sources?.map((s: any) => (
              <span key={s.source}>
                {s.source || "unknown"} <b>{s.count}</b>
              </span>
            ))}
          </div>
          <p className="data-note">
            Recorded counters can be incomplete. Cache/reasoning counters may
            overlap token categories; do not sum them. Token totals are not
            subscription charges.
          </p>
        </section>
        <section className="ops-panel pressure-panel">
          <div className="panel-heading">
            <h2>Host pressure</h2>
            <span className="section-index">10s / 60s average</span>
          </div>
          {["cpu", "memory", "io"].map((key) => (
            <Pair
              key={key}
              label={
                key === "io" ? "I/O stalls" : `${key.toUpperCase()} stalls`
              }
              value={
                d?.pressure?.[key]?.some
                  ? `${pct(d.pressure[key].some.avg10)} / ${pct(d.pressure[key].some.avg60)}`
                  : "Unavailable"
              }
            />
          ))}
          <p className="data-note">
            Linux PSI: time tasks waited for resources, not resource
            utilisation.
          </p>
        </section>
        <section className="ops-panel transport-panel">
          <div className="panel-heading">
            <h2>Runtime & transport</h2>
            <span className="subtle-tag">Read only</span>
          </div>
          <Pair
            label="Gateway"
            value={
              activity?.gateway?.version
                ? `Hermes ${activity.gateway.version}`
                : "Unavailable"
            }
          />
          {activity?.gateway?.platforms?.map((p: any) => (
            <Pair key={p.name} label={p.name} value={p.state} />
          ))}
          <Pair
            label="HSUH chats / queued"
            value={`${count(activity?.hsuh?.conversations)} / ${count(activity?.hsuh?.queued)}`}
          />
          <div className="source-line">
            {activity?.delegations?.map((p: any) => (
              <span key={p.state}>
                Delegations {p.state} <b>{p.count}</b>
              </span>
            ))}
          </div>
        </section>
      </div>
      <footer className="overview-footer">
        <span>
          Host data: psutil + Linux /proc · session metadata: SQLite read-only ·
          quota: native Hermes usage
        </span>
        <span>OpenUI renderer · local assets · no external telemetry</span>
      </footer>
    </div>
  );
}

// A narrow OpenUI library: text, measurements, tables and local checklist state.
// No raw HTML, scripts, URLs, image sources, remote tools or model-driven requests.
const text = z.string().max(5000);
const Stack = defineComponent({
  name: "Stack",
  description: "A vertical group of UI elements.",
  props: z.object({ children: z.array(z.any()).max(40) }),
  component: ({ props }: any) => {
    const render = useRenderNode();
    return (
      <div className="gen-stack">
        {props.children.map((n: any, i: number) => (
          <React.Fragment key={i}>{render(n)}</React.Fragment>
        ))}
      </div>
    );
  },
});
const Heading = defineComponent({
  name: "Heading",
  description: "A short heading.",
  props: z.object({ text }),
  component: ({ props }: any) => <h3>{props.text}</h3>,
});
const Paragraph = defineComponent({
  name: "Paragraph",
  description: "Plain text explanation.",
  props: z.object({ text }),
  component: ({ props }: any) => <p>{props.text}</p>,
});
const Metric = defineComponent({
  name: "Metric",
  description: "A supplied fact, never invented live telemetry.",
  props: z.object({ label: text, value: text, note: text }),
  component: ({ props }: any) => (
    <div className="gen-metric">
      <span>{props.label}</span>
      <strong>{props.value}</strong>
      <small>{props.note}</small>
    </div>
  ),
});
const DataTable = defineComponent({
  name: "DataTable",
  description: "A bounded table of supplied text.",
  props: z.object({
    columns: z.array(text).max(8),
    rows: z.array(z.array(text).max(8)).max(50),
  }),
  component: ({ props }: any) => (
    <div className="gen-table">
      <table>
        <thead>
          <tr>
            {props.columns.map((v: string, i: number) => (
              <th key={i}>{v}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {props.rows.map((r: string[], i: number) => (
            <tr key={i}>
              {r.map((v, j) => (
                <td key={j}>{v}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  ),
});
function ChecklistView({ items }: any) {
  const [done, setDone] = useState<number[]>([]);
  return (
    <fieldset className="gen-checklist">
      <legend>Checklist · saved only in this view</legend>
      {items.map((v: string, i: number) => (
        <label key={i}>
          <input
            type="checkbox"
            checked={done.includes(i)}
            onChange={() =>
              setDone((old) =>
                old.includes(i) ? old.filter((x) => x !== i) : [...old, i],
              )
            }
          />
          <span>{v}</span>
        </label>
      ))}
    </fieldset>
  );
}
const Checklist = defineComponent({
  name: "Checklist",
  description: "Interactive checklist with local-only checkboxes.",
  props: z.object({ items: z.array(text).max(30) }),
  component: ({ props }: any) => <ChecklistView items={props.items} />,
});
const library = createLibrary({
  components: [Stack, Heading, Paragraph, Metric, DataTable, Checklist],
  root: "Stack",
});
const parser = createParser(library.toJSONSchema(), library.root);
export function isSafeOpenUI(source: string) {
  if (
    typeof source !== "string" ||
    source.length > 24000 ||
    source.split("\n").length > 150 ||
    /\b(?:Query|Mutation|Action)\s*\(/.test(source)
  )
    return false;
  try {
    const parsed = parser.parse(source);
    return !parsed.meta.errors.length && !parsed.meta.unresolved.length;
  } catch {
    return false;
  }
}

class RenderBoundary extends Component<
  { source: string; children: React.ReactNode },
  { failed: boolean }
> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  render() {
    return this.state.failed ? (
      <pre>{this.props.source}</pre>
    ) : (
      this.props.children
    );
  }
}
const roots = new Map<HTMLElement, Root>();
function renderOpenUI(target: HTMLElement, source: string) {
  if (!isSafeOpenUI(source)) {
    target.appendChild(
      Object.assign(document.createElement("pre"), {
        textContent: source.slice(0, 24000),
      }),
    );
    return;
  }
  const root = createRoot(target);
  roots.set(target, root);
  root.render(
    <RenderBoundary source={source}>
      <div className="generated-ui">
        <span className="gen-label">OpenUI · model-generated content</span>
        <Renderer
          response={source}
          library={library}
          isStreaming={false}
          toolProvider={{}}
          onAction={() => {}}
          onError={() => {}}
        />
      </div>
    </RenderBoundary>,
  );
}
function disposeOpenUI() {
  for (const [target, root] of roots) {
    root.unmount();
    roots.delete(target);
  }
}
// Explicit app-owned entry points. Neither grants an API/agent action to a model.
if (typeof window !== "undefined" && typeof document !== "undefined") {
  (window as any).HSUHOpenUI = {
    render: renderOpenUI,
    dispose: disposeOpenUI,
    version: "1.0.1",
  };
  const mount = document.getElementById("overview-root");
  if (mount) createRoot(mount).render(<Overview />);
}
export { library };
