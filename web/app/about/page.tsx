import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "About & data — Resource finder",
  description:
    "What this Michigan resource finder indexes, its limitations, and how to verify information.",
};

export default function AboutPage() {
  return (
    <div className="min-h-full bg-stone-50 text-stone-900 dark:bg-stone-950 dark:text-stone-100">
      <main
        id="main-content"
        className="mx-auto max-w-2xl px-4 py-12 sm:px-6"
      >
        <p className="mb-6">
          <Link
            href="/"
            className="text-sm text-stone-600 underline decoration-stone-300 underline-offset-2 hover:text-stone-900 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-stone-800 dark:text-stone-400 dark:hover:text-stone-100 dark:focus-visible:outline-stone-200"
          >
            ← Back to search
          </Link>
        </p>
        <h1 className="text-2xl font-semibold tracking-tight text-stone-800 dark:text-stone-50">
          About this tool &amp; data limitations
        </h1>
        <div className="mt-8 space-y-6 text-sm leading-relaxed text-stone-700 dark:text-stone-300">
          <section className="space-y-2" aria-labelledby="purpose-heading">
            <h2
              id="purpose-heading"
              className="text-base font-semibold text-stone-900 dark:text-stone-100"
            >
              What it is
            </h2>
            <p>
              This app is a <strong>decision-support search</strong> for food,
              shelter, and related social services in Michigan. It combines
              keyword search (BM25), semantic similarity (embeddings), your
              chosen address for distance, and optional filters such as open
              hours and eligibility hints. It does{" "}
              <strong>not</strong> replace calling 211, a housing agency, or
              emergency services when you need a definitive answer.
            </p>
          </section>
          <section className="space-y-2" aria-labelledby="indexed-heading">
            <h2
              id="indexed-heading"
              className="text-base font-semibold text-stone-900 dark:text-stone-100"
            >
              What is indexed
            </h2>
            <p>
              Listings come from curated and open datasets we process into a
              single catalog (for example, OpenStreetMap and other
              directories). Each record may include organization name,
              categories, address or approximate location, hours, eligibility
              notes, phone, and source links—not every field is complete for
              every resource.
            </p>
          </section>
          <section className="space-y-2" aria-labelledby="limitations-heading">
            <h2
              id="limitations-heading"
              className="text-base font-semibold text-stone-900 dark:text-stone-100"
            >
              Limitations
            </h2>
            <ul className="list-inside list-disc space-y-1.5 pl-1">
              <li>
                Coverage is <strong>not exhaustive</strong>. Some services will
                be missing, duplicated, or slightly mislocated.
              </li>
              <li>
                Hours and eligibility can be <strong>out of date</strong> or
                summarized incorrectly from source text.
              </li>
              <li>
                &quot;Open now&quot; uses structured hours when available; many
                records lack reliable hours, so that signal can be wrong or
                empty.
              </li>
              <li>
                Rank scores reflect our retrieval model—not a guarantee of
                fitness for your situation.
              </li>
            </ul>
          </section>
          <section className="space-y-2" aria-labelledby="verify-heading">
            <h2
              id="verify-heading"
              className="text-base font-semibold text-stone-900 dark:text-stone-100"
            >
              Always verify
            </h2>
            <p>
              Before you travel or rely on a service,{" "}
              <strong>call ahead</strong> or check the official website. For
              broad help finding services in Michigan, contact{" "}
              <strong>211</strong> (dial 211) or visit{" "}
              <a
                href="https://www.mi211.org/"
                className="font-medium text-stone-900 underline decoration-stone-400 underline-offset-2 hover:decoration-stone-600 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-stone-800 dark:text-stone-100 dark:decoration-stone-500 dark:focus-visible:outline-stone-200"
                target="_blank"
                rel="noopener noreferrer"
              >
                mi211.org
              </a>
              .
            </p>
          </section>
        </div>
      </main>
    </div>
  );
}
