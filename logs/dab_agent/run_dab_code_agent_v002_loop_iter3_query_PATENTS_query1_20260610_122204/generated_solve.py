#!/usr/bin/env python3
"""
solve.py

Reads local patent publication SQLite DB and CPC definition SQL dump,
computes per-CPC-code yearly counts (by filing year), computes EMA (alpha=0.2)
for each CPC canonical code, determines each code's best year (year with max EMA,
tie-breaking to the latest year), and outputs the CPC group codes at level 5
whose best year is 2022.

Files read:
- PUBLICATION_DB_PATH (SQLite): /home/m0st1ma/research/DataAgentBench/query_PATENTS/query_dataset/patent_publication.db
- CPC_DEFINITION_SQL_PATH (text SQL dump): /home/m0st1ma/research/DataAgentBench/query_PATENTS/query_dataset/patent_CPCDefinition.sql

File written:
- FINAL_ANSWER_PATH (final_answer.txt): /home/m0st1ma/research/text2sql/logs/dab_agent/run_dab_code_agent_v002_loop_iter3_query_PATENTS_query1_20260610_122204/final_answer.txt

Assumptions and fallback behavior (documented as required):
- We first attempt to parse CPC definitions from the SQL dump to obtain canonical symbol -> level and titleFull.
- If parsing yields no usable level information, we fall back to a conservative heuristic:
    * Treat any classification token that contains a '/' as a level-5 group code (conservative: groups/subgroups typically include '/').
    * This fallback is provisional and logged prominently.
- Filing year is extracted from the 'filing_date' field using a conservative regex for a 4-digit year.
  If filing_date lacks a year, publication_date is used as fallback.
- CPC codes in publication rows are attempted to be extracted by:
    1. Trying to parse the field as JSON.
    2. Regex extraction of "code":"..." patterns.
    3. Fallback regex to find tokens that look like CPC codes (contain a '/' and letters/digits).
- Only canonical codes that are present in the parsed metadata with level == 5 are guaranteed to be considered authoritative.
  If we used the heuristic fallback to treat raw codes as level-5, those are marked provisional in stdout.
- EMA is computed per canonical code across all years present in data (sorted ascending). EMA_first_year = value_first_year.
- Output is one code per line, sorted ascending, written to FINAL_ANSWER_PATH with no extra commentary.

This script prints detailed progress and warnings to stdout to aid debugging.
"""

import sqlite3
import json
import re
import os
import sys
import math
from collections import defaultdict, OrderedDict

# Paths (from the prompt)
PUBLICATION_DB_PATH = "/home/m0st1ma/research/DataAgentBench/query_PATENTS/query_dataset/patent_publication.db"
CPC_DEFINITION_SQL_PATH = "/home/m0st1ma/research/DataAgentBench/query_PATENTS/query_dataset/patent_CPCDefinition.sql"
FINAL_ANSWER_PATH = "/home/m0st1ma/research/text2sql/logs/dab_agent/run_dab_code_agent_v002_loop_iter3_query_PATENTS_query1_20260610_122204/final_answer.txt"

REQUESTED_LEVEL = 5
EMA_ALPHA = 0.2
TARGET_YEAR = 2022

# Utility functions
def safe_read_file(path):
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()
    except Exception as e:
        print(f"ERROR: Could not read file {path}: {e}", file=sys.stderr)
        return None

def tokenize_tuple_content(s):
    """
    Split a parenthesized tuple content into tokens by commas that are NOT inside quotes.
    Keeps quotes around quoted tokens for later stripping.
    """
    tokens = []
    cur = []
    in_quote = False
    quote_char = None
    i = 0
    while i < len(s):
        ch = s[i]
        if ch in ("'", '"'):
            if not in_quote:
                in_quote = True
                quote_char = ch
                cur.append(ch)
            else:
                # possible end of quote, but consider escaped quotes
                cur.append(ch)
                if ch == quote_char:
                    # check for doubled quotes (SQL escaping) e.g. '' or ""
                    next_ch = s[i+1] if i+1 < len(s) else None
                    if next_ch == quote_char:
                        # escaped, consume next as well
                        i += 1
                        cur.append(next_ch)
                    else:
                        in_quote = False
                        quote_char = None
        elif ch == ',' and not in_quote:
            token = ''.join(cur).strip()
            tokens.append(token)
            cur = []
        else:
            cur.append(ch)
        i += 1
    # last token
    last = ''.join(cur).strip()
    if last:
        tokens.append(last)
    return tokens

def strip_quotes(s):
    s = s.strip()
    if len(s) >= 2 and ((s[0] == s[-1] and s[0] in ("'", '"'))):
        # remove surrounding quotes
        inner = s[1:-1]
        # handle common SQL escaping of single quotes by doubling
        inner = inner.replace("''", "'").replace('""', '"')
        return inner
    return s

def extract_potential_code_from_token(tok):
    """
    Return token string if it looks like a CPC symbol (contains a slash and letters/digits),
    else None.
    """
    t = strip_quotes(tok)
    # Conservative pattern: contains letter(s) followed by digits and a '/' then digits/letters
    if '/' in t:
        # remove surrounding whitespace
        t2 = t.strip()
        # Filter out obviously long descriptive strings by length threshold for a code
        if 2 <= len(t2) <= 50:
            # Accept if has at least one letter and one digit
            if re.search(r'[A-Za-z]', t2) and re.search(r'\d', t2):
                return t2
    return None

def parse_cpc_definition_sql(path):
    """
    Parse the CPC definition SQL dump for tuples that include symbol and level.
    Returns mapping: symbol -> {'level': int or None, 'titleFull': str or None}
    The parser is robust/heuristic: looks for parenthesized tuples and tokens that look like symbols and levels.
    """
    text = safe_read_file(path)
    if text is None:
        print("CPC definition SQL file not readable; returning empty mapping.", file=sys.stderr)
        return {}

    # Attempt to find INSERT INTO ... VALUES blocks; fallback: scan all parenthesized tuples
    # We'll gather all parenthesized chunks that look like tuples with at least one token containing a '/'
    tuples = re.findall(r'\([^()]{1,4000}\)', text, flags=re.DOTALL)
    mapping = {}
    found_count = 0
    for tup in tuples:
        content = tup[1:-1]  # strip parentheses
        tokens = tokenize_tuple_content(content)
        # find a token that looks like a CPC symbol
        symbol = None
        level = None
        title = None
        for tok in tokens:
            candidate = extract_potential_code_from_token(tok)
            if candidate:
                symbol = candidate
                break
        # find integer token for level (1..10)
        for tok in tokens:
            t = strip_quotes(tok)
            if re.fullmatch(r'\d{1,2}', t):
                try:
                    lv = int(t)
                    if 1 <= lv <= 10:
                        level = lv
                        break
                except:
                    pass
        # find a long quoted token as title (heuristic: >10 chars)
        for tok in tokens:
            if tok and (tok[0] in ("'", '"') or tok[-1] in ("'", '"')):
                t = strip_quotes(tok)
                if len(t) >= 8:
                    # avoid picking the symbol itself
                    if t != symbol:
                        title = t
                        break
        if symbol:
            found_count += 1
            mapping.setdefault(symbol, {})
            if 'level' not in mapping[symbol]:
                mapping[symbol]['level'] = level
            if 'titleFull' not in mapping[symbol]:
                mapping[symbol]['titleFull'] = title
    print(f"Parsed CPC definition SQL: found {found_count} tuples with potential CPC symbols; unique symbols: {len(mapping)}")
    # Clean mapping entries: ensure each has keys
    cleaned = {}
    for sym, info in mapping.items():
        cleaned[sym] = {'level': info.get('level'), 'titleFull': info.get('titleFull')}
    return cleaned

def extract_year_from_text(s):
    if not s:
        return None
    # search for 4-digit year between 1800 and 2100
    m = re.search(r'(18|19|20)\d{2}', s)
    if m:
        try:
            y = int(m.group(0))
            return y
        except:
            return None
    return None

def extract_codes_from_cpc_field(raw):
    """
    Attempt to extract CPC code tokens from a publicationinfo.cpc-like field.
    Strategies:
      1) Try to parse JSON directly (if field is a JSON array of objects with 'code' keys)
      2) Regex find "code":"..."/'code': '...' patterns
      3) Regex fallback: find tokens with pattern of letters/digits and a '/' inside.
    Returns list of normalized code strings.
    """
    if raw is None:
        return []
    s = raw.strip()
    results = []
    # Strategy 1: JSON parse
    if (s.startswith('[') or s.startswith('{')) and ('"' in s or "'" in s):
        try:
            # try to fix common single-quote JSON by replacing single quotes with double quotes when safe
            try_s = s
            # If it looks like Python repr with single quotes, attempt ast.literal_eval?
            # But to be conservative, try json.loads first
            parsed = json.loads(try_s)
            if isinstance(parsed, list):
                for item in parsed:
                    if isinstance(item, dict):
                        code = item.get('code') or item.get('symbol') or item.get('cpc')
                        if code:
                            results.append(str(code).strip())
                    elif isinstance(item, str):
                        results.append(item.strip())
            elif isinstance(parsed, dict):
                # maybe dict with nested
                for k, v in parsed.items():
                    if isinstance(v, str) and '/' in v:
                        results.append(v.strip())
        except Exception:
            # try a looser approach: replace single quotes with double quotes and try again
            try:
                alt = s.replace("'", '"')
                parsed = json.loads(alt)
                if isinstance(parsed, list):
                    for item in parsed:
                        if isinstance(item, dict):
                            code = item.get('code') or item.get('symbol') or item.get('cpc')
                            if code:
                                results.append(str(code).strip())
                elif isinstance(parsed, dict):
                    for k, v in parsed.items():
                        if isinstance(v, str) and '/' in v:
                            results.append(v.strip())
            except Exception:
                pass
    # Strategy 2: regex "code"\s*:\s*"..."
    for m in re.finditer(r'["\']code["\']\s*:\s*["\']([^"\']+)["\']', s, flags=re.IGNORECASE):
        results.append(m.group(1).strip())
    # Strategy 3: generic token regex: find sequences with letters/digits and a '/' and digit after slash
    if not results:
        for m in re.finditer(r'([A-Z][A-Z0-9]{0,4}\d{1,4}/[0-9A-Z]+)', s, flags=re.IGNORECASE):
            results.append(m.group(1).strip())
    # Deduplicate and normalize uppercase
    results_norm = []
    seen = set()
    for r in results:
        rr = r.strip()
        if rr:
            rr_up = rr.upper()
            if rr_up not in seen:
                seen.add(rr_up)
                results_norm.append(rr_up)
    return results_norm

def main():
    print("Starting solve.py")
    print(f"PUBLICATION_DB_PATH = {PUBLICATION_DB_PATH}")
    print(f"CPC_DEFINITION_SQL_PATH = {CPC_DEFINITION_SQL_PATH}")
    print(f"FINAL_ANSWER_PATH = {FINAL_ANSWER_PATH}")
    # 1) Parse CPC definition SQL to build mapping symbol -> {level, titleFull}
    print("Parsing CPC definition SQL...")
    cpc_def = parse_cpc_definition_sql(CPC_DEFINITION_SQL_PATH)
    mapped_levels_count = sum(1 for v in cpc_def.values() if v.get('level') is not None)
    print(f"CPC definitions with explicit levels parsed: {mapped_levels_count} / {len(cpc_def)}")
    if len(cpc_def) == 0 or mapped_levels_count == 0:
        print("WARNING: CPC definition parsing yielded no explicit level info. Will use conservative fallback heuristics.", file=sys.stderr)
        fallback_mode = True
    else:
        fallback_mode = False

    # 2) Connect to publication DB and read publicationinfo rows
    if not os.path.exists(PUBLICATION_DB_PATH):
        print(f"ERROR: Publication DB not found at {PUBLICATION_DB_PATH}", file=sys.stderr)
        # Write empty final answer and exit non-zero
        try:
            os.makedirs(os.path.dirname(FINAL_ANSWER_PATH), exist_ok=True)
            with open(FINAL_ANSWER_PATH, "w", encoding="utf-8") as fo:
                fo.write("")
            print(f"Wrote empty final answer to {FINAL_ANSWER_PATH}")
        except Exception as e:
            print(f"Failed to write empty final answer: {e}", file=sys.stderr)
        sys.exit(1)

    conn = None
    try:
        conn = sqlite3.connect(PUBLICATION_DB_PATH)
        cur = conn.cursor()
        # Check if publicationinfo exists
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='publicationinfo'")
        if not cur.fetchone():
            print("ERROR: Table 'publicationinfo' not found in publication DB.", file=sys.stderr)
            sys.exit(1)
        # Fetch rows: select rowid, cpc, filing_date, publication_date
        cur.execute("PRAGMA table_info(publicationinfo)")
        cols = [r[1] for r in cur.fetchall()]
        print(f"publicationinfo columns: {cols}")
        # We'll query cpc (or cpc_prefix) and filing_date/publication_date
        fetch_cols = []
        for candidate in ('cpc', 'cpc_prefix', 'cpc_classification'):
            if candidate in cols:
                fetch_cols.append(candidate)
                break
        # Use 'cpc' as primary if present
        if 'cpc' in cols:
            cpc_col = 'cpc'
        elif 'cpc_prefix' in cols:
            cpc_col = 'cpc_prefix'
        else:
            # fallback to column named 'cpc' even if not declared; will raise later
            cpc_col = 'cpc'
        date_col = 'filing_date' if 'filing_date' in cols else ('publication_date' if 'publication_date' in cols else None)
        if date_col is None:
            print("ERROR: Neither 'filing_date' nor 'publication_date' found in publicationinfo.", file=sys.stderr)
            sys.exit(1)
        sql = f"SELECT rowid, {cpc_col}, filing_date, publication_date FROM publicationinfo"
        cur.execute(sql)
        rows = cur.fetchall()
        print(f"Fetched {len(rows)} rows from publicationinfo.")
    except Exception as e:
        print(f"ERROR reading publication DB: {e}", file=sys.stderr)
        if conn:
            conn.close()
        sys.exit(1)

    # 3) Process rows: extract year and codes, map to canonical symbols where possible
    year_code_counts = defaultdict(lambda: defaultdict(int))  # year -> code -> count
    raw_records = 0
    mapped_records = 0
    unmapped_records = 0
    unmapped_code_examples = {}
    canonical_codes_seen = set()
    for row in rows:
        raw_records += 1
        rowid, cpc_field, filing_date_field, publication_date_field = row
        # Extract year from filing_date first, else publication_date
        y = extract_year_from_text(filing_date_field) if filing_date_field else None
        if y is None:
            y = extract_year_from_text(publication_date_field) if publication_date_field else None
        if y is None:
            # skip this record
            unmapped_records += 1
            if len(unmapped_code_examples) < 5:
                unmapped_code_examples[rowid] = ("no_date", filing_date_field, publication_date_field)
            continue
        codes = extract_codes_from_cpc_field(cpc_field)
        if not codes:
            unmapped_records += 1
            if len(unmapped_code_examples) < 5:
                unmapped_code_examples[rowid] = ("no_codes", cpc_field)
            continue
        any_mapped_this_row = False
        for code in codes:
            canon = None
            # Attempt exact match to cpc_def mapping
            if code in cpc_def:
                canon = code
            else:
                # Try normalization variants
                code_norm = code.strip().upper()
                if code_norm in cpc_def:
                    canon = code_norm
                else:
                    # Try to find a mapping key that exactly equals the left part up to some canonical length
                    # (This is a mild, cautious attempt to match codes that differ in leading zeros etc.)
                    # We will not aggressively infer hierarchy here.
                    # Check direct prefix matches: choose the longest mapping key that is a prefix of code_norm
                    candidates = [k for k in cpc_def.keys() if code_norm.startswith(k)]
                    if candidates:
                        # pick the longest candidate (most specific)
                        candidates.sort(key=lambda x: -len(x))
                        canon = candidates[0]
            if canon is None:
                # If fallback mode and code contains '/', treat as provisional level-5 code
                if fallback_mode and '/' in code:
                    canon = code  # provisional canonical
                    # mark as provisional in cpc_def with level == REQUESTED_LEVEL
                    if canon not in cpc_def:
                        cpc_def[canon] = {'level': REQUESTED_LEVEL, 'titleFull': None}
                else:
                    # cannot map; skip counting this code
                    unmapped_records += 1
                    if len(unmapped_code_examples) < 10:
                        unmapped_code_examples[rowid] = ("unmapped_code", code)
                    continue
            # record
            year_code_counts[y][canon] += 1
            canonical_codes_seen.add(canon)
            any_mapped_this_row = True
            mapped_records += 1
        # end codes loop
    # end rows loop

    print(f"Total publication rows processed: {raw_records}")
    print(f"Total code occurrences mapped to canonical symbols: {mapped_records}")
    print(f"Total rows with no usable date or codes (approx): {unmapped_records}")
    if unmapped_code_examples:
        print("Examples of unmapped rows/codes:", unmapped_code_examples)

    # 4) Prepare per-code time series (years sorted)
    # Collect sorted list of all years observed
    all_years = sorted(year_code_counts.keys())
    if not all_years:
        print("No year-coded data available. Writing empty final answer.", file=sys.stderr)
        # write empty final answer
        try:
            os.makedirs(os.path.dirname(FINAL_ANSWER_PATH), exist_ok=True)
            with open(FINAL_ANSWER_PATH, "w", encoding="utf-8") as fo:
                fo.write("")
            print(f"Wrote empty final answer to {FINAL_ANSWER_PATH}")
        except Exception as e:
            print(f"Failed to write empty final answer: {e}", file=sys.stderr)
        if conn:
            conn.close()
        sys.exit(0)

    print(f"Years observed: {all_years}")

    # Build for each canonical code a list of values aligned to all_years
    code_time_series = {}
    for code in sorted(canonical_codes_seen):
        vals = []
        for y in all_years:
            vals.append(year_code_counts[y].get(code, 0))
        code_time_series[code] = (all_years, vals)

    # 5) Compute EMA per code across years
    code_ema_by_year = {}  # code -> list of ema values aligned to years
    code_best_year = {}    # code -> (best_year, best_ema)
    for code, (years, vals) in code_time_series.items():
        emas = []
        ema_prev = None
        for i, v in enumerate(vals):
            if i == 0:
                ema = float(v)
            else:
                ema = EMA_ALPHA * float(v) + (1.0 - EMA_ALPHA) * ema_prev
            emas.append(ema)
            ema_prev = ema
        code_ema_by_year[code] = (years, emas)
        # find best year (max EMA); tie-breaker latest year
        max_ema = max(emas) if emas else None
        if max_ema is None:
            continue
        # collect indices with max
        indices = [i for i, e in enumerate(emas) if abs(e - max_ema) < 1e-12]
        # tie-break: pick latest year -> max index
        best_idx = max(indices)
        best_year = years[best_idx]
        code_best_year[code] = (best_year, max_ema)

    print(f"Computed EMA for {len(code_ema_by_year)} canonical codes.")

    # 6) Filter codes whose best year == TARGET_YEAR and are at requested level == REQUESTED_LEVEL
    selected_codes = []
    provisional_included = False
    not_at_level = []
    for code, (best_year, best_ema) in code_best_year.items():
        if best_year != TARGET_YEAR:
            continue
        info = cpc_def.get(code)
        if info is None:
            # not in definitions; skip unless fallback mode allowed and we marked it earlier
            continue
        level = info.get('level')
        if level is None:
            # if fallback_mode and we inserted provisional level earlier, accept
            if fallback_mode and code in cpc_def and cpc_def[code].get('level') == REQUESTED_LEVEL:
                selected_codes.append(code)
                provisional_included = True
            else:
                not_at_level.append((code, level))
        else:
            if level == REQUESTED_LEVEL:
                selected_codes.append(code)
            else:
                not_at_level.append((code, level))

    print(f"Total canonical codes considered: {len(canonical_codes_seen)}")
    print(f"Codes with best year == {TARGET_YEAR}: {sum(1 for c in code_best_year if code_best_year[c][0]==TARGET_YEAR)}")
    print(f"Codes selected at level {REQUESTED_LEVEL} with best year == {TARGET_YEAR}: {len(selected_codes)}")
    if provisional_included:
        print("WARNING: Some selected codes were included based on fallback heuristic (provisional).", file=sys.stderr)
    if not_at_level:
        print(f"Codes that had best year {TARGET_YEAR} but are not at level {REQUESTED_LEVEL} (sample up to 10): {not_at_level[:10]}")

    # Ensure uniqueness and deterministic order
    selected_codes = sorted(set(selected_codes))

    # Validation checks per S8:
    # - Each output code must appear in metadata mapping and be at requested level (unless provisional fallback used)
    invalid_codes = []
    for code in selected_codes:
        info = cpc_def.get(code)
        if info is None:
            invalid_codes.append(code)
        else:
            lvl = info.get('level')
            if lvl is None and not (fallback_mode and info.get('level') == REQUESTED_LEVEL):
                # if level is None and fallback_mode wasn't used to set it, mark invalid
                invalid_codes.append(code)
            elif lvl is not None and lvl != REQUESTED_LEVEL:
                invalid_codes.append(code)
    if invalid_codes:
        print("WARNING: Some selected codes failed validation and will be removed:", invalid_codes, file=sys.stderr)
        selected_codes = [c for c in selected_codes if c not in invalid_codes]

    # Final write: one code per line, sorted
    try:
        os.makedirs(os.path.dirname(FINAL_ANSWER_PATH), exist_ok=True)
        with open(FINAL_ANSWER_PATH, "w", encoding="utf-8") as fo:
            for code in selected_codes:
                fo.write(code + "\n")
        print(f"Wrote {len(selected_codes)} codes to {FINAL_ANSWER_PATH}")
    except Exception as e:
        print(f"ERROR: Failed to write final answer to {FINAL_ANSWER_PATH}: {e}", file=sys.stderr)
        if conn:
            conn.close()
        sys.exit(1)

    # Print summary statistics
    total_codes_considered = len(canonical_codes_seen)
    total_mapped_defs = len([k for k,v in cpc_def.items() if v.get('level') is not None])
    print("Summary:")
    print(f"  Total publication rows processed: {raw_records}")
    print(f"  Total code occurrences mapped: {mapped_records}")
    print(f"  Distinct canonical codes seen in data: {total_codes_considered}")
    print(f"  Distinct codes in CPC definitions with levels: {total_mapped_defs}")
    print(f"  Selected codes (level {REQUESTED_LEVEL}, best year {TARGET_YEAR}): {len(selected_codes)}")
    if len(selected_codes) == 0:
        print("NOTE: No codes selected. This may be due to no codes having best year == target or no definitions at requested level.", file=sys.stderr)

    if conn:
        conn.close()

if __name__ == "__main__":
    main()
