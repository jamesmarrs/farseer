#!/usr/bin/env python3
"""Resolve each MPN in the KiCad BOM to an LCSC / JLCPCB part number.

Reads docs/generated/farseer-bom.csv (produced by export_kicad.sh) and writes
docs/generated/jlcpcb-parts.csv, one row per unique MPN.

Matching is EXACT MPN ONLY, case-insensitive: this board is an automotive-grade
design (AEC-Q200 passives, AEC-Q100 regulators) and a "close enough" substitute
silently drops that qualification. A part JLCPCB does not carry is reported as
no-exact-match with an empty LCSC column, for a human to decide. Such a row also
lists whatever JLC does stock under a similar MPN in JLCCandidates - those are
UNVERIFIED leads (often only a tape-and-reel suffix apart, sometimes a different
grade entirely), never an automatic substitution.

The one liberty taken is punctuation: JLC writes some MPNs without the
manufacturer's dashes (EEH-ZA1H101P as EEHZA1H101P), so comparison ignores
non-alphanumeric characters. That is the same ordering number, not a substitute,
and those rows are flagged exact-normalized.

Existing hits in jlcpcb-parts.csv are reused so re-runs stay offline; rows that
previously missed are retried. Use --refresh to re-query every MPN.
"""
import argparse
import csv
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BOM_CSV = os.path.join(REPO_ROOT, "docs", "generated", "farseer-bom.csv")
OUT_CSV = os.path.join(REPO_ROOT, "docs", "generated", "jlcpcb-parts.csv")

SEARCH_URL = "https://jlcsearch.tscircuit.com/api/search"
FIELDS = [
    "MPN",
    "Manufacturer",
    "LCSC",
    "PartClass",
    "Stock",
    "UnitPrice",
    "JLCPackage",
    "JLCDescription",
    "MatchStatus",
    "JLCCandidates",
]
STEM_LEN = 8
MAX_CANDIDATES = 5


def normalize(mpn):
    """Upper-case, punctuation-stripped MPN for comparison."""
    return re.sub(r"[^A-Z0-9]", "", (mpn or "").upper())


def die(msg):
    sys.exit(f"error: {msg}")


def read_bom():
    """Return [(mpn, manufacturer, [designators])] for unique MPNs, in BOM order."""
    if not os.path.exists(BOM_CSV):
        die(f"{BOM_CSV} not found - run scripts/export_kicad.sh first")
    order, seen = [], {}
    with open(BOM_CSV, newline="") as fh:
        for row in csv.DictReader(fh):
            mpn = row["MPN"].strip()
            if not mpn:
                continue
            key = mpn.upper()
            if key not in seen:
                seen[key] = [mpn, row["Manufacturer"].strip(), []]
                order.append(key)
            seen[key][2].append(row["Reference"])
    return [tuple(seen[k]) for k in order]


def read_previous():
    """Previous successful lookups, keyed by upper-case MPN."""
    if not os.path.exists(OUT_CSV):
        return {}
    with open(OUT_CSV, newline="") as fh:
        return {
            row["MPN"].strip().upper(): row
            for row in csv.DictReader(fh)
            if row.get("LCSC", "").strip()
        }


def search(mpn, timeout=20):
    url = f"{SEARCH_URL}?{urllib.parse.urlencode({'q': mpn})}"
    req = urllib.request.Request(url, headers={"User-Agent": "farseer-bom/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.load(resp).get("components", [])


def part_class(component):
    if component.get("is_basic"):
        return "Basic"
    if component.get("is_preferred"):
        return "Preferred"
    return "Extended"


def describe_candidates(components):
    """One-line, clearly unverified summary of what JLC stocks under a near MPN."""
    ranked = sorted(components, key=lambda c: -(c.get("stock") or 0))[:MAX_CANDIDATES]
    return "; ".join(
        f"{c.get('mfr')} (C{c['lcsc']}, {c.get('package') or '?'}, stock {c.get('stock') or 0})"
        for c in ranked
    )


def lookup(mpn, manufacturer, retries=3):
    """Exact-MPN lookup. Returns a result row dict."""
    miss = {
        "MPN": mpn,
        "Manufacturer": manufacturer,
        "LCSC": "",
        "PartClass": "",
        "Stock": "",
        "UnitPrice": "",
        "JLCPackage": "",
        "JLCDescription": "",
        "MatchStatus": "no-exact-match",
        "JLCCandidates": "",
    }

    def try_search(query):
        for attempt in range(retries):
            try:
                return search(query)
            except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as exc:
                if attempt == retries - 1:
                    raise
                time.sleep(1.5 * (attempt + 1))

    try:
        components = try_search(mpn)
    except OSError as exc:
        miss["MatchStatus"] = f"lookup-failed: {exc}"
        return miss

    target = normalize(mpn)
    exact = [c for c in components if normalize(c.get("mfr")) == target]
    if not exact:
        # Nothing under the full MPN: widen to the family stem purely to report
        # what JLC does stock nearby. Still no LCSC number is assigned.
        if not components and len(mpn) > STEM_LEN:
            try:
                components = try_search(mpn[:STEM_LEN])
            except OSError:
                components = []
        miss["JLCCandidates"] = describe_candidates(components)
        return miss

    # Prefer the in-stock offer, then the cheaper one, when JLC lists duplicates.
    exact.sort(key=lambda c: (-(c.get("stock") or 0), c.get("price") or 1e9))
    best = exact[0]
    return {
        "MPN": mpn,
        "Manufacturer": manufacturer,
        "LCSC": f"C{best['lcsc']}",
        "PartClass": part_class(best),
        "Stock": str(best.get("stock") or 0),
        "UnitPrice": "" if best.get("price") is None else f"{best['price']:.4f}",
        "JLCPackage": (best.get("package") or "").strip(),
        "JLCDescription": " ".join((best.get("description") or "").split()),
        "MatchStatus": "exact" if (best.get("mfr") or "").strip().upper() == mpn.upper() else "exact-normalized",
        "JLCCandidates": "" if (best.get("mfr") or "").strip().upper() == mpn.upper() else f"JLC lists it as {best.get('mfr')}",
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--refresh", action="store_true", help="re-query every MPN, ignoring cached hits")
    ap.add_argument("--delay", type=float, default=0.3, help="seconds between queries (default 0.3)")
    args = ap.parse_args()

    parts = read_bom()
    previous = {} if args.refresh else read_previous()

    rows = []
    for mpn, manufacturer, refs in parts:
        cached = previous.get(mpn.upper())
        if cached:
            row = {f: cached.get(f, "") for f in FIELDS}
            row["Manufacturer"] = manufacturer
            rows.append(row)
            print(f"  cached {mpn:24s} {row['LCSC']}")
            continue
        row = lookup(mpn, manufacturer)
        rows.append(row)
        status = row["LCSC"] or row["MatchStatus"]
        print(f"  {'ok    ' if row['LCSC'] else 'MISS  '} {mpn:24s} {status}")
        time.sleep(args.delay)

    os.makedirs(os.path.dirname(OUT_CSV), exist_ok=True)
    with open(OUT_CSV, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS, quoting=csv.QUOTE_ALL)
        writer.writeheader()
        writer.writerows(rows)

    hits = [r for r in rows if r["LCSC"]]
    failures = [r for r in rows if r["MatchStatus"].startswith("lookup-failed")]
    normalized = sum(1 for r in hits if r["MatchStatus"] == "exact-normalized")
    print(f"\n{len(hits)}/{len(rows)} MPNs matched exactly -> {OUT_CSV}")
    if normalized:
        print(f"  of those, {normalized} matched only after ignoring MPN punctuation")
    for label in ("Basic", "Preferred", "Extended"):
        n = sum(1 for r in hits if r["PartClass"] == label)
        if n:
            print(f"  {label}: {n}")
    if failures:
        print(f"warning: {len(failures)} lookups errored out; re-run to retry", file=sys.stderr)


if __name__ == "__main__":
    main()
