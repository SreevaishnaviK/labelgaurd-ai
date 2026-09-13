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

export type ExtractionEvidence = {
  ocr_block_id: string;
  page_number: number;
};

export type FieldCandidate = {
  raw_text: string | null;
  value: Record<string, unknown> | null;
};

export type ExtractedField = {
  field_name: string;
  status: FieldStatus;
  value: Record<string, unknown> | null;
  raw_text: string | null;
  ocr_confidence: number | null;
  extraction_confidence: number | null;
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

export type ApiErrorDetail = {
  code: string;
  message: string;
};
