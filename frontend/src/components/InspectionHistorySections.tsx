/**
 * Phase 9 inspection-details sections: Verification History, Audit History,
 * Evaluation Versions and the Report block. All data comes from the backend —
 * nothing here derives legal status; it only displays persisted records.
 */
import { useCallback, useEffect, useState } from "react";
import { Download, FileText, History as HistoryIcon, Loader2, RefreshCw, ShieldCheck } from "lucide-react";

import {
  fetchAuditLog,
  fetchEvaluationVersions,
  fetchReportMeta,
  fetchRuleVerifications,
  generateReport,
  reportDownloadUrl,
} from "../lib/inspections";
import type { AuditLogEntry, EvaluationVersion, OfficerVerificationRecord, ReportMeta } from "../types/api";

const card = "rounded-xl border border-brand-border bg-white shadow-xs";

function SectionShell({
  title,
  subtitle,
  icon: Icon,
  children,
}: {
  title: string;
  subtitle: string;
  icon: typeof HistoryIcon;
  children: React.ReactNode;
}) {
  return (
    <section className={card}>
      <div className="flex items-start gap-3 border-b border-brand-border px-5 py-4">
        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-brand-light">
          <Icon className="h-4.5 w-4.5 text-brand-green" aria-hidden="true" />
        </span>
        <div>
          <h3 className="text-sm font-semibold text-brand-dark">{title}</h3>
          <p className="mt-0.5 text-xs text-brand-muted">{subtitle}</p>
        </div>
      </div>
      <div className="px-5 py-4">{children}</div>
    </section>
  );
}

function Empty({ text }: { text: string }) {
  return <p className="py-2 text-sm text-brand-muted">{text}</p>;
}

function fmt(ts: string): string {
  return new Date(ts).toLocaleString();
}

/* --------------------------- Verification History --------------------------- */

export function VerificationHistorySection({ inspectionId }: { inspectionId: string }) {
  const [rows, setRows] = useState<OfficerVerificationRecord[] | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchRuleVerifications(inspectionId)
      .then((r) => !cancelled && setRows(r))
      .catch(() => !cancelled && setRows([]));
    return () => {
      cancelled = true;
    };
  }, [inspectionId]);

  return (
    <SectionShell
      title="Verification History"
      subtitle="Every officer decision, newest first — earlier decisions are never hidden or overwritten."
      icon={ShieldCheck}
    >
      {rows === null ? (
        <Loader2 className="h-4 w-4 animate-spin text-brand-muted" aria-label="Loading" />
      ) : rows.length === 0 ? (
        <Empty text="No officer verifications recorded yet." />
      ) : (
        <ul className="divide-y divide-brand-border">
          {rows.map((v) => (
            <li key={v.id} className="py-3 first:pt-0 last:pb-0">
              <div className="flex flex-wrap items-center gap-2">
                <span className="rounded-full bg-brand-light px-2.5 py-0.5 text-[11px] font-semibold text-brand-green">
                  {v.decision.replaceAll("_", " ")}
                </span>
                <span className="text-xs text-brand-muted">rule evaluation #{v.rule_evaluation_id}</span>
                <span className="text-xs text-brand-muted">· evaluation #{v.evaluation_id}</span>
              </div>
              {v.comment && <p className="mt-1.5 text-sm text-brand-dark">“{v.comment}”</p>}
              <p className="mt-1 text-xs text-brand-muted">
                {v.officer_identifier} · {fmt(v.created_at)}
              </p>
            </li>
          ))}
        </ul>
      )}
    </SectionShell>
  );
}

/* ------------------------------- Audit History ------------------------------- */

export function AuditHistorySection({ inspectionId }: { inspectionId: string }) {
  const [rows, setRows] = useState<AuditLogEntry[] | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchAuditLog(inspectionId)
      .then((r) => !cancelled && setRows(r))
      .catch(() => !cancelled && setRows([]));
    return () => {
      cancelled = true;
    };
  }, [inspectionId]);

  return (
    <SectionShell
      title="Audit History"
      subtitle="Append-only record of every action — entries are never edited or deleted."
      icon={HistoryIcon}
    >
      {rows === null ? (
        <Loader2 className="h-4 w-4 animate-spin text-brand-muted" aria-label="Loading" />
      ) : rows.length === 0 ? (
        <Empty text="No audit entries recorded yet." />
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-[11px] font-semibold tracking-[0.12em] text-brand-muted uppercase">
                <th scope="col" className="py-2 pr-4">Timestamp</th>
                <th scope="col" className="py-2 pr-4">Actor</th>
                <th scope="col" className="py-2 pr-4">Action</th>
                <th scope="col" className="py-2 pr-4">Decision</th>
                <th scope="col" className="py-2 pr-4">Previous</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((a) => (
                <tr key={a.id} className="border-t border-brand-border">
                  <td className="py-2 pr-4 whitespace-nowrap text-brand-muted">{fmt(a.timestamp)}</td>
                  <td className="py-2 pr-4 text-brand-dark">{a.actor}</td>
                  <td className="py-2 pr-4 text-brand-dark">{a.action.replaceAll("_", " ")}</td>
                  <td className="py-2 pr-4 text-brand-dark">{a.decision ?? "—"}</td>
                  <td className="py-2 pr-4 text-brand-muted">{a.previous_state ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </SectionShell>
  );
}

/* ---------------------------- Evaluation Versions ---------------------------- */

export function EvaluationVersionsSection({
  inspectionId,
  refreshKey,
}: {
  inspectionId: string;
  refreshKey?: number;
}) {
  const [rows, setRows] = useState<EvaluationVersion[] | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchEvaluationVersions(inspectionId)
      .then((r) => !cancelled && setRows(r))
      .catch(() => !cancelled && setRows([]));
    return () => {
      cancelled = true;
    };
  }, [inspectionId, refreshKey]);

  return (
    <SectionShell
      title="Evaluation Versions"
      subtitle="Each assessment is an immutable version — viewing history never edits it."
      icon={RefreshCw}
    >
      {rows === null ? (
        <Loader2 className="h-4 w-4 animate-spin text-brand-muted" aria-label="Loading" />
      ) : rows.length === 0 ? (
        <Empty text="No evaluation has been run yet." />
      ) : (
        <ul className="divide-y divide-brand-border">
          {[...rows].reverse().map((v) => (
            <li key={v.evaluation_id} className="flex flex-wrap items-center gap-x-3 gap-y-1 py-2.5 first:pt-0 last:pb-0">
              <span className="text-sm font-medium text-brand-dark">Evaluation v{v.evaluation_version}</span>
              <span className="rounded-full bg-brand-light px-2 py-0.5 text-[11px] font-semibold text-brand-green">
                {v.overall_status.replaceAll("_", " ")}
              </span>
              <span className="text-xs text-brand-muted">
                {fmt(v.created_at)} · engine {v.engine_version} ·{" "}
                {v.has_officer_verification ? "officer verified" : "not yet verified for this evaluation"}
              </span>
            </li>
          ))}
        </ul>
      )}
    </SectionShell>
  );
}

/* ---------------------------------- Report ---------------------------------- */

export function ReportSection({ inspectionId }: { inspectionId: string }) {
  const [meta, setMeta] = useState<ReportMeta | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    fetchReportMeta(inspectionId)
      .then(setMeta)
      .catch(() => setMeta(null));
  }, [inspectionId]);

  useEffect(load, [load]);

  const generate = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      setMeta(await generateReport(inspectionId));
    } catch (err) {
      setError(
        err instanceof Error && err.message.includes("No evaluation")
          ? "Run an assessment before generating a report."
          : "Report generation failed. Please try again.",
      );
    } finally {
      setBusy(false);
    }
  }, [inspectionId]);

  return (
    <SectionShell
      title="Inspection Assessment Report"
      subtitle="Server-generated PDF from persisted data — an assessment record, not a legal certification."
      icon={FileText}
    >
      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={generate}
          disabled={busy}
          className="inline-flex items-center gap-2 rounded-lg bg-brand-dark px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-brand-green disabled:opacity-60"
        >
          {busy ? (
            <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
          ) : (
            <FileText className="h-4 w-4" aria-hidden="true" />
          )}
          {meta ? "Regenerate Report" : "Generate Report"}
        </button>
        {meta && (
          <a
            href={reportDownloadUrl(inspectionId)}
            className="inline-flex items-center gap-2 rounded-lg border border-brand-border bg-white px-4 py-2 text-sm font-medium text-brand-dark transition-colors hover:border-brand-green/40"
          >
            <Download className="h-4 w-4" aria-hidden="true" />
            Download Report (v{meta.evaluation_version})
          </a>
        )}
      </div>
      {error && <p className="mt-3 text-sm text-red-700">{error}</p>}
      {meta && (
        <dl className="mt-4 space-y-1 text-xs text-brand-muted">
          <div className="flex gap-2">
            <dt className="font-medium text-brand-dark">Report generated:</dt>
            <dd>{fmt(meta.generated_at)}</dd>
          </div>
          <div className="flex gap-2">
            <dt className="font-medium text-brand-dark">Evaluation:</dt>
            <dd>v{meta.evaluation_version}</dd>
          </div>
          <div className="flex flex-wrap gap-2">
            <dt className="font-medium text-brand-dark">Report Integrity Hash (SHA-256):</dt>
            <dd className="break-all font-mono">{meta.report_hash}</dd>
          </div>
          <p className="pt-1 text-[11px]">The hash verifies the file has not been altered — it is not a digital signature.</p>
        </dl>
      )}
    </SectionShell>
  );
}
