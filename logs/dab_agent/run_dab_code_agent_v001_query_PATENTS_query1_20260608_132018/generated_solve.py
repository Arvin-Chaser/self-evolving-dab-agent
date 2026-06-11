#!/usr/bin/env python3
"""
solve.py

DAB task:
- Compute exponential moving averages (alpha=0.2) of yearly patent filing counts per CPC code.
- Identify, for each CPC code (treated at the most specific group level appearing in the data),
  the year where its EMA is maximal ("best year").
- Output only the CPC group codes (level 5 / most specific codes containing a slash) whose best year is 2022.

Assumptions / notes:
- The script reads the SQLite publication database at PUBLICATION_DB_PATH.
- The CPC classifications may be stored in a JSON-like list in a column (commonly 'cpc' or 'cpc_prefix').
  The script detects the column and attempts several parsing strategies:
    - json.loads if the field is JSON.
    - regex extraction for CPC-like tokens if not JSON.
- Filing year is extracted from the 'filing_date' text by searching for a 4-digit year (e.g., 2019).
  Rows without a parsable filing year are skipped.
- Each patent (row) contributes at most once per CPC code (per row duplicates are deduplicated).
- EMA is computed across the continuous year range from the dataset's min year to max year,
  treating missing-year counts as 0 for that code.
- "Level 5" is interpreted as the most specific CPC group codes as provided (codes containing a slash,
  e.g., "H01M10/0565"). Only such codes are considered for the final filtering.
- The output file contains one CPC code per line (no extra text).

Outputs:
- Writes the final list of CPC codes (one per line) to FINAL_ANSWER_PATH.
- Prints progress and diagnostic info to stdout.
"""

import sqlite3
import json
import re
import sys
from collections import defaultdict, OrderedDict

# Paths provided by the task environment
PUBLICATION_DB_PATH = "/home/m0st1ma/research/DataAgentBench/query_PATENTS/query_dataset/patent_publication.db"
CPC_DEFINITION_SQL_PATH = "/home/m0st1ma/research/DataAgentBench/query_PATENTS/query_dataset/patent_CPCDefinition.sql"
FINAL_ANSWER_PATH = "/home/m0st1ma/research/text2sql/logs/dab_agent/run_dab_code_agent_v001_query_PATENTS_query1_20260608_132018/final_answer.txt"

# EMA smoothing factor
ALPHA = 0.2

def find_cpc_column(cursor):
    """Detect which column likely contains CPC data."""
    cursor.execute("PRAGMA table_info(publicationinfo);")
    cols = [row[1] for row in cursor.fetchall()]
    candidates = [c for c in cols if c and 'cpc' in c.lower()]
    if candidates:
        # Prefer exact 'cpc' then 'cpc_prefix' else first candidate
        if 'cpc' in candidates:
            return 'cpc'
        if 'cpc_prefix' in candidates:
            return 'cpc_prefix'
        return candidates[0]
    # fallback: if no cpc-like column, try to use 'ipc' as last resort
    if 'ipc' in cols:
        return 'ipc'
    raise RuntimeError("No CPC-like column found in publicationinfo table.")

# Regex to find 4-digit year
YEAR_RE = re.compile(r'\b(19|20)\d{2}\b')

# Regex to extract CPC-like codes: start with letter, two digits, one letter, then digits/letters, slash, digits
CPC_TOKEN_RE = re.compile(r'\b[A-H][0-9]{2}[A-Z][0-9A-Z]*/[0-9A-Z]+\b')

def extract_cpc_codes(value):
    """
    Given a field value that may contain CPC info, return a list of CPC code strings.
    Handles JSON list-of-dicts, or raw text with codes.
    """
    if value is None:
        return []
    s = value.strip()
    # Try JSON parse if it looks like JSON
    if s.startswith('[') or s.startswith('{'):
        try:
            parsed = json.loads(s)
            codes = []
            if isinstance(parsed, list):
                for el in parsed:
                    if isinstance(el, dict):
                        code = el.get('code') or el.get('symbol') or el.get('cpc')
                        if code and isinstance(code, str):
                            codes.append(code.strip())
                    elif isinstance(el, str):
                        codes.append(el.strip())
                if codes:
                    return codes
            elif isinstance(parsed, dict):
                # single dict perhaps
                code = parsed.get('code') or parsed.get('symbol') or parsed.get('cpc')
                if code:
                    return [code.strip()]
        except Exception:
            # fall through to regex
            pass
    # Not JSON or JSON parse failed: use regex to find tokens
    codes = CPC_TOKEN_RE.findall(s)
    # Deduplicate maintaining order
    seen = set()
    out = []
    for c in codes:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out

def extract_year(value):
    """Extract a 4-digit year from a natural-language date string. Returns int year or None."""
    if not value:
        return None
    m = YEAR_RE.search(value)
    if m:
        return int(m.group(0))
    return None

def compute_ema_for_counts(counts_by_year, years_sorted):
    """
    counts_by_year: dict year->count (int)
    years_sorted: iterable of years in ascending order
    Returns dict year->ema
    """
    ema = {}
    prev = None
    for y in years_sorted:
        x = counts_by_year.get(y, 0)
        if prev is None:
            s = float(x)
        else:
            s = ALPHA * float(x) + (1 - ALPHA) * prev
        ema[y] = s
        prev = s
    return ema

def main():
    print("Opening publication database:", PUBLICATION_DB_PATH)
    conn = sqlite3.connect(PUBLICATION_DB_PATH)
    cursor = conn.cursor()

    try:
        cpc_col = find_cpc_column(cursor)
    except Exception as e:
        print("ERROR detecting CPC column:", e)
        conn.close()
        sys.exit(1)

    print("Detected CPC column:", cpc_col)

    # Query filing_date and cpc column
    query = f"SELECT filing_date, {cpc_col} FROM publicationinfo;"
    try:
        cursor.execute(query)
    except Exception as e:
        print("ERROR executing query:", e)
        conn.close()
        sys.exit(1)

    rows = cursor.fetchall()
    print("Total rows fetched from publicationinfo:", len(rows))

    # Build per-code per-year counts
    counts = defaultdict(lambda: defaultdict(int))  # counts[code][year] = count
    all_years = set()
    row_idx = 0
    skipped_no_year = 0
    skipped_no_cpc = 0

    for filing_date, cpc_field in rows:
        row_idx += 1
        year = extract_year(filing_date or "")
        if year is None:
            skipped_no_year += 1
            continue
        all_years.add(year)

        codes = extract_cpc_codes(cpc_field if cpc_field is not None else "")
        if not codes:
            skipped_no_cpc += 1
            continue

        # deduplicate codes per row to avoid multiple counts for same patent-code in same row
        seen = set()
        for code in codes:
            if not code:
                continue
            if code in seen:
                continue
            seen.add(code)
            # Consider only "level 5" style codes (codes containing a slash). We'll keep all for EMA computation,
            # but final filtering will use presence of slash.
            counts[code][year] += 1

    print(f"Processed {row_idx} rows: skipped_no_year={skipped_no_year}, skipped_no_cpc={skipped_no_cpc}")
    print("Unique CPC codes found:", len(counts))

    if not counts:
        print("No CPC codes with years found. Exiting.")
        conn.close()
        # Write empty final answer
        with open(FINAL_ANSWER_PATH, "w") as fout:
            fout.write("")
        return

    min_year = min(all_years)
    max_year = max(all_years)
    years_sorted = list(range(min_year, max_year + 1))
    print("Year range in data:", min_year, "to", max_year)

    # For each code compute EMA across full year range
    code_best_year = {}  # code -> (best_year, best_ema)
    code_ema_series = {}

    for code, year_counts in counts.items():
        # compute ema
        ema_series = compute_ema_for_counts(year_counts, years_sorted)
        code_ema_series[code] = ema_series
        # find year(s) where ema is maximal
        best_year = max(ema_series.items(), key=lambda kv: (kv[1], -kv[0]))[0]  # tie-breaker: larger ema then smaller year?
        best_ema = ema_series[best_year]
        code_best_year[code] = (best_year, best_ema)

    # Filter codes that are "level 5" - interpret as codes with a slash '/'
    selected_codes = [code for code, (yr, ema) in code_best_year.items() if yr == 2022 and '/' in code]

    selected_codes_sorted = sorted(selected_codes)

    print("Number of CPC codes (level 5) whose best year is 2022:", len(selected_codes_sorted))
    # Optionally print a few examples
    for i, c in enumerate(selected_codes_sorted[:50], 1):
        by, be = code_best_year[c]
        print(f"{i}. {c}  best_year={by}  best_ema={be:.3f}")

    # Write final answers: one code per line
    try:
        with open(FINAL_ANSWER_PATH, "w") as fout:
            for code in selected_codes_sorted:
                fout.write(code + "\n")
        print("Wrote final answer to", FINAL_ANSWER_PATH)
    except Exception as e:
        print("ERROR writing final answer:", e)
    finally:
        conn.close()

if __name__ == "__main__":
    main()
