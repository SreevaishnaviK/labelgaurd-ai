import { useCallback, useRef, useState } from "react";
import { AlertTriangle, FileText, Loader2, Upload, X } from "lucide-react";
import { UploadError, uploadInspection, validateFile } from "../lib/inspections";
import type { UploadSuccess } from "../types/api";

export type UploadPhase = "idle" | "uploading" | "processing" | "failed";

const btnPrimary =
  "inline-flex items-center justify-center gap-2 rounded-lg bg-brand-dark px-5 py-2.5 text-sm font-medium text-brand-white transition-colors hover:bg-brand-green disabled:cursor-not-allowed disabled:opacity-60";
const btnSecondary =
  "inline-flex items-center justify-center gap-2 rounded-lg border border-brand-border bg-brand-white px-5 py-2.5 text-sm font-medium text-brand-dark transition-colors hover:border-brand-green/40 hover:bg-brand-light";

const PROCESSING_STEPS = [
  "Validating image",
  "Preparing document",
  "Running OCR",
  "Extracting text regions",
];

function formatBytes(bytes: number) {
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export default function UploadFlow({ onCompleted }: { onCompleted: (result: UploadSuccess) => void }) {
  const [phase, setPhase] = useState<UploadPhase>("idle");
  const [file, setFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [validationMessage, setValidationMessage] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<{ code: string; message: string } | null>(null);
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const previewRef = useRef<string | null>(null);

  const setFileWithPreview = useCallback((next: File | null) => {
    if (previewRef.current) {
      URL.revokeObjectURL(previewRef.current);
      previewRef.current = null;
    }
    setFile(next);
    if (next && next.type.startsWith("image/")) {
      const url = URL.createObjectURL(next);
      previewRef.current = url;
      setPreviewUrl(url);
    } else {
      setPreviewUrl(null);
    }
  }, []);

  const clearFile = useCallback(() => {
    // Reset the phase too — after a failed upload it would otherwise stay
    // "failed" with no error shown, rendering an empty, dead dropzone.
    setPhase("idle");
    setFileWithPreview(null);
    setValidationMessage(null);
    setErrorMessage(null);
  }, [setFileWithPreview]);

  const acceptFile = useCallback(
    (candidate: File) => {
      const message = validateFile(candidate);
      if (message) {
        setFileWithPreview(null);
        setValidationMessage(message);
        return;
      }
      setPhase("idle");
      setValidationMessage(null);
      setErrorMessage(null);
      setFileWithPreview(candidate);
    },
    [setFileWithPreview],
  );

  const startUpload = useCallback(async () => {
    if (!file) return;
    setErrorMessage(null);
    setPhase("uploading");
    try {
      const result = await uploadInspection(file);
      setPhase("processing");
      // Keep the processing state visible briefly so the pipeline stages read;
      // the upload itself was real — this is presentation only.
      window.setTimeout(() => onCompleted(result), 1200);
    } catch (error) {
      const detail =
        error instanceof UploadError
          ? { code: error.code, message: error.message }
          : { code: "UPLOAD_FAILED", message: "Upload failed. Please try again." };
      setErrorMessage(detail);
      setPhase("failed");
    }
  }, [file, onCompleted]);

  const busy = phase === "uploading" || phase === "processing";

  return (
    <div
      onDragOver={(event) => {
        event.preventDefault();
        if (!busy) setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={(event) => {
        event.preventDefault();
        setDragging(false);
        const dropped = event.dataTransfer.files?.[0];
        if (dropped && !busy) acceptFile(dropped);
      }}
      className={`rounded-2xl border-2 border-dashed bg-brand-white transition-colors ${
        dragging ? "border-brand-green bg-brand-light/70" : "border-brand-border"
      } p-8 sm:p-12`}
    >
      <input
        ref={inputRef}
        type="file"
        accept=".png,.jpg,.jpeg,.pdf,image/png,image/jpeg,application/pdf"
        className="hidden"
        aria-label="Choose a product label file"
        onChange={(event) => {
          const chosen = event.target.files?.[0];
          if (chosen) acceptFile(chosen);
          event.target.value = "";
        }}
      />

      {phase === "idle" && !file && (
        <div className="flex flex-col items-center text-center">
          {dragging ? (
            <>
              <span className="mb-5 flex h-14 w-14 items-center justify-center rounded-full border border-brand-border bg-brand-light">
                <Upload className="h-6 w-6 text-brand-green" aria-hidden="true" />
              </span>
              <h3 className="text-lg font-medium text-brand-dark">Drop the label here</h3>
            </>
          ) : (
            <>
              <span className="mb-5 flex h-14 w-14 items-center justify-center rounded-full border border-brand-border bg-brand-light">
                <Upload className="h-6 w-6 text-brand-green" aria-hidden="true" />
              </span>
              <h3 className="text-lg font-medium text-brand-dark">Upload Product Label</h3>
              <p className="mt-1.5 text-sm text-brand-muted">PNG, JPG, JPEG or PDF</p>
              <p className="text-sm text-brand-muted">Maximum 20 MB</p>
              <button type="button" onClick={() => inputRef.current?.click()} className={`${btnPrimary} mt-6`}>
                <Upload className="h-4 w-4" aria-hidden="true" />
                Choose File
              </button>
              <span className="mt-3 text-sm text-brand-muted">or drag and drop</span>
            </>
          )}
          {validationMessage && (
            <p className="mt-4 max-w-md text-sm text-brand-danger" role="alert">
              {validationMessage}
            </p>
          )}
        </div>
      )}

      {phase === "idle" && file && (
        <div className="flex flex-col items-center gap-6 text-center">
          <div className="flex w-full max-w-md items-center gap-4 rounded-xl border border-brand-border bg-brand-light/60 p-4 text-left">
            {previewUrl ? (
              <img
                src={previewUrl}
                alt={`Preview of ${file.name}`}
                className="h-16 w-16 shrink-0 rounded-lg border border-brand-border object-cover"
              />
            ) : (
              <span className="flex h-16 w-16 shrink-0 items-center justify-center rounded-lg border border-brand-border bg-white">
                <FileText className="h-6 w-6 text-brand-green" aria-hidden="true" />
              </span>
            )}
            <span className="min-w-0 flex-1">
              <span className="block truncate text-sm font-medium text-brand-dark">{file.name}</span>
              <span className="block text-xs text-brand-muted">{formatBytes(file.size)}</span>
            </span>
            <button
              type="button"
              onClick={clearFile}
              className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-brand-border bg-white text-brand-muted transition-colors hover:text-brand-danger"
              aria-label={`Remove file ${file.name}`}
            >
              <X className="h-4 w-4" aria-hidden="true" />
            </button>
          </div>
          <div className="flex flex-col items-center gap-3 sm:flex-row">
            <button type="button" onClick={startUpload} className={btnPrimary}>
              <Upload className="h-4 w-4" aria-hidden="true" />
              Run OCR Inspection
            </button>
            <button type="button" onClick={() => inputRef.current?.click()} className={btnSecondary}>
              Choose Different File
            </button>
          </div>
        </div>
      )}

      {busy && (
        <div className="flex flex-col items-center text-center">
          <Loader2 className="h-8 w-8 animate-spin text-brand-green" aria-hidden="true" />
          <h3 className="mt-5 text-lg font-medium text-brand-dark">
            {phase === "uploading" ? "Uploading product label..." : "Analyzing label image"}
          </h3>
          {phase === "processing" && (
            <ul className="mt-5 space-y-2 text-left" aria-live="polite">
              {PROCESSING_STEPS.map((step) => (
                <li key={step} className="flex items-center gap-2.5 text-sm text-brand-muted">
                  <span className="h-1.5 w-1.5 rounded-full bg-brand-green" aria-hidden="true" />
                  {step}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {phase === "failed" && errorMessage && (
        <div className="flex flex-col items-center text-center">
          <AlertTriangle className="h-10 w-10 text-brand-danger" aria-hidden="true" />
          <h3 className="mt-4 text-lg font-medium text-brand-dark">Upload failed</h3>
          <p className="mt-2 max-w-md text-sm leading-relaxed text-brand-muted" role="alert">
            {errorMessage.message}
          </p>
          <p className="mt-1 font-mono text-xs text-brand-muted">{errorMessage.code}</p>
          <div className="mt-6 flex flex-col gap-3 sm:flex-row">
            <button type="button" onClick={startUpload} className={btnPrimary}>
              Try Again
            </button>
            <button type="button" onClick={clearFile} className={btnSecondary}>
              Choose Another File
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
