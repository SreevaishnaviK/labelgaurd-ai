import { useState } from "react";
// Panel state (which rule row is expanded) is local; API state lives in the
// OcrResultView owner so the run button and error banner stay in sync with
// the rest of the result screen.
import {
  AlertTriangle,
  Check,
  ChevronDown,
  ChevronRight,
  Crosshair,
  HelpCircle,
  Loader2,
  MinusCircle,
  Play,
  RefreshCw,
  Scale,
  X,
} from "lucide-react";
import type { Evaluation, OCRBlock, RuleEvaluationStatus, RuleResult } from "../types/api";

const btnPrimary =
  "inline-flex items-center justify-center gap-2 rounded-lg bg-brand-dark px-5 py-2.5 text-sm font-medium text-brand-white transition-colors hover:bg-brand-green";
const btnSecondary =
  "inline-flex items-center justify-center gap-2 rounded-lg border border-brand-border bg-brand-white px-5 py-2.5 text-sm font-medium text-brand-dark transition-colors hover:border-brand-green/40 hover:bg-brand-light";

const STATUS_META: Record<
  RuleEvaluationStatus,
  { label: string; icon: typeof Check; tone: string; dot: string }
> = {
  COMPLIANT: {
    label: "Compliant",
    icon: Check,
    tone: "bg-brand-green/10 text-brand-green",
    dot: "text-brand-green",
  },
  VIOLATION: {
    label: "Violation",
    icon: X,
    tone: "bg-brand-danger/10 text-brand-danger",
    dot: "text-brand-danger",
  },
  REVIEW_REQUIRED: {
    label: "Review required",
    icon: AlertTriangle,
    tone: "bg-amber-500/10 text-amber-600",
    dot: "text-amber-500",
  },
  NOT_VERIFIABLE: {
    label: "Not verifiable",
    icon: HelpCircle,
    tone: "bg-brand-muted/10 text-brand-muted",
    dot: "text-brand-muted",
  },
  NOT_APPLICABLE: {
    label: "Not applicable",
    icon: MinusCircle,
    tone: "bg-brand-muted/10 text-brand-muted",
    dot: "text-brand-muted",
  },
};

const OVERALL_META: Record<
  string,
  { label: string; tone: string }
> = {
  COMPLIANT: { label: "Compliant", tone: "bg-brand-green/10 text-brand-green" },
  NON_COMPLIANT: { label: "Non-compliant", tone: "bg-brand-danger/10 text-brand-danger" },
  REVIEW_REQUIRED: { label: "Review required", tone: "bg-amber-500/10 text-amber-600" },
  INCOMPLETE: { label: "Incomplete", tone: "bg-brand-muted/10 text-brand-muted" },
};

function resultLine(result: RuleResult): string {
  const actual = result.actual_information ?? {};
  const first = Object.entries(actual).find(([, v]) => v !== null && v !== undefined && v !== "");
  return first ? `${first[0].replace(/_/g, " ")}: ${String(first[1])}` : result.rule_title;
}

function RuleRow({
  result,
  evidenceBlocks,
  activeBlockId,
  onSelectBlock,
}: {
  result: RuleResult;
  evidenceBlocks: { block: OCRBlock; page: number }[];
  activeBlockId: string | null;
  onSelectBlock: (block: OCRBlock | null) => void;
}) {
  const [open, setOpen] = useState(false);
  const meta = STATUS_META[result.status] ?? STATUS_META.NOT_VERIFIABLE;
  const Icon = meta.icon;
  const isHighlighting =
    activeBlockId !== null &&
    evidenceBlocks.some(({ block }) => block.block_id === activeBlockId);

  return (
    <li className={`rounded-xl border transition-colors ${
      isHighlighting ? "border-brand-green bg-brand-green/5" : "border-brand-border bg-brand-cream"
    }`}>
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        className="flex w-full items-center gap-3 p-4 text-left"
      >
        <span className={`inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-full ${meta.tone}`}>
          <Icon className="h-4 w-4" aria-hidden="true" />
        </span>
        <span className="min-w-0 flex-1">
          <span className="block truncate text-sm font-medium text-brand-dark">{result.rule_title}</span>
          <span className="mt-0.5 block truncate text-xs text-brand-muted">
            Rule {result.rule_number} · {resultLine(result)}
          </span>
        </span>
        <span className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${meta.tone}`}>
          {meta.label}
        </span>
        {open ? (
          <ChevronDown className="h-4 w-4 shrink-0 text-brand-muted" aria-hidden="true" />
        ) : (
          <ChevronRight className="h-4 w-4 shrink-0 text-brand-muted" aria-hidden="true" />
        )}
      </button>

      {open && (
        <div className="border-t border-brand-border px-4 py-3 text-sm">
          <p className="leading-relaxed text-brand-dark">{result.finding}</p>
          <dl className="mt-3 grid gap-x-6 gap-y-1 text-xs sm:grid-cols-2">
            <div className="flex gap-1">
              <dt className="text-brand-muted">Source:</dt>
              <dd className="text-brand-dark">
                {(result.source?.document as string) ?? "Legal Metrology (Packaged Commodities) Rules, 2011"}
                {result.source?.page ? ` · p. ${result.source.page}` : ""}
              </dd>
            </div>
            {result.confidence != null && (
              <div className="flex gap-1">
                <dt className="text-brand-muted">Engine confidence:</dt>
                <dd className="text-brand-dark">{Math.round(result.confidence * 100)}%</dd>
              </div>
            )}
            {result.requires_officer_verification && (
              <div className="flex gap-1 sm:col-span-2">
                <dt className="text-amber-600">Requires officer verification</dt>
              </div>
            )}
          </dl>
          {evidenceBlocks.length > 0 ? (
            <div className="mt-3 flex flex-wrap gap-2">
              {evidenceBlocks.map(({ block, page }) => (
                <button
                  key={block.block_id}
                  type="button"
                  onClick={() =>
                    onSelectBlock(activeBlockId === block.block_id ? null : block)
                  }
                  className={`inline-flex max-w-full items-center gap-1.5 rounded-md border px-2 py-1 font-mono text-[11px] transition-colors ${
                    activeBlockId === block.block_id
                      ? "border-brand-green bg-brand-green/10 text-brand-green"
                      : "border-brand-border bg-brand-white text-brand-muted hover:border-brand-green/40 hover:text-brand-dark"
                  }`}
                  title={block.text}
                >
                  <Crosshair className="h-3 w-3 shrink-0" aria-hidden="true" />
                  <span className="truncate">
                    {block.block_id} (p.{page})
                  </span>
                </button>
              ))}
            </div>
          ) : (
            <p className="mt-3 text-xs text-brand-muted">
              No OCR evidence referenced for this result.
            </p>
          )}
        </div>
      )}
    </li>
  );
}

function OverallStatus({ evaluation }: { evaluation: Evaluation }) {
  const meta = OVERALL_META[evaluation.overall_status] ?? OVERALL_META.INCOMPLETE;
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
      <p className="text-sm text-brand-muted">Overall status</p>
      <span className={`rounded-full px-3 py-1 text-xs font-semibold uppercase tracking-wide ${meta.tone}`}>
        {meta.label}
      </span>
      <p className="font-mono text-[11px] text-brand-muted">
        engine {evaluation.engine_version} · assessment #{evaluation.evaluation_version}
      </p>
    </div>
  );
}

export default function CompliancePanel({
  evaluation,
  blocksById,
  activeBlock,
  onSelectBlock,
  onRunEvaluation,
  evaluating,
  evaluateError,
}: {
  evaluation: Evaluation | null;
  blocksById: Map<string, OCRBlock>;
  activeBlock: OCRBlock | null;
  onSelectBlock: (block: OCRBlock | null) => void;
  onRunEvaluation: () => void;
  evaluating: boolean;
  evaluateError: string | null;
}) {
  const hasEvaluation = evaluation !== null;
  const counts = hasEvaluation
    ? evaluation.results.reduce<Record<string, number>>((acc, result) => {
        acc[result.status] = (acc[result.status] ?? 0) + 1;
        return acc;
      }, {})
    : {};

  return (
    <section className="mt-6 rounded-2xl border border-brand-border bg-brand-white p-6" aria-labelledby="compliance-heading">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 id="compliance-heading" className="text-lg font-medium text-brand-dark">
            AI-Assisted Compliance Assessment
          </h2>
          <p className="mt-1 text-sm text-brand-muted">
            Automated check of extracted label information against Legal
            Metrology (Packaged Commodities) Rules, 2011. This is an
            assessment, not legal certification.
          </p>
        </div>
        <button
          type="button"
          onClick={onRunEvaluation}
          disabled={evaluating}
          className={hasEvaluation ? btnSecondary : btnPrimary}
        >
          {evaluating ? (
            <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
          ) : hasEvaluation ? (
            <RefreshCw className="h-4 w-4" aria-hidden="true" />
          ) : (
            <Play className="h-4 w-4" aria-hidden="true" />
          )}
          {evaluating ? "Assessing…" : hasEvaluation ? "Re-run assessment" : "Run assessment"}
        </button>
      </div>

      {evaluateError && (
        <p className="mt-3 rounded-xl border border-brand-danger/30 bg-brand-danger/5 p-3 text-sm text-brand-danger">
          {evaluateError}
        </p>
      )}

      {!hasEvaluation && !evaluateError && !evaluating && (
        <div className="mt-4 flex items-center gap-3 rounded-xl border border-dashed border-brand-border bg-brand-cream p-5">
          <Scale className="h-6 w-6 text-brand-muted" aria-hidden="true" />
          <p className="text-sm text-brand-muted">
            No compliance assessment has been run for this inspection yet.
          </p>
        </div>
      )}

      {hasEvaluation && (
        <>
          <div className="mt-4">
            <OverallStatus evaluation={evaluation} />
          </div>
          <div className="mt-3 flex flex-wrap gap-2 text-[11px] font-medium">
            {Object.entries(counts).map(([status, count]) => {
              const meta = STATUS_META[status as RuleEvaluationStatus] ?? STATUS_META.NOT_VERIFIABLE;
              return (
                <span key={status} className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 ${meta.tone}`}>
                  {status === "VIOLATION" && <X className="h-3 w-3" aria-hidden="true" />}
                  {status === "COMPLIANT" && <Check className="h-3 w-3" aria-hidden="true" />}
                  {status === "REVIEW_REQUIRED" && <AlertTriangle className="h-3 w-3" aria-hidden="true" />}
                  {count} {meta.label.toLowerCase()}
                </span>
              );
            })}
          </div>
          <ul className="mt-4 space-y-2">
            {evaluation.results.map((result) => (
              <RuleRow
                key={result.rule_id}
                result={result}
                evidenceBlocks={result.evidence
                  .filter((ref) => ref.evidence_type === "ocr_block" && ref.ocr_block_id !== null)
                  .flatMap((ref) => {
                    const block = blocksById.get(ref.ocr_block_id!);
                    return block ? [{ block, page: ref.page_number ?? 1 }] : [];
                  })}
                activeBlockId={activeBlock?.block_id ?? null}
                onSelectBlock={onSelectBlock}
              />
            ))}
          </ul>
        </>
      )}
    </section>
  );
}
