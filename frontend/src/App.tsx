import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Activity,
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  CheckCircle2,
  ChevronDown,
  CircleHelp,
  ClipboardCheck,
  Download,
  Eye,
  FileCheck,
  FileText,
  History,
  LayoutDashboard,
  Loader2,
  Menu,
  ScanLine,
  Search,
  Upload,
  X,
  XCircle,
  type LucideIcon,
} from "lucide-react";

/* ---------------------------------- types --------------------------------- */

type View = "dashboard" | "inspect" | "analyzing" | "results" | "reports" | "history";
type StatusTone = "compliant" | "review" | "violation";
type UploadInfo = { name: string; size: number };

interface ChecklistItem {
  id: string;
  requirement: string;
  status: StatusTone;
  detail: string;
  confidence: number;
  evidence: string | null;
}

interface Finding {
  id: string;
  requirement: string;
  status: StatusTone;
  checked: string;
  findingText: string;
  confidence: number;
  evidence: string;
}

interface InspectionRecord {
  id: string;
  product: string;
  manufacturer: string;
  inspector: string;
  date: string; // ISO
  score: number;
  status: StatusTone;
}

type StatusFilter = "all" | StatusTone;
type SortKey = "newest" | "oldest" | "score-desc" | "score-asc";

const APP_NAME = "LabelGuard AI";

/* --------------------------------- helpers -------------------------------- */

function cx(...parts: Array<string | false | null | undefined>) {
  return parts.filter(Boolean).join(" ");
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function formatDisplayDate(iso: string) {
  const [y, m, d] = iso.split("-").map(Number);
  return `${d} ${MONTHS[m - 1]} ${y}`;
}

function formatBytes(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/* ------------------------------ status system ----------------------------- */

/**
 * Status tone metadata. `label` is the badge wording used for overall status,
 * findings, and table rows; `checklistLabel` is the wording the compliance
 * checklist rows must use ("Review Required" per the §13 spec).
 */
const STATUS_META: Record<
  StatusTone,
  { label: string; checklistLabel: string; badge: string; text: string; icon: LucideIcon }
> = {
  compliant: {
    label: "Compliant",
    checklistLabel: "Compliant",
    badge: "border-brand-success/25 bg-brand-success/10 text-brand-success",
    text: "text-brand-success",
    icon: CheckCircle2,
  },
  review: {
    label: "Needs Review",
    checklistLabel: "Review Required",
    badge: "border-brand-warning/25 bg-brand-warning/10 text-brand-warning",
    text: "text-brand-warning",
    icon: AlertTriangle,
  },
  violation: {
    label: "Violation Detected",
    checklistLabel: "Violation Detected",
    badge: "border-brand-danger/25 bg-brand-danger/10 text-brand-danger",
    text: "text-brand-danger",
    icon: XCircle,
  },
};

function StatusBadge({
  status,
  className,
  variant = "default",
}: {
  status: StatusTone;
  className?: string;
  variant?: "default" | "checklist";
}) {
  const meta = STATUS_META[status];
  const Icon = meta.icon;
  return (
    <span
      className={cx(
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium whitespace-nowrap",
        meta.badge,
        className,
      )}
    >
      <Icon className="h-3.5 w-3.5" aria-hidden="true" />
      {variant === "checklist" ? meta.checklistLabel : meta.label}
    </span>
  );
}

/* ------------------------------- shared styles ----------------------------- */

const btnPrimary =
  "inline-flex items-center justify-center gap-2 rounded-lg bg-brand-dark px-5 py-2.5 text-sm font-medium text-brand-white transition-colors hover:bg-brand-green active:bg-brand-dark";
const btnSecondary =
  "inline-flex items-center justify-center gap-2 rounded-lg border border-brand-border bg-brand-white px-5 py-2.5 text-sm font-medium text-brand-dark transition-colors hover:border-brand-green/40 hover:bg-brand-light";
const btnGhost =
  "inline-flex items-center justify-center gap-2 rounded-lg px-4 py-2.5 text-sm font-medium text-brand-muted transition-colors hover:bg-brand-light hover:text-brand-dark";
const btnTable =
  "inline-flex items-center gap-1.5 rounded-lg border border-brand-border bg-white px-3 py-1.5 text-xs font-medium text-brand-dark transition-colors hover:bg-brand-light";
const card = "rounded-2xl border border-brand-border bg-brand-white";
const inputBase =
  "h-10 w-full rounded-lg border border-brand-border bg-white px-3 text-sm text-brand-dark placeholder:text-brand-muted/70";

/* -------------------------------- demo data ------------------------------- */

const DEMO_PRODUCT = {
  name: "Premium Wheat Flour",
  manufacturer: "ABC Foods Pvt. Ltd.",
  netQuantity: "1 kg",
  mrp: "₹68.00",
  customerCare: "1800-XXX-XXXX",
};

const DEMO_INSPECTION = {
  date: "2026-09-13",
  score: 82,
  status: "review" as StatusTone,
};

const CHECKLIST: ChecklistItem[] = [
  {
    id: "product-name",
    requirement: "Product Name",
    status: "compliant",
    detail:
      "Product name is clearly declared on the principal display panel and was extracted with high confidence.",
    confidence: 96,
    evidence: "product-name",
  },
  {
    id: "manufacturer",
    requirement: "Manufacturer / Packer Details",
    status: "compliant",
    detail: "Manufacturer name was identified along with packer or marketer details.",
    confidence: 94,
    evidence: "manufacturer",
  },
  {
    id: "address",
    requirement: "Address",
    status: "compliant",
    detail: "A complete postal address was detected on the label panel.",
    confidence: 92,
    evidence: "manufacturer",
  },
  {
    id: "net-qty",
    requirement: "Net Quantity",
    status: "compliant",
    detail: "Standard unit of measure declared in the prescribed manner.",
    confidence: 97,
    evidence: "net-qty",
  },
  {
    id: "mrp",
    requirement: "MRP",
    status: "review",
    detail:
      "A declared retail price was detected, but print legibility is low. Officer should confirm the declared MRP against the physical label.",
    confidence: 78,
    evidence: "mrp",
  },
  {
    id: "date",
    requirement: "Date of Manufacture / Packing",
    status: "compliant",
    detail: "Date of packing was detected and appears to follow the required format.",
    confidence: 90,
    evidence: "date",
  },
  {
    id: "consumer-care",
    requirement: "Consumer Care Details",
    status: "review",
    detail:
      "A toll-free number was detected, but the e-mail or postal consumer care details could not be confidently extracted.",
    confidence: 74,
    evidence: "consumer-care",
  },
  {
    id: "declaration",
    requirement: "Mandatory Declarations",
    status: "violation",
    detail:
      "The required declaration could not be confidently identified on the submitted label.",
    confidence: 87,
    evidence: "declaration",
  },
];

const FINDINGS: Finding[] = [
  {
    id: "finding-mrp",
    requirement: "MRP — Declared Retail Sale Price",
    status: "review",
    checked:
      "A legible maximum retail price, inclusive of all taxes, declared on the principal display panel.",
    findingText:
      "A price of ₹68.00 was detected, but the print region is partially illegible in the submitted image. The exact declared MRP should be confirmed against the physical package.",
    confidence: 78,
    evidence: "mrp",
  },
  {
    id: "finding-consumer-care",
    requirement: "Consumer Care Details",
    status: "review",
    checked: "Consumer care contact details — phone number and e-mail or postal address.",
    findingText:
      "A toll-free number was identified. The e-mail address region was blurred and could not be extracted with sufficient confidence.",
    confidence: 74,
    evidence: "consumer-care",
  },
  {
    id: "finding-declaration",
    requirement: "Mandatory Declaration",
    status: "violation",
    checked: "The mandatory declaration block required for this commodity category.",
    findingText:
      "The required declaration could not be confidently identified on the submitted label. The declarations panel was extracted, but no matching text was recognized.",
    confidence: 87,
    evidence: "declaration",
  },
];

/** Single source of truth for inspections — Reports and History both derive from it. */
const INSPECTIONS_SEED: InspectionRecord[] = [
  { id: "LGA-2026-00124", product: "Premium Wheat Flour", manufacturer: "ABC Foods Pvt. Ltd.", inspector: "Officer A. Sharma", date: "2026-09-13", score: 82, status: "review" },
  { id: "LGA-2026-00123", product: "Sunflower Refined Oil", manufacturer: "Gold Harvest Foods", inspector: "Officer R. Iyer", date: "2026-09-12", score: 95, status: "compliant" },
  { id: "LGA-2026-00122", product: "Instant Masala Noodles", manufacturer: "Spice Kraft Foods", inspector: "Officer K. Nair", date: "2026-09-12", score: 64, status: "violation" },
  { id: "LGA-2026-00121", product: "Mixed Fruit Juice 1L", manufacturer: "Orchard Fresh Beverages", inspector: "Officer S. Verma", date: "2026-09-11", score: 91, status: "compliant" },
  { id: "LGA-2026-00120", product: "Antibacterial Hand Wash", manufacturer: "CleanCo Home Care", inspector: "Officer A. Sharma", date: "2026-09-10", score: 88, status: "compliant" },
  { id: "LGA-2026-00119", product: "Chocolate Biscuits 120g", manufacturer: "SweetCrust Bakers", inspector: "Officer R. Iyer", date: "2026-09-09", score: 73, status: "review" },
  { id: "LGA-2026-00118", product: "Basmati Rice 5kg", manufacturer: "GreenField Agro", inspector: "Officer S. Verma", date: "2026-09-08", score: 96, status: "compliant" },
  { id: "LGA-2026-00117", product: "Detergent Powder 1kg", manufacturer: "CleanCo Home Care", inspector: "Officer K. Nair", date: "2026-09-07", score: 58, status: "violation" },
];

const PIPELINE_STEPS: { num: string; label: string; icon: LucideIcon }[] = [
  { num: "01", label: "Upload", icon: Upload },
  { num: "02", label: "Extract", icon: ScanLine },
  { num: "03", label: "Analyze", icon: Activity },
  { num: "04", label: "Verify", icon: ClipboardCheck },
  { num: "05", label: "Report", icon: FileCheck },
];

const ANALYSIS_STEPS = [
  "Image received",
  "Extracting label information",
  "Checking compliance requirements",
  "Preparing assessment",
];

const STEP_DURATIONS = [700, 900, 1200, 900];

/* --------------------------------- navbar --------------------------------- */

const NAV_LINKS: { id: View; label: string; icon: LucideIcon }[] = [
  { id: "dashboard", label: "Dashboard", icon: LayoutDashboard },
  { id: "inspect", label: "Inspect Product", icon: ScanLine },
  { id: "reports", label: "Reports", icon: FileText },
  { id: "history", label: "History", icon: History },
];

function activeNavId(view: View): View {
  if (view === "analyzing" || view === "results") return "inspect";
  return view;
}

function Navbar({
  view,
  navOpen,
  onNavOpenChange,
  onNavigate,
  scrolled,
}: {
  view: View;
  navOpen: boolean;
  onNavOpenChange: (open: boolean) => void;
  onNavigate: (view: View) => void;
  scrolled: boolean;
}) {
  const active = activeNavId(view);

  useEffect(() => {
    if (!navOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onNavOpenChange(false);
    };
    document.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
    };
  }, [navOpen, onNavOpenChange]);

  return (
    <>
      <header
        className={cx(
          "sticky top-0 z-40 border-b transition-colors duration-300",
          scrolled
            ? "border-brand-border bg-brand-cream/85 backdrop-blur-md"
            : "border-transparent bg-brand-cream",
        )}
      >
        <div className="mx-auto flex h-18 max-w-7xl items-center justify-between gap-4 px-4 sm:px-6 lg:px-8">
          <button
            type="button"
            onClick={() => onNavigate("dashboard")}
            className="flex items-center gap-2.5 rounded-lg text-left"
            aria-label={`${APP_NAME} — go to dashboard`}
          >
            <img
              src="/labelguard-mark.png"
              alt=""
              className="h-10 w-10 shrink-0 object-contain"
              width={40}
              height={40}
            />
            <span className="text-lg font-semibold tracking-tight text-brand-dark">{APP_NAME}</span>
          </button>

          <nav className="hidden items-center gap-1 lg:flex" aria-label="Primary">
            {NAV_LINKS.map((link) => (
              <button
                key={link.id}
                type="button"
                onClick={() => onNavigate(link.id)}
                aria-current={active === link.id ? "page" : undefined}
                className={cx(
                  "rounded-full px-4 py-2 text-sm transition-colors",
                  active === link.id
                    ? "bg-brand-light font-medium text-brand-dark"
                    : "text-brand-muted hover:bg-brand-light/70 hover:text-brand-dark",
                )}
              >
                {link.label}
              </button>
            ))}
          </nav>

          <div className="flex items-center gap-3">
            <span
              className="hidden items-center gap-2 rounded-full border border-brand-border bg-brand-white px-3 py-1.5 md:inline-flex"
              title="All inspection services operational"
            >
              <span className="relative flex h-2 w-2">
                <span className="absolute inline-flex h-full w-full rounded-full bg-brand-success opacity-40" aria-hidden="true" />
                <span className="relative inline-flex h-2 w-2 rounded-full bg-brand-success" aria-hidden="true" />
              </span>
              <span className="text-xs font-medium text-brand-muted">System Online</span>
            </span>

            <button type="button" onClick={() => onNavigate("inspect")} className={cx(btnPrimary, "hidden sm:inline-flex")}>
              New Inspection
            </button>

            <button
              type="button"
              className="inline-flex h-10 w-10 items-center justify-center rounded-lg border border-brand-border bg-brand-white text-brand-dark transition-colors hover:bg-brand-light lg:hidden"
              aria-label={navOpen ? "Close navigation menu" : "Open navigation menu"}
              aria-expanded={navOpen}
              onClick={() => onNavOpenChange(!navOpen)}
            >
              {navOpen ? <X className="h-5 w-5" aria-hidden="true" /> : <Menu className="h-5 w-5" aria-hidden="true" />}
            </button>
          </div>
        </div>
      </header>

      {navOpen && (
        <div
          className="fixed inset-0 z-50 flex flex-col bg-brand-cream lg:hidden"
          role="dialog"
          aria-modal="true"
          aria-label="Navigation menu"
        >
          <div className="mx-auto flex h-18 w-full max-w-7xl items-center justify-between px-4 sm:px-6">
            <span className="flex items-center gap-2.5">
              <img
                src="/labelguard-mark.png"
                alt=""
                className="h-10 w-10 shrink-0 object-contain"
                width={40}
                height={40}
              />
              <span className="text-lg font-semibold tracking-tight text-brand-dark">{APP_NAME}</span>
            </span>
            <button
              type="button"
              className="inline-flex h-10 w-10 items-center justify-center rounded-lg border border-brand-border bg-brand-white text-brand-dark"
              aria-label="Close navigation menu"
              onClick={() => onNavOpenChange(false)}
            >
              <X className="h-5 w-5" aria-hidden="true" />
            </button>
          </div>

          <nav className="mx-auto flex w-full max-w-7xl flex-1 flex-col gap-2 px-4 pt-6 sm:px-6" aria-label="Mobile">
            {NAV_LINKS.map((link) => {
              const Icon = link.icon;
              return (
                <button
                  key={link.id}
                  type="button"
                  onClick={() => onNavigate(link.id)}
                  aria-current={active === link.id ? "page" : undefined}
                  className={cx(
                    "flex items-center gap-3 rounded-xl border px-4 py-4 text-left text-base transition-colors",
                    active === link.id
                      ? "border-brand-green/30 bg-brand-light font-medium text-brand-dark"
                      : "border-brand-border bg-brand-white text-brand-muted",
                  )}
                >
                  <Icon className="h-5 w-5" aria-hidden="true" />
                  {link.label}
                  <ArrowRight className="ml-auto h-4 w-4 text-brand-border" aria-hidden="true" />
                </button>
              );
            })}
          </nav>

          <div className="mx-auto w-full max-w-7xl px-4 pb-10 sm:px-6">
            <span className="mb-4 inline-flex items-center gap-2 rounded-full border border-brand-border bg-brand-white px-3 py-1.5">
              <span className="relative flex h-2 w-2">
                <span className="absolute inline-flex h-full w-full rounded-full bg-brand-success opacity-40" aria-hidden="true" />
                <span className="relative inline-flex h-2 w-2 rounded-full bg-brand-success" aria-hidden="true" />
              </span>
              <span className="text-xs font-medium text-brand-muted">System Online</span>
            </span>
            <button
              type="button"
              onClick={() => onNavigate("inspect")}
              className={cx(btnPrimary, "w-full py-3.5 text-base")}
            >
              New Inspection
              <ArrowRight className="h-4 w-4" aria-hidden="true" />
            </button>
          </div>
        </div>
      )}
    </>
  );
}

/* ------------------------------ page furniture ----------------------------- */

function SectionHeader({
  eyebrow,
  title,
  text,
  right,
}: {
  eyebrow?: string;
  title: React.ReactNode;
  text?: string;
  right?: React.ReactNode;
}) {
  return (
    <div className="mb-8 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
      <div className="max-w-2xl">
        {eyebrow && (
          <p className="mb-2 text-[11px] font-semibold tracking-[0.2em] text-brand-green uppercase">{eyebrow}</p>
        )}
        <h2 className="text-2xl font-light tracking-tight text-brand-dark sm:text-3xl">{title}</h2>
        {text && <p className="mt-2 text-sm leading-relaxed text-brand-muted sm:text-base">{text}</p>}
      </div>
      {right && <div className="shrink-0">{right}</div>}
    </div>
  );
}

function BackButton({ onClick, label = "Back to Dashboard" }: { onClick: () => void; label?: string }) {
  return (
    <button type="button" onClick={onClick} className={cx(btnGhost, "-ml-4 mb-6")}>
      <ArrowLeft className="h-4 w-4" aria-hidden="true" />
      {label}
    </button>
  );
}

function EmptyState({
  icon: Icon,
  title,
  text,
  actionLabel,
  onAction,
}: {
  icon: LucideIcon;
  title: string;
  text: string;
  actionLabel?: string;
  onAction?: () => void;
}) {
  return (
    <div className={cx(card, "flex flex-col items-center px-6 py-16 text-center")}>
      <span className="mb-5 flex h-14 w-14 items-center justify-center rounded-full border border-brand-border bg-brand-light">
        <Icon className="h-6 w-6 text-brand-green" aria-hidden="true" />
      </span>
      <h3 className="text-lg font-medium text-brand-dark">{title}</h3>
      <p className="mt-2 max-w-sm text-sm leading-relaxed text-brand-muted">{text}</p>
      {actionLabel && onAction && (
        <button type="button" onClick={onAction} className={cx(btnPrimary, "mt-6")}>
          {actionLabel}
          <ArrowRight className="h-4 w-4" aria-hidden="true" />
        </button>
      )}
    </div>
  );
}

function DemoNote({ className }: { className?: string }) {
  return (
    <p className={cx("text-xs leading-relaxed text-brand-muted", className)}>
      Demonstration environment — inspections, products and results shown are illustrative sample data for
      presentation purposes.
    </p>
  );
}

/* ------------------------------- score ring ------------------------------- */

function ScoreRing({ score }: { score: number }) {
  const size = 176;
  const stroke = 12;
  const r = (size - stroke) / 2;
  const circumference = 2 * Math.PI * r;
  const [drawn, setDrawn] = useState(false);

  useEffect(() => {
    const id = requestAnimationFrame(() => setDrawn(true));
    return () => cancelAnimationFrame(id);
  }, []);

  const offset = circumference * (1 - (drawn ? score : 0) / 100);

  return (
    <div className="relative" style={{ width: size, height: size }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} role="img" aria-label={`Compliance score ${score} out of 100`}>
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke="var(--color-brand-border)"
          strokeWidth={stroke}
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke="var(--color-brand-green)"
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          transform={`rotate(-90 ${size / 2} ${size / 2})`}
          className="transition-[stroke-dashoffset] duration-1000 ease-out"
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="text-4xl font-light tracking-tight text-brand-dark" aria-hidden="true">
          {score}
          <span className="text-lg text-brand-muted"> / 100</span>
        </span>
        <span className="mt-1 text-[11px] font-semibold tracking-[0.14em] text-brand-muted uppercase">
          Compliance Score
        </span>
      </div>
    </div>
  );
}

/* --------------------------------- upload --------------------------------- */

function UploadCard({
  upload,
  onFile,
  onRun,
  onClear,
  onSample,
  compact = false,
}: {
  upload: UploadInfo | null;
  onFile: (file: File) => void;
  onRun: () => void;
  onClear: () => void;
  onSample?: () => void;
  compact?: boolean;
}) {
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const openPicker = () => inputRef.current?.click();

  return (
    <div
      onDragOver={(e) => {
        e.preventDefault();
        setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDragging(false);
        const file = e.dataTransfer.files?.[0];
        if (file) onFile(file);
      }}
      className={cx(
        "rounded-2xl border-2 border-dashed bg-brand-white transition-colors",
        dragging ? "border-brand-green bg-brand-light/70" : "border-brand-border",
        compact ? "p-6 sm:p-8" : "p-8 sm:p-12",
      )}
    >
      <input
        ref={inputRef}
        type="file"
        accept=".png,.jpg,.jpeg,.pdf,image/png,image/jpeg,application/pdf"
        className="hidden"
        aria-label="Choose a product label file"
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) onFile(file);
          e.target.value = "";
        }}
      />

      {!upload ? (
        <div className="flex flex-col items-center text-center">
          <span className="mb-5 flex h-14 w-14 items-center justify-center rounded-full border border-brand-border bg-brand-light">
            <Upload className="h-6 w-6 text-brand-green" aria-hidden="true" />
          </span>
          <h3 className="text-lg font-medium text-brand-dark">Upload Product Label</h3>
          <p className="mt-1.5 text-sm text-brand-muted">PNG, JPG or PDF up to 20 MB</p>
          <div className="mt-6 flex flex-col items-center gap-3 sm:flex-row">
            <button type="button" onClick={openPicker} className={btnPrimary}>
              <Upload className="h-4 w-4" aria-hidden="true" />
              Choose File
            </button>
            {onSample && (
              <button type="button" onClick={onSample} className={btnSecondary}>
                <FileText className="h-4 w-4" aria-hidden="true" />
                Use Sample Label
              </button>
            )}
            <span className="text-sm text-brand-muted">or drag and drop</span>
          </div>
        </div>
      ) : (
        <div className="flex flex-col items-center gap-6 text-center">
          <div className="flex w-full max-w-md items-center gap-3 rounded-xl border border-brand-border bg-brand-light/60 p-4 text-left">
            <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-brand-white border border-brand-border">
              <FileText className="h-5 w-5 text-brand-green" aria-hidden="true" />
            </span>
            <span className="min-w-0 flex-1">
              <span className="block truncate text-sm font-medium text-brand-dark">{upload.name}</span>
              <span className="block text-xs text-brand-muted">{formatBytes(upload.size)} · ready for inspection</span>
            </span>
            <button
              type="button"
              onClick={onClear}
              className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-brand-border bg-white text-brand-muted transition-colors hover:bg-white hover:text-brand-danger"
              aria-label={`Remove file ${upload.name}`}
            >
              <X className="h-4 w-4" aria-hidden="true" />
            </button>
          </div>
          <div className="flex flex-col items-center gap-3 sm:flex-row">
            <button type="button" onClick={onRun} className={btnPrimary}>
              Run AI Inspection
              <ArrowRight className="h-4 w-4" aria-hidden="true" />
            </button>
            <button type="button" onClick={openPicker} className={btnSecondary}>
              Choose Different File
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

/* -------------------------------- pipeline -------------------------------- */

function Pipeline({ activeStep = 0 }: { activeStep?: number }) {
  return (
    <ol className="grid grid-cols-5 items-start gap-1 sm:flex sm:items-center sm:justify-between sm:gap-2" aria-label="AI inspection pipeline">
      {PIPELINE_STEPS.map((step, i) => {
        const Icon = step.icon;
        const isActive = i === activeStep;
        return (
          <li key={step.num} className="contents sm:contents">
            <div className="flex flex-col items-center gap-2 text-center">
              <span
                className={cx(
                  "flex h-11 w-11 items-center justify-center rounded-full border transition-colors",
                  isActive
                    ? "border-brand-dark bg-brand-dark text-brand-white"
                    : "border-brand-border bg-brand-white text-brand-muted",
                )}
              >
                <Icon className="h-5 w-5" aria-hidden="true" />
              </span>
              <span className={cx("text-[10px] font-semibold tracking-[0.18em]", isActive ? "text-brand-dark" : "text-brand-muted")}>
                {step.num}
              </span>
              <span className={cx("text-xs sm:text-sm", isActive ? "font-semibold text-brand-dark" : "font-medium text-brand-muted")}>
                {step.label}
              </span>
            </div>
            {i < PIPELINE_STEPS.length - 1 && (
              <span className="hidden sm:block" aria-hidden="true">
                <ArrowRight className="h-4 w-4 text-brand-border" />
              </span>
            )}
          </li>
        );
      })}
    </ol>
  );
}

/* -------------------------------- dashboard ------------------------------- */

const METRICS: { label: string; value: number; icon: LucideIcon }[] = [
  { label: "Total Inspections", value: 248, icon: ClipboardCheck },
  { label: "Compliant", value: 187, icon: CheckCircle2 },
  { label: "Needs Review", value: 39, icon: CircleHelp },
  { label: "Violations Detected", value: 22, icon: AlertTriangle },
];

function DashboardView({
  upload,
  onFile,
  onRun,
  onClear,
  onNavigate,
}: {
  upload: UploadInfo | null;
  onFile: (file: File) => void;
  onRun: () => void;
  onClear: () => void;
  onNavigate: (view: View) => void;
}) {
  return (
    <div className="mx-auto max-w-7xl px-4 pb-20 sm:px-6 lg:px-8">
      {/* Hero */}
      <section className="animate-fade-up py-14 sm:py-20">
        <p className="text-[11px] font-semibold tracking-[0.24em] text-brand-green uppercase">
          AI-Powered Compliance Inspection
        </p>
        <h1 className="mt-4 max-w-3xl text-4xl font-light tracking-tight text-balance text-brand-dark sm:text-5xl lg:text-6xl">
          {APP_NAME}
        </h1>
        <p className="mt-5 max-w-2xl text-base leading-relaxed text-brand-muted sm:text-lg">
          AI-powered compliance inspection for packaged commodity labels.
        </p>
        <div className="mt-8 flex flex-col gap-3 sm:flex-row">
          <button type="button" onClick={() => onNavigate("inspect")} className={btnPrimary}>
            Start New Inspection
            <ArrowRight className="h-4 w-4" aria-hidden="true" />
          </button>
          <button type="button" onClick={() => onNavigate("history")} className={btnSecondary}>
            <History className="h-4 w-4" aria-hidden="true" />
            View Inspection History
          </button>
        </div>
      </section>

      {/* Overview */}
      <section className="animate-fade-up py-4" style={{ animationDelay: "80ms" }}>
        <SectionHeader
          eyebrow="Overview"
          title="Compliance Overview"
          text="Monitor inspections and identify products requiring attention."
        />
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {METRICS.map((m) => {
            const Icon = m.icon;
            return (
              <div
                key={m.label}
                className={cx(card, "group p-6 transition-all duration-300 hover:-translate-y-0.5 hover:border-brand-green/30 hover:shadow-sm")}
              >
                <span className="flex h-10 w-10 items-center justify-center rounded-lg bg-brand-light">
                  <Icon className="h-5 w-5 text-brand-green" aria-hidden="true" />
                </span>
                <p className="mt-5 text-3xl font-light tracking-tight text-brand-dark">{m.value}</p>
                <p className="mt-1 text-sm font-medium text-brand-muted">{m.label}</p>
              </div>
            );
          })}
        </div>
      </section>

      {/* Inspection workspace */}
      <section className="animate-fade-up py-14" style={{ animationDelay: "140ms" }} aria-labelledby="inspect-heading">
        <SectionHeader
          title="Inspect a Product"
          text="Upload product packaging or label images to begin an automated compliance inspection."
        />
        <UploadCard upload={upload} onFile={onFile} onRun={onRun} onClear={onClear} />
        <DemoNote className="mt-3" />
      </section>

      {/* Pipeline */}
      <section className="animate-fade-up pb-8" style={{ animationDelay: "200ms" }} aria-labelledby="pipeline-heading">
        <div className={cx(card, "p-6 sm:p-8")}>
          <div className="mb-8 flex flex-col gap-1">
            <h3 id="pipeline-heading" className="text-sm font-semibold tracking-[0.14em] text-brand-muted uppercase">
              AI Inspection Pipeline
            </h3>
            <p className="text-sm text-brand-muted">
              Every inspection moves through a five-stage pipeline — from raw image to an evidence-backed, officer-ready report.
            </p>
          </div>
          <Pipeline activeStep={0} />
        </div>
      </section>
    </div>
  );
}

/* --------------------------------- inspect --------------------------------- */

function InspectView({
  upload,
  onFile,
  onRun,
  onClear,
  onSample,
  onNavigate,
}: {
  upload: UploadInfo | null;
  onFile: (file: File) => void;
  onRun: () => void;
  onClear: () => void;
  onSample: () => void;
  onNavigate: (view: View) => void;
}) {
  return (
    <div className="mx-auto max-w-7xl animate-fade-up px-4 pb-20 sm:px-6 lg:px-8">
      <div className="pt-8 sm:pt-12">
        <BackButton onClick={() => onNavigate("dashboard")} />
        <SectionHeader
          eyebrow="Product Inspection"
          title="Inspect a Product"
          text="Upload product packaging or label images to begin an automated compliance inspection."
        />
      </div>

      <div className="grid gap-6 lg:grid-cols-5">
        <div className="lg:col-span-3">
          <UploadCard
            upload={upload}
            onFile={onFile}
            onRun={onRun}
            onClear={onClear}
            onSample={onSample}
          />
          <DemoNote className="mt-3" />
        </div>

        <aside className="lg:col-span-2">
          <div className={cx(card, "p-6 sm:p-8")}>
            <h3 className="text-sm font-semibold tracking-[0.14em] text-brand-muted uppercase">
              What the AI Checks
            </h3>
            <p className="mt-2 text-sm leading-relaxed text-brand-muted">
              Each inspection evaluates mandatory declarations under Legal Metrology / Packaged Commodities
              requirements, including:
            </p>
            <ul className="mt-5 space-y-3">
              {[
                "Product name and principal display details",
                "Manufacturer, packer and address details",
                "Net quantity in the standard unit of measure",
                "Declared retail sale price (MRP)",
                "Date of manufacture or packing",
                "Consumer care contact details",
                "Category-specific mandatory declarations",
              ].map((item) => (
                <li key={item} className="flex items-start gap-2.5 text-sm text-brand-dark">
                  <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-brand-success" aria-hidden="true" />
                  {item}
                </li>
              ))}
            </ul>
            <div className="mt-6 border-t border-brand-border pt-5">
              <Pipeline activeStep={0} />
            </div>
          </div>
        </aside>
      </div>
    </div>
  );
}

/* -------------------------------- analyzing -------------------------------- */

function AnalyzingView({ fileName, step }: { fileName: string | null; step: number }) {
  return (
    <div className="mx-auto flex min-h-[70vh] max-w-xl animate-fade-up flex-col justify-center px-4 py-16 sm:px-6">
      <div className={cx(card, "p-8 sm:p-10")}>
        <div className="mb-2 h-1 w-full overflow-hidden rounded-full bg-brand-light">
          <div
            className="h-full rounded-full bg-brand-green transition-all duration-700 ease-out"
            style={{ width: `${Math.min((step / ANALYSIS_STEPS.length) * 100, 100)}%` }}
          />
        </div>

        <h1 className="mt-6 text-2xl font-light tracking-tight text-brand-dark sm:text-3xl">
          Analyzing Product Label
        </h1>
        <p className="mt-2 text-sm text-brand-muted">
          {fileName ? (
            <>
              Inspection in progress for <span className="font-medium text-brand-dark">{fileName}</span>
            </>
          ) : (
            "Inspection in progress"
          )}
        </p>

        <ol className="mt-8 space-y-4" aria-live="polite" aria-label="Analysis progress">
          {ANALYSIS_STEPS.map((label, i) => {
            const done = i < step;
            const active = i === step;
            return (
              <li key={label} className="flex items-center gap-3">
                {done && <CheckCircle2 className="h-5 w-5 shrink-0 text-brand-success" aria-hidden="true" />}
                {active && <Loader2 className="h-5 w-5 shrink-0 animate-spin text-brand-green" aria-hidden="true" />}
                {!done && !active && (
                  <span className="flex h-5 w-5 shrink-0 items-center justify-center" aria-hidden="true">
                    <span className="h-2.5 w-2.5 rounded-full border-2 border-brand-border" />
                  </span>
                )}
                <span
                  className={cx(
                    "text-sm",
                    done && "text-brand-dark",
                    active && "font-medium text-brand-dark",
                    !done && !active && "text-brand-muted",
                  )}
                >
                  {label}
                </span>
                {done && <span className="ml-auto text-[11px] font-medium text-brand-muted">Done</span>}
              </li>
            );
          })}
        </ol>

        <div className="mt-8 flex items-start gap-3 rounded-xl border border-brand-border bg-brand-light/60 p-4">
          <CircleHelp className="mt-0.5 h-4 w-4 shrink-0 text-brand-green" aria-hidden="true" />
          <p className="text-xs leading-relaxed text-brand-muted">
            <span className="font-semibold text-brand-dark">AI-assisted assessment.</span> Preliminary results
            require officer verification before any regulatory conclusion.
          </p>
        </div>
      </div>
    </div>
  );
}

/* --------------------------------- results --------------------------------- */

function EvidenceBox({
  target,
  active,
  tone,
  label,
  alwaysVisible = false,
  className,
}: {
  target: string;
  active: boolean;
  tone: StatusTone;
  label: string;
  alwaysVisible?: boolean;
  className: string;
}) {
  if (!active && !alwaysVisible) return null;
  const toneClasses: Record<StatusTone, string> = {
    compliant: "border-brand-success/50",
    review: "border-brand-warning/60",
    violation: "border-brand-danger/60",
  };
  const chipClasses: Record<StatusTone, string> = {
    compliant: "bg-brand-success/10 text-brand-success",
    review: "bg-brand-warning/10 text-brand-warning",
    violation: "bg-brand-danger/10 text-brand-danger",
  };
  return (
    <div
      data-testid={`evidence-${target}`}
      className={cx(
        "pointer-events-none absolute rounded-md border-2 border-dashed transition-all duration-300",
        toneClasses[tone],
        active && "ring-2 ring-brand-green/40 ring-offset-2 ring-offset-white",
        className,
      )}
    >
      <span
        className={cx(
          "absolute -top-2.5 left-2 rounded px-1.5 py-0.5 text-[9px] font-semibold tracking-[0.12em] uppercase",
          chipClasses[tone],
        )}
      >
        {label}
      </span>
    </div>
  );
}

function ResultsView({
  inspectionId,
  onNavigate,
  onNewInspection,
}: {
  inspectionId: string;
  onNavigate: (view: View) => void;
  onNewInspection: () => void;
}) {
  const [evidenceTarget, setEvidenceTarget] = useState<string | null>(null);
  const timerRef = useRef<number | null>(null);

  useEffect(() => {
    return () => {
      if (timerRef.current) window.clearTimeout(timerRef.current);
    };
  }, []);

  const showEvidence = useCallback((target: string) => {
    setEvidenceTarget(target);
    document.getElementById("label-viewer")?.scrollIntoView({ behavior: "smooth", block: "center" });
    if (timerRef.current) window.clearTimeout(timerRef.current);
    timerRef.current = window.setTimeout(() => setEvidenceTarget(null), 3200);
  }, []);

  return (
    <div className="mx-auto max-w-7xl animate-fade-up px-4 pb-20 sm:px-6 lg:px-8">
      <div className="pt-8 sm:pt-12">
        <BackButton onClick={() => onNavigate("dashboard")} />

        {/* Header card */}
        <section id="inspection-results" className={cx(card, "p-6 sm:p-8 lg:p-10")} aria-labelledby="results-heading">
          <div className="flex flex-col gap-10 lg:flex-row lg:items-center lg:justify-between">
            <div className="min-w-0 flex-1">
              <p className="text-[11px] font-semibold tracking-[0.24em] text-brand-green uppercase">
                Inspection Results
              </p>
              <h1 id="results-heading" className="mt-3 text-2xl font-light tracking-tight text-brand-dark sm:text-3xl">
                {DEMO_PRODUCT.name}
              </h1>
              <p className="mt-1 text-sm text-brand-muted">Packaged Commodity · {DEMO_PRODUCT.manufacturer}</p>

              <dl className="mt-8 grid grid-cols-1 gap-x-8 gap-y-5 sm:grid-cols-3">
                <div>
                  <dt className="text-[11px] font-semibold tracking-[0.14em] text-brand-muted uppercase">
                    Inspection ID
                  </dt>
                  <dd className="mt-1 text-sm font-medium text-brand-dark">{inspectionId}</dd>
                </div>
                <div>
                  <dt className="text-[11px] font-semibold tracking-[0.14em] text-brand-muted uppercase">
                    Inspection Date
                  </dt>
                  <dd className="mt-1 text-sm font-medium text-brand-dark">
                    {formatDisplayDate(DEMO_INSPECTION.date)}
                  </dd>
                </div>
                <div>
                  <dt className="text-[11px] font-semibold tracking-[0.14em] text-brand-muted uppercase">
                    Overall Status
                  </dt>
                  <dd className="mt-1.5">
                    <StatusBadge status={DEMO_INSPECTION.status} />
                  </dd>
                </div>
              </dl>

              <div className="mt-8 flex items-start gap-3 rounded-xl border border-brand-border bg-brand-light/60 p-4">
                <CircleHelp className="mt-0.5 h-4 w-4 shrink-0 text-brand-green" aria-hidden="true" />
                <p className="text-xs leading-relaxed text-brand-muted">
                  <span className="font-semibold text-brand-dark">AI-assisted assessment.</span> This result is
                  decision support only and requires officer verification before any regulatory conclusion.
                </p>
              </div>
            </div>

            <div className="flex shrink-0 flex-col items-center gap-6 lg:pl-10">
              <ScoreRing score={DEMO_INSPECTION.score} />
              <ul className="w-full space-y-2 text-sm">
                {[
                  { dot: "bg-brand-dark", text: "14 requirements checked" },
                  { dot: "bg-brand-success", text: "11 compliant" },
                  { dot: "bg-brand-warning", text: "2 require review" },
                  { dot: "bg-brand-danger", text: "1 violation detected" },
                ].map((row) => (
                  <li key={row.text} className="flex items-center gap-2.5 text-brand-muted">
                    <span className={cx("h-2 w-2 rounded-full", row.dot)} aria-hidden="true" />
                    {row.text}
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </section>
      </div>

      {/* Checklist + findings */}
      <div className="mt-6 grid gap-6 lg:grid-cols-5">
        <section className="lg:col-span-3" aria-labelledby="checklist-heading">
          <div className={cx(card, "p-6 sm:p-8")}>
            <h2 id="checklist-heading" className="text-xl font-light tracking-tight text-brand-dark">
              Compliance Assessment
            </h2>
            <p className="mt-1.5 text-sm text-brand-muted">
              Requirements evaluated against Legal Metrology / Packaged Commodities requirements.
            </p>

            <ul className="mt-6 divide-y divide-brand-border">
              {CHECKLIST.map((item) => {
                const meta = STATUS_META[item.status];
                const Icon = meta.icon;
                return (
                  <li key={item.id} className="flex items-start gap-4 py-4 first:pt-0 last:pb-0">
                    <Icon className={cx("mt-0.5 h-5 w-5 shrink-0", meta.text)} aria-hidden="true" />
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <h3 className="text-sm font-semibold text-brand-dark">{item.requirement}</h3>
                        <StatusBadge status={item.status} variant="checklist" />
                      </div>
                      <p className="mt-1 text-sm leading-relaxed text-brand-muted">{item.detail}</p>
                    </div>
                    {item.evidence && (
                      <button
                        type="button"
                        onClick={() => showEvidence(item.evidence as string)}
                        className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-brand-border bg-white text-brand-muted transition-colors hover:text-brand-dark"
                        aria-label={`View label evidence for ${item.requirement}`}
                        title="View label evidence"
                      >
                        <Eye className="h-4 w-4" aria-hidden="true" />
                      </button>
                    )}
                  </li>
                );
              })}
            </ul>

            <p className="mt-6 border-t border-brand-border pt-4 text-xs leading-relaxed text-brand-muted">
              The checklist shows grouped requirement categories — 14 individual requirements were evaluated in this
              inspection.
            </p>
          </div>
        </section>

        <section className="lg:col-span-2" aria-labelledby="findings-heading">
          <div className="space-y-4">
            <div className="px-1">
              <h2 id="findings-heading" className="text-xl font-light tracking-tight text-brand-dark">
                Evidence &amp; Findings
              </h2>
              <p className="mt-1.5 text-sm text-brand-muted">
                Explainable findings with confidence levels and supporting evidence.
              </p>
            </div>

            {FINDINGS.map((finding) => {
              const meta = STATUS_META[finding.status];
              return (
                <article key={finding.id} className={cx(card, "p-6")}>
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <h3 className="text-sm font-semibold text-brand-dark">{finding.requirement}</h3>
                    <StatusBadge status={finding.status} />
                  </div>

                  <p className="mt-3 text-sm leading-relaxed text-brand-muted">{finding.findingText}</p>

                  <dl className="mt-5 space-y-4 border-t border-brand-border pt-5 text-sm">
                    <div>
                      <dt className="text-[11px] font-semibold tracking-[0.14em] text-brand-muted uppercase">
                        What Was Checked
                      </dt>
                      <dd className="mt-1 leading-relaxed text-brand-dark">{finding.checked}</dd>
                    </div>
                    <div>
                      <dt className="text-[11px] font-semibold tracking-[0.14em] text-brand-muted uppercase">
                        Confidence
                      </dt>
                      <dd className="mt-1.5 flex items-center gap-3">
                        <span className={cx("text-sm font-semibold", meta.text)}>{finding.confidence}%</span>
                        <span className="h-1.5 w-24 overflow-hidden rounded-full bg-brand-light">
                          <span
                            className={cx(
                              "block h-full rounded-full",
                              finding.status === "compliant" && "bg-brand-success",
                              finding.status === "review" && "bg-brand-warning",
                              finding.status === "violation" && "bg-brand-danger",
                            )}
                            style={{ width: `${finding.confidence}%` }}
                          />
                        </span>
                      </dd>
                    </div>
                    <div>
                      <dt className="text-[11px] font-semibold tracking-[0.14em] text-brand-muted uppercase">
                        Verification
                      </dt>
                      <dd className="mt-1 flex items-center gap-2 text-brand-dark">
                        <ClipboardCheck className="h-4 w-4 shrink-0 text-brand-green" aria-hidden="true" />
                        Officer verification required
                      </dd>
                    </div>
                  </dl>

                  <button type="button" onClick={() => showEvidence(finding.evidence)} className={cx(btnSecondary, "mt-5 w-full")}>
                    <Eye className="h-4 w-4" aria-hidden="true" />
                    View Label Evidence
                  </button>
                </article>
              );
            })}

            <div className="flex items-start gap-3 rounded-xl border border-brand-border bg-brand-light/60 p-4">
              <CircleHelp className="mt-0.5 h-4 w-4 shrink-0 text-brand-green" aria-hidden="true" />
              <p className="text-xs leading-relaxed text-brand-muted">
                Findings above are preliminary AI outputs. An authorized officer must review the evidence and confirm
                each finding before any regulatory conclusion is drawn.
              </p>
            </div>
          </div>
        </section>
      </div>

      {/* Label viewer + detected fields */}
      <div id="label-viewer" className="mt-6 grid scroll-mt-24 gap-6 lg:grid-cols-2">
        <section aria-labelledby="label-heading">
          <div className={cx(card, "p-6 sm:p-8")}>
            <div className="mb-6 flex items-center justify-between">
              <h2 id="label-heading" className="text-lg font-medium text-brand-dark">
                Submitted Label
              </h2>
              <span className="rounded-full border border-brand-border bg-brand-light px-2.5 py-1 text-[10px] font-semibold tracking-[0.14em] text-brand-muted uppercase">
                Demo Label
              </span>
            </div>

            <div className="relative overflow-hidden rounded-xl border border-brand-border bg-white p-5 sm:p-7">
              {/* Mock printed label */}
              <div className="flex min-h-[380px] flex-col">
                <div className="flex items-start justify-between">
                  <div className="relative">
                    <p className="text-[10px] font-semibold tracking-[0.3em] text-brand-muted uppercase">
                      GoldenFields Foods
                    </p>
                    <p className="mt-2 text-xl font-semibold tracking-tight text-brand-dark sm:text-2xl">
                      Premium Wheat Flour
                    </p>
                    <p className="mt-1 text-xs text-brand-muted">Whole Wheat Atta · Packed in India</p>
                    <EvidenceBox
                      target="product-name"
                      active={evidenceTarget === "product-name"}
                      tone="compliant"
                      label="Product Name"
                      className="top-[-6px] left-[-8px] h-[72px] w-[62%]"
                    />
                  </div>
                  <div className="relative w-[40%] max-w-45">
                    <p className="text-[9px] font-semibold tracking-[0.2em] text-brand-muted uppercase">
                      Declarations
                    </p>
                    <div className="mt-2 space-y-1.5">
                      {[100, 86, 94, 70, 90, 58].map((w, i) => (
                        <div key={i} className="h-1.5 rounded bg-brand-light" style={{ width: `${w}%` }} />
                      ))}
                    </div>
                    <EvidenceBox
                      target="declaration"
                      active={evidenceTarget === "declaration"}
                      tone="violation"
                      label="Not Identified"
                      alwaysVisible
                      className="top-[-8px] right-[-10px] h-[86%] w-[110%]"
                    />
                  </div>
                </div>

                <div className="mt-auto space-y-5 pt-8">
                  <div className="relative">
                    <p className="text-xs text-brand-muted">
                      Mfd. &amp; Pkd. by <span className="font-medium text-brand-dark">ABC Foods Pvt. Ltd.</span>, Plot
                      42, Industrial Area Phase II, Sector 82 — 201305
                    </p>
                    <EvidenceBox
                      target="manufacturer"
                      active={evidenceTarget === "manufacturer"}
                      tone="compliant"
                      label="Manufacturer"
                      className="top-[-8px] left-[-8px] h-[36px] w-[96%]"
                    />
                  </div>
                  <div className="flex flex-wrap items-end justify-between gap-4">
                    <div className="relative">
                      <p className="text-[10px] font-semibold tracking-[0.14em] text-brand-muted uppercase">
                        MRP
                      </p>
                      <p className="mt-1 text-lg font-semibold text-brand-dark opacity-60">₹ 68.00</p>
                      <p className="text-[10px] text-brand-muted">(incl. of all taxes)</p>
                      <EvidenceBox
                        target="mrp"
                        active={evidenceTarget === "mrp"}
                        tone="review"
                        label="Low Legibility"
                        alwaysVisible
                        className="top-[-6px] left-[-8px] h-[64px] w-[130%]"
                      />
                    </div>
                    <div className="relative">
                      <p className="text-[10px] font-semibold tracking-[0.14em] text-brand-muted uppercase">
                        Customer Care
                      </p>
                      <p className="mt-1 text-sm font-medium text-brand-dark">1800-XXX-XXXX</p>
                      <EvidenceBox
                        target="consumer-care"
                        active={evidenceTarget === "consumer-care"}
                        tone="review"
                        label="Partial"
                        alwaysVisible
                        className="top-[-6px] right-[-8px] h-[52px] w-[110%]"
                      />
                    </div>
                  </div>
                  <div className="relative flex items-center justify-between border-t border-brand-border pt-4">
                    <p className="text-xs text-brand-muted">
                      Net Qty. <span className="font-semibold text-brand-dark">1 kg</span>
                    </p>
                    <p className="text-xs text-brand-muted">
                      PKD: <span className="font-semibold text-brand-dark">08/2026</span>
                    </p>
                    <EvidenceBox
                      target="net-qty"
                      active={evidenceTarget === "net-qty"}
                      tone="compliant"
                      label="Net Qty"
                      className="top-[-8px] left-[-8px] h-[26px] w-[64px]"
                    />
                    <EvidenceBox
                      target="date"
                      active={evidenceTarget === "date"}
                      tone="compliant"
                      label="Packing Date"
                      className="top-[-8px] right-[-8px] h-[26px] w-[86px]"
                    />
                  </div>
                </div>
              </div>
            </div>

            <div className="mt-4 flex flex-wrap items-center gap-x-5 gap-y-2">
              <span className="flex items-center gap-1.5 text-xs text-brand-muted">
                <span className="h-2 w-2 rounded-full border border-dashed border-brand-success" aria-hidden="true" />
                Extracted region
              </span>
              <span className="flex items-center gap-1.5 text-xs text-brand-muted">
                <span className="h-2 w-2 rounded-full border border-dashed border-brand-warning" aria-hidden="true" />
                Needs review
              </span>
              <span className="flex items-center gap-1.5 text-xs text-brand-muted">
                <span className="h-2 w-2 rounded-full border border-dashed border-brand-danger" aria-hidden="true" />
                Not identified
              </span>
            </div>
            <DemoNote className="mt-2" />
          </div>
        </section>

        <section aria-labelledby="detected-heading">
          <div className={cx(card, "p-6 sm:p-8")}>
            <h2 id="detected-heading" className="text-lg font-medium text-brand-dark">
              Detected Information
            </h2>
            <p className="mt-1.5 text-sm text-brand-muted">
              Fields extracted by the AI pipeline, with extraction confidence.
            </p>

            <dl className="mt-6 divide-y divide-brand-border">
              {[
                { label: "Product Name", value: DEMO_PRODUCT.name, confidence: 96, evidence: "product-name" },
                { label: "Net Quantity", value: DEMO_PRODUCT.netQuantity, confidence: 97, evidence: "net-qty" },
                { label: "MRP", value: DEMO_PRODUCT.mrp, confidence: 78, evidence: "mrp" },
                { label: "Manufacturer", value: DEMO_PRODUCT.manufacturer, confidence: 94, evidence: "manufacturer" },
                { label: "Customer Care", value: DEMO_PRODUCT.customerCare, confidence: 74, evidence: "consumer-care" },
              ].map((field) => (
                <div
                  key={field.label}
                  className={cx(
                    "flex items-center justify-between gap-4 py-4 transition-colors first:pt-0 last:pb-0",
                    evidenceTarget === field.evidence && "rounded-lg bg-brand-light px-3",
                  )}
                >
                  <div>
                    <dt className="text-[11px] font-semibold tracking-[0.14em] text-brand-muted uppercase">
                      {field.label}
                    </dt>
                    <dd className="mt-1 text-sm font-medium text-brand-dark">{field.value}</dd>
                  </div>
                  <button
                    type="button"
                    onClick={() => showEvidence(field.evidence)}
                    className={cx(
                      "shrink-0 text-xs font-medium transition-colors",
                      field.confidence < 80
                        ? "text-brand-warning"
                        : "text-brand-success",
                    )}
                    aria-label={`${field.label}: ${field.value}. Confidence ${field.confidence} percent. View label evidence.`}
                  >
                    {field.confidence}%
                  </button>
                </div>
              ))}
            </dl>

            <p className="mt-6 flex items-start gap-2.5 rounded-xl border border-brand-border bg-brand-light/60 p-4 text-xs leading-relaxed text-brand-muted">
              <CircleHelp className="mt-0.5 h-4 w-4 shrink-0 text-brand-green" aria-hidden="true" />
              <span>
                <span className="font-semibold text-brand-dark">Officer note:</span> fields below 80% confidence
                should be confirmed against the physical package before finalizing the report.
              </span>
            </p>
          </div>
        </section>
      </div>

      {/* Officer verification + actions */}
      <section className="mt-6" aria-labelledby="verification-heading">
        <div className="rounded-2xl border border-brand-warning/30 bg-brand-warning/5 p-6">
          <div className="flex flex-col gap-5 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex items-start gap-4">
              <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl border border-brand-warning/30 bg-brand-white">
                <ClipboardCheck className="h-5 w-5 text-brand-warning" aria-hidden="true" />
              </span>
              <div>
                <h2 id="verification-heading" className="text-sm font-semibold text-brand-dark">
                  Officer verification required
                </h2>
                <p className="mt-1 max-w-xl text-sm leading-relaxed text-brand-muted">
                  2 review items and 1 violation need confirmation by an authorized officer before regulatory action
                  or report finalization.
                </p>
              </div>
            </div>
            <div className="flex flex-col gap-3 sm:flex-row sm:shrink-0">
              <button type="button" onClick={() => onNavigate("reports")} className={btnPrimary}>
                <FileCheck className="h-4 w-4" aria-hidden="true" />
                Generate Report
              </button>
              <button type="button" onClick={() => onNavigate("history")} className={btnSecondary}>
                <History className="h-4 w-4" aria-hidden="true" />
                View History
              </button>
              <button type="button" onClick={onNewInspection} className={btnGhost}>
                New Inspection
              </button>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}

/* --------------------------------- reports --------------------------------- */

function ReportsView({ rows }: { rows: InspectionRecord[] }) {
  const sorted = useMemo(
    () => [...rows].sort((a, b) => b.date.localeCompare(a.date) || b.id.localeCompare(a.id)),
    [rows],
  );

  return (
    <div className="mx-auto max-w-7xl animate-fade-up px-4 pb-20 sm:px-6 lg:px-8">
      <div className="pt-8 sm:pt-12">
        <SectionHeader
          eyebrow="Reports"
          title="Compliance Reports"
          text="Completed inspection reports with status, score and assigned inspector."
        />

        <div className={cx(card, "overflow-hidden")}>
          {/* Desktop table */}
          <div className="hidden overflow-x-auto md:block">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-brand-light/60 text-left text-[11px] font-semibold tracking-[0.14em] text-brand-muted uppercase">
                  <th scope="col" className="px-6 py-4">Inspection ID</th>
                  <th scope="col" className="px-6 py-4">Product</th>
                  <th scope="col" className="px-6 py-4">Date</th>
                  <th scope="col" className="px-6 py-4">Score</th>
                  <th scope="col" className="px-6 py-4">Status</th>
                  <th scope="col" className="px-6 py-4">Inspector</th>
                  <th scope="col" className="px-6 py-4 text-right">Report</th>
                </tr>
              </thead>
              <tbody>
                {sorted.map((row) => (
                  <tr key={row.id} className="border-t border-brand-border transition-colors hover:bg-brand-cream/70">
                    <td className="px-6 py-4 font-medium whitespace-nowrap text-brand-dark">{row.id}</td>
                    <td className="px-6 py-4 text-brand-dark">{row.product}</td>
                    <td className="px-6 py-4 whitespace-nowrap text-brand-muted">{formatDisplayDate(row.date)}</td>
                    <td className={cx("px-6 py-4 font-semibold", STATUS_META[row.status].text)}>{row.score}</td>
                    <td className="px-6 py-4">
                      <StatusBadge status={row.status} />
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-brand-muted">{row.inspector}</td>
                    <td className="px-6 py-4">
                      <div className="flex items-center justify-end gap-2">
                        <button type="button" className={btnTable} title="Open report (demo)">
                          <Eye className="h-3.5 w-3.5" aria-hidden="true" />
                          View Report
                        </button>
                        <button type="button" className={btnTable} title="Export as PDF (demo)" aria-label={`Export report ${row.id} as PDF`}>
                          <Download className="h-3.5 w-3.5" aria-hidden="true" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Mobile cards */}
          <ul className="divide-y divide-brand-border md:hidden">
            {sorted.map((row) => (
              <li key={row.id} className="p-4">
                <div className="flex items-center justify-between gap-3">
                  <span className="text-sm font-medium text-brand-dark">{row.id}</span>
                  <StatusBadge status={row.status} />
                </div>
                <p className="mt-2 text-base font-medium text-brand-dark">{row.product}</p>
                <dl className="mt-3 grid grid-cols-3 gap-2 text-xs">
                  <div>
                    <dt className="text-brand-muted">Date</dt>
                    <dd className="mt-0.5 font-medium text-brand-dark">{formatDisplayDate(row.date)}</dd>
                  </div>
                  <div>
                    <dt className="text-brand-muted">Score</dt>
                    <dd className={cx("mt-0.5 font-semibold", STATUS_META[row.status].text)}>{row.score}</dd>
                  </div>
                  <div>
                    <dt className="text-brand-muted">Inspector</dt>
                    <dd className="mt-0.5 font-medium text-brand-dark">{row.inspector}</dd>
                  </div>
                </dl>
                <div className="mt-4 flex gap-2">
                  <button type="button" className={cx(btnTable, "flex-1 justify-center py-2")}>
                    <Eye className="h-3.5 w-3.5" aria-hidden="true" />
                    View Report
                  </button>
                  <button type="button" className={cx(btnTable, "justify-center py-2")} aria-label={`Export report ${row.id} as PDF`}>
                    <Download className="h-3.5 w-3.5" aria-hidden="true" />
                    Export PDF
                  </button>
                </div>
              </li>
            ))}
          </ul>
        </div>

        <DemoNote className="mt-3" />
        <p className="mt-2 text-xs text-brand-muted">
          Report actions are placeholders in this demonstration build.
        </p>
      </div>
    </div>
  );
}

/* --------------------------------- history --------------------------------- */

function HistoryView({
  rows,
  onNavigate,
}: {
  rows: InspectionRecord[];
  onNavigate: (view: View) => void;
}) {
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [sortKey, setSortKey] = useState<SortKey>("newest");

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    let out = rows.filter((row) => {
      const matchesQuery =
        q === "" ||
        row.id.toLowerCase().includes(q) ||
        row.product.toLowerCase().includes(q) ||
        row.manufacturer.toLowerCase().includes(q);
      const matchesStatus = statusFilter === "all" || row.status === statusFilter;
      return matchesQuery && matchesStatus;
    });
    out = [...out].sort((a, b) => {
      switch (sortKey) {
        case "oldest":
          return a.date.localeCompare(b.date) || a.id.localeCompare(b.id);
        case "score-desc":
          return b.score - a.score;
        case "score-asc":
          return a.score - b.score;
        default:
          return b.date.localeCompare(a.date) || b.id.localeCompare(a.id);
      }
    });
    return out;
  }, [rows, query, statusFilter, sortKey]);

  const hasFilters = query.trim() !== "" || statusFilter !== "all";

  const clearFilters = () => {
    setQuery("");
    setStatusFilter("all");
    setSortKey("newest");
  };

  return (
    <div className="mx-auto max-w-7xl animate-fade-up px-4 pb-20 sm:px-6 lg:px-8">
      <div className="pt-8 sm:pt-12">
        <SectionHeader
          eyebrow="History"
          title="Inspection History"
          text="All past inspections with compliance scores and outcomes."
        />

        {/* Controls */}
        <div className="mb-5 flex flex-col gap-3 md:flex-row md:items-center">
          <div className="relative flex-1">
            <Search
              className="pointer-events-none absolute top-1/2 left-3.5 h-4 w-4 -translate-y-1/2 text-brand-muted"
              aria-hidden="true"
            />
            <input
              type="search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search inspections"
              aria-label="Search inspections"
              className={cx(inputBase, "pl-10")}
            />
          </div>
          <div className="flex gap-3">
            <div className="relative flex-1 md:w-44">
              <select
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value as StatusFilter)}
                aria-label="Filter by status"
                className={cx(inputBase, "appearance-none pr-9")}
              >
                <option value="all">All Statuses</option>
                <option value="compliant">Compliant</option>
                <option value="review">Needs Review</option>
                <option value="violation">Violation Detected</option>
              </select>
              <ChevronDown
                className="pointer-events-none absolute top-1/2 right-3 h-4 w-4 -translate-y-1/2 text-brand-muted"
                aria-hidden="true"
              />
            </div>
            <div className="relative flex-1 md:w-48">
              <select
                value={sortKey}
                onChange={(e) => setSortKey(e.target.value as SortKey)}
                aria-label="Sort inspections"
                className={cx(inputBase, "appearance-none pr-9")}
              >
                <option value="newest">Newest first</option>
                <option value="oldest">Oldest first</option>
                <option value="score-desc">Score: high to low</option>
                <option value="score-asc">Score: low to high</option>
              </select>
              <ChevronDown
                className="pointer-events-none absolute top-1/2 right-3 h-4 w-4 -translate-y-1/2 text-brand-muted"
                aria-hidden="true"
              />
            </div>
          </div>
        </div>

        {filtered.length === 0 ? (
          hasFilters ? (
            <EmptyState
              icon={Search}
              title="No matching inspections"
              text="Try adjusting your search or status filters to find previous inspections."
              actionLabel="Clear Filters"
              onAction={clearFilters}
            />
          ) : (
            <EmptyState
              icon={ClipboardCheck}
              title="No inspections yet"
              text="Start your first product inspection to begin building your compliance history."
              actionLabel="Start Inspection"
              onAction={() => onNavigate("inspect")}
            />
          )
        ) : (
          <div className={cx(card, "overflow-hidden")}>
            {/* Desktop table */}
            <div className="hidden overflow-x-auto md:block">
              <table className="w-full text-sm">
                <caption className="sr-only">Inspection history</caption>
                <thead>
                  <tr className="bg-brand-light/60 text-left text-[11px] font-semibold tracking-[0.14em] text-brand-muted uppercase">
                    <th scope="col" className="px-6 py-4">Inspection ID</th>
                    <th scope="col" className="px-6 py-4">Product</th>
                    <th scope="col" className="px-6 py-4">Inspection Date</th>
                    <th scope="col" className="px-6 py-4">Compliance Score</th>
                    <th scope="col" className="px-6 py-4">Status</th>
                    <th scope="col" className="px-6 py-4 text-right">Action</th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((row) => (
                    <tr key={row.id} className="border-t border-brand-border transition-colors hover:bg-brand-cream/70">
                      <td className="px-6 py-4 font-medium whitespace-nowrap text-brand-dark">{row.id}</td>
                      <td className="px-6 py-4 text-brand-dark">{row.product}</td>
                      <td className="px-6 py-4 whitespace-nowrap text-brand-muted">{formatDisplayDate(row.date)}</td>
                      <td className={cx("px-6 py-4 font-semibold", STATUS_META[row.status].text)}>
                        {row.score}
                        <span className="text-xs font-normal text-brand-muted"> / 100</span>
                      </td>
                      <td className="px-6 py-4">
                        <StatusBadge status={row.status} />
                      </td>
                      <td className="px-6 py-4 text-right">
                        <button type="button" className={btnTable} onClick={() => onNavigate("results")}>
                          <Eye className="h-3.5 w-3.5" aria-hidden="true" />
                          View
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Mobile cards */}
            <ul className="divide-y divide-brand-border md:hidden">
              {filtered.map((row) => (
                <li key={row.id} className="p-4">
                  <div className="flex items-center justify-between gap-3">
                    <span className="text-sm font-medium text-brand-dark">{row.id}</span>
                    <StatusBadge status={row.status} />
                  </div>
                  <p className="mt-2 text-base font-medium text-brand-dark">{row.product}</p>
                  <div className="mt-3 flex items-center justify-between text-xs">
                    <span className="text-brand-muted">{formatDisplayDate(row.date)}</span>
                    <span className={cx("font-semibold", STATUS_META[row.status].text)}>
                      {row.score} / 100
                    </span>
                  </div>
                  <button type="button" onClick={() => onNavigate("results")} className={cx(btnTable, "mt-4 w-full justify-center py-2")}>
                    <Eye className="h-3.5 w-3.5" aria-hidden="true" />
                    View Inspection
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}

        <DemoNote className="mt-3" />
      </div>
    </div>
  );
}

/* ---------------------------------- footer --------------------------------- */

function Footer() {
  return (
    <footer className="border-t border-brand-border bg-brand-white">
      <div className="mx-auto flex max-w-7xl flex-col items-start justify-between gap-3 px-4 py-8 sm:flex-row sm:items-center sm:px-6 lg:px-8">
        <div className="flex items-center gap-3">
          <img src="/favicon.png" alt="" className="h-8 w-8 shrink-0 object-contain" width={32} height={32} />
          <p className="text-xs leading-relaxed text-brand-muted">
            <span className="font-medium text-brand-dark">{APP_NAME}</span> — Analyze. Verify. Comply.
            Demonstration interface: AI-assisted assessment; officer verification required for regulatory
            decisions.
          </p>
        </div>
      </div>
    </footer>
  );
}

/* ----------------------------------- app ----------------------------------- */

function formatInspectionId(num: number) {
  return `LGA-2026-${String(num).padStart(5, "0")}`;
}

export default function App() {
  const [view, setView] = useState<View>("dashboard");
  const [navOpen, setNavOpen] = useState(false);
  const [scrolled, setScrolled] = useState(false);
  const [upload, setUpload] = useState<UploadInfo | null>(null);
  const [analysisStep, setAnalysisStep] = useState(0);
  const [inspections, setInspections] = useState<InspectionRecord[]>(INSPECTIONS_SEED);
  const [activeInspectionId, setActiveInspectionId] = useState<string | null>(null);

  const navigate = useCallback((next: View) => {
    setView(next);
    setNavOpen(false);
    window.scrollTo({ top: 0, behavior: "instant" as ScrollBehavior });
  }, []);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 8);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  const handleFile = useCallback((file: File) => {
    setUpload({ name: file.name, size: file.size });
  }, []);

  const handleSample = useCallback(() => {
    setUpload({ name: "premium-wheat-flour-label.png", size: 2_411_520 });
  }, []);

  const handleClearUpload = useCallback(() => setUpload(null), []);

  const handleRun = useCallback(() => {
    setAnalysisStep(0);
    navigate("analyzing");
  }, [navigate]);

  const handleNewInspection = useCallback(() => {
    setUpload(null);
    navigate("inspect");
  }, [navigate]);

  const completeInspection = useCallback(() => {
    // Allocate the next ID from the records themselves — no duplicate IDs possible.
    const maxNum = Math.max(124, ...inspections.map((r) => Number.parseInt(r.id.slice(-5), 10)));
    const id = formatInspectionId(maxNum + 1);
    setInspections((rows) => [
      {
        id,
        product: DEMO_PRODUCT.name,
        manufacturer: DEMO_PRODUCT.manufacturer,
        inspector: "Officer A. Sharma",
        date: DEMO_INSPECTION.date,
        score: DEMO_INSPECTION.score,
        status: DEMO_INSPECTION.status,
      },
      ...rows,
    ]);
    setActiveInspectionId(id);
    navigate("results");
  }, [inspections, navigate]);

  // AI analysis pipeline simulation
  useEffect(() => {
    if (view !== "analyzing") return;
    if (analysisStep >= ANALYSIS_STEPS.length) {
      const t = window.setTimeout(completeInspection, 500);
      return () => window.clearTimeout(t);
    }
    const t = window.setTimeout(() => setAnalysisStep((s) => s + 1), STEP_DURATIONS[analysisStep]);
    return () => window.clearTimeout(t);
  }, [view, analysisStep, completeInspection]);

  return (
    <div className="flex min-h-screen flex-col bg-brand-cream text-brand-dark">
      <Navbar
        view={view}
        navOpen={navOpen}
        onNavOpenChange={setNavOpen}
        onNavigate={navigate}
        scrolled={scrolled}
      />

      <main className="flex-1">
        {view === "dashboard" && (
          <DashboardView
            upload={upload}
            onFile={handleFile}
            onRun={handleRun}
            onClear={handleClearUpload}
            onNavigate={navigate}
          />
        )}
        {view === "inspect" && (
          <InspectView
            upload={upload}
            onFile={handleFile}
            onRun={handleRun}
            onClear={handleClearUpload}
            onSample={handleSample}
            onNavigate={navigate}
          />
        )}
        {view === "analyzing" && <AnalyzingView fileName={upload?.name ?? null} step={analysisStep} />}
        {view === "results" && (
          <ResultsView
            inspectionId={activeInspectionId ?? "LGA-2026-00124"}
            onNavigate={navigate}
            onNewInspection={handleNewInspection}
          />
        )}
        {view === "reports" && <ReportsView rows={inspections} />}
        {view === "history" && <HistoryView rows={inspections} onNavigate={navigate} />}
      </main>

      <Footer />
    </div>
  );
}
