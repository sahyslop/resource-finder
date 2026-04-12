/** Prominent crisis and national helplines (Michigan / US). */
export function CrisisBanner() {
  return (
    <aside
      className="border-b border-amber-200/80 bg-amber-50 text-amber-950 dark:border-amber-900/50 dark:bg-amber-950/40 dark:text-amber-100"
      aria-label="Crisis and emergency resources"
    >
      <div className="mx-auto flex max-w-2xl flex-col gap-2 px-4 py-3 text-sm sm:flex-row sm:flex-wrap sm:items-center sm:justify-between sm:gap-x-6 sm:gap-y-2 sm:px-6">
        <p className="font-medium text-amber-950 dark:text-amber-50">
          If you or someone else is in immediate danger, call{" "}
          <a
            href="tel:911"
            className="rounded underline decoration-amber-700 underline-offset-2 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-amber-800 dark:decoration-amber-300 dark:focus-visible:outline-amber-200"
          >
            911
          </a>
          .
        </p>
        <ul className="flex flex-col gap-1.5 text-[13px] sm:flex-row sm:flex-wrap sm:gap-x-5">
          <li>
            <span className="text-amber-800/90 dark:text-amber-200/90">
              Michigan 211 (free referral):{" "}
            </span>
            <a
              href="tel:211"
              className="font-semibold underline decoration-amber-700 underline-offset-2 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-amber-800 dark:decoration-amber-300"
            >
              Dial 211
            </a>
            {" · "}
            <a
              href="https://www.mi211.org/"
              target="_blank"
              rel="noopener noreferrer"
              className="underline decoration-amber-700 underline-offset-2 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-amber-800 dark:decoration-amber-300"
            >
              mi211.org
            </a>
          </li>
          <li>
            <span className="text-amber-800/90 dark:text-amber-200/90">
              Suicide &amp; crisis (24/7):{" "}
            </span>
            <a
              href="tel:988"
              className="font-semibold underline decoration-amber-700 underline-offset-2 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-amber-800 dark:decoration-amber-300"
            >
              988
            </a>
          </li>
        </ul>
      </div>
    </aside>
  );
}
