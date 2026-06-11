#!/usr/bin/env python3
# coding: utf-8
"""
solve.py for DAB query:
Identify CPC technology areas with highest EMA of patent filings each year (alpha=0.2),
and return only the CPC group codes at level 5 whose best year is 2022.

Files used:
- CPC_DEFINITION_SQL_PATH: /home/m0st1ma/research/DataAgentBench/query_PATENTS/query_dataset/patent_CPCDefinition.sql
- PUBLICATION_DB_PATH: /home/m0st1ma/research/DataAgentBench/query_PATENTS/query_dataset/patent_publication.db
Final output written to FINAL_ANSWER_PATH.

Assumptions & notes (documented per S2/S7):
- We parse the CPC definition SQL dump to build a mapping of symbol -> metadata (including parent).
- We compute levels either from an explicit 'level' column if present, otherwise by constructing parent->children
  relations and assigning root level=1, children level=root+1, etc.
- We only map classification values that exactly match a canonical 'symbol' from the CPC definition mapping.
  We do NOT invent or heuristically infer canonical codes beyond walking parent links to reach level 5.
- For patent dates we prefer 'filing_date' (to represent "filings each year"); if missing, we fall back to 'publication_date'.
  We extract years by searching for a 4-digit year (19xx|20xx) in the natural-language date field.
- EMA: years are sorted ascending; EMA_first = value_first_year; EMA_t = alpha * value_t + (1-alpha) * EMA_{t-1}.
- Tie-breaking for best year: if multiple years share the same max EMA, choose the latest year (deterministic).
- Output: one CPC symbol per line (canonical symbol), sorted ascending, only those at level 5 whose best year == 2022.

This script prints progress and mapping coverage statistics to stdout.

Author: Data Agent
"""

import os
import sys
import sqlite3
import re
import json
import math
from collections import defaultdict, deque

# Paths (from environment of the task)
DAB_ROOT = "/home/m0st1ma/research/DataAgentBench"
CASE_DIR = "/home/m0st1ma/research/DataAgentBench/query_PATENTS/query1"
PUBLICATION_DB_PATH = "/home/m0st1ma/research/DataAgentBench/query_PATENTS/query_dataset/patent_publication.db"
CPC_DEFINITION_SQL_PATH = "/home/m0st1ma/research/DataAgentBench/query_PATENTS/query_dataset/patent_CPCDefinition.sql"
FINAL_ANSWER_PATH = "/home/m0st1ma/research/text2sql/logs/dab_agent/run_dab_code_agent_v002_loop_iter2_query_PATENTS_query1_20260610_122025/final_answer.txt"

ALPHA = 0.2
TARGET_LEVEL = 5
TARGET_YEAR = 2022

# ---------------------------
# Utility: SQL INSERT parser
# ---------------------------
def find_cpc_definition_inserts(sql_text):
    """
    Find INSERT statements into the cpc definition table.
    Return list of tuples: (column_list_or_None, values_part_text)
    """
    inserts = []
    # Regex to find INSERT INTO ... cpc_definition ... VALUES ...
    # Be tolerant to quoting of table name.
    pattern = re.compile(r'INSERT\s+INTO\s+["`]?cpc_definition["`]?\s*(\([^\)]*\))?\s*VALUES\s*(\(.+?;\s*)', re.IGNORECASE | re.DOTALL)
    # The above might fail if the file uses many statements; fallback to scanning lines and collecting items manually.
    for m in pattern.finditer(sql_text):
        cols = m.group(1)
        vals = m.group(2)
        inserts.append((cols, vals))
    if inserts:
        return inserts

    # Fallback: more generic scanning for lines starting with INSERT INTO cpc_definition
    inserts = []
    for m in re.finditer(r'INSERT\s+INTO\s+["`]?cpc_definition["`]?\s*(\([^\)]*\))?\s*VALUES\s*', sql_text, re.IGNORECASE):
        start = m.end()
        # From start find the terminating semicolon for this INSERT
        idx = start
        depth = 0
        while idx < len(sql_text):
            ch = sql_text[idx]
            if ch == '(':
                depth += 1
            elif ch == ')':
                depth -= 1
            elif ch == ';' and depth <= 0:
                # end
                end = idx + 1
                inserts.append((m.group(1), sql_text[start:end]))
                break
            idx += 1
    return inserts

def split_toplevel_tuples(values_text):
    """
    Given a VALUES(...)... string (starting at first '('), extract a list of tuple-strings,
    each includes the outer parentheses, e.g., "( 'a', 'b' ),( 'c','d' )".
    This function returns list of the inner contents of each tuple (without surrounding parentheses).
    """
    tuples = []
    s = values_text.strip().rstrip(';').strip()
    i = 0
    n = len(s)
    # skip possible leading "VALUES"
    if s.upper().startswith('VALUES'):
        s = s[6:].lstrip()
        i = 0
        n = len(s)
    # parse
    while i < n:
        # find next '(' at top level
        while i < n and s[i] != '(':
            i += 1
        if i >= n:
            break
        depth = 0
        start = i
        i2 = i
        in_quote = False
        quote_char = None
        while i2 < n:
            ch = s[i2]
            if in_quote:
                if ch == quote_char:
                    # check for escaped quote by doubling (SQL way)
                    if i2 + 1 < n and s[i2+1] == quote_char:
                        i2 += 2
                        continue
                    else:
                        in_quote = False
                        quote_char = None
                        i2 += 1
                        continue
                else:
                    i2 += 1
                    continue
            else:
                if ch in ("'", '"'):
                    in_quote = True
                    quote_char = ch
                    i2 += 1
                    continue
                if ch == '(':
                    depth += 1
                elif ch == ')':
                    depth -= 1
                    if depth == 0:
                        # include closing ')'
                        tuple_str = s[start+1:i2]  # inner content
                        tuples.append(tuple_str)
                        i = i2 + 1
                        break
                i2 += 1
        else:
            break
    return tuples

def parse_sql_value_token(tok):
    """
    Parse a single SQL value token (string quoted with single quotes possibly with doubled quotes),
    or NULL, or numeric.
    Return python value (str or None or number).
    """
    tok = tok.strip()
    if not tok:
        return None
    if tok.upper() == 'NULL':
        return None
    if tok.startswith("'") and tok.endswith("'"):
        inner = tok[1:-1]
        # replace doubled single-quotes with one
        inner = inner.replace("''", "'")
        return inner
    if tok.startswith('"') and tok.endswith('"'):
        inner = tok[1:-1]
        inner = inner.replace('""', '"')
        return inner
    # try numeric
    try:
        if '.' in tok:
            return float(tok)
        else:
            return int(tok)
    except:
        return tok

def split_tuple_tokens(tuple_inner):
    """
    Given inner content of tuple, split on commas not inside quotes.
    Return list of tokens as strings.
    """
    tokens = []
    i = 0
    n = len(tuple_inner)
    start = 0
    in_quote = False
    quote_char = None
    while i < n:
        ch = tuple_inner[i]
        if in_quote:
            if ch == quote_char:
                # possible escaped quote
                if i + 1 < n and tuple_inner[i+1] == quote_char:
                    i += 2
                    continue
                else:
                    in_quote = False
                    quote_char = None
                    i += 1
                    continue
            else:
                i += 1
                continue
        else:
            if ch in ("'", '"'):
                in_quote = True
                quote_char = ch
                i += 1
                continue
            if ch == ',':
                tok = tuple_inner[start:i].strip()
                tokens.append(tok)
                start = i + 1
            i += 1
    # last token
    if start < n:
        tok = tuple_inner[start:].strip()
        tokens.append(tok)
    return tokens

# ---------------------------
# Parse CPC definition SQL
# ---------------------------
def parse_cpc_definition(sql_path):
    """
    Parse CPC definition SQL file to extract rows for cpc_definition table.
    Returns:
      - mapping: symbol -> dict of columns (as strings)
      - column_names: list of column names found (may be empty)
    """
    if not os.path.exists(sql_path):
        print(f"ERROR: CPC definition SQL file not found at {sql_path}", file=sys.stderr)
        return {}, []

    with open(sql_path, 'r', encoding='utf-8', errors='ignore') as f:
        txt = f.read()

    inserts = find_cpc_definition_inserts(txt)
    if not inserts:
        print("WARNING: No INSERT INTO cpc_definition found in SQL dump. Attempting to parse CREATE TABLE data.", file=sys.stderr)
        return {}, []

    mapping = {}
    column_names_global = None
    total_rows = 0
    for cols_part, values_part in inserts:
        # Determine column names if provided
        cols = None
        if cols_part:
            # strip parentheses and split by commas
            raw = cols_part.strip()
            if raw.startswith('(') and raw.endswith(')'):
                raw = raw[1:-1]
            # split by commas not in quotes (simple split; column names typically simple)
            cols = [c.strip().strip('`"') for c in raw.split(',')]
        # Extract tuple groups
        tuple_inners = split_toplevel_tuples(values_part)
        for inner in tuple_inners:
            tokens = split_tuple_tokens(inner)
            values = [parse_sql_value_token(t) for t in tokens]
            if cols and len(cols) == len(values):
                row = dict(zip(cols, values))
            else:
                # if no cols, we can't map; try to guess common columns names
                row = {}
                # fallback column names attempt:
                # common CPC definition fields: symbol, titleFull, titleAbbrev, parent, level
                guess_cols = ['symbol','titleFull','title','titleAbbrev','parent','level','kind']
                for i, v in enumerate(values):
                    if i < len(guess_cols):
                        row[guess_cols[i]] = v
                    else:
                        row[f'col_{i}'] = v
            # require symbol
            sym = None
            for key in ('symbol','code','cpc'):
                if key in row and row[key]:
                    sym = row[key]
                    break
            if not sym:
                # attempt to find first token that looks like a symbol (has '/')
                for v in values:
                    if isinstance(v, str) and '/' in v:
                        sym = v
                        break
            if not sym:
                # give up on this row
                continue
            sym = sym.strip()
            row['symbol'] = sym
            mapping[sym] = row
            total_rows += 1

    print(f"Parsed CPC definition: extracted {total_rows} rows (unique symbols: {len(mapping)})")
    # determine column names if any insert had them
    for cols_part, _ in inserts:
        if cols_part:
            raw = cols_part.strip()
            if raw.startswith('(') and raw.endswith(')'):
                raw = raw[1:-1]
            column_names_global = [c.strip().strip('`"') for c in raw.split(',')]
            break

    return mapping, column_names_global

# ---------------------------
# Build level mapping using parent relationships
# ---------------------------
def compute_levels(mapping):
    """
    Given mapping: symbol -> row dict (may include 'parent' and 'level'),
    compute a numeric level for each symbol.
    Return dict symbol->level (int).
    Rules:
    - If explicit 'level' present and parseable as int, use it.
    - Else, build parent->children graph using 'parent' column (if present), and assign root nodes level=1,
      propagate levels to children (BFS). If cycles or unreachable nodes exist, attempt safe fallback.
    """
    levels = {}
    has_explicit = False
    for sym, row in mapping.items():
        lv = None
        for key in ('level', 'level_number', 'lvl'):
            if key in row and row[key] is not None:
                try:
                    lv = int(row[key])
                    break
                except:
                    pass
        if lv is not None:
            levels[sym] = lv
            has_explicit = True

    if has_explicit:
        # For rows without explicit level, try to infer by walking parent chain up to explicit ancestor
        for sym, row in mapping.items():
            if sym in levels:
                continue
            # walk parents until find a node with explicit level or run out
            cur = sym
            depth = 0
            seen = set()
            found = False
            while True:
                if cur in seen:
                    break
                seen.add(cur)
                parent = mapping.get(cur, {}).get('parent')
                if parent is None or parent == '' or parent == '\\N':
                    break
                parent = str(parent).strip()
                if parent in levels:
                    # assign level relative to parent
                    levels[sym] = levels[parent] + depth + 1
                    found = True
                    break
                cur = parent
                depth += 1
            if not found:
                # fallback: assign level = max explicit level seen + 1 (conservative)
                levels[sym] = max(levels.values()) + 1 if levels else 1
        return levels

    # No explicit levels: build parent->children graph and BFS from roots
    parent_of = {}
    children = defaultdict(list)
    for sym, row in mapping.items():
        parent = row.get('parent')
        if parent is None:
            # try other keys
            for k in row.keys():
                if k.lower() == 'parent':
                    parent = row.get(k)
                    break
        if parent is None or parent == '' or parent == '\\N':
            parent_of[sym] = None
        else:
            parent = str(parent).strip()
            parent_of[sym] = parent
            children[parent].append(sym)

    # roots: those with parent None or parent not in mapping
    roots = []
    for sym in mapping.keys():
        p = parent_of.get(sym)
        if p is None or p not in mapping:
            roots.append(sym)
    if not roots:
        # fallback: pick symbols with shortest symbol strings as roots (conservative)
        roots = sorted(mapping.keys(), key=lambda s: len(s))[:10]

    q = deque()
    for r in roots:
        levels[r] = 1
        q.append(r)
    # BFS
    while q:
        node = q.popleft()
        node_level = levels.get(node, 1)
        for ch in children.get(node, []):
            if ch in levels:
                continue
            levels[ch] = node_level + 1
            q.append(ch)

    # For any remaining symbols not reached, assign high level by walking parents until found or default 99
    for sym in mapping.keys():
        if sym in levels:
            continue
        cur = sym
        visited = set()
        depth = 0
        assigned = False
        while cur and cur not in visited:
            visited.add(cur)
            p = parent_of.get(cur)
            if p in levels:
                levels[sym] = levels[p] + depth
                assigned = True
                break
            cur = p
            depth += 1
        if not assigned:
            levels[sym] = max(levels.values()) + 1 if levels else 1

    print(f"Computed levels for {len(levels)} CPC symbols (target level for query = {TARGET_LEVEL})")
    return levels

# ---------------------------
# Publication DB parsing
# ---------------------------
def extract_year_from_text(dt_text):
    """
    Extract a 4-digit year (19xx or 20xx) from natural-language date.
    Return int year or None.
    """
    if not dt_text:
        return None
    m = re.search(r'(19|20)\d{2}', dt_text)
    if m:
        try:
            return int(m.group(0))
        except:
            return None
    return None

def extract_cpc_codes_from_field(field_text):
    """
    Try to extract CPC codes from a field which may be:
      - JSON array of objects with "code" keys (as in sample cpc_prefix)
      - plain string with codes separated by commas/semicolons
      - already canonical single code
    We will:
      - attempt json.loads; if it's a list of dicts with 'code', collect those
      - else, find tokens containing '/' and alphanumerics (simple heuristic for extraction)
    Return list of code strings (normalized).
    """
    if not field_text:
        return []
    txt = field_text.strip()
    codes = []
    # Try JSON
    try:
        parsed = json.loads(txt)
        if isinstance(parsed, list):
            for item in parsed:
                if isinstance(item, dict):
                    for k in ('code','symbol'):
                        if k in item and item[k]:
                            codes.append(str(item[k]).strip())
                            break
                elif isinstance(item, str):
                    codes.append(item.strip())
            if codes:
                return [c.upper() for c in codes]
    except Exception:
        pass

    # If not JSON, try to find tokens that look like CPC: contain a '/' and not too long
    # This is a mild heuristic for extraction only; we will not use this to infer hierarchy.
    tokens = re.split(r'[;\n,()\t]', txt)
    for t in tokens:
        t2 = t.strip().strip('"').strip("'")
        if not t2:
            continue
        if '/' in t2:
            # cleanup
            t3 = re.sub(r'[^A-Za-z0-9/]', '', t2).upper()
            if '/' in t3:
                codes.append(t3)
    # If nothing found, fallback: look for typical pattern like 'C01B33/00' anywhere
    if not codes:
        for m in re.finditer(r'[A-Z]\d{2}[A-Z]?[^ \t,;)]*/\d+[A-Za-z0-9]*', txt.upper()):
            codes.append(m.group(0))
    return codes

# ---------------------------
# Main computation
# ---------------------------
def main():
    # Step 1: Parse CPC definition SQL
    print("Step 1: Parsing CPC definition SQL...")
    mapping, colnames = parse_cpc_definition(CPC_DEFINITION_SQL_PATH)
    if not mapping:
        print("ERROR: No CPC mapping could be parsed. Exiting.", file=sys.stderr)
        # still write empty output file
        try:
            with open(FINAL_ANSWER_PATH, 'w', encoding='utf-8') as fo:
                fo.write("")
        except Exception as e:
            print(f"ERROR writing empty final answer file: {e}", file=sys.stderr)
        sys.exit(1)

    # Step 2: compute levels
    levels = compute_levels(mapping)

    # Step 3: Build parent links map for traversal
    parent = {}
    for sym, row in mapping.items():
        p = None
        # common parent keys
        if 'parent' in row and row['parent'] not in (None, '', '\\N'):
            p = row['parent']
        else:
            # try to find any key named like parent (case-insensitive)
            for k in row.keys():
                if k.lower() == 'parent' and row[k] not in (None, '', '\\N'):
                    p = row[k]
                    break
        if p is None:
            parent[sym] = None
        else:
            parent[sym] = str(p).strip()

    # Step 4: Open publication DB and iterate rows
    if not os.path.exists(PUBLICATION_DB_PATH):
        print(f"ERROR: Publication DB not found at {PUBLICATION_DB_PATH}", file=sys.stderr)
        sys.exit(1)

    conn = sqlite3.connect(PUBLICATION_DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # Try to select cpc, cpc_prefix, filing_date, publication_date
    cols_to_select = []
    # Check columns present in table
    try:
        cur.execute("PRAGMA table_info(publicationinfo)")
        cols_info = cur.fetchall()
        cols = [r['name'] for r in cols_info]
    except Exception as e:
        print(f"ERROR querying publicationinfo schema: {e}", file=sys.stderr)
        conn.close()
        sys.exit(1)

    # Choose fields: prefer 'cpc' or 'cpc_prefix'
    cpc_field = None
    if 'cpc' in cols:
        cpc_field = 'cpc'
    elif 'cpc_prefix' in cols:
        cpc_field = 'cpc_prefix'
    else:
        # fallback: try any column with 'cpc' in name
        for c in cols:
            if 'cpc' in c.lower():
                cpc_field = c
                break
    if 'filing_date' in cols:
        date_field = 'filing_date'
    elif 'publication_date' in cols:
        date_field = 'publication_date'
    else:
        # fallback pick any date-like
        date_field = None
        for c in cols:
            if 'date' in c.lower():
                date_field = c
                break

    if cpc_field is None:
        print("ERROR: No CPC-like column found in publicationinfo table. Columns:", cols, file=sys.stderr)
        conn.close()
        sys.exit(1)
    if date_field is None:
        print("ERROR: No date-like column found in publicationinfo table. Columns:", cols, file=sys.stderr)
        conn.close()
        sys.exit(1)

    print(f"Using CPC field '{cpc_field}' and date field '{date_field}' for analysis.")
    # Query all rows (stream)
    try:
        cur.execute(f"SELECT rowid, {cpc_field} as cpc_field, {date_field} as date_field FROM publicationinfo")
    except Exception as e:
        print(f"ERROR selecting from publicationinfo: {e}", file=sys.stderr)
        conn.close()
        sys.exit(1)

    # Aggregate counts: counts[(level5_symbol)][year] = count
    counts = defaultdict(lambda: defaultdict(int))
    total_rows = 0
    total_cpc_entries = 0
    mapped_entries = 0
    unmapped_entries = 0

    # For dedup per patent per code-year: keep set of (rowid, level5_symbol, year)
    seen_patent_code_year = set()

    for row in cur:
        total_rows += 1
        rowid = row['rowid']
        raw_cpc_field = row['cpc_field']
        raw_date_field = row['date_field']
        year = extract_year_from_text(raw_date_field)
        if year is None:
            # skip if no year found
            continue
        # Only consider years in a reasonable range
        if year < 1800 or year > 2100:
            continue

        codes = extract_cpc_codes_from_field(raw_cpc_field)
        if not codes:
            continue
        total_cpc_entries += len(codes)
        # For each extracted code attempt exact mapping then map to level 5 ancestor if possible
        for code in codes:
            code_norm = str(code).strip()
            # exact mapping
            if code_norm in mapping:
                mapped_entries += 1
                # determine its level (from computed levels)
                code_level = levels.get(code_norm)
                if code_level is None:
                    # cannot determine level -> skip
                    unmapped_entries += 1
                    continue
                # If code already at level 5, use it; if deeper (level > 5), walk parents up to level 5
                if code_level == TARGET_LEVEL:
                    level5_sym = code_norm
                elif code_level > TARGET_LEVEL:
                    # walk up parents
                    cur_sym = code_norm
                    level_cur = code_level
                    while level_cur > TARGET_LEVEL and cur_sym is not None:
                        cur_sym = parent.get(cur_sym)
                        level_cur = levels.get(cur_sym, None) if cur_sym is not None else None
                    if cur_sym is None or level_cur is None or level_cur != TARGET_LEVEL:
                        # cannot reach level 5
                        unmapped_entries += 1
                        continue
                    level5_sym = cur_sym
                else:
                    # code_level < TARGET_LEVEL -> cannot aggregate downwards (we won't invent children)
                    unmapped_entries += 1
                    continue

                key = (rowid, level5_sym, year)
                if key in seen_patent_code_year:
                    continue
                seen_patent_code_year.add(key)
                counts[level5_sym][year] += 1
            else:
                # not exact match -> do not map
                unmapped_entries += 1
                continue

    conn.close()
    print(f"Processed {total_rows} rows; extracted {total_cpc_entries} CPC entries.")
    print(f"Exact-mapped CPC entries: {mapped_entries}; unmapped/ignored entries: {unmapped_entries}")
    total_mapped_codes = len(counts)
    print(f"Total distinct level-5 candidate codes observed (after mapping to level 5): {total_mapped_codes}")

    # Mapping coverage check: if a significant fraction unmapped, warn
    total_entries = total_cpc_entries if total_cpc_entries > 0 else 1
    unmapped_frac = unmapped_entries / total_entries
    if unmapped_frac > 0.05:
        print(f"WARNING: {unmapped_entries} out of {total_entries} ({unmapped_frac:.2%}) CPC entries were unmapped or could not be reduced to level {TARGET_LEVEL}.", file=sys.stderr)
        print("This script only uses exact symbol matches from the CPC definition and parent links to reach the requested level.", file=sys.stderr)

    # Step: for each level5 code, compute year series and EMA
    # Determine full set of years across data for deterministic ordering
    all_years = set()
    for sym, ydict in counts.items():
        all_years.update(ydict.keys())
    if not all_years:
        print("No year data available after mapping. Writing empty final answer.")
        with open(FINAL_ANSWER_PATH, 'w', encoding='utf-8') as fo:
            fo.write("")
        sys.exit(0)
    year_list = sorted(all_years)
    print(f"Years observed (sorted): {year_list}")

    # For each code, build a time series covering all years in year_list (filling missing years with zero)
    ema_by_code = {}  # sym -> dict year->ema
    best_year_by_code = {}
    for sym in counts.keys():
        series = [counts[sym].get(y, 0) for y in year_list]
        # compute EMA
        ema_series = []
        for i, val in enumerate(series):
            if i == 0:
                ema = float(val)
            else:
                ema = ALPHA * float(val) + (1.0 - ALPHA) * ema_series[-1]
            ema_series.append(ema)
        # map back to years
        year_to_ema = {year_list[i]: ema_series[i] for i in range(len(year_list))}
        ema_by_code[sym] = year_to_ema
        # determine best year: max EMA, tie-breaker choose latest year
        max_ema = max(year_to_ema.values())
        candidate_years = [y for y, e in year_to_ema.items() if abs(e - max_ema) < 1e-12]
        best_year = max(candidate_years)
        best_year_by_code[sym] = best_year

    # Filter codes whose best year == TARGET_YEAR
    selected_codes = [sym for sym, by in best_year_by_code.items() if by == TARGET_YEAR]
    selected_codes_sorted = sorted(set(selected_codes))
    print(f"Codes with best year == {TARGET_YEAR}: {len(selected_codes_sorted)}")

    # Validation checks per S8:
    # - Each output code must appear in the metadata mapping and be at the requested level.
    valid_outputs = []
    invalids = []
    for sym in selected_codes_sorted:
        if sym not in mapping:
            invalids.append((sym, "not_in_mapping"))
            continue
        lvl = levels.get(sym)
        if lvl != TARGET_LEVEL:
            invalids.append((sym, f"level_{lvl}_!=_{TARGET_LEVEL}"))
            continue
        valid_outputs.append(sym)
    if invalids:
        print("WARNING: Some selected codes failed validation and will be excluded:", invalids, file=sys.stderr)

    # Final statistics
    total_canonical_codes_considered = len([s for s in levels.keys() if levels.get(s) == TARGET_LEVEL])
    print(f"Total canonical codes at level {TARGET_LEVEL} in metadata: {total_canonical_codes_considered}")
    num_bestmatch = len(selected_codes_sorted)
    print(f"Number of level-{TARGET_LEVEL} codes whose best year == {TARGET_YEAR}: {num_bestmatch}")
    print(f"Number of valid outputs after validation: {len(valid_outputs)}")

    # Write final_answer.txt: one code per line, sorted ascending
    valid_outputs_sorted = sorted(valid_outputs)
    try:
        os.makedirs(os.path.dirname(FINAL_ANSWER_PATH), exist_ok=True)
        with open(FINAL_ANSWER_PATH, 'w', encoding='utf-8') as fo:
            for sym in valid_outputs_sorted:
                fo.write(sym.strip() + "\n")
        print(f"Wrote final answer to {FINAL_ANSWER_PATH} ({len(valid_outputs_sorted)} lines).")
    except Exception as e:
        print(f"ERROR writing final answer file: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("Unhandled exception during execution:", file=sys.stderr)
        import traceback
        traceback.print_exc()
        # Attempt to write empty output to satisfy runner expectations
        try:
            with open(FINAL_ANSWER_PATH, 'w', encoding='utf-8') as fo:
                fo.write("")
        except Exception:
            pass
        sys.exit(1)
