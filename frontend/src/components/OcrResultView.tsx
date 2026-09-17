import { useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle,
  ArrowLeft,
  BadgeCheck,
  Check,
  Copy,
  Crosshair,
  Eye,
  EyeOff,
  FileText,
  Loader2,
} from "lucide-react";
import CompliancePanel from "./CompliancePanel";
import { findEvidenceBlock, VisualEvidenceCard } from "./VisualEvidencePanel";
import {
  AuditHistorySection,
  EvaluationVersionsSection,
  ReportSection,
  VerificationHistorySection,
} from "./InspectionHistorySections";
import {
  createFieldVerification,
  createRuleVerification,
  evaluateInspection,
  fetchInspection,
  inspectionImageUrl,
} from "../lib/inspections";
import { apiUrl } from "../lib/api";
import type {
  Evaluation,
  ExtractedField,
  FieldVerification,
  Inspection,
  OCRBlock,
  SystemStatus,
  VisualEvidence,
} from "../types/api";

const btnPrimary =
  "inline-flex items-center justify-center gap-2 rounded-lg bg-brand-dark px-5 py-2.5 text-sm font-medium text-brand-white transition-colors hover:bg-brand-green";
const btnSecondary =
  "inline-flex items-center justify-center gap-2 rounded-lg border border-brand-border bg-brand-white px-5 py-2.5 text-sm font-medium text-brand-dark transition-colors hover:border-brand-green/40 hover:bg-brand-light";

const FIELD_LABELS: Record<string, string> = {
  product_name: "Product Name",
  manufacturer: "Manufacturer",
  packer: "Packer",
  importer: "Importer",
  marketer: "Marketer",
  manufacturer_address: "Manufacturer Address",
  packer_address: "Packer Address",
  importer_address: "Importer Address",
  net_quantity: "Net Quantity",
  mrp: "MRP",
  manufacturing_date: "Manufacturing Date",
  packing_date: "Packing Date",
  best_before: "Best Before",
  use_by: "Use By",
  expiry_date: "Expiry Date",
  consumer_care: "Consumer Care",
  customer_care_phone: "Customer Care Phone",
  customer_care_email: "Customer Care Email",
  website: "Website",
  batch_number: "Batch Number",
  lot_number: "Lot Number",
  country_of_origin: "Country of Origin",
  ingredients: "Ingredients",
  vegetarian_non_vegetarian: "Vegetarian / Non-Vegetarian",
};

function provenanceLabel(field: ExtractedField): string {
  if (field.method === "ai_assisted") return "AI-assisted";
  if (field.method === "deterministic_fallback") return "Deterministic fallback";
  return "Pattern-based";
}

async function fetchSystemStatus(): Promise<SystemStatus> {
  const response = await fetch(apiUrl("/api/v1/system/status"));
  if (!response.ok) throw new Error("System status unavailable");
  return response.json();
}

function formatValue(field: ExtractedField): string | null {
  const value = field.value;
  if (!value) return null;
  if (field.field_name === "mrp" && typeof value.amount === "number") {
    return `₹${value.amount.toFixed(2)}`;
  }
  if (field.field_name === "net_quantity") {
    return `${value.value} ${value.unit}`;
  }
  if (field.field_name === "vegetarian_non_vegetarian") {
    return value.declaration === "vegetarian" ? "Vegetarian" : "Non-Vegetarian";
  }
  const text = Object.values(value).find((part) => typeof part === "string" && part.length > 0);
  return typeof text === "string" ? text : null;
}

function FieldCard({
  field,
  blocksById,
  isActive,
  onSelectBlock,
  verification,
  onSaveVerification,
}: {
  field: ExtractedField;
  blocksById: Map<string, OCRBlock>;
  isActive: boolean;
  onSelectBlock: (block: OCRBlock | null) => void;
  verification: FieldVerification | null;
  onSaveVerification: (
    payload: {
      extracted_field_id: number;
      verification_status: "verified" | "corrected";
      verified_value?: Record<string, unknown> | null;
      comment?: string | null;
      evidence_ocr_block_id?: string | null;
    },
  ) => Promise<void>;
}) {
  const value = formatValue(field);
  const isAmbiguous = field.status === "ambiguous";
  const isDetected = field.status === "detected";
  const evidenceBlock = field.evidence.length ? blocksById.get(field.evidence[0].ocr_block_id) ?? null : null;
  const [verifying, setVerifying] = useState(false);
  const [correctedValue, setCorrectedValue] = useState("");
  const [comment, setComment] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const saveVerification = async (status: "verified" | "corrected") => {
    if (status === "corrected" && !correctedValue.trim()) {
      setError("Enter the verified value.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const current = field.value ?? {};
      const edited =
        status === "corrected"
          ? Object.fromEntries(
              Object.entries(current).map(([key, existing]) =>
                typeof existing === "string" && existing.length > 0 ? [key, correctedValue.trim()] : [key, existing],
              ),
            )
          : null;
      await onSaveVerification({
        extracted_field_id: field.extracted_field_id,
        verification_status: status,
        verified_value: edited,
        comment: comment.trim() || null,
        evidence_ocr_block_id: field.evidence[0]?.ocr_block_id ?? null,
      });
      setVerifying(false);
      setCorrectedValue("");
      setComment("");
    } catch (err) {
      setError(err instanceof Error && err.message ? err.message : "Could not save the verification.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div
      className={`rounded-xl border p-4 transition-colors ${
        isActive
          ? "border-brand-green bg-brand-green/5"
          : "border-brand-border bg-brand-cream"
      }`}
    >
      <div className="flex items-center justify-between gap-2">
        <p className="text-[11px] font-semibold tracking-[0.14em] text-brand-muted uppercase">
          {FIELD_LABELS[field.field_name] ?? field.field_name}
        </p>
        <span
          className={`rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${
            isDetected
              ? "bg-brand-green/10 text-brand-green"
              : isAmbiguous
                ? "bg-amber-500/10 text-amber-600"
                : "bg-brand-muted/10 text-brand-muted"
          }`}
        >
          {isDetected ? "Detected" : isAmbiguous ? "Needs review" : "Not detected"}
        </span>
      </div>

      {isAmbiguous ? (
        <div className="mt-2">
          <p className="text-sm font-medium text-brand-dark">Multiple possible values detected</p>
          <ul className="mt-1 space-y-0.5">
            {field.candidates?.map((candidate, index) => (
              <li key={index} className="text-xs text-brand-muted">
                Candidate {index + 1} ({candidate.method === "ai_assisted" ? "AI-assisted" : "pattern-based"}):{" "}
                {candidate.raw_text ?? JSON.stringify(candidate.value)}
              </li>
            ))}
          </ul>
        </div>
      ) : value ? (
        <p className="mt-2 text-sm font-medium break-words text-brand-dark">{value}</p>
      ) : (
        <p className="mt-2 text-sm text-brand-muted">Not detected</p>
      )}

      <div className="mt-3 flex items-center justify-between gap-2">
        <p className="font-mono text-[10px] text-brand-muted">
          {provenanceLabel(field)}
          {field.extraction_confidence != null && ` · ${field.extraction_confidence}%`}
          {field.ocr_confidence != null && ` · ocr ${field.ocr_confidence}%`}
          {field.resolution_status === "conflict" && " · conflicting readings"}
          {field.resolution_status === "ai_unavailable" && " · AI unavailable"}
        </p>
        <div className="flex items-center gap-1">
          {evidenceBlock && (
            <button
              type="button"
              onClick={() => onSelectBlock(isActive ? null : evidenceBlock)}
              className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-[11px] font-medium text-brand-green transition-colors hover:bg-brand-green/10"
              aria-label={`Highlight OCR evidence for ${FIELD_LABELS[field.field_name] ?? field.field_name}`}
            >
              <Crosshair className="h-3 w-3" aria-hidden="true" />
              Evidence
            </button>
          )}
          {(isDetected || isAmbiguous) && !verifying && (
            <button
              type="button"
              onClick={() => setVerifying(true)}
              className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-[11px] font-medium text-brand-dark transition-colors hover:bg-brand-dark/5"
            >
              <BadgeCheck className="h-3 w-3" aria-hidden="true" />
              {verification ? "Re-verify" : "Verify"}
            </button>
          )}
        </div>
      </div>

      {verification && (
        <div className="mt-2 rounded-lg border border-brand-green/30 bg-brand-green/5 p-2.5">
          <p className="flex items-center gap-1 text-[11px] font-semibold text-brand-dark">
            <BadgeCheck className="h-3 w-3 text-brand-green" aria-hidden="true" />
            Officer {verification.verification_status === "corrected" ? "Verified (corrected)" : "Verified"}
          </p>
          {verification.verification_status === "corrected" && verification.verified_value && (
            <p className="mt-1 text-xs text-brand-dark">
              Verified value: {formatValue({ ...field, value: verification.verified_value }) ?? JSON.stringify(verification.verified_value)}
            </p>
          )}
          {verification.comment && <p className="mt-1 text-xs text-brand-muted">"{verification.comment}"</p>}
          <p className="mt-1 font-mono text-[10px] text-brand-muted">
            {verification.officer_identifier} · {new Date(verification.created_at).toLocaleString()}
          </p>
        </div>
      )}

      {verifying && (
        <div className="mt-2 rounded-lg border border-brand-border bg-brand-white p-2.5">
          <p className="text-[11px] text-brand-muted">
            The original extracted value above is never overwritten.
          </p>
          <div className="mt-1.5 flex gap-2">
            <button
              type="button"
              disabled={saving}
              onClick={() => saveVerification("verified")}
              className="rounded-lg bg-brand-dark px-2.5 py-1.5 text-xs font-medium text-brand-white transition-colors hover:bg-brand-green disabled:opacity-50"
            >
              {saving ? <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" /> : <Check className="h-3.5 w-3.5" aria-hidden="true" />}
              Confirm as extracted
            </button>
            <button
              type="button"
              disabled={saving}
              onClick={() => saveVerification("corrected")}
              className="rounded-lg border border-brand-border px-2.5 py-1.5 text-xs font-medium text-brand-dark transition-colors hover:border-brand-green/40 disabled:opacity-50"
            >
              Edit &amp; verify
            </button>
            <button
              type="button"
              onClick={() => {
                setVerifying(false);
                setError(null);
              }}
              className="rounded-lg px-2 py-1.5 text-xs text-brand-muted hover:text-brand-dark"
            >
              Cancel
            </button>
          </div>
          {correctedValue !== "" || comment !== "" || error ? (
            <>
              <input
                type="text"
                value={correctedValue}
                onChange={(event) => setCorrectedValue(event.target.value)}
                maxLength={2000}
                placeholder="Verified value (replaces the extracted value when verified)"
                className="mt-2 w-full rounded-lg border border-brand-border bg-brand-cream p-2 text-xs text-brand-dark placeholder:text-brand-muted/70 focus:border-brand-green focus:outline-none"
              />
              <input
                type="text"
                value={comment}
                onChange={(event) => setComment(event.target.value)}
                maxLength={4000}
                placeholder={"Optional comment — e.g. 'Confirmed from package.'"}
                className="mt-1.5 w-full rounded-lg border border-brand-border bg-brand-cream p-2 text-xs text-brand-dark placeholder:text-brand-muted/70 focus:border-brand-green focus:outline-none"
              />
            </>
          ) : null}
          {error && <p className="mt-1.5 text-xs text-brand-danger">{error}</p>}
        </div>
      )}
    </div>
  );
}

function AIExtractionStatus({ status, provider }: { status: string | null; provider: string | null }) {
  if (!status) return null; // status endpoint unreachable — say nothing rather than alarm
  const label =
    status === "ok"
      ? provider && provider !== "none"
        ? "Available"
        : "Deterministic mode"
      : "Unavailable — deterministic extraction used";
  const tone = status === "ok" ? "bg-brand-green/10 text-brand-green" : "bg-brand-muted/10 text-brand-muted";
  return (
    <div className="mt-2 flex items-center gap-2">
      <span className="text-sm text-brand-muted">AI Extraction</span>
      <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${tone}`}>
        {label}
      </span>
    </div>
  );
}

function StructuredInformation({
  fields,
  blocks,
  activeBlock,
  onSelectBlock,
  aiStatus,
  aiProvider,
  fieldVerifications,
  onSaveFieldVerification,
}: {
  fields: ExtractedField[];
  blocks: OCRBlock[];
  activeBlock: OCRBlock | null;
  onSelectBlock: (block: OCRBlock | null) => void;
  aiStatus: string | null;
  aiProvider: string | null;
  fieldVerifications: Map<number, FieldVerification>;
  onSaveFieldVerification: (
    payload: {
      extracted_field_id: number;
      verification_status: "verified" | "corrected";
      verified_value?: Record<string, unknown> | null;
      comment?: string | null;
      evidence_ocr_block_id?: string | null;
    },
  ) => Promise<void>;
}) {
  const blocksById = useMemo(() => new Map(blocks.map((b) => [b.block_id, b])), [blocks]);
  const activeEvidenceField = activeBlock
    ? fields.find((field) => field.evidence.some((ref) => ref.ocr_block_id === activeBlock.block_id))
    : undefined;

  if (fields.length === 0) {
    return (
      <section className="mt-6 rounded-2xl border border-brand-border bg-brand-white p-6">
        <h2 className="text-lg font-medium text-brand-dark">Structured Information</h2>
        <p className="mt-2 text-sm text-brand-muted">
          Structured extraction is unavailable for this inspection.
        </p>
      </section>
    );
  }

  return (
    <section className="mt-6 rounded-2xl border border-brand-border bg-brand-white p-6" aria-labelledby="fields-heading">
      <h2 id="fields-heading" className="text-lg font-medium text-brand-dark">
        Structured Information
      </h2>
      <AIExtractionStatus status={aiStatus} provider={aiProvider} />
      <p className="mt-1 text-sm text-brand-muted">
        Fields read from the OCR text. Click a field's evidence to highlight it on the label.
        Officer verification is stored separately — the extracted value is never overwritten.
      </p>
      <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {fields.map((field) => (
          <FieldCard
            key={field.field_name}
            field={field}
            blocksById={blocksById}
            isActive={activeEvidenceField?.field_name === field.field_name}
            onSelectBlock={onSelectBlock}
            verification={fieldVerifications.get(field.extracted_field_id) ?? null}
            onSaveVerification={onSaveFieldVerification}
          />
        ))}
      </div>
    </section>
  );
}

function SummaryMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-brand-border bg-brand-white p-4">
      <p className="text-2xl font-light tracking-tight text-brand-dark">{value}</p>
      <p className="mt-0.5 text-xs font-medium text-brand-muted">{label}</p>
    </div>
  );
}

function ImageEvidence({
  inspection,
  activeBlock,
  onSelectBlock,
  showBoxes,
  overlayRef,
  evidenceBoxes,
}: {
  inspection: Inspection;
  activeBlock: OCRBlock | null;
  onSelectBlock: (block: OCRBlock | null) => void;
  showBoxes: boolean;
  overlayRef: React.RefObject<HTMLDivElement | null>;
  evidenceBoxes: VisualEvidence[];
}) {
  const page = inspection.ocr.pages[0];
  const url = inspectionImageUrl(inspection.inspection_id);

  // Blocks carry coordinates against the processed OCR page. Perspective
  // correction changes geometry, so on warped pages the boxes would drift on
  // the original image — they are hidden with an explanatory note instead.
  const warped = page?.warped ?? false;

  // Resize-only pages: original and processed share proportions, so bboxes are
  // placed as percentages of the page dimensions — they then track the
  // <img> at any rendered size, and an image whose pixels were downscaled by
  // the server (e.g. huge photos) still lines up exactly.
  const usable = Boolean(page && page.width > 0 && page.height > 0 && !warped);
  const pageWidth = page?.width ?? 1;
  const pageHeight = page?.height ?? 1;

  return (
    <div className="relative inline-block">
      <img
        src={url}
        alt={`Original uploaded label for inspection ${inspection.inspection_id}`}
        className="max-h-[560px] w-auto max-w-full rounded-lg border border-brand-border bg-white"
      />
      {showBoxes && usable && (
        <div ref={overlayRef} className="absolute inset-0">
          {evidenceBoxes.map((item) => (
            <div
              key={item.evidence_id}
              className={`pointer-events-none absolute border-2 border-dashed ${
                activeBlock &&
                (item.ocr_block_ids.includes(activeBlock.block_id) || item.ocr_block_id === activeBlock.block_id)
                  ? "border-brand-dark bg-brand-dark/5"
                  : "border-brand-dark/40"
              }`}
              style={{
                left: `${(item.bbox!.x / pageWidth) * 100}%`,
                top: `${(item.bbox!.y / pageHeight) * 100}%`,
                width: `${(item.bbox!.width / pageWidth) * 100}%`,
                height: `${(item.bbox!.height / pageHeight) * 100}%`,
              }}
            />
          ))}
          {inspection.ocr.blocks.map((block) => {
            const isActive = activeBlock?.block_id === block.block_id;
            return (
              <button
                key={block.block_id}
                type="button"
                aria-label={`Block ${block.block_number}: ${block.text}. Confidence ${block.confidence}%`}
                onClick={() => onSelectBlock(isActive ? null : block)}
                className={`absolute cursor-pointer border transition-colors ${
                  isActive
                    ? "border-brand-green bg-brand-green/20"
                    : "border-brand-green/50 bg-brand-green/5 hover:bg-brand-green/15"
                }`}
                style={{
                  left: `${(block.bbox.x / pageWidth) * 100}%`,
                  top: `${(block.bbox.y / pageHeight) * 100}%`,
                  width: `${(block.bbox.width / pageWidth) * 100}%`,
                  height: `${(block.bbox.height / pageHeight) * 100}%`,
                }}
              />
            );
          })}
        </div>
      )}
    </div>
  );
}

export default function OcrResultView({ inspectionId, onNavigate }: { inspectionId: string; onNavigate: () => void }) {
  const [inspection, setInspection] = useState<Inspection | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showBoxes, setShowBoxes] = useState(true);
  const [activeBlock, setActiveBlock] = useState<OCRBlock | null>(null);
  const [copied, setCopied] = useState(false);
  const [systemStatus, setSystemStatus] = useState<SystemStatus | null>(null);
  const [evaluation, setEvaluation] = useState<Evaluation | null>(null);
  const [evaluating, setEvaluating] = useState(false);
  const [evaluateError, setEvaluateError] = useState<string | null>(null);
  const [activeEvidenceItem, setActiveEvidenceItem] = useState<VisualEvidence | null>(null);
  const [evidenceOverlay, setEvidenceOverlay] = useState(true);
  const overlayRef = useRef<HTMLDivElement>(null);

  const toggleBoxes = () => {
    // Hiding the overlay must not strand focus inside an aria-hidden subtree.
    if (showBoxes && overlayRef.current?.contains(document.activeElement)) {
      (document.activeElement as HTMLElement).blur();
    }
    setShowBoxes((value) => !value);
  };

  // Hooks live above every early return (Rules of Hooks).
  const blocksById = useMemo(
    () => new Map((inspection?.ocr.blocks ?? []).map((b) => [b.block_id, b])),
    [inspection],
  );

  // An evidence card selects its anchor OCR block — one coordinate system.
  const evidenceActiveBlock = useMemo(
    () => (activeEvidenceItem ? findEvidenceBlock(activeEvidenceItem, blocksById) : null),
    [activeEvidenceItem, blocksById],
  );
  const effectiveActiveBlock = evidenceActiveBlock ?? activeBlock;

  const evidenceBoxes = useMemo(() => {
    if (!inspection) return [];
    return inspection.visual_evidence.filter(
      (item) => item.bbox && item.verification_status === "AUTOMATED" && item.evidence_type !== "DECLARATION_REGION",
    );
  }, [inspection]);

  const runEvaluation = async () => {
    setEvaluating(true);
    setEvaluateError(null);
    try {
      setEvaluation(await evaluateInspection(inspectionId));
    } catch (err) {
      setEvaluateError(
        err instanceof Error && err.message
          ? err.message
          : "Could not run the assessment.",
      );
    } finally {
      setEvaluating(false);
    }
  };

  // Reload after any officer action so effective statuses and verification
  // records reflect the persisted truth (originals stay immutable).
  const [refreshKey, setRefreshKey] = useState(0);
  const refreshAfterAction = async () => {
    try {
      const data = await fetchInspection(inspectionId);
      setInspection(data);
      setEvaluation(data.evaluation ?? null);
      setRefreshKey((k) => k + 1);
    } catch {
      /* keep showing the pre-action state rather than blanking the screen */
    }
  };

  const saveRuleVerification = async (payload: {
    rule_evaluation_id: number;
    decision: string;
    comment?: string | null;
  }) => {
    await createRuleVerification(inspectionId, payload);
  };

  const saveFieldVerification = async (payload: {
    extracted_field_id: number;
    verification_status: "verified" | "corrected";
    verified_value?: Record<string, unknown> | null;
    comment?: string | null;
    evidence_ocr_block_id?: string | null;
  }) => {
    await createFieldVerification(inspectionId, payload);
  };

  const fieldVerificationsById = useMemo(
    () => new Map((inspection?.field_verifications ?? []).map((v) => [v.extracted_field_id, v])),
    [inspection],
  );

  useEffect(() => {
    let cancelled = false;
    fetchInspection(inspectionId)
      .then((data) => {
        if (!cancelled) {
          setInspection(data);
          setEvaluation(data.evaluation ?? null);
          setActiveEvidenceItem(null);
        }
      })
      .catch((err: Error) => {
        if (!cancelled) setError(err.message);
      });
    return () => {
      cancelled = true;
    };
  }, [inspectionId]);

  useEffect(() => {
    let cancelled = false;
    fetchSystemStatus()
      .then((status) => {
        if (!cancelled) setSystemStatus(status);
      })
      .catch(() => {
        /* status chip stays hidden — never look broken over an optional chip */
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (error) {
    return (
      <div className="mx-auto max-w-2xl px-4 py-16 text-center">
        <AlertTriangle className="mx-auto h-10 w-10 text-brand-danger" aria-hidden="true" />
        <h1 className="mt-4 text-xl font-medium text-brand-dark">Could not load inspection</h1>
        <p className="mt-2 text-sm text-brand-muted">{error}</p>
        <button type="button" onClick={onNavigate} className={`${btnPrimary} mt-6`}>
          <ArrowLeft className="h-4 w-4" /> Back to Dashboard
        </button>
      </div>
    );
  }

  if (!inspection) {
    return (
      <div className="flex min-h-[50vh] items-center justify-center gap-3 text-brand-muted">
        <Loader2 className="h-5 w-5 animate-spin" aria-hidden="true" />
        <span className="text-sm">Loading inspection…</span>
      </div>
    );
  }

  const { ocr } = inspection;
  const characters = ocr.full_text.length;

  const copyText = async () => {
    try {
      await navigator.clipboard.writeText(ocr.full_text);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      /* clipboard unavailable */
    }
  };

  return (
    <div className="mx-auto max-w-7xl animate-fade-up px-4 pb-20 sm:px-6 lg:px-8">
      <div className="pt-8 sm:pt-12">
        <button type="button" onClick={onNavigate} className="mb-6 inline-flex items-center gap-2 rounded-lg px-4 py-2.5 text-sm font-medium text-brand-muted transition-colors hover:bg-brand-light hover:text-brand-dark">
          <ArrowLeft className="h-4 w-4" /> Back to Dashboard
        </button>

        <p className="text-[11px] font-semibold tracking-[0.2em] text-brand-green uppercase">
          Inspection {inspection.inspection_id}
        </p>
        <h1 className="mt-2 text-3xl font-light tracking-tight text-brand-dark sm:text-4xl">
          OCR Analysis Result
        </h1>
        <p className="mt-2 max-w-2xl text-sm leading-relaxed text-brand-muted sm:text-base">
          AI vision has extracted visible text from the uploaded product label.
        </p>
      </div>

      <div className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <SummaryMetric label="Pages" value={String(ocr.pages.length)} />
        <SummaryMetric label="Text Blocks" value={String(ocr.blocks_detected)} />
        <SummaryMetric label="Characters" value={String(characters)} />
        <SummaryMetric label="Average Confidence" value={`${ocr.average_confidence}%`} />
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-2">
        <section className="rounded-2xl border border-brand-border bg-brand-white p-6" aria-labelledby="evidence-heading">
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
            <h2 id="evidence-heading" className="text-lg font-medium text-brand-dark">
              Original Label
            </h2>
            <div className="flex gap-2">
              {evidenceBoxes.length > 0 && (
                <button
                  type="button"
                  onClick={() => setEvidenceOverlay((value) => !value)}
                  className={btnSecondary}
                  aria-pressed={evidenceOverlay}
                >
                  {evidenceOverlay ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                  {evidenceOverlay ? "Hide evidence" : "Show evidence"}
                </button>
              )}
              <button
                type="button"
                onClick={toggleBoxes}
                className={btnSecondary}
                aria-pressed={showBoxes}
              >
                {showBoxes ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                {showBoxes ? "Hide boxes" : "Show boxes"}
              </button>
            </div>
          </div>
          <ImageEvidence
            inspection={inspection}
            activeBlock={effectiveActiveBlock}
            onSelectBlock={setActiveBlock}
            showBoxes={showBoxes}
            overlayRef={overlayRef}
            evidenceBoxes={evidenceOverlay ? evidenceBoxes : []}
          />

          {inspection.ocr.pages[0]?.warped && (
            <p className="mt-4 rounded-xl border border-brand-border bg-brand-light/60 p-4 text-xs leading-relaxed text-brand-muted">
              Perspective correction was applied to this label, so its text
              coordinates do not map onto the original image — the box overlay is
              disabled for this page. The processed image the OCR engine read is
              preserved server-side as evidence.
            </p>
          )}

          {activeBlock && (
            <div className="mt-4 rounded-xl border border-brand-border bg-brand-light/60 p-4">
              <p className="text-[11px] font-semibold tracking-[0.14em] text-brand-muted uppercase">
                Block #{activeBlock.block_number}
              </p>
              <p className="mt-1 font-medium text-brand-dark">{activeBlock.text}</p>
              <p className="mt-1 font-mono text-xs text-brand-muted">
                Confidence {activeBlock.confidence}% · {activeBlock.block_id}
              </p>
            </div>
          )}
        </section>

        <section className="rounded-2xl border border-brand-border bg-brand-white p-6" aria-labelledby="text-heading">
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
            <h2 id="text-heading" className="text-lg font-medium text-brand-dark">
              Extracted Text
            </h2>
            <button type="button" onClick={copyText} className={btnSecondary}>
              {copied ? <Check className="h-4 w-4 text-brand-success" /> : <Copy className="h-4 w-4" />}
              {copied ? "Copied" : "Copy text"}
            </button>
          </div>
          {ocr.full_text.trim() ? (
            <div
              className="max-h-[560px] overflow-y-auto rounded-xl border border-brand-border bg-brand-cream p-5 text-sm leading-relaxed text-brand-dark"
              tabIndex={0}
            >
              {ocr.pages.length > 1
                ? ocr.pages.map((page) => (
                    <div key={page.page_number} className="mb-6 last:mb-0">
                      <p className="mb-2 font-mono text-[11px] font-semibold tracking-[0.14em] text-brand-muted uppercase">
                        Page {page.page_number}
                      </p>
                      <p className="whitespace-pre-wrap">{page.full_text}</p>
                    </div>
                  ))
                : <p className="whitespace-pre-wrap">{ocr.full_text}</p>}
            </div>
          ) : (
            <div className="flex flex-col items-center rounded-xl border border-dashed border-brand-border bg-brand-cream p-10 text-center">
              <FileText className="h-8 w-8 text-brand-muted" aria-hidden="true" />
              <p className="mt-3 text-sm text-brand-muted">
                No text could be read from this document.
              </p>
            </div>
          )}
          <p className="mt-4 font-mono text-xs text-brand-muted">
            {inspection.file.original_filename} · {inspection.file.document_type} ·{" "}
            {new Date(inspection.created_at).toLocaleString()}
          </p>
        </section>
      </div>

      <StructuredInformation
        fields={inspection.extraction.fields}
        blocks={ocr.blocks}
        activeBlock={activeBlock}
        onSelectBlock={setActiveBlock}
        aiStatus={systemStatus?.ai ?? null}
        aiProvider={systemStatus?.ai_provider ?? null}
        fieldVerifications={fieldVerificationsById}
        onSaveFieldVerification={saveFieldVerification}
      />

      {inspection.visual_evidence.length > 0 && (
        <section
          className="mt-6 rounded-2xl border border-brand-border bg-brand-white p-6"
          aria-labelledby="visual-evidence-heading"
        >
          <h2 id="visual-evidence-heading" className="text-lg font-medium text-brand-dark">
            Visual Evidence
          </h2>
          <p className="mt-1 text-sm text-brand-muted">
            Automated measurements from the label image. Pixel values are
            estimates — physical units appear only with a real calibration.
          </p>
          <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {inspection.visual_evidence.map((item) => (
              <VisualEvidenceCard
                key={item.evidence_id}
                item={item}
                isActive={activeEvidenceItem?.evidence_id === item.evidence_id}
                onSelect={(selected) => {
                  setActiveEvidenceItem(selected);
                  setActiveBlock(null);
                }}
              />
            ))}
          </div>
        </section>
      )}

      <CompliancePanel
        evaluation={evaluation}
        blocksById={blocksById}
        activeBlock={activeBlock}
        onSelectBlock={setActiveBlock}
        onRunEvaluation={runEvaluation}
        evaluating={evaluating}
        evaluateError={evaluateError}
        onSaveVerification={saveRuleVerification}
        onVerificationSaved={refreshAfterAction}
      />

      <div className="mt-6 grid gap-4">
        <VerificationHistorySection inspectionId={inspectionId} />
        <AuditHistorySection inspectionId={inspectionId} />
        <EvaluationVersionsSection inspectionId={inspectionId} refreshKey={refreshKey} />
        <ReportSection inspectionId={inspectionId} />
      </div>
    </div>
  );
}
