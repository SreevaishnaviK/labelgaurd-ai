/** Shared API models for LabelGuard AI backend communication. */

export type BBox = {
  x: number;
  y: number;
  width: number;
  height: number;
};

export type OCRBlock = {
  block_id: string;
  page_number: number;
  text: string;
  confidence: number;
  bbox: BBox;
  line_number: number;
  block_number: number;
};

export type OCRPage = {
  page_number: number;
  width: number;
  height: number;
  full_text: string;
  /** Processed (OCR-ready) page image path, relative to the backend. */
  processed_path: string | null;
  /** True when perspective correction changed geometry. */
  warped: boolean;
};

export type FileMeta = {
  original_filename: string;
  document_type: string;
};

export type InspectionStatus = "uploaded" | "processing" | "processed" | "failed";

export type FieldStatus = "detected" | "not_detected" | "ambiguous";

/** All fields the AI service reports — the prompt's 23 plus marketer
 * ("Marketed by" is a listed role indicator and gets its own field). */
export const FIELD_NAMES = [
  "product_name", "manufacturer", "packer", "importer", "marketer",
  "manufacturer_address", "packer_address", "importer_address",
  "net_quantity", "mrp", "manufacturing_date", "packing_date",
  "best_before", "use_by", "expiry_date", "consumer_care",
  "customer_care_phone", "customer_care_email", "website",
  "batch_number", "lot_number", "country_of_origin", "ingredients",
  "vegetarian_non_vegetarian",
] as const;

export type ExtractionEvidence = {
  ocr_block_id: string;
  page_number: number;
};

export type FieldCandidate = {
  raw_text: string | null;
  value: Record<string, unknown> | null;
  /** Provenance of this reading (Phase 4): deterministic | ai_assisted. */
  method: string;
  confidence: number | null;
  evidence: ExtractionEvidence[];
};

export type ExtractedField = {
  field_name: string;
  status: FieldStatus;
  value: Record<string, unknown> | null;
  raw_text: string | null;
  ocr_confidence: number | null;
  extraction_confidence: number | null;
  /** Phase 4 provenance: the AI provider's own confidence (null when pure
   * deterministic) and how the final value was settled. */
  ai_confidence: number | null;
  resolution_status: string | null;
  method: string;
  evidence: ExtractionEvidence[];
  candidates: FieldCandidate[] | null;
};

export type Inspection = {
  inspection_id: string;
  status: InspectionStatus;
  created_at: string;
  file: FileMeta;
  ocr: {
    pages: OCRPage[];
    blocks: OCRBlock[];
    full_text: string;
    blocks_detected: number;
    average_confidence: number;
  };
  extraction: {
    fields: ExtractedField[];
  };
};

export type UploadSuccess = {
  inspection_id: string;
  status: string;
  filename: string;
  document_type: string;
  pages: number;
  text_length: number;
  blocks_detected: number;
};

export type SystemStatus = {
  backend: string;
  database: string;
  computer_vision: string;
  ai: string;
  legal_engine: string;
  /** AI extraction provider name: none | mock | openai | unknown. */
  ai_provider: string;
};

export type ApiErrorDetail = {
  code: string;
  message: string;
};
