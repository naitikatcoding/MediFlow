import Link from 'next/link';
import {
  ArrowRight,
  Boxes,
  Building2,
  Check,
  ScanLine,
  Shield,
  Sparkles,
  TrendingDown,
} from 'lucide-react';
import { ScrollReveal } from '../components/landing/ScrollReveal';

export const metadata = {
  title: 'MediFlow — Medicine supply, made clear',
  description:
    'A clearer way to manage medicine inventory, anticipate shortages, reduce expiry waste, and coordinate safe redistribution.',
};

const capabilities = [
  {
    icon: Boxes,
    title: 'Know what is on hand',
    description:
      'See medicine and batch-level inventory across facilities, with the details teams need to make informed decisions.',
  },
  {
    icon: TrendingDown,
    title: 'Spot risks sooner',
    description:
      'Bring low-stock signals, demand forecasts, and approaching expiries into one calm, actionable view.',
  },
  {
    icon: Building2,
    title: 'Move surplus safely',
    description:
      'Find potential facility-to-facility matches, then coordinate reviews and approvals before anything moves.',
  },
];

const steps = [
  {
    number: '01',
    title: 'See the whole picture',
    description: 'Bring facility stock, batches, and demand into a shared operational view.',
  },
  {
    number: '02',
    title: 'Understand what needs attention',
    description: 'Surface shortage and expiry risks while there is still time to respond.',
  },
  {
    number: '03',
    title: 'Coordinate with confidence',
    description: 'Review redistribution opportunities with the right people and clear approvals.',
  },
  {
    number: '04',
    title: 'Keep every handoff visible',
    description: 'Follow transfers through dispatch and receipt with QR-supported tracking.',
  },
];

const operatingFacts = [
  { value: '04', label: 'stages from signal to receipt' },
  { value: '02', label: 'source and destination approvals' },
  { value: '01', label: 'QR-traceable transfer record' },
];

function Brand() {
  return (
    <Link href="/" className="inline-flex items-center gap-2.5" aria-label="MediFlow home">
      <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-emerald-800 text-white">
        <Shield className="h-[18px] w-[18px]" strokeWidth={2.2} />
      </span>
      <span className="text-[15px] font-semibold tracking-tight text-slate-900">
        MediFlow
      </span>
    </Link>
  );
}

export default function LandingPage() {
  return (
    <main className="overflow-hidden bg-[#fbfcfa] text-slate-900">
      <header className="sticky top-0 z-30 border-b border-slate-200/80 bg-[#fbfcfa]/90 backdrop-blur-md">
        <div className="mx-auto flex h-[4.5rem] max-w-7xl items-center justify-between px-5 sm:px-8">
          <Brand />
          <nav aria-label="Main navigation" className="hidden items-center gap-8 md:flex">
            <a href="#platform" className="text-[13px] font-medium text-slate-600 transition hover:text-emerald-800">Platform</a>
            <a href="#how-it-works" className="text-[13px] font-medium text-slate-600 transition hover:text-emerald-800">How it works</a>
            <a href="#principles" className="text-[13px] font-medium text-slate-600 transition hover:text-emerald-800">Our approach</a>
          </nav>
          <Link
            href="/dashboard"
            className="inline-flex items-center gap-2 rounded-lg bg-emerald-800 px-4 py-2.5 text-xs font-semibold text-white transition hover:bg-emerald-900 focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-emerald-200"
          >
            Get started
            <ArrowRight className="h-3.5 w-3.5" />
          </Link>
        </div>
      </header>

      <section className="relative bg-[radial-gradient(ellipse_at_50%_0%,rgba(16,185,129,0.09),transparent_68%)]">
        <div className="mx-auto max-w-7xl px-5 pb-14 pt-20 sm:px-8 sm:pb-16 sm:pt-28 lg:pt-32">
          <div className="mx-auto max-w-4xl text-center">
            <ScrollReveal className="mx-auto max-w-4xl">
              <div className="mb-7 inline-flex items-center gap-2 rounded-full border border-emerald-100 bg-white px-3 py-1.5 text-[11px] font-medium text-emerald-900 shadow-sm shadow-emerald-950/[0.03]">
                <Sparkles className="h-3.5 w-3.5 text-emerald-700" />
                Medicine supply, made clear
              </div>
              <h1 className="mx-auto max-w-4xl text-[2.9rem] font-semibold leading-[1.06] tracking-[-0.055em] text-slate-950 sm:text-6xl lg:text-[4.6rem]">
                A clearer path from
                <span className="block text-emerald-800">supply to care.</span>
              </h1>
              <p className="mx-auto mt-6 max-w-2xl text-[15px] leading-7 text-slate-600 sm:text-base">
                MediFlow helps healthcare teams see medicine inventory clearly, anticipate shortages and expiry, and coordinate safe redistribution across facilities.
              </p>
              <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
                <Link
                  href="/dashboard"
                  className="inline-flex min-h-12 items-center justify-center gap-2 rounded-lg bg-emerald-800 px-5 text-sm font-semibold text-white shadow-sm transition hover:bg-emerald-900 focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-emerald-200"
                >
                  Get started
                  <ArrowRight className="h-4 w-4" />
                </Link>
                <a
                  href="#platform"
                  className="inline-flex min-h-12 items-center justify-center gap-2 rounded-lg px-4 text-sm font-semibold text-slate-700 transition hover:bg-white"
                >
                  Explore the platform
                  <ArrowRight className="h-4 w-4" />
                </a>
              </div>
              <div className="mt-8 flex flex-wrap justify-center gap-x-5 gap-y-2 text-[11px] text-slate-500">
                <span className="inline-flex items-center gap-1.5"><Check className="h-3.5 w-3.5 text-emerald-700" />Inventory visibility</span>
                <span className="inline-flex items-center gap-1.5"><Check className="h-3.5 w-3.5 text-emerald-700" />Human-led approvals</span>
                <span className="inline-flex items-center gap-1.5"><Check className="h-3.5 w-3.5 text-emerald-700" />Traceable transfers</span>
              </div>
            </ScrollReveal>
          </div>

          <div className="mx-auto mt-16 grid max-w-4xl grid-cols-1 divide-y divide-slate-200 border-y border-slate-200 bg-white/70 sm:mt-20 sm:grid-cols-3 sm:divide-x sm:divide-y-0">
            {operatingFacts.map((fact, index) => (
              <ScrollReveal
                as="div"
                key={fact.value}
                delay={index * 100}
                className="px-5 py-5 text-center sm:px-7 sm:py-6"
              >
                <p className="text-3xl font-semibold tracking-[-0.05em] text-emerald-900 sm:text-4xl">
                  {fact.value}
                </p>
                <p className="mt-1.5 text-[11px] font-medium text-slate-600 sm:text-xs">
                  {fact.label}
                </p>
              </ScrollReveal>
            ))}
          </div>
        </div>
      </section>

      <section id="platform" className="border-y border-slate-200/80 bg-white">
        <div className="mx-auto max-w-7xl px-5 py-16 sm:px-8 sm:py-20">
          <ScrollReveal className="max-w-2xl">
            <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-emerald-800">A clearer operating picture</p>
            <h2 className="mt-3 text-3xl font-semibold tracking-[-0.04em] text-slate-950 sm:text-[2.6rem]">
              Less searching. Better decisions.
            </h2>
            <p className="mt-4 max-w-xl text-sm leading-6 text-slate-600">
              Bring the signals that matter together, so teams can focus on getting essential medicines where they are needed.
            </p>
          </ScrollReveal>
          <div className="mt-10 grid gap-4 md:grid-cols-3">
            {capabilities.map(({ icon: Icon, title, description }, index) => (
              <ScrollReveal as="article" key={title} delay={index * 100} className="rounded-2xl border border-slate-200 bg-[#fbfcfa] p-6 sm:p-7">
                <span className={`flex h-10 w-10 items-center justify-center rounded-xl ${
                  index === 1 ? 'bg-amber-50 text-amber-800' : 'bg-emerald-50 text-emerald-800'
                }`}>
                  <Icon className="h-[18px] w-[18px]" />
                </span>
                <h3 className="mt-5 text-[15px] font-semibold text-slate-900">{title}</h3>
                <p className="mt-2 text-[13px] leading-6 text-slate-600">{description}</p>
              </ScrollReveal>
            ))}
          </div>
        </div>
      </section>

      <section id="how-it-works" className="mx-auto max-w-7xl px-5 py-16 sm:px-8 sm:py-20">
        <div className="grid gap-10 lg:grid-cols-[0.8fr_1.2fr] lg:gap-20">
          <ScrollReveal>
            <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-emerald-800">How it works</p>
            <h2 className="mt-3 max-w-md text-3xl font-semibold leading-tight tracking-[-0.04em] text-slate-950 sm:text-[2.6rem]">
              From a signal to a tracked handoff.
            </h2>
            <p className="mt-4 max-w-md text-sm leading-6 text-slate-600">
              A practical workflow that keeps people in control while making the next step easier to see.
            </p>
            <Link
              href="/dashboard"
              className="mt-7 inline-flex items-center gap-2 text-sm font-semibold text-emerald-800 transition hover:text-emerald-950"
            >
              See MediFlow in action <ArrowRight className="h-4 w-4" />
            </Link>
          </ScrollReveal>
          <div className="divide-y divide-slate-200 border-y border-slate-200">
            {steps.map((step, index) => (
              <ScrollReveal as="div" key={step.number} delay={index * 70} className="grid grid-cols-[2.75rem_1fr] gap-3 py-5 sm:grid-cols-[3.5rem_1fr] sm:gap-5 sm:py-6">
                <span className="pt-0.5 text-xs font-semibold tracking-wide text-emerald-800">{step.number}</span>
                <div>
                  <h3 className="text-sm font-semibold text-slate-900">{step.title}</h3>
                  <p className="mt-1.5 max-w-xl text-[13px] leading-6 text-slate-600">{step.description}</p>
                </div>
              </ScrollReveal>
            ))}
          </div>
        </div>
      </section>

      <section id="principles" className="bg-[#10251f] text-white">
        <div className="mx-auto grid max-w-7xl gap-10 px-5 py-14 sm:px-8 sm:py-16 md:grid-cols-[1fr_auto] md:items-center">
          <ScrollReveal className="max-w-2xl">
            <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-emerald-300">Built for responsible operations</p>
            <h2 className="mt-3 text-2xl font-semibold tracking-[-0.035em] sm:text-3xl">
              Better visibility. People stay in control.
            </h2>
            <p className="mt-3 max-w-xl text-sm leading-6 text-slate-300">
              MediFlow brings data and teams together. Transfer recommendations remain recommendations—review, approval, and custody are explicit parts of the process.
            </p>
          </ScrollReveal>
          <ScrollReveal as="div" delay={120} className="flex flex-col gap-3 text-[12px] text-slate-200">
            <span className="inline-flex items-center gap-2"><Shield className="h-4 w-4 text-emerald-300" />Human approval before movement</span>
            <span className="inline-flex items-center gap-2"><ScanLine className="h-4 w-4 text-emerald-300" />QR-supported transfer tracking</span>
          </ScrollReveal>
        </div>
      </section>

      <section className="mx-auto max-w-7xl px-5 py-16 sm:px-8 sm:py-20">
        <ScrollReveal className="flex flex-col items-start justify-between gap-7 rounded-2xl border border-emerald-100 bg-emerald-50/70 p-7 sm:p-10 md:flex-row md:items-center">
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-emerald-800">Ready to take a look?</p>
            <h2 className="mt-2 text-2xl font-semibold tracking-[-0.035em] text-slate-950 sm:text-3xl">
              Start with a clearer view of your supply.
            </h2>
            <p className="mt-2 text-sm text-slate-600">Open the MediFlow dashboard—no account setup required.</p>
          </div>
          <Link
            href="/dashboard"
            className="inline-flex min-h-12 shrink-0 items-center justify-center gap-2 rounded-lg bg-emerald-800 px-5 text-sm font-semibold text-white transition hover:bg-emerald-900 focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-emerald-200"
          >
            Get started <ArrowRight className="h-4 w-4" />
          </Link>
        </ScrollReveal>
      </section>

      <footer className="border-t border-slate-200 bg-white">
        <div className="mx-auto flex max-w-7xl flex-col gap-4 px-5 py-6 sm:px-8 md:flex-row md:items-center md:justify-between">
          <Brand />
          <p className="text-[11px] text-slate-500">A clearer way to coordinate essential medicine supply.</p>
          <Link href="/dashboard" className="text-xs font-semibold text-emerald-800 transition hover:text-emerald-950">
            Go to dashboard
          </Link>
        </div>
      </footer>
    </main>
  );
}
