/**
 * Phase 9 database-backed views: dashboard overview, Inspection History and
 * Reports. All rows, filters, pagination and metrics come from the backend —
 * nothing is filtered locally from a preloaded dataset, and no mock records
 * are created or displayed.
 */
import { useCallback, useEffect, useState } from "react";
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  CircleHelp,
  ClipboardCheck,
  Eye,
  Search,
} from "lucide-react";

import { fetchDashboardMetrics, fetchInspectionHistory } from "../lib/inspections";
import type { DashboardMetrics, InspectionHistory } from "../types/api";

const card = "rounded-2xl border border-brand-border bg-brand-white";
const inputBase =
  "h-10 w-full rounded-lg border border-brand-border bg-white px-3 text-sm text-brand-dark placeholder:text-brand-muted/70";
const btnTable =
  "inline-flex items-center gap-1.5 rounded-lg border border-brand-border bg-white px-3 py-1.5 text-xs font-medium text-brand-dark transition-colors hover:bg-brand-light";

const ASSESSMENT_META: Record<string, { label: string; badge: string }> = {
  COMPLIANT: { label: "Compliant", badge: "bg-green-50 text-green-700 border-green-200" },
  NON_COMPLIANT: { label: "Non-Compliant", badge: "bg-red-50 text-red-700 border-red-200" },
  REVIEW_REQUIRED: { label: "Review Required", badge: "bg-amber-50 text-amber-700 border-amber-200" },
  INCOMPLETE: { label: "Incomplete", badge: "bg-gray-50 text-gray-600 border-gray-200" },
};

export function AssessmentBadge({ status }: { status: string | null }) {
  if (!status) {
    return (
      <span className="inline-flex items-center whitespace-nowrap rounded-full border border-gray-200 bg-gray-50 px-2.5 py-1 text-xs font-medium text-gray-500">
        No assessment
      </span>
    );
  }
  const meta = ASSESSMENT_META[status] ?? { label: status, badge: "bg-gray-50 text-gray-600 border-gray-200" };
  return (
    <span className={`inline-flex items-center whitespace-nowrap rounded-full border px-2.5 py-1 text-xs font-medium ${meta.badge}`}>
      {meta.label}
    </span>
  );
}

function fmtDate(ts: string): string {
  return new Date(ts).toLocaleDateString(undefined, { day: "2-digit", month: "short", year: "numeric" });
}

/* ------------------------------ history view ------------------------------ */

const STATUS_FILTERS = [
  { value: "", label: "All Statuses" },
  { value: "COMPLIANT", label: "Compliant" },
  { value: "NON_COMPLIANT", label: "Non-Compliant" },
  { value: "REVIEW_REQUIRED", label: "Review Required" },
  { value: "INCOMPLETE", label: "Incomplete" },
];

export function InspectionHistoryView({
  onOpenInspection,
  onNewInspection,
}: {
  onOpenInspection: (inspectionId: string) => void;
  onNewInspection: () => void;
}) {
  const [page, setPage] = useState(1);
  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [data, setData] = useState<InspectionHistory | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(() => {
    setLoading(true);
    fetchInspectionHistory({
      page,
      page_size: 10,
      status: status || null,
      search: search || null,
      date_from: dateFrom || null,
    })
      .then(setData)
      .catch(() => setData(null))
      .finally(() => setLoading(false));
  }, [page, search, status, dateFrom]);

  useEffect(load, [load]);

  const hasFilters = search !== "" || status !== "" || dateFrom !== "";
  const clearFilters = () => {
    setSearchInput("");
    setSearch("");
    setStatus("");
    setDateFrom("");
    setPage(1);
  };

  return (
    <div className="mx-auto max-w-7xl animate-fade-up px-4 pb-20 sm:px-6 lg:px-8">
      <div className="pt-8 sm:pt-12">
        <p className="text-[11px] font-semibold tracking-[0.24em] text-brand-green uppercase">History</p>
        <h1 className="mt-2 text-3xl font-light tracking-tight text-brand-dark">Inspection History</h1>
        <p className="mt-2 max-w-2xl text-sm text-brand-muted">
          All past inspections with their automated and officer-verified assessments. No compliance score is
          computed — status is an assessment outcome, not a certification.
        </p>

        {/* Filters — server-side, never local filtering of a preloaded set */}
        <div className="mb-5 mt-6 flex flex-col gap-3 md:flex-row md:items-center">
          <div className="relative flex-1">
            <Search className="pointer-events-none absolute top-1/2 left-3.5 h-4 w-4 -translate-y-1/2 text-brand-muted" aria-hidden="true" />
            <input
              type="search"
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  setPage(1);
                  setSearch(searchInput.trim());
                }
              }}
              placeholder="Search by inspection ID, product or manufacturer — press Enter"
              aria-label="Search inspections"
              className={`${inputBase} pl-10`}
            />
          </div>
          <div className="flex flex-wrap gap-3">
            <select
              value={status}
              onChange={(e) => {
                setPage(1);
                setStatus(e.target.value);
              }}
              aria-label="Filter by status"
              className={`${inputBase} appearance-none pr-9 md:w-44`}
            >
              {STATUS_FILTERS.map((f) => (
                <option key={f.value} value={f.value}>
                  {f.label}
                </option>
              ))}
            </select>
            <input
              type="date"
              value={dateFrom}
              onChange={(e) => {
                setPage(1);
                setDateFrom(e.target.value);
              }}
              aria-label="Filter from date"
              className={`${inputBase} md:w-40`}
            />
          </div>
        </div>

        {loading ? (
          <p className="py-10 text-sm text-brand-muted">Loading inspections…</p>
        ) : !data || data.items.length === 0 ? (
          <div className={`${card} p-10 text-center`}>
            <ClipboardCheck className="mx-auto h-8 w-8 text-brand-muted" aria-hidden="true" />
            <p className="mt-3 text-sm font-medium text-brand-dark">
              {hasFilters ? "No matching inspections" : "No inspections yet"}
            </p>
            <p className="mt-1 text-sm text-brand-muted">
              {hasFilters
                ? "Try adjusting your search or filters."
                : "Start your first product inspection to begin building your compliance history."}
            </p>
            {hasFilters ? (
              <button type="button" onClick={clearFilters} className="mt-4 text-sm font-medium text-brand-green underline">
                Clear Filters
              </button>
            ) : (
              <button type="button" onClick={onNewInspection} className="mt-4 text-sm font-medium text-brand-green underline">
                Start Inspection
              </button>
            )}
          </div>
        ) : (
          <>
            <div className={`${card} overflow-hidden`}>
              <div className="hidden overflow-x-auto md:block">
                <table className="w-full text-sm">
                  <caption className="sr-only">Inspection history</caption>
                  <thead>
                    <tr className="bg-brand-light/60 text-left text-[11px] font-semibold tracking-[0.14em] text-brand-muted uppercase">
                      <th scope="col" className="px-6 py-4">Inspection ID</th>
                      <th scope="col" className="px-6 py-4">Product</th>
                      <th scope="col" className="px-6 py-4">Date</th>
                      <th scope="col" className="px-6 py-4">Automated Status</th>
                      <th scope="col" className="px-6 py-4">Officer Verification</th>
                      <th scope="col" className="px-6 py-4">Effective Status</th>
                      <th scope="col" className="px-6 py-4">Evaluation Version</th>
                      <th scope="col" className="px-6 py-4 text-right">Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.items.map((row) => (
                      <tr
                        key={row.inspection_id}
                        className="cursor-pointer border-t border-brand-border transition-colors hover:bg-brand-cream/70"
                        onClick={() => onOpenInspection(row.inspection_id)}
                      >
                        <td className="px-6 py-4 font-medium whitespace-nowrap text-brand-dark">{row.inspection_id}</td>
                        <td className="px-6 py-4 text-brand-dark">{row.product_name ?? "—"}</td>
                        <td className="px-6 py-4 whitespace-nowrap text-brand-muted">{fmtDate(row.inspection_date)}</td>
                        <td className="px-6 py-4"><AssessmentBadge status={row.automated_status} /></td>
                        <td className="px-6 py-4 text-xs text-brand-muted">
                          {row.verification_required ? "Verified" : "—"}
                        </td>
                        <td className="px-6 py-4"><AssessmentBadge status={row.effective_status} /></td>
                        <td className="px-6 py-4 text-brand-muted">{row.evaluation_version ? `v${row.evaluation_version}` : "—"}</td>
                        <td className="px-6 py-4 text-right">
                          <button
                            type="button"
                            className={btnTable}
                            onClick={(e) => {
                              e.stopPropagation();
                              onOpenInspection(row.inspection_id);
                            }}
                          >
                            <Eye className="h-3.5 w-3.5" aria-hidden="true" />
                            View
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {/* Mobile cards */}
              <ul className="divide-y divide-brand-border md:hidden">
                {data.items.map((row) => (
                  <li key={row.inspection_id} className="p-4">
                    <button type="button" onClick={() => onOpenInspection(row.inspection_id)} className="w-full text-left">
                      <div className="flex items-center justify-between gap-3">
                        <span className="text-sm font-medium text-brand-dark">{row.inspection_id}</span>
                        <AssessmentBadge status={row.effective_status} />
                      </div>
                      <p className="mt-1.5 text-base font-medium text-brand-dark">{row.product_name ?? "—"}</p>
                      <p className="mt-1 text-xs text-brand-muted">
                        {fmtDate(row.inspection_date)} · automated {row.automated_status ? row.automated_status.replaceAll("_", " ").toLowerCase() : "n/a"}
                        {row.evaluation_version ? ` · v${row.evaluation_version}` : ""}
                      </p>
                    </button>
                  </li>
                ))}
              </ul>
            </div>

            {/* Pagination */}
            <div className="mt-4 flex items-center justify-between">
              <p className="text-xs text-brand-muted">
                Page {data.page} of {Math.max(1, data.pages)} · {data.total} inspection{data.total === 1 ? "" : "s"}
              </p>
              <div className="flex gap-2">
                <button
                  type="button"
                  className={btnTable}
                  disabled={data.page <= 1}
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                >
                  <ChevronLeft className="h-3.5 w-3.5" aria-hidden="true" /> Previous
                </button>
                <button
                  type="button"
                  className={btnTable}
                  disabled={data.page >= data.pages}
                  onClick={() => setPage((p) => p + 1)}
                >
                  Next <ChevronRight className="h-3.5 w-3.5" aria-hidden="true" />
                </button>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

/* ----------------------------- reports view ------------------------------ */

export function ReportsView({
  onOpenInspection,
  onNewInspection,
}: {
  onOpenInspection: (inspectionId: string) => void;
  onNewInspection: () => void;
}) {
  const [page, setPage] = useState(1);
  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");
  const [data, setData] = useState<InspectionHistory | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(() => {
    setLoading(true);
    fetchInspectionHistory({ page, page_size: 10, search: search || null })
      .then(setData)
      .catch(() => setData(null))
      .finally(() => setLoading(false));
  }, [page, search]);

  useEffect(load, [load]);

  return (
    <div className="mx-auto max-w-7xl animate-fade-up px-4 pb-20 sm:px-6 lg:px-8">
      <div className="pt-8 sm:pt-12">
        <p className="text-[11px] font-semibold tracking-[0.24em] text-brand-green uppercase">Reports</p>
        <h1 className="mt-2 text-3xl font-light tracking-tight text-brand-dark">Assessment Reports</h1>
        <p className="mt-2 max-w-2xl text-sm text-brand-muted">
          Open an inspection to generate or download its Inspection Assessment Report (PDF). Reports are bound to a
          specific evaluation version and are not legal certifications.
        </p>

        <div className="mb-5 mt-6 flex flex-col gap-3 md:flex-row">
          <div className="relative flex-1">
            <Search className="pointer-events-none absolute top-1/2 left-3.5 h-4 w-4 -translate-y-1/2 text-brand-muted" aria-hidden="true" />
            <input
              type="search"
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  setPage(1);
                  setSearch(searchInput.trim());
                }
              }}
              placeholder="Search by inspection ID, product or manufacturer — press Enter"
              aria-label="Search inspections"
              className={`${inputBase} pl-10`}
            />
          </div>
        </div>

        {loading ? (
          <p className="py-10 text-sm text-brand-muted">Loading…</p>
        ) : !data || data.items.length === 0 ? (
          <div className={`${card} p-10 text-center`}>
            <p className="text-sm font-medium text-brand-dark">No inspections found</p>
            <button type="button" onClick={onNewInspection} className="mt-3 text-sm font-medium text-brand-green underline">
              Start Inspection
            </button>
          </div>
        ) : (
          <>
            <div className={`${card} overflow-hidden`}>
              <div className="hidden overflow-x-auto md:block">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="bg-brand-light/60 text-left text-[11px] font-semibold tracking-[0.14em] text-brand-muted uppercase">
                      <th scope="col" className="px-6 py-4">Inspection ID</th>
                      <th scope="col" className="px-6 py-4">Product</th>
                      <th scope="col" className="px-6 py-4">Date</th>
                      <th scope="col" className="px-6 py-4">Automated Status</th>
                      <th scope="col" className="px-6 py-4">Effective Status</th>
                      <th scope="col" className="px-6 py-4 text-right">Report</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.items.map((row) => (
                      <tr key={row.inspection_id} className="border-t border-brand-border transition-colors hover:bg-brand-cream/70">
                        <td className="px-6 py-4 font-medium whitespace-nowrap text-brand-dark">{row.inspection_id}</td>
                        <td className="px-6 py-4 text-brand-dark">{row.product_name ?? "—"}</td>
                        <td className="px-6 py-4 whitespace-nowrap text-brand-muted">{fmtDate(row.inspection_date)}</td>
                        <td className="px-6 py-4"><AssessmentBadge status={row.automated_status} /></td>
                        <td className="px-6 py-4"><AssessmentBadge status={row.effective_status} /></td>
                        <td className="px-6 py-4 text-right">
                          <button type="button" className={btnTable} onClick={() => onOpenInspection(row.inspection_id)}>
                            <Eye className="h-3.5 w-3.5" aria-hidden="true" />
                            Open & Report
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <ul className="divide-y divide-brand-border md:hidden">
                {data.items.map((row) => (
                  <li key={row.inspection_id} className="p-4">
                    <div className="flex items-center justify-between gap-3">
                      <span className="text-sm font-medium text-brand-dark">{row.inspection_id}</span>
                      <AssessmentBadge status={row.effective_status} />
                    </div>
                    <p className="mt-1.5 text-base font-medium text-brand-dark">{row.product_name ?? "—"}</p>
                    <button type="button" onClick={() => onOpenInspection(row.inspection_id)} className={`${btnTable} mt-3 w-full justify-center py-2`}>
                      <Eye className="h-3.5 w-3.5" aria-hidden="true" /> Open & Report
                    </button>
                  </li>
                ))}
              </ul>
            </div>
            <div className="mt-4 flex items-center justify-between">
              <p className="text-xs text-brand-muted">
                Page {data.page} of {Math.max(1, data.pages)} · {data.total} inspection{data.total === 1 ? "" : "s"}
              </p>
              <div className="flex gap-2">
                <button type="button" className={btnTable} disabled={data.page <= 1} onClick={() => setPage((p) => Math.max(1, p - 1))}>
                  <ChevronLeft className="h-3.5 w-3.5" aria-hidden="true" /> Previous
                </button>
                <button type="button" className={btnTable} disabled={data.page >= data.pages} onClick={() => setPage((p) => p + 1)}>
                  Next <ChevronRight className="h-3.5 w-3.5" aria-hidden="true" />
                </button>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

/* ---------------------------- dashboard metrics ---------------------------- */

const METRIC_ICONS = {
  total: ClipboardCheck,
  compliant: CheckCircle2,
  review: CircleHelp,
  violation: AlertTriangle,
} as const;

export function DashboardMetricsCards({ onNavigate }: { onNavigate: (view: "history") => void }) {
  const [metrics, setMetrics] = useState<DashboardMetrics | null>(null);

  useEffect(() => {
    fetchDashboardMetrics()
      .then(setMetrics)
      .catch(() => setMetrics(null));
  }, []);

  if (!metrics) {
    return (
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className={`${card} p-6`}>
            <div className="h-5 w-24 rounded bg-brand-light" />
            <div className="mt-5 h-8 w-14 rounded bg-brand-light" />
            <div className="mt-1 h-3 w-20 rounded bg-brand-light/60" />
          </div>
        ))}
      </div>
    );
  }

  const automated = metrics.automated ?? {};
  const effective = metrics.officer_effective ?? {};
  const cards = [
    { key: "total", label: "Total Inspections", value: metrics.total_inspections },
    { key: "compliant", label: "Compliant Assessments", value: effective.COMPLIANT ?? 0 },
    { key: "review", label: "Requires Review", value: (effective.REVIEW_REQUIRED ?? 0) + (effective.INCOMPLETE ?? 0) },
    { key: "violation", label: "Non-Compliant Assessments", value: effective.NON_COMPLIANT ?? 0 },
  ];
  return (
    <>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {cards.map((m) => {
          const Icon = METRIC_ICONS[m.key as keyof typeof METRIC_ICONS];
          return (
            <div key={m.key} className={`${card} group p-6 transition-all duration-300 hover:-translate-y-0.5 hover:border-brand-green/30 hover:shadow-sm`}>
              <span className="flex h-10 w-10 items-center justify-center rounded-lg bg-brand-light">
                <Icon className="h-5 w-5 text-brand-green" aria-hidden="true" />
              </span>
              <p className="mt-5 text-3xl font-light tracking-tight text-brand-dark">{m.value}</p>
              <p className="mt-1 text-sm font-medium text-brand-muted">{m.label}</p>
            </div>
          );
        })}
      </div>

      {/* Automated vs officer-effective, side by side — officer data never
          silently replaces automated statistics. */}
      <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-2">
        <div className={`${card} p-6`}>
          <h3 className="text-xs font-semibold tracking-[0.14em] text-brand-muted uppercase">Automated Assessment</h3>
          <ul className="mt-4 space-y-2 text-sm">
            {["COMPLIANT", "NON_COMPLIANT", "REVIEW_REQUIRED", "INCOMPLETE"].map((s) => (
              <li key={s} className="flex items-center justify-between">
                <span className="text-brand-dark">{s.replaceAll("_", " ").toLowerCase()}</span>
                <span className="font-medium text-brand-dark">{automated[s] ?? 0}</span>
              </li>
            ))}
          </ul>
        </div>
        <div className={`${card} p-6`}>
          <h3 className="text-xs font-semibold tracking-[0.14em] text-brand-muted uppercase">Officer-Verified Assessment</h3>
          <ul className="mt-4 space-y-2 text-sm">
            {["COMPLIANT", "NON_COMPLIANT", "REVIEW_REQUIRED", "INCOMPLETE"].map((s) => (
              <li key={s} className="flex items-center justify-between">
                <span className="text-brand-dark">{s.replaceAll("_", " ").toLowerCase()}</span>
                <span className="font-medium text-brand-dark">{effective[s] ?? 0}</span>
              </li>
            ))}
          </ul>
        </div>
      </div>

      {/* Recent inspections — real rows or an honest empty state */}
      <div className={`${card} mt-4 overflow-hidden`}>
        <div className="flex items-center justify-between px-6 py-4">
          <h3 className="text-xs font-semibold tracking-[0.14em] text-brand-muted uppercase">Recent Inspections</h3>
          <button type="button" onClick={() => onNavigate("history")} className="inline-flex items-center gap-1 text-sm font-medium text-brand-green">
            View all <ArrowRight className="h-3.5 w-3.5" aria-hidden="true" />
          </button>
        </div>
        {metrics.recent_inspections.length === 0 ? (
          <p className="px-6 pb-6 text-sm text-brand-muted">No inspections yet — metrics will appear here after the first inspection.</p>
        ) : (
          <ul className="divide-y divide-brand-border">
            {metrics.recent_inspections.map((r) => (
              <li key={r.inspection_id} className="flex flex-wrap items-center justify-between gap-2 px-6 py-3">
                <span className="text-sm font-medium text-brand-dark">{r.inspection_id}</span>
                <span className="text-sm text-brand-dark">{r.product_name ?? "—"}</span>
                <span className="text-xs text-brand-muted">{fmtDate(r.created_at)}</span>
                <AssessmentBadge status={r.effective_status ?? r.automated_status} />
              </li>
            ))}
          </ul>
        )}
      </div>
    </>
  );
}
