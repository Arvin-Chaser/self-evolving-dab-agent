#!/usr/bin/env python3
# solve.py
#
# This script implements the DAB task:
# "Identify the CPC technology areas with the highest exponential moving average
#  of patent filings each year (smoothing factor 0.2), and return only the CPC
#  group codes at level 5 whose best year is 2022."
#
# Files used:
# - PUBLICATION_DB_PATH: SQLite database with `publicationinfo` table (patent records)
# - CPC_DEFINITION_SQL_PATH: SQL dump containing the cpc_definition table with CPC metadata
# - FINAL_ANSWER_PATH: output path for final_answer.txt
#
# Assumptions and fallbacks (documented as required):
# - We attempt to parse the cpc_definition SQL dump to obtain a mapping: symbol -> metadata (including level and titleFull).
#   If the dump contains a column whose name includes 'level' or 'depth', we use it as the level.
# - Publication records may store CPC data in different text columns. We first try the 'cpc' column. If absent or empty,
#   we search all text columns in each row for JSON-like patterns that contain '"code":' entries or for tokens that look like CPC codes.
# - We match classification values to the exact canonical 'symbol' from the metadata whenever possible.
#   If an exact match is not found for a code extracted from publications, we attempt a deterministic fallback:
#     - Find the longest metadata symbol that is a prefix of the extracted code (e.g., metadata 'H01M10/056' is a prefix of 'H01M10/0565').
#     - This fallback is only used when the exact code is missing in metadata; it is documented here as a heuristic.
# - If metadata does not include an explicit level column, we will attempt to infer levels conservatively:
#     - We prefer metadata-driven levels; as a fallback we compute a pseudo-level based on slash-separated depth:
#       number of characters before and after slash are not used directly as "level" but the fallback level is the count of
#       hierarchical segments (e.g., 'A01B1/00' => segments ['A01B1','00'] => fallback level = 2).
#   This fallback is used only when metadata lacks explicit numeric level info.
#
# Steps implemented:
# 1. Parse CPC definition SQL to build mapping symbol -> {level, titleFull}
# 2. Connect to publication DB and read all rows from publicationinfo
# 3. For each row, extract filing year (from filing_date text); skip rows without a 4-digit year
# 4. Extract CPC codes from best candidate columns (prefer cpc); parse JSON-like structures or find "code":"..." tokens
# 5. Normalize codes and map to metadata symbols (exact match preferred; then longest-prefix fallback)
# 6. Keep only mapped canonical symbols and aggregate counts per year per canonical symbol
# 7. Restrict to canonical symbols that are at level 5 (using metadata or fallback level logic)
# 8. For each symbol, compute EMA across years with alpha=0.2 (years sorted ascending). EMA_first = value_first_year.
# 9. For each symbol, determine best year (year with maximum EMA). Tie-breaker: choose latest year.
# 10. Filter symbols whose best year == 2022
# 11. Write final_answer.txt containing one canonical CPC code per line, sorted ascending.
#
# Outputs printed to stdout: progress, counts, mapping coverage warnings, and final counts.
#
# Important: Only local files and standard python libraries are used.

import sqlite3
import re
import json
import sys
from pathlib import Path
from collections import defaultdict, Counter, OrderedDict

# Paths provided by environment of the task:
PUBLICATION_DB_PATH = "/home/m0st1ma/research/DataAgentBench/query_PATENTS/query_dataset/patent_publication.db"
CPC_DEFINITION_SQL_PATH = "/home/m0st1ma/research/DataAgentBench/query_PATENTS/query_dataset/patent_CPCDefinition.sql"
FINAL_ANSWER_PATH = "/home/m0st1ma/research/text2sql/logs/dab_agent/run_dab_code_agent_v002_loop_query_PATENTS_query1_20260610_121601/final_answer.txt"

# EMA smoothing factor:
ALPHA = 0.2
TARGET_YEAR = 2022
TARGET_LEVEL = 5

def parse_create_table_columns(sql_text, table_name):
    """
    Parse CREATE TABLE ... ( ... ) for the given table_name and return ordered list of column names.
    Returns None if not found.
    """
    pattern = re.compile(r'CREATE\s+TABLE\s+["`]?%s["`]?\s*\((.*?)\);' % re.escape(table_name), re.IGNORECASE | re.DOTALL)
    m = pattern.search(sql_text)
    if not m:
        return None
    cols_blob = m.group(1)
    cols = []
    # Split by commas but be conservative: column definitions usually are like `col` TYPE ...
    # We'll find occurrences of backtick-quoted or double-quoted or bare identifiers at start of line/segment.
    for line in re.split(r',\s*(?=[`"\w])', cols_blob):
        line = line.strip()
        if not line:
            continue
        # column name may be quoted with ` or "
        cm = re.match(r'[`"]?([A-Za-z0-9_]+)[`"]?\s+', line)
        if cm:
            cols.append(cm.group(1))
    return cols

def split_values_tuples(values_blob):
    """
    Given the text between VALUES and the ending semicolon, split into individual tuple strings.
    It will split on top-level '),(' boundaries, handling parentheses inside strings crudely.
    """
    tuples = []
    s = values_blob.strip()
    if not s:
        return tuples
    # Remove leading "VALUES" if present
    s = re.sub(r'^\s*VALUES\s*', '', s, flags=re.IGNORECASE).strip()
    # Remove trailing semicolon if present
    if s.endswith(';'):
        s = s[:-1]
    # We expect something like "(...),(...),(...)".
    parts = []
    cur = []
    depth = 0
    in_str = False
    i = 0
    while i < len(s):
        ch = s[i]
        cur.append(ch)
        if ch == "'" :
            # handle SQL single-quoted strings: in SQL, a single quote inside string is represented by two single quotes ('')
            # toggle in_str but skip doubled quotes
            if in_str:
                # if next char is also a single quote, consume it as escaped quote and remain in string
                if i+1 < len(s) and s[i+1] == "'":
                    cur.append(s[i+1])
                    i += 1  # skip the next quote as escape
                else:
                    in_str = False
            else:
                in_str = True
        elif not in_str:
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                # When depth becomes 0, we finished a tuple. Capture it.
                if depth == 0:
                    tuples.append(''.join(cur).strip())
                    cur = []
                    # Skip possible commas and whitespace following
                    # Advance i until next non-space and not comma; but loop will handle.
        i += 1
    # cleanup: sometimes there may be leftover
    if cur and ''.join(cur).strip():
        leftover = ''.join(cur).strip()
        if leftover.startswith('(') and leftover.endswith(')'):
            tuples.append(leftover)
    # Normalize tuples: remove surrounding parentheses if present
    normalized = []
    for t in tuples:
        t = t.strip()
        if t.startswith('VALUES'):
            t = re.sub(r'^\s*VALUES\s*', '', t, flags=re.IGNORECASE).strip()
        if t.startswith('(') and t.endswith(')'):
            t = t[1:-1]
        normalized.append(t)
    return normalized

def parse_sql_tuple_to_fields(t):
    """
    Given a SQL tuple body like "'a',NULL,'b''c',123", parse into Python values (strings or None or numbers as string).
    We'll return raw strings for non-NULL tokens.
    """
    vals = []
    i = 0
    cur = []
    in_str = False
    while i < len(t):
        ch = t[i]
        if in_str:
            if ch == "'":
                # check for escape ''
                if i+1 < len(t) and t[i+1] == "'":
                    cur.append("'")
                    i += 2
                    continue
                else:
                    # end of string
                    vals.append(''.join(cur))
                    cur = []
                    in_str = False
                    i += 1
                    # skip optional whitespace until comma
                    while i < len(t) and t[i].isspace():
                        i += 1
                    if i < len(t) and t[i] == ',':
                        i += 1
                    continue
            else:
                cur.append(ch)
                i += 1
                continue
        else:
            # not in string
            if ch.isspace():
                i += 1
                continue
            if ch == "'":
                in_str = True
                i += 1
                continue
            # parse until comma
            start = i
            while i < len(t) and t[i] != ',':
                i += 1
            token = t[start:i].strip()
            if token.upper() == 'NULL':
                vals.append(None)
            else:
                # return as-is (could be numeric)
                vals.append(token)
            # skip comma
            if i < len(t) and t[i] == ',':
                i += 1
            continue
    # if we ended while in_str, we push cur
    if in_str:
        vals.append(''.join(cur))
    return vals

def parse_cpc_definition(sql_path):
    """
    Parse the CPC definition SQL dump and return:
      - mapping: symbol -> metadata dict (including level if available and titleFull if available)
      - columns list for cpc_definition if available
    """
    text = Path(sql_path).read_text(encoding='utf-8', errors='ignore')
    cols = parse_create_table_columns(text, 'cpc_definition')
    mapping = {}
    found_inserts = 0
    # find all INSERT INTO cpc_definition ...; statements
    insert_pattern = re.compile(r'INSERT\s+INTO\s+["`]?cpc_definition["`]?\s*(?:\([^\)]*\))?\s*VALUES\s*(.*?);', re.IGNORECASE | re.DOTALL)
    for m in insert_pattern.finditer(text):
        found_inserts += 1
        values_blob = m.group(1)
        tuples = split_values_tuples(values_blob)
        for tup in tuples:
            fields = parse_sql_tuple_to_fields(tup)
            if not cols:
                # If we don't know columns, we won't be able to map; skip for now but try to glean symbol/title by position heuristics
                # We'll store raw tuples under a synthetic key if needed later
                continue
            if len(fields) != len(cols):
                # mismatch; skip this tuple
                continue
            row = dict(zip(cols, fields))
            symbol = None
            titleFull = None
            level = None
            # common column names to consider:
            # symbol, titleFull, title_full, title, level, depth
            for key in row:
                lk = key.lower()
                if lk == 'symbol':
                    symbol = row[key]
                if lk in ('titlefull', 'title_full', 'title'):
                    titleFull = row[key]
                if 'level' in lk or 'depth' in lk or lk == 'lvl':
                    # try convert to int
                    try:
                        if row[key] is not None:
                            level = int(row[key])
                    except Exception:
                        # sometimes it's string; try float then int
                        try:
                            level = int(float(row[key]))
                        except Exception:
                            level = None
            if symbol:
                mapping[symbol] = {'titleFull': titleFull, 'level': level}
    # As a fallback: try to find lines that explicitly encode symbol and titleFull in plain INSERT statements without knowing columns
    if not mapping:
        # attempt a simpler parse: find patterns like ('symbol','...','titleFull',level,...) heuristically
        # Search for occurrences of a token that looks like a CPC symbol inside the SQL and capture neighbouring tokens
        sym_pattern = re.compile(r"'\s*([A-H]\d{2}[A-Z]?\d*/[0-9A-Za-z]+)'\s*,\s*'([^']{0,200})'", re.IGNORECASE)
        for mm in sym_pattern.finditer(text):
            sym = mm.group(1)
            title = mm.group(2)
            if sym not in mapping:
                mapping[sym] = {'titleFull': title, 'level': None}
    return mapping, cols

def extract_codes_from_text_candidate(txt):
    """
    Given a text blob, attempt to extract CPC codes.
    Strategies:
      - If JSON-like structure with "code": "X...", use regex to pull all code values.
      - Else, find tokens matching pattern like 'A01B1/00' (capital letter, digits, letters, slash, digits/letters)
    Returns list of code strings (normalized).
    """
    if not txt:
        return []
    codes = []
    # Try to find JSON-like "code":"..."/"code": '...' occurrences
    for m in re.finditer(r'"code"\s*:\s*"([^"]+)"', txt):
        codes.append(m.group(1).strip())
    for m in re.finditer(r"'code'\s*:\s*'([^']+)'", txt):
        codes.append(m.group(1).strip())
    # Also support occurrences like "code":\n "X..." etc
    for m in re.finditer(r'"code"\s*:\s*([A-Za-z0-9/]+)', txt):
        codes.append(m.group(1).strip())
    # Generic CPC-like tokens: letter then 2 digits then optional letter+digits then slash then digits/letters (common pattern)
    # We'll be permissive but avoid false positives by requiring at least one letter, digits, slash
    for m in re.finditer(r'\b([A-H][0-9]{2}[A-Z]?[0-9A-Z]*/[0-9A-Z]+)\b', txt):
        codes.append(m.group(1).strip())
    # Deduplicate while preserving order
    seen = set()
    out = []
    for c in codes:
        if c and c not in seen:
            seen.add(c)
            out.append(c)
    return out

def find_cpc_columns(conn):
    """
    Inspect table publicationinfo and return list of text columns to search for CPC data.
    """
    cur = conn.cursor()
    cur.execute("PRAGMA table_info('publicationinfo');")
    cols_info = cur.fetchall()
    candidates = []
    for cid, name, ctype, notnull, dflt, pk in cols_info:
        # consider TEXT columns or columns named like cpc, cpc_prefix, classification
        if name.lower() in ('cpc', 'cpc_prefix', 'cpc_codes', 'cpc_data'):
            candidates.append(name)
            continue
        if ctype and ctype.upper().startswith('TEXT'):
            candidates.append(name)
    # Deduplicate preserving order
    seen = set()
    out = []
    for c in candidates:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out

def extract_year_from_text(txt):
    """
    Extract a 4-digit year from natural-language date text. Return int year or None.
    Prefer 19xx/20xx 4-digit.
    """
    if not txt:
        return None
    m = re.search(r'(?<!\d)(19|20)\d{2}(?!\d)', txt)
    if m:
        try:
            return int(m.group(0))
        except:
            return None
    # Sometimes year given as '21' for 2021 - avoid guessing two-digit years; require 4-digit
    return None

def main():
    print("Starting solve.py")
    print("PUBLICATION_DB_PATH:", PUBLICATION_DB_PATH)
    print("CPC_DEFINITION_SQL_PATH:", CPC_DEFINITION_SQL_PATH)
    print("FINAL_ANSWER_PATH:", FINAL_ANSWER_PATH)
    # 1) Parse CPC definition SQL
    print("Parsing CPC definition SQL...")
    try:
        cpc_map, cpc_def_cols = parse_cpc_definition(CPC_DEFINITION_SQL_PATH)
    except Exception as e:
        print("ERROR parsing CPC definition SQL:", e)
        cpc_map = {}
        cpc_def_cols = None
    print(f"Parsed {len(cpc_map)} CPC entries from SQL (approx). Columns known for cpc_definition: {cpc_def_cols}")

    # Determine if we have explicit level info in mapping
    any_with_level = any((v.get('level') is not None) for v in cpc_map.values())
    print("Metadata contains explicit level for some entries?:", any_with_level)

    # 2) Read publication DB
    print("Connecting to publication database...")
    conn = sqlite3.connect(PUBLICATION_DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # Determine candidate columns to search for CPC codes
    text_candidate_cols = find_cpc_columns(conn)
    print("Text candidate columns to search for CPC codes:", text_candidate_cols)

    # We'll read all rows and attempt to extract filing year and CPC codes
    cur.execute("SELECT rowid, * FROM publicationinfo;")
    rows = cur.fetchall()
    total_rows = len(rows)
    print("Total publicationinfo rows:", total_rows)

    # Aggregation structures
    # counts[(canonical_symbol, year)] = count
    counts = defaultdict(int)
    unmapped_code_counter = Counter()
    mapped_codes_set = set()
    rows_with_year = 0
    rows_with_codes = 0
    total_extracted_codes = 0

    # Precompute list of canonical symbols for prefix-fallback matching sorted by length desc
    canonical_symbols = list(cpc_map.keys())
    canonical_symbols_sorted = sorted(canonical_symbols, key=lambda s: len(s) if s else 0, reverse=True)

    for r in rows:
        # extract filing year first
        filing_date = None
        # prefer column named 'filing_date' if present
        try:
            filing_date = r['filing_date']
        except Exception:
            # any column that looks like *date may be present; fallback: look for common columns
            for k in r.keys():
                if 'filing' in k.lower() and 'date' in k.lower():
                    filing_date = r[k]
                    break
        year = extract_year_from_text(filing_date) if filing_date else None
        if year is None:
            # try publication_date sometimes they want filings per publication year but we stick to filing_date per instructions
            # we'll still attempt to get a year to avoid losing data if filing_date is missing. Use publication_date as fallback.
            pub_date = None
            try:
                pub_date = r['publication_date']
            except Exception:
                for k in r.keys():
                    if 'publication' in k.lower() and 'date' in k.lower():
                        pub_date = r[k]
                        break
            year = extract_year_from_text(pub_date) if pub_date else None
        if year is None:
            # skip this row - we cannot place it in a year bucket
            continue
        rows_with_year += 1

        # Extract CPC codes from candidate columns
        codes_found = []
        for col in text_candidate_cols:
            try:
                val = r[col]
            except Exception:
                continue
            if not val:
                continue
            # try JSON parsing if it appears to be JSON array/object
            if isinstance(val, str) and val.strip().startswith('['):
                # heuristic: look for "code" fields
                extracted = extract_codes_from_text_candidate(val)
                if extracted:
                    codes_found.extend(extracted)
                    # Prefer first successful column that yields JSON-like codes
                    break
            # if it's a plain string, try to extract code tokens
            extracted = extract_codes_from_text_candidate(str(val))
            if extracted:
                codes_found.extend(extracted)
                # do not break: continue to collect from other columns too
        if not codes_found:
            # No codes extracted for this row
            continue
        rows_with_codes += 1
        total_extracted_codes += len(codes_found)

        # For each extracted code, map to canonical symbol in cpc_map
        for code in codes_found:
            norm = code.strip()
            # common normalization: uppercase
            norm = norm.upper()
            mapped = None
            if norm in cpc_map:
                mapped = norm
            else:
                # fallback: try to find longest canonical symbol that is a prefix of norm
                for cand in canonical_symbols_sorted:
                    if cand and norm.startswith(cand):
                        mapped = cand
                        break
            if not mapped:
                # track unmapped and skip
                unmapped_code_counter[norm] += 1
                continue
            # record mapping
            mapped_codes_set.add(mapped)
            counts[(mapped, year)] += 1

    print("Rows with identifiable year:", rows_with_year)
    print("Rows with CPC codes extracted:", rows_with_codes)
    print("Total extracted code tokens:", total_extracted_codes)
    print("Unique canonical codes mapped (approx):", len(mapped_codes_set))
    print("Unmapped distinct extracted codes count:", len(unmapped_code_counter))
    if len(unmapped_code_counter) > 0:
        # show top unmapped examples
        print("Top 10 unmapped extracted codes (sample):", unmapped_code_counter.most_common(10))

    # 3) Build per-code time series of annual counts
    # Gather all years present
    years_set = set()
    for (_, yr) in counts.keys():
        years_set.add(yr)
    if not years_set:
        print("No year-count data available after mapping. Exiting with empty output.")
        Path(FINAL_ANSWER_PATH).write_text("", encoding='utf-8')
        return
    years = sorted(years_set)
    print("Years covered (sorted):", years[:5], "..." if len(years) > 5 else "")

    # Build per-code ordered dict of year->count (fill zeros for missing years)
    per_code_series = {}
    all_codes = sorted(set(k for k, _ in counts.keys()))
    for code in all_codes:
        series = OrderedDict()
        for y in years:
            series[y] = counts.get((code, y), 0)
        per_code_series[code] = series

    # 4) Filter codes to only those that are at TARGET_LEVEL according to metadata (or fallback)
    def code_level_from_metadata(code):
        entry = cpc_map.get(code)
        if not entry:
            return None
        lvl = entry.get('level')
        if lvl is not None:
            return lvl
        # fallback: infer pseudo-level by counting slash-segments (conservative)
        # e.g., 'H01M10/0565' -> segments ['H01M10','0565'] => fallback level = 2
        if '/' in code:
            return len(code.split('/'))
        # if no slash, treat as level 1
        return 1

    codes_at_target_level = []
    for code in per_code_series.keys():
        lvl = code_level_from_metadata(code)
        if lvl == TARGET_LEVEL:
            codes_at_target_level.append(code)
    print(f"Canonical codes considered: {len(per_code_series)}. Codes at target level {TARGET_LEVEL}: {len(codes_at_target_level)}")

    # If no codes at level 5 via metadata, we will exit gracefully with empty output (do not invent codes)
    if not codes_at_target_level:
        print(f"No codes identified at level {TARGET_LEVEL} based on metadata/fallback. Writing empty final answer.")
        Path(FINAL_ANSWER_PATH).write_text("", encoding='utf-8')
        return

    # 5) For each code at target level, compute EMA across years
    best_year_by_code = {}
    ema_by_code_by_year = {}
    for code in codes_at_target_level:
        series = per_code_series[code]
        ema_series = OrderedDict()
        prev_ema = None
        for y, val in series.items():
            if prev_ema is None:
                ema = float(val)
            else:
                ema = ALPHA * float(val) + (1.0 - ALPHA) * prev_ema
            ema_series[y] = ema
            prev_ema = ema
        ema_by_code_by_year[code] = ema_series
        # determine best year: year with maximum EMA; tie -> choose latest year
        max_ema = None
        best_year = None
        for y, ema_val in ema_series.items():
            if max_ema is None or ema_val > max_ema or (ema_val == max_ema and (best_year is None or y > best_year)):
                max_ema = ema_val
                best_year = y
        best_year_by_code[code] = best_year

    # 6) Filter codes whose best year == TARGET_YEAR
    final_codes = [c for c, by in best_year_by_code.items() if by == TARGET_YEAR]
    final_codes_sorted = sorted(set(final_codes))

    # Validation checks
    # - Each output code must appear in metadata mapping and be at requested level
    invalids = []
    for c in final_codes_sorted:
        if c not in cpc_map:
            invalids.append((c, "missing in metadata"))
        else:
            lvl = code_level_from_metadata(c)
            if lvl != TARGET_LEVEL:
                invalids.append((c, f"level {lvl} != {TARGET_LEVEL}"))
    if invalids:
        print("Validation: some final codes failed checks:", invalids)
        print("Proceeding to write only the valid subset.")
        final_codes_sorted = [c for c in final_codes_sorted if c in cpc_map and code_level_from_metadata(c) == TARGET_LEVEL]

    print("Total canonical codes at target level considered:", len(codes_at_target_level))
    print("Codes whose best year == %d:" % TARGET_YEAR, len(final_codes_sorted))

    # 7) Write final answer: one code per line, sorted ascending
    out_text = "\n".join(final_codes_sorted)
    out_path = Path(FINAL_ANSWER_PATH)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(out_text, encoding='utf-8')
    print("Wrote final answer to", FINAL_ANSWER_PATH)
    print("Sample of output (first 20 lines):")
    for i, line in enumerate(final_codes_sorted[:20], 1):
        print(f"{i}: {line}")
    print("Done.")

if __name__ == "__main__":
    main()
