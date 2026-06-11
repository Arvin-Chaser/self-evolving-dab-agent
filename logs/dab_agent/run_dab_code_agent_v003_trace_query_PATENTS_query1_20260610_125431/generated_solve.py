#!/usr/bin/env python3
"""
solve.py for DAB query_PATENTS/query1

This script:
- Parses CPC definition SQL to map CPC symbols to hierarchical levels (preferred).
- Reads the publication sqlite database to extract filing years and CPC codes.
- Aggregates counts per year per CPC symbol (filtered to level 5).
- Computes EMA (alpha=0.2) for each symbol across years.
- Picks each symbol's best year (year with max EMA; ties -> latest year).
- Outputs the CPC symbols (one per line) at level 5 whose best year == 2022.

Writes:
- FINAL_ANSWER_PATH: final_answer.txt (codes only, one per line, sorted ascending)
- STAGE_TRACE_PATH: stage_trace.json (8-stage structured execution trace)

Notes and assumptions are recorded in the stage trace.
"""
import sqlite3
import json
import re
import sys
import traceback
from pathlib import Path
from collections import defaultdict, OrderedDict
from datetime import datetime

# Paths provided by the environment (hardcoded by the task)
DAB_ROOT = "/home/m0st1ma/research/DataAgentBench"
CASE_DIR = "/home/m0st1ma/research/DataAgentBench/query_PATENTS/query1"
PUBLICATION_DB_PATH = "/home/m0st1ma/research/DataAgentBench/query_PATENTS/query_dataset/patent_publication.db"
CPC_DEFINITION_SQL_PATH = "/home/m0st1ma/research/DataAgentBench/query_PATENTS/query_dataset/patent_CPCDefinition.sql"
FINAL_ANSWER_PATH = "/home/m0st1ma/research/text2sql/logs/dab_agent/run_dab_code_agent_v003_trace_query_PATENTS_query1_20260610_125431/final_answer.txt"
STAGE_TRACE_PATH = "/home/m0st1ma/research/text2sql/logs/dab_agent/run_dab_code_agent_v003_trace_query_PATENTS_query1_20260610_125431/stage_trace.json"

# Global: stage trace list
stage_trace = []

def write_trace():
    try:
        Path(STAGE_TRACE_PATH).parent.mkdir(parents=True, exist_ok=True)
        with open(STAGE_TRACE_PATH, "w", encoding="utf-8") as f:
            json.dump(stage_trace, f, indent=2)
    except Exception as e:
        print("Failed to write stage trace:", e, file=sys.stderr)

def add_stage(stage, status, summary, evidence_used=None, assumptions=None, outputs=None, uncertainties=None, error=None):
    obj = {
        "stage": stage,
        "status": status,
        "summary": summary,
        "evidence_used": evidence_used or [],
        "assumptions": assumptions or [],
        "outputs": outputs or [],
        "uncertainties": uncertainties or [],
        "error": error if error is None else str(error)
    }
    stage_trace.append(obj)
    # write trace on each stage update to be robust
    write_trace()

# Utility: parse SQL CREATE TABLE to get column order for cpc_definition
def parse_create_table_columns(sql_text, table_name='cpc_definition'):
    # find CREATE TABLE "...table_name..." (...) block
    pattern = re.compile(r'CREATE\s+TABLE\s+["`]?'+re.escape(table_name)+r'["`]?\s*\((.*?)\);', re.IGNORECASE | re.S)
    m = pattern.search(sql_text)
    if not m:
        # sometimes table names are unquoted
        pattern2 = re.compile(r'CREATE\s+TABLE\s+'+re.escape(table_name)+r'\s*\((.*?)\);', re.IGNORECASE | re.S)
        m = pattern2.search(sql_text)
    if not m:
        return None
    cols_block = m.group(1)
    # split by commas but be careful of parentheses - simple heuristic: split lines by comma-newline or newline
    # columns usually one per line
    cols = []
    for line in cols_block.splitlines():
        line = line.strip()
        if not line:
            continue
        # remove trailing comma
        if line.endswith(','):
            line = line[:-1].strip()
        # extract column name
        # patterns: "colname" TEXT, colname TEXT, 'colname' ...
        mcol = re.match(r'["`]?([^"`\s]+)["`]?\s+', line)
        if mcol:
            cols.append(mcol.group(1))
    return cols

# Utility: parse VALUES tuples from INSERT INTO for a given table
def extract_insert_tuples(sql_text, table_name='cpc_definition'):
    # Collect all INSERT INTO ... table_name ... VALUES (...) statements
    pattern = re.compile(r'INSERT\s+INTO\s+["`]?'+re.escape(table_name)+r'["`]?\s+VALUES\s*(.*?);', re.IGNORECASE | re.S)
    matches = pattern.findall(sql_text)
    tuples = []
    for block in matches:
        # block may contain multiple tuples separated by ,(...)
        # We will scan the block and extract balanced-parenthesis groups
        i = 0
        n = len(block)
        while i < n:
            # find next '('
            while i < n and block[i] != '(':
                i += 1
            if i >= n:
                break
            depth = 0
            start = i
            while i < n:
                if block[i] == '(':
                    depth += 1
                elif block[i] == ')':
                    depth -= 1
                    if depth == 0:
                        # include this ) and break
                        i += 1
                        tup = block[start:i]
                        tuples.append(tup)
                        break
                i += 1
    return tuples

# Utility: parse a single SQL tuple string like "('A01B','title',NULL,5)"
def parse_sql_tuple(tuple_str):
    """
    Returns list of values. Strings are unescaped, NULL -> None, numbers as numbers (or strings).
    The tuple_str includes surrounding parentheses.
    """
    s = tuple_str.strip()
    if s.startswith('(') and s.endswith(')'):
        s = s[1:-1]
    vals = []
    i = 0
    n = len(s)
    while i < n:
        while i < n and s[i].isspace():
            i += 1
        if i >= n:
            break
        if s[i] == "'":
            # parse quoted string, handle escaped '' as '
            i += 1
            start = i
            buf = []
            while i < n:
                if s[i] == "'":
                    if i+1 < n and s[i+1] == "'":
                        buf.append("'")
                        i += 2
                        continue
                    else:
                        i += 1
                        break
                else:
                    buf.append(s[i])
                    i += 1
            val = ''.join(buf)
            vals.append(val)
            # skip spaces and optional comma
            while i < n and s[i].isspace():
                i += 1
            if i < n and s[i] == ',':
                i += 1
            continue
        else:
            # parse until comma
            start = i
            while i < n and s[i] != ',':
                i += 1
            token = s[start:i].strip()
            if token.upper() == 'NULL':
                vals.append(None)
            else:
                # try number
                vals.append(token)
            if i < n and s[i] == ',':
                i += 1
            continue
    return vals

def parse_year_from_text(text):
    if not text:
        return None
    # Find 4-digit year between 1800 and 2050
    m = re.search(r'((?:18|19|20)\d{2})', text)
    if m:
        try:
            y = int(m.group(1))
            return y
        except:
            return None
    return None

def safe_print(*args, **kwargs):
    print(*args, **kwargs)
    sys.stdout.flush()

def main():
    # Prepare initial stage entries
    try:
        # S1 - Task understanding
        add_stage(
            stage="S1_task_understanding",
            status="started",
            summary="Interpret task: return CPC group codes at level 5 whose best year (by EMA alpha=0.2) is 2022.",
            evidence_used=[
                "Natural language question in prompt",
                "Requirement: smoothing factor 0.2; level 5; best year == 2022"
            ],
            assumptions=[
                "Use filing_date as the 'patent filings each year' unless filing_date missing; will parse year from filing_date text."
            ],
            outputs=[],
            uncertainties=["Whether filing_date is present for all rows; exact name of CPC column in DB (cpc or cpc_prefix)"]
        )
        add_stage("S1_task_understanding", "completed",
                  "Task parsed and high-level decisions made.",
                  evidence_used=["Prompt details"],
                  assumptions=["Use filing_date; filter level 5; EMA alpha=0.2"],
                  outputs=["Plan to parse CPCDefinition SQL and publication DB"])
        # S2 - Data schema grounding
        add_stage("S2_data_schema_grounding", "started",
                  "Load and parse CPC definition SQL to get mapping of symbol -> level and titleFull where possible.",
                  evidence_used=[CPC_DEFINITION_SQL_PATH],
                  assumptions=["CPC definition SQL contains CREATE TABLE for cpc_definition and INSERT statements with columns including 'symbol' and some 'level' indicator."],
                  outputs=[],
                  uncertainties=[])
        cpc_def_map = {}  # symbol -> dict(fields)
        cpc_symbols_level = {}  # symbol -> level (int)
        cpc_titles = {}  # symbol -> titleFull if available
        sql_text = ""
        try:
            with open(CPC_DEFINITION_SQL_PATH, "r", encoding="utf-8", errors="ignore") as f:
                sql_text = f.read()
            safe_print("Loaded CPC definition SQL file, size:", len(sql_text))
            cols = parse_create_table_columns(sql_text, table_name='cpc_definition')
            if cols:
                safe_print("Parsed CREATE TABLE cpc_definition columns:", cols[:20])
            else:
                safe_print("Could not find CREATE TABLE cpc_definition; will attempt to parse INSERTs heuristically.")
            tuples = extract_insert_tuples(sql_text, table_name='cpc_definition')
            safe_print("Found", len(tuples), "INSERT tuples for cpc_definition (may include many).")
            parsed_count = 0
            # Determine which column corresponds to 'symbol' and which to 'level'/'level' like names
            symbol_col_idx = None
            level_col_idx = None
            title_col_idx = None
            if cols:
                # normalize column names
                lc = [c.lower() for c in cols]
                for idx, name in enumerate(lc):
                    if name in ('symbol', 'code', 'id'):
                        symbol_col_idx = idx
                    if 'level' in name or 'lvl' in name:
                        level_col_idx = idx
                    if name in ('titlefull', 'title_full', 'title'):
                        title_col_idx = idx
            # parse tuples
            for t in tuples:
                vals = parse_sql_tuple(t)
                if not vals:
                    continue
                parsed_count += 1
                sym = None
                level = None
                title = None
                if cols and symbol_col_idx is not None and symbol_col_idx < len(vals):
                    sym = vals[symbol_col_idx]
                else:
                    # fallback: assume first non-null string field is symbol
                    for v in vals:
                        if isinstance(v, str) and v and re.search(r'[A-Z]\d', v):
                            sym = v
                            break
                if cols and level_col_idx is not None and level_col_idx < len(vals):
                    lv = vals[level_col_idx]
                    if isinstance(lv, str):
                        # try to parse int
                        try:
                            level = int(re.sub(r"[^0-9]", "", lv))
                        except:
                            level = None
                    elif isinstance(lv, (int, float)):
                        level = int(lv)
                    else:
                        level = None
                else:
                    # try to find an integer-like token in the tuple near the end
                    for v in vals[::-1]:
                        if v is None:
                            continue
                        if isinstance(v, str) and re.fullmatch(r'\d+', v):
                            try:
                                vv = int(v)
                                if 1 <= vv <= 10:
                                    level = vv
                                    break
                            except:
                                pass
                if cols and title_col_idx is not None and title_col_idx < len(vals):
                    title = vals[title_col_idx]
                else:
                    # attempt heuristic: a longer string not symbol
                    for v in vals:
                        if isinstance(v, str) and v and v != sym and len(v) > 5:
                            title = v
                            break
                if sym:
                    cpc_def_map[sym] = {"level": level, "title": title}
                    if level is not None:
                        cpc_symbols_level[sym] = level
                    if title:
                        cpc_titles[sym] = title
            if parsed_count == 0:
                add_stage("S2_data_schema_grounding", "failed",
                          "No INSERT tuples parsed for cpc_definition; cannot build mapping from SQL.",
                          evidence_used=[CPC_DEFINITION_SQL_PATH],
                          assumptions=[],
                          outputs=[],
                          uncertainties=["CPC definition SQL parsing failed; file format unexpected."],
                          error="No tuples parsed")
            else:
                add_stage("S2_data_schema_grounding", "completed",
                          "Parsed CPC definition SQL and extracted symbol->level mappings where available.",
                          evidence_used=[CPC_DEFINITION_SQL_PATH, f"Parsed {parsed_count} tuples"],
                          assumptions=["If level field not found, will fallback to heuristics for level detection."],
                          outputs=[f"Extracted {len(cpc_def_map)} symbols; {len(cpc_symbols_level)} with explicit level"],
                          uncertainties=["Some symbols may lack explicit level in SQL; fallback required."])
        except Exception as e:
            add_stage("S2_data_schema_grounding", "failed",
                      "Exception while parsing CPC definition SQL.",
                      evidence_used=[CPC_DEFINITION_SQL_PATH],
                      assumptions=[],
                      outputs=[],
                      uncertainties=["Parsing SQL may fail due to unexpected format."],
                      error=traceback.format_exc())
            # continue with empty mapping but record failure
        # If we did not obtain level info for many symbols, plan fallback
        fallback_used = False
        if len(cpc_symbols_level) == 0:
            # fallback: infer level by counting components of the symbol using "/" splits and numeric parts
            fallback_used = True
            add_stage("S2_data_schema_grounding", "completed",
                      "No explicit level info found; will fallback to heuristic mapping from symbol shape.",
                      evidence_used=[CPC_DEFINITION_SQL_PATH],
                      assumptions=["Infer level from symbol string shape: level 5 corresponds to subgroup symbols (has slash and additional digits)"],
                      outputs=["Using fallback heuristic for symbol->level mapping"],
                      uncertainties=["Heuristic may misclassify some symbols; preference is metadata but none found."])
            # implement simple heuristic: level = 1..5 based on presence of section/class/subclass/maingroup/subgroup
            # Common CPC symbol formats: A01B1/00 (class+subclass+group maybe). We'll define:
            # - If symbol contains '/' and right side length > 2 -> assume subgroup (level 5)
            for sym in list(cpc_def_map.keys()):
                # if symbol already had some level None, set via heuristic
                if cpc_def_map[sym].get("level") is None:
                    s = sym.strip()
                    if '/' in s:
                        # count parts: left part e.g., "H01M10" and right part "0565" etc.
                        # classify as level 5 when slash present
                        inferred = 5
                    else:
                        inferred = 4
                    cpc_def_map[sym]['level'] = inferred
                    cpc_symbols_level[sym] = inferred
        # S3 - Planning and decomposition
        add_stage("S3_planning_decomposition", "completed",
                  "Decomposed task into steps: load DB, normalize CPCs, map to canonical symbols/levels, aggregate counts by year, compute EMA, determine best year, filter by 2022, output codes.",
                  evidence_used=[PUBLICATION_DB_PATH, CPC_DEFINITION_SQL_PATH],
                  assumptions=["Will treat filing_date as the filing year source; will parse year via regex; will only count CPC symbols mapped to level 5."],
                  outputs=[
                      "Steps: load DB, extract CPC list per row, extract filing year, map codes via cpc_def_map, aggregate counts, compute EMA(alpha=0.2), find best year per code, filter best year==2022"
                  ])
        # S4 - Tool dependency planning
        add_stage("S4_tool_dependency_planning", "started",
                  "Decide which local files to use and which to avoid.",
                  evidence_used=[PUBLICATION_DB_PATH, CPC_DEFINITION_SQL_PATH],
                  assumptions=[],
                  outputs=[],
                  uncertainties=[])
        allowed_files = [PUBLICATION_DB_PATH, CPC_DEFINITION_SQL_PATH]
        forbidden_files = ["ground_truth.csv", "validate.py", "any external internet"]
        add_stage("S4_tool_dependency_planning", "completed",
                  "Tool plan: only local DB and SQL definition are used; validator and ground truth are not read.",
                  evidence_used=allowed_files,
                  assumptions=["Do not access validator or ground truth files."],
                  outputs=[f"Allowed: {allowed_files}", f"Forbidden: {forbidden_files}"])
        # S5 - Query/code generation (prepare to query DB)
        add_stage("S5_query_code_generation", "started",
                  "Prepare SQL query to extract necessary fields from publicationinfo table.",
                  evidence_used=[PUBLICATION_DB_PATH],
                  assumptions=["publicationinfo table exists with fields including cpc and filing_date (or cpc_prefix)."],
                  outputs=[])
        # Connect to DB and inspect columns
        conn = None
        col_names = []
        cpc_col_candidates = []
        try:
            conn = sqlite3.connect(PUBLICATION_DB_PATH)
            cur = conn.cursor()
            # get table info
            cur.execute("PRAGMA table_info(publicationinfo);")
            rows = cur.fetchall()
            col_names = [r[1] for r in rows]
            safe_print("publicationinfo columns:", col_names)
            # choose cpc column: prefer 'cpc', then 'cpc_prefix'
            if 'cpc' in col_names:
                cpc_col_candidates.append('cpc')
            if 'cpc_prefix' in col_names:
                cpc_col_candidates.append('cpc_prefix')
            if 'cpc_codes' in col_names:
                cpc_col_candidates.append('cpc_codes')
            if not cpc_col_candidates:
                # fallback: try any column name containing 'cpc'
                for c in col_names:
                    if 'cpc' in c.lower():
                        cpc_col_candidates.append(c)
            if not cpc_col_candidates:
                add_stage("S5_query_code_generation", "failed",
                          "No CPC-like column found in publicationinfo table.",
                          evidence_used=[f"Columns: {col_names}"],
                          assumptions=[],
                          outputs=[],
                          uncertainties=["DB schema unexpected."],
                          error="No CPC column")
                # cannot proceed
                return
            chosen_cpc_col = cpc_col_candidates[0]
            safe_print("Chosen CPC column:", chosen_cpc_col)
            add_stage("S5_query_code_generation", "completed",
                      "SQL and extraction plan prepared.",
                      evidence_used=[PUBLICATION_DB_PATH, f"Chosen CPC column: {chosen_cpc_col}"],
                      assumptions=["Will extract filing_date and chosen CPC column from publicationinfo."],
                      outputs=[f"Will query columns: filing_date, {chosen_cpc_col}"])
        except Exception as e:
            add_stage("S5_query_code_generation", "failed",
                      "Failed to inspect publication DB.",
                      evidence_used=[PUBLICATION_DB_PATH],
                      assumptions=[],
                      outputs=[],
                      uncertainties=["DB may be corrupt or inaccessible."],
                      error=traceback.format_exc())
            return

        # S6 - Execution: read rows and extract CPCs and filing years
        add_stage("S6_execution", "started",
                  "Extract rows from publicationinfo and parse filing years and CPC codes.",
                  evidence_used=[PUBLICATION_DB_PATH, chosen_cpc_col if 'chosen_cpc_col' in locals() else 'cpc?'],
                  assumptions=["filing_date text contains a 4-digit year; CPC field contains JSON-like array or single code strings."],
                  outputs=[],
                  uncertainties=[])
        # We'll iterate over rows in DB and parse
        try:
            cur = conn.cursor()
            # Select needed columns
            # Use chosen_cpc_col variable
            sel_col = chosen_cpc_col
            query = f"SELECT {sel_col}, filing_date FROM publicationinfo;"
            cur.execute(query)
            rows = cur.fetchall()
            safe_print("Total rows fetched from publicationinfo:", len(rows))
            # aggregate raw counts per (symbol, year)
            counts = defaultdict(lambda: defaultdict(int))  # counts[symbol][year] = int
            unmapped_codes_set = set()
            total_codes_seen = 0
            rows_with_dates = 0
            rows_with_cpc = 0
            for i, (cpc_field, filing_date) in enumerate(rows):
                year = parse_year_from_text(filing_date) if filing_date else None
                if year:
                    rows_with_dates += 1
                # parse cpc_field: may be JSON-like array string; we'll extract all tokens that look like CPC symbols e.g., 'H01M10/0565' via regex
                if not cpc_field:
                    continue
                rows_with_cpc += 1
                # Attempt to find all occurrences of pattern: uppercase letter(s) + digits + uppercase letter(s) + digits? + '/' + digits+ (and optional / etc)
                # Simpler: find tokens with pattern [A-Z][0-9A-Z]{0,4}\d+/\d+[A-Z0-9/]* (but to be permissive, pick sequences with a slash)
                found = re.findall(r'[A-Z]\w*?\d+/\d+[A-Za-z0-9/]*', cpc_field)
                # also find tokens like C01B35/00 (common)
                if not found:
                    # fallback: find things with a slash and alphanumerics around
                    found = re.findall(r'[A-Za-z0-9]+/[0-9A-Za-z]+', cpc_field)
                # dedupe
                found = list(dict.fromkeys(found))
                if not found:
                    continue
                for sym_raw in found:
                    sym = sym_raw.strip()
                    total_codes_seen += 1
                    # Normalize: uppercase, remove surrounding quotes
                    norm = sym.upper().strip().strip('"').strip("'")
                    # Map to canonical symbol present in cpc_def_map
                    if norm in cpc_def_map:
                        canon = norm
                        level = cpc_def_map[canon].get("level")
                    else:
                        # maybe definition uses variants without leading zeros; try simple normalization: remove leading zeros in subgroup part
                        canon = None
                        # try to find exact match ignoring leading zeros after slash
                        m = re.match(r'^([^/]+)/(0*)(\d+.*)$', norm)
                        if m:
                            candidate = f"{m.group(1)}/{m.group(3)}"
                            if candidate in cpc_def_map:
                                canon = candidate
                                level = cpc_def_map[canon].get("level")
                        if canon is None:
                            # try to match by prefix: if definition has symbol that startswith left part of norm
                            left = norm.split('/')[0]
                            # find any symbol in cpc_def_map starting with left + '/'
                            matches = [s for s in cpc_def_map.keys() if s.startswith(left + '/')]
                            if len(matches) == 1:
                                canon = matches[0]
                                level = cpc_def_map[canon].get("level")
                            else:
                                # no canonical mapping found
                                canon = None
                                level = None
                    if canon is None:
                        unmapped_codes_set.add(norm)
                        continue
                    # require level==5 for counting per task (aggregate only level 5)
                    if level != 5:
                        # skip non-level-5 entries
                        continue
                    if year is None:
                        # we cannot attribute to a year - skip
                        continue
                    counts[canon][year] += 1
            safe_print("Rows with dates:", rows_with_dates, "Rows with CPC-like content:", rows_with_cpc, "Total codes seen:", total_codes_seen)
            safe_print("Unique level-5 canonical symbols counted:", len(counts))
            safe_print("Unique unmapped codes encountered (sample up to 20):", list(sorted(unmapped_codes_set))[:20])
            add_stage("S6_execution", "completed",
                      "Extracted CPC symbols and filing years; aggregated raw counts per symbol-year for level 5 symbols.",
                      evidence_used=[PUBLICATION_DB_PATH],
                      assumptions=["Parsing CPCs via regex; using filing_date extracted year."],
                      outputs=[f"Total level-5 symbols with counts: {len(counts)}", f"Unmapped code examples: {list(sorted(unmapped_codes_set))[:10]}"],
                      uncertainties=["Some CPC entries could not be mapped to canonical symbols; regex parsing may miss some formats."])
        except Exception as e:
            add_stage("S6_execution", "failed",
                      "Exception during DB extraction and parsing.",
                      evidence_used=[PUBLICATION_DB_PATH],
                      assumptions=[],
                      outputs=[],
                      uncertainties=["DB access or parsing error."],
                      error=traceback.format_exc())
            return
        finally:
            try:
                conn.close()
            except:
                pass

        # S7 - Transformation and calculation
        add_stage("S7_transformation_calculation", "started",
                  "Compute EMA(alpha=0.2) per symbol across years and determine best year (max EMA).",
                  evidence_used=[f"Aggregated counts for {len(counts)} symbols"],
                  assumptions=["Sort years ascending for EMA; initialize EMA of first year = count of that year; alpha=0.2; tie-breaker for best year is latest year."],
                  outputs=[],
                  uncertainties=[])
        try:
            alpha = 0.2
            symbol_ema_by_year = {}  # symbol -> dict year->ema
            symbol_best_year = {}  # symbol -> (best_year, best_ema)
            symbol_time_series = {}  # symbol -> OrderedDict(year->count)
            # Determine global year range if needed
            for sym, year_counts in counts.items():
                # ensure chronological order
                years = sorted(year_counts.keys())
                if not years:
                    continue
                # build full series from min to max year filling zeros for missing years
                miny = years[0]
                maxy = years[-1]
                years_full = list(range(miny, maxy+1))
                ts = OrderedDict()
                for y in years_full:
                    ts[y] = year_counts.get(y, 0)
                # compute EMA
                ema_by_year = {}
                prev_ema = None
                for idx, y in enumerate(sorted(ts.keys())):
                    val = ts[y]
                    if idx == 0:
                        ema = float(val)
                    else:
                        ema = alpha * float(val) + (1 - alpha) * prev_ema
                    ema_by_year[y] = ema
                    prev_ema = ema
                symbol_time_series[sym] = ts
                symbol_ema_by_year[sym] = ema_by_year
                # find best year: max EMA; tie -> choose latest year (deterministic)
                best_year = None
                best_ema = None
                for y, e in ema_by_year.items():
                    if best_ema is None or e > best_ema or (e == best_ema and y > best_year):
                        best_ema = e
                        best_year = y
                symbol_best_year[sym] = (best_year, best_ema)
            safe_print("Computed EMA for symbols. Total symbols processed:", len(symbol_best_year))
            # Filter to symbols whose best year == 2022
            target_year = 2022
            selected_symbols = [s for s, (by, e) in symbol_best_year.items() if by == target_year]
            safe_print("Symbols whose best year == 2022:", len(selected_symbols))
            # Sort deterministically
            selected_symbols_sorted = sorted(selected_symbols)
            add_stage("S7_transformation_calculation", "completed",
                      "Computed EMA and selected symbols whose best year is 2022.",
                      evidence_used=[f"alpha={alpha}", f"Counts for {len(counts)} symbols"],
                      assumptions=["EMA initialized at first available year count. Tie-breaking: choose latest year."],
                      outputs=[f"Selected {len(selected_symbols_sorted)} symbols with best year=={target_year}"],
                      uncertainties=["If mapping coverage incomplete, some symbols may be missed."])
        except Exception as e:
            add_stage("S7_transformation_calculation", "failed",
                      "Exception during EMA computation or selection.",
                      evidence_used=[],
                      assumptions=[],
                      outputs=[],
                      uncertainties=[],
                      error=traceback.format_exc())
            return

        # S8 - Answer synthesis and validation
        add_stage("S8_answer_synthesis_validation", "started",
                  "Validate selected symbols against mapping and write final answer file with one code per line.",
                  evidence_used=[CPC_DEFINITION_SQL_PATH, PUBLICATION_DB_PATH],
                  assumptions=["All output codes must be present in cpc_def_map with level==5; outputs must be unique and sorted."],
                  outputs=[],
                  uncertainties=[])
        try:
            # Validation checks
            valid_outputs = []
            invalids = []
            for sym in selected_symbols_sorted:
                # check presence in mapping and level
                if sym not in cpc_def_map:
                    invalids.append((sym, "not_in_mapping"))
                    continue
                lvl = cpc_def_map[sym].get("level")
                if lvl != 5:
                    invalids.append((sym, f"level_{lvl}"))
                    continue
                valid_outputs.append(sym)
            # uniqueness check
            unique_outputs = list(OrderedDict.fromkeys(valid_outputs))
            # final counts
            total_canonical_considered = len(cpc_symbols_level)
            num_with_best_2022 = len(selected_symbols_sorted)
            num_output = len(unique_outputs)
            safe_print("Validation: total canonical symbols with level info:", total_canonical_considered)
            safe_print("Validation: symbols with best year==2022 (before removing invalid):", num_with_best_2022)
            safe_print("Validation: final output count (after mapping & level checks):", num_output)
            if invalids:
                safe_print("Some selected symbols failed validation (examples up to 20):", invalids[:20])
            # Write final answer file
            Path(FINAL_ANSWER_PATH).parent.mkdir(parents=True, exist_ok=True)
            with open(FINAL_ANSWER_PATH, "w", encoding="utf-8") as f:
                for sym in unique_outputs:
                    f.write(sym.strip() + "\n")
            safe_print("Wrote final answer to", FINAL_ANSWER_PATH)
            # Record stage completion
            add_stage("S8_answer_synthesis_validation", "completed",
                      "Final answer written and validations performed.",
                      evidence_used=[CPC_DEFINITION_SQL_PATH, PUBLICATION_DB_PATH],
                      assumptions=["Output codes written one per line, sorted ascending."],
                      outputs=[
                          f"FINAL_ANSWER_PATH: {FINAL_ANSWER_PATH}",
                          f"Total canonical symbols considered: {total_canonical_considered}",
                          f"Symbols with best year==2022 before validation: {num_with_best_2022}",
                          f"Final output count: {num_output}"
                      ],
                      uncertainties=[f"{len(unmapped_codes_set)} raw codes could not be mapped; they were skipped."])
        except Exception as e:
            add_stage("S8_answer_synthesis_validation", "failed",
                      "Exception while validating or writing final answer.",
                      evidence_used=[],
                      assumptions=[],
                      outputs=[],
                      uncertainties=[],
                      error=traceback.format_exc())
            return

    except Exception as e_outer:
        # Catch-all: ensure trace is written with failure
        add_stage("S1_task_understanding", "failed",
                  "Unhandled exception in main execution.",
                  evidence_used=[],
                  assumptions=[],
                  outputs=[],
                  uncertainties=[],
                  error=traceback.format_exc())
        safe_print("Unhandled exception:", traceback.format_exc())
    finally:
        # Final write of trace to ensure persisted
        write_trace()

if __name__ == "__main__":
    main()
