import { useState } from "react";
// Panel state (which rule row is expanded) is local; API state lives in the
// OcrResultView owner so the run button and error banner stay in sync with
// the rest of the result screen.
import {
  AlertTriangle,
  BadgeCheck,
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

/** Officer decisions applicable to a given automated status. Overrides are
 * always offered; CONFIRM_* must match the automated status (the backend
 * validates this too — the UI mirrors the rule). */
function decisionsFor(status: RuleEvaluationStatus): { decision: string; label: string; commentRequired: boolean }[] {
  const confirm =
    status === "REVIEW_REQUIRED"
      ? [{ decision: "CONFIRM_REVIEW_REQUIRED", label: "Confirm review", commentRequired: false }]
      : status === "NOT_VERIFIABLE"
        ? [{ decision: "CONFIRM_NOT_VERIFIABLE", label: "Confirm not verifiable", commentRequired: false }]
        : status === "NOT_APPLICABLE"
          ? [{ decision: "CONFIRM_NOT_APPLICABLE", label: "Confirm not applicable", commentRequired: false }]
          : [];
  return [
    { decision: "ACCEPT", label: "Accept", commentRequired: false },
    ...confirm,
    { decision: "OVERRIDE_COMPLIANT", label: "Override → compliant", commentRequired: true },
    { decision: "OVERRIDE_VIOLATION", label: "Override → violation", commentRequired: true },
  ];
}

const DECISION_LABELS: Record<string, string> = {
  ACCEPT: "Accept",
  OVERRIDE_COMPLIANT: "Override — compliant",
  OVERRIDE_VIOLATION: "Override — violation",
  CONFIRM_REVIEW_REQUIRED: "Confirm review required",
  CONFIRM_NOT_VERIFIABLE: "Confirm not verifiable",
  CONFIRM_NOT_APPLICABLE: "Confirm not applicable",
};

function OfficerVerificationBlock({
  result,
  onSave,
  onSaved,
}: {
  result: RuleResult;
  onSave: (
    payload: { rule_evaluation_id: number; decision: string; comment?: string | null },
  ) => Promise<void>;
  onSaved: () => void;
}) {
  const existing = result.officer_verification;
  const [decision, setDecision] = useState<string | null>(null);
  const [comment, setComment] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const options = decisionsFor(result.status);
  const overrideSelected = decision === "OVERRIDE_COMPLIANT" || decision === "OVERRIDE_VIOLATION";

  const save = async () => {
    if (!decision) return;
    if (overrideSelected && !comment.trim()) {
      setError("An override requires a written reason.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await onSave({
        rule_evaluation_id: result.rule_evaluation_id,
        decision,
        comment: comment.trim() || null,
      });
      setDecision(null);
      setComment("");
      onSaved();
    } catch (err) {
      setError(err instanceof Error && err.message ? err.message : "Could not save the verification.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="mt-3 rounded-xl border border-brand-border bg-brand-white p-3">
      <p className="flex items-center gap-1.5 text-[11px] font-semibold tracking-[0.14em] text-brand-dark uppercase">
        <BadgeCheck className="h-3.5 w-3.5 text-brand-green" aria-hidden="true" />
        Officer Verification
      </p>
      <p className="mt-1 text-xs text-brand-muted">
        Stored separately from the automated result above, which it never
        modifies. Overrides require a written reason.
      </p>

      {existing && (
        <div className="mt-2 rounded-lg border border-brand-green/30 bg-brand-green/5 p-3">
          <p className="text-xs font-semibold text-brand-dark">
            Officer Verified · {DECISION_LABELS[existing.decision] ?? existing.decision}
          </p>
          {existing.comment && <p className="mt-1 text-xs text-brand-dark">"{existing.comment}"</p>}
          <p className="mt-1 font-mono text-[10px] text-brand-muted">
            {existing.officer_identifier} · {new Date(existing.verified_at).toLocaleString()}
          </p>
        </div>
      )}

      <div className="mt-2 flex flex-wrap gap-2">
        {options.map((option) => (
          <button
            key={option.decision}
            type="button"
            disabled={saving}
            onClick={() => {
              setDecision(option.decision);
              setError(null);
            }}
            aria-pressed={decision === option.decision}
            className={`rounded-lg border px-2.5 py-1.5 text-xs font-medium transition-colors disabled:opacity-50 ${
              decision === option.decision
                ? "border-brand-green bg-brand-green/10 text-brand-green"
                : "border-brand-border bg-brand-cream text-brand-dark hover:border-brand-green/40"
            }`}
          >
            {option.label}
          </button>
        ))}
      </div>

      {decision && (
        <div className="mt-2">
          <label className="sr-only" htmlFor={`comment-${result.rule_evaluation_id}`}>
            Verification comment{overrideSelected ? " (required)" : " (optional)"}
          </label>
          <textarea
            id={`comment-${result.rule_evaluation_id}`}
            value={comment}
            onChange={(event) => setComment(event.target.value)}
            rows={2}
            maxLength={4000}
            disabled={saving}
            placeholder={
              overrideSelected
                ? "Required — e.g. \"Physical label inspected manually; declaration is clearly visible.\""
                : "Optional note"
            }
            className="w-full rounded-lg border border-brand-border bg-brand-cream p-2 text-xs text-brand-dark placeholder:text-brand-muted/70 focus:border-brand-green focus:outline-none"
          />
          <div className="mt-2 flex items-center gap-2">
            <button
              type="button"
              onClick={save}
              disabled={saving}
              className="inline-flex items-center gap-1.5 rounded-lg bg-brand-dark px-3 py-1.5 text-xs font-medium text-brand-white transition-colors hover:bg-brand-green disabled:opacity-50"
            >
              {saving ? <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" /> : <Check className="h-3.5 w-3.5" aria-hidden="true" />}
              Save Verification
            </button>
            <button
              type="button"
              onClick={() => {
                setDecision(null);
                setComment("");
                setError(null);
              }}
              disabled={saving}
              className="rounded-lg px-2 py-1.5 text-xs text-brand-muted transition-colors hover:text-brand-dark"
            >
              Cancel
            </button>
          </div>
        </div>
      )}
      {error && <p className="mt-2 text-xs text-brand-danger">{error}</p>}
    </div>
  );
}

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
  onSaveVerification,
  onVerificationSaved,
}: {
  result: RuleResult;
  evidenceBlocks: { block: OCRBlock; page: number }[];
  activeBlockId: string | null;
  onSelectBlock: (block: OCRBlock | null) => void;
  onSaveVerification: (
    payload: { rule_evaluation_id: number; decision: string; comment?: string | null },
  ) => Promise<void>;
  onVerificationSaved: () => void;
}) {
  const [open, setOpen] = useState(false);
  const meta = STATUS_META[result.status] ?? STATUS_META.NOT_VERIFIABLE;
  const Icon = meta.icon;
  const verified = result.officer_verification !== null;
  const effective = result.effective_status ?? result.status;
  const effectiveMeta = STATUS_META[effective as RuleEvaluationStatus] ?? STATUS_META.NOT_VERIFIABLE;
  const EffectiveIcon = effectiveMeta.icon;
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
        {verified && (
          <span
            className="inline-flex shrink-0 items-center gap-1 rounded-full bg-brand-dark/5 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-brand-dark"
            title="Officer-verified decision recorded"
          >
            <BadgeCheck className="h-3 w-3" aria-hidden="true" />
            Verified
          </span>
        )}
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

          {verified && (
            <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1 rounded-lg bg-brand-cream px-3 py-2 text-xs">
              <dt className="text-brand-muted">Effective assessment:</dt>
              <dd className={`inline-flex items-center gap-1 font-semibold ${effectiveMeta.dot}`}>
                <EffectiveIcon className="h-3.5 w-3.5" aria-hidden="true" />
                {effectiveMeta.label}
                {effective !== result.status && " — Officer Verified"}
              </dd>
            </div>
          )}

          <OfficerVerificationBlock result={result} onSave={onSaveVerification} onSaved={onVerificationSaved} />
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
  onSaveVerification,
  onVerificationSaved,
}: {
  evaluation: Evaluation | null;
  blocksById: Map<string, OCRBlock>;
  activeBlock: OCRBlock | null;
  onSelectBlock: (block: OCRBlock | null) => void;
  onRunEvaluation: () => void;
  evaluating: boolean;
  evaluateError: string | null;
  onSaveVerification: (
    payload: { rule_evaluation_id: number; decision: string; comment?: string | null },
  ) => Promise<void>;
  onVerificationSaved: () => void;
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
          {evaluation.officer_effective_status != null && (
            <p className="mt-2 flex items-center gap-2 text-sm text-brand-dark">
              <BadgeCheck className="h-4 w-4 text-brand-green" aria-hidden="true" />
              Officer-Verified Assessment:
              <span className="font-semibold">
                {OVERALL_META[evaluation.officer_effective_status]?.label ?? evaluation.officer_effective_status}
              </span>
              <span className="text-xs text-brand-muted">
                (automated assessment above is unchanged)
              </span>
            </p>
          )}
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
                onSaveVerification={onSaveVerification}
                onVerificationSaved={onVerificationSaved}
              />
            ))}
          </ul>
        </>
      )}
    </section>
  );
}
