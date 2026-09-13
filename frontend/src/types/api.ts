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
};

export type FileMeta = {
  original_filename: string;
  document_type: string;
};

export type InspectionStatus = "uploaded" | "processing" | "processed" | "failed";

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
