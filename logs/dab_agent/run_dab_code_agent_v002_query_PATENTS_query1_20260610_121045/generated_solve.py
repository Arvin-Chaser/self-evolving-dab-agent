#!/usr/bin/env python3
"""
solve.py for DAB query:
Identify the CPC technology areas with the highest exponential moving average (EMA)
of patent filings each year (smoothing factor 0.2), and return only the CPC group
codes at level 5 whose best year is 2022.

Files used:
- PUBLICATION_DB_PATH: SQLite DB with table publicationinfo (patent records).
- CPC_DEFINITION_SQL_PATH: SQL dump containing cpc_definition table (symbols, levels, parents, titles).
Final answer will be written to FINAL_ANSWER_PATH (one code per line).

Assumptions & fallback behavior (documented here):
- We prefer metadata from CPC_DEFINITION_SQL_PATH to determine symbol->level and parent relations.
- If level/parent metadata is not available for a symbol, we attempt conservative matching:
  1) If a raw CPC code exactly matches a symbol from metadata, we use that.
  2) If not, as a fallback we try to extract codes from the publicationinfo cpc fields using JSON parsing,
     then by searching for any known symbol substrings in the text (metadata-driven).
  3) If still unmapped, we may try a loose regex to extract CPC-like tokens, but these will be included only if
     we can map them to metadata; otherwise they are treated as unmapped and reported.
- EMA initialization: EMA_first_year = count_first_year (as required).
- Tie-breaking for best year (multiple years with same EMA): choose the latest year (deterministic).

This script follows the required S1..S8 rules from the task instructions.
"""
import sqlite3
import json
import re
import sys
from pathlib import Path
from collections import defaultdict, Counter, OrderedDict

# Local paths provided by the environment
DAB_ROOT = "/home/m0st1ma/research/DataAgentBench"
CASE_DIR = "/home/m0st1ma/research/DataAgentBench/query_PATENTS/query1"
PUBLICATION_DB_PATH = "/home/m0st1ma/research/DataAgentBench/query_PATENTS/query_dataset/patent_publication.db"
CPC_DEFINITION_SQL_PATH = "/home/m0st1ma/research/DataAgentBench/query_PATENTS/query_dataset/patent_CPCDefinition.sql"
FINAL_ANSWER_PATH = "/home/m0st1ma/research/text2sql/logs/dab_agent/run_dab_code_agent_v002_query_PATENTS_query1_20260610_121045/final_answer.txt"

ALPHA = 0.2  # smoothing factor for EMA
TARGET_YEAR = 2022
TARGET_LEVEL = 5

def parse_cpc_definition(sql_text):
    """
    Parse the CPC definition SQL dump to extract:
    - column order for cpc_definition table (if CREATE TABLE present)
    - all INSERT tuples for cpc_definition and map symbols to their columns
    We return:
      - defs: dict symbol -> dict of column->value (raw strings)
      - colnames: list of column names discovered (may be empty if not found)
    """
    defs = {}  # symbol -> dict of fields
    colnames = []

    # Try to find CREATE TABLE definition for cpc_definition to get column order
    create_match = re.search(r'CREATE TABLE\s+"?cpc_definition"?\s*\((.*?)\)\s*;', sql_text, re.S | re.I)
    if create_match:
        cols_blob = create_match.group(1)
        # Split by commas that start new column definitions (naive but works for typical SQL dumps)
        # We'll extract column names by regex of first token (possibly quoted)
        cols = []
        for line in re.split(r',\s*(?=(?:[^"\']|"[^"]*"|\'[^\']*\')*$)', cols_blob):
            line = line.strip()
            if not line:
                continue
            m = re.match(r'["\']?([A-Za-z0-9_]+)["\']?\s+', line)
            if m:
                cols.append(m.group(1))
        colnames = cols

    # Find all INSERT INTO cpc_definition ... VALUES (...),(...),...;
    insert_iters = re.finditer(r'INSERT INTO\s+"?cpc_definition"?\s*(?:\([^\)]*\))?\s*VALUES\s*(.*?);', sql_text, re.S | re.I)
    tuples_found = 0
    for m in insert_iters:
        values_blob = m.group(1).strip()
        # Find all tuples: sequences of (....) possibly separated by commas.
        # We'll parse by scanning characters to collect balanced parentheses content.
        i = 0
        n = len(values_blob)
        while i < n:
            # skip whitespace and commas
            while i < n and values_blob[i] in " \r\n\t,":
                i += 1
            if i >= n:
                break
            if values_blob[i] != '(':
                # unexpected, try to skip until next '('
                i = values_blob.find('(', i)
                if i == -1:
                    break
            depth = 0
            j = i
            while j < n:
                if values_blob[j] == '(':
                    depth += 1
                elif values_blob[j] == ')':
                    depth -= 1
                    if depth == 0:
                        break
                j += 1
            if j >= n:
                break
            tuple_text = values_blob[i+1:j]
            tuples_found += 1
            # Parse tuple_text into fields respecting single quotes
            fields = []
            cur = ''
            in_quote = False
            escape = False
            for ch in tuple_text:
                if in_quote:
                    if escape:
                        cur += ch
                        escape = False
                    elif ch == '\\':
                        escape = True
                    elif ch == "'":
                        in_quote = False
                        # keep the quote-delimited string as a single field (without quotes)
                    else:
                        cur += ch
                else:
                    if ch == "'":
                        in_quote = True
                    elif ch == ',':
                        fields.append(cur.strip())
                        cur = ''
                    else:
                        cur += ch
            if cur != '' or tuple_text.endswith(','):
                fields.append(cur.strip())
            # Normalize fields: if field was quoted it is already captured without outer quotes;
            # but numeric or NULL kept as is.
            norm_fields = []
            for f in fields:
                f = f.strip()
                if len(f) >= 2 and f[0] == "'" and f[-1] == "'":
                    # remove bounding quotes and unescape single quotes
                    inner = f[1:-1].replace("''", "'").replace("\\'", "'")
                    norm_fields.append(inner)
                else:
                    # could be NULL or number
                    if f.upper() == 'NULL':
                        norm_fields.append(None)
                    else:
                        norm_fields.append(f)
            # Map to colnames if available
            entry = {}
            if colnames and len(colnames) >= len(norm_fields):
                for idx, val in enumerate(norm_fields):
                    entry[colnames[idx]] = val
            else:
                # fallback mapping using common column name heuristics
                # Guess symbol is first, title/titleFull near, level maybe contains digits
                # We'll assign by positions: 0->symbol, 1->title (if present), last->level if numeric
                if len(norm_fields) >= 1:
                    entry['symbol'] = norm_fields[0]
                if len(norm_fields) >= 2:
                    entry['titleFull'] = norm_fields[1]
                # try to find numeric level in any field
                lvl = None
                for f in norm_fields[::-1]:
                    if f is None:
                        continue
                    if re.fullmatch(r'\d+', str(f)):
                        lvl = int(f)
                        break
                if lvl is not None:
                    entry['level'] = lvl
            # store if we have a symbol
            sym = entry.get('symbol') or entry.get('symbol'.lower())
            if sym:
                defs[sym] = entry
            i = j + 1

    # If we didn't find any inserts (unlikely), try to find lines like VALUES('A01B',...);
    if not defs:
        # fallback regex for tuples: find ('symbol', ... , level)
        tuple_matches = re.finditer(r"\('([^']+)'\s*,\s*'([^']*)'[^)]*?(\d+)\s*\)", sql_text, re.S)
        for tm in tuple_matches:
            sym = tm.group(1)
            title = tm.group(2)
            lvl = int(tm.group(3))
            defs[sym] = {'symbol': sym, 'titleFull': title, 'level': lvl}

    return defs, colnames, tuples_found

def build_parent_level_mappings(defs):
    """
    From defs (symbol -> fields), try to extract:
      - level_map: symbol -> int level (if available)
      - parent_map: symbol -> parent_symbol (if available)
      - title_map: symbol -> titleFull (if available)
    Heuristics are applied to find likely parent column names.
    """
    level_map = {}
    parent_map = {}
    title_map = {}

    # Candidate keys
    candidates = set()
    for v in defs.values():
        candidates.update(v.keys())

    # heuristics for column names
    level_keys = [k for k in candidates if k.lower() in ('level', 'lvl', 'level_id', 'depth')]
    parent_keys = [k for k in candidates if k.lower() in ('parent', 'parent_symbol', 'parentid', 'parent_id')]
    title_keys = [k for k in candidates if k.lower() in ('titlefull', 'title_full', 'title', 'titleFull')]

    for sym, fields in defs.items():
        # level
        lvl = None
        for lk in level_keys:
            val = fields.get(lk)
            if val is None:
                continue
            try:
                lvl = int(val)
                break
            except:
                # sometimes level is string numeric
                try:
                    lvl = int(str(val))
                    break
                except:
                    pass
        if lvl is not None:
            level_map[sym] = lvl
        # parent
        parent = None
        for pk in parent_keys:
            pval = fields.get(pk)
            if pval:
                parent = pval
                break
        if parent:
            parent_map[sym] = parent
        # title
        for tk in title_keys:
            tval = fields.get(tk)
            if tval:
                title_map[sym] = tval
                break
    return level_map, parent_map, title_map

def climb_to_level(symbol, level_map, parent_map, max_steps=100):
    """
    Given a symbol, climb parents until we find a node with level == TARGET_LEVEL.
    Returns the symbol at TARGET_LEVEL, or None if not reachable.
    """
    cur = symbol
    steps = 0
    visited = set()
    while cur and steps < max_steps and cur not in visited:
        visited.add(cur)
        steps += 1
        if cur in level_map and level_map[cur] == TARGET_LEVEL:
            return cur
        # climb parent
        cur = parent_map.get(cur)
    return None

def extract_year_from_text(text):
    if not text:
        return None
    # find 4-digit year between 1800 and 2099
    m = re.search(r'(18|19|20)\d{2}', text)
    if m:
        return int(m.group(0))
    return None

def split_tuple_fields_into_codes_from_json_or_text(blob, known_symbols_set):
    """
    Attempt to extract CPC codes from a blob of text.
    Strategy:
     - If blob looks like JSON array, try json.loads and extract 'code' values.
     - Else, search for known symbols (from metadata) as substrings (exact match).
     - Else, as a last resort, use a regex to pull CPC-like tokens.
    Returns list of codes (unique).
    """
    codes = []
    if not blob or not blob.strip():
        return codes
    blob_str = blob.strip()
    # Try JSON
    try:
        parsed = json.loads(blob_str)
        if isinstance(parsed, list):
            for entry in parsed:
                if isinstance(entry, dict):
                    c = entry.get('code') or entry.get('symbol')
                    if c:
                        codes.append(c.strip())
            if codes:
                return list(OrderedDict.fromkeys(codes))
    except Exception:
        pass
    # Search for known symbols as substrings (metadata-driven)
    found = set()
    # To avoid extremely slow checks when known_symbols_set is large, we do greedy: check tokens and known symbols by longest-first
    # Build ordered list of known symbols sorted by length desc (cache)
    for sym in sorted(known_symbols_set, key=lambda s: -len(s)):
        if sym in blob_str:
            found.add(sym)
    if found:
        # maintain deterministic order
        return sorted(found)
    # Fallback regex to capture patterns like 'H01M10/0565' or 'C01B33/00' or 'B29L2031/3017'
    regex = re.findall(r'[A-Z]\d{2}[A-Z](?:[0-9A-Z/]+)?', blob_str)
    if regex:
        # normalize uniq
        return list(OrderedDict.fromkeys(regex))
    return []

def main():
    print("Starting solve.py")
    print("PUBLICATION_DB_PATH:", PUBLICATION_DB_PATH)
    print("CPC_DEFINITION_SQL_PATH:", CPC_DEFINITION_SQL_PATH)
    print("FINAL_ANSWER_PATH:", FINAL_ANSWER_PATH)
    # Read CPC definition SQL
    sql_path = Path(CPC_DEFINITION_SQL_PATH)
    if not sql_path.exists():
        print("ERROR: CPC definition SQL file not found at", CPC_DEFINITION_SQL_PATH, file=sys.stderr)
        return
    sql_text = sql_path.read_text(encoding='utf-8', errors='ignore')
    print("Parsing CPC definition SQL...")
    defs, colnames, tuples_found = parse_cpc_definition(sql_text)
    print(f"Parsed {len(defs)} definition rows (tuples found in INSERTs: {tuples_found}).")
    level_map, parent_map, title_map = build_parent_level_mappings(defs)
    print(f"Level map size: {len(level_map)}; Parent map size: {len(parent_map)}; Titles: {len(title_map)}")
    # Build known symbol set (for substring detection)
    known_symbols = set(defs.keys())

    # If we don't have explicit level info, warn and plan fallback
    if not level_map:
        print("WARNING: No explicit 'level' metadata found in cpc_definition. Will attempt heuristics and fallbacks.", file=sys.stderr)

    # Connect to publication DB and inspect columns
    pub_db = Path(PUBLICATION_DB_PATH)
    if not pub_db.exists():
        print("ERROR: publication DB not found at", PUBLICATION_DB_PATH, file=sys.stderr)
        return
    conn = sqlite3.connect(PUBLICATION_DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    # inspect table columns
    cur.execute("PRAGMA table_info('publicationinfo');")
    table_info = cur.fetchall()
    colnames_pub = [r['name'] for r in table_info]
    print("Publication table columns:", colnames_pub)
    # choose CPC-like columns
    cpc_columns = [c for c in colnames_pub if 'cpc' in c.lower()]
    if not cpc_columns:
        # fallback to 'cpc' column specifically
        if 'cpc' in colnames_pub:
            cpc_columns = ['cpc']
    print("Using CPC columns:", cpc_columns)
    # prefer filing_date column for filings per year; fallback use publication_date
    date_col = None
    if 'filing_date' in colnames_pub:
        date_col = 'filing_date'
    elif 'publication_date' in colnames_pub:
        date_col = 'publication_date'
    else:
        date_col = None
    print("Using date column for year extraction:", date_col)

    # Query all rows from publicationinfo (streaming)
    query_cols = []
    if date_col:
        query_cols.append(date_col)
    for c in cpc_columns:
        if c not in query_cols:
            query_cols.append(c)
    select_sql = "SELECT rowid, " + ", ".join(query_cols) + " FROM publicationinfo"
    cur.execute(select_sql)
    rows = cur.fetchall()
    print("Total publicationinfo rows fetched:", len(rows))
    # Aggregate counts per level-5 code per year
    counts = defaultdict(lambda: defaultdict(int))  # counts[code][year] = count
    unmapped_rows = 0
    raw_codes_seen = set()
    mapped_codes_set = set()
    rows_with_any_cpc = 0

    for r in rows:
        # extract year
        year = None
        if date_col:
            year = extract_year_from_text(r[date_col])
        if year is None and 'publication_date' in colnames_pub and date_col != 'publication_date':
            year = extract_year_from_text(r['publication_date'])
        if year is None:
            # cannot determine year -> skip
            continue
        # gather codes from cpc columns
        codes_in_row = []
        for ccol in cpc_columns:
            blob = r[ccol]
            if not blob:
                continue
            extracted = split_tuple_fields_into_codes_from_json_or_text(blob, known_symbols)
            for code in extracted:
                if code:
                    codes_in_row.append(code.strip())
        if codes_in_row:
            rows_with_any_cpc += 1
        # Map each raw code to level-5 canonical symbol using metadata
        mapped_any = False
        for raw_code in codes_in_row:
            raw_codes_seen.add(raw_code)
            # direct metadata match?
            if raw_code in level_map and level_map.get(raw_code) == TARGET_LEVEL:
                # already at level 5
                counts[raw_code][year] += 1
                mapped_codes_set.add(raw_code)
                mapped_any = True
                continue
            # If raw_code exists in defs but different level, try climbing parent chain
            if raw_code in defs:
                target = climb_to_level(raw_code, level_map, parent_map)
                if target:
                    counts[target][year] += 1
                    mapped_codes_set.add(target)
                    mapped_any = True
                    continue
            # If raw_code not in defs, try to find the longest known symbol that is a prefix of raw_code
            # This is a conservative fallback: only use if it yields a known symbol in defs.
            candidate = None
            for sym in sorted(known_symbols, key=lambda s: -len(s)):
                if raw_code.startswith(sym):
                    candidate = sym
                    break
            if candidate:
                # attempt to climb candidate to level 5
                if candidate in level_map and level_map[candidate] == TARGET_LEVEL:
                    counts[candidate][year] += 1
                    mapped_codes_set.add(candidate)
                    mapped_any = True
                    continue
                targ = climb_to_level(candidate, level_map, parent_map)
                if targ:
                    counts[targ][year] += 1
                    mapped_codes_set.add(targ)
                    mapped_any = True
                    continue
            # last resort: if raw_code itself contains exact known symbol substring, map that
            mapped = False
            for sym in sorted(known_symbols, key=lambda s: -len(s)):
                if sym in raw_code:
                    targ = sym
                    if targ in level_map and level_map[targ] == TARGET_LEVEL:
                        counts[targ][year] += 1
                        mapped_codes_set.add(targ)
                        mapped_any = True
                        mapped = True
                        break
                    else:
                        targ2 = climb_to_level(targ, level_map, parent_map)
                        if targ2:
                            counts[targ2][year] += 1
                            mapped_codes_set.add(targ2)
                            mapped_any = True
                            mapped = True
                            break
            if mapped:
                continue
            # If reached here, the raw code could not be mapped to level-5 canonical symbol
            # We'll skip counting it but register that mapping was incomplete.
        if not mapped_any:
            unmapped_rows += 1

    total_raw_codes = len(raw_codes_seen)
    print("Rows with any CPC:", rows_with_any_cpc)
    print("Unique raw CPC codes seen:", total_raw_codes)
    print("Unique mapped level-5 canonical codes so far:", len(mapped_codes_set))
    print("Rows with no mappable CPC to level-5 (counted):", unmapped_rows)

    # Now, for each mapped canonical code, compute annual EMA over the years observed for that code.
    # First find full set of years across dataset for consistent ordering per code (we can use per-code years)
    # But EMA must be computed over chronological years available for that code; if some years missing, treat missing as 0 count.
    code_ema_by_year = {}  # code -> dict year->ema
    code_best_year = {}  # code -> (best_year, best_ema)
    for code in counts:
        year_counts = counts[code]  # dict year->count
        years = sorted(year_counts.keys())
        if not years:
            continue
        # To ensure continuity, we consider all years between min and max for that code, filling missing with 0
        miny, maxy = years[0], years[-1]
        year_sequence = list(range(miny, maxy + 1))
        ema_by_year = {}
        prev_ema = None
        for y in year_sequence:
            val = year_counts.get(y, 0)
            if prev_ema is None:
                ema = float(val)
            else:
                ema = ALPHA * val + (1 - ALPHA) * prev_ema
            ema_by_year[y] = ema
            prev_ema = ema
        code_ema_by_year[code] = ema_by_year
        # determine best year: maximum EMA; tie-breaker choose latest year
        best_year = None
        best_ema = None
        for y, e in ema_by_year.items():
            if best_ema is None or e > best_ema or (e == best_ema and y > best_year):
                best_ema = e
                best_year = y
        if best_year is not None:
            code_best_year[code] = (best_year, best_ema)

    print("Computed EMA for codes:", len(code_ema_by_year))
    # Filter to codes whose best year is TARGET_YEAR and that are confirmed to be at level TARGET_LEVEL in metadata
    selected_codes = []
    for code, (byear, bema) in code_best_year.items():
        if byear == TARGET_YEAR:
            # confirm level
            if code in level_map:
                if level_map[code] == TARGET_LEVEL:
                    selected_codes.append(code)
                else:
                    # attempt climbing (shouldn't be necessary)
                    targ = climb_to_level(code, level_map, parent_map)
                    if targ and level_map.get(targ) == TARGET_LEVEL:
                        selected_codes.append(targ)
            else:
                # if no explicit level info, we cannot be sure; skip (conservative)
                pass

    selected_codes = sorted(set(selected_codes))
    print("Total canonical codes considered:", len(counts))
    print("Codes with best year == {}: {}".format(TARGET_YEAR, len([c for c,(y,e) in code_best_year.items() if y==TARGET_YEAR])))
    print("Codes selected (level {} and best year {}): {}".format(TARGET_LEVEL, TARGET_YEAR, len(selected_codes)))

    # Validation checks
    #  - Each output code must appear in metadata mapping and be at requested level.
    invalids = [c for c in selected_codes if c not in level_map or level_map.get(c) != TARGET_LEVEL]
    if invalids:
        print("WARNING: some selected codes do not have metadata level=={}: {}".format(TARGET_LEVEL, invalids), file=sys.stderr)

    # Write final answer: one code per line, sorted ascending
    out_path = Path(FINAL_ANSWER_PATH)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open('w', encoding='utf-8') as f:
        for code in selected_codes:
            f.write(code.strip() + "\n")

    print("Final answer written to", FINAL_ANSWER_PATH)
    print("Number of codes written:", len(selected_codes))
    # Print a small sample with best-year and EMA for debugging (first 20)
    sample_count = 0
    for code in selected_codes[:20]:
        byear, bema = code_best_year.get(code, (None, None))
        print(f"CODE: {code}  BEST_YEAR: {byear}  BEST_EMA: {bema}")
        sample_count += 1

if __name__ == "__main__":
    main()
