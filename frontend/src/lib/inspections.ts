/**
 * Inspection API client. All calls go through apiUrl() — no hardcoded hosts.
 */
import { apiUrl } from "./api";
import type { ApiErrorDetail, Inspection, UploadSuccess } from "../types/api";

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
