import Link from "next/link";

export function SiteNav() {
  return (
    <header className="border-b border-stone-200 bg-white/90 dark:border-stone-800 dark:bg-stone-950/90">
      <div className="mx-auto flex max-w-2xl items-center justify-between gap-4 px-4 py-3 sm:px-6">
        <Link
          href="/"
          className="text-sm font-semibold text-stone-800 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-stone-800 dark:text-stone-100 dark:focus-visible:outline-stone-200"
        >
          Resource finder
        </Link>
        <nav aria-label="Site">
          <Link
            href="/about"
            className="text-sm text-stone-600 underline decoration-stone-300 underline-offset-2 hover:text-stone-900 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-stone-800 dark:text-stone-400 dark:decoration-stone-600 dark:hover:text-stone-100 dark:focus-visible:outline-stone-200"
          >
            About &amp; data
          </Link>
        </nav>
      </div>
    </header>
  );
}
