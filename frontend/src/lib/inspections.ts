/**
 * Inspection API client. All calls go through apiUrl() — no hardcoded hosts.
 */
import { apiUrl } from "./api";
import type { ApiErrorDetail, Evaluation, Inspection, UploadSuccess } from "../types/api";

const MAX_SIZE_MB = 20;
export const ALLOWED_MIME_TYPES = ["image/png", "image/jpeg", "application/pdf"];

export class UploadError extends Error {
  code: string;
  constructor(detail: ApiErrorDetail) {
    super(detail.message);
    this.code = detail.code;
  }
}

export function validateFile(file: File): string | null {
  const extension = file.name.split(".").pop()?.toLowerCase() ?? "";
  const extensionOk = ["png", "jpg", "jpeg", "pdf"].includes(extension);
  const mimeOk = ALLOWED_MIME_TYPES.includes(file.type);
  if (!extensionOk || (file.type !== "" && !mimeOk)) {
    return "Unsupported file format. Please upload PNG, JPG, JPEG or PDF.";
  }
  if (file.size > MAX_SIZE_MB * 1024 * 1024) {
    return `File exceeds the ${MAX_SIZE_MB} MB limit.`;
  }
  if (file.size === 0) {
    return "The selected file is empty.";
  }
  return null;
}

async function errorFromResponse(response: Response): Promise<UploadError> {
  try {
    const body = await response.json();
    const detail = body?.detail;
    if (detail && typeof detail === "object" && "code" in detail) {
      return new UploadError(detail as ApiErrorDetail);
    }
  } catch {
    /* fall through */
  }
  return new UploadError({ code: "UPLOAD_FAILED", message: `Upload failed (${response.status}).` });
}

export async function uploadInspection(file: File): Promise<UploadSuccess> {
  const validationMessage = validateFile(file);
  if (validationMessage) {
    throw new UploadError({ code: "INVALID_FILE", message: validationMessage });
  }
  const form = new FormData();
  form.append("file", file);
  const response = await fetch(apiUrl("/api/v1/inspections/upload"), {
    method: "POST",
    body: form,
  });
  if (!response.ok) {
    throw await errorFromResponse(response);
  }
  return (await response.json()) as UploadSuccess;
}

export async function fetchInspection(inspectionId: string): Promise<Inspection> {
  const response = await fetch(apiUrl(`/api/v1/inspections/${encodeURIComponent(inspectionId)}`));
  if (!response.ok) {
    throw await errorFromResponse(response);
  }
  return (await response.json()) as Inspection;
}

export function inspectionImageUrl(inspectionId: string): string {
  return apiUrl(`/api/v1/inspections/${encodeURIComponent(inspectionId)}/image`);
}

/** Run a new automated evaluation version over the persisted inspection. */
export async function evaluateInspection(inspectionId: string): Promise<Evaluation> {
  const response = await fetch(
    apiUrl(`/api/v1/inspections/${encodeURIComponent(inspectionId)}/evaluate`),
    { method: "POST" },
  );
  if (!response.ok) {
    throw await errorFromResponse(response);
  }
  return (await response.json()) as Evaluation;
}

/** Record one officer decision on an immutable rule evaluation (Phase 8). */
export async function createRuleVerification(
  inspectionId: string,
  payload: {
    rule_evaluation_id: number;
    decision: string;
    comment?: string | null;
    evidence_ocr_block_id?: string | null;
    evidence_visual_evidence_id?: string | null;
    evidence_extracted_field_id?: number | null;
  },
): Promise<void> {
  const response = await fetch(
    apiUrl(`/api/v1/inspections/${encodeURIComponent(inspectionId)}/verifications`),
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
  );
  if (!response.ok) {
    throw await errorFromResponse(response);
  }
}

/** Record one officer verification of an extracted field — the original
 * extracted value is never modified. */
export async function createFieldVerification(
  inspectionId: string,
  payload: {
    extracted_field_id: number;
    verification_status: "verified" | "corrected";
    verified_value?: Record<string, unknown> | null;
    comment?: string | null;
    evidence_ocr_block_id?: string | null;
  },
): Promise<void> {
  const response = await fetch(
    apiUrl(`/api/v1/inspections/${encodeURIComponent(inspectionId)}/field-verifications`),
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
  );
  if (!response.ok) {
    throw await errorFromResponse(response);
  }
}
