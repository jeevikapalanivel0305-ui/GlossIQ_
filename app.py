import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import json
import os
import sys
import base64
import html as _html
from datetime import datetime

# Ensure backend modules can be imported
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from backend.purview_connector import PurviewConnector
from backend.databricks_unity_connector import DatabricksUnityConnector
from backend.ai_recommender import generate_glossary_suggestions
from backend.internal_governance import generate_internal_governance
from backend.governance_engine import GovernanceEngine
from backend.persistence_manager import PersistenceManager
from backend.workflow_manager import WorkflowManager

st.set_page_config(
    page_title="Glossary Enricher Accelerator",
    page_icon="📖",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ============================================
# CONSTANTS & ASSETS
# ============================================

# ICORE_ICONS dictionary removed. Using native Material Icons.


# ============================================
# HELPERS
# ============================================

def load_css(file_name):
    """Load and inject CSS styling"""
    css_path = os.path.join(os.path.dirname(__file__), file_name)
    try:
        with open(css_path) as f:
            st.markdown(f'<style>{f.read()}</style>', unsafe_allow_html=True)
    except FileNotFoundError:
        pass

# Helper for navigation callbacks
def set_nav_tab(tab_name):
    st.session_state.selected_tab = tab_name

# Initialize Session State
if 'connector_creds' not in st.session_state:
    st.session_state.connector_creds = {
        'purview_account_name': '',
        'purview_tenant_id': '',
        'purview_client_id': '',
        'purview_client_secret': ''
    }
if 'purview_search_results' not in st.session_state:
    st.session_state.purview_search_results = []
if 'tables_metadata' not in st.session_state:
    st.session_state.tables_metadata = {}
if 'glossary_suggestions' not in st.session_state:
    st.session_state.glossary_suggestions = []
if 'is_authenticated' not in st.session_state:
    st.session_state.is_authenticated = False
if 'purview_collections' not in st.session_state:
    st.session_state.purview_collections = []
if 'selected_tab' not in st.session_state:
    st.session_state.selected_tab = "Executive Dashboard"
if 'glossary_df' not in st.session_state:
    st.session_state.glossary_df = None
if 'active_connector' not in st.session_state:
    st.session_state.active_connector = None
if 'connector_statuses' not in st.session_state:
    st.session_state.connector_statuses = {
        'Microsoft Purview': 'Not Connected',
        'Microsoft SQL Server': 'Not Connected',
        'Snowflake': 'Not Connected',
        'Databricks': 'Not Connected',
        'Oracle': 'Not Connected'
    }
if 'user_role' not in st.session_state:
    st.session_state.user_role = "Administrator"
if 'user_name' not in st.session_state:
    st.session_state.user_name = "Jeevika P."
if 'uc_search_results' not in st.session_state:
    st.session_state.uc_search_results = []

# ── On every fresh browser session, wipe Pending/Conflict entries from the
#    approval queue so the Review tab starts clean.  Approved/Rejected entries
#    remain in the audit log and are untouched.
if 'queue_cleared_this_session' not in st.session_state:
    WorkflowManager.purge_pending_from_queue()
    st.session_state.queue_cleared_this_session = True

# Integration Connectors State – reinitialise if 'image' key is missing (migration guard)
_CONNECTOR_DEFAULTS = {
    'Microsoft Purview': {'letter': 'MP',  'image': 'purview.jfif',    'desc': 'Data Governance Map','color_bg': '#EFF6FF', 'color_txt': '#1D4ED8', 'push': True,  'pull': True,  'status': 'Not connected', 'last_sync': '', 'api_endpoint': '', 'api_token': '', 'channel': ''},
    'Collibra':          {'letter': 'Co',  'image': 'collibra.png',    'desc': 'Data catalog',       'color_bg': '#EBF5FF', 'color_txt': '#1E3A8A', 'push': True,  'pull': True,  'status': 'Not connected', 'last_sync': '', 'api_endpoint': '', 'api_token': '', 'channel': ''},
    'Atlan':             {'letter': 'At',  'image': 'atlan.png',       'desc': 'Data catalog',       'color_bg': '#F3E8FF', 'color_txt': '#6B21A8', 'push': True,  'pull': False, 'status': 'Not connected', 'last_sync': '', 'api_endpoint': '', 'api_token': '', 'channel': ''},
    'dbt Cloud':         {'letter': 'dbt', 'image': 'dbt cloud.png',   'desc': 'Transformation',     'color_bg': '#DCFCE7', 'color_txt': '#166534', 'push': False, 'pull': True,  'status': 'Not connected', 'last_sync': '', 'api_endpoint': '', 'api_token': '', 'channel': ''},
    'Alation':           {'letter': 'Al',  'image': 'alation.png',     'desc': 'Data catalog',       'color_bg': '#FEE2E2', 'color_txt': '#991B1B', 'push': True,  'pull': True,  'status': 'Not connected', 'last_sync': '', 'api_endpoint': '', 'api_token': '', 'channel': ''},
    'Slack':             {'letter': 'Sl',  'image': 'slack.png',       'desc': 'Notifications',      'color_bg': '#FEF3C7', 'color_txt': '#92400E', 'push': True,  'pull': False, 'status': 'Not connected', 'last_sync': '', 'api_endpoint': '', 'api_token': '', 'channel': '#data-governance'},
    'Databricks Unity':  {'letter': 'DB',  'image': 'databricks.png',  'desc': 'Unity Catalog Tags',  'color_bg': '#FFF3E0', 'color_txt': '#E65100', 'push': True,  'pull': False, 'status': 'Not connected', 'last_sync': '', 'api_endpoint': '', 'api_token': '', 'channel': ''},
}
_needs_reinit = (
    'integration_connectors' not in st.session_state
    or 'image' not in next(iter(st.session_state.get('integration_connectors', {None: {}}).values()), {})
    or 'Microsoft Purview' not in st.session_state.get('integration_connectors', {})
)
if _needs_reinit:
    st.session_state.integration_connectors = {
        'Microsoft Purview': {'letter': 'MP',  'image': 'purview.jfif',    'desc': 'Data Governance Map','color_bg': '#EFF6FF', 'color_txt': '#1D4ED8', 'push': True,  'pull': True,  'status': 'Not connected', 'last_sync': '', 'api_endpoint': '', 'api_token': '', 'channel': ''},
        'Collibra':          {'letter': 'Co',  'image': 'collibra.png',    'desc': 'Data catalog',       'color_bg': '#EBF5FF', 'color_txt': '#1E3A8A', 'push': True,  'pull': True,  'status': 'Not connected', 'last_sync': '', 'api_endpoint': '', 'api_token': '', 'channel': ''},
        'Atlan':             {'letter': 'At',  'image': 'atlan.png',       'desc': 'Data catalog',       'color_bg': '#F3E8FF', 'color_txt': '#6B21A8', 'push': True,  'pull': False, 'status': 'Not connected', 'last_sync': '', 'api_endpoint': '', 'api_token': '', 'channel': ''},
        'dbt Cloud':         {'letter': 'dbt', 'image': 'dbt cloud.png',   'desc': 'Transformation',     'color_bg': '#DCFCE7', 'color_txt': '#166534', 'push': False, 'pull': True,  'status': 'Not connected', 'last_sync': '', 'api_endpoint': '', 'api_token': '', 'channel': ''},
        'Alation':           {'letter': 'Al',  'image': 'alation.png',     'desc': 'Data catalog',       'color_bg': '#FEE2E2', 'color_txt': '#991B1B', 'push': True,  'pull': True,  'status': 'Not connected', 'last_sync': '', 'api_endpoint': '', 'api_token': '', 'channel': ''},
        'Slack':             {'letter': 'Sl',  'image': 'slack.png',       'desc': 'Notifications',      'color_bg': '#FEF3C7', 'color_txt': '#92400E', 'push': True,  'pull': False, 'status': 'Not connected', 'last_sync': '', 'api_endpoint': '', 'api_token': '', 'channel': '#data-governance'},
        'Databricks Unity':  {'letter': 'DB',  'image': 'databricks.png',  'desc': 'Unity Catalog Tags',  'color_bg': '#FFF3E0', 'color_txt': '#E65100', 'push': True,  'pull': False, 'status': 'Not connected', 'last_sync': '', 'api_endpoint': '', 'api_token': '', 'channel': ''},
    }

# Permanent Cache Initialization (Survives tab-switching unmounting)
if 'perm_cache' not in st.session_state:
    st.session_state.perm_cache = {
        'search_source_type': 'All',
        'search_collection': 'All Collections',
        'search_keyword': 'Customer',
        'glossary_industry': 'General',
        'glossary_options': ['Business Term', 'Business Definition'],
        'selected_table_ids': [],  # Persists checkbox selections across tab switches
        'uc_srch_cat_val': '— select catalog —',
        'uc_srch_sch_val': '— select schema —',
        'uc_srch_kw_val': '',
    }
else:
    # Migrate legacy session state if it exists
    if 'glossary_options' in st.session_state.perm_cache:
        old_opts = st.session_state.perm_cache['glossary_options']
        new_opts = []
        for opt in old_opts:
            if opt == "Glossary Term": new_opts.append("Business Term")
            elif opt == "Glossary Definition": new_opts.append("Business Definition")
            else: new_opts.append(opt)
        st.session_state.perm_cache['glossary_options'] = list(set(new_opts))

def update_cache(cache_key, widget_key):
    """Explicitly transfer widget value to permanent anchor cache."""
    if widget_key in st.session_state:
        st.session_state.perm_cache[cache_key] = st.session_state[widget_key]

# ============================================
# UI COMPONENTS
# ============================================

def render_sidebar():
    with st.sidebar:
        # Logo Section
        st.markdown(f'''
            <div class="sidebar-brand">
                <div style="background:#CC0000; width:34px; height:34px; border-radius:6px; display:flex; align-items:center; justify-content:center; color:white; font-weight:800; font-size:18px;">G</div>
                <div style="font-family:'Inter', sans-serif; font-size:18px; font-weight:700; color:#111827; letter-spacing:-0.5px;">
                    GlossIQ
                </div>
            </div>
            <div style="font-size:10px; color:#9CA3AF; padding:0 24px 20px 24px; font-weight:600; text-transform:uppercase; letter-spacing:0.05em; margin-top:-10px;">
                Glossary Enricher
            </div>
        ''', unsafe_allow_html=True)

        current_tab = st.session_state.get('selected_tab', "Executive Dashboard")

        # Intelligence
        st.markdown('<div class="sidebar-category">Intelligence</div>', unsafe_allow_html=True)
        st.button(
            "Executive Dashboard", 
            key="nav_dashboard", 
            icon=":material/dashboard:", 
            use_container_width=True, 
            on_click=set_nav_tab, 
            args=("Executive Dashboard",),
            type="primary" if current_tab == "Executive Dashboard" else "secondary"
        )
        st.button(
            "Conflict Detection", 
            key="nav_Conflict", 
            icon=":material/warning:", 
            use_container_width=True, 
            on_click=set_nav_tab, 
            args=("Conflict Detection",),
            type="primary" if current_tab == "Conflict Detection" else "secondary"
        )

        # Operations
        st.markdown('<div class="sidebar-category">Operations</div>', unsafe_allow_html=True)
        
        # Integrations & API as first item
        st.button(
            "Integrations & API", 
            key="nav_Integrations", 
            icon=":material/link:", 
            use_container_width=True, 
            on_click=set_nav_tab, 
            args=("Integrations & API",),
            type="primary" if current_tab == "Integrations & API" else "secondary"
        )

        st.button(
            "Asset Search", 
            key="nav_Asset Search", 
            icon=":material/search:", 
            use_container_width=True, 
            on_click=set_nav_tab, 
            args=("Asset Search",),
            type="primary" if current_tab == "Asset Search" else "secondary"
        )

        # Governance
        st.markdown('<div class="sidebar-category">Governance</div>', unsafe_allow_html=True)
        st.button(
            "Glossary AI", 
            key="nav_Glossary AI", 
            icon=":material/school:", 
            use_container_width=True, 
            on_click=set_nav_tab, 
            args=("Glossary AI",),
            type="primary" if current_tab == "Glossary AI" else "secondary"
        )
        
        st.button(
            "Review & Approval", 
            key="nav_Review", 
            icon=":material/playlist_add_check:", 
            use_container_width=True, 
            on_click=set_nav_tab, 
            args=("Review & Approval",),
            type="primary" if current_tab == "Review & Approval" else "secondary"
        )

        st.button(
            "Glossary Hub", 
            key="nav_Master Glossary", 
            icon=":material/inventory_2:", 
            use_container_width=True, 
            on_click=set_nav_tab, 
            args=("Glossary Hub",),
            type="primary" if current_tab == "Glossary Hub" else "secondary"
        )

        st.button(
            "Lineage Map", 
            key="nav_Lineage", 
            icon=":material/account_tree:", 
            use_container_width=True, 
            on_click=set_nav_tab, 
            args=("Lineage Map",),
            type="primary" if current_tab == "Lineage Map" else "secondary"
        )

        # Feedback Stats removed as requested

        # Profile & RBAC Switcher
        st.markdown('<div class="sidebar-category">System Admin</div>', unsafe_allow_html=True)
        new_role = st.selectbox(
            "Switch Role (Demo)", 
            ["Administrator", "Editor", "Viewer"], 
            index=["Administrator", "Editor", "Viewer"].index(st.session_state.user_role)
        )
        if new_role != st.session_state.user_role:
            st.session_state.user_role = new_role
            st.rerun()

        st.markdown(f'''
            <div style="position:fixed; bottom:0; left:0; width:260px; background:white; border-top:1px solid #F3F4F6; padding:16px 24px; display:flex; align-items:center; gap:12px;">
                <div style="width:36px; height:36px; border-radius:50%; background:#CC0000; color:white; display:flex; align-items:center; justify-content:center; font-weight:600; font-size:14px;">JP</div>
                <div>
                    <div style="font-size:13px; font-weight:600; color:#111827;">{st.session_state.user_name}</div>
                    <div style="font-size:11px; color:#6B7280;">{st.session_state.user_role}</div>
                </div>
            </div>
        ''', unsafe_allow_html=True)

def render_dashboard_header(view_name):
    st.markdown(f'''
        <div style="background-color: #ffffff; border-bottom: 1px solid #E5E7EB; padding: 12px 32px; margin: 0 -2rem 24px -2rem; display: flex; justify-content: space-between; align-items: center; position: sticky; top: -1px; z-index: 100;">
            <div class="breadcrumb-container">
                <span class="breadcrumb-parent">GlossIQ</span>
                <span style="color:#D1D5DB; margin: 0 4px;">&gt;</span>
                <span style="color:#111827; font-weight: 600;">{view_name}</span>
            </div>
            <div class="header-right">
                <div class="search-mock" style="display: flex; align-items: center; gap: 8px;">
                    Search... (Ctrl+K)
                </div>
                <div class="system-status">
                    <span class="status-dot"></span>
                    All Systems Operational
                </div>
                <div style="opacity:0.6; cursor:pointer; font-size: 20px;">👤</div>
            </div>
        </div>
    ''', unsafe_allow_html=True)

def _img_tag(filename, size=24):
    """Return an <img> tag with a base64-encoded asset image."""
    img_path = os.path.join(os.path.dirname(__file__), "assets", filename)
    try:
        with open(img_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        ext = filename.split(".")[-1].lower()
        mime = "image/jpeg" if ext in ("jpg", "jfif", "jpeg") else f"image/{ext}"
        return f'<img src="data:{mime};base64,{b64}" style="width:{size}px;height:{size}px;object-fit:contain;">'
    except FileNotFoundError:
        return "🔌"

@st.dialog("Configure Integration")
def _configure_integration_dialog(name):
    """Dialog to configure integration connector credentials."""
    cfg = st.session_state.integration_connectors[name]
    st.markdown(f"**{name}** — {cfg['desc']}")
    st.divider()

    if name == "Databricks Unity":
        st.info("Connect to Databricks to push glossary terms as Unity Catalog tags (key = column name, value = business term).")
        st.text_input("Workspace URL", placeholder="https://adb-xxxx.azuredatabricks.net", value=cfg['api_endpoint'], key=f"int_ep_{name}")
        st.text_input("Personal Access Token", type="password", value=cfg['api_token'], key=f"int_tk_{name}")
    elif name == "Slack":
        st.text_input("Webhook URL", value=cfg['api_endpoint'], key=f"int_ep_{name}")
        st.text_input("Bot Token", type="password", value=cfg['api_token'], key=f"int_tk_{name}")
        st.text_input("Default Channel", value=cfg.get('channel', '#data-governance'), key=f"int_ch_{name}")
    elif name == "Microsoft Purview":
        st.info("Authenticate to Microsoft Purview data map to enable Search & Enrichment features.")
        st.text_input("Account Name", value=st.session_state.connector_creds.get('purview_account_name',''), key=f"mp_ac_{name}")
        st.text_input("Tenant ID", value=st.session_state.connector_creds.get('purview_tenant_id',''), key=f"mp_te_{name}")
        st.text_input("Client ID", value=st.session_state.connector_creds.get('purview_client_id',''), key=f"mp_ci_{name}")
        st.text_input("Client Secret", type="password", value=st.session_state.connector_creds.get('purview_client_secret',''), key=f"mp_cs_{name}")
    else:
        st.text_input("API Endpoint", value=cfg['api_endpoint'], key=f"int_ep_{name}")
        st.text_input("API Token / Secret", type="password", value=cfg['api_token'], key=f"int_tk_{name}")

    c1, c2 = st.columns(2)
    with c1:
        if st.button("Save & Connect", type="primary", use_container_width=True):
            if name == "Microsoft Purview":
                account_name = st.session_state[f"mp_ac_{name}"]
                tenant_id = st.session_state[f"mp_te_{name}"]
                client_id = st.session_state[f"mp_ci_{name}"]
                client_secret = st.session_state[f"mp_cs_{name}"]
                
                st.session_state.connector_creds.update({
                    'purview_account_name': account_name, 
                    'purview_tenant_id': tenant_id, 
                    'purview_client_id': client_id, 
                    'purview_client_secret': client_secret
                })
                connector = PurviewConnector(account_name, tenant_id, client_id, client_secret)
                success, msg = connector.authenticate()
                if success:
                    st.session_state.is_authenticated = True
                    try: 
                        st.session_state.purview_collections = connector.get_collections()
                    except: 
                        pass
                else:
                    st.error(f"Failed to authenticate: {msg}")
                    st.stop()
            elif name == "Databricks Unity":
                _ep = st.session_state[f"int_ep_{name}"]
                _tk = st.session_state[f"int_tk_{name}"]
                st.session_state.integration_connectors[name]['api_endpoint'] = _ep
                st.session_state.integration_connectors[name]['api_token'] = _tk
                with st.spinner("Testing Databricks connection…"):
                    _db_ok, _db_msg = DatabricksUnityConnector(_ep, _tk).test_connection()
                if not _db_ok:
                    st.error(f"Connection failed: {_db_msg}")
                    st.stop()
            else:
                st.session_state.integration_connectors[name]['api_endpoint'] = st.session_state[f"int_ep_{name}"]
                st.session_state.integration_connectors[name]['api_token'] = st.session_state[f"int_tk_{name}"]
                if name == "Slack":
                    st.session_state.integration_connectors[name]['channel'] = st.session_state[f"int_ch_{name}"]

            from datetime import datetime
            st.session_state.integration_connectors[name]['status'] = 'Connected'
            st.session_state.integration_connectors[name]['last_sync'] = datetime.now().strftime("%I:%M %p")
            st.success(f"Connected to {name} successfully!")
            st.rerun()
    with c2:
        if cfg['status'] == 'Connected':
            if st.button("Disconnect", use_container_width=True):
                st.session_state.integration_connectors[name]['status'] = 'Not connected'
                st.session_state.integration_connectors[name]['last_sync'] = ''
                if name == "Microsoft Purview":
                    st.session_state.is_authenticated = False
                st.rerun()

def render_integrations_tab():
    render_dashboard_header("Integrations & API")
    st.markdown('<div class="workbench-header"><div class="accent-line"></div><h1 class="workbench-title">Integrations & API</h1><p class="workbench-desc">Connect your glossary hub to external tools and expose approved terms via REST API</p></div>', unsafe_allow_html=True)

    # ── shared card renderer ─────────────────────────────────────────────────
    def _render_connector_card(col, name, cfg):
        is_connected = cfg['status'] == 'Connected'
        status_dot   = "#10B981" if is_connected else "#D1D5DB"
        push_badge   = '<span style="font-size:11px;background:#E0F2FE;color:#0369A1;padding:2px 8px;border-radius:12px;">Push</span>' if cfg['push'] else ''
        pull_badge   = '<span style="font-size:11px;background:#F3E8FF;color:#7E22CE;padding:2px 8px;border-radius:12px;">Pull</span>' if cfg['pull'] else ''
        sync_text    = f"Synced {cfg['last_sync']}" if cfg['last_sync'] else (cfg.get('channel') or ('Connected' if is_connected else 'Not connected'))

        # Build avatar: try image first, fall back to letter square
        img_html = _img_tag(cfg.get('image', ''), size=30)
        if img_html == '🔌':  # file not found
            avatar = f'<div style="width:36px;height:36px;border-radius:6px;background:{cfg["color_bg"]};color:{cfg["color_txt"]};font-weight:700;font-size:13px;display:flex;align-items:center;justify-content:center;flex-shrink:0;">{cfg["letter"]}</div>'
        else:
            avatar = f'<div style="width:36px;height:36px;border-radius:6px;background:{cfg["color_bg"]};display:flex;align-items:center;justify-content:center;flex-shrink:0;overflow:hidden;">{img_html}</div>'

        with col:
            st.markdown(f"""
            <div style="border:1px solid #E5E7EB;border-radius:8px;padding:16px;margin-bottom:8px;background:white;">
                <div style="display:flex;justify-content:space-between;align-items:center;">
                    <div style="display:flex;align-items:center;gap:12px;">
                        {avatar}
                        <div>
                            <div style="font-weight:600;color:#111827;font-size:15px;">{name}</div>
                            <div style="font-size:12px;color:#6B7280;">{cfg['desc']}</div>
                        </div>
                    </div>
                    <div style="width:8px;height:8px;border-radius:50%;background:{status_dot};"></div>
                </div>
                <div style="margin-top:12px;display:flex;gap:8px;">{push_badge} {pull_badge}</div>
                <div style="margin-top:14px;"><span style="font-size:12px;color:#6B7280;">{sync_text}</span></div>
            </div>
            """, unsafe_allow_html=True)
            btn_label = "Configure" if is_connected else "Connect"
            if st.button(btn_label, key=f"int_btn_{name}", use_container_width=True):
                _configure_integration_dialog(name)

    # ═══════════════════════════════════════════════════════════════════════════
    # CATALOG CONNECTORS
    # ═══════════════════════════════════════════════════════════════════════════
    st.markdown("<p style='font-size:13px;font-weight:600;color:#6B7280;text-transform:uppercase;margin-bottom:12px;'>CATALOG CONNECTORS</p>", unsafe_allow_html=True)

    connectors = st.session_state.integration_connectors
    names = list(connectors.keys())

    # Render 3 per row
    for row_start in range(0, len(names), 3):
        row_names = names[row_start:row_start + 3]
        cols = st.columns(3)
        for i, name in enumerate(row_names):
            _render_connector_card(cols[i], name, connectors[name])

@st.dialog("Review Term")
def _review_term_dialog(idx):
    item = st.session_state.review_queue[idx]
    st.markdown(f"### Review: {item['term']}")
    st.write(f"**Asset:** {item['asset']}")
    st.write(f"**Requested By:** {item['requester']}")
    st.write(f"**Description:** {item['description']}")
    
    st.divider()
    comment = st.text_area("Add a comment (optional)", key=f"rev_com_{idx}")
    
    c1, c2 = st.columns(2)
    with c1:
        if st.button("Approve", type="primary", use_container_width=True):
            st.session_state.review_queue[idx]['status'] = 'Approved'
            st.success("Term approved!")
            st.rerun()
    with c2:
        if st.button("Reject", use_container_width=True):
            st.session_state.review_queue[idx]['status'] = 'Rejected'
            st.rerun()

def render_review_tab():
    render_dashboard_header("Review & Approval")
    st.markdown(
        '<div class="workbench-header"><div class="accent-line"></div>'
        '<h1 class="workbench-title">Review & Approval Workflow</h1>'
        '<p class="workbench-desc">AI Suggestion → Conflict Check → Approve / Reject → Glossary Hub → Power Automate</p>'
        '</div>',
        unsafe_allow_html=True,
    )

    # ── Show persistent email notification after rerun ─────────────────────────
    if "_email_notification" in st.session_state:
        email_ok, email_msg = st.session_state.pop("_email_notification")
        if email_ok:
            st.success(f"📧 {email_msg}")
        else:
            st.warning(f"📧 Email not sent: {email_msg}")

    # ── Unity Catalog scope: when connected, every sub-tab is restricted to UC terms ──
    _uc_on     = st.session_state.get('integration_connectors', {}).get('Databricks Unity', {}).get('status') == 'Connected'
    _uc_source = "Databricks Unity Catalog" if _uc_on else None

    # ── Queue stats bar ────────────────────────────────────────────────────────
    stats = WorkflowManager.get_queue_stats(source_filter=_uc_source)
    s_cols = st.columns(5)
    STAT_META = [
        ("Pending",           "#F59E0B", "⏳"),
        ("Conflict Detected", "#EF4444", "⚠️"),
        ("Approved",          "#10B981", "✅"),
        ("Approved (Merged)", "#3B82F6", "🔀"),
        ("Rejected",          "#6B7280", "✖"),
    ]
    for col, (label, color, icon) in zip(s_cols, STAT_META):
        col.markdown(
            f"""<div style="background:white;border:1px solid #E5E7EB;border-top:3px solid {color};
            border-radius:8px;padding:14px 16px;text-align:center;">
            <div style="font-size:22px;font-weight:700;color:{color};">{stats.get(label, 0)}</div>
            <div style="font-size:12px;color:#6B7280;margin-top:2px;">{icon} {label}</div>
            </div>""",
            unsafe_allow_html=True,
        )

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Pre-load source-scoped audit log (used both by queue cards and Audit Log tab) ──
    _tab1_audit = WorkflowManager.load_audit_log()
    if _uc_on:
        _tab1_audit = [e for e in _tab1_audit if e.get("source") == "Databricks Unity Catalog"]

    # ── Inner workflow tabs ────────────────────────────────────────────────────
    wf_tab1, wf_tab2, wf_tab3 = st.tabs(
        ["📋 Approval Queue", "➕ User Suggestion", "📜 Audit Log"]
    )

    # ══════════════════════════════════════════════════════════════════════════
    # TAB 2 — User Suggestion
    # ══════════════════════════════════════════════════════════════════════════
    with wf_tab2:
        st.markdown("#### Create Glossary Term Suggestion")
        st.caption(
            "Manually submit a term for review, or use the **Glossary AI** tab to auto-generate "
            "terms and they will appear here automatically."
        )

        with st.form("create_suggestion_form", clear_on_submit=True):
            f_col1, f_col2 = st.columns([2, 1])
            with f_col1:
                f_physical = st.text_input("Physical Term", placeholder="e.g. CUST_LTV")
                f_term = st.text_input("Business Term *", placeholder="e.g. Customer Lifetime Value")
                f_def  = st.text_area("Definition *", placeholder="A precise business definition…", height=100)
            with f_col2:
                _manual_sources = ["Manual", "AI Suggester", "Data Steward", "Business User", "Imported"]
                if _uc_on:
                    _manual_sources = ["Databricks Unity Catalog"] + _manual_sources
                f_source = st.selectbox(
                    "Source",
                    _manual_sources,
                )
                f_score = st.slider("Confidence Score", 0, 100, 80)

            submitted = st.form_submit_button("Add to Approval Queue", type="primary", use_container_width=True)
            if submitted:
                if not f_term.strip() or not f_def.strip():
                    st.error("Business Term and Definition are required.")
                else:
                    queue_before = WorkflowManager.load_approval_queue()
                    already = next(
                        (e for e in queue_before
                         if e.get("term_name", "").strip().lower() == f_term.strip().lower()
                         and e.get("status") in ("Pending", "Conflict Detected")),
                        None,
                    )
                    if already:
                        st.warning(f"⚠️ **'{f_term}'** is already in the Approval Queue with status **{already['status']}**. No duplicate added.")
                    else:
                        WorkflowManager.create_suggested_term(
                            term_name        = f_term,
                            definition       = f_def,
                            source           = f_source,
                            confidence_score = f_score,
                            physical_term    = f_physical,
                        )
                        st.success(f"✅ Term **'{f_term}'** added to the Approval Queue.")
                        st.rerun()

    # ══════════════════════════════════════════════════════════════════════════
    # TAB 1 — Approval Queue
    # ══════════════════════════════════════════════════════════════════════════
    with wf_tab1:
        # ── Header row with Clear Decided button ─────────────────────────────────
        hdr_col, btn_col = st.columns([3, 1])
        hdr_col.markdown("#### Approval Queue")
        with btn_col:
            if st.button("🗑️ Clear Decided", use_container_width=True,
                         help="Remove all Approved/Rejected entries from the queue. They remain in the Audit Log."):
                removed = WorkflowManager.purge_decided_from_queue()
                if removed:
                    st.success(f"Removed {removed} decided entry(s) from the queue.")
                else:
                    st.info("No decided entries to remove.")
                st.rerun()

        queue = WorkflowManager.load_approval_queue()
        # When UC is connected, restrict queue to UC-sourced terms only
        if _uc_on:
            queue = [e for e in queue if e.get("source") == "Databricks Unity Catalog"]
        # Default: show only undecided items
        undecided_statuses = ("Pending", "Conflict Detected")
        if not queue:
            st.info("The approval queue is empty. Add terms in the **User Suggestion** tab.")
        else:
            # ── Filter bar ────────────────────────────────────────────────────
            filter_col, _, search_col = st.columns([1, 2, 1])
            with filter_col:
                status_filter = st.selectbox(
                    "Filter by Status",
                    ["Active (Pending + Conflict)", "Pending", "Conflict Detected",
                     "Approved", "Approved (Merged)", "Rejected", "All"],
                    key="aq_status_filter",
                )
            with search_col:
                search_term = st.text_input(
                    "Search Term Name", placeholder="Type to filter…", key="aq_search"
                )

            if status_filter == "Active (Pending + Conflict)":
                filtered = [e for e in queue if e.get("status") in undecided_statuses]
            elif status_filter == "All":
                filtered = queue
            else:
                filtered = [e for e in queue if e.get("status") == status_filter]

            if search_term:
                filtered = [
                    e for e in filtered
                    if search_term.lower() in e.get("term_name", "").lower()
                ]

            if not filtered:
                st.info("No items match the current filter.")
            else:
                # Get configured webhooks for Power Automate
                webhooks = st.session_state.get("webhooks", [])

                # Split into Table-level and Column-level groups
                # Use (e.get("term_type") or "Column") to safely handle None values
                table_entries  = [e for e in filtered if (e.get("term_type") or "Column").strip().lower() == "table"]
                column_entries = [e for e in filtered if (e.get("term_type") or "Column").strip().lower() != "table"]

                # ── Helpers ───────────────────────────────────────────────
                def _render_queue_entry(entry, idx):
                    status      = entry.get("status", "Pending")
                    term_id     = entry["term_id"]
                    term_name   = _html.escape(entry.get("term_name", ""))
                    definition  = _html.escape(entry.get("definition", ""))
                    score       = entry.get("confidence_score", 0)
                    ai_src      = entry.get("source", "")
                    ai_label    = "User Submitted" if ai_src == "User" else "AI Suggested"
                    ai_type     = "user" if ai_src == "User" else "ai"
                    _pt = (entry.get("physical_term") or entry.get("related_column") or
                           (entry.get("table_name") if (entry.get("term_type") or "").lower() == "table" else ""))
                    source_disp = _html.escape(_pt or ai_src or "")
                    has_conflict = bool(entry.get("conflict_found"))
                    suggested_raw  = entry.get("created_at") or entry.get("suggested_at") or ""
                    suggested_date = suggested_raw[:10] if suggested_raw else "—"

                    # Check audit log: if term already approved there, treat as conflict
                    # _tab1_audit is pre-scoped to UC when UC is connected (closure variable)
                    _audit = _tab1_audit
                    _ename = (entry.get("term_name") or "").strip().lower()
                    _ephys = (entry.get("physical_term") or entry.get("related_column") or "").strip().lower()
                    _etbl  = (entry.get("table_name") or "").strip().lower()

                    # Case 1: exact same business term already approved → must Merge
                    audit_conflict = any(
                        (e.get("term_name") or "").strip().lower() == _ename
                        and e.get("status") == "Approved"
                        for e in _audit
                    )

                    # Case 2: same physical_term + table but DIFFERENT business term already approved
                    # → warn but still allow Approve / Reject
                    _prior_diff = next(
                        (
                            e for e in _audit
                            if e.get("status") == "Approved"
                            and _ephys
                            and (e.get("physical_term") or "").strip().lower() == _ephys
                            and (e.get("table_name") or "").strip().lower() == _etbl
                            and (e.get("term_name") or "").strip().lower() != _ename
                        ),
                        None,
                    )
                    audit_diff_term = _prior_diff is not None

                    if audit_conflict:
                        has_conflict = True
                    elif audit_diff_term:
                        has_conflict = True

                    # Build badge / conflict snippets as plain strings (no multiline)
                    ai_bs = ("background:#E6F1FB;color:#185FA5;border:0.5px solid #B5D4F4;"
                             if ai_type == "ai" else
                             "background:#EAF3DE;color:#3B6D11;border:0.5px solid #C0DD97;")
                    conflict_tag = (
                        (
                            '<span style="display:inline-flex;align-items:center;gap:3px;font-size:11px;'
                            'color:#A32D2D;background:#FCEBEB;border:0.5px solid #F7C1C1;'
                            'border-radius:4px;padding:2px 6px;">&#9888; Already Approved — Use Merge</span>'
                        ) if audit_conflict else (
                            '<span style="display:inline-flex;align-items:center;gap:3px;font-size:11px;'
                            'color:#854F0B;background:#FEF3C7;border:0.5px solid #FDE68A;'
                            'border-radius:4px;padding:2px 6px;">&#9888; Different Business Term Already Approved</span>'
                        ) if audit_diff_term else (
                            '<span style="display:inline-flex;align-items:center;gap:3px;font-size:11px;'
                            'color:#A32D2D;background:#FCEBEB;border:0.5px solid #F7C1C1;'
                            'border-radius:4px;padding:2px 6px;">&#9888; Conflict Detected</span>'
                        )
                    ) if has_conflict else ""

                    # Card status badge — dynamic based on conflict state
                    if audit_conflict:
                        status_badge_style = "background:#FCEBEB;color:#A32D2D;border:0.5px solid #F7C1C1;"
                        status_badge_text  = "Conflict — Use Merge"
                        card_border        = "border:1px solid #F7C1C1;"
                    elif audit_diff_term:
                        status_badge_style = "background:#FEF3C7;color:#854F0B;border:0.5px solid #FDE68A;"
                        status_badge_text  = "Conflict — Diff Term"
                        card_border        = "border:1px solid #FDE68A;"
                    elif has_conflict:
                        status_badge_style = "background:#FCEBEB;color:#A32D2D;border:0.5px solid #F7C1C1;"
                        status_badge_text  = "Conflict Detected"
                        card_border        = "border:1px solid #F7C1C1;"
                    else:
                        status_badge_style = "background:#FAEEDA;color:#854F0B;border:0.5px solid #FAC775;"
                        status_badge_text  = "Pending"
                        card_border        = "border:0.5px solid #E0DED8;"

                    # Full card — single st.markdown call, HTML built by concatenation (no newlines/indentation issues)
                    card = (
                        f'<div style="{card_border}border-radius:10px;padding:14px 16px;background:#fff;margin-bottom:4px;">'
                          '<div style="display:flex;justify-content:space-between;align-items:flex-start;gap:12px;">'
                            '<div style="flex:1;min-width:0;">'
                              f'<div style="font-size:13px;font-weight:600;color:#1A1A18;margin-bottom:4px;">{term_name}</div>'
                              f'<div style="font-size:12px;color:#6B6B67;line-height:1.55;margin-bottom:8px;">{definition}</div>'
                              '<div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;">'
                                f'<span style="font-size:11px;color:#888780;">'
                                  '<span style="display:inline-block;width:6px;height:6px;border-radius:50%;background:#378ADD;margin-right:4px;vertical-align:middle;"></span>'
                                  f'Source: <strong>{source_disp}</strong>'
                                '</span>'
                                f'{conflict_tag}'
                              '</div>'
                            '</div>'
                            '<div style="flex-shrink:0;min-width:140px;text-align:right;">'
                              '<div style="display:flex;align-items:center;gap:4px;justify-content:flex-end;flex-wrap:wrap;margin-bottom:5px;">'
                                f'<span style="font-size:10px;font-weight:500;padding:2px 7px;border-radius:4px;{status_badge_style}">{status_badge_text}</span>'
                                f'<span style="font-size:10px;font-weight:500;padding:2px 7px;border-radius:4px;{ai_bs}">{ai_label}</span>'
                                f'<span style="font-size:11px;font-weight:700;color:#2C2C2A;">{score}%</span>'
                              '</div>'
                              f'<div style="font-size:10px;color:#888780;line-height:1.5;">Suggested on<br/>{suggested_date}</div>'
                            '</div>'
                          '</div>'
                        '</div>'
                    )

                    cb_col, card_col = st.columns([0.4, 5.6])
                    with cb_col:
                        st.write("")
                        st.checkbox("select", key=f"sel_{term_id}", label_visibility="collapsed")
                    with card_col:
                        st.markdown(card, unsafe_allow_html=True)

                        if status in ("Pending", "Conflict Detected"):
                            if audit_conflict:
                                # Same business term already approved: ✓ disabled, ✕ hidden, 🔀 Merge visible
                                _, _, ba, bm, bmore = st.columns([2, 2, 1, 1, 1])
                            else:
                                # Normal OR audit_diff_term: all three buttons shown, approve/reject enabled
                                _, _, ba, br, bm = st.columns([2, 2, 1, 1, 1])

                            if audit_diff_term and not audit_conflict:
                                st.caption(
                                    f"⚠️ Physical term **{_ephys.upper()}** in table **{_etbl}** "
                                    f"already has an approved business term "
                                    f"**'{_prior_diff.get('term_name', '')}'**. "
                                    "Approving will deactivate the old record and create a new active version."
                                )
                            with ba:
                                if st.button("✓", key=f"approve_{term_id}",
                                             use_container_width=True, type="primary",
                                             disabled=audit_conflict):
                                    ok, msg = WorkflowManager.approve_term(
                                        term_id,
                                        approver_comment=st.session_state.get(f"comment_{term_id}", ""),
                                        webhooks=webhooks,
                                    )
                                    st.success(msg) if ok else st.error(msg)
                                    st.rerun()
                            if audit_conflict:
                                with bm:
                                    if st.button("🔀 Merge", key=f"merge_{term_id}",
                                                 use_container_width=True, type="primary",
                                                 help="Term already approved — merge to create new version"):
                                        ok, msg = WorkflowManager.approve_with_merge(
                                            term_id,
                                            approver_comment=st.session_state.get(f"comment_{term_id}", ""),
                                            webhooks=webhooks,
                                        )
                                        st.success(msg) if ok else st.error(msg)
                                        st.rerun()
                                with bmore:
                                    with st.popover("···", use_container_width=True):
                                        st.markdown("**Additional actions**")
                                        st.text_input(
                                            "Comment",
                                            placeholder="Approver comment…",
                                            key=f"comment_{term_id}",
                                            label_visibility="collapsed",
                                        )
                                        st.warning("⚠️ This term was already approved. Approve (✓) and Reject (✕) are disabled. Use 🔀 Merge to create a new version.")
                            else:
                                with br:
                                    if st.button("✕", key=f"reject_{term_id}",
                                                 use_container_width=True):
                                        ok, msg, pa_results = WorkflowManager.reject_term(
                                            term_id,
                                            approver_comment=st.session_state.get(f"comment_{term_id}", ""),
                                            webhooks=webhooks,
                                        )
                                        if ok:
                                            active_wh = [w for w in webhooks if w.get("status") == "Active"
                                                         and w.get("event") == "term.rejected"]
                                            if not active_wh:
                                                st.session_state["_email_notification"] = (
                                                    False,
                                                    "No active PA webhook for 'term.rejected'. "
                                                    "Go to **Integrations & API → Webhooks**."
                                                )
                                            else:
                                                succeeded = [r for r in pa_results if r.get("success")]
                                                if succeeded:
                                                    st.session_state["_email_notification"] = (
                                                        True, "Power Automate triggered — email sent.")
                                                else:
                                                    err = (pa_results[0].get("error",
                                                           f"HTTP {pa_results[0].get('status_code', '?')}")
                                                           if pa_results else "No response")
                                                    st.session_state["_email_notification"] = (
                                                        False, f"PA call failed: {err}")
                                        else:
                                            st.error(msg)
                                        st.rerun()
                                with bm:
                                    with st.popover("···", use_container_width=True):
                                        st.markdown("**Additional actions**")
                                        st.text_input(
                                            "Comment",
                                            placeholder="Approver comment…",
                                            key=f"comment_{term_id}",
                                            label_visibility="collapsed",
                                        )
                                        st.divider()
                                        if not entry.get("conflict_checked"):
                                            if st.button("🔍 Check Conflict",
                                                         key=f"conflict_{term_id}",
                                                         use_container_width=True):
                                                cf, mt = WorkflowManager.run_conflict_check(term_id)
                                                st.success("No conflict found.") if not cf else st.warning(f"Conflict: {mt}")
                                                st.rerun()
                                        else:
                                            st.caption("⚠️ Conflict Found" if entry.get("conflict_found")
                                                       else "✅ No Conflict")
                                        st.divider()
                                        merge_disabled = not entry.get("conflict_found", False)
                                        if st.button("🔀 Merge", key=f"merge_{term_id}",
                                                     use_container_width=True, disabled=merge_disabled,
                                                     help="Only when conflict detected"):
                                            ok, msg = WorkflowManager.approve_with_merge(
                                                term_id,
                                                approver_comment=st.session_state.get(f"comment_{term_id}", ""),
                                                webhooks=webhooks,
                                            )
                                            st.success(msg) if ok else st.error(msg)
                                            st.rerun()

                        elif status in ("Approved", "Approved (Merged)", "Rejected"):
                            dec_date = (entry.get('decision_date') or '')[:10]
                            comment  = entry.get('approver_comment', '')
                            cap = f"{status} · {dec_date}"
                            if comment:
                                cap += f" · {comment}"
                            st.caption(cap)

                    st.markdown("<hr style='margin:0 0 4px 0;border:none;border-top:0.5px solid #EBEBEB;'>",
                                unsafe_allow_html=True)

                def _render_decided_entry(entry, idx):
                    """Render an approved/rejected entry as a collapsed expander."""
                    status    = entry.get("status", "")
                    term_name = entry.get("term_name", "")
                    dec_date  = (entry.get("decision_date") or "")[:10]
                    icon      = "✅" if "Approved" in status else "✖"
                    label     = f"{icon} {term_name}  —  {status}  ({dec_date})"
                    with st.expander(label, expanded=False):
                        if entry.get("physical_term"):
                            st.markdown(f"**Physical Term:** {entry.get('physical_term')}")
                        st.markdown(f"**Definition:** {entry.get('definition', '')}")
                        if entry.get("table_name"):
                            st.markdown(f"**Table:** {entry.get('table_name')}")
                        st.markdown(f"**Source:** {entry.get('source', '')}  |  **Confidence:** {entry.get('confidence_score', '')}%")
                        if entry.get("approver_comment"):
                            st.markdown(f"**Comment:** _{entry['approver_comment']}_")

                tbl_active   = [e for e in table_entries  if e.get("status") in ("Pending", "Conflict Detected")]
                tbl_decided  = [e for e in table_entries  if e.get("status") not in ("Pending", "Conflict Detected")]
                col_active   = [e for e in column_entries if e.get("status") in ("Pending", "Conflict Detected")]
                col_decided  = [e for e in column_entries if e.get("status") not in ("Pending", "Conflict Detected")]

                # ── Table-Level Terms (collapsible) ───────────────────────────
                with st.expander(f"🗂️  Table-Level Terms  ·  {len(tbl_active)} pending", expanded=True):
                    if tbl_active:
                        for idx, entry in enumerate(tbl_active):
                            _render_queue_entry(entry, idx)
                    elif not tbl_decided:
                        st.caption("No table-level terms in the current filter.")
                    for idx, entry in enumerate(tbl_decided):
                        _render_decided_entry(entry, idx)

                # ── Column-Level Terms (collapsible) ──────────────────────────
                with st.expander(f"📄  Column-Level Terms  ·  {len(col_active)} pending", expanded=True):
                    if col_active:
                        for idx, entry in enumerate(col_active):
                            _render_queue_entry(entry, len(tbl_active) + idx)
                    elif not col_decided:
                        st.caption("No column-level terms in the current filter.")
                    for idx, entry in enumerate(col_decided):
                        _render_decided_entry(entry, len(tbl_decided) + idx)

                # ── Footer: bulk actions ──────────────────────────────────────
                all_active = tbl_active + col_active
                n_sel = sum(
                    1 for e in all_active
                    if st.session_state.get(f"sel_{e['term_id']}", False)
                )
                st.markdown("<div style='height:6px;'></div>", unsafe_allow_html=True)
                st.markdown(
                    "<style>div[data-testid='stButton'] button[kind='primaryFormSubmit'],"
                    "div[data-testid='stButton'] button[kind='primary'] {color:#ffffff !important;}</style>",
                    unsafe_allow_html=True,
                )
                st.markdown(
                    "<div style='border:0.5px solid #E0DED8;border-radius:10px;"
                    "padding:10px 16px;background:#fff;display:flex;"
                    "align-items:center;justify-content:space-between;'>"
                    f"<span style='font-size:12px;color:#888780;'>"
                    f"{n_sel} item{'s' if n_sel != 1 else ''} selected</span>"
                    "</div>",
                    unsafe_allow_html=True,
                )
                _fc1, _fc2, _fc3 = st.columns([2, 2, 2])
                with _fc1:
                    if st.button("✕ Reject Unconfirmed", key="bulk_reject_unconfirmed",
                                 use_container_width=True,
                                 help="Reject all conflict-flagged pending terms"):
                        for e in all_active:
                            if e.get("conflict_found"):
                                WorkflowManager.reject_term(
                                    e["term_id"],
                                    approver_comment="Bulk: rejected unconfirmed",
                                    webhooks=webhooks,
                                )
                        st.rerun()
                with _fc2:
                    if st.button("✓ Approve Selected", key="bulk_approve",
                                 use_container_width=True, type="primary",
                                 disabled=(n_sel == 0)):
                        for e in all_active:
                            if st.session_state.get(f"sel_{e['term_id']}", False):
                                WorkflowManager.approve_term(
                                    e["term_id"],
                                    approver_comment="Bulk approve",
                                    webhooks=webhooks,
                                )
                        st.rerun()
                with _fc3:
                    if st.button("✕ Reject Selected", key="bulk_reject",
                                 use_container_width=True,
                                 disabled=(n_sel == 0)):
                        for e in all_active:
                            if st.session_state.get(f"sel_{e['term_id']}", False):
                                WorkflowManager.reject_term(
                                    e["term_id"],
                                    approver_comment="Bulk reject",
                                    webhooks=webhooks,
                                )
                        st.rerun()

    # ══════════════════════════════════════════════════════════════════════════
    # TAB 3 — Audit Log
    # ══════════════════════════════════════════════════════════════════════════
    with wf_tab3:
        st.markdown("#### Audit Log — Decision History")

        decided = WorkflowManager.load_audit_log()

        if not decided:
            st.info("No decisions have been made yet.")
        else:
            # Deduplicate by (term_name, status) — keeps latest decision per term+status,
            # even if term was re-submitted with a different term_id
            seen = {}
            for e in sorted(decided, key=lambda x: x.get("decision_date", "")):
                key = ((e.get("term_name") or "").strip().lower(), e.get("status"))
                seen[key] = e
            unique = sorted(seen.values(), key=lambda x: x.get("decision_date", ""), reverse=True)

            # ── Source filter — auto-select based on active connector ─────────
            all_sources = sorted(set(e.get("source") or "Unknown" for e in unique))
            _connectors_state = st.session_state.get('integration_connectors', {})
            _purview_on = _connectors_state.get('Microsoft Purview', {}).get('status') == 'Connected'
            # Determine default: UC connected → UC; Purview only → All Sources (Purview governs all); else All
            if _uc_on and "Databricks Unity Catalog" in all_sources:
                _default_src = "Databricks Unity Catalog"
            else:
                _default_src = "All Sources"
            src_filter_col, tbl_filter_col, _ = st.columns([1, 1, 2])
            with src_filter_col:
                _src_opts = ["All Sources"] + all_sources
                selected_source = st.selectbox(
                    "Filter by Source",
                    _src_opts,
                    index=_src_opts.index(_default_src) if _default_src in _src_opts else 0,
                    key="audit_source_filter",
                )
            if selected_source != "All Sources":
                unique = [e for e in unique if (e.get("source") or "Unknown") == selected_source]

            # ── Table filter ──────────────────────────────────────────────────
            all_tables = sorted(set(e.get("table_name", "") or "—" for e in unique))
            with tbl_filter_col:
                selected_table = st.selectbox(
                    "Filter by Table",
                    ["All Tables"] + all_tables,
                    key="audit_table_filter",
                )

            filtered_log = unique if selected_table == "All Tables" else [
                e for e in unique if (e.get("table_name") or "—") == selected_table
            ]

            # ── Render table-by-table ─────────────────────────────────────────
            tables_in_view = sorted(set(e.get("table_name", "") or "—" for e in filtered_log))
            for table in tables_in_view:
                table_entries = [e for e in filtered_log if (e.get("table_name") or "—") == table]
                st.markdown(
                    f"<div style='margin:16px 0 6px 0;padding:6px 14px;"
                    f"background:#EFF6FF;border-left:4px solid #3B82F6;"
                    f"border-radius:4px;font-weight:700;font-size:14px;'>📋 {table}</div>",
                    unsafe_allow_html=True,
                )
                rows = []
                for sno, e in enumerate(table_entries, start=1):
                    rows.append({
                        "S.No":            sno,
                        "Physical Term":   e.get("physical_term") or "—",
                        "Business Term":   e.get("term_name"),
                        "Status":          e.get("status"),
                        "Source":          e.get("source"),
                        "Confidence":      e.get("confidence_score"),
                        "Conflict":        "Yes" if e.get("conflict_found") else "No",
                        "Decision Date":   (e.get("decision_date") or "")[:19].replace("T", " "),
                        "Comment":         e.get("approver_comment", ""),
                    })
                df_tbl = pd.DataFrame(rows)
                st.dataframe(
                    df_tbl,
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "S.No":          st.column_config.NumberColumn("S.No", width="small"),
                        "Status":        st.column_config.TextColumn("Status", width="small"),
                        "Physical Term": st.column_config.TextColumn("Physical Term", width="medium"),
                        "Confidence":    st.column_config.NumberColumn("Confidence (%)", width="small"),
                    },
                )

def _infer_domain(table_name: str, source: str) -> str:
    """Infer a business domain from table name and source system."""
    tl = table_name.lower()
    if any(x in tl for x in ['patient', 'clinical', 'medical', 'diagnosis', 'treatment', 'health']):
        return 'Healthcare'
    if any(x in tl for x in ['sales', 'revenue', 'invoice', 'payment', 'finance', 'ledger']):
        return 'Finance'
    if any(x in tl for x in ['customer', 'client', 'crm', 'account', 'contact']):
        return 'CRM'
    if any(x in tl for x in ['product', 'inventory', 'item', 'sku', 'catalog']):
        return 'Product'
    if any(x in tl for x in ['employee', 'hr', 'staff', 'payroll', 'workforce']):
        return 'HR'
    if 'purview' in source.lower():
        return 'Governance'
    if 'databricks' in source.lower():
        return 'Data Engineering'
    return 'Enterprise'


def _safe_mermaid_id(s: str) -> str:
    import re
    return re.sub(r'[^a-zA-Z0-9_]', '_', s)


def _mermaid_label(s: str) -> str:
    return s.replace('"', "'").replace('\n', ' ')


def _render_mermaid(mermaid_code: str, height: int = 480) -> None:
    """Render a Mermaid diagram inside an iframe-safe HTML block."""
    st.components.v1.html(
        f"""<!DOCTYPE html>
<html>
<head>
<script type="module">
  import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.esm.min.mjs';
  mermaid.initialize({{
    startOnLoad: true,
    theme: 'default',
    flowchart: {{ curve: 'basis', useMaxWidth: true, padding: 24 }}
  }});
</script>
<style>body{{margin:0;padding:12px;background:#fff;font-family:Inter,sans-serif;}}</style>
</head>
<body>
<div class="mermaid">
{mermaid_code}
</div>
</body>
</html>""",
        height=height,
        scrolling=True,
    )


def render_lineage_tab():
    render_dashboard_header("Lineage Map")
    st.markdown(
        '<div class="workbench-header"><div class="accent-line"></div>'
        '<h1 class="workbench-title">Business Term Lineage</h1>'
        '<p class="workbench-desc">End-to-end lineage: '
        '<strong>Source</strong> → <strong>Asset (Table)</strong> → <strong>Attribute (Column)</strong> → <strong>Business Term</strong>, '
        'with Domain ownership and confidence score. Only terms from connected sources are shown.</p>'
        '</div>',
        unsafe_allow_html=True,
    )

    # ── Source-to-connector mapping ──────────────────────────────────────────
    # Maps a glossary "Source" value → integration_connectors key
    # Only terms whose source maps to a Connected integration are shown.
    _SRC_CONNECTOR_MAP = {
        "Databricks Unity Catalog": "Databricks Unity",
        "Microsoft Purview":        "Microsoft Purview",
    }

    _connectors = st.session_state.get("integration_connectors", {})

    def _source_is_available(src: str) -> bool:
        # AI Suggester / Manual / etc. are internal — never shown in lineage.
        # Only sources that exist in _SRC_CONNECTOR_MAP are real integrations.
        if src not in _SRC_CONNECTOR_MAP:
            return False
        connector_key = _SRC_CONNECTOR_MAP[src]
        # Direct match: the source's own connector is connected
        if _connectors.get(connector_key, {}).get("status") == "Connected":
            return True
        # Purview as governance layer: when Purview is connected it catalogs
        # Databricks Unity Catalog assets, so surface those terms too.
        if src == "Databricks Unity Catalog":
            return _connectors.get("Microsoft Purview", {}).get("status") == "Connected"
        return False

    # ── Load glossary_master ─────────────────────────────────────────────────
    glossary_path = os.path.join(os.path.dirname(__file__), 'backend', 'glossary_master.json')
    try:
        with open(glossary_path, encoding='utf-8') as _f:
            glossary_data = json.load(_f)
    except Exception:
        glossary_data = {}

    # ── Flatten ALL active terms (used for total count) ──────────────────────
    all_terms_full: dict = {}
    for entries in glossary_data.values():
        for entry in entries:
            if entry.get("Active", 0) == 1:
                bt = entry["Business Term"]
                if bt not in all_terms_full:
                    all_terms_full[bt] = []
                all_terms_full[bt].append(entry)

    # ── Filter to CONNECTED-source terms only ────────────────────────────────
    # Strict: only terms whose source maps to a currently-connected integration.
    # Purview connected → all glossary terms (Purview governs the whole hub).
    # Databricks connected → only Databricks-sourced terms.
    # Neither → nothing shown.
    all_terms: dict = {}
    for bt, ents in all_terms_full.items():
        filtered = [e for e in ents if _source_is_available(e.get("Source", ""))]
        if filtered:
            all_terms[bt] = filtered

    purview_connected = _connectors.get("Microsoft Purview", {}).get("status") == "Connected"

    if not all_terms:
        st.warning(
            "No terms available from connected sources. "
            "Connect **Microsoft Purview** or **Databricks Unity** in **Integrations & API**."
        )
        if st.button("Go to Integrations & API", key="lin_goto_int"):
            st.session_state.selected_tab = "Integrations & API"
            st.rerun()
        return

    # ── Term selector ────────────────────────────────────────────────────────
    term_list = sorted(all_terms.keys())
    selected_term = st.selectbox(
        "Select a Business Term to explore its lineage",
        term_list,
        key="lineage_term_selector",
    )

    entries = all_terms[selected_term]

    # ── Build Mermaid lineage diagram ────────────────────────────────────────
    # Layout: [Integration Source] --> [Table] --> [Column] --> ((Business Term))
    #                                              [Domain] -.-> ((Business Term))
    lines = ['flowchart LR']
    lines.append('    classDef source  fill:#DBEAFE,stroke:#2563EB,color:#1E3A8A,font-weight:700,rx:6')
    lines.append('    classDef tbl     fill:#D1FAE5,stroke:#059669,color:#064E3B,font-weight:600')
    lines.append('    classDef col     fill:#FEF3C7,stroke:#D97706,color:#78350F,font-weight:600')
    lines.append('    classDef term    fill:#CC0000,stroke:#7F1D1D,color:#FFFFFF,font-weight:700,font-size:15px')
    lines.append('    classDef domain  fill:#F3E8FF,stroke:#7C3AED,color:#4C1D95,font-weight:600')
    lines.append('    classDef purview fill:#EFF6FF,stroke:#1D4ED8,color:#1E3A8A,font-weight:600')
    lines.append('    classDef sl_node fill:#F9FAFB,stroke:#D1D5DB,color:#6B7280,font-size:12px')
    lines.append('')

    # Central term node (right-most)
    term_node_id = 'BTERM'
    lines.append(f'    {term_node_id}(("{_mermaid_label(selected_term)}"))')
    lines.append(f'    class {term_node_id} term')
    lines.append('')

    seen_src, seen_tbl, seen_col, seen_dom = {}, {}, {}, {}

    databricks_connected = _connectors.get("Databricks Unity", {}).get("status") == "Connected"

    for entry in entries:
        raw_src = entry.get("Source", "Unknown")
        tbl     = entry.get("table_name", "unknown")
        phys    = entry.get("Physical Term", "")
        etype   = entry.get("Type", "Column")
        dom     = _infer_domain(tbl, raw_src)
        conf    = entry.get("Confidence (%)", 0)

        # Display source: always show the CONNECTED integration, not the internal generation source.
        # Purview only connected  → show all terms as "Microsoft Purview"
        # Databricks only         → show as "Databricks Unity Catalog"
        # Both connected          → keep original source label
        if purview_connected and not databricks_connected:
            src = "Microsoft Purview"
        elif databricks_connected and not purview_connected:
            src = "Databricks Unity Catalog"
        else:
            src = raw_src  # both connected — preserve original

        src_id = _safe_mermaid_id(f"SRC_{src}")
        tbl_id = _safe_mermaid_id(f"TBL_{tbl}")
        col_id = _safe_mermaid_id(f"COL_{tbl}_{phys}")
        dom_id = _safe_mermaid_id(f"DOM_{dom}")

        # Source node
        if src_id not in seen_src:
            seen_src[src_id] = src
            if "databricks" in src.lower():
                icon, cls = "🔷", "source"
            else:  # Microsoft Purview or any mapped integration
                icon, cls = "🔵", "purview"
            lines.append(f'    {src_id}["{icon} {_mermaid_label(src)}"]')
            lines.append(f'    class {src_id} {cls}')

        # Table node  (labelled as "asset")
        if tbl_id not in seen_tbl:
            seen_tbl[tbl_id] = tbl
            lines.append(f'    {tbl_id}[("📋 {_mermaid_label(tbl)}")]')
            lines.append(f'    class {tbl_id} tbl')

        # Source ──source──► Table(asset)
        lines.append(f'    {src_id} -->|"source"| {tbl_id}')

        # Column node (attribute) → Business Term
        if etype == "Column" and phys:
            if col_id not in seen_col:
                seen_col[col_id] = phys
                lines.append(f'    {col_id}["⚙ {_mermaid_label(phys)}\nattribute"]')
                lines.append(f'    class {col_id} col')
            # Table ──asset──► Column(physical term)
            lines.append(f'    {tbl_id} -->|"asset"| {col_id}')
            # Column ──maps to · score──► Business Term
            lines.append(f'    {col_id} -->|"maps to · {conf}%"| {term_node_id}')
        else:
            # Table(asset) ──maps to · score──► Business Term (table-level term)
            lines.append(f'    {tbl_id} -->|"maps to · {conf}%"| {term_node_id}')

        # Domain node (dashed arrow into term)
        if dom_id not in seen_dom:
            seen_dom[dom_id] = dom
            lines.append(f'    {dom_id}[/"🏷 {_mermaid_label(dom)} Domain · {conf}% score"/]')
            lines.append(f'    class {dom_id} domain')
        lines.append(f'    {dom_id} -.->|"owns"| {term_node_id}')

    # Purview is already the primary source node — no separate catalogued node needed
    # (only add if Purview NOT connected, to show governance relationship)
    if not purview_connected:
        lines.append('')
        lines.append('    PV_CAT["📘 Microsoft Purview"]')
        lines.append('    class PV_CAT purview')
        lines.append(f'    PV_CAT -.->|"catalogued"| {term_node_id}')

    mermaid_lineage = '\n'.join(lines)

    # ── Render: Business Term Lineage diagram ────────────────────────────────
    st.markdown("##### Lineage Graph")
    _render_mermaid(mermaid_lineage, height=480)

    # ── Definition ───────────────────────────────────────────────────────────
    st.markdown("**Definition:**")
    for entry in reversed(entries):
        defn = entry.get("Definition / Description", "")
        if defn:
            st.info(defn)
            break

def render_search_tab():
    render_dashboard_header("Asset Search")

    _connectors  = st.session_state.integration_connectors
    _purview_on  = _connectors.get("Microsoft Purview", {}).get("status") == "Connected"
    _db_on       = _connectors.get("Databricks Unity", {}).get("status") == "Connected"

    if _purview_on and _db_on:
        _asset_desc = "Discover and select data assets from Microsoft Purview or Databricks Unity Catalog for AI analysis"
    elif _purview_on:
        _asset_desc = "Discover and select data assets from Microsoft Purview for AI analysis"
    elif _db_on:
        _asset_desc = "Discover and select data assets from Databricks Unity Catalog for AI analysis"
    else:
        _asset_desc = "Discover and select data assets from Microsoft Purview or Databricks Unity Catalog for AI analysis"

    st.markdown(f'<div class="workbench-header"><div class="accent-line"></div><h1 class="workbench-title">Asset Search</h1><p class="workbench-desc">{_asset_desc}</p></div>', unsafe_allow_html=True)

    if not _purview_on and not _db_on:
        st.warning("No data source is connected. Connect Microsoft Purview or Databricks Unity in **Integrations & API**.")
        if st.button("Go to Integrations & API", use_container_width=True):
            st.session_state.selected_tab = "Integrations & API"
            st.rerun()
        return

    # ── Source selector when both are connected ───────────────────────────────
    sources_available = []
    if _purview_on:  sources_available.append("Microsoft Purview")
    if _db_on:       sources_available.append("Databricks Unity Catalog")

    if len(sources_available) > 1:
        active_source = st.radio(
            "Select Data Source", sources_available,
            horizontal=True, key="search_active_source",
        )
    else:
        active_source = sources_available[0]

    st.markdown("<br>", unsafe_allow_html=True)

    # ══════════════════════════════════════════════════════════════════════════
    # MICROSOFT PURVIEW SEARCH
    # ══════════════════════════════════════════════════════════════════════════
    if active_source == "Microsoft Purview":
        mcol1, mcol2 = st.columns([1, 1])
        with mcol1:
            st.markdown('<div class="metric-card">', unsafe_allow_html=True)
            st.markdown("##### Search Parameters")
            source_type_options = {"All": "all", "Azure SQL": "azure_sql_table", "Snowflake": "snowflake_table", "Oracle": "oracle_table", "Databricks": "databricks_table", "Fabric": "fabric_lakehouse_table", "Generic Table": "Table"}
            sc1, sc2 = st.columns(2)
            source_options_list = list(source_type_options.keys())

            st_idx = source_options_list.index(st.session_state.perm_cache['search_source_type']) if st.session_state.perm_cache['search_source_type'] in source_options_list else 0
            with sc1: st.selectbox("Source Type", source_options_list, index=st_idx, key="search_source_type_box", on_change=update_cache, args=("search_source_type", "search_source_type_box"))

            coll_options = ["All Collections"] + [c.get('friendlyName') or c.get('name') for c in st.session_state.get('purview_collections', [])]
            cl_idx = coll_options.index(st.session_state.perm_cache['search_collection']) if st.session_state.perm_cache['search_collection'] in coll_options else 0
            with sc2: st.selectbox("Collection", coll_options, index=cl_idx, key="search_collection_box", on_change=update_cache, args=("search_collection", "search_collection_box"))

            st.text_input("Keyword Search", value=st.session_state.perm_cache['search_keyword'], key="search_keyword_box", on_change=update_cache, args=("search_keyword", "search_keyword_box"))

            selected_source_type = st.session_state.perm_cache['search_source_type']
            search_query = st.session_state.perm_cache['search_keyword']

            if st.button("Search Assets", type="primary", key="purview_search_btn"):
                connector = PurviewConnector(
                    st.session_state.connector_creds['purview_account_name'],
                    st.session_state.connector_creds['purview_tenant_id'],
                    st.session_state.connector_creds['purview_client_id'],
                    st.session_state.connector_creds['purview_client_secret'],
                )
                try:
                    url = f"https://{st.session_state.connector_creds['purview_account_name']}.purview.azure.com/datamap/api/search/query"
                    payload = {"keywords": f"{search_query}*", "limit": 100, "filter": {"entityType": source_type_options[selected_source_type]} if selected_source_type != "All" else {}}
                    connector.authenticate()
                    import requests as _req
                    r = _req.post(url, headers=connector._headers(), json=payload, timeout=30)
                    if r.status_code == 200:
                        raw_results = r.json().get('value', [])
                        filtered_results = [res for res in raw_results if res.get('name', '').lower().startswith(search_query.lower())]
                        st.session_state.purview_search_results = filtered_results
                except Exception as e:
                    st.error(str(e))
            st.markdown('</div>', unsafe_allow_html=True)

        if st.session_state.purview_search_results:
            st.markdown("### Search Results")
            results_df = pd.DataFrame(st.session_state.purview_search_results)
            saved_ids = st.session_state.perm_cache.get('selected_table_ids', [])
            results_df['Select'] = results_df['qualifiedName'].apply(lambda x: x in saved_ids)
            edited_df = st.data_editor(
                results_df[['Select', 'name', 'entityType', 'collectionId', 'qualifiedName']],
                key="search_results_editor",
                hide_index=True,
                use_container_width=True,
            )
            current_selected = edited_df[edited_df['Select'] == True]['qualifiedName'].tolist()
            st.session_state.perm_cache['selected_table_ids'] = current_selected
            selected_tables = [item for item in st.session_state.purview_search_results if item.get('qualifiedName') in current_selected]

            if st.button("Fetch Schemas", type="primary", key="purview_fetch_btn"):
                connector = PurviewConnector(
                    st.session_state.connector_creds['purview_account_name'],
                    st.session_state.connector_creds['purview_tenant_id'],
                    st.session_state.connector_creds['purview_client_id'],
                    st.session_state.connector_creds['purview_client_secret'],
                )
                st.session_state.tables_metadata = {}
                for table in selected_tables:
                    col_data = connector.get_table_columns_with_guids(table.get('id'))
                    st.session_state.tables_metadata[table.get('id')] = {
                        "name": table.get('name'),
                        "qualifiedName": table.get('qualifiedName'),
                        "columns": list(col_data.keys()),
                        "column_guids": col_data,
                        "source": "purview",
                    }
                st.success("Schemas fetched successfully.")

    # ══════════════════════════════════════════════════════════════════════════
    # DATABRICKS UNITY CATALOG SEARCH
    # ══════════════════════════════════════════════════════════════════════════
    else:
        _db_cfg = _connectors.get("Databricks Unity", {})
        _db_conn = DatabricksUnityConnector(
            _db_cfg.get("api_endpoint", ""),
            _db_cfg.get("api_token", ""),
        )

        st.markdown("##### Browse Unity Catalog")

        fc1, fc2, fc3, fc4 = st.columns([1, 1, 1, 1])

        # ── Catalog ───────────────────────────────────────────────────────────
        with fc1:
            if "uc_search_cats" not in st.session_state:
                cats, cat_err = _db_conn.list_catalogs()
                st.session_state.uc_search_cats = cats if not cat_err else []
                if cat_err:
                    st.error(f"Catalogs: {cat_err}")
            cat_opts = ["— select catalog —"] + st.session_state.uc_search_cats
            saved_cat = st.session_state.perm_cache.get("uc_srch_cat_val", "— select catalog —")
            cat_idx = cat_opts.index(saved_cat) if saved_cat in cat_opts else 0
            sel_cat = st.selectbox("Catalog", cat_opts, index=cat_idx, key="uc_srch_cat",
                                   on_change=update_cache, args=("uc_srch_cat_val", "uc_srch_cat"))

        # ── Schema ────────────────────────────────────────────────────────────
        with fc2:
            if sel_cat and sel_cat != "— select catalog —":
                sch_cache_key = f"uc_search_schs_{sel_cat}"
                if sch_cache_key not in st.session_state:
                    schs, sch_err = _db_conn.list_schemas(sel_cat)
                    st.session_state[sch_cache_key] = schs if not sch_err else []
                    if sch_err:
                        st.error(f"Schemas: {sch_err}")
                sch_opts = ["— select schema —"] + st.session_state[sch_cache_key]
            else:
                sch_opts = ["— select schema —"]
            saved_sch = st.session_state.perm_cache.get("uc_srch_sch_val", "— select schema —")
            sch_idx = sch_opts.index(saved_sch) if saved_sch in sch_opts else 0
            sel_sch = st.selectbox("Schema", sch_opts, index=sch_idx, key="uc_srch_sch",
                                   on_change=update_cache, args=("uc_srch_sch_val", "uc_srch_sch"),
                                   disabled=(not sel_cat or sel_cat == "— select catalog —"))

        # ── Keyword filter ────────────────────────────────────────────────────
        with fc3:
            saved_kw = st.session_state.perm_cache.get("uc_srch_kw_val", "")
            uc_keyword = st.text_input("Table Keyword Filter", value=saved_kw, key="uc_srch_kw",
                                       on_change=update_cache, args=("uc_srch_kw_val", "uc_srch_kw"),
                                       placeholder="e.g. customer")

        # ── Search button ─────────────────────────────────────────────────────
        with fc4:
            st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
            do_search = st.button("Browse Tables", type="primary", key="uc_srch_btn",
                                  disabled=(not sel_sch or sel_sch == "— select schema —"))

        if do_search and sel_cat and sel_sch and sel_sch != "— select schema —":
            with st.spinner("Loading tables…"):
                tables, tbl_err = _db_conn.search_tables(sel_cat, sel_sch, uc_keyword)
            if tbl_err:
                st.error(f"Could not list tables: {tbl_err}")
            else:
                st.session_state.uc_search_results = tables

        # ── Results table ─────────────────────────────────────────────────────
        if st.session_state.get("uc_search_results"):
            st.markdown("### Search Results")
            res = st.session_state.uc_search_results
            res_df = pd.DataFrame(res)
            saved_uc = st.session_state.perm_cache.get("uc_selected_tables", [])
            res_df["Select"] = res_df["full_name"].apply(lambda x: x in saved_uc)

            edited_uc = st.data_editor(
                res_df[["Select", "name", "catalog_name", "schema_name", "table_type", "full_name"]],
                key="uc_results_editor",
                hide_index=True,
                use_container_width=True,
                column_config={
                    "Select":       st.column_config.CheckboxColumn("Select"),
                    "name":         st.column_config.TextColumn("Table Name"),
                    "catalog_name": st.column_config.TextColumn("Catalog"),
                    "schema_name":  st.column_config.TextColumn("Schema"),
                    "table_type":   st.column_config.TextColumn("Type"),
                    "full_name":    st.column_config.TextColumn("Full Name"),
                },
            )
            uc_selected = edited_uc[edited_uc["Select"] == True]["full_name"].tolist()
            st.session_state.perm_cache["uc_selected_tables"] = uc_selected

            if st.button("Fetch Schemas", type="primary", key="uc_fetch_btn", disabled=not uc_selected):
                st.session_state.tables_metadata = {}
                with st.spinner("Fetching column schemas from Unity Catalog…"):
                    for row in res:
                        if row["full_name"] not in uc_selected:
                            continue
                        cols, col_err = _db_conn.get_table_columns(
                            row["catalog_name"], row["schema_name"], row["name"]
                        )
                        if col_err:
                            st.warning(f"{row['name']}: {col_err}")
                            continue
                        # Use full_name as the unique ID (mirrors Purview's entity GUID usage)
                        st.session_state.tables_metadata[row["full_name"]] = {
                            "name": row["name"],
                            "qualifiedName": row["full_name"],
                            "columns": cols,
                            "column_guids": {c: c for c in cols},  # identity map — no Purview GUIDs
                            "source": "databricks",
                            "catalog": row["catalog_name"],
                            "schema": row["schema_name"],
                        }
                if st.session_state.tables_metadata:
                    st.success(f"Schemas fetched for {len(st.session_state.tables_metadata)} table(s).")

    # ══════════════════════════════════════════════════════════════════════════
    # DETECTED SCHEMAS  (shared by both sources)
    # ══════════════════════════════════════════════════════════════════════════
    if st.session_state.get('tables_metadata'):
        st.markdown("---")
        st.markdown("### Detected Schemas")
        for tid, meta in st.session_state.tables_metadata.items():
            src_badge = "Databricks" if meta.get("source") == "databricks" else "Purview"
            with st.expander(f"{src_badge}  {meta['name']}  —  {len(meta['columns'])} columns", expanded=True):
                for cname in meta['columns']:
                    st.markdown(f"`{cname}`")

        st.markdown("<br>", unsafe_allow_html=True)
        selected_guids = list(st.session_state.tables_metadata.keys())
        has_history = PersistenceManager.has_stored_data(selected_guids)

        c1, c2 = st.columns(2)
        with c1:
            if st.button("Generate AI Suggestions", use_container_width=True, type="secondary" if has_history else "primary"):
                st.session_state.selected_tab = "Glossary AI"
                st.rerun()
        with c2:
            if st.button("Master Store", use_container_width=True, type="primary" if has_history else "secondary", disabled=not has_history):
                st.session_state.selected_tab = "Glossary Hub"
                st.rerun()

        if has_history:
            st.info("Note: These assets already have approved records in the Master Store.")

def render_glossary_tab():
    render_dashboard_header("Glossary AI")
    st.markdown('<div class="workbench-header"><div class="accent-line"></div><h1 class="workbench-title">Glossary AI</h1><p class="workbench-desc">AI-powered generation of formal Business terms and definitions</p></div>', unsafe_allow_html=True)
    
    if not st.session_state.get('tables_metadata'):
        st.warning("Please search for assets in 'Asset Search' first.")
        return

    # Migrate existing dataframe columns if needed
    if st.session_state.get('glossary_df') is not None:
        if "Glossary Term" in st.session_state.glossary_df.columns:
            st.session_state.glossary_df = st.session_state.glossary_df.rename(columns={
                "Glossary Term": "Business Term",
                "Definition / Description": "Description",
                "Original Name": "Physical Term"
            })

    col_ctx, col_opt = st.columns([2, 1])
    with col_ctx:
        st.markdown('<div class="metric-card">', unsafe_allow_html=True)
        # Use a persistent key 'biz_ctx_input'
        st.text_area("Business Context / Requirements (AI Training)", key="biz_ctx", height=100)
        st.markdown('</div>', unsafe_allow_html=True)
    with col_opt:
        st.markdown('<div class="metric-card">', unsafe_allow_html=True)
        ind_list = ["General", "Finance", "Healthcare", "Retail", "Energy"]
        ind_idx = ind_list.index(st.session_state.perm_cache['glossary_industry']) if st.session_state.perm_cache['glossary_industry'] in ind_list else 0
        st.selectbox("Industry", ind_list, index=ind_idx, key="glossary_industry_box", on_change=update_cache, args=("glossary_industry", "glossary_industry_box"))
        
        opt_list = ["Business Term", "Business Definition", "Classifications"]
        # Filter default to only valid options
        safe_defaults = [o for o in st.session_state.perm_cache['glossary_options'] if o in opt_list]
        st.multiselect("Information to Generate", opt_list, default=safe_defaults, key="glossary_options_box", on_change=update_cache, args=("glossary_options", "glossary_options_box"))
        st.markdown('</div>', unsafe_allow_html=True)
        
        # Sync to internal vars for generation from anchor cache
        st.session_state.industry = st.session_state.perm_cache['glossary_industry']
        st.session_state.ai_options = st.session_state.perm_cache['glossary_options']
    
    selected_asset_names = [m['name'] for m in st.session_state.tables_metadata.values()]
    st.markdown(f"**Currently Processing Assets: {', '.join(selected_asset_names)}**")

    # New AI Suggestion button in this tab
    if st.button("AI Suggestion", type="primary"):
            # Generate all recommendations via Gemini
            all_s = []
            industry = st.session_state.get('industry', 'General')
            options = st.session_state.get('ai_options', ["Business Term", "Business Definition"])
            
            for tid, meta in st.session_state.tables_metadata.items():
                suggestions = generate_glossary_suggestions(meta['name'], meta['columns'], industry=industry, business_context=st.session_state.get('biz_ctx', ""), selected_options=options)
                for s in suggestions:
                    s['table_guid'] = tid
                    s['table_name'] = meta['name']
                    # Use raw column name, but provide the table name if it's a table
                    orig_col = s.get('related_column', '')
                    if s.get('type') == 'Table':
                        s['display_column'] = meta['name']
                    else:
                        s['display_column'] = orig_col  # plain schema column name
                    
                    if s.get('type') == 'Column':
                        s['entity_guid'] = meta['column_guids'].get(orig_col)
                    else:
                        s['entity_guid'] = tid
                all_s.extend(suggestions)
            
            # Apply Automated Governance Rules (Deterministic Regex/Keyword matching)
            all_s = GovernanceEngine.process_suggestions(all_s)
            
            st.session_state.glossary_suggestions = all_s
            df = pd.DataFrame(all_s)
            if not df.empty:
                # New Learning Loop Columns
                if 'Status' not in df.columns: df['Status'] = 'Pending'
                
                st.session_state.glossary_df = df.rename(columns={
                    "type": "Type", 
                    "display_column": "Physical Term", 
                    "name": "Business Term", 
                    "description": "Description", 
                    "classification": "Classification", 
                    "tags": "Governance Tags",
                    "confidence_score": "Confidence (%)"
                })
                
                # Initialize Select column
                st.session_state.glossary_df['Select'] = False
                
                # Reorder according to request: Select first, Confidence last, others in between.
                # Explicitly exclude the internal GUID columns as requested in the image.
                desired_cols = ['Select', 'Status', 'Type', 'Physical Term', 'Business Term', 'Description', 'Classification', 'Governance Tags', 'Confidence (%)']
                actual_cols = [c for c in desired_cols if c in st.session_state.glossary_df.columns]
                
                # Internal columns to keep but hide (for processing)
                internal_cols = ['table_guid', 'entity_guid', 'table_name', 'related_column'] 
                
                st.session_state.glossary_df = st.session_state.glossary_df[actual_cols + [c for c in internal_cols if c in st.session_state.glossary_df.columns]]
                
                st.session_state.raw_suggestions = all_s
            st.rerun()

    if st.session_state.get('glossary_df') is not None:
        st.subheader("Recommended Business Terms ")

        full_df = st.session_state.glossary_df.copy()
        # Drop Level column if it was added in a previous run
        if 'Level' in full_df.columns:
            full_df = full_df.drop(columns=['Level'])

        _col_config = {
            "Select": st.column_config.CheckboxColumn("Select", help="Tick to approve the term", default=False),
            "Status": st.column_config.SelectboxColumn("Status", help="Approval status", options=["Pending", "Accepted", "Rejected"], required=True, disabled=True),
            "Confidence (%)": st.column_config.ProgressColumn("Confidence (%)", help="AI confidence in this suggestion", format="%d%%", min_value=0, max_value=100),
            "table_guid": None, "entity_guid": None, "table_name": None, "related_column": None,
        }

        visible_cols = ['Select', 'Status', 'Type', 'Physical Term', 'Business Term',
                        'Description', 'Classification', 'Governance Tags', 'Confidence (%)']
        actual_visible = [c for c in visible_cols if c in full_df.columns]

        merged_df = full_df.copy()
        changed = False

        # Group by table_name and render one editor per table
        tables = full_df['table_name'].unique() if 'table_name' in full_df.columns else ['']
        for table in tables:
            if 'table_name' in full_df.columns:
                grp = full_df[full_df['table_name'] == table]
                # Sort Table type to the top within each group
                grp = grp.sort_values(
                    by='Type',
                    key=lambda s: s.str.strip().str.lower().map(lambda v: 0 if v == 'table' else 1),
                    kind='stable'
                )
                tbl_idx = grp.index.tolist()
            else:
                tbl_idx = full_df.index.tolist()

            label = table if table else "Unknown Table"
            st.markdown(
                f"<div style='margin:18px 0 6px 0;padding:7px 14px;"
                f"background:#EFF6FF;border-left:4px solid #3B82F6;"
                f"border-radius:4px;font-weight:700;font-size:14px;'>📋 {label}</div>",
                unsafe_allow_html=True,
            )

            prev_state = {i: bool(full_df.at[i, 'Select']) for i in tbl_idx}
            edited = st.data_editor(
                full_df.loc[tbl_idx],
                key=f"gloss_ed_{label}",
                hide_index=True,
                use_container_width=True,
                column_config=_col_config,
                column_order=actual_visible,
            )
            if not edited.equals(full_df.loc[tbl_idx]):
                for i, row in edited.iterrows():
                    if row['Select']:
                        edited.at[i, 'Status'] = 'Accepted'
                    else:
                        if edited.at[i, 'Status'] == 'Accepted':
                            edited.at[i, 'Status'] = 'Pending'
                        if prev_state.get(i, False) and not row['Select']:
                            term_name = row.get('Business Term') or row.get('Original Name') or ''
                            if term_name:
                                WorkflowManager.remove_from_queue_by_name(term_name)
                merged_df.loc[tbl_idx] = edited
                changed = True

        if changed:
            st.session_state.glossary_df = merged_df
            st.rerun()
        
        # Store Terms Button
        components.html("""
        <script>
            function styleApprovalBtn() {
                try {
                    var doc = window.parent.document;
                    var btns = doc.querySelectorAll('button');
                    btns.forEach(function(btn) {
                        if (btn.innerText.trim() === 'Send to Approval Queue') {
                            btn.style.setProperty('background-color', '#e53935', 'important');
                            btn.style.setProperty('color', 'white', 'important');
                            btn.style.setProperty('border', 'none', 'important');
                        }
                    });
                } catch(e) {}
            }
            styleApprovalBtn();
            setTimeout(styleApprovalBtn, 150);
            setTimeout(styleApprovalBtn, 500);
        </script>
        """, height=0)
        if st.button("Send to Approval Queue", use_container_width=False, help="Route selected AI terms through the Review & Approval workflow before publishing to the Glossary Hub"):
            selected_df = st.session_state.glossary_df[st.session_state.glossary_df['Select'] == True]
            if selected_df.empty:
                st.warning("Please select at least one term to send to the Approval Queue.")
            else:
                # Clear previous batch of the same source before adding the new one
                _any_uc_rows = any(
                    st.session_state.tables_metadata.get(str(row.get("table_guid", "")), {}).get("source") == "databricks"
                    for _, row in selected_df.iterrows()
                )
                _clear_src = "Databricks Unity Catalog" if _any_uc_rows else "AI Suggester"
                WorkflowManager.clear_ai_pending_from_queue(source=_clear_src)
                WorkflowManager.clear_ai_suggested_terms(source=_clear_src)
                queued_count = 0
                for _, row in selected_df.iterrows():
                    term_name     = row.get("Business Term") or row.get("Original Name") or ""
                    definition    = row.get("Description") or row.get("Definition / Description") or ""
                    score         = int(row.get("Confidence (%)", 80) or 80)
                    term_type     = str(row.get("Type", "Column") or "Column")
                    physical_term = str(row.get("Physical Term") or row.get("related_column") or "")
                    if term_name:
                        # Detect whether the term came from a Databricks Unity Catalog table
                        _tbl_meta = st.session_state.tables_metadata.get(str(row.get("table_guid", "")), {})
                        _src = "Databricks Unity Catalog" if _tbl_meta.get("source") == "databricks" else "AI Suggester"
                        WorkflowManager.create_suggested_term(
                            term_name        = term_name,
                            definition       = definition,
                            source           = _src,
                            confidence_score = score,
                            table_name       = str(row.get("table_name", "") or ""),
                            term_type        = term_type,
                            physical_term    = physical_term,
                        )
                        queued_count += 1
                if queued_count:
                    st.session_state.glossary_df = None
                    st.session_state.glossary_suggestions = []
                    st.session_state.selected_tab = "Review & Approval"
                    st.rerun()
                else:
                    st.warning("No valid terms found in selection.")

def render_master_glossary_tab():
    render_dashboard_header("Glossary Hub")
    st.markdown('<div class="workbench-header"><div class="accent-line"></div><h1 class="workbench-title">Glossary Hub</h1><p class="workbench-desc">Enterprise Source of Truth — All approved, versioned glossary records with full audit history.</p></div>', unsafe_allow_html=True)
    
    summaries = PersistenceManager.get_all_stored_summaries()
    
    if not summaries:
        st.info("No approved glossary records found. Generate suggestions in 'Glossary AI' to get started.")
        return
        
    df_sum = pd.DataFrame(summaries)
    all_asset_names = df_sum["Asset Name"].tolist()

    # ── Collect all metadata for filters (single batch read) ────────────────────
    _all_guids = df_sum["Asset GUID"].tolist()
    _all_records = PersistenceManager.get_all_versions(_all_guids) or []

    # ── Unity Catalog scope: when Databricks Unity is connected, show only UC-approved records ──
    _hub_uc_connected = st.session_state.get('integration_connectors', {}).get('Databricks Unity', {}).get('status') == 'Connected'
    if _hub_uc_connected:
        _all_records = [r for r in _all_records if r.get("Source") == "Databricks Unity Catalog"]
        _uc_guids = {r.get("table_guid") for r in _all_records if r.get("table_guid")}
        summaries = [s for s in summaries if s["Asset GUID"] in _uc_guids]
        if not summaries:
            st.info("No Unity Catalog approved records found. Generate AI suggestions from Databricks assets and approve them to see them here.")
            return
        df_sum = pd.DataFrame(summaries)
        all_asset_names = df_sum["Asset Name"].tolist()

    all_types = sorted(set(r.get("Type", "Column") for r in _all_records))
    all_classifications = sorted(set(
        r.get("Classification", "") for r in _all_records if r.get("Classification", "")
    ))

    # ── TWO COLUMN LAYOUT: left = filters, right = data ───────────────────────
    col_filters, col_main = st.columns([1, 4], gap="large")

    # ═══════════════════════════════════════════════════════════════════════════
    # LEFT PANEL — Purview-style Filter Accordion
    # ═══════════════════════════════════════════════════════════════════════════
    with col_filters:
        st.markdown("""
        <div class="purview-filter-panel">
            <div class="filter-panel-title">Filters</div>
        </div>
        """, unsafe_allow_html=True)

        collection_filter = "All"

        # Detect Unity Catalog connection
        _uc_cfg = st.session_state.get('integration_connectors', {}).get('Databricks Unity', {})
        _uc_connected = _uc_cfg.get('status') == 'Connected'

        if _uc_connected:
            # ── Load catalogs once into session state ──────────────────────────
            _uc_conn = DatabricksUnityConnector(_uc_cfg.get('api_endpoint', ''), _uc_cfg.get('api_token', ''))
            if 'hub_uc_catalogs' not in st.session_state:
                _catalogs, _cat_err = _uc_conn.list_catalogs()
                st.session_state.hub_uc_catalogs = _catalogs if not _cat_err else []
            _catalogs = st.session_state.hub_uc_catalogs

            # ── Catalog filter (Unity Catalog) ─────────────────────────────────
            with st.expander("Catalog", expanded=False):
                catalog_filter_options = ["All"] + _catalogs
                hub_catalog_filter = st.radio(
                    "Select catalog", catalog_filter_options,
                    key="hub_catalog_filter", label_visibility="collapsed"
                )

            # ── Load schemas once per selected catalog into session state ───────
            _sch_cache_key = f"hub_uc_schemas_{hub_catalog_filter}"
            if _sch_cache_key not in st.session_state:
                if hub_catalog_filter != "All":
                    _schemas, _ = _uc_conn.list_schemas(hub_catalog_filter)
                else:
                    _schemas = []
                    for _cat in _catalogs:
                        _s, _ = _uc_conn.list_schemas(_cat)
                        _schemas.extend(_s)
                st.session_state[_sch_cache_key] = _schemas
            _schemas = st.session_state[_sch_cache_key]

            # ── Schema filter (Unity Catalog) ──────────────────────────────────
            with st.expander("Schema", expanded=False):
                schema_filter_options = ["All"] + _schemas
                hub_schema_filter = st.radio(
                    "Select schema", schema_filter_options,
                    key="hub_schema_filter", label_visibility="collapsed"
                )

            data_source_filter = "All"
            asset_filter = "All"
        else:
            hub_catalog_filter = "All"
            hub_schema_filter = "All"

            # ── Data Source Type filter ────────────────────────────────────────
            with st.expander("Data Source Type", expanded=False):
                data_source_options = ["All", "Azure SQL", "Snowflake", "Databricks", "Oracle", "Fabric"]
                data_source_filter = st.radio(
                    "Select source", data_source_options,
                    key="hub_datasource_filter", label_visibility="collapsed"
                )

            # ── Collection filter ──────────────────────────────────────────────
            with st.expander("Collection", expanded=False):
                coll_names = [c.get('friendlyName') or c.get('name') for c in st.session_state.get('purview_collections', [])]
                if not coll_names:
                    coll_names = ["Default"]
                show_all_colls = st.checkbox("**See more**", key="hub_coll_see_more", value=False)
                if show_all_colls:
                    coll_filter_options = ["All"] + coll_names
                else:
                    coll_filter_options = ["All"] + coll_names[:3]
                asset_filter = st.radio(
                    "Select collection", coll_filter_options,
                    key="hub_asset_filter", label_visibility="collapsed"
                )
                if show_all_colls:
                    st.caption("Uncheck 'See more' to hide")

        # ── Classification filter ──────────────────────────────────────────────
        with st.expander("Classification", expanded=False):
            classification_options = ["All"] + all_classifications if all_classifications else ["All", "PII", "Confidential", "Public"]
            classification_filter = st.radio(
                "Select classification", classification_options,
                key="hub_class_filter", label_visibility="collapsed"
            )

        # ── Records Status filter ──────────────────────────────────────────────
        with st.expander("Record Status", expanded=False):
            record_status = st.radio(
                "Select status", ["All", "Active", "Non-Active"],
                key="hub_status_filter", label_visibility="collapsed"
            )

        # ── Table / Asset filter ──────────────────────────────────────────────
        with st.expander("Table Filter", expanded=False):
            if asset_filter != "All":
                asset_to_view = asset_filter
                st.markdown(
                    f"<div class='hub-asset-badge'>📋 Viewing: <strong>{asset_to_view}</strong></div>",
                    unsafe_allow_html=True
                )
            else:
                asset_to_view = st.selectbox("Select Table/Asset to View", all_asset_names, key="hub_asset_select", label_visibility="collapsed")

    # ═══════════════════════════════════════════════════════════════════════════
    # RIGHT PANEL — Main Content Area
    # ═══════════════════════════════════════════════════════════════════════════
    with col_main:
        # ── Toolbar row ──────────────────────────────────────────────────────
        tb_left, tb_right = st.columns([3, 1])
        with tb_left:
            pass # The header is shown below
        with tb_right:
            edit_mode = st.toggle("✏️ Edit Mode", key="hub_edit_mode", value=False)
            if edit_mode:
                st.caption("Edits update the active record.")

        st.markdown("<hr style='margin:10px 0 18px 0; border-color:#E5E7EB;'>", unsafe_allow_html=True)

        # ── Data Display ──────────────────────────────────────────────────────
        if asset_to_view:
            selected_guid = df_sum[df_sum["Asset Name"] == asset_to_view]["Asset GUID"].iloc[0]
            full_history = PersistenceManager.get_all_versions([selected_guid])
            
            if full_history:
                df_hist = pd.DataFrame(full_history)

                # When UC is connected, restrict to UC-sourced records only
                if _hub_uc_connected and "Source" in df_hist.columns:
                    df_hist = df_hist[df_hist["Source"] == "Databricks Unity Catalog"]
                if df_hist.empty:
                    st.info("No Unity Catalog approved records for this asset.")
                    st.stop()
                
                # Apply filters
                if record_status == "Active":
                    df_hist = df_hist[df_hist["Active"] == 1]
                elif record_status == "Non-Active":
                    df_hist = df_hist[df_hist["Active"] == 0]
                
                if collection_filter != "All" and "Type" in df_hist.columns:
                    df_hist = df_hist[df_hist["Type"] == collection_filter]

                if classification_filter != "All" and "Classification" in df_hist.columns:
                    df_hist = df_hist[df_hist["Classification"] == classification_filter]
                
                # Active records first
                df_hist = df_hist.sort_values("Active", ascending=False).reset_index(drop=True)

                HIDDEN_COLS = {
                    "Select": None, "Status": None, "version": None,
                    "is_active": None, "timestamp": None, "data": None,
                    "table_guid": None, "entity_guid": None,
                    "table_name": None, "related_column": None, "Confidence (%)": None
                }
                
                # Reorder columns: Active, Version, then required columns in order, Stored At last
                priority_cols = ["Active", "Version"]
                desired_order = ["Type", "Physical Term", "Business Term", "Description", "Source", "Stored At"]

                # Normalise column names first
                df_hist = df_hist.rename(columns={
                    "Original Name":           "Physical Term",
                    "Definition / Description": "Description",
                    "Glossary Term":            "Business Term",
                })

                # Keep only columns that actually exist in the df
                middle_cols = [c for c in desired_order if c in df_hist.columns and c not in priority_cols]
                extra_cols  = [c for c in df_hist.columns
                               if c not in priority_cols and c not in middle_cols and c not in HIDDEN_COLS]
                df_hist = df_hist[priority_cols + middle_cols + extra_cols]

                active_count = (df_hist["Active"] == 1).sum()
                total_count  = len(df_hist)

                # Remove trailing empty / all-NaN rows
                df_hist = df_hist.dropna(how="all").reset_index(drop=True)

                # Status badges
                badge_row = st.columns([2, 2, 4])
                with badge_row[0]:
                    st.markdown(f"<span class='hub-badge hub-badge-active'>✓ {active_count} Active</span>", unsafe_allow_html=True)
                with badge_row[1]:
                    st.markdown(f"<span class='hub-badge hub-badge-total'>⏱ {total_count} Total</span>", unsafe_allow_html=True)

                st.markdown(f"#### Version History — {asset_to_view}")
                st.markdown("<br>", unsafe_allow_html=True)

                col_config = {
                    "Active":        st.column_config.NumberColumn("Active",   help="1 = Current, 0 = Historical", width="small"),
                    "Version":       st.column_config.NumberColumn("Version",  width="small"),
                    "Type":          st.column_config.TextColumn("Type",       width="small"),
                    "Physical Term": st.column_config.TextColumn("Physical Term"),
                    "Business Term": st.column_config.TextColumn("Business Term"),
                    "Description":   st.column_config.TextColumn("Description"),
                    "Source":        st.column_config.TextColumn("Source",     width="small"),
                    "Stored At":     st.column_config.TextColumn("Last Updated"),
                    **HIDDEN_COLS
                }

                st.data_editor(
                    df_hist,
                    key=f"hub_view_{selected_guid}",
                    hide_index=True,
                    use_container_width=True,
                    disabled=(not edit_mode),
                    num_rows="fixed",
                    column_config=col_config
                )

                st.markdown("<br>", unsafe_allow_html=True)

                # ── Register / Push — only show button for connected integration ──
                can_register = st.session_state.user_role == "Administrator"
                active_df = df_hist[df_hist["Active"] == 1]

                _connectors  = st.session_state.integration_connectors
                _purview_cfg = _connectors.get("Microsoft Purview", {})
                _db_cfg      = _connectors.get("Databricks Unity", {})
                _purview_on  = _purview_cfg.get("status") == "Connected"
                _db_on       = _db_cfg.get("status") == "Connected"

                st.markdown("""
                <style>
                div[data-testid="stButton"] > button {
                    background-color: #E53935 !important;
                    color: #ffffff !important;
                    border: none !important;
                }
                div[data-testid="stButton"] > button:hover {
                    background-color: #C62828 !important;
                    color: #ffffff !important;
                }
                </style>
                """, unsafe_allow_html=True)

                # ── Microsoft Purview button (only if connected) ──────────────────
                if _purview_on:
                    reg_label = f"Register {len(active_df)} Active Term(s) to Purview"
                    if st.button(reg_label, type="primary", use_container_width=True, disabled=not can_register):
                        creds = st.session_state.get("connector_creds", {})
                        account_name  = creds.get("purview_account_name", "")
                        tenant_id     = creds.get("purview_tenant_id", "")
                        client_id     = creds.get("purview_client_id", "")
                        client_secret = creds.get("purview_client_secret", "")

                        if not all([account_name, tenant_id, client_id, client_secret]):
                            st.error("Purview credentials are missing. Reconnect in **Integrations & API**.")
                        else:
                            connector = PurviewConnector(account_name, tenant_id, client_id, client_secret)
                            ok, auth_msg = connector.authenticate()
                            if not ok:
                                st.error(f"Authentication failed: {auth_msg}")
                            else:
                                try:
                                    glossaries = connector.get_glossaries()
                                    if isinstance(glossaries, list) and glossaries:
                                        glossary_guid = glossaries[0].get("guid", "")
                                    elif isinstance(glossaries, dict):
                                        glossary_guid = glossaries.get("guid", "")
                                    else:
                                        glossary_guid = ""
                                except Exception as ge:
                                    st.error(f"Could not fetch glossaries: {ge}")
                                    glossary_guid = ""

                                if not glossary_guid:
                                    st.error("No glossary found in Purview. Please create a glossary first.")
                                else:
                                    col_guid_lookup = {}
                                    for _tid, _meta in st.session_state.get("tables_metadata", {}).items():
                                        for _cname, _cguid in (_meta.get("column_guids") or {}).items():
                                            col_guid_lookup[_cname.upper()] = _cguid

                                    _table_name = (active_df.iloc[0].get("table_name") or active_df.iloc[0].get("Physical Term", "")).upper() if not active_df.empty else ""
                                    _real_table_guid = None
                                    for _tid, _meta in st.session_state.get("tables_metadata", {}).items():
                                        if (_meta.get("name") or "").upper() == _table_name or (_meta.get("name") or "").upper() in asset_to_view.upper():
                                            _real_table_guid = _tid
                                            break

                                    if _real_table_guid:
                                        try:
                                            with st.spinner("Fetching column schema from Purview…"):
                                                live_cols = connector.get_table_columns_with_guids(_real_table_guid)
                                            for _cname, _cguid in live_cols.items():
                                                col_guid_lookup[_cname.upper()] = _cguid
                                        except Exception:
                                            pass
                                    else:
                                        try:
                                            with st.spinner("Searching Purview for table schema…"):
                                                _found_table_guid = connector.search_entity_by_name(asset_to_view)
                                            if _found_table_guid:
                                                live_cols = connector.get_table_columns_with_guids(_found_table_guid)
                                                for _cname, _cguid in live_cols.items():
                                                    col_guid_lookup[_cname.upper()] = _cguid
                                        except Exception:
                                            pass

                                    registered, errors = 0, []
                                    with st.spinner("Registering terms to Purview…"):
                                        for _, row in active_df.iterrows():
                                            term_name     = str(row.get("Business Term") or row.get("Glossary Term", "")).strip()
                                            definition    = str(row.get("Description") or row.get("Definition / Description", "")).strip()
                                            physical_term = str(row.get("Physical Term") or row.get("Original Name", "")).strip()
                                            if not term_name:
                                                continue
                                            try:
                                                purview_entity_guid = col_guid_lookup.get(physical_term.upper())
                                                if not purview_entity_guid and physical_term:
                                                    purview_entity_guid = connector.search_entity_by_name(physical_term)
                                                    if purview_entity_guid:
                                                        col_guid_lookup[physical_term.upper()] = purview_entity_guid

                                                existing_term_guid = connector.get_term_by_name(term_name)
                                                if existing_term_guid:
                                                    connector.update_glossary_term(existing_term_guid, term_name, definition, glossary_guid)
                                                    final_term_guid = existing_term_guid
                                                else:
                                                    result = connector.create_glossary_term(term_name, definition, glossary_guid)
                                                    final_term_guid = result.get("guid") if isinstance(result, dict) else None

                                                if final_term_guid and purview_entity_guid:
                                                    connector.assign_term_to_entity(final_term_guid, purview_entity_guid)
                                                    registered += 1
                                                elif final_term_guid:
                                                    errors.append(f"{term_name}: Column '{physical_term}' not found in Purview — term saved but not linked")
                                                    registered += 1
                                                else:
                                                    errors.append(f"{term_name}: Could not obtain term GUID after create/update")
                                            except Exception as ex:
                                                errors.append(f"{term_name}: {str(ex)}")
                                    if errors:
                                        st.warning(f"Registered {registered} term(s) with {len(errors)} error(s):\n" + "\n".join(f"• {e}" for e in errors))
                                    else:
                                        st.success(f"✅ {registered} active term(s) from **{asset_to_view}** registered and assigned to Purview.")

                # ── Databricks Unity Catalog button (only if connected) ────────────
                if _db_on:
                    _db_browse   = DatabricksUnityConnector(_db_cfg.get("api_endpoint", ""), _db_cfg.get("api_token", ""))
                    _meta_entry  = st.session_state.get("tables_metadata", {}).get(selected_guid, {})
                    uc_full_name = _meta_entry.get("qualifiedName", "")

                    _whs, _wh_err = _db_browse.list_sql_warehouses()
                    _wh_id = ""
                    if not _wh_err and _whs:
                        _running = [w for w in _whs if w["state"] == "RUNNING"]
                        _wh_id = (_running or _whs)[0]["id"]

                    uc_label = f"Push {len(active_df)} Active Term(s) to Unity Catalog"
                    if st.button(uc_label, type="primary", use_container_width=True, disabled=(not can_register or not uc_full_name)):
                        if not uc_full_name:
                            st.warning("No table selected. Please select a table in **Asset Search** first.")
                        else:
                            _tag_pairs = []
                            for _, _row in active_df.iterrows():
                                _phys = str(_row.get("Physical Term") or _row.get("Original Name", "")).strip()
                                _biz  = str(_row.get("Business Term") or _row.get("Glossary Term", "")).strip()
                                if _phys and _biz:
                                    _tag_pairs.append({"tag_name": _phys, "tag_value": _biz})
                            if not _tag_pairs:
                                st.warning("No column/business-term pairs found in the active records.")
                            else:
                                with st.spinner(f"Pushing {len(_tag_pairs)} tag(s) to Unity Catalog…"):
                                    _applied, _skipped, _errs = _db_browse.push_tags_to_table(uc_full_name, _tag_pairs, warehouse_id=_wh_id)
                                if _errs:
                                    st.error("Push failed:\n" + "\n".join(f"• {e}" for e in _errs))
                                else:
                                    if _applied:
                                        st.success(f"✅ {_applied} tag(s) pushed to `{uc_full_name}` in Unity Catalog.")
                                    if _skipped:
                                        st.info(f"⏭ {len(_skipped)} tag(s) already exist and were skipped: {', '.join(f'`{s}`' for s in _skipped)}")
                                    if not _applied and not _skipped:
                                        st.warning("No tags were pushed.")

def render_dashboard_tab():

    # ─── Data ────────────────────────────────────────────────────────────────
    metrics     = PersistenceManager.get_dashboard_metrics()
    summaries   = PersistenceManager.get_all_stored_summaries()
    suggestions = st.session_state.get('glossary_suggestions', [])
    audit_log   = WorkflowManager.load_audit_log()
    tables_meta = st.session_state.get('tables_metadata', {})

    # ── Unity Catalog scope: when connected, restrict all metrics to UC-approved records ──
    if st.session_state.get('integration_connectors', {}).get('Databricks Unity', {}).get('status') == 'Connected':
        # Filter inline — no kwarg dependency on persistence_manager
        _all_recs_dash = PersistenceManager.get_all_versions(
            [s["Asset GUID"] for s in summaries]
        ) or []
        _uc_recs_dash  = [r for r in _all_recs_dash if r.get("Source") == "Databricks Unity Catalog"]
        _uc_guids_dash = {r.get("table_guid") for r in _uc_recs_dash if r.get("table_guid")}
        summaries  = [s for s in summaries if s["Asset GUID"] in _uc_guids_dash]
        # Recompute metrics from UC records only
        _active_ids, _active_ct = set(), 0
        for _r in _uc_recs_dash:
            if _r.get("Active") == 1:
                _tid = _r.get("entity_guid") or _r.get("Physical Term") or _r.get("Original Name")
                if _tid and _tid not in _active_ids:
                    _active_ids.add(_tid); _active_ct += 1
        metrics = {
            "Total Assets":  len(_uc_guids_dash),
            "Active Terms":  _active_ct,
            "Total History": len(_uc_recs_dash),
        }
        audit_log = [e for e in (audit_log or []) if e.get("source") == "Databricks Unity Catalog"]

    maturity_fill = min(100, int((metrics["Active Terms"] / max(metrics["Total Assets"] * 5, 1)) * 100))
    pending_count = len([e for e in (audit_log or []) if e.get("status") not in ("Approved", "Approved (Merged)", "Rejected")])

    # ─── Page header ─────────────────────────────────────────────────────────
    st.markdown(
        '<div style="margin-bottom:20px;">'
        + '<div style="width:32px;height:3px;background:#E24B4A;border-radius:2px;margin-bottom:12px;"></div>'
        + '<div style="font-size:22px;font-weight:500;color:#1A1A18;margin-bottom:4px;">Governance Intelligence Hub</div>'
        + '<div style="font-size:13px;color:#888780;">Real-time enterprise metadata maturity and glossary health monitoring.</div>'
        + '</div>',
        unsafe_allow_html=True,
    )

    # ─── 6 KPI metric cards ───────────────────────────────────────────────────
    rejected_count          = sum(1 for e in (audit_log or []) if e.get("status") == "Rejected")
    conflict_detected_count = sum(1 for e in (audit_log or []) if e.get("conflict_found"))

    mc1, mc2, mc3, mc4, mc5, mc6 = st.columns(6)
    kpi_cfg = [
        (mc1, "TOTAL ASSETS",       str(metrics["Total Assets"]),    metrics["Total Assets"],    100,  "#378ADD", "assets indexed",                   None),
        (mc2, "ACTIVE TERMS",       str(metrics["Active Terms"]),    metrics["Active Terms"],    200,  "#1D9E75", "in master glossary",                True),
        (mc3, "TOTAL REVISIONS",    str(metrics["Total History"]),   metrics["Total History"],   200,  "#EF9F27", f"{pending_count} pending review",   False if pending_count else None),
        (mc4, "MATURITY SCORE",     f"{maturity_fill}%",             maturity_fill,              100,  "#E24B4A", "Target: 85%",                       None),
        (mc5, "REJECTED",           str(rejected_count),             rejected_count,             50,   "#888780", "from audit log",                    False if rejected_count else None),
        (mc6, "CONFLICT DETECTED",  str(conflict_detected_count),    conflict_detected_count,    50,   "#E24B4A", "merges + re-submissions",           False if conflict_detected_count else None),
    ]
    for col, label, value, raw, mx, color, trend, trend_up in kpi_cfg:
        fp = min(100, int((raw / max(mx, 1)) * 100))
        tc = "#1D9E75" if trend_up is True else "#E24B4A" if trend_up is False else "#888780"
        ta = "↑ " if trend_up is True else "↓ " if trend_up is False else ""
        col.markdown(
            f'<div style="background:#F4F3EF;border-radius:8px;padding:14px;">'
            + f'<div style="font-size:10px;color:#888780;letter-spacing:0.06em;margin-bottom:6px;">{label}</div>'
            + f'<div style="font-size:22px;font-weight:500;color:#1A1A18;margin-bottom:8px;">{value}</div>'
            + f'<div style="height:3px;border-radius:2px;background:#E0DED8;overflow:hidden;margin-bottom:5px;">'
            + f'<div style="width:{fp}%;height:100%;border-radius:2px;background:{color};"></div></div>'
            + f'<div style="font-size:11px;color:{tc};">{ta}{trend}</div>'
            + '</div>',
            unsafe_allow_html=True,
        )

    st.markdown("<div style='height:14px;'></div>", unsafe_allow_html=True)

    # ─── Recent Activity + Right column ──────────────────────────────────────
    col_act, col_right = st.columns([2, 1])

    _badge_bg  = {"Approved": "#EAF3DE", "Approved (Merged)": "#EAF3DE", "Rejected": "#FCEBEB", "Pending": "#FAEEDA", "Conflict": "#FCEBEB"}
    _badge_fg  = {"Approved": "#3B6D11", "Approved (Merged)": "#3B6D11", "Rejected": "#A32D2D", "Pending": "#854F0B", "Conflict": "#A32D2D"}
    _icon_bg   = {"Approved": "#EAF3DE", "Approved (Merged)": "#EAF3DE", "Rejected": "#FCEBEB", "Pending": "#E6F1FB", "Conflict": "#FCEBEB"}
    _icon_fg   = {"Approved": "#3B6D11", "Approved (Merged)": "#3B6D11", "Rejected": "#A32D2D", "Pending": "#378ADD", "Conflict": "#A32D2D"}
    _icon_sym  = {"Approved": "✓", "Approved (Merged)": "⟳", "Rejected": "✕", "Pending": "·", "Conflict": "!"}

    with col_act:
        act_html = (
            '<div style="background:#fff;border:0.5px solid #E0DED8;border-radius:12px;padding:14px;">'
            + '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">'
            + '<span style="font-size:13px;font-weight:500;color:#1A1A18;">Recent Activity</span>'
            + '<span style="font-size:11px;color:#888780;">Audit log</span>'
            + '</div>'
        )
        recent_entries = sorted(audit_log or [], key=lambda e: e.get("decision_date", ""), reverse=True)[:6]
        if recent_entries:
            for entry in recent_entries:
                sts  = entry.get("status", "Pending")
                term = _html.escape(str(entry.get("term_name", "—")))
                phys = _html.escape(str(entry.get("physical_term", "")))
                dr   = entry.get("decision_date", "")
                try:
                    dfmt = datetime.fromisoformat(dr).strftime("%d %b, %H:%M") if dr else "—"
                except Exception:
                    dfmt = dr[:10] if dr else "—"
                ib  = _icon_bg.get(sts, "#F4F3EF")
                ic  = _icon_fg.get(sts, "#888780")
                sym = _icon_sym.get(sts, "·")
                bb  = _badge_bg.get(sts, "#F4F3EF")
                bf  = _badge_fg.get(sts, "#888780")
                name_label = f"{phys} — {term}" if phys else term
                act_html += (
                    '<div style="display:flex;align-items:flex-start;gap:10px;padding:9px 0;border-bottom:0.5px solid #EBEBEB;">'
                    + f'<div style="width:28px;height:28px;border-radius:8px;background:{ib};display:flex;align-items:center;justify-content:center;flex-shrink:0;font-size:13px;color:{ic};font-weight:600;">{sym}</div>'
                    + '<div style="flex:1;min-width:0;">'
                    + f'<div style="font-size:12px;font-weight:500;color:#1A1A18;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">{name_label}</div>'
                    + f'<div style="font-size:11px;color:#888780;">{sts} · {dfmt}</div>'
                    + '</div>'
                    + f'<span style="font-size:10px;padding:2px 7px;border-radius:4px;flex-shrink:0;white-space:nowrap;background:{bb};color:{bf};">{sts}</span>'
                    + '</div>'
                )
        else:
            act_html += '<div style="font-size:12px;color:#888780;padding:16px 0;">No activity yet — approve or reject terms to see history here.</div>'
        act_html += '</div>'
        st.markdown(act_html, unsafe_allow_html=True)

    with col_right:
        # ── AI Suggestions ────────────────────────────────────────────────────
        sug_colors = ["#378ADD", "#1D9E75", "#EF9F27", "#E24B4A"]
        top_sugs   = (suggestions or [])[:4]
        sug_html   = (
            '<div style="background:#fff;border:0.5px solid #E0DED8;border-radius:12px;padding:14px;margin-bottom:10px;">'
            + '<div style="font-size:13px;font-weight:500;color:#1A1A18;margin-bottom:12px;">AI Suggestions</div>'
        )
        if top_sugs:
            for i, s in enumerate(top_sugs):
                cc       = sug_colors[i % len(sug_colors)]
                sname    = _html.escape(str(s.get('name', s.get('term_name', '—'))))
                conf_raw = s.get('confidence_score', s.get('confidence', 0))
                try:
                    conf_val = float(conf_raw)
                    conf = f"{int(conf_val * 100 if conf_val <= 1 else conf_val)}%"
                except Exception:
                    conf = str(conf_raw)
                is_last = (i == len(top_sugs) - 1)
                sug_html += (
                    f'<div style="display:flex;align-items:center;gap:8px;padding:7px 0;'
                    + f'border-bottom:{"none" if is_last else "0.5px solid #EBEBEB"};font-size:12px;">'
                    + f'<div style="width:8px;height:8px;border-radius:50%;background:{cc};flex-shrink:0;"></div>'
                    + f'<span style="flex:1;color:#1A1A18;">{sname}</span>'
                    + f'<span style="font-size:11px;color:#888780;">{conf}</span>'
                    + '</div>'
                )
        else:
            sug_html += '<div style="font-size:12px;color:#888780;padding:8px 0;">No suggestions yet — run Glossary AI to generate.</div>'
        sug_html += '</div>'
        st.markdown(sug_html, unsafe_allow_html=True)

        # ── Quick Links ───────────────────────────────────────────────────────
        ql_items = [
            ("#E6F1FB", "#378ADD", "🔍", "Search Assets",   "Asset Search"),
            ("#EAF3DE", "#3B6D11", "✦",  "AI Suggester",    "Glossary AI"),
            ("#FAEEDA", "#854F0B", "⊞",  "Master Store",    "Glossary Hub"),
            ("#FCEBEB", "#A32D2D", "☰",  "Review Queue",    "Review & Approval"),
        ]
        ql_html = (
            '<div style="background:#fff;border:0.5px solid #E0DED8;border-radius:12px;padding:14px;">'
            + '<div style="font-size:13px;font-weight:500;color:#1A1A18;margin-bottom:10px;">Quick Links</div>'
            + '<div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;">'
        )
        for ibg, ic, emoji, label, _ in ql_items:
            ql_html += (
                f'<div style="background:#F4F3EF;border:0.5px solid #E0DED8;border-radius:8px;padding:10px 12px;font-size:12px;color:#2C2C2A;display:flex;align-items:center;gap:6px;cursor:default;">'
                + f'<div style="width:22px;height:22px;border-radius:6px;background:{ibg};display:flex;align-items:center;justify-content:center;flex-shrink:0;font-size:11px;color:{ic};">{emoji}</div>'
                + f'{label} ↗</div>'
            )
        ql_html += '</div></div>'
        st.markdown(ql_html, unsafe_allow_html=True)

        st.markdown("<div style='height:6px;'></div>", unsafe_allow_html=True)
        qn1, qn2 = st.columns(2)
        for i, (_, _, _, label, tab) in enumerate(ql_items):
            nc = qn1 if i % 2 == 0 else qn2
            if nc.button(f"→ {label}", key=f"ql_nav_{i}", use_container_width=True):
                st.session_state.selected_tab = tab
                st.rerun()

    st.markdown("<div style='height:14px;'></div>", unsafe_allow_html=True)

    # ─── Enrichment Coverage + Glossary Health ────────────────────────────────
    col_enr, col_hlth = st.columns(2)

    with col_enr:
        enr_colors = ["#378ADD", "#1D9E75", "#EF9F27", "#E24B4A"]
        # Fixed domain buckets with keyword mappings
        domain_buckets = {
            "Healthcare":       ["PATIENT", "MEMBER", "PERSON", "DEMOGRAPHIC", "BENEFICIARY", "INDIVIDUAL"],
            "Claims & Billing": ["CLAIM", "BILL", "CHARGE", "PAYMENT", "INVOICE", "ENCOUNTER", "REVENUE"],
            "Clinical Terms":   ["DIAGNOSIS", "PROCEDURE", "MEDICATION", "LAB", "TEST", "CLINICAL", "CODE", "ICD", "CPT"],
            "Provider Network": ["PROVIDER", "DOCTOR", "PHYSICIAN", "FACILITY", "NPI", "NETWORK", "PRACTITIONER"],
        }
        domain_stats = {d: {"active": 0, "total": 0} for d in domain_buckets}
        uncategorised = {"active": 0, "total": 0}

        for s in (summaries or []):
            aname = (s.get("Asset Name") or "").upper()
            recs  = PersistenceManager.get_all_versions([s["Asset GUID"]]) or []
            active_n = sum(1 for r in recs if r.get("Active") == 1)
            total_n  = max(len(recs), 1)
            matched = False
            for domain, keywords in domain_buckets.items():
                if any(kw in aname for kw in keywords):
                    domain_stats[domain]["active"] += active_n
                    domain_stats[domain]["total"]  += total_n
                    matched = True
                    break
            if not matched:
                uncategorised["active"] += active_n
                uncategorised["total"]  += total_n

        # Only show domains that have data, or all 4 if nothing is loaded yet
        enr_data = []
        for i, (domain, stats) in enumerate(domain_stats.items()):
            if stats["total"] > 0:
                pct = min(100, int(stats["active"] / stats["total"] * 100))
            else:
                pct = 0
            enr_data.append((domain, pct, enr_colors[i % 4]))
        if uncategorised["total"] > 0:
            pct = min(100, int(uncategorised["active"] / uncategorised["total"] * 100))
            enr_data.append(("Other", pct, "#888780"))
        enr_html = (
            '<div style="background:#fff;border:0.5px solid #E0DED8;border-radius:12px;padding:14px;">'
            + '<div style="font-size:13px;font-weight:500;color:#1A1A18;margin-bottom:12px;">Enrichment Coverage by Domain</div>'
        )
        for lbl, pct, color in enr_data:
            enr_html += (
                f'<div style="display:flex;align-items:center;gap:10px;margin-bottom:10px;">'
                + f'<div style="font-size:12px;color:#888780;width:110px;flex-shrink:0;">{_html.escape(lbl)}</div>'
                + f'<div style="flex:1;height:6px;background:#E0DED8;border-radius:3px;overflow:hidden;">'
                + f'<div style="width:{pct}%;height:100%;border-radius:3px;background:{color};"></div></div>'
                + f'<div style="font-size:11px;color:#888780;width:30px;text-align:right;flex-shrink:0;">{pct}%</div>'
                + '</div>'
            )
        enr_html += '</div>'
        st.markdown(enr_html, unsafe_allow_html=True)

    with col_hlth:
        all_recs    = [r for s in (summaries or []) for r in (PersistenceManager.get_all_versions([s["Asset GUID"]]) or [])]
        active_recs = [r for r in all_recs if r.get("Active") == 1]
        defined_ct  = sum(1 for r in active_recs if str(r.get("Description") or r.get("Definition / Description", "")).strip())
        conflict_ct = sum(1 for e in (audit_log or []) if e.get("conflict_found"))
        orphaned_ct = sum(1 for r in active_recs if not (r.get("Asset GUID") or r.get("table_name")))
        ai_cov_pct  = min(100, int(len(suggestions) / max(metrics["Total Assets"] * 5, 1) * 100)) if suggestions else 0
        health_tiles = [
            ("Defined",     str(defined_ct),    "terms w/ definitions",  "#1D9E75"),
            ("Conflicts",   str(conflict_ct),   "need resolution",        "#E24B4A"),
            ("Orphaned",    str(orphaned_ct),   "no asset link",          "#EF9F27"),
            ("AI Coverage", f"{ai_cov_pct}%",   "AI-enriched terms",     "#378ADD"),
        ]
        hlth_html = (
            '<div style="background:#fff;border:0.5px solid #E0DED8;border-radius:12px;padding:14px;">'
            + '<div style="font-size:13px;font-weight:500;color:#1A1A18;margin-bottom:12px;">Glossary Health</div>'
            + '<div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;">'
        )
        for name, value, sub, color in health_tiles:
            hlth_html += (
                f'<div style="background:#F4F3EF;border-radius:8px;padding:10px 12px;">'
                + f'<div style="font-size:11px;color:#888780;margin-bottom:3px;">{name}</div>'
                + f'<div style="font-size:18px;font-weight:500;color:{color};">{value}</div>'
                + f'<div style="font-size:10px;color:#888780;">{sub}</div>'
                + '</div>'
            )
        hlth_html += '</div></div>'
        st.markdown(hlth_html, unsafe_allow_html=True)

    st.markdown("<div style='height:20px;'></div>", unsafe_allow_html=True)

    # ─── Governance Health Score ──────────────────────────────────────────────
    st.markdown(
        '<div style="height:1px;background:#E0DED8;margin-bottom:20px;"></div>'
        + '<div style="font-size:15px;font-weight:500;color:#1A1A18;margin-bottom:4px;">Governance Health Score</div>'
        + '<div style="font-size:12px;color:#888780;margin-bottom:16px;">Composite score (0–100) combining coverage, freshness, conflict rate, and review velocity.</div>',
        unsafe_allow_html=True,
    )

    gh_metrics   = metrics
    gh_summaries = summaries
    gh_suggestions = suggestions

    coverage_score = min(100, int((gh_metrics["Active Terms"] / max(gh_metrics["Total Assets"] * 5, 1)) * 100))
    freshness_score = 0
    if gh_summaries:
        _now = datetime.now()
        _recent = sum(
            1 for s in gh_summaries
            if (lambda d: d is not None and (_now - d).days <= 7)(
                (lambda v: datetime.fromisoformat(str(v).replace("Z", "")) if v else None)(s.get("Last Updated"))
            )
        )
        freshness_score = min(100, int((_recent / len(gh_summaries)) * 100))

    gh_conflict_count = sum(1 for e in (audit_log or []) if e.get("conflict_found"))
    if gh_suggestions and gh_summaries:
        _approved_lk = {}
        for s in gh_summaries:
            for r in (PersistenceManager.get_all_versions([s["Asset GUID"]]) or []):
                if r.get("Active") == 1:
                    phys = str(r.get("Physical Term") or r.get("Original Name", "")).lower().strip()
                    if phys:
                        _approved_lk.setdefault(phys, []).append(r)
        for sug in gh_suggestions:
            phys = str(sug.get('related_column', '') or sug.get('display_column', '')).lower().strip()
            if phys in _approved_lk:
                if any((ex.get("Business Term") or ex.get("Glossary Term", "")).lower().strip() != sug.get('name', '').lower().strip() for ex in _approved_lk[phys]):
                    gh_conflict_count += 1

    conflict_score = max(0, 100 - gh_conflict_count * 20)
    velocity_score = min(100, int((gh_metrics["Active Terms"] / max(gh_metrics["Total History"], 1)) * 100))
    composite      = int(coverage_score * 0.35 + freshness_score * 0.25 + conflict_score * 0.20 + velocity_score * 0.20)
    gauge_color    = "#1D9E75" if composite >= 70 else "#EF9F27" if composite >= 40 else "#E24B4A"
    grade          = "Excellent" if composite >= 80 else "Good" if composite >= 60 else "Needs Work" if composite >= 40 else "Critical"

    gh_left, gh_right = st.columns([1, 2])
    with gh_left:
        st.markdown(
            '<div style="background:#fff;border:0.5px solid #E0DED8;border-radius:12px;padding:24px;text-align:center;">'
            + '<div style="font-size:10px;color:#888780;font-weight:600;text-transform:uppercase;letter-spacing:0.06em;margin:0 0 10px 0;">Composite Score</div>'
            + '<div style="position:relative;width:140px;height:140px;margin:0 auto 10px auto;">'
            + f'<svg viewBox="0 0 36 36" style="width:140px;height:140px;transform:rotate(-90deg);">'
            + f'<path d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831" fill="none" stroke="#F4F3EF" stroke-width="3"/>'
            + f'<path d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831" fill="none" stroke="{gauge_color}" stroke-width="3" stroke-dasharray="{composite}, 100" stroke-linecap="round"/>'
            + '</svg>'
            + f'<div style="position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);">'
            + f'<div style="font-size:1.8rem;font-weight:600;color:{gauge_color};">{composite}</div>'
            + '<div style="font-size:10px;color:#888780;">/100</div>'
            + '</div></div>'
            + f'<div style="font-size:13px;font-weight:600;color:{gauge_color};">{grade}</div>'
            + '</div>',
            unsafe_allow_html=True,
        )

    with gh_right:
        ghs1, ghs2, ghs3, ghs4 = st.columns(4)
        for col, lbl, score, weight in [
            (ghs1, "Coverage",  coverage_score,  "35%"),
            (ghs2, "Freshness", freshness_score, "25%"),
            (ghs3, "Conflicts", conflict_score,  "20%"),
            (ghs4, "Velocity",  velocity_score,  "20%"),
        ]:
            sc = "#1D9E75" if score >= 70 else "#EF9F27" if score >= 40 else "#E24B4A"
            col.markdown(
                f'<div style="background:#fff;border:0.5px solid #E0DED8;border-radius:8px;padding:12px;text-align:center;">'
                + f'<div style="font-size:10px;color:#888780;font-weight:600;text-transform:uppercase;letter-spacing:0.04em;margin:0 0 4px 0;">{lbl}</div>'
                + f'<div style="font-size:1.4rem;font-weight:600;color:{sc};margin:0;">{score}</div>'
                + f'<div style="font-size:10px;color:#888780;margin:3px 0 6px 0;">{weight}</div>'
                + f'<div style="height:4px;background:#F4F3EF;border-radius:2px;overflow:hidden;">'
                + f'<div style="height:100%;width:{score}%;background:{sc};border-radius:2px;"></div></div>'
                + '</div>',
                unsafe_allow_html=True,
            )
        st.markdown("<div style='height:10px;'></div>", unsafe_allow_html=True)
        gh_recs = []
        if coverage_score  < 50: gh_recs.append(("Improve Coverage",    "Run AI suggestions on more assets.",                            "#E24B4A"))
        if freshness_score < 50: gh_recs.append(("Refresh Stale Terms", "Some records haven't been updated recently.",                   "#EF9F27"))
        if conflict_score  < 80: gh_recs.append(("Resolve Conflicts",   f"{gh_conflict_count} conflict(s) detected.",                   "#E24B4A"))
        if velocity_score  < 50: gh_recs.append(("Accelerate Reviews",  "Speed up the approval workflow.",                              "#EF9F27"))
        if not gh_recs:          gh_recs.append(("All Clear",           "Governance health is strong. Keep it up!",                     "#1D9E75"))
        for title, desc, color in gh_recs:
            st.markdown(
                f'<div style="border-left:3px solid {color};padding:8px 12px;margin-bottom:6px;background:#fff;border-radius:0 6px 6px 0;border:0.5px solid #E0DED8;border-left:3px solid {color};">'
                + f'<div style="font-size:12px;font-weight:500;color:#1A1A18;">{title}</div>'
                + f'<div style="font-size:11px;color:#888780;margin:2px 0 0 0;">{desc}</div></div>',
                unsafe_allow_html=True,
            )

# ═══════════════════════════════════════════════════════════════════════════════
# ENRICHMENT COVERAGE HEATMAP
# ═══════════════════════════════════════════════════════════════════════════════
def render_coverage_heatmap_tab():
    render_dashboard_header("Coverage Heatmap")
    st.markdown('<div class="workbench-header"><div class="accent-line"></div><h1 class="workbench-title">Enrichment Coverage Heatmap</h1><p class="workbench-desc">Visual overlay showing which tables and columns already have approved glossary terms vs. gaps — turns asset search into a prioritisation tool.</p></div>', unsafe_allow_html=True)

    summaries = PersistenceManager.get_all_stored_summaries()
    tables_metadata = st.session_state.get('tables_metadata', {})

    if not summaries and not tables_metadata:
        st.info("No assets discovered yet. Use **Asset Search** to fetch schemas, then return here to see coverage gaps.")
        return

    # Build a combined view: all known assets and their column-level coverage
    coverage_rows = []
    approved_map = {}  # guid -> set of covered physical terms

    for s in (summaries or []):
        guid = s["Asset GUID"]
        records = PersistenceManager.get_all_versions([guid]) or []
        active = [r for r in records if r.get("Active") == 1]
        approved_map[guid] = set(
            str(r.get("Physical Term") or r.get("Original Name", "")) for r in active
        )

    # Merge with currently fetched schemas
    for tid, meta in tables_metadata.items():
        approved_cols = approved_map.get(tid, set())
        total_cols = len(meta.get('columns', []))
        covered = sum(1 for c in meta.get('columns', []) if c in approved_cols)
        pct = int((covered / total_cols) * 100) if total_cols else 0
        for col_name in meta.get('columns', []):
            coverage_rows.append({
                "Asset": meta['name'],
                "Column": col_name,
                "Has Term": "Yes" if col_name in approved_cols else "No",
                "Coverage": pct
            })

    if not coverage_rows:
        # Fallback: show summary-level only
        for s in (summaries or []):
            guid = s["Asset GUID"]
            records = PersistenceManager.get_all_versions([guid]) or []
            active_count = sum(1 for r in records if r.get("Active") == 1)
            coverage_rows.append({
                "Asset": s["Asset Name"],
                "Column": "(summary)",
                "Has Term": "Yes" if active_count > 0 else "No",
                "Coverage": min(100, active_count * 10)
            })

    df_cov = pd.DataFrame(coverage_rows)

    # ── KPI row ──────────────────────────────────────────────────────────────
    assets_list = df_cov["Asset"].unique()
    total_cells = len(df_cov)
    covered_cells = len(df_cov[df_cov["Has Term"] == "Yes"])
    gap_cells = total_cells - covered_cells
    overall_pct = int((covered_cells / total_cells) * 100) if total_cells else 0

    k1, k2, k3 = st.columns(3)
    for col, label, value, color in [
        (k1, "Total Columns", total_cells, "#334155"),
        (k2, "Covered", covered_cells, "#10B981"),
        (k3, "Gaps", gap_cells, "#EF4444"),
    ]:
        col.markdown(f'''
            <div style="background:white; border:1px solid #E5E7EB; border-radius:12px; padding:20px; text-align:center;">
                <p style="font-size:12px; color:#6B7280; font-weight:600; text-transform:uppercase; margin:0 0 4px 0;">{label}</p>
                <h2 style="font-size:2rem; color:{color}; margin:0; font-weight:800;">{value}</h2>
            </div>
        ''', unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Overall progress ─────────────────────────────────────────────────────
    bar_color = "#10B981" if overall_pct >= 70 else "#F59E0B" if overall_pct >= 40 else "#EF4444"
    st.markdown(f'''
        <div style="background:white; border:1px solid #E5E7EB; border-radius:12px; padding:20px;">
            <div style="display:flex; justify-content:space-between; margin-bottom:8px;">
                <span style="font-weight:600; color:#111827;">Overall Enrichment Coverage</span>
                <span style="font-weight:700; color:{bar_color};">{overall_pct}%</span>
            </div>
            <div style="height:12px; background:#F3F4F6; border-radius:6px; overflow:hidden;">
                <div style="height:100%; width:{overall_pct}%; background:{bar_color}; border-radius:6px; transition:width 0.6s ease;"></div>
            </div>
        </div>
    ''', unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Per-asset heatmap grid ───────────────────────────────────────────────
    st.markdown("#### Column-Level Coverage")
    for asset_name in assets_list:
        asset_df = df_cov[df_cov["Asset"] == asset_name]
        covered_count = len(asset_df[asset_df["Has Term"] == "Yes"])
        total_count = len(asset_df)
        pct = int((covered_count / total_count) * 100) if total_count else 0

        with st.expander(f"{asset_name}  —  {covered_count}/{total_count} columns covered ({pct}%)", expanded=False):
            # Render a cell grid
            cells_html = ""
            for _, row in asset_df.iterrows():
                bg = "#DCFCE7" if row["Has Term"] == "Yes" else "#FEE2E2"
                fg = "#166534" if row["Has Term"] == "Yes" else "#991B1B"
                icon = "✓" if row["Has Term"] == "Yes" else "✗"
                cells_html += f'<div style="background:{bg}; color:{fg}; padding:8px 12px; border-radius:6px; font-size:12px; font-weight:500; display:inline-flex; align-items:center; gap:4px; margin:4px;">{icon} {row["Column"]}</div>'

            st.markdown(f'<div style="display:flex; flex-wrap:wrap;">{cells_html}</div>', unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════════
# CONFLICT DETECTION
# ═══════════════════════════════════════════════════════════════════════════════
def render_conflict_detection_tab():
    render_dashboard_header("Conflict Detection")
    st.markdown('<div class="workbench-header"><div class="accent-line"></div><h1 class="workbench-title">Conflict Detection</h1><p class="workbench-desc">Auto-flag when an AI suggestion conflicts with an existing approved term in the hub — see clashes before they land in review.</p></div>', unsafe_allow_html=True)

    # ── Use the approval queue as the single source of truth ─────────────────
    # "Conflicts Found" here mirrors the "Conflict Detected" KPI card in the
    # Approval Queue tab.  Both read from WorkflowManager.get_queue_stats().
    stats = WorkflowManager.get_queue_stats()
    queue = WorkflowManager.load_approval_queue()

    # All queue entries currently flagged as Conflict Detected
    conflict_entries = [e for e in queue if e.get("status") == "Conflict Detected"]
    n_conflicts = stats.get("Conflict Detected", 0)

    # Total queue entries (pending + conflict) as "items scanned"
    n_in_queue = stats.get("Pending", 0) + n_conflicts

    # ── KPI cards ─────────────────────────────────────────────────────────────
    k1, k2 = st.columns(2)
    k1.markdown(f'''
        <div style="background:white; border:1px solid #E5E7EB; border-radius:12px; padding:20px; text-align:center;">
            <p style="font-size:12px; color:#6B7280; font-weight:600; text-transform:uppercase; margin:0 0 4px 0;">Items in Approval Queue</p>
            <h2 style="font-size:2rem; color:#334155; margin:0; font-weight:800;">{n_in_queue}</h2>
        </div>
    ''', unsafe_allow_html=True)
    clash_color = "#EF4444" if n_conflicts else "#10B981"
    k2.markdown(f'''
        <div style="background:white; border:1px solid #E5E7EB; border-radius:12px; padding:20px; text-align:center;">
            <p style="font-size:12px; color:#6B7280; font-weight:600; text-transform:uppercase; margin:0 0 4px 0;">Conflicts Found</p>
            <h2 style="font-size:2rem; color:{clash_color}; margin:0; font-weight:800;">{n_conflicts}</h2>
        </div>
    ''', unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    if not conflict_entries:
        st.success("No conflicts detected. All queued terms are compatible with the existing approved glossary.")
    else:
        st.warning(f"{n_conflicts} conflict(s) detected — review before approving.")
        st.markdown("<br>", unsafe_allow_html=True)
        audit_log = WorkflowManager.load_audit_log()
        for i, entry in enumerate(conflict_entries):
            term_name  = entry.get("term_name", "")
            definition = entry.get("definition", "")
            physical   = entry.get("physical_term") or entry.get("related_column") or ""
            match_type = entry.get("conflict_match_type") or "Conflict Detected"
            ex_name    = entry.get("existing_term_name") or "—"

            # Look up the conflicting approved entry for its definition
            ex_entry = next(
                (e for e in audit_log
                 if e.get("status") in ("Approved", "Approved (Merged)")
                 and (e.get("term_name") or "").strip().lower() == ex_name.strip().lower()),
                None,
            )
            ex_desc = (ex_entry.get("definition") or "") if ex_entry else ""

            label = f"Conflict #{i+1}: `{physical or term_name}` — {match_type}"
            with st.expander(label, expanded=(i == 0)):
                col_a, col_b = st.columns(2)
                with col_a:
                    st.markdown(f'''
                        <div style="background:#FEF2F2; border:1px solid #FECACA; border-radius:8px; padding:16px;">
                            <p style="font-size:11px; color:#991B1B; font-weight:700; text-transform:uppercase; margin:0 0 8px 0;">Existing Approved Term</p>
                            <p style="font-weight:600; color:#111827; margin:0 0 4px 0;">{_html.escape(ex_name)}</p>
                            <p style="font-size:13px; color:#6B7280; margin:0;">{_html.escape(str(ex_desc)[:120])}</p>
                        </div>
                    ''', unsafe_allow_html=True)
                with col_b:
                    st.markdown(f'''
                        <div style="background:#FFF7ED; border:1px solid #FED7AA; border-radius:8px; padding:16px;">
                            <p style="font-size:11px; color:#92400E; font-weight:700; text-transform:uppercase; margin:0 0 8px 0;">Queued Term (New)</p>
                            <p style="font-weight:600; color:#111827; margin:0 0 4px 0;">{_html.escape(term_name)}</p>
                            <p style="font-size:13px; color:#6B7280; margin:0;">{_html.escape(str(definition)[:120])}</p>
                        </div>
                    ''', unsafe_allow_html=True)



def main():
    load_css('style.css')
    render_sidebar()
    tab = st.session_state.get('selected_tab', "Executive Dashboard")
    
    if tab == "Executive Dashboard": render_dashboard_tab()
    elif tab == "Integrations & API": render_integrations_tab()
    elif tab == "Review & Approval": render_review_tab()
    elif tab == "Lineage Map": render_lineage_tab()
    elif tab == "Conflict Detection": render_conflict_detection_tab()
    elif tab == "Asset Search": render_search_tab()
    elif tab == "Glossary AI": render_glossary_tab()
    elif tab in ("Glossary Hub", "Master Glossary"): render_master_glossary_tab()
    else:
        render_dashboard_header(tab)
        st.info(f"The '{tab}' module is currently under construction.")

if __name__ == "__main__":
    main()
