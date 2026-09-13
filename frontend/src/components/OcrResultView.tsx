import { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  ArrowLeft,
  Check,
  Copy,
  Eye,
  EyeOff,
  FileText,
  Loader2,
} from "lucide-react";
import { fetchInspection, inspectionImageUrl } from "../lib/inspections";
import type { Inspection, OCRBlock } from "../types/api";

const btnPrimary =
  "inline-flex items-center justify-center gap-2 rounded-lg bg-brand-dark px-5 py-2.5 text-sm font-medium text-brand-white transition-colors hover:bg-brand-green";
const btnSecondary =
  "inline-flex items-center justify-center gap-2 rounded-lg border border-brand-border bg-brand-white px-5 py-2.5 text-sm font-medium text-brand-dark transition-colors hover:border-brand-green/40 hover:bg-brand-light";

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
}: {
  inspection: Inspection;
  activeBlock: OCRBlock | null;
  onSelectBlock: (block: OCRBlock | null) => void;
  showBoxes: boolean;
}) {
  const [naturalSize, setNaturalSize] = useState<{ width: number; height: number } | null>(null);
  const page = inspection.ocr.pages[0];
  const url = inspectionImageUrl(inspection.inspection_id);

  // Blocks carry coordinates against the processed OCR page. Perspective
  // correction changes geometry, so on warped pages the boxes would drift on
  // the original image — they are hidden with an explanatory note instead.
  const warped = page?.warped ?? false;

  // Resize-only pages: map processed-page coordinates onto the original by
  // aspect ratio (uniform scale in each axis; aspect is preserved).
  const scale = useMemo(() => {
    if (warped || !naturalSize || !page || page.width === 0 || page.height === 0) return null;
    return { x: naturalSize.width / page.width, y: naturalSize.height / page.height };
  }, [warped, naturalSize, page]);

  return (
    <div className="relative inline-block">
      <img
        src={url}
        alt={`Original uploaded label for inspection ${inspection.inspection_id}`}
        className="max-h-[560px] w-auto max-w-full rounded-lg border border-brand-border bg-white"
        onLoad={(event) => {
          const img = event.currentTarget;
          setNaturalSize({ width: img.naturalWidth, height: img.naturalHeight });
        }}
      />
      {showBoxes && scale && !warped && (
        <div className="absolute inset-0" aria-hidden="true">
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
                  left: `${block.bbox.x * scale.x}px`,
                  top: `${block.bbox.y * scale.y}px`,
                  width: `${block.bbox.width * scale.x}px`,
                  height: `${block.bbox.height * scale.y}px`,
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
              onClick={() => setShowBoxes((value) => !value)}
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
    </div>
  );
}
