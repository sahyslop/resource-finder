"use client";

import { FormEvent, useState } from "react";

/** Same-origin `/api/...` when unset (proxied by Next); else full URL to Flask. */
function apiUrl(path: string): string {
  const base = (process.env.NEXT_PUBLIC_API_URL ?? "").trim().replace(/\/$/, "");
  const p = path.startsWith("/") ? path : `/${path}`;
  return base ? `${base}${p}` : p;
}

type Resource = {
  resource_id?: string;
  org_name?: string;
  service_category?: string[];
  address?: string;
  city?: string;
  state?: string;
  zip?: string;
  hours_text?: string;
  phone?: string;
  source_url?: string;
};

type SearchResultItem = {
  rank: number;
  final_score: number;
  distance_label: string;
  status: string;
  eligibility_preview: string;
  resource: Resource;
};

type SearchResponse = {
  query: string;
  lat: number;
  lon: number;
  top_k: number;
  indexed_count: number;
  max_miles?: number;
  results: SearchResultItem[];
};

const DISTANCE_PRESETS_MI = [5, 10, 15, 25, 50] as const;

function formatCategories(categories: string[] | undefined) {
  if (!categories?.length) return "";
  return categories.map((c) => c.replace(/_/g, " ")).join(", ");
}

function formatAddress(r: Resource) {
  const line = (r.address ?? "").trim();
  if (line) return line;
  const city = r.city ?? "";
  const state = r.state ?? "";
  const zip = r.zip ?? "";
  return [city, state, zip].filter(Boolean).join(", ");
}

export default function Home() {
  const [query, setQuery] = useState("");
  const [lat, setLat] = useState("42.2808");
  const [lon, setLon] = useState("-83.7430");
  const [top, setTop] = useState("5");
  const [distanceFilterOn, setDistanceFilterOn] = useState(false);
  const [maxMiles, setMaxMiles] = useState("10");
  const [loading, setLoading] = useState(false);
  const [locating, setLocating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<SearchResponse | null>(null);

  function locateMe() {
    if (typeof navigator === "undefined" || !navigator.geolocation) {
      setError(
        "This browser does not support location. Enter latitude and longitude manually."
      );
      return;
    }
    setLocating(true);
    setError(null);
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setLat(pos.coords.latitude.toFixed(6));
        setLon(pos.coords.longitude.toFixed(6));
        setLocating(false);
      },
      (err) => {
        setLocating(false);
        const code = err.code;
        if (code === err.PERMISSION_DENIED) {
          setError(
            "Location permission denied. Allow location for this site or enter coordinates manually."
          );
        } else if (code === err.POSITION_UNAVAILABLE) {
          setError(
            "Could not determine your position. Try again or enter coordinates manually."
          );
        } else if (code === err.TIMEOUT) {
          setError("Location request timed out. Try again.");
        } else {
          setError("Could not read your location.");
        }
      },
      { enableHighAccuracy: true, maximumAge: 60_000, timeout: 15_000 }
    );
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setData(null);
    const q = query.trim();
    if (!q) {
      setError("Enter a search query.");
      return;
    }

    const latN = parseFloat(lat);
    const lonN = parseFloat(lon);
    const topN = parseInt(top, 10);
    if (Number.isNaN(latN) || Number.isNaN(lonN) || Number.isNaN(topN)) {
      setError("Latitude, longitude, and number of results must be valid numbers.");
      return;
    }

    let maxMilesN: number | undefined;
    if (distanceFilterOn) {
      const parsed = parseFloat(maxMiles);
      if (Number.isNaN(parsed) || parsed <= 0) {
        setError("Enter a valid distance in miles (greater than zero).");
        return;
      }
      maxMilesN = parsed;
    }

    setLoading(true);
    try {
      const res = await fetch(apiUrl("/api/search"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          query: q,
          lat: latN,
          lon: lonN,
          top: topN,
          ...(maxMilesN !== undefined ? { max_miles: maxMilesN } : {}),
        }),
      });
      const json = await res.json();
      if (!res.ok) {
        setError((json as { error?: string }).error ?? "Search failed.");
        return;
      }
      setData(json as SearchResponse);
    } catch {
      setError(
        "Could not reach the API. Is the Flask server running? " +
          (process.env.NEXT_PUBLIC_API_URL?.trim()
            ? `(${process.env.NEXT_PUBLIC_API_URL.trim()})`
            : "With default settings, Next proxies /api/* to http://127.0.0.1:5000 (see API_UPSTREAM).")
      );
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-full bg-stone-50 text-stone-900 dark:bg-stone-950 dark:text-stone-100">
      <main className="mx-auto flex max-w-2xl flex-col gap-10 px-4 py-16 sm:px-6">
        <header className="space-y-2 text-center sm:text-left">
          <h1 className="text-2xl font-semibold tracking-tight text-stone-800 dark:text-stone-50">
            Resource finder
          </h1>
          <p className="text-sm leading-relaxed text-stone-600 dark:text-stone-400">
            Find food, shelter, and housing help in Michigan when you need support.
            Search in plain language; results use your location for distance.
          </p>
        </header>

        <form onSubmit={onSubmit} className="space-y-4">
          <div className="flex flex-col gap-2 sm:flex-row">
            <label className="sr-only" htmlFor="q">
              Search
            </label>
            <input
              id="q"
              type="search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="e.g. food pantry near me, emergency shelter tonight"
              className="min-h-11 flex-1 rounded-lg border border-stone-200 bg-white px-3 py-2 text-sm shadow-sm outline-none ring-stone-400 placeholder:text-stone-400 focus:ring-2 dark:border-stone-700 dark:bg-stone-900 dark:ring-stone-500"
              autoComplete="off"
            />
            <button
              type="submit"
              disabled={loading}
              className="min-h-11 rounded-lg bg-stone-800 px-4 text-sm font-medium text-white transition hover:bg-stone-700 disabled:opacity-50 dark:bg-stone-200 dark:text-stone-900 dark:hover:bg-white"
            >
              {loading ? "Searching…" : "Search"}
            </button>
          </div>
          <fieldset className="space-y-3 rounded-lg border border-stone-200 bg-white/80 p-3 text-xs dark:border-stone-800 dark:bg-stone-900/50">
            <legend className="px-1 text-[11px] font-medium uppercase tracking-wide text-stone-500">
              Location &amp; results
            </legend>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="max-w-sm text-[11px] leading-snug text-stone-500 dark:text-stone-400">
                Uses your device location in the browser. No API key or account needed.
              </p>
              <button
                type="button"
                onClick={locateMe}
                disabled={loading || locating}
                className="shrink-0 rounded-md border border-stone-300 bg-stone-100 px-3 py-1.5 text-[11px] font-medium text-stone-800 transition hover:bg-stone-200 disabled:opacity-50 dark:border-stone-600 dark:bg-stone-800 dark:text-stone-200 dark:hover:bg-stone-700"
              >
                {locating ? "Locating…" : "Use my location"}
              </button>
            </div>
            <div className="grid gap-3 sm:grid-cols-3">
            <label className="flex flex-col gap-1">
              <span className="text-stone-500">Latitude</span>
              <input
                value={lat}
                onChange={(e) => setLat(e.target.value)}
                className="rounded border border-stone-200 bg-white px-2 py-1.5 dark:border-stone-700 dark:bg-stone-900"
              />
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-stone-500">Longitude</span>
              <input
                value={lon}
                onChange={(e) => setLon(e.target.value)}
                className="rounded border border-stone-200 bg-white px-2 py-1.5 dark:border-stone-700 dark:bg-stone-900"
              />
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-stone-500">Max results</span>
              <input
                value={top}
                onChange={(e) => setTop(e.target.value)}
                type="number"
                min={1}
                max={20}
                className="rounded border border-stone-200 bg-white px-2 py-1.5 dark:border-stone-700 dark:bg-stone-900"
              />
            </label>
            </div>

            <div className="border-t border-stone-200 pt-3 dark:border-stone-700">
              <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                <div className="min-w-0 space-y-0.5">
                  <p className="text-[11px] font-medium text-stone-600 dark:text-stone-300">
                    Distance limit
                  </p>
                  <p className="text-[11px] leading-snug text-stone-500 dark:text-stone-400">
                    When on, only resources with a known location within this
                    radius are considered.
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => setDistanceFilterOn((v) => !v)}
                  aria-pressed={distanceFilterOn}
                  className={`shrink-0 rounded-lg border px-3 py-2 text-left text-[11px] font-medium transition sm:min-w-[9.5rem] ${
                    distanceFilterOn
                      ? "border-emerald-700/40 bg-emerald-50 text-emerald-950 ring-1 ring-emerald-600/25 dark:border-emerald-500/30 dark:bg-emerald-950/50 dark:text-emerald-100 dark:ring-emerald-500/20"
                      : "border-stone-300 bg-stone-100 text-stone-800 hover:bg-stone-200 dark:border-stone-600 dark:bg-stone-800 dark:text-stone-200 dark:hover:bg-stone-700"
                  }`}
                >
                  <span className="block text-[10px] uppercase tracking-wide text-stone-500 dark:text-stone-400">
                    {distanceFilterOn ? "Enabled" : "Off"}
                  </span>
                  <span className="mt-0.5 block">
                    {distanceFilterOn
                      ? `Within ${maxMiles.trim() || "…"} mi`
                      : "Any distance"}
                  </span>
                </button>
              </div>

              {distanceFilterOn && (
                <div className="mt-3 space-y-2">
                  <p className="text-[10px] font-medium uppercase tracking-wide text-stone-500">
                    Max distance
                  </p>
                  <div className="flex flex-wrap items-center gap-2">
                    {DISTANCE_PRESETS_MI.map((m) => {
                      const active = maxMiles.trim() === String(m);
                      return (
                        <button
                          key={m}
                          type="button"
                          onClick={() => setMaxMiles(String(m))}
                          className={`rounded-full border px-2.5 py-1 text-[11px] font-medium tabular-nums transition ${
                            active
                              ? "border-stone-800 bg-stone-800 text-white dark:border-stone-200 dark:bg-stone-200 dark:text-stone-900"
                              : "border-stone-300 bg-white text-stone-700 hover:border-stone-400 hover:bg-stone-50 dark:border-stone-600 dark:bg-stone-900 dark:text-stone-300 dark:hover:bg-stone-800"
                          }`}
                        >
                          {m} mi
                        </button>
                      );
                    })}
                    <label className="flex items-center gap-1.5 rounded-full border border-dashed border-stone-300 bg-stone-50/80 px-2.5 py-1 dark:border-stone-600 dark:bg-stone-900/40">
                      <span className="text-[11px] text-stone-500">Other</span>
                      <input
                        type="number"
                        min={1}
                        max={250}
                        step={1}
                        value={maxMiles}
                        onChange={(e) => setMaxMiles(e.target.value)}
                        className="w-14 rounded border border-stone-200 bg-white px-1.5 py-0.5 text-center text-[11px] tabular-nums text-stone-900 dark:border-stone-600 dark:bg-stone-900 dark:text-stone-100"
                      />
                    </label>
                  </div>
                </div>
              )}
            </div>
          </fieldset>
        </form>

        {error && (
          <p
            className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800 dark:border-red-900 dark:bg-red-950/40 dark:text-red-200"
            role="alert"
          >
            {error}
          </p>
        )}

        {data && (
          <section className="space-y-4" aria-live="polite">
            <p className="text-xs text-stone-500">
              {data.results.length} result{data.results.length === 1 ? "" : "s"} ·{" "}
              {data.indexed_count} resources indexed
              {data.max_miles != null && (
                <>
                  {" "}
                  · within {data.max_miles} mi
                </>
              )}
            </p>
            {data.results.length === 0 ? (
              <p className="rounded-lg border border-stone-200 bg-white px-4 py-6 text-center text-sm text-stone-600 dark:border-stone-800 dark:bg-stone-900/40 dark:text-stone-400">
                No results found. Try a broader query or remove constraints.
              </p>
            ) : (
              <ul className="space-y-4">
                {data.results.map((item) => {
                  const r = item.resource;
                  const name = r.org_name ?? "Unknown";
                  const categories = formatCategories(r.service_category);
                  const addr = formatAddress(r);
                  const hours = (r.hours_text ?? "").trim();
                  return (
                    <li
                      key={r.resource_id ?? `${name}-${item.rank}`}
                      className="rounded-xl border border-stone-200 bg-white p-4 shadow-sm dark:border-stone-800 dark:bg-stone-900/60"
                    >
                      <div className="flex flex-wrap items-baseline justify-between gap-2">
                        <h2 className="text-base font-medium text-stone-800 dark:text-stone-100">
                          {item.rank}. {name}
                        </h2>
                        <span className="text-xs tabular-nums text-stone-500">
                          score {item.final_score.toFixed(2)}
                        </span>
                      </div>
                      {categories && (
                        <p className="mt-1 text-xs text-stone-500">{categories}</p>
                      )}
                      {addr && (
                        <p className="mt-2 text-sm text-stone-700 dark:text-stone-300">
                          {addr}
                        </p>
                      )}
                      <dl className="mt-3 grid gap-1 text-xs text-stone-600 dark:text-stone-400">
                        <div className="flex gap-2">
                          <dt className="shrink-0 font-medium text-stone-500">
                            Distance
                          </dt>
                          <dd>{item.distance_label}</dd>
                        </div>
                        <div className="flex gap-2">
                          <dt className="shrink-0 font-medium text-stone-500">
                            Status
                          </dt>
                          <dd>{item.status}</dd>
                        </div>
                        {hours && (
                          <div className="flex gap-2">
                            <dt className="shrink-0 font-medium text-stone-500">
                              Hours
                            </dt>
                            <dd className="line-clamp-2">{hours}</dd>
                          </div>
                        )}
                        {item.eligibility_preview && (
                          <div className="flex gap-2">
                            <dt className="shrink-0 font-medium text-stone-500">
                              Eligibility
                            </dt>
                            <dd className="line-clamp-2">
                              {item.eligibility_preview}
                            </dd>
                          </div>
                        )}
                        {r.phone && (
                          <div className="flex gap-2">
                            <dt className="shrink-0 font-medium text-stone-500">
                              Phone
                            </dt>
                            <dd>
                              <a
                                href={`tel:${r.phone.replace(/\s/g, "")}`}
                                className="underline decoration-stone-300 underline-offset-2 hover:text-stone-900 dark:hover:text-stone-200"
                              >
                                {r.phone}
                              </a>
                            </dd>
                          </div>
                        )}
                        {r.source_url && (
                          <div className="flex gap-2 pt-1">
                            <dt className="sr-only">Source</dt>
                            <dd>
                              <a
                                href={r.source_url}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="text-sm font-medium text-stone-800 underline decoration-stone-300 underline-offset-2 hover:text-stone-950 dark:text-stone-200"
                              >
                                View source
                              </a>
                            </dd>
                          </div>
                        )}
                      </dl>
                    </li>
                  );
                })}
              </ul>
            )}
          </section>
        )}
      </main>
    </div>
  );
}
