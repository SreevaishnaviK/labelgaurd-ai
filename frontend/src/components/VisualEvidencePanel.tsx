import { Crosshair } from "lucide-react";
import type { OCRBlock, VisualEvidence } from "../types/api";

const TYPE_LABELS: Record<string, string> = {
  PDP_AREA: "Candidate PDP",
  TEXT_HEIGHT: "Letter Height",
  DECLARATION_REGION: "Declaration Region",
  CONTRAST: "Contrast",
  READABILITY: "Readability",
  BOUNDARY: "Package Boundary",
  DECLARATION_SYMBOL: "Declaration Symbol",
  PACKAGE_DIMENSION: "Package Dimensions",
  QUANTITY_MEASUREMENT: "Quantity Measurement",
};

function formatValue(item: VisualEvidence): string {
  if (item.value === null || item.value === undefined) return "—";
  if (typeof item.value === "string") return item.value;
  const rounded = item.value >= 100 ? Math.round(item.value).toString() : item.value.toFixed(2);
  return item.unit === "px2" || item.unit === "cm2" ? `${rounded} ${item.unit}` : `${rounded}${item.unit ? ` ${item.unit}` : ""}`;
}

function evidenceLine(item: VisualEvidence): string {
  if (item.evidence_type === "DECLARATION_SYMBOL") {
    if (item.verification_status === "INSUFFICIENT_EVIDENCE") return "Not detected";
    return typeof item.value === "string" ? `Detected ${item.value.replace(/_/g, " ")}` : "Symbol detected";
  }
  if (item.evidence_type === "DECLARATION_REGION") {
    const label = typeof item.value === "string" ? item.value.replace(/_/g, " ").toLowerCase() : "declaration";
    return `Detected ${label}`;
  }
  if (item.evidence_type === "TEXT_HEIGHT") {
    return item.unit === "mm" ? formatValue(item) : "Physical height unavailable";
  }
  if (item.evidence_type === "PDP_AREA") {
    return item.unit === "cm2" ? formatValue(item) : `${formatValue(item)} (pixel estimate)`;
  }
  return formatValue(item);
}

function unitNote(item: VisualEvidence): string | null {
  if (item.evidence_type === "TEXT_HEIGHT" && item.unit === "px") {
    return "Estimated in pixels — not a physical millimetre value.";
  }
  if (item.evidence_type === "PDP_AREA" && item.unit === "px2") {
    return "Candidate panel in pixels — physical cm² requires calibration.";
  }
  return null;
}

export function VisualEvidenceCard({
  item,
  isActive,
  onSelect,
}: {
  item: VisualEvidence;
  isActive: boolean;
  onSelect: (item: VisualEvidence | null) => void;
}) {
  const insufficient = item.verification_status === "INSUFFICIENT_EVIDENCE";
  const hasBox = item.bbox !== null && !insufficient;
  return (
    <div
      className={`rounded-xl border p-4 transition-colors ${
        isActive ? "border-brand-green bg-brand-green/5" : "border-brand-border bg-brand-cream"
      }`}
    >
      <div className="flex items-center justify-between gap-2">
        <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-brand-muted">
          {TYPE_LABELS[item.evidence_type] ?? item.evidence_type}
          {item.field_name && item.evidence_type === "DECLARATION_REGION" && (
            <span className="ml-1 normal-case tracking-normal">· {item.field_name.replace(/_/g, " ")}</span>
          )}
        </p>
        <span
          className={`rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${
            insufficient ? "bg-brand-muted/10 text-brand-muted" : "bg-brand-green/10 text-brand-green"
          }`}
        >
          {insufficient ? "Insufficient evidence" : "Automated"}
        </span>
      </div>
      <p className="mt-2 text-sm font-medium text-brand-dark">{evidenceLine(item)}</p>
      <p className="mt-1 font-mono text-[10px] text-brand-muted">
        {item.method}
        {item.confidence != null && ` · ${Math.round(item.confidence * 100)}%`}
      </p>
      {unitNote(item) && <p className="mt-1 text-[11px] leading-snug text-amber-600">{unitNote(item)}</p>}
      {item.note && !unitNote(item) && <p className="mt-1 text-[11px] leading-snug text-brand-muted">{item.note}</p>}
      {hasBox && (
        <button
          type="button"
          onClick={() => onSelect(isActive ? null : item)}
          className="mt-2 inline-flex items-center gap-1 rounded-md px-2 py-1 text-[11px] font-medium text-brand-green transition-colors hover:bg-brand-green/10"
        >
          <Crosshair className="h-3 w-3" aria-hidden="true" />
          Evidence
        </button>
      )}
    </div>
  );
}

export function findEvidenceBlock(item: VisualEvidence, blocksById: Map<string, OCRBlock>): OCRBlock | null {
  const ids = item.ocr_block_ids.length ? item.ocr_block_ids : item.ocr_block_id ? [item.ocr_block_id] : [];
  for (const id of ids) {
    const block = blocksById.get(id);
    if (block) return block;
  }
  return null;
}
