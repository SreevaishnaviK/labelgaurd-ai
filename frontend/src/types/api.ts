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
  /** Persisted row id — the reference officers verify against (Phase 8). */
  extracted_field_id: number;
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

export type RuleEvaluationStatus =
  | "COMPLIANT"
  | "VIOLATION"
  | "REVIEW_REQUIRED"
  | "NOT_VERIFIABLE"
  | "NOT_APPLICABLE";

/** One measured/observed visual fact from the CV evidence layer. Pixel
 * values stay pixels; physical units appear only with real calibration. */
export type VisualEvidence = {
  evidence_id: string;
  evidence_type: string;
  page_number: number;
  bbox: BBox | null;
  value: number | string | null;
  unit: string | null;
  confidence: number | null;
  method: string;
  verification_status: "AUTOMATED" | "INSUFFICIENT_EVIDENCE";
  ocr_block_id: string | null;
  ocr_block_ids: string[];
  field_name: string | null;
  note: string | null;
};

/** Reference from a rule result to its supporting data. */
export type RuleEvidence = {
  evidence_type: string;
  evidence_reference: string | null;
  ocr_block_id: string | null;
  page_number: number | null;
  extracted_field_id: number | null;
  source_page: number | null;
};

/** One rule's automated result — immutable, produced by the legal engine. */
export type RuleResult = {
  rule_evaluation_id: number;
  rule_id: string;
  rule_number: string;
  rule_title: string;
  status: RuleEvaluationStatus;
  severity: string;
  finding: string;
  required_information: string[];
  actual_information: Record<string, unknown>;
  confidence: number | null;
  requires_officer_verification: boolean;
  source: { document?: string; page?: number | null } & Record<string, unknown>;
  evidence: RuleEvidence[];
  /** Phase 8: layered beside the automated result, never replacing it. */
  effective_status: RuleEvaluationStatus | null;
  officer_verification: OfficerVerification | null;
};

/** A human officer's decision on one rule — stored separately from the
 * automated result, which it never modifies. */
export type OfficerVerification = {
  id: number;
  decision: string;
  comment: string | null;
  officer_identifier: string;
  verified_at: string;
  evidence_ocr_block_id: string | null;
  evidence_visual_evidence_id: string | null;
  evidence_extracted_field_id: number | null;
};

/** Officer verification of one extracted field (value corrections live only
 * here — the original extraction is never overwritten). */
export type FieldVerification = {
  id: number;
  extracted_field_id: number;
  field_name: string;
  verification_status: "verified" | "corrected";
  verified_value: Record<string, unknown> | null;
  comment: string | null;
  officer_identifier: string;
  evidence_ocr_block_id: string | null;
  evidence_visual_evidence_id: string | null;
  created_at: string;
};

export type AuditLogEntry = {
  id: number;
  inspection_id: string;
  action: string;
  actor: string;
  evaluation_id: number | null;
  rule_evaluation_id: number | null;
  decision: string | null;
  previous_state: string | null;
  comment: string | null;
  timestamp: string;
};

// AuditLogEntry is declared once, above — the Phase 9 section reuses it.

/** Overall assessment state — a rollup, never a score or certification. */
export type OverallStatus = "COMPLIANT" | "NON_COMPLIANT" | "REVIEW_REQUIRED" | "INCOMPLETE";

export type Evaluation = {
  inspection_id: string;
  evaluation_id: number;
  evaluation_version: number;
  engine_version: string;
  overall_status: OverallStatus;
  evaluated_at: string;
  results: RuleResult[];
  /** Phase 8: backend-derived effective rollup + pending-verification flag.
   * null when the payload predates the verification layer. */
  officer_effective_status: OverallStatus | null;
  verification_required: boolean | null;
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
  evaluation: Evaluation | null;
  visual_evidence: VisualEvidence[];
  /** Phase 8: officer verifications of extracted fields. */
  field_verifications: FieldVerification[];
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

// --- Phase 9: history, dashboard, evaluation versions, reports ---

export interface InspectionSummary {
  inspection_id: string;
  product_name: string | null;
  inspection_date: string;
  automated_status: string | null;
  officer_verified_status: string | null;
  effective_status: string | null;
  evaluation_version: number | null;
  verification_required: boolean;
  has_evaluation: boolean;
  created_at: string;
  updated_at: string;
}

export interface InspectionHistory {
  items: InspectionSummary[];
  page: number;
  page_size: number;
  total: number;
  pages: number;
}

export interface DashboardMetrics {
  total_inspections: number;
  automated: Record<string, number>;
  officer_effective: Record<string, number>;
  recent_inspections: Array<{
    inspection_id: string;
    product_name: string | null;
    created_at: string;
    automated_status: string | null;
    effective_status: string | null;
  }>;
}

export interface EvaluationVersion {
  evaluation_id: number;
  evaluation_version: number;
  engine_version: string;
  overall_status: string;
  created_at: string;
  has_officer_verification: boolean;
}

export interface ReportMeta {
  id: number;
  inspection_id: string;
  evaluation_id: number;
  evaluation_version: number;
  report_hash: string;
  storage_reference: string;
  generated_at: string;
}

export interface OfficerVerificationRecord {
  id: number;
  inspection_id: string;
  evaluation_id: number;
  rule_evaluation_id: number;
  decision: string;
  comment: string | null;
  officer_identifier: string;
  evidence_ocr_block_id: string | null;
  evidence_visual_evidence_id: string | null;
  evidence_extracted_field_id: number | null;
  created_at: string;
}

export interface FieldVerificationRecord {
  id: number;
  extracted_field_id: number;
  field_name: string;
  verification_status: string;
  verified_value: Record<string, unknown> | null;
  comment: string | null;
  officer_identifier: string;
  evidence_ocr_block_id: string | null;
  evidence_visual_evidence_id: string | null;
  created_at: string;
}
