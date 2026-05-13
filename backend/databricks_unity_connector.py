"""
Databricks Unity Catalog Connector
Pushes approved glossary terms to Unity Catalog as table-level tags.

Tag format:
  key   = Physical Term (column name)
  value = Business Term

Author: Jeevika
"""

import requests
from urllib.parse import quote


class DatabricksUnityConnector:
    def __init__(self, workspace_url: str, token: str):
        """
        Parameters
        ----------
        workspace_url : str
            Databricks workspace URL, e.g. https://adb-xxxx.azuredatabricks.net
        token : str
            Personal Access Token (PAT) with Unity Catalog permissions.
        """
        self.workspace_url = workspace_url.rstrip("/")
        self.token = token.strip()

    def _headers(self):
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

    # ─────────────────────────────────────────────────────────────────────────
    # TEST CONNECTION
    # ─────────────────────────────────────────────────────────────────────────
    def test_connection(self):
        """Return (success: bool, message: str)."""
        url = f"{self.workspace_url}/api/2.1/unity-catalog/catalogs"
        try:
            r = requests.get(url, headers=self._headers(), timeout=15)
            if r.status_code == 200:
                catalogs = r.json().get("catalogs", [])
                names = [c.get("name", "") for c in catalogs[:3]]
                return True, f"Connected. Visible catalogs: {', '.join(names) or 'none'}"
            elif r.status_code == 401:
                return False, "Authentication failed — check your Personal Access Token."
            elif r.status_code == 403:
                return False, "Access denied — token lacks Unity Catalog permissions."
            else:
                return False, f"HTTP {r.status_code}: {r.text[:300]}"
        except requests.exceptions.ConnectionError:
            return False, f"Cannot reach workspace at {self.workspace_url}. Check the URL."
        except Exception as e:
            return False, str(e)

    # ─────────────────────────────────────────────────────────────────────────
    # SQL WAREHOUSE HELPERS
    # ─────────────────────────────────────────────────────────────────────────
    def list_sql_warehouses(self) -> tuple[list[dict], str]:
        """Return ([{id, name, state}, ...], error_msg)."""
        url = f"{self.workspace_url}/api/2.0/sql/warehouses"
        try:
            r = requests.get(url, headers=self._headers(), timeout=15)
            if r.status_code == 200:
                whs = [
                    {"id": w["id"], "name": w.get("name", w["id"]), "state": w.get("state", "")}
                    for w in r.json().get("warehouses", [])
                    if w.get("id")
                ]
                return whs, ""
            return [], f"HTTP {r.status_code}: {r.text[:200]}"
        except Exception as e:
            return [], str(e)

    def _execute_sql(self, warehouse_id: str, statement: str) -> tuple[bool, str]:
        """
        Execute a SQL statement via the SQL Statement Execution API.
        Returns (success: bool, error_msg: str).
        """
        import time
        url = f"{self.workspace_url}/api/2.0/sql/statements"
        payload = {
            "statement": statement,
            "warehouse_id": warehouse_id,
            "wait_timeout": "50s",
            "on_wait_timeout": "CANCEL",
        }
        try:
            r = requests.post(url, headers=self._headers(), json=payload, timeout=60)
            if r.status_code not in (200, 201):
                return False, f"HTTP {r.status_code}: {r.text[:300]}"
            body = r.json()
            state = body.get("status", {}).get("state", "")
            if state == "SUCCEEDED":
                return True, ""
            # Poll if still running
            stmt_id = body.get("statement_id")
            if state in ("RUNNING", "PENDING") and stmt_id:
                poll_url = f"{self.workspace_url}/api/2.0/sql/statements/{stmt_id}"
                for _ in range(30):
                    time.sleep(2)
                    pr = requests.get(poll_url, headers=self._headers(), timeout=15)
                    if pr.status_code == 200:
                        pstate = pr.json().get("status", {}).get("state", "")
                        if pstate == "SUCCEEDED":
                            return True, ""
                        if pstate in ("FAILED", "CANCELED", "CLOSED"):
                            err = pr.json().get("status", {}).get("error", {}).get("message", pstate)
                            return False, err
                return False, "Statement timed out after polling."
            err_msg = body.get("status", {}).get("error", {}).get("message", state)
            return False, err_msg or f"Unexpected state: {state}"
        except Exception as e:
            return False, str(e)

    # ─────────────────────────────────────────────────────────────────────────
    # BROWSE UNITY CATALOG
    # ─────────────────────────────────────────────────────────────────────────
    def list_catalogs(self) -> tuple[list[str], str]:
        """Return ([catalog_names], error_msg). error_msg is '' on success."""
        url = f"{self.workspace_url}/api/2.1/unity-catalog/catalogs"
        try:
            r = requests.get(url, headers=self._headers(), timeout=15)
            if r.status_code == 200:
                names = [c.get("name", "") for c in r.json().get("catalogs", []) if c.get("name")]
                return names, ""
            return [], f"HTTP {r.status_code}: {r.text[:200]}"
        except Exception as e:
            return [], str(e)

    def list_schemas(self, catalog_name: str) -> tuple[list[str], str]:
        """Return ([schema_names], error_msg)."""
        url = f"{self.workspace_url}/api/2.1/unity-catalog/schemas"
        try:
            r = requests.get(url, headers=self._headers(), params={"catalog_name": catalog_name}, timeout=15)
            if r.status_code == 200:
                names = [s.get("name", "") for s in r.json().get("schemas", []) if s.get("name")]
                return names, ""
            return [], f"HTTP {r.status_code}: {r.text[:200]}"
        except Exception as e:
            return [], str(e)

    def list_tables(self, catalog_name: str, schema_name: str) -> tuple[list[str], str]:
        """Return ([table_names], error_msg).  Names are short (no three-part prefix)."""
        url = f"{self.workspace_url}/api/2.1/unity-catalog/tables"
        try:
            r = requests.get(
                url, headers=self._headers(),
                params={"catalog_name": catalog_name, "schema_name": schema_name},
                timeout=20,
            )
            if r.status_code == 200:
                names = [t.get("name", "") for t in r.json().get("tables", []) if t.get("name")]
                return names, ""
            return [], f"HTTP {r.status_code}: {r.text[:200]}"
        except Exception as e:
            return [], str(e)

    def verify_table_exists(self, full_table_name: str) -> tuple[bool, str]:
        """
        Check whether a table exists in Unity Catalog.
        Returns (exists: bool, message: str).
        """
        encoded = quote(full_table_name, safe="")
        url = f"{self.workspace_url}/api/2.1/unity-catalog/tables/{encoded}"
        try:
            r = requests.get(url, headers=self._headers(), timeout=15)
            if r.status_code == 200:
                return True, ""
            elif r.status_code == 404:
                return False, (
                    f"Table '{full_table_name}' was not found via the Unity Catalog API. "
                    "Verify the catalog name, schema name, and table name are correct and "
                    "that your token has USE CATALOG + USE SCHEMA privileges."
                )
            elif r.status_code == 403:
                return False, f"Access denied when looking up '{full_table_name}'. Check USE CATALOG / USE SCHEMA privileges."
            else:
                return False, f"Unexpected HTTP {r.status_code} when verifying table: {r.text[:200]}"
        except Exception as e:
            return False, str(e)

    def _query_sql(self, warehouse_id: str, statement: str) -> tuple[list[dict], str]:
        """
        Execute a SQL SELECT and return (rows, error_msg).
        Each row is a dict keyed by column name.
        """
        import time
        url = f"{self.workspace_url}/api/2.0/sql/statements"
        payload = {
            "statement": statement,
            "warehouse_id": warehouse_id,
            "wait_timeout": "30s",
            "on_wait_timeout": "CANCEL",
        }
        try:
            r = requests.post(url, headers=self._headers(), json=payload, timeout=45)
            if r.status_code not in (200, 201):
                return [], f"HTTP {r.status_code}: {r.text[:200]}"
            body = r.json()
            # Poll if still running
            state = body.get("status", {}).get("state", "")
            stmt_id = body.get("statement_id")
            if state in ("RUNNING", "PENDING") and stmt_id:
                poll_url = f"{self.workspace_url}/api/2.0/sql/statements/{stmt_id}"
                for _ in range(20):
                    time.sleep(2)
                    pr = requests.get(poll_url, headers=self._headers(), timeout=15)
                    if pr.status_code == 200:
                        body = pr.json()
                        state = body.get("status", {}).get("state", "")
                        if state not in ("RUNNING", "PENDING"):
                            break
            if body.get("status", {}).get("state") != "SUCCEEDED":
                err = body.get("status", {}).get("error", {}).get("message", state)
                return [], err or f"Query ended in state: {state}"
            # Parse result
            manifest = body.get("manifest", {})
            columns  = [c["name"] for c in manifest.get("schema", {}).get("columns", [])]
            rows = []
            for chunk in body.get("result", {}).get("data_array", []):
                rows.append(dict(zip(columns, chunk)))
            return rows, ""
        except Exception as e:
            return [], str(e)

    def get_existing_tags(self, full_table_name: str, warehouse_id: str = "") -> tuple[dict, str]:
        """
        Fetch tags already applied to a Unity Catalog table.
        Returns ({tag_name: tag_value}, error_msg).

        Tries the REST GET endpoint first; falls back to querying
        INFORMATION_SCHEMA.TABLE_TAGS via SQL.
        """
        # ── 1. REST attempt ──────────────────────────────────────────────────
        encoded = quote(full_table_name, safe="")
        try:
            r = requests.get(
                f"{self.workspace_url}/api/2.1/unity-catalog/tables/{encoded}/tags",
                headers=self._headers(), timeout=15,
            )
            if r.status_code == 200:
                pairs = r.json().get("tag_pairs", [])
                return {p["tag_name"]: p.get("tag_value", "") for p in pairs}, ""
            # 404 → REST not available, fall through
            if r.status_code not in (404, 405):
                return {}, f"HTTP {r.status_code}: {r.text[:200]}"
        except Exception:
            pass  # network hiccup — try SQL path

        # ── 2. SQL fallback: INFORMATION_SCHEMA.TABLE_TAGS ───────────────────
        if not warehouse_id:
            whs, wh_err = self.list_sql_warehouses()
            if wh_err or not whs:
                return {}, "Could not fetch existing tags (no SQL warehouse available)."
            running = [w for w in whs if w["state"] == "RUNNING"]
            warehouse_id = (running or whs)[0]["id"]

        parts = full_table_name.split(".")
        if len(parts) != 3:
            return {}, f"Expected catalog.schema.table, got: {full_table_name}"
        catalog, schema, table = parts

        sql = (
            f"SELECT tag_name, tag_value "
            f"FROM `{catalog}`.information_schema.table_tags "
            f"WHERE schema_name = '{schema}' AND table_name = '{table}'"
        )
        rows, sql_err = self._query_sql(warehouse_id, sql)
        if sql_err:
            return {}, f"Could not fetch existing tags via SQL: {sql_err}"
        return {row["tag_name"]: row.get("tag_value", "") for row in rows}, ""

    # ─────────────────────────────────────────────────────────────────────────
    # PUSH TAGS TO TABLE
    # ─────────────────────────────────────────────────────────────────────────
    # Characters not allowed in Unity Catalog tag keys per Databricks docs
    _TAG_KEY_FORBIDDEN = str.maketrans({c: "_" for c in ".,_-=/:_"})  # replace with underscore

    @staticmethod
    def _sanitize_tag_key(key: str) -> str:
        """
        Unity Catalog tag keys may not contain: . , - = / :
        Replace any such character with an underscore.
        Also strip leading/trailing spaces (also forbidden).
        """
        import re
        sanitized = re.sub(r'[.,\-=/:]+', '_', key).strip()
        return sanitized or "unknown"

    def push_tags_to_table(
        self,
        full_table_name: str,
        tag_pairs: list[dict],
        warehouse_id: str = "",
    ) -> tuple[int, list[str], list[str]]:
        """
        Apply tags to a Unity Catalog table, skipping any that already exist.

        Tries REST API first; if the /tags endpoint returns 404 it falls back
        to ALTER TABLE … SET TAGS via the SQL Statement Execution API.

        Parameters
        ----------
        full_table_name : str
            Three-part table name: catalog.schema.table
        tag_pairs : list of dict
            Each dict has {"tag_name": <physical_term>, "tag_value": <business_term>}
        warehouse_id : str
            Optional SQL warehouse ID.  Auto-resolved if blank.

        Returns
        -------
        (applied: int, skipped: list[str], errors: list[str])
        skipped contains tag_name strings that were already present on the table.
        """
        if not tag_pairs:
            return 0, [], []

        # Pre-flight: confirm the table actually exists
        exists, verify_err = self.verify_table_exists(full_table_name)
        if not exists:
            return 0, [], [verify_err]

        # Resolve warehouse early — needed for both duplicate check and SQL fallback
        resolved_wh = warehouse_id
        if not resolved_wh:
            whs, wh_err = self.list_sql_warehouses()
            if not wh_err and whs:
                running = [w for w in whs if w["state"] == "RUNNING"]
                resolved_wh = (running or whs)[0]["id"]

        # Fetch tags already on the table and build a set of existing key names
        existing_tags, _fetch_err = self.get_existing_tags(full_table_name, resolved_wh)
        existing_keys = {k.lower() for k in existing_tags}

        # Sanitize + split into new vs duplicate
        skipped_names: list[str] = []
        sanitized_pairs: list[dict] = []
        for p in tag_pairs:
            sanitized_key = self._sanitize_tag_key(p["tag_name"])
            if sanitized_key.lower() in existing_keys:
                skipped_names.append(sanitized_key)
            else:
                sanitized_pairs.append({
                    "tag_name": sanitized_key,
                    "tag_value": str(p.get("tag_value", "")).strip(),
                })

        if not sanitized_pairs:
            # Every tag already exists
            return 0, skipped_names, []

        # ── 1. Try REST API ──────────────────────────────────────────────────
        encoded_name = quote(full_table_name, safe="")
        rest_url = f"{self.workspace_url}/api/2.1/unity-catalog/tables/{encoded_name}/tags"
        try:
            r = requests.post(
                rest_url, headers=self._headers(),
                json={"tag_pairs": sanitized_pairs}, timeout=30,
            )
            if r.status_code in (200, 204):
                return len(sanitized_pairs), skipped_names, []
            if r.status_code == 401:
                return 0, skipped_names, ["Authentication failed — check your Personal Access Token."]
            if r.status_code == 403:
                return 0, skipped_names, [f"Permission denied — token needs APPLY TAG on '{full_table_name}'."]
            if r.status_code == 400:
                return 0, skipped_names, [f"Bad request (invalid tag key/value): {r.text[:400]}"]
            # 404 or other → fall through to SQL path
        except requests.exceptions.ConnectionError:
            return 0, skipped_names, [f"Cannot reach workspace at {self.workspace_url}."]
        except Exception as e:
            return 0, skipped_names, [str(e)]

        # ── 2. SQL fallback: ALTER TABLE … SET TAGS ──────────────────────────
        if not resolved_wh:
            return 0, skipped_names, [
                "REST tags endpoint unavailable and no SQL warehouses found. "
                "Create a SQL warehouse in your Databricks workspace."
            ]

        parts = full_table_name.split(".")
        safe_table = (
            f"`{parts[0]}`.`{parts[1]}`.`{parts[2]}`" if len(parts) == 3
            else full_table_name
        )
        tag_clause = ", ".join(
            f"'{p['tag_name']}' = '{p['tag_value'].replace(chr(39), chr(39)+chr(39))}'"
            for p in sanitized_pairs
        )
        sql = f"ALTER TABLE {safe_table} SET TAGS ({tag_clause})"

        ok, sql_err = self._execute_sql(resolved_wh, sql)
        if ok:
            return len(sanitized_pairs), skipped_names, []
        return 0, skipped_names, [f"SQL fallback failed: {sql_err}"]

    # ─────────────────────────────────────────────────────────────────────────
    # GET TABLE COLUMNS
    # ─────────────────────────────────────────────────────────────────────────
    def get_table_columns(self, catalog: str, schema: str, table: str) -> tuple[list[str], str]:
        """
        Return the column names for a Unity Catalog table.

        Uses GET /api/2.1/unity-catalog/tables/{catalog}.{schema}.{table}
        which returns the full table metadata including column definitions.

        Returns
        -------
        ([column_names], error_msg)  — error_msg is '' on success.
        """
        full_name = f"{catalog}.{schema}.{table}"
        encoded = quote(full_name, safe="")
        url = f"{self.workspace_url}/api/2.1/unity-catalog/tables/{encoded}"
        try:
            r = requests.get(url, headers=self._headers(), timeout=15)
            if r.status_code == 200:
                cols = [c["name"] for c in r.json().get("columns", []) if c.get("name")]
                return cols, ""
            elif r.status_code == 404:
                return [], f"Table '{full_name}' not found in Unity Catalog."
            elif r.status_code == 403:
                return [], f"Access denied for '{full_name}'. Check USE CATALOG / USE SCHEMA privileges."
            return [], f"HTTP {r.status_code}: {r.text[:200]}"
        except Exception as e:
            return [], str(e)

    def search_tables(self, catalog: str, schema: str, keyword: str = "") -> tuple[list[dict], str]:
        """
        List tables in a catalog+schema, optionally filtered by keyword.

        Returns
        -------
        ([{name, catalog_name, schema_name, full_name, table_type}, ...], error_msg)
        """
        url = f"{self.workspace_url}/api/2.1/unity-catalog/tables"
        params: dict = {"catalog_name": catalog, "schema_name": schema}
        try:
            r = requests.get(url, headers=self._headers(), params=params, timeout=20)
            if r.status_code == 200:
                tables = r.json().get("tables", [])
                results = []
                for t in tables:
                    name = t.get("name", "")
                    if keyword and keyword.lower() not in name.lower():
                        continue
                    results.append({
                        "name": name,
                        "catalog_name": t.get("catalog_name", catalog),
                        "schema_name": t.get("schema_name", schema),
                        "full_name": t.get("full_name", f"{catalog}.{schema}.{name}"),
                        "table_type": t.get("table_type", ""),
                    })
                return results, ""
            return [], f"HTTP {r.status_code}: {r.text[:200]}"
        except Exception as e:
            return [], str(e)
