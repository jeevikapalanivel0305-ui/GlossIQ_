"""
Read-only check: how are glossary terms linked to assets in a Purview account?

Run from the GlossIQ folder:
    .venv\\Scripts\\python.exe tools\\check_purview_terms.py
    .venv\\Scripts\\python.exe tools\\check_purview_terms.py --table PATIENT_ADDRESS

Credentials come from environment variables PURVIEW_TENANT_ID, PURVIEW_CLIENT_ID,
PURVIEW_CLIENT_SECRET, PURVIEW_ACCOUNT_NAME, then from the [purview] section of
.streamlit/secrets.toml, and otherwise are prompted for. Nothing is written to Purview.
The output contains no secrets, so it is safe to share.
"""
import argparse
import getpass
import os
import sys
import tomllib

import requests

API = {"api-version": "2023-09-01"}


def load_creds():
    keys = ["tenant_id", "client_id", "client_secret", "account_name"]
    creds = {k: os.environ.get(f"PURVIEW_{k.upper()}", "") for k in keys}
    secrets_path = os.path.join(os.path.dirname(__file__), "..", ".streamlit", "secrets.toml")
    if os.path.exists(secrets_path):
        with open(secrets_path, "rb") as f:
            pv = tomllib.load(f).get("purview", {})
        for k in keys:
            creds[k] = creds[k] or pv.get(k, "")
    for k in keys:
        if not creds[k]:
            creds[k] = (getpass.getpass if k == "client_secret" else input)(f"{k}: ").strip()
    return creds


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--table", help="also show the glossary links on this table and its columns (e.g. PATIENT_ADDRESS)")
    args = ap.parse_args()
    c = load_creds()

    tok = requests.post(
        f"https://login.microsoftonline.com/{c['tenant_id']}/oauth2/v2.0/token",
        data={"grant_type": "client_credentials", "client_id": c["client_id"],
              "client_secret": c["client_secret"], "scope": "https://purview.azure.net/.default"},
        timeout=30)
    if tok.status_code != 200:
        sys.exit(f"Authentication failed (HTTP {tok.status_code}): {tok.text[:300]}")
    h = {"Authorization": "Bearer " + tok.json()["access_token"]}
    base = f"https://{c['account_name']}.purview.azure.com/datamap/api/atlas/v2"

    def get(path, **params):
        r = requests.get(base + path, headers=h, params={**API, **params}, timeout=60)
        if r.status_code != 200:
            raise RuntimeError(f"GET {path} -> HTTP {r.status_code}: {r.text[:300]}")
        return r.json()

    print(f"Purview account: {c['account_name']}\n")

    # 1. Relationship types that can connect a glossary term to something
    rels = get("/types/typedefs", type="relationship").get("relationshipDefs", [])
    print("== Relationship types with a glossary end ==")
    for r in rels:
        e1, e2 = r["endDef1"], r["endDef2"]
        if "Glossary" in e1.get("type", "") + e2.get("type", "") or "member" in (e1["name"] + e2["name"]).lower():
            print(f"  {r['name']}: {e1['type']}.{e1['name']}  <->  {e2['type']}.{e2['name']}")

    # 2. Every glossary and how each term is attached to assets
    glossaries = get("/glossary")
    print(f"\n== Glossaries ({len(glossaries)}) - GlossIQ registers into the FIRST one ==")
    for i, g in enumerate(glossaries):
        print(f"  [{i}] {g.get('name')}  ({len(g.get('terms') or [])} terms)")

    bad = 0
    for g in glossaries:
        print(f"\n== Terms in '{g.get('name')}' that are linked to assets ==")
        for t in g.get("terms") or []:
            d = get(f"/glossary/term/{t['termGuid']}")
            for a in d.get("assignedEntities") or []:
                kind = a.get("relationshipType") or "?"
                flag = "" if kind == "AtlasGlossarySemanticAssignment" else "   <-- NOT a glossary-term assignment"
                bad += bool(flag)
                print(f"  {d.get('name')!r} -> {a.get('typeName')} {a.get('displayText')!r} [{kind}]{flag}")

    # 3. Optional: look at one table and its columns from the asset side
    def show_links(e, indent):
        found = False
        for attr, val in (e.get("relationshipAttributes") or {}).items():
            for x in val if isinstance(val, list) else [val]:
                if isinstance(x, dict) and ("Glossary" in (x.get("typeName") or "") or "member" in attr.lower()):
                    kind = x.get("relationshipType")
                    flag = "" if attr == "meanings" and kind == "AtlasGlossarySemanticAssignment" else "   <-- NOT a glossary term"
                    print(f"{indent}{attr}: {x.get('typeName')} {x.get('displayText')!r} [{kind}]{flag}")
                    found = True
        if not found:
            print(f"{indent}(no glossary links)")

    if args.table:
        r = requests.post(f"https://{c['account_name']}.purview.azure.com/datamap/api/search/query",
                          headers=h, params=API, json={"keywords": args.table, "limit": 50}, timeout=30)
        hits = [v for v in r.json().get("value", []) if (v.get("name") or "").upper() == args.table.upper()]
        print(f"\n== Assets named {args.table} ({len(hits)}) ==")
        for v in hits:
            e = get(f"/entity/guid/{v['id']}").get("entity", {})
            print(f"  {e.get('typeName')} {v.get('qualifiedName')}")
            show_links(e, "    ")
            for attr, val in (e.get("relationshipAttributes") or {}).items():
                for col in val if isinstance(val, list) else []:
                    if isinstance(col, dict) and "column" in (col.get("typeName") or "").lower():
                        print(f"    column {col.get('displayText')}")
                        show_links(get(f"/entity/guid/{col['guid']}").get("entity", {}), "      ")

    print(f"\nLinks that are not glossary-term assignments: {bad}")

    # 4. Unified Catalog: governance domains and whether asset curation looks enabled
    uc = f"https://{c['account_name']}.purview.azure.com/datagovernance/catalog"
    uc_v = {"api-version": "2025-09-15-preview"}
    r = requests.get(uc + "/businessdomains", headers=h, params=uc_v, timeout=30)
    print("\n== Unified Catalog ==")
    if r.status_code != 200:
        print(f"  Not available (HTTP {r.status_code}): {r.text[:200]}")
        return
    domains = r.json().get("value", [])
    staging = any(d.get("name") == ".StagingDomain" for d in domains)
    terms = requests.get(uc + "/terms", headers=h, params={**uc_v, "top": 100}, timeout=30).json().get("value", [])
    migrated = sum(1 for t in terms if t.get("isMigrated"))
    print(f"  Governance domains: {len(domains)}  ({', '.join(d.get('name', '') for d in domains[:8])}"
          f"{', ...' if len(domains) > 8 else ''})")
    print(f"  Domain terms (first 100): {len(terms)}, migrated from classic: {migrated}")
    print(f"  .StagingDomain present: {staging}")
    print("  Asset curation: " + ("LOOKS ENABLED - classic glossary is read-only; terms go on columns as domain terms"
                                   if staging or migrated else
                                   "looks OFF - only classic terms can be put on columns"))


if __name__ == "__main__":
    main()
