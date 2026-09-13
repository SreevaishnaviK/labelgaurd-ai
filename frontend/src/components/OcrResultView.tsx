import { useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle,
  ArrowLeft,
  Check,
  Copy,
  Crosshair,
  Eye,
  EyeOff,
  FileText,
  Loader2,
} from "lucide-react";
import { fetchInspection, inspectionImageUrl } from "../lib/inspections";
import type { ExtractedField, Inspection, OCRBlock } from "../types/api";

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
}: {
  field: ExtractedField;
  blocksById: Map<string, OCRBlock>;
  isActive: boolean;
  onSelectBlock: (block: OCRBlock | null) => void;
}) {
  const value = formatValue(field);
  const isAmbiguous = field.status === "ambiguous";
  const isDetected = field.status === "detected";
  const evidenceBlock = field.evidence.length ? blocksById.get(field.evidence[0].ocr_block_id) ?? null : null;

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
                Candidate {index + 1}: {candidate.raw_text ?? JSON.stringify(candidate.value)}
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
          {field.extraction_confidence != null && `extraction ${field.extraction_confidence}%`}
          {field.extraction_confidence != null && field.ocr_confidence != null && " · "}
          {field.ocr_confidence != null && `ocr ${field.ocr_confidence}%`}
        </p>
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
      </div>
    </div>
  );
}

function StructuredInformation({
  fields,
  blocks,
  activeBlock,
  onSelectBlock,
}: {
  fields: ExtractedField[];
  blocks: OCRBlock[];
  activeBlock: OCRBlock | null;
  onSelectBlock: (block: OCRBlock | null) => void;
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
      <p className="mt-1 text-sm text-brand-muted">
        Fields read from the OCR text. Click a field's evidence to highlight it on the label.
      </p>
      <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {fields.map((field) => (
          <FieldCard
            key={field.field_name}
            field={field}
            blocksById={blocksById}
            isActive={activeEvidenceField?.field_name === field.field_name}
            onSelectBlock={onSelectBlock}
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
}: {
  inspection: Inspection;
  activeBlock: OCRBlock | null;
  onSelectBlock: (block: OCRBlock | null) => void;
  showBoxes: boolean;
  overlayRef: React.RefObject<HTMLDivElement | null>;
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
  const overlayRef = useRef<HTMLDivElement>(null);

  const toggleBoxes = () => {
    // Hiding the overlay must not strand focus inside an aria-hidden subtree.
    if (showBoxes && overlayRef.current?.contains(document.activeElement)) {
      (document.activeElement as HTMLElement).blur();
    }
    setShowBoxes((value) => !value);
  };

  useEffect(() => {
    let cancelled = false;
    fetchInspection(inspectionId)
      .then((data) => {
        if (!cancelled) setInspection(data);
      })
      .catch((err: Error) => {
        if (!cancelled) setError(err.message);
      });
    return () => {
      cancelled = true;
    };
  }, [inspectionId]);

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
          <ImageEvidence
            inspection={inspection}
            activeBlock={activeBlock}
            onSelectBlock={setActiveBlock}
            showBoxes={showBoxes}
            overlayRef={overlayRef}
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
      />
    </div>
  );
}
