"""
SQLite-based persistence for the Glossary Hub.
Stores all approved/rejected terms permanently across sessions.
"""

import sqlite3
import json
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "glossary_hub.db")


def _get_conn():
    """Get a connection to the SQLite database."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    """Initialize the database tables if they don't exist."""
    conn = _get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS glossary_terms (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entity_guid TEXT,
            table_guid TEXT,
            table_name TEXT,
            business_term TEXT,
            physical_term TEXT,
            description TEXT,
            classification TEXT DEFAULT '',
            type TEXT DEFAULT 'Column',
            source TEXT DEFAULT 'AI Suggester',
            confidence INTEGER DEFAULT 0,
            active INTEGER DEFAULT 1,
            version INTEGER DEFAULT 1,
            status TEXT DEFAULT 'Approved',
            stored_at TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_table_guid ON glossary_terms(table_guid)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_active ON glossary_terms(active)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_status ON glossary_terms(status)
    """)
    # Migration: add classification column if missing (existing databases)
    try:
        conn.execute("ALTER TABLE glossary_terms ADD COLUMN classification TEXT DEFAULT ''")
    except Exception:
        pass  # column already exists
    conn.commit()
    conn.close()


def store_term(entity_guid, table_guid, table_name, business_term, physical_term,
               description, term_type="Column", source="AI Suggester",
               confidence=0, active=1, version=1, status="Approved", stored_at=None,
               classification=""):
    """Store a single term record in the database."""
    conn = _get_conn()
    conn.execute("""
        INSERT INTO glossary_terms 
        (entity_guid, table_guid, table_name, business_term, physical_term,
         description, classification, type, source, confidence, active, version, status, stored_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (entity_guid, table_guid, table_name, business_term, physical_term,
          description, classification or "", term_type, source, confidence, active, version, status,
          stored_at or datetime.now().isoformat()))
    conn.commit()
    conn.close()


def deactivate_term(table_guid, physical_term):
    """Deactivate existing active records for a physical term (SCD Type 2)."""
    conn = _get_conn()
    conn.execute("""
        UPDATE glossary_terms 
        SET active = 0 
        WHERE table_guid = ? AND LOWER(physical_term) = LOWER(?) AND active = 1
    """, (table_guid, physical_term))
    conn.commit()
    conn.close()


def deactivate_by_business_term(table_guid, business_term):
    """Deactivate existing active records for a business term name (SCD Type 2).
    When a new version of the same business term is approved, the old record becomes non-active."""
    conn = _get_conn()
    conn.execute("""
        UPDATE glossary_terms 
        SET active = 0 
        WHERE table_guid = ? AND LOWER(business_term) = LOWER(?) AND active = 1
    """, (table_guid, business_term))
    conn.commit()
    conn.close()


def get_active_terms(table_guid=None, source_filter=None, since=None):
    """Get only currently active (approved) terms. If 'since' is set, only return terms stored after that timestamp."""
    conn = _get_conn()
    query = "SELECT * FROM glossary_terms WHERE active = 1 AND status != 'Rejected'"
    params = []
    if table_guid:
        query += " AND table_guid = ?"
        params.append(table_guid)
    if source_filter:
        query += " AND source = ?"
        params.append(source_filter)
    if since:
        query += " AND stored_at >= ?"
        params.append(since)
    query += " ORDER BY table_name, physical_term"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_all_terms(table_guid=None, source_filter=None):
    """Get all terms (active + historical + rejected) for history view."""
    conn = _get_conn()
    query = "SELECT * FROM glossary_terms WHERE 1=1"
    params = []
    if table_guid:
        query += " AND table_guid = ?"
        params.append(table_guid)
    if source_filter:
        query += " AND source = ?"
        params.append(source_filter)
    query += " ORDER BY stored_at DESC"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_approved_history(table_guid=None, source_filter=None):
    """Get all approved terms (active + previously-active) excluding rejected, for History view."""
    conn = _get_conn()
    query = "SELECT * FROM glossary_terms WHERE status IN ('Approved', 'Approved (Merged)')"
    params = []
    if table_guid:
        query += " AND table_guid = ?"
        params.append(table_guid)
    if source_filter:
        query += " AND source = ?"
        params.append(source_filter)
    query += " ORDER BY LOWER(physical_term), version ASC"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_latest_approved_per_term(table_guid=None, source_filter=None):
    """Get only the latest approved version per physical_term. Used for History OFF."""
    conn = _get_conn()
    # Build WHERE clause for the scope
    where_parts = ["g.status IN ('Approved', 'Approved (Merged)')"]
    params = []
    if table_guid:
        where_parts.append("g.table_guid = ?")
        params.append(table_guid)
    if source_filter:
        where_parts.append("g.source = ?")
        params.append(source_filter)
    where_clause = " AND ".join(where_parts)

    # Subquery: max version per physical_term within the same scope
    sub_where_parts = ["g2.status IN ('Approved', 'Approved (Merged)')"]
    sub_params = []
    if table_guid:
        sub_where_parts.append("g2.table_guid = ?")
        sub_params.append(table_guid)
    sub_where_clause = " AND ".join(sub_where_parts)

    query = f"""
        SELECT g.* FROM glossary_terms g
        WHERE {where_clause}
        AND g.version = (
            SELECT MAX(g2.version) FROM glossary_terms g2
            WHERE LOWER(g2.physical_term) = LOWER(g.physical_term)
            AND {sub_where_clause}
        )
        ORDER BY g.physical_term
    """
    all_params = params + sub_params
    rows = conn.execute(query, all_params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_all_table_summaries(source_filter=None, since=None):
    """Get summary of all tables in the database. If 'since' is set, only count terms stored after that timestamp."""
    conn = _get_conn()
    query = """
        SELECT table_guid, table_name,
               SUM(CASE WHEN active = 1 AND status != 'Rejected' THEN 1 ELSE 0 END) as active_terms,
               COUNT(*) as total_history,
               MAX(stored_at) as last_updated
        FROM glossary_terms
        WHERE 1=1
    """
    params = []
    if source_filter:
        query += " AND source = ?"
        params.append(source_filter)
    if since:
        query += " AND stored_at >= ?"
        params.append(since)
    query += " GROUP BY table_guid, table_name ORDER BY last_updated DESC"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_table_names_with_active_terms(source_filter=None):
    """Get table names that have at least one active approved term."""
    conn = _get_conn()
    query = """
        SELECT DISTINCT table_guid, table_name 
        FROM glossary_terms 
        WHERE active = 1 AND status != 'Rejected'
    """
    params = []
    if source_filter:
        query += " AND source = ?"
        params.append(source_filter)
    query += " ORDER BY table_name"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_next_version(physical_term, table_guid=None):
    """Get the next version number for a physical term within the same table."""
    conn = _get_conn()
    if table_guid:
        row = conn.execute("""
            SELECT MAX(version) as max_ver FROM glossary_terms
            WHERE LOWER(physical_term) = LOWER(?) AND table_guid = ?
        """, (physical_term, table_guid)).fetchone()
    else:
        row = conn.execute("""
            SELECT MAX(version) as max_ver FROM glossary_terms
            WHERE LOWER(physical_term) = LOWER(?)
        """, (physical_term,)).fetchone()
    conn.close()
    return (row["max_ver"] or 0) + 1


def fix_duplicate_versions():
    """Fix any physical terms that have duplicate/incorrect version numbers, scoped per table_guid + physical_term."""
    conn = _get_conn()
    groups = conn.execute("""
        SELECT table_guid, physical_term
        FROM glossary_terms
        GROUP BY table_guid, LOWER(physical_term)
        HAVING COUNT(*) > 1
    """).fetchall()
    fixed = 0
    for g in groups:
        rows = conn.execute("""
            SELECT id, version FROM glossary_terms
            WHERE table_guid = ? AND LOWER(physical_term) = LOWER(?)
            ORDER BY stored_at ASC, id ASC
        """, (g["table_guid"], g["physical_term"])).fetchall()
        needs_fix = any(rows[i]["version"] != i + 1 for i in range(len(rows)))
        if needs_fix:
            for seq, row in enumerate(rows, start=1):
                conn.execute("UPDATE glossary_terms SET version = ? WHERE id = ?", (seq, row["id"]))
                fixed += 1
    if fixed:
        conn.commit()
    conn.close()
    return fixed


def sync_from_audit_log(audit_log_path):
    """Rebuild SQLite DB from audit_log.json if DB is empty but audit log has data."""
    if not os.path.exists(audit_log_path):
        return 0
    try:
        with open(audit_log_path, 'r') as f:
            audit_log = json.load(f)
    except (json.JSONDecodeError, IOError):
        return 0

    if not audit_log:
        return 0

    conn = _get_conn()
    count = conn.execute("SELECT COUNT(*) as cnt FROM glossary_terms").fetchone()["cnt"]
    if count > 0:
        conn.close()
        return 0  # Already has data

    # Process all decided entries from audit log
    decided = sorted(
        [e for e in audit_log if e.get("status") in ("Approved", "Approved (Merged)", "Rejected")],
        key=lambda x: x.get("decision_date", ""),
    )

    imported = 0
    for entry in decided:
        raw_table = (entry.get("table_name") or "").strip()
        safe_table = raw_table.replace(" ", "_").replace("/", "_") if raw_table else ""
        asset_guid = f"workflow_{safe_table.upper()}" if safe_table else f"workflow_{entry.get('term_id', 'unknown')}"
        table_name = raw_table.upper() if raw_table else "Workflow Terms"
        phys_term = entry.get("physical_term") or entry.get("term_name") or ""
        is_approved = entry.get("status") in ("Approved", "Approved (Merged)")

        # Deactivate previous active record for this physical term in same table (SCD Type 2)
        if is_approved:
            conn.execute("""
                UPDATE glossary_terms 
                SET active = 0 
                WHERE table_guid = ? AND LOWER(physical_term) = LOWER(?) AND active = 1
            """, (asset_guid, phys_term))

        # Get next version scoped to this table
        row = conn.execute("""
            SELECT MAX(version) as max_ver FROM glossary_terms
            WHERE LOWER(physical_term) = LOWER(?) AND table_guid = ?
        """, (phys_term, asset_guid)).fetchone()
        next_ver = (row["max_ver"] or 0) + 1

        conn.execute("""
            INSERT INTO glossary_terms 
            (entity_guid, table_guid, table_name, business_term, physical_term,
             description, classification, type, source, confidence, active, version, status, stored_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            entry.get("term_id", ""),
            asset_guid,
            table_name,
            entry.get("term_name", ""),
            phys_term,
            entry.get("definition", ""),
            entry.get("classification", ""),
            entry.get("term_type", "Column"),
            entry.get("source", "MS Purview"),
            entry.get("confidence_score", 0),
            1 if is_approved else 0,
            next_ver,
            entry.get("status", ""),
            entry.get("decision_date", datetime.now().isoformat()),
        ))
        imported += 1

    conn.commit()
    conn.close()
    return imported


def sync_from_master_json(master_path):
    """One-time migration: import existing glossary_master.json into SQLite."""
    if not os.path.exists(master_path):
        return 0
    try:
        with open(master_path, 'r') as f:
            master = json.load(f)
    except (json.JSONDecodeError, IOError):
        return 0

    if not master:
        return 0

    conn = _get_conn()
    # Check if DB already has data
    count = conn.execute("SELECT COUNT(*) as cnt FROM glossary_terms").fetchone()["cnt"]
    if count > 0:
        conn.close()
        return 0  # Already migrated

    imported = 0
    for table_guid, records in master.items():
        for r in records:
            conn.execute("""
                INSERT INTO glossary_terms 
                (entity_guid, table_guid, table_name, business_term, physical_term,
                 description, type, source, confidence, active, version, status, stored_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                r.get("entity_guid", ""),
                table_guid,
                r.get("table_name", ""),
                r.get("Business Term", ""),
                r.get("Physical Term", ""),
                r.get("Definition / Description", ""),
                r.get("Type", "Column"),
                r.get("Source", "AI Suggester"),
                r.get("Confidence (%)", 0),
                r.get("Active", 0),
                r.get("Version", 1),
                r.get("Status", "Approved" if r.get("Active") == 1 else "Historical"),
                r.get("Stored At", datetime.now().isoformat()),
            ))
            imported += 1

    conn.commit()
    conn.close()
    return imported


def get_ai_coverage_stats():
    """Return (ai_term_count, total_term_count) for active approved terms."""
    conn = _get_conn()
    row = conn.execute("""
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN source IN ('AI Suggester', 'MS Purview', 'Databricks Unity Catalog') THEN 1 ELSE 0 END) as ai_count
        FROM glossary_terms
        WHERE active = 1 AND status NOT IN ('Rejected')
    """).fetchone()
    conn.close()
    return (row["ai_count"] or 0, row["total"] or 0)


def get_active_glossary_terms_for_lineage():
    """Return distinct active glossary terms with status='Approved' or 'Approved (Merged)' for lineage dropdown."""
    conn = _get_conn()
    rows = conn.execute("""
        SELECT DISTINCT business_term
        FROM glossary_terms
        WHERE active = 1 AND status IN ('Approved', 'Approved (Merged)')
        AND business_term IS NOT NULL AND business_term != ''
        ORDER BY business_term
    """).fetchall()
    conn.close()
    return [r["business_term"] for r in rows]


def check_approved_term_exists(term_name, physical_term=None):
    """Check if a same/similar term is already approved. Returns list of matching approved terms with max version."""
    conn = _get_conn()
    results = []
    # Match by business term name
    rows = conn.execute("""
        SELECT business_term, physical_term, MAX(version) as version, status, source
        FROM glossary_terms
        WHERE status IN ('Approved', 'Approved (Merged)')
        AND LOWER(business_term) = LOWER(?)
        GROUP BY LOWER(business_term), LOWER(physical_term)
    """, (term_name.strip(),)).fetchall()
    results.extend([dict(r) for r in rows])
    # Also match by physical term if provided
    if physical_term and physical_term.strip():
        phys_rows = conn.execute("""
            SELECT business_term, physical_term, MAX(version) as version, status, source
            FROM glossary_terms
            WHERE status IN ('Approved', 'Approved (Merged)')
            AND LOWER(physical_term) = LOWER(?)
            GROUP BY LOWER(business_term), LOWER(physical_term)
        """, (physical_term.strip(),)).fetchall()
        seen = {(r['business_term'].lower(), r['physical_term'].lower()) for r in results}
        for r in phys_rows:
            if (r['business_term'].lower(), r['physical_term'].lower()) not in seen:
                results.append(dict(r))
    conn.close()
    return results


# Initialize DB on import
init_db()
