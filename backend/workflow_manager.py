"""
Glossary Management Workflow Manager
Implements the full AI Suggestion → Approval Queue → Glossary Hub pipeline.

Tables / Stores:
  - ai_suggested_terms   → backend/ai_suggested_terms.json
  - approval_queue       → backend/approval_queue.json
  - glossary_hub         → backend/glossary_master.json  (shared with PersistenceManager)

API:
  - createSuggestedTerm()
  - checkConflictWithHub()
  - approveTerm()
  - rejectTerm()
  - triggerPowerAutomate()
"""

import json
import os
import uuid
import smtplib
from datetime import datetime
from difflib import SequenceMatcher
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from backend import glossary_db

# ── Storage paths ──────────────────────────────────────────────────────────────
SUGGESTED_TERMS_STORE = "backend/ai_suggested_terms.json"
APPROVAL_QUEUE_STORE  = "backend/approval_queue.json"
MASTER_STORE          = "backend/glossary_master.json"
AUDIT_LOG_STORE       = "backend/audit_log.json"


class WorkflowManager:
    # ──────────────────────────────────────────────────────────────────────────
    # Internal helpers
    # ──────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _load(path):
        if not os.path.exists(path):
            return []
        try:
            with open(path, "r") as f:
                return json.load(f)
        except Exception:
            return []

    @staticmethod
    def _save(path, data):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            json.dump(data, f, indent=4)

    @classmethod
    def _load_master(cls):
        if not os.path.exists(MASTER_STORE):
            return {}
        try:
            with open(MASTER_STORE, "r") as f:
                return json.load(f)
        except Exception:
            return {}

    @classmethod
    def _save_master(cls, data):
        os.makedirs(os.path.dirname(MASTER_STORE), exist_ok=True)
        with open(MASTER_STORE, "w") as f:
            json.dump(data, f, indent=4)

    # ──────────────────────────────────────────────────────────────────────────
    # Public load helpers
    # ──────────────────────────────────────────────────────────────────────────

    @classmethod
    def load_suggested_terms(cls):
        """Load all AI-suggested terms."""
        return cls._load(SUGGESTED_TERMS_STORE)

    @classmethod
    def load_audit_log(cls):
        return cls._load(AUDIT_LOG_STORE)

    @classmethod
    def _append_audit_log(cls, entry, final_status, approver_comment):
        """
        Append a decision record to the persistent audit log.
        Every action is recorded. Only skips exact duplicate (same term_id + same status).
        """
        log = cls.load_audit_log()
        # Only skip if the exact same term_id already has this exact status
        already = any(
            e.get("term_id") == entry.get("term_id")
            and e.get("status") == final_status
            for e in log
        )
        if already:
            return
        log.append({
            "term_id":          entry.get("term_id"),
            "term_name":        entry.get("term_name"),
            "definition":       entry.get("definition"),
            "source":           entry.get("source"),
            "confidence_score": entry.get("confidence_score"),
            "table_name":       entry.get("table_name", ""),
            "physical_term":    entry.get("physical_term") or entry.get("related_column") or "",
            "term_type":        entry.get("term_type", "Column"),
            "conflict_found":   entry.get("conflict_found", False),
            "status":           final_status,
            "approver_comment": approver_comment,
            "decision_date":    datetime.now().isoformat(),
        })
        cls._save(AUDIT_LOG_STORE, log)

    @classmethod
    def _update_audit_log_status(cls, term_name, new_status, approver_comment=None, new_term_id=None, new_definition=None):
        """
        Find the existing audit log row for term_name and update its status in-place.
        Optionally updates term_id, definition, approver_comment and decision_date.
        Used by approve_with_merge to avoid a duplicate row.
        """
        log = cls.load_audit_log()
        name_lower = (term_name or "").strip().lower()
        for row in log:
            if (row.get("term_name") or "").strip().lower() == name_lower:
                row["status"] = new_status
                row["decision_date"] = datetime.now().isoformat()
                if new_status == "Approved (Merged)":
                    row["conflict_found"] = True
                if approver_comment is not None:
                    row["approver_comment"] = approver_comment
                if new_term_id is not None:
                    row["term_id"] = new_term_id
                if new_definition is not None:
                    row["definition"] = new_definition
                break
        cls._save(AUDIT_LOG_STORE, log)

    @classmethod
    def _rebuild_master_from_audit_log(cls):
        """
        Rebuild glossary_master.json from audit_log.json (Approved + Rejected entries).
        The Glossary Hub is always 100% derived from the audit log — no other write path.
        Entries are processed in chronological order so SCD Type 2 versioning is correct.
        Rejected entries are stored with Active=0 to preserve full decision history.
        """
        audit_log = cls.load_audit_log()
        # All decided entries (Approved, Approved (Merged), Rejected), oldest first
        decided = sorted(
            [e for e in audit_log if e.get("status") in ("Approved", "Approved (Merged)", "Rejected")],
            key=lambda x: x.get("decision_date", ""),
        )

        master = {}
        for entry in decided:
            raw_table  = (entry.get("table_name") or "").strip()
            safe_table = raw_table.replace(" ", "_").replace("/", "_") if raw_table else None
            # Normalise key to uppercase to avoid case-sensitive duplicates
            asset_guid = f"workflow_{safe_table.upper()}" if safe_table else f"workflow_{entry.get('term_id', 'unknown')}"
            table_name = raw_table.upper() if raw_table else "Workflow Approved Terms"

            if asset_guid not in master:
                master[asset_guid] = []

            bucket = master[asset_guid]
            entry_phys = (entry.get("physical_term") or entry.get("term_name") or "").strip().lower()
            entry_biz = (entry.get("term_name") or "").strip().lower()
            entry_status = entry.get("status", "")
            is_approved = entry_status in ("Approved", "Approved (Merged)")

            # SCD Type 2: deactivate any active record in this bucket that shares
            # the same Physical Term OR same Business Term (only when new entry is approved)
            if is_approved:
                for r in bucket:
                    r_phys = (r.get("Physical Term") or "").strip().lower()
                    r_biz = (r.get("Business Term") or "").strip().lower()
                    if (r_phys and r_phys == entry_phys) or (r_biz and r_biz == entry_biz):
                        r["Active"] = 0

            # Version = count of all records for this physical term + 1
            same = [r for r in bucket
                    if (r.get("Physical Term") or "").strip().lower() == entry_phys]
            next_version = len(same) + 1
            bucket.append({
                "entity_guid":              entry.get("term_id"),
                "table_guid":               asset_guid,
                "table_name":               table_name,
                "Business Term":            entry.get("term_name"),
                "Physical Term":            entry.get("physical_term") or entry.get("term_name"),
                "Definition / Description": entry.get("definition"),
                "Type":                     entry.get("term_type", "Column"),
                "Source":                   entry.get("source", "Manual"),
                "Confidence (%)":           entry.get("confidence_score", 0),
                "Active":                   1 if is_approved else 0,
                "Version":                  next_version,
                "Stored At":               entry.get("decision_date", datetime.now().isoformat()),
                "Status":                   entry_status,
            })

        cls._save_master(master)
        return master

    @classmethod
    def load_approval_queue(cls):
        """Load the full approval queue."""
        return cls._load(APPROVAL_QUEUE_STORE)

    # ──────────────────────────────────────────────────────────────────────────
    # 1. createSuggestedTerm()
    # ──────────────────────────────────────────────────────────────────────────

    @classmethod
    def create_suggested_term(cls, term_name, definition, source="Manual", confidence_score=80, table_name="", term_type="Column", physical_term=""):
        """
        Creates a new AI-suggested term and adds it to both:
          - ai_suggested_terms store
          - approval_queue with status 'Pending'

        Prevents duplicates: if a term with the same name already exists in
        Pending or Conflict Detected state, returns its existing term_id.

        Returns the generated (or existing) term_id.
        """
        # Deduplication: skip if same (term_name, table_name) is already queued and not yet decided
        _tname  = term_name.strip().lower()
        _tbl    = (table_name or "").strip().lower()
        queue = cls.load_approval_queue()
        existing = next(
            (
                e for e in queue
                if e.get("term_name", "").strip().lower() == _tname
                and e.get("table_name", "").strip().lower() == _tbl
                and e.get("status") in ("Pending", "Conflict Detected")
            ),
            None,
        )
        if existing:
            return existing["term_id"]

        now      = datetime.now().isoformat()
        term_id  = str(uuid.uuid4())

        term = {
            "term_id":          term_id,
            "term_name":        term_name.strip(),
            "definition":       definition.strip(),
            "source":           source,
            "confidence_score": int(confidence_score),
            "created_date":     now,
            "table_name":       table_name.strip() if table_name else "",
            "term_type":        term_type,
            "physical_term":    physical_term.strip() if physical_term else "",
        }

        # Persist to ai_suggested_terms — deduplicate by (term_name, table_name)
        suggested = cls.load_suggested_terms()
        already_suggested = any(
            s.get("term_name", "").strip().lower() == _tname
            and s.get("table_name", "").strip().lower() == _tbl
            for s in suggested
        )
        if not already_suggested:
            suggested.append(term)
            cls._save(SUGGESTED_TERMS_STORE, suggested)

        # Add entry to approval_queue
        queue_entry = {
            **term,
            "status":              "Pending",
            "conflict_checked":    False,
            "conflict_found":      False,
            "conflict_match_type": None,
            "existing_term_id":    None,
            "existing_term_name":  None,
            "approver_comment":    "",
            "decision_date":       None,
        }
        queue.append(queue_entry)
        cls._save(APPROVAL_QUEUE_STORE, queue)

        # Immediately run a fresh conflict check so the KPI card and queue status
        # reflect any conflicts as soon as the term lands in the queue.
        cls.run_conflict_check(term_id)

        return term_id

    # ──────────────────────────────────────────────────────────────────────────
    # 2. checkConflictWithHub()
    # ──────────────────────────────────────────────────────────────────────────

    @classmethod
    def check_conflict_with_hub(cls, term_name, source_filter=None, table_name=None, physical_term=None):
        """
        Checks if term_name already exists in the Glossary Hub (master store).
        When source_filter is set (e.g. "Databricks Unity Catalog"), only active
        records matching that Source are checked — keeps UC and Purview glossaries isolated.

        Match logic (in priority order):
          1. Same table_name + same Business Term + same Physical Term (column) → exact duplicate, merge
          2. Same table_name + same Physical Term (column) → column already mapped
          3. Exact term_name match (case-insensitive)
          4. Fuzzy match with similarity >= 0.85

        Returns:
            (conflict_found: bool, existing_term_id: str|None,
             existing_term_name: str|None, match_type: str)
        """
        master     = cls._load_master()
        term_lower = term_name.strip().lower()
        table_lower = (table_name or "").strip().lower()
        phys_lower = (physical_term or "").strip().lower()

        # Priority 1: exact match on table_name + Business Term + Physical Term
        if table_lower and phys_lower and term_lower:
            for asset_guid, records in master.items():
                for record in records:
                    if record.get("Active") != 1:
                        continue
                    if source_filter and record.get("Source") != source_filter:
                        continue
                    r_table = (record.get("table_name") or "").strip().lower()
                    r_biz = (record.get("Business Term") or "").strip().lower()
                    r_phys = (record.get("Physical Term") or "").strip().lower()
                    if r_table == table_lower and r_biz == term_lower and r_phys == phys_lower:
                        return (
                            True,
                            record.get("entity_guid", asset_guid),
                            record.get("Business Term"),
                            "Exact Duplicate — Use Merge",
                        )

        # Priority 2: same table + same column but different/any business term
        if table_lower and phys_lower:
            for asset_guid, records in master.items():
                for record in records:
                    if record.get("Active") != 1:
                        continue
                    if source_filter and record.get("Source") != source_filter:
                        continue
                    r_table = (record.get("table_name") or "").strip().lower()
                    r_phys = (record.get("Physical Term") or "").strip().lower()
                    if r_table == table_lower and r_phys == phys_lower:
                        return (
                            True,
                            record.get("entity_guid", asset_guid),
                            record.get("Business Term"),
                            "Column Already Mapped",
                        )

        # Priority 3 & 4: Exact / fuzzy name match — ONLY within the SAME table
        # If the term is from a different table, it is NOT a conflict
        for asset_guid, records in master.items():
            for record in records:
                if record.get("Active") != 1:
                    continue
                if source_filter and record.get("Source") != source_filter:
                    continue
                # Skip records from a different table
                r_table = (record.get("table_name") or "").strip().lower()
                if table_lower and r_table and r_table != table_lower:
                    continue

                for field in ["Business Term", "Physical Term", "Original Name",
                               "Glossary Term", "name"]:
                    existing = record.get(field, "")
                    if not existing:
                        continue
                    existing_lower = str(existing).strip().lower()

                    # Exact match
                    if existing_lower == term_lower:
                        return (
                            True,
                            record.get("entity_guid", asset_guid),
                            str(existing),
                            "Exact Match",
                        )

                    # Fuzzy match
                    ratio = SequenceMatcher(None, term_lower, existing_lower).ratio()
                    if ratio >= 0.85:
                        return (
                            True,
                            record.get("entity_guid", asset_guid),
                            str(existing),
                            f"Fuzzy Match ({int(ratio * 100)}%)",
                        )

        return False, None, None, "No Conflict"

    # ──────────────────────────────────────────────────────────────────────────
    # Internal queue helper
    # ──────────────────────────────────────────────────────────────────────────

    @classmethod
    def _update_queue_entry(cls, term_id, updates):
        queue = cls.load_approval_queue()
        for entry in queue:
            if entry["term_id"] == term_id:
                entry.update(updates)
                break
        cls._save(APPROVAL_QUEUE_STORE, queue)

    @classmethod
    def run_conflict_check(cls, term_id):
        """
        Run a fresh conflict check for a specific term and update its queue entry.
        When the term's source is "Databricks Unity Catalog", all checks are scoped
        to UC-sourced records only — keeping UC and Purview glossaries isolated.

        Checks (in priority order):
          1. Glossary Hub (master store) — exact / fuzzy name match
          2. Audit log — same business term already Approved (must use Merge)
          3. Audit log — same physical_term + table_name but DIFFERENT business term
             already Approved (Different Business Term Already Approved)

        Sets status to 'Conflict Detected' if any conflict is found.
        Always resets conflict_checked = True so the result is always fresh.

        Returns: (conflict_found: bool, match_type: str)
        """
        queue = cls.load_approval_queue()
        entry = next((e for e in queue if e["term_id"] == term_id), None)
        if not entry:
            return False, "Term not found"

        term_name  = entry.get("term_name", "")
        name_lower = term_name.strip().lower()
        physical   = (entry.get("physical_term") or entry.get("related_column") or "").strip().lower()
        table      = (entry.get("table_name") or "").strip().lower()

        # Determine source isolation scope
        entry_source  = entry.get("source", "")
        source_filter = entry_source if entry_source == "Databricks Unity Catalog" else None

        conflict_found = False
        existing_id    = None
        existing_name  = None
        match_type     = "No Conflict"

        # Load audit log once
        audit_log = cls.load_audit_log()
        if source_filter:
            audit_log = [e for e in audit_log if e.get("source") == source_filter]

        # ── Check 1: same connector + same table + same column + SAME business term
        #    → conflict (merge only)
        if physical and table:
            same_col_same_term = next(
                (
                    e for e in audit_log
                    if e.get("status") in ("Approved", "Approved (Merged)")
                    and (e.get("physical_term") or "").strip().lower() == physical
                    and (e.get("table_name") or "").strip().lower() == table
                    and (e.get("source") or "") == entry_source
                    and (e.get("term_name") or "").strip().lower() == name_lower
                ),
                None,
            )
            if same_col_same_term:
                conflict_found = True
                existing_id    = same_col_same_term.get("term_id")
                existing_name  = same_col_same_term.get("term_name")
                match_type     = "Already Approved — Use Merge"

        # ── Check 2: same connector + same table + same column + DIFFERENT business term
        #    → conflict (all options: approve, reject, merge)
        if not conflict_found and physical and table:
            diff_term = next(
                (
                    e for e in audit_log
                    if e.get("status") in ("Approved", "Approved (Merged)")
                    and (e.get("physical_term") or "").strip().lower() == physical
                    and (e.get("table_name") or "").strip().lower() == table
                    and (e.get("source") or "") == entry_source
                    and (e.get("term_name") or "").strip().lower() != name_lower
                ),
                None,
            )
            if diff_term:
                conflict_found = True
                existing_id    = diff_term.get("term_id")
                existing_name  = diff_term.get("term_name")
                match_type     = "Different Business Term Already Approved"

        # ── Check 3: Glossary Hub (master store) — exact/fuzzy name match ────
        if not conflict_found:
            hub_conflict, hub_id, hub_name, hub_match = cls.check_conflict_with_hub(
                term_name, source_filter=source_filter,
                table_name=entry.get("table_name", ""),
                physical_term=entry.get("physical_term") or entry.get("related_column") or ""
            )
            if hub_conflict:
                conflict_found = True
                existing_id    = hub_id
                existing_name  = hub_name
                match_type     = hub_match

        updates = {
            "conflict_checked":    True,
            "conflict_found":      conflict_found,
            "existing_term_id":    existing_id,
            "existing_term_name":  existing_name,
            "conflict_match_type": match_type,
        }
        if conflict_found:
            updates["status"] = "Conflict Detected"
        else:
            # Reset to Pending if a previous check had flagged it but now it's clean
            if entry.get("status") == "Conflict Detected":
                updates["status"] = "Pending"

        cls._update_queue_entry(term_id, updates)
        return conflict_found, match_type

    @classmethod
    def _recheck_pending_conflicts(cls):
        """
        Re-run conflict checks on all remaining Pending/Conflict Detected entries.
        Called after approve/merge to update conflict counts accurately.
        """
        queue = cls.load_approval_queue()
        for entry in queue:
            if entry.get("status") in ("Pending", "Conflict Detected"):
                cls.run_conflict_check(entry["term_id"])

    # ──────────────────────────────────────────────────────────────────────────
    # 3. approveTerm()
    # ──────────────────────────────────────────────────────────────────────────

    @classmethod
    def approve_term(cls, term_id, approver_comment=""):
        """
        Approve a term:
          1. Audit log is written first (source of truth)
          2. Glossary Hub is rebuilt from the audit log
          3. Queue status updated

        Returns: (success: bool, message: str)
        """
        queue = cls.load_approval_queue()
        entry = next((e for e in queue if e["term_id"] == term_id), None)
        if not entry:
            return False, "Term not found in queue"

        # Block if this exact term (same name + same physical_term + same table) already Approved
        audit_log = cls.load_audit_log()
        entry_name = (entry.get("term_name") or "").strip().lower()
        entry_phys = (entry.get("physical_term") or "").strip().lower()
        entry_table = (entry.get("table_name") or "").strip().lower()
        entry_source = entry.get("source", "")
        prior = next(
            (e for e in audit_log
             if e.get("status") in ("Approved", "Approved (Merged)")
             and (e.get("term_name") or "").strip().lower() == entry_name
             and (e.get("physical_term") or "").strip().lower() == entry_phys
             and (e.get("table_name") or "").strip().lower() == entry_table
             and (e.get("source") or "") == entry_source),
            None,
        )
        if prior:
            cls._update_queue_entry(term_id, {
                "status":              "Conflict Detected",
                "conflict_found":      True,
                "conflict_checked":    True,
                "conflict_match_type": "Already approved in audit log",
                "existing_term_name":  prior.get("term_name"),
                "existing_term_id":    prior.get("term_id"),
            })
            return False, f"Term '{entry.get('term_name')}' was already approved. Use Merge to update it."

        # 1. Write to audit log FIRST (source of truth)
        cls._append_audit_log(entry, "Approved", approver_comment)

        # 2. Rebuild Glossary Hub entirely from audit log
        cls._rebuild_master_from_audit_log()

        # 3. Store in SQLite database for permanent persistence
        raw_table = (entry.get("table_name") or "").strip()
        safe_table = raw_table.replace(" ", "_").replace("/", "_") if raw_table else ""
        asset_guid = f"workflow_{safe_table.upper()}" if safe_table else f"workflow_{term_id}"
        phys_term = entry.get("physical_term") or entry.get("term_name") or ""
        biz_term = entry.get("term_name") or ""
        # Deactivate previous active record for this physical term
        glossary_db.deactivate_term(asset_guid, phys_term)
        # Deactivate previous active record for this business term name
        glossary_db.deactivate_by_business_term(asset_guid, biz_term)
        next_ver = glossary_db.get_next_version(asset_guid, phys_term)
        glossary_db.store_term(
            entity_guid=term_id,
            table_guid=asset_guid,
            table_name=raw_table.upper() if raw_table else "Workflow Approved Terms",
            business_term=entry.get("term_name", ""),
            physical_term=phys_term,
            description=entry.get("definition", ""),
            term_type=entry.get("term_type", "Column"),
            source=entry.get("source", "AI Suggester"),
            confidence=entry.get("confidence_score", 0),
            active=1,
            version=next_ver,
            status="Approved",
        )

        # 4. Update queue entry
        cls._update_queue_entry(term_id, {
            "status":           "Approved",
            "approver_comment": approver_comment,
            "decision_date":    datetime.now().isoformat(),
        })

        # 5. Re-run conflict checks on remaining pending entries
        cls._recheck_pending_conflicts()

        return True, "Term approved and added to Glossary Hub"

    # ──────────────────────────────────────────────────────────────────────────
    # 4. rejectTerm()
    # ──────────────────────────────────────────────────────────────────────────

    @classmethod
    def reject_term(cls, term_id, approver_comment=""):
        """
        Reject a term:
          1. Updates queue status → 'Rejected'
          2. Writes to audit log
          3. Rebuilds Glossary Hub to include rejection history

        Returns: (success: bool, message: str)
        """
        queue = cls.load_approval_queue()
        entry = next((e for e in queue if e["term_id"] == term_id), None)
        if not entry:
            return False, "Term not found in queue"

        cls._update_queue_entry(term_id, {
            "status":           "Rejected",
            "approver_comment": approver_comment,
            "decision_date":    datetime.now().isoformat(),
        })

        # Persist to audit log
        cls._append_audit_log(entry, "Rejected", approver_comment)

        # Rebuild Glossary Hub to include rejection history
        cls._rebuild_master_from_audit_log()

        # Store rejection in SQLite database for permanent history
        raw_table = (entry.get("table_name") or "").strip()
        safe_table = raw_table.replace(" ", "_").replace("/", "_") if raw_table else ""
        asset_guid = f"workflow_{safe_table.upper()}" if safe_table else f"workflow_{term_id}"
        phys_term = entry.get("physical_term") or entry.get("term_name") or ""
        next_ver = glossary_db.get_next_version(asset_guid, phys_term)
        glossary_db.store_term(
            entity_guid=term_id,
            table_guid=asset_guid,
            table_name=raw_table.upper() if raw_table else "Workflow Terms",
            business_term=entry.get("term_name", ""),
            physical_term=phys_term,
            description=entry.get("definition", ""),
            term_type=entry.get("term_type", "Column"),
            source=entry.get("source", "AI Suggester"),
            confidence=entry.get("confidence_score", 0),
            active=0,
            version=next_ver,
            status="Rejected",
        )

        return True, "Term rejected"

    # ──────────────────────────────────────────────────────────────────────────
    # Rejection email
    # ──────────────────────────────────────────────────────────────────────────

    @classmethod
    def send_rejection_email(cls, entry, approver_comment=""):
        """
        Send a rejection notification email to the fixed recipient.
        SMTP credentials are read from Streamlit secrets:

            [email]
            smtp_host     = "smtp.gmail.com"
            smtp_port     = 587
            sender_email  = "your-sender@example.com"
            sender_password = "your-app-password"

        Returns (success: bool, message: str).
        """
        RECIPIENT = "jeevika.palanivelu@ilink-systems.com"

        try:
            import streamlit as st
            cfg          = st.secrets.get("email", {})
            smtp_host    = cfg.get("smtp_host",      "smtp.gmail.com")
            smtp_port    = int(cfg.get("smtp_port",  587))
            sender_email = cfg.get("sender_email",   "")
            sender_pass  = cfg.get("sender_password","")
        except Exception:
            # Outside Streamlit context (e.g. unit tests) – skip silently
            return False, "Streamlit secrets unavailable"

        if not sender_email or not sender_pass:
            return False, "Email credentials not configured in .streamlit/secrets.toml"

        term_name  = entry.get("term_name", "N/A")
        definition = entry.get("definition", "N/A")
        source     = entry.get("source", "N/A")
        score      = entry.get("confidence_score", "N/A")
        comment    = approver_comment or "No comment provided."
        timestamp  = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        subject = f"[GlossIQ] Term Rejected: {term_name}"

        html_body = f"""\
<html><body style="font-family:Arial,sans-serif;color:#111827;">
<div style="max-width:600px;margin:0 auto;border:1px solid #E5E7EB;border-radius:8px;overflow:hidden;">
  <div style="background:#CC0000;padding:20px 24px;">
    <h2 style="color:white;margin:0;">GlossIQ — Term Rejected</h2>
  </div>
  <div style="padding:24px;">
    <p>A glossary term has been <strong style="color:#EF4444;">rejected</strong> and requires your attention.</p>
    <table style="width:100%;border-collapse:collapse;margin-top:16px;">
      <tr style="background:#F9FAFB;"><td style="padding:10px 14px;font-weight:600;width:35%;">Term Name</td><td style="padding:10px 14px;">{term_name}</td></tr>
      <tr><td style="padding:10px 14px;font-weight:600;">Definition</td><td style="padding:10px 14px;">{definition}</td></tr>
      <tr style="background:#F9FAFB;"><td style="padding:10px 14px;font-weight:600;">Source</td><td style="padding:10px 14px;">{source}</td></tr>
      <tr><td style="padding:10px 14px;font-weight:600;">Confidence Score</td><td style="padding:10px 14px;">{score}%</td></tr>
      <tr style="background:#F9FAFB;"><td style="padding:10px 14px;font-weight:600;">Approver Comment</td><td style="padding:10px 14px;">{comment}</td></tr>
      <tr><td style="padding:10px 14px;font-weight:600;">Rejected At</td><td style="padding:10px 14px;">{timestamp}</td></tr>
    </table>
    <p style="margin-top:24px;font-size:13px;color:#6B7280;">This notification was generated automatically by GlossIQ. Log in to the <strong>Review &amp; Approval</strong> tab to take further action.</p>
  </div>
</div>
</body></html>"""

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = sender_email
        msg["To"]      = RECIPIENT
        msg.attach(MIMEText(html_body, "html"))

        try:
            with smtplib.SMTP(smtp_host, smtp_port, timeout=15) as server:
                server.ehlo()
                server.starttls()
                server.login(sender_email, sender_pass)
                server.sendmail(sender_email, [RECIPIENT], msg.as_string())
            return True, f"Rejection email sent to {RECIPIENT}"
        except smtplib.SMTPAuthenticationError:
            return False, "SMTP authentication failed — check sender_email / sender_password in secrets.toml"
        except Exception as exc:
            return False, f"Failed to send rejection email: {exc}"

    # ──────────────────────────────────────────────────────────────────────────
    # Approve with Merge
    # ──────────────────────────────────────────────────────────────────────────

    @classmethod
    def approve_with_merge(cls, term_id, approver_comment=""):
        """
        Approve and merge with an existing term already in the audit log.
        Updates the existing audit log row status to 'Approved (Merged)' in-place
        (no new row is added). Then rebuilds the Glossary Hub from the audit log.

        Returns: (success: bool, message: str)
        """
        queue = cls.load_approval_queue()
        entry = next((e for e in queue if e["term_id"] == term_id), None)
        if not entry:
            return False, "Term not found in queue"

        # 1. Update existing audit log row in-place (no new row)
        cls._update_audit_log_status(
            term_name=entry.get("term_name"),
            new_status="Approved (Merged)",
            approver_comment=approver_comment,
            new_term_id=term_id,
            new_definition=entry.get("definition"),
        )

        # 2. Rebuild Glossary Hub from audit log
        cls._rebuild_master_from_audit_log()

        # 3. Store merged term in SQLite database
        raw_table = (entry.get("table_name") or "").strip()
        safe_table = raw_table.replace(" ", "_").replace("/", "_") if raw_table else ""
        asset_guid = f"workflow_{safe_table.upper()}" if safe_table else f"workflow_{term_id}"
        phys_term = entry.get("physical_term") or entry.get("term_name") or ""
        biz_term = entry.get("term_name") or ""
        glossary_db.deactivate_term(asset_guid, phys_term)
        # Deactivate previous active record for this business term name
        glossary_db.deactivate_by_business_term(asset_guid, biz_term)
        next_ver = glossary_db.get_next_version(asset_guid, phys_term)
        glossary_db.store_term(
            entity_guid=term_id,
            table_guid=asset_guid,
            table_name=raw_table.upper() if raw_table else "Workflow Approved Terms",
            business_term=entry.get("term_name", ""),
            physical_term=phys_term,
            description=entry.get("definition", ""),
            term_type=entry.get("term_type", "Column"),
            source=entry.get("source", "AI Suggester"),
            confidence=entry.get("confidence_score", 0),
            active=1,
            version=next_ver,
            status="Approved (Merged)",
        )

        # 4. Update queue entry
        cls._update_queue_entry(term_id, {
            "status":           "Approved (Merged)",
            "approver_comment": approver_comment,
            "decision_date":    datetime.now().isoformat(),
        })

        # 5. Re-run conflict checks on remaining pending entries
        cls._recheck_pending_conflicts()

        return True, "Term merged — existing audit log record updated to Approved (Merged)"

    # ──────────────────────────────────────────────────────────────────────────
    # Stats helper
    # ──────────────────────────────────────────────────────────────────────────

    @classmethod
    def get_queue_stats(cls, source_filter=None, session_start=None):
        """
        Return a dict of {status: count} for the KPI cards.
        When source_filter is set, counts are restricted to entries matching that source.
        When session_start is set, decided counts (Approved/Rejected/Merged) only include
        entries decided after that timestamp (ISO format).

        Source of truth:
          - "Pending" and "Conflict Detected" → approval queue
            (these terms have not been decided yet and are NOT in the audit log)
          - "Approved", "Approved (Merged)", "Rejected" → audit log
            (decided entries are written to the audit log on decision)
        """
        queue = cls.load_approval_queue()
        audit_log = cls.load_audit_log()

        if source_filter:
            queue     = [e for e in queue     if e.get("source") == source_filter]
            audit_log = [e for e in audit_log if e.get("source") == source_filter]

        # Filter audit log to only include decisions from current session
        if session_start:
            audit_log = [e for e in audit_log if (e.get("decision_date") or "") >= session_start]

        stats = {
            "Pending":           sum(1 for e in queue if e.get("status") == "Pending"),
            "Conflict Detected": sum(1 for e in queue if e.get("status") == "Conflict Detected"),
            "Approved":          sum(1 for e in audit_log if e.get("status") == "Approved"),
            "Approved (Merged)": sum(1 for e in audit_log if e.get("status") == "Approved (Merged)"),
            "Rejected":          sum(1 for e in audit_log if e.get("status") == "Rejected"),
        }
        return stats

    @classmethod
    def clear_ai_suggested_terms(cls, source="AI Suggester"):
        """
        Remove all entries matching `source` from ai_suggested_terms store.
        Called before sending a fresh AI recommendation batch so the store
        only contains the currently selected terms.
        Returns count of removed entries.
        """
        suggested = cls.load_suggested_terms()
        before    = len(suggested)
        suggested = [s for s in suggested if s.get("source") != source]
        removed   = before - len(suggested)
        if removed:
            cls._save(SUGGESTED_TERMS_STORE, suggested)
        return removed

    @classmethod
    def clear_ai_pending_from_queue(cls, source="AI Suggester"):
        """
        Remove all entries matching `source` with status Pending or Conflict Detected
        from the approval queue. Called before sending a fresh recommendation batch
        so the queue only contains the currently selected terms.
        Returns count of removed entries.
        """
        queue  = cls.load_approval_queue()
        before = len(queue)
        queue  = [
            e for e in queue
            if not (
                e.get("source") == source
                and e.get("status") in ("Pending", "Conflict Detected")
            )
        ]
        removed = before - len(queue)
        if removed:
            cls._save(APPROVAL_QUEUE_STORE, queue)
        return removed

    @classmethod
    def remove_from_queue_by_name(cls, term_name):
        """
        Remove a term from the approval queue by name (case-insensitive).
        Only removes entries that are still undecided (Pending / Conflict Detected).
        Returns True if anything was removed.
        """
        queue   = cls.load_approval_queue()
        before  = len(queue)
        queue   = [
            e for e in queue
            if not (
                e.get("term_name", "").strip().lower() == term_name.strip().lower()
                and e.get("status") in ("Pending", "Conflict Detected")
            )
        ]
        if len(queue) < before:
            cls._save(APPROVAL_QUEUE_STORE, queue)
            return True
        return False

    @classmethod
    def purge_decided_from_queue(cls):
        """
        Remove all decided entries (Approved / Approved (Merged) / Rejected)
        from the approval_queue store. They are already visible in the Audit Log.
        Returns count of removed entries.
        """
        queue   = cls.load_approval_queue()
        active  = [e for e in queue if e.get("status") in ("Pending", "Conflict Detected")]
        removed = len(queue) - len(active)
        cls._save(APPROVAL_QUEUE_STORE, active)
        return removed

    @classmethod
    def purge_pending_from_queue(cls):
        """
        Remove all Pending / Conflict Detected entries from the approval queue.
        Called once per browser session so the queue starts empty and only fills
        with terms sent during the current session.
        Approved / Rejected entries in the audit log are untouched.
        Returns count of removed entries.
        """
        queue   = cls.load_approval_queue()
        decided = [e for e in queue if e.get("status") not in ("Pending", "Conflict Detected")]
        removed = len(queue) - len(decided)
        cls._save(APPROVAL_QUEUE_STORE, decided)
        return removed
