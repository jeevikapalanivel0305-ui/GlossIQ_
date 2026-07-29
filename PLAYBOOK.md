# GlossIQ — Glossary Enricher Accelerator Playbook

---

## 1. Executive Summary

**GlossIQ** is an AI-powered Data Governance accelerator that automates the creation, enrichment, and management of business glossary terms across enterprise data catalogs. It bridges the gap between physical data assets (tables, columns) and their business meaning by leveraging Azure OpenAI, Microsoft Purview, and Databricks Unity Catalog.

| Attribute | Detail |
|-----------|--------|
| **Product Name** | GlossIQ — Glossary Enricher Accelerator |
| **Tech Stack** | Python · Streamlit · Azure OpenAI · Microsoft Purview · Databricks Unity Catalog |
| **Author** | Jeevika Palanivelu (iLink Systems) |
| **Target Users** | Data Stewards, Data Governance Teams, CDOs, Business Analysts |
| **Deployment** | Local / Streamlit Cloud / Azure App Service |

---

## 2. Value Proposition

### Business Problem
- Manual glossary creation is slow, inconsistent, and expensive
- Physical-to-business term mapping is labor-intensive
- Governance classifications (PII, Confidential) are often missed or inconsistent
- No single pane of glass for glossary approval workflows
- Lack of lineage between source systems, physical assets, and business terms

### How GlossIQ Solves It

| Challenge | GlossIQ Solution |
|-----------|-----------------|
| Manual glossary authoring | AI-generated business terms, definitions, and classifications |
| Inconsistent governance tagging | Automated rule engine (regex + metadata keyword matching) |
| Fragmented approval process | Built-in Review & Approval workflow with conflict detection |
| No lineage visibility | Visual Mermaid-based lineage: Source → Table → Column → Business Term |
| Siloed data catalogs | Multi-connector architecture (Purview, Databricks, Collibra, Atlan, etc.) |
| Access control gaps | Role-Based Access Control (RBAC) with granular permissions |

### Key Differentiators
1. **AI + Rules Hybrid** — Azure OpenAI generates suggestions; deterministic governance rules override for sensitive data
2. **SCD Type 2 Versioning** — Full term-level version history; never lose historical definitions
3. **Conflict Detection** — Automatically detects duplicate/conflicting terms across sources
4. **Bi-directional Sync** — Push approved terms back to Unity Catalog as tags
5. **Semantic Search** — Embedding-based natural language search across the glossary

---

## 3. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                         FRONTEND (Streamlit)                         │
│  ┌──────────┬───────────┬──────────┬───────────┬──────────────────┐ │
│  │Dashboard │Asset Search│Glossary AI│Review &   │ Glossary Hub    │ │
│  │          │           │          │ Approval  │ + Semantic Search│ │
│  └──────────┴───────────┴──────────┴───────────┴──────────────────┘ │
└───────────────────────────────┬─────────────────────────────────────┘
                                │
┌───────────────────────────────▼─────────────────────────────────────┐
│                         BACKEND (Python)                             │
│  ┌────────────────┐  ┌──────────────────┐  ┌─────────────────────┐ │
│  │ AI Recommender │  │ Governance Engine │  │ Workflow Manager     │ │
│  │ (Azure OpenAI) │  │ (Rule-based)     │  │ (Approve/Reject/    │ │
│  │                │  │                  │  │  Merge/Conflict)    │ │
│  └────────────────┘  └──────────────────┘  └─────────────────────┘ │
│  ┌────────────────┐  ┌──────────────────┐  ┌─────────────────────┐ │
│  │ Persistence    │  │ Semantic Search   │  │ Internal Governance │ │
│  │ Manager (SCD2) │  │ (Embeddings)     │  │ (Heuristic Engine)  │ │
│  └────────────────┘  └──────────────────┘  └─────────────────────┘ │
└───────────────────────────────┬─────────────────────────────────────┘
                                │
┌───────────────────────────────▼─────────────────────────────────────┐
│                      CONNECTORS / INTEGRATIONS                       │
│  ┌─────────────┐  ┌───────────────────┐  ┌───────────────────────┐ │
│  │ Microsoft   │  │ Databricks Unity  │  │ Collibra / Atlan /    │ │
│  │ Purview     │  │ Catalog           │  │ dbt / Alation / Slack │ │
│  └─────────────┘  └───────────────────┘  └───────────────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
                                │
┌───────────────────────────────▼─────────────────────────────────────┐
│                      DATA STORES (JSON)                              │
│  glossary_master.json │ approval_queue.json │ audit_log.json        │
│  rbac_store.json      │ ai_suggested_terms.json │ lineage_store.json│
└─────────────────────────────────────────────────────────────────────┘
```

---

## 4. Feature Catalogue

### 4.1 Executive Dashboard
- At-a-glance KPIs: total terms, pending approvals, conflict rate
- System health status

### 4.2 Integrations & API
- **Microsoft Purview** — OAuth2 client-credentials authentication; search assets by keyword, type, collection
- **Databricks Unity Catalog** — PAT-based auth; list catalogs/schemas/tables; push tags via SQL Statement API
- **Collibra, Atlan, dbt Cloud, Alation** — Generic API endpoint + token configuration (push/pull)
- **Slack** — Webhook notifications for governance events

### 4.3 Asset Search
- Purview: keyword search with source-type and collection filters; fetch table schemas (column names + GUIDs)
- Databricks Unity: catalog → schema → table browsing; column discovery via SQL warehouse

### 4.4 Glossary AI (AI Recommendation Engine)
- **Azure OpenAI GPT-4** generates:
  - Business Terms
  - Business Definitions
  - Data Classifications (PII, Confidential, Internal, Public)
  - Confidence Scores
- **Governance Rule Engine overlay** — deterministic regex + keyword rules override AI for sensitive columns (email, phone, Aadhaar, SSN, etc.)
- **Internal Heuristic Engine** — domain-aware field-name decomposition for offline/fallback term generation
- **CDE (Critical Data Element) Identification** — AI identifies CDEs based on business requirements and industry context

### 4.5 Review & Approval Workflow
- Pipeline: **AI Suggestion → Conflict Check → Approve / Reject / Merge → Glossary Hub**
- Conflict detection: checks existing approved terms for same physical term + table
- Merge capability: SCD Type 2 — deactivates old version, creates new active version
- Bulk actions: approve/reject selected, reject all conflicting
- User suggestion form for manual term submission
- RBAC-enforced: only permitted roles can approve/reject

### 4.6 Glossary Hub (Master Glossary)
- Central repository of all approved terms
- SCD Type 2 versioning (Version number, Active flag, Valid From/To)
- Filterable by source, table, domain
- Export-ready data model

### 4.7 Semantic Search
- **Azure OpenAI Embeddings** (text-embedding-ada-002) for vector similarity search
- Cosine similarity with configurable threshold (default 0.70)
- Natural language queries across all active glossary terms
- Keyword fallback search

### 4.8 Lineage Map
- Interactive Mermaid.js diagrams
- Flow: **Integration Source → Table (Asset) → Column (Attribute) → Business Term**
- Domain ownership inference (Healthcare, Finance, Retail, HR, etc.)
- Confidence score annotations on edges
- Automatically scoped to connected sources only

### 4.9 Conflict Detection
- Identifies duplicate or overlapping business terms across sources
- Flags terms where same physical column has different business names
- Provides merge path for reconciliation

### 4.10 RBAC Management
- Role-based permissions: Administrator, Reader, custom roles
- Granular permissions: `can_read`, `can_approve`, `can_reject`, `can_suggest`, `can_edit_glossary`, `can_manage_rbac`
- User CRUD with email-based login
- Password reset functionality

---

## 5. Prerequisites & Setup

### 5.1 Requirements

| Component | Details |
|-----------|---------|
| Python | 3.9+ |
| Azure OpenAI | GPT-4 deployment + text-embedding-ada-002 |
| Microsoft Purview | Service Principal with Data Catalog Reader role |
| Databricks | Personal Access Token with Unity Catalog permissions |

### 5.2 Installation

```powershell
# Clone / copy the accelerator
cd Purview_Glossary

# Install dependencies
pip install -r requirements.txt

# Configure secrets
mkdir .streamlit
```

### 5.3 Secrets Configuration

Create `.streamlit/secrets.toml`:

```toml
# Azure OpenAI
AZURE_OPENAI_ENDPOINT = "https://<your-resource>.openai.azure.com/"
AZURE_OPENAI_API_KEY = "<your-api-key>"
AZURE_OPENAI_API_VERSION = "2024-12-01-preview"
AZURE_OPENAI_DEPLOYMENTNAME = "gpt-4.1"
AZURE_OPENAI_EMBEDDING_DEPLOYMENT = "text-embedding-ada-002"
MAX_TOKENS = "16384"
```

### 5.4 Running the Application

```powershell
streamlit run app.py
```

Default login: `jeevika.palanivelu@ilink-systems.com` / `user321` (Administrator)

---

## 6. Demo Flow (Step-by-Step Walkthrough)

### Scenario: Enrich a Databricks Unity Catalog table with business glossary terms

#### Step 1 — Login
1. Navigate to the app URL
2. Sign in with Administrator credentials
3. You land on the Executive Dashboard

#### Step 2 — Connect Data Source
1. Navigate to **Integrations & API**
2. Click **Connect** on the **Databricks Unity** card
3. Enter Workspace URL and Personal Access Token
4. Click **Save & Connect** — verify "Connected" status

#### Step 3 — Discover Assets
1. Navigate to **Asset Search**
2. Select catalog → schema from dropdowns
3. Browse available tables; select target table(s)
4. Click **Fetch Columns** — see physical schema (column names, types)

#### Step 4 — Generate AI Glossary Terms
1. Navigate to **Glossary AI**
2. Select enrichment options: Business Term, Business Definition, Classification
3. Choose industry context (Finance, Healthcare, Retail, etc.)
4. Click **Generate** — AI produces suggestions for each column
5. Review the overlay: Governance Engine auto-classifies PII/Confidential columns
6. Terms are automatically queued in the Approval Queue

#### Step 5 — Review & Approve
1. Navigate to **Review & Approval**
2. See pending terms in the **Approval Queue** tab
3. Review each card: Physical Term, Business Term, Definition, Confidence Score
4. Handle conflicts:
   - **No conflict** → Click ✓ to approve
   - **Same term already approved** → Click 🔀 Merge (creates new SCD2 version)
   - **Different term for same column** → Choose Approve (overrides) or Reject
5. Use bulk actions for efficiency
6. Approved terms flow to the Glossary Hub

#### Step 6 — Explore the Glossary Hub
1. Navigate to **Glossary Hub**
2. View all active terms with version history
3. Filter by source, table, or search by term name

#### Step 7 — Visualize Lineage
1. Navigate to **Lineage Map**
2. Select a Business Term from the dropdown
3. See full lineage: Databricks → Table → Column → Business Term + Domain

#### Step 8 — Semantic Search
1. Navigate to **Semantic Search**
2. Enter natural language query (e.g., "customer contact information")
3. Get ranked results by semantic similarity

#### Step 9 — Push to Unity Catalog (Optional)
- Approved terms can be pushed back to Databricks as Unity Catalog tags
- Tag format: `key = column_name`, `value = business_term`

---

## 7. Data Model

### glossary_master.json (Master Glossary Store)
```json
{
  "<asset_guid>": [
    {
      "Physical Term": "cust_email",
      "Business Term": "Customer Email Address",
      "Definition / Description": "Primary email contact for the customer",
      "Type": "Column",
      "table_name": "dim_customer",
      "Classification": "PII",
      "Confidence (%)": 95,
      "Source": "Databricks Unity Catalog",
      "Version": 1,
      "Active": 1,
      "Valid From": "2026-07-20T10:00:00",
      "Valid To": null,
      "Tags": ["Domain: CRM", "PII"]
    }
  ]
}
```

### approval_queue.json
```json
[
  {
    "term_id": "uuid-...",
    "term_name": "Customer Email Address",
    "physical_term": "cust_email",
    "definition": "Primary email contact...",
    "table_name": "dim_customer",
    "source": "Databricks Unity Catalog",
    "confidence_score": 95,
    "status": "Pending",
    "conflict_found": false,
    "created_at": "2026-07-20T10:00:00"
  }
]
```

### rbac_store.json
```json
{
  "users": {
    "user@domain.com": {
      "name": "User Name",
      "role": "Administrator",
      "can_read": true,
      "can_approve": true,
      "can_reject": true,
      "can_suggest": true,
      "can_edit_glossary": true
    }
  },
  "roles": {
    "Administrator": { "can_read": true, "can_approve": true, "...": "..." },
    "Reader": { "can_read": true, "can_approve": false, "...": "..." }
  }
}
```

---

## 8. Module Reference

| Module | File | Purpose |
|--------|------|---------|
| Main App | `app.py` | Streamlit UI, navigation, page rendering |
| Purview Connector | `backend/purview_connector.py` | Azure AD auth, Purview DataMap search, CDE discovery |
| Databricks Connector | `backend/databricks_unity_connector.py` | Unity Catalog API, SQL warehouse execution, tag push |
| AI Recommender | `backend/ai_recommender.py` | Azure OpenAI GPT-4 term/definition generation |
| Governance Engine | `backend/governance_engine.py` | Regex + keyword rule-based classification overlay |
| Internal Governance | `backend/internal_governance.py` | Heuristic field-name decomposition, domain inference |
| Workflow Manager | `backend/workflow_manager.py` | Approval queue CRUD, conflict detection, merge, audit log |
| Persistence Manager | `backend/persistence_manager.py` | SCD Type 2 glossary storage, RBAC persistence |
| Semantic Search | `backend/semantic_search.py` | Embedding generation, cosine similarity search |

---

## 9. Governance Engine — Rule Details

### Sensitive Data Detection (Automated)

| Classification | Trigger Keywords | Confidence |
|---------------|-----------------|------------|
| **PII** | email, phone, mobile, address, dob, gender, name | 85–95% |
| **Confidential** | salary, ssn, aadhaar, pan, passport, credit, bank | 90–100% |
| **Internal** | id, guid, uuid, key, reference, code | 80% |

### Regex Pattern Matching (on sample values)

| Pattern | Classification | Confidence |
|---------|---------------|------------|
| Email format | PII | 100% |
| Phone (E.164) | PII | 90% |
| Aadhaar (12-digit) | Confidential | 100% |

### Priority: Rule Engine always overrides AI suggestions for classified columns.

---

## 10. Integration Matrix

| Connector | Auth Method | Push | Pull | Status |
|-----------|-------------|------|------|--------|
| Microsoft Purview | OAuth2 (Client Credentials) | ✅ | ✅ | Production |
| Databricks Unity | PAT (Personal Access Token) | ✅ | ✅ | Production |
| Collibra | API Token | ✅ | ✅ | Configured |
| Atlan | API Token | ✅ | ❌ | Configured |
| dbt Cloud | API Token | ❌ | ✅ | Configured |
| Alation | API Token | ✅ | ✅ | Configured |
| Slack | Webhook | ✅ | ❌ | Configured |

---

## 11. RBAC Permissions Matrix

| Permission | Administrator | Data Steward | Reviewer | Reader |
|-----------|:---:|:---:|:---:|:---:|
| Read glossary | ✅ | ✅ | ✅ | ✅ |
| Suggest terms | ✅ | ✅ | ❌ | ❌ |
| Approve terms | ✅ | ✅ | ✅ | ❌ |
| Reject terms | ✅ | ✅ | ✅ | ❌ |
| Edit glossary | ✅ | ✅ | ❌ | ❌ |
| Manage RBAC | ✅ | ❌ | ❌ | ❌ |

---

## 12. Talking Points for Customer Demos

### Opening (30 seconds)
> "GlossIQ automates the most painful part of data governance — building and maintaining a business glossary. It uses AI to generate business terms from your physical data assets, applies deterministic governance rules for sensitive data classification, and provides a full approval workflow with conflict detection and SCD Type 2 versioning."

### Key Messages
1. **Time-to-Value**: "What takes weeks manually, GlossIQ does in minutes — connect, discover, generate, approve."
2. **Trust + AI**: "AI suggests, but governance rules enforce. PII classification is never left to probability alone."
3. **Multi-Platform**: "Works with Purview and Databricks today, with Collibra, Atlan, and dbt in the roadmap."
4. **Auditability**: "Every decision is logged. Full version history. Complete lineage from source to business term."
5. **Enterprise-Ready**: "RBAC, conflict detection, bulk operations, semantic search — built for scale."

### Objection Handling

| Objection | Response |
|-----------|----------|
| "We already have Purview" | "GlossIQ enhances Purview — it adds AI-driven term generation, approval workflows, and conflict detection that Purview doesn't natively provide." |
| "How accurate is the AI?" | "The Governance Engine provides a deterministic safety net. Sensitive data (PII, Confidential) is classified by rules with 100% confidence, not left to AI probability." |
| "What about data security?" | "All processing uses Azure OpenAI (your tenant). No data leaves your Azure boundary. RBAC ensures only authorized users can approve terms." |
| "Can it scale?" | "The architecture supports multiple connectors, bulk operations, and semantic search with embeddings. The approval workflow handles hundreds of terms efficiently." |

---

## 13. Roadmap & Extension Points

| Phase | Capability |
|-------|-----------|
| **Current** | Purview + Databricks + AI Glossary + Approval + Lineage |
| **Next** | Collibra/Atlan live sync, Power Automate notifications, API export |
| **Future** | Data Quality rules from glossary, automated stewardship assignment, multi-language support |

---

## 14. Troubleshooting

| Issue | Resolution |
|-------|-----------|
| "DNS resolution failed for Purview" | Check account name, VPN/firewall, internet connectivity |
| "AADSTS700016 — App not found" | Verify Client ID and Tenant ID match the same Azure AD |
| "Databricks 401" | PAT expired or lacks Unity Catalog permissions |
| AI returns empty suggestions | Check Azure OpenAI endpoint, API key, and deployment name in secrets.toml |
| Semantic search returns no results | Ensure embedding deployment is configured and glossary has active terms |
| Login fails | User must be added via RBAC Management by an Administrator |

---

## 15. File Structure

```
Purview_Glossary/
├── app.py                          # Main Streamlit application
├── requirements.txt                # Python dependencies
├── style.css                       # Custom UI styling
├── .streamlit/
│   └── secrets.toml                # Azure OpenAI + connector secrets
├── assets/
│   └── purview.jfif                # Connector logos
├── backend/
│   ├── __init__.py
│   ├── ai_recommender.py           # Azure OpenAI integration
│   ├── ai_suggested_terms.json     # AI suggestion staging store
│   ├── approval_queue.json         # Pending approval queue
│   ├── audit_log.json              # Decision audit trail
│   ├── databricks_unity_connector.py # Databricks UC API connector
│   ├── glossary_master.json        # Master glossary (SCD2)
│   ├── governance_engine.py        # Rule-based classification engine
│   ├── internal_governance.py      # Heuristic term generation
│   ├── lineage_store.json          # Lineage relationship data
│   ├── persistence_manager.py      # Storage + RBAC persistence
│   ├── purview_connector.py        # Microsoft Purview connector
│   ├── rbac_store.json             # User/role definitions
│   ├── semantic_search.py          # Embedding-based search
│   └── workflow_manager.py         # Approval pipeline orchestration
└── PLAYBOOK.md                     # This document
```

---

*Last updated: 2026-07-20*
