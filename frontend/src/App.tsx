/**
 * LabelGuard AI application shell.
 *
 * Views are wired to real backend flows only: dashboard (DB-backed metrics +
 * upload), inspect (upload), the OCR result/assessment view, and the
 * database-backed History and Reports pages. There is no mock inspection
 * data anywhere — every displayed record comes from PostgreSQL via the API.
 */
import { useCallback, useEffect, useState } from "react";
import {
  ArrowLeft,
  ArrowRight,
  CheckCircle2,
  FileCheck,
  FileText,
  History as HistoryIcon,
  LayoutDashboard,
  Menu,
  ScanLine,
  X,
  type LucideIcon,
} from "lucide-react";

import UploadFlow from "./components/UploadFlow";
import OcrResultView from "./components/OcrResultView";
import {
  DashboardMetricsCards,
  InspectionHistoryView,
  ReportsView as ReportsDataView,
} from "./components/DataViews";
import type { UploadSuccess } from "./types/api";

/* ---------------------------------- types --------------------------------- */

type View = "dashboard" | "inspect" | "ocr-result" | "reports" | "history";

const APP_NAME = "LabelGuard AI";

/* --------------------------------- helpers -------------------------------- */

function cx(...parts: Array<string | false | null | undefined>) {
  return parts.filter(Boolean).join(" ");
}

/* --------------------------------- navbar --------------------------------- */

const NAV_LINKS: { id: View; label: string; icon: LucideIcon }[] = [
  { id: "dashboard", label: "Dashboard", icon: LayoutDashboard },
  { id: "inspect", label: "Inspect Product", icon: ScanLine },
  { id: "reports", label: "Reports", icon: FileText },
  { id: "history", label: "History", icon: HistoryIcon },
];

function activeNavId(view: View): View {
  if (view === "ocr-result") return "inspect";
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
          scrolled ? "border-brand-border bg-brand-cream/85 backdrop-blur-md" : "border-transparent bg-brand-cream",
        )}
      >
        <div className="mx-auto flex h-18 max-w-7xl items-center justify-between gap-4 px-4 sm:px-6 lg:px-8">
          <button
            type="button"
            onClick={() => onNavigate("dashboard")}
            className="flex items-center gap-2.5 rounded-lg text-left"
            aria-label={`${APP_NAME} — go to dashboard`}
          >
            <img src="/labelguard-mark.png" alt="" className="h-10 w-10 shrink-0 object-contain" width={40} height={40} />
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
                    : "text-brand-muted hover:bg-brand-light/60 hover:text-brand-dark",
                )}
              >
                {link.label}
              </button>
            ))}
          </nav>

          <button
            type="button"
            className="rounded-lg p-2 text-brand-dark lg:hidden"
            aria-label={navOpen ? "Close navigation menu" : "Open navigation menu"}
            aria-expanded={navOpen}
            onClick={() => onNavOpenChange(!navOpen)}
          >
            {navOpen ? <X className="h-5 w-5" aria-hidden="true" /> : <Menu className="h-5 w-5" aria-hidden="true" />}
          </button>
        </div>
      </header>

      {/* Mobile drawer */}
      <div
        className={cx(
          "fixed inset-0 z-50 lg:hidden",
          navOpen ? "pointer-events-auto" : "pointer-events-none",
        )}
        aria-hidden={!navOpen}
      >
        <div
          className={cx(
            "absolute inset-0 bg-brand-dark/25 transition-opacity duration-300",
            navOpen ? "opacity-100" : "opacity-0",
          )}
          onClick={() => onNavOpenChange(false)}
        />
        <nav
          className={cx(
            "absolute inset-y-0 right-0 flex w-72 max-w-[85vw] flex-col gap-1 bg-brand-white p-5 shadow-lg transition-transform duration-300",
            navOpen ? "translate-x-0" : "translate-x-full",
          )}
          aria-label="Mobile"
        >
          {NAV_LINKS.map((link) => {
            const Icon = link.icon;
            return (
              <button
                key={link.id}
                type="button"
                onClick={() => onNavigate(link.id)}
                className={cx(
                  "flex items-center gap-3 rounded-lg px-3 py-2.5 text-left text-sm",
                  active === link.id ? "bg-brand-light font-medium text-brand-dark" : "text-brand-muted hover:bg-brand-light/60",
                )}
              >
                <Icon className="h-4 w-4" aria-hidden="true" />
                {link.label}
              </button>
            );
          })}
        </nav>
      </div>
    </>
  );
}

/* ---------------------------- shared small pieces --------------------------- */

function BackButton({ onClick }: { onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="inline-flex items-center gap-1.5 text-sm font-medium text-brand-muted transition-colors hover:text-brand-dark"
    >
      <ArrowLeft className="h-4 w-4" aria-hidden="true" />
      Back to Dashboard
    </button>
  );
}

function SectionHeader({
  eyebrow,
  title,
  text,
}: {
  eyebrow?: string;
  title: string;
  text?: string;
}) {
  return (
    <div className="max-w-2xl">
      {eyebrow && (
        <p className="text-[11px] font-semibold tracking-[0.24em] text-brand-green uppercase">{eyebrow}</p>
      )}
      <h2 className="mt-2 text-2xl font-light tracking-tight text-brand-dark sm:text-3xl">{title}</h2>
      {text && <p className="mt-2 text-sm leading-relaxed text-brand-muted">{text}</p>}
    </div>
  );
}

function DemoNote({ className }: { className?: string }) {
  return (
    <p className={cx("text-xs leading-relaxed text-brand-muted", className)}>
      AI-assisted compliance assessment only — results require officer verification and are not a legal
      certification.
    </p>
  );
}

const PIPELINE_STEPS: { num: string; label: string; icon: LucideIcon }[] = [
  { num: "01", label: "Upload", icon: ScanLine },
  { num: "02", label: "Extract", icon: ScanLine },
  { num: "03", label: "Analyze", icon: FileCheck },
  { num: "04", label: "Verify", icon: CheckCircle2 },
  { num: "05", label: "Report", icon: FileText },
];

function Pipeline({ activeStep = 0 }: { activeStep?: number }) {
  return (
    <ol
      className="grid grid-cols-5 items-start gap-1 sm:flex sm:items-center sm:justify-between sm:gap-2"
      aria-label="AI inspection pipeline"
    >
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
              <span
                className={cx(
                  "text-[10px] font-semibold tracking-[0.18em]",
                  isActive ? "text-brand-dark" : "text-brand-muted",
                )}
              >
                {step.num}
              </span>
              <span
                className={cx(
                  "text-xs sm:text-sm",
                  isActive ? "font-semibold text-brand-dark" : "font-medium text-brand-muted",
                )}
              >
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

function DashboardView({
  onNavigate,
  onOcrCompleted,
}: {
  onNavigate: (view: View) => void;
  onOcrCompleted: (result: UploadSuccess) => void;
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
          AI-assisted compliance inspection for packaged commodity labels — every result requires officer
          verification.
        </p>
        <div className="mt-8 flex flex-col gap-3 sm:flex-row">
          <button type="button" onClick={() => onNavigate("inspect")} className="inline-flex items-center justify-center gap-2 rounded-lg bg-brand-dark px-5 py-2.5 text-sm font-medium text-white transition-colors hover:bg-brand-green">
            Start New Inspection
            <ArrowRight className="h-4 w-4" aria-hidden="true" />
          </button>
          <button
            type="button"
            onClick={() => onNavigate("history")}
            className="inline-flex items-center justify-center gap-2 rounded-lg border border-brand-border bg-white px-5 py-2.5 text-sm font-medium text-brand-dark transition-colors hover:border-brand-green/40 hover:bg-brand-light"
          >
            <HistoryIcon className="h-4 w-4" aria-hidden="true" />
            View Inspection History
          </button>
        </div>
      </section>

      {/* Overview — real database metrics */}
      <section className="animate-fade-up py-4" style={{ animationDelay: "80ms" }}>
        <SectionHeader
          eyebrow="Overview"
          title="Compliance Overview"
          text="Live inspection counts from the database — automated and officer-verified assessments shown side by side."
        />
        <div className="mt-6">
          <DashboardMetricsCards onNavigate={onNavigate} />
        </div>
      </section>

      {/* Inspection workspace */}
      <section className="animate-fade-up py-14" style={{ animationDelay: "140ms" }} aria-labelledby="inspect-heading">
        <SectionHeader
          title="Inspect a Product"
          text="Upload product packaging or label images to begin an automated compliance inspection."
        />
        <div className="mt-6">
          <UploadFlow onCompleted={onOcrCompleted} />
        </div>
        <DemoNote className="mt-3" />
      </section>

      {/* Pipeline */}
      <section className="animate-fade-up pb-8" style={{ animationDelay: "200ms" }} aria-labelledby="pipeline-heading">
        <div className="rounded-2xl border border-brand-border bg-white p-6 sm:p-8">
          <div className="mb-8 flex flex-col gap-1">
            <h3 id="pipeline-heading" className="text-sm font-semibold tracking-[0.14em] text-brand-muted uppercase">
              AI Inspection Pipeline
            </h3>
            <p className="text-sm text-brand-muted">
              Every inspection moves through a five-stage pipeline — from raw image to an evidence-backed,
              officer-ready report.
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
  onNavigate,
  onOcrCompleted,
}: {
  onNavigate: (view: View) => void;
  onOcrCompleted: (result: UploadSuccess) => void;
}) {
  return (
    <div className="mx-auto max-w-7xl animate-fade-up px-4 pb-20 sm:px-6 lg:px-8">
      <div className="pt-8 sm:pt-12">
        <BackButton onClick={() => onNavigate("dashboard")} />
        <SectionHeader
          eyebrow="Product Inspection"
          title="Inspect a Product"
          text="Upload a product label image or PDF. The pipeline reads the visible text, extracts structured information, measures the label, and runs the legal evaluation."
        />
      </div>

      <div className="grid gap-6 lg:grid-cols-5">
        <div className="lg:col-span-3">
          <UploadFlow onCompleted={onOcrCompleted} />
          <DemoNote className="mt-3" />
        </div>

        <aside className="lg:col-span-2">
          <div className="rounded-2xl border border-brand-border bg-white p-6 sm:p-8">
            <h3 className="text-sm font-semibold tracking-[0.14em] text-brand-muted uppercase">What the pipeline reads</h3>
            <p className="mt-2 text-sm leading-relaxed text-brand-muted">
              OCR text with positions and confidence, structured extraction with provenance, visual measurements
              from the CV evidence layer, and a rule-by-rule legal assessment.
            </p>
            <ul className="mt-5 space-y-3">
              {[
                "Printed text lines with pixel bounding boxes",
                "Structured fields with extraction provenance",
                "Visual measurements: contrast, regions, candidate PDP",
                "Rule results with evidence references",
                "Officer verification and audit history",
              ].map((item) => (
                <li key={item} className="flex items-start gap-2.5 text-sm text-brand-dark">
                  <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-brand-success" aria-hidden="true" />
                  {item}
                </li>
              ))}
            </ul>
            <div className="mt-6 border-t border-brand-border pt-5">
              <Pipeline activeStep={2} />
            </div>
          </div>
        </aside>
      </div>
    </div>
  );
}

/* ---------------------------------- footer --------------------------------- */

function Footer() {
  return (
    <footer className="border-t border-brand-border bg-white">
      <div className="mx-auto flex max-w-7xl flex-col items-start justify-between gap-3 px-4 py-8 sm:flex-row sm:items-center sm:px-6 lg:px-8">
        <div className="flex items-center gap-3">
          <img src="/favicon.png" alt="" className="h-8 w-8 shrink-0 object-contain" width={32} height={32} />
          <p className="text-xs leading-relaxed text-brand-muted">
            <span className="font-medium text-brand-dark">{APP_NAME}</span> — Analyze. Verify. Comply.
            AI-assisted assessment; officer verification required for regulatory decisions. Not a legal
            certification.
          </p>
        </div>
      </div>
    </footer>
  );
}

/* ----------------------------------- app ----------------------------------- */

export default function App() {
  // Persisted so a browser refresh on the OCR result screen can reload the
  // inspection from the backend (acceptance test: refresh still shows results).
  const [view, setView] = useState<View>(() =>
    window.sessionStorage.getItem("labelguard.activeInspectionId") ? "ocr-result" : "dashboard",
  );
  const [navOpen, setNavOpen] = useState(false);
  const [scrolled, setScrolled] = useState(false);
  const [activeInspectionId, setActiveInspectionId] = useState<string | null>(
    () => window.sessionStorage.getItem("labelguard.activeInspectionId"),
  );

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

  const handleNewInspection = useCallback(() => {
    navigate("inspect");
  }, [navigate]);

  // Open a real inspection from History / Reports: persists the active id so
  // a refresh keeps showing the same inspection, then loads the result view.
  const openInspectionFromHistory = useCallback(
    (inspectionId: string) => {
      setActiveInspectionId(inspectionId);
      window.sessionStorage.setItem("labelguard.activeInspectionId", inspectionId);
      navigate("ocr-result");
    },
    [navigate],
  );

  const handleOcrCompleted = useCallback(
    (result: UploadSuccess) => {
      setActiveInspectionId(result.inspection_id);
      window.sessionStorage.setItem("labelguard.activeInspectionId", result.inspection_id);
      navigate("ocr-result");
    },
    [navigate],
  );

  return (
    <div className="flex min-h-screen flex-col bg-brand-cream text-brand-dark">
      <Navbar view={view} navOpen={navOpen} onNavOpenChange={setNavOpen} onNavigate={navigate} scrolled={scrolled} />

      <main className="flex-1">
        {view === "dashboard" && <DashboardView onNavigate={navigate} onOcrCompleted={handleOcrCompleted} />}
        {view === "inspect" && <InspectView onNavigate={navigate} onOcrCompleted={handleOcrCompleted} />}
        {view === "ocr-result" && activeInspectionId && (
          <OcrResultView inspectionId={activeInspectionId} onNavigate={() => navigate("dashboard")} />
        )}
        {view === "reports" && (
          <ReportsDataView onOpenInspection={openInspectionFromHistory} onNewInspection={handleNewInspection} />
        )}
        {view === "history" && (
          <InspectionHistoryView onOpenInspection={openInspectionFromHistory} onNewInspection={handleNewInspection} />
        )}
      </main>

      <Footer />
    </div>
  );
}
