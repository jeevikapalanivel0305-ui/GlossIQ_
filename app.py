import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import json
import os
import sys
import base64
import html as _html
import re
from datetime import datetime

# Ensure backend modules can be imported
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from backend.purview_connector import PurviewConnector
from backend.databricks_unity_connector import DatabricksUnityConnector
from backend.ai_recommender import generate_glossary_suggestions
from backend.internal_governance import generate_internal_governance
from backend.governance_engine import GovernanceEngine
from backend.persistence_manager import PersistenceManager, load_rbac, save_rbac
from backend.workflow_manager import WorkflowManager, is_suggested
from backend.semantic_search import semantic_search_glossary, keyword_search_glossary
from backend import glossary_db
from backend import credential_store

st.set_page_config(
    page_title="Glossary Enricher Accelerator",
    page_icon="📖",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
    <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:opsz,wght,FILL,GRAD@20..48,100..700,0..1,-50..200" />
    <style>
    .material-symbols-outlined {
        font-family: 'Material Symbols Outlined';
        font-weight: normal;
        font-style: normal;
        font-size: 18px;
        line-height: 1;
        letter-spacing: normal;
        text-transform: none;
        display: inline-block;
        white-space: nowrap;
        word-wrap: normal;
        direction: ltr;
        -webkit-font-smoothing: antialiased;
        vertical-align: middle;
    }
    </style>
""", unsafe_allow_html=True)

# ============================================
# LOGIN PAGE
# ============================================

def render_login_page():
    """Render login page - only users added via RBAC Management can log in."""
    st.markdown("""
        <style>
        [data-testid="stSidebar"] { display: none; }
        .login-container {
            max-width: 400px;
            margin: 80px auto;
            padding: 40px;
            border-radius: 12px;
            border: 1px solid #E5E7EB;
            background: white;
            box-shadow: 0 4px 24px rgba(0,0,0,0.06);
        }
        .login-header {
            text-align: center;
            margin-bottom: 32px;
        }
        .login-header h1 {
            font-size: 24px;
            font-weight: 700;
            color: #111827;
            margin: 0;
        }
        .login-header p {
            font-size: 13px;
            color: #6B7280;
            margin-top: 8px;
        }
        .login-brand {
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 10px;
            margin-bottom: 16px;
        }
        div[data-testid="stForm"] [data-testid="stFormSubmitButton"] button,
        div[data-testid="stForm"] button[kind="primary"] {
            background-color: #C90000 !important;
            border-color: #C90000 !important;
            color: #FFFFFF !important;
        }
        div[data-testid="stForm"] [data-testid="stFormSubmitButton"] button:hover,
        div[data-testid="stForm"] button[kind="primary"]:hover {
            background-color: #A90000 !important;
            border-color: #A90000 !important;
            color: #FFFFFF !important;
        }
        </style>
    """, unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 1.5, 1])
    with col2:
        st.markdown("""
            <div class="login-container">
                <div class="login-header">
                    <div class="login-brand">
                        <div style="background:#CC0000; width:38px; height:38px; border-radius:8px; display:flex; align-items:center; justify-content:center; color:white; font-weight:800; font-size:20px;">G</div>
                        <span style="font-size:22px; font-weight:700; color:#111827;">GlossIQ</span>
                    </div>
                    <p>Sign in with your registered email</p>
                </div>
            </div>
        """, unsafe_allow_html=True)

        with st.form("login_form"):
            email = st.text_input("Email", value="admin@glossiq.com", placeholder="Enter your email address")
            password = st.text_input("Password", value="user321", type="password", placeholder="Enter your password")
            submitted = st.form_submit_button("Sign In", type="primary", use_container_width=True)

            if submitted:
                if not email.strip() or not password.strip():
                    st.error("Please enter both email and password.")
                else:
                    # Load RBAC users and check credentials
                    rbac_users_data, _ = load_rbac()
                    user_record = rbac_users_data.get(email.strip().lower())
                    if user_record and user_record.get("password") == password:
                        st.session_state.logged_in = True
                        st.session_state.logged_in_email = email.strip().lower()
                        st.session_state.user_name = user_record.get("name", email.strip())
                        st.session_state.user_role = user_record.get("role", "Reader")
                        st.rerun()
                    else:
                        st.error("Invalid email or password. Only registered users can log in.")

        st.markdown("<p style='text-align:center; font-size:12px; color:#9CA3AF; margin-top:16px;'>Contact your administrator to get access.</p>", unsafe_allow_html=True)

        # ── Forgot Password ──────────────────────────────────────────────────
        if "show_forgot_password" not in st.session_state:
            st.session_state.show_forgot_password = False

        if st.button("Forgot Password?", key="forgot_pwd_btn", use_container_width=True):
            st.session_state.show_forgot_password = not st.session_state.show_forgot_password

        if st.session_state.show_forgot_password:
            st.markdown("---")
            st.markdown("#### Reset Password")
            with st.form("reset_password_form"):
                reset_email = st.text_input("Registered Email", placeholder="Enter your registered email")
                old_password = st.text_input("Current Password", type="password", placeholder="Enter your current password")
                new_password = st.text_input("New Password", type="password", placeholder="Enter new password")
                confirm_password = st.text_input("Confirm Password", type="password", placeholder="Re-enter new password")
                reset_submitted = st.form_submit_button("Reset Password", type="primary", use_container_width=True)

                if reset_submitted:
                    if not reset_email.strip() or not old_password.strip() or not new_password.strip() or not confirm_password.strip():
                        st.error("All fields are required.")
                    elif new_password != confirm_password:
                        st.error("Passwords do not match.")
                    elif len(new_password) < 4:
                        st.error("Password must be at least 4 characters.")
                    else:
                        rbac_users_data, rbac_roles_data = load_rbac()
                        user_record = rbac_users_data.get(reset_email.strip().lower())
                        if user_record:
                            if user_record.get("password") != old_password:
                                st.error("Current password is incorrect.")
                            else:
                                rbac_users_data[reset_email.strip().lower()]["password"] = new_password
                                save_rbac(rbac_users_data, rbac_roles_data)
                                st.success("✅ Password updated successfully! You can now sign in with your new password.")
                                st.session_state.show_forgot_password = False
                        else:
                            st.error("Email not found. Only registered users can reset their password.")


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
_purview_defaults = st.secrets.get("purview", {})
if 'connector_creds' not in st.session_state:
    st.session_state.connector_creds = {
        'purview_account_name': _purview_defaults.get('account_name', ''),
        'purview_tenant_id': _purview_defaults.get('tenant_id', ''),
        'purview_client_id': _purview_defaults.get('client_id', ''),
        'purview_client_secret': _purview_defaults.get('client_secret', '')
    }
if 'purview_search_results' not in st.session_state:
    st.session_state.purview_search_results = []
if 'tables_metadata' not in st.session_state:
    st.session_state.tables_metadata = {}
if 'glossary_suggestions' not in st.session_state:
    st.session_state.glossary_suggestions = []
if 'is_authenticated' not in st.session_state:
    st.session_state.is_authenticated = False
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
if 'logged_in_email' not in st.session_state:
    st.session_state.logged_in_email = ""
if 'purview_collections' not in st.session_state:
    st.session_state.purview_collections = []
if 'selected_tab' not in st.session_state:
    st.session_state.selected_tab = "Executive Dashboard"
if 'glossary_df' not in st.session_state:
    st.session_state.glossary_df = None
if 'glossary_df_version' not in st.session_state:
    st.session_state.glossary_df_version = 0
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
    st.session_state.user_role = "Reader"
if 'user_name' not in st.session_state:
    st.session_state.user_name = ""
if 'uc_search_results' not in st.session_state:
    st.session_state.uc_search_results = []

# ── RBAC: Role-Based Access Control configuration ─────────────────────────
if 'rbac_users' not in st.session_state or 'rbac_roles' not in st.session_state:
    _persisted_users, _persisted_roles = load_rbac()
    st.session_state.rbac_users = _persisted_users
    st.session_state.rbac_roles = _persisted_roles
# Migration: ensure can_read exists in all roles and users (added after initial release)
for _r in st.session_state.rbac_roles.values():
    if "can_read" not in _r:
        _r["can_read"] = True
for _u in st.session_state.rbac_users.values():
    if "can_read" not in _u:
        _u["can_read"] = True

# ── On every fresh browser session, wipe Pending/Conflict entries from the
#    approval queue so the Review tab starts clean.  Approved/Rejected entries
#    remain in the audit log and are untouched.
if 'queue_cleared_this_session' not in st.session_state:
    WorkflowManager.purge_pending_from_queue()
    st.session_state.queue_cleared_this_session = True
    st.session_state.session_start_time = datetime.now().isoformat()
# Ensure session_start_time always exists (handles sessions started before this code)
if 'session_start_time' not in st.session_state:
    st.session_state.session_start_time = datetime.now().isoformat()

# ── Auto-sync: rebuild SQLite DB from audit log if DB is empty ─────────────
if 'db_synced_this_session' not in st.session_state:
    _audit_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backend", "audit_log.json")
    _master_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backend", "glossary_master.json")
    glossary_db.sync_from_audit_log(_audit_path)
    glossary_db.sync_from_master_json(_master_path)
    glossary_db.fix_duplicate_versions()
    st.session_state.db_synced_this_session = True

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
    # Every connector starts disconnected — the card shows "Connect" until the user connects it
    st.session_state.integration_connectors = {k: dict(v) for k, v in _CONNECTOR_DEFAULTS.items()}

# Permanent Cache Initialization (Survives tab-switching unmounting)
if 'perm_cache' not in st.session_state:
    st.session_state.perm_cache = {
        'search_source_type': 'All',
        'search_collection': 'All Collections',
        'search_keyword': 'Customer',
        'glossary_industry': 'General',
        'glossary_options': ['Business Term', 'Business Definition', 'Classifications'],
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
        def nav_button(label, icon, tab_name, key):
            st.button(
                label,
                key=key,
                icon=f":material/{icon}:",
                use_container_width=True,
                on_click=set_nav_tab,
                args=(tab_name,),
                type="primary" if current_tab == tab_name else "secondary",
            )

        st.markdown(f'''
            <div class="sidebar-brand">
                <div class="sidebar-brand-mark">G</div>
                <div class="sidebar-brand-name">GlossIQ</div>
            </div>
            <div class="sidebar-brand-subtitle">
                GLOSSARY ENRICHER
            </div>
        ''', unsafe_allow_html=True)

        current_tab = st.session_state.get('selected_tab', "Executive Dashboard")

        st.markdown('<div class="sidebar-category">Intelligence</div>', unsafe_allow_html=True)
        nav_button("Executive Dashboard", "home", "Executive Dashboard", "nav_dashboard")
        nav_button("Conflict Detection", "compare_arrows", "Conflict Detection", "nav_Conflict")

        st.markdown('<div class="sidebar-category">Operations</div>', unsafe_allow_html=True)
        nav_button("Integrations & API", "power", "Integrations & API", "nav_Integrations")
        nav_button("Asset Search", "database", "Asset Search", "nav_Asset Search")

        st.markdown('<div class="sidebar-category">Governance</div>', unsafe_allow_html=True)
        nav_button("Glossary AI", "auto_awesome", "Glossary AI", "nav_Glossary AI")
        nav_button("Review & Approval", "assignment_turned_in", "Review & Approval", "nav_Review")
        nav_button("Glossary Hub", "menu_book", "Glossary Hub", "nav_Master Glossary")
        nav_button("Semantic Search", "search", "Semantic Search", "nav_Semantic Search")
        nav_button("Lineage Map", "account_tree", "Lineage Map", "nav_Lineage")

        st.markdown('<div class="sidebar-category">System Admin</div>', unsafe_allow_html=True)
        nav_button("RBAC Management", "settings", "RBAC Management", "nav_RBAC")

        _available_demo_roles = list(st.session_state.rbac_roles.keys())
        _current_role_idx = _available_demo_roles.index(st.session_state.user_role) if st.session_state.user_role in _available_demo_roles else 0
        _is_admin = st.session_state.user_role == "Administrator"
        new_role = st.selectbox(
            "Switch Role (Demo)", 
            _available_demo_roles, 
            index=_current_role_idx,
            disabled=not _is_admin
        )
        if _is_admin and new_role != st.session_state.user_role:
            st.session_state.user_role = new_role
            st.session_state.logged_in = False
            st.session_state.logged_in_email = ""
            st.rerun()

        # Generate initials from the logged-in user's name
        _uname = st.session_state.user_name or ""
        _initials = "".join([part[0].upper() for part in _uname.split() if part][:2]) if _uname else "?"

        st.markdown(f'''
            <div class="sidebar-user">
                <div class="sidebar-user-avatar">{_initials}</div>
                <div class="sidebar-user-details">
                    <div class="sidebar-user-name">{st.session_state.user_name}</div>
                    <div class="sidebar-user-role">{st.session_state.user_role}</div>
                </div>
            </div>
        ''', unsafe_allow_html=True)
        if st.button("Logout", key="logout_btn", icon=":material/logout:", use_container_width=True):
            st.session_state.logged_in = False
            st.session_state.logged_in_email = ""
            st.rerun()

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

_NEW_CONN = "Enter new credentials"
_PV_FIELD_KEYS = {"account_name": "mp_ac_Microsoft Purview", "tenant_id": "mp_te_Microsoft Purview",
                  "client_id": "mp_ci_Microsoft Purview", "client_secret": "mp_cs_Microsoft Purview"}


def _cred_key():
    """Encryption key for saved credentials from Streamlit secrets, if one is configured."""
    try:
        return st.secrets.get("CREDENTIALS_KEY") or None
    except Exception:
        return None


def _load_saved_purview_creds():
    """Load button: check the PIN, then copy the saved values into the Purview fields."""
    title = st.session_state.get("mp_saved_choice")
    try:
        creds = credential_store.unlock(st.session_state.get("logged_in_email", ""), title,
                                        st.session_state.get("mp_saved_pin", ""), _cred_key())
    except credential_store.PinError as e:
        st.session_state["mp_saved_msg"] = (False, str(e))
    else:
        for f, k in _PV_FIELD_KEYS.items():
            st.session_state[k] = creds.get(f, "")
        st.session_state["mp_saved_msg"] = (True, f"Loaded '{title}'. Click Save & Connect.")
    st.session_state["mp_saved_pin"] = ""


def _delete_saved_purview_creds():
    title = st.session_state.get("mp_saved_choice")
    try:
        credential_store.delete(st.session_state.get("logged_in_email", ""), title,
                                st.session_state.get("mp_saved_pin", ""))
    except credential_store.PinError as e:
        st.session_state["mp_saved_msg"] = (False, f"Enter the right PIN to delete it. {e}")
    else:
        st.session_state["mp_saved_choice"] = _NEW_CONN
        st.session_state["mp_saved_msg"] = (True, f"Deleted '{title}'.")
    st.session_state["mp_saved_pin"] = ""


@st.dialog("Save Purview credentials?")
def _save_purview_creds_dialog():
    creds = st.session_state["_offer_save_purview_creds"]
    user = st.session_state.get("logged_in_email", "")
    st.markdown(f"Connected to **{_html.escape(creds['account_name'])}**. Save these credentials so you "
                "can pick them next time instead of typing them again?")
    title = st.text_input("Title", key="mp_save_title", placeholder="e.g. iLink governance hub")
    if title.strip() in credential_store.list_titles(user):
        st.caption("A saved connection with this title exists and will be replaced.")
    p1, p2 = st.columns(2)
    with p1:
        pin = st.text_input("PIN", type="password", max_chars=8, key="mp_save_pin",
                            help=f"{credential_store.PIN_RULE}. You'll enter it to load these credentials.")
    with p2:
        pin2 = st.text_input("Confirm PIN", type="password", max_chars=8, key="mp_save_pin2")
    pin_problem = ("" if not pin else
                   f"The PIN must be {credential_store.PIN_RULE}." if not credential_store.valid_pin(pin) else
                   "The PINs don't match." if pin2 and pin != pin2 else "")
    if pin_problem:
        st.caption(f":red[{pin_problem}]")
    can_save = bool(title.strip()) and credential_store.valid_pin(pin) and pin == pin2
    c1, c2 = st.columns(2)
    with c1:
        if st.button("Save", type="primary", use_container_width=True, disabled=not can_save, key="mp_save_yes"):
            credential_store.save(user, title, creds, pin, _cred_key())
            st.session_state.pop("_offer_save_purview_creds", None)
            for k in ("mp_save_title", "mp_save_pin", "mp_save_pin2"):
                st.session_state.pop(k, None)
            st.toast(f"Saved as '{title.strip()}'")
            st.rerun()
    with c2:
        if st.button("Don't save", use_container_width=True, key="mp_save_no"):
            st.session_state.pop("_offer_save_purview_creds", None)
            st.rerun()


def _configure_integration_dialog(name):
    """Set flag to open the connector config panel and rerun to show it."""
    st.session_state["_open_integration_config"] = name

@st.dialog("Configure Connector")
def _show_connector_dialog(name):
    """Native Streamlit dialog popup for connector configuration."""
    cfg = st.session_state.integration_connectors[name]
    st.markdown(f"### {name}")
    st.caption(cfg['desc'])
    st.divider()

    if name == "Databricks Unity":
        st.info("Connect to Databricks to push glossary terms as Unity Catalog tags.")
        st.text_input("Workspace URL", placeholder="https://adb-xxxx.azuredatabricks.net", value=cfg['api_endpoint'], key=f"int_ep_{name}")
        st.text_input("Personal Access Token", type="password", value=cfg['api_token'], key=f"int_tk_{name}")
    elif name == "Slack":
        st.text_input("Webhook URL", value=cfg['api_endpoint'], key=f"int_ep_{name}")
        st.text_input("Bot Token", type="password", value=cfg['api_token'], key=f"int_tk_{name}")
        st.text_input("Default Channel", value=cfg.get('channel', '#data-governance'), key=f"int_ch_{name}")
    elif name == "Microsoft Purview":
        st.info("Authenticate to Microsoft Purview data map.")
        _user = st.session_state.get("logged_in_email", "")
        _saved = credential_store.list_titles(_user)
        # Fields start from the active credentials; a saved connection overwrites them
        for _f, _k in _PV_FIELD_KEYS.items():
            st.session_state.setdefault(_k, st.session_state.connector_creds.get(f"purview_{_f}", ""))
        if _saved:
            st.selectbox("Saved connection", [_NEW_CONN] + _saved, key="mp_saved_choice",
                         help="Pick credentials you saved earlier, enter their PIN and load them.")
            _choice = st.session_state.get("mp_saved_choice", _NEW_CONN)
            if _choice != _NEW_CONN:
                if credential_store.has_pin(_user, _choice):
                    st.text_input("PIN", type="password", max_chars=8, key="mp_saved_pin",
                                  placeholder=f"PIN for '{_choice}'")
                else:
                    st.caption("Saved before PINs were added — load it, then connect and save it again with a PIN.")
                _b1, _b2 = st.columns(2)
                with _b1:
                    st.button("Load credentials", type="primary", use_container_width=True, key="mp_saved_load",
                              on_click=_load_saved_purview_creds)
                with _b2:
                    st.button("Delete saved connection", use_container_width=True, key="mp_saved_delete",
                              on_click=_delete_saved_purview_creds)
            _msg = st.session_state.pop("mp_saved_msg", None)
            if _msg:
                (st.success if _msg[0] else st.error)(_msg[1])
        st.text_input("Account Name", key=_PV_FIELD_KEYS["account_name"])
        st.text_input("Tenant ID", key=_PV_FIELD_KEYS["tenant_id"])
        st.text_input("Client ID", key=_PV_FIELD_KEYS["client_id"])
        st.text_input("Client Secret", type="password", key=_PV_FIELD_KEYS["client_secret"])
    else:
        st.text_input("API Endpoint", value=cfg['api_endpoint'], key=f"int_ep_{name}")
        st.text_input("API Token / Secret", type="password", value=cfg['api_token'], key=f"int_tk_{name}")

    st.divider()
    c1, c2 = st.columns(2)
    with c1:
        if st.button("Save & Connect", type="primary", use_container_width=True, key=f"int_save_{name}"):
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
                    # Offer to save these credentials unless they're already saved
                    _new_creds = {"account_name": account_name, "tenant_id": tenant_id,
                                  "client_id": client_id, "client_secret": client_secret}
                    if not credential_store.find_title(st.session_state.get("logged_in_email", ""), _new_creds, _cred_key()):
                        st.session_state["_offer_save_purview_creds"] = _new_creds
                    try:
                        st.session_state.purview_collections = connector.get_collections()
                    except:
                        pass
                    try:
                        st.session_state.purview_classification_types = connector.get_classification_types()
                    except:
                        st.session_state.purview_classification_types = []
                else:
                    st.error(f"Failed to authenticate: {msg}")
                    st.stop()
            elif name == "Databricks Unity":
                _ep = st.session_state[f"int_ep_{name}"]
                _tk = st.session_state[f"int_tk_{name}"]
                st.session_state.integration_connectors[name]['api_endpoint'] = _ep
                st.session_state.integration_connectors[name]['api_token'] = _tk
                with st.spinner("Testing Databricks connection..."):
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
            st.session_state.pop("_open_integration_config", None)
            st.success(f"Connected to {name} successfully!")
            st.rerun()
    with c2:
        if cfg['status'] == 'Connected':
            if st.button("Disconnect", use_container_width=True, key=f"int_disc_{name}"):
                st.session_state.integration_connectors[name]['status'] = 'Not connected'
                st.session_state.integration_connectors[name]['last_sync'] = ''
                if name == "Microsoft Purview":
                    st.session_state.is_authenticated = False
                st.session_state.pop("_open_integration_config", None)
                st.rerun()

def render_integrations_tab():
    render_dashboard_header("Integrations & API")
    st.markdown('<div class="workbench-header"><div class="accent-line"></div><h1 class="workbench-title">Integrations & API</h1><p class="workbench-desc">Connect your glossary hub to external tools and expose approved terms via REST API</p></div>', unsafe_allow_html=True)

    connectors = st.session_state.integration_connectors

    # ── Show dialog popup if a connector is selected ──────────────────────────
    _open_cfg = st.session_state.pop("_open_integration_config", None)
    if _open_cfg and _open_cfg in connectors:
        _show_connector_dialog(_open_cfg)
    elif st.session_state.get("_offer_save_purview_creds"):
        _save_purview_creds_dialog()

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
                st.rerun()

    # ═══════════════════════════════════════════════════════════════════════════
    # CATALOG CONNECTORS
    # ═══════════════════════════════════════════════════════════════════════════
    st.markdown("<p style='font-size:13px;font-weight:600;color:#6B7280;text-transform:uppercase;margin-bottom:12px;'>CATALOG CONNECTORS</p>", unsafe_allow_html=True)

    names = list(connectors.keys())

    # Render 3 per row
    for row_start in range(0, len(names), 3):
        row_names = names[row_start:row_start + 3]
        cols = st.columns(3)
        for i, name in enumerate(row_names):
            _render_connector_card(cols[i], name, connectors[name])

def _review_term_dialog(idx):
    """Set flag to show inline review for this term."""
    st.session_state["_open_review_term"] = idx

def _render_inline_review_term(idx):
    """Render term review inline (replaces st.dialog)."""
    item = st.session_state.review_queue[idx]
    st.markdown(f"### Review: {item['term']}")
    st.write(f"**Asset:** {item['asset']}")
    st.write(f"**Requested By:** {item['requester']}")
    st.write(f"**Description:** {item['description']}")

    st.divider()
    comment = st.text_area("Add a comment (optional)", key=f"rev_com_{idx}")

    c1, c2 = st.columns(2)
    with c1:
        if st.button("Approve", type="primary", use_container_width=True, key=f"rev_approve_{idx}"):
            st.session_state.review_queue[idx]['status'] = 'Approved'
            st.session_state.pop("_open_review_term", None)
            st.success("Term approved!")
            st.rerun()
    with c2:
        if st.button("Reject", use_container_width=True, key=f"rev_reject_{idx}"):
            st.session_state.review_queue[idx]['status'] = 'Rejected'
            st.session_state.pop("_open_review_term", None)
            st.rerun()

_AQ_UNDECIDED = ("Pending", "Conflict Detected")

# Generated field → (label, icon, text colour, background)
_AQ_FIELD_META = {
    "term_name":      ("Business Term",  "🏷️", "#5B21B6", "#EDE9FE"),
    "definition":     ("Description",    "📝", "#0F766E", "#CCFBF1"),
    "classification": ("Classification", "🛡️", "#B45309", "#FEF3C7"),
}

# Result state → (chip label, chip text colour, chip background, row background)
_AQ_STATE_STYLE = {
    "changed":      ("Changed",          "#A32D2D", "#FCEBEB", "#FFF5F5"),
    "duplicate":    ("Already in use",   "#A32D2D", "#FCEBEB", "#FFF5F5"),
    "other_column": ("Different column", "#854F0B", "#FEF3C7", "#FFFBEB"),
    "same":         ("Same",             "#3B6D11", "#EAF3DE", "#FFFFFF"),
    "added":        ("New (was empty)",  "#185FA5", "#E6F1FB", "#FFFFFF"),
}


def _aq_field_pill(field_key):
    label, icon, fg, bg = _AQ_FIELD_META[field_key]
    return (f'<span style="display:inline-flex;align-items:center;gap:4px;font-size:11.5px;font-weight:600;'
            f'color:{fg};background:{bg};border-radius:999px;padding:3px 10px;">{icon} {label}</span>')


def _aq_entry_fields(entries):
    """Generated fields present in any of the entries, in display order."""
    return [k for k in _AQ_FIELD_META if any(is_suggested(e, k) for e in entries)]


def _aq_conflict_guidance(info):
    existing = info["existing"]
    if existing["match"] == "same_name":
        text = (f"A business term can be active on only one column per table. Approving deactivates it on "
                f"<strong>{_html.escape(existing['physical_term'] or '—')}</strong>. Reject to keep the current mapping.")
    elif info["fields"]:
        text = ("<strong>Approve</strong> or <strong>Merge</strong> replaces the highlighted values and creates a new version. "
                "<strong>Reject</strong> keeps the approved version as it is.")
    else:
        text = "Nothing would change. <strong>Reject</strong> to clear it from the queue."
    if info.get("nulled"):
        text += (" <br/>⚪ Not generated: <strong>" + ", ".join(info["nulled"]) +
                 "</strong> — stored as <code>null</code> in the Glossary Hub on approval.")
    return text


def _aq_conflict_comparison_html(info):
    """Side-by-side table: approved value vs new suggestion for the generated fields, conflicts highlighted."""
    existing = info["existing"]
    approved_meta = " · ".join(p for p in (
        f"v{existing['version']}" if existing.get("version") else "",
        f"approved {existing['decided_on']}" if existing.get("decided_on") else "",
    ) if p)

    def _val(v):
        if not str(v or "").strip():
            return '<span style="color:#9CA3AF;font-style:italic;">empty</span>'
        return f'<span style="color:#1F2937;">{_html.escape(str(v))}</span>'

    th = "padding:8px 12px;text-align:left;font-size:11px;font-weight:700;color:#6B7280;text-transform:uppercase;letter-spacing:.04em;border-bottom:1px solid #E5E7EB;"
    td = "padding:9px 12px;font-size:13px;vertical-align:top;border-bottom:1px solid #F0F0EE;"
    rows_html = ""
    for r in info["rows"]:
        chip, fg, bg, row_bg = _AQ_STATE_STYLE[r["state"]]
        is_conflict = r["state"] in ("changed", "duplicate", "other_column")
        marker = f"border-left:3px solid {fg};" if is_conflict else "border-left:3px solid transparent;"
        tick = "⚠ " if is_conflict else "✓ " if r["state"] == "same" else ""
        suggested = f"<strong>{_val(r['suggested'])}</strong>" if is_conflict else _val(r["suggested"])
        rows_html += (
            f'<tr style="background:{row_bg};">'
            f'<td style="{td}{marker}font-weight:600;color:#374151;white-space:nowrap;">{r["field"]}</td>'
            f'<td style="{td}">{_val(r["current"])}</td>'
            f'<td style="{td}">{suggested}</td>'
            f'<td style="{td}white-space:nowrap;"><span style="font-size:11px;font-weight:700;color:{fg};background:{bg};'
            f'border-radius:999px;padding:3px 10px;">{tick}{chip}</span></td>'
            '</tr>'
        )
    return (
        '<div style="border:1px solid #E5E7EB;border-radius:10px;overflow:hidden;background:#fff;box-shadow:0 1px 3px rgba(0,0,0,.04);">'
        '<table style="width:100%;border-collapse:collapse;">'
        f'<thead><tr style="background:#F9FAFB;">'
        f'<th style="{th}width:18%;">Field</th>'
        f'<th style="{th}width:33%;">Currently approved'
        + (f' <span style="text-transform:none;font-weight:500;color:#9CA3AF;">({approved_meta})</span>' if approved_meta else '') +
        f'</th>'
        f'<th style="{th}width:33%;">New suggestion</th>'
        f'<th style="{th}width:16%;">Result</th>'
        '</tr></thead>'
        f'<tbody>{rows_html}</tbody></table>'
        f'<div style="padding:9px 12px;font-size:12px;color:#4B5563;background:#F9FAFB;border-top:1px solid #E5E7EB;line-height:1.6;">'
        f'ℹ️ {_aq_conflict_guidance(info)}</div>'
        '</div>'
    )


def _aq_apply(action, entries, comment):
    """Run approve / merge / reject over queue entries; returns (level, message) for display."""
    done, failed = 0, []
    for e in entries:
        if action == "approve":
            ok, msg = WorkflowManager.approve_term(e["term_id"], approver_comment=comment)
        elif action == "merge":
            ok, msg = WorkflowManager.approve_with_merge(e["term_id"], approver_comment=comment)
        else:
            ok, msg = WorkflowManager.reject_term(e["term_id"], approver_comment=comment)
        if ok:
            done += 1
        else:
            failed.append(f"**{e.get('physical_term') or e.get('term_name')}** — {msg}")
    if done and action in ("approve", "merge"):
        st.session_state["hub_approved_this_session"] = True
    verb = {"approve": "approved", "merge": "merged", "reject": "rejected"}[action]
    msg = f"{done} term(s) {verb}."
    if failed:
        return "warning", msg + "\n\nSkipped:\n" + "\n".join(f"- {f}" for f in failed)
    return "success", msg


def _render_approval_queue(entries):
    """Approval Queue grouped table by table (like the Glossary Hub), with field-level conflict details."""
    perms = get_current_user_permissions()
    can_approve = perms.get("can_approve", False)
    can_reject  = perms.get("can_reject", False)
    ver = st.session_state.get("aq_editor_ver", 0)

    if "_aq_result" in st.session_state:
        level, msg = st.session_state.pop("_aq_result")
        getattr(st, level)(msg)

    # Same-named tables from different databases stay separate
    by_table = {}
    for e in entries:
        key = (((e.get("table_name") or "").strip() or "—").upper(), _asset_location(e.get("table_qualified_name")))
        by_table.setdefault(key, []).append(e)

    selected, conflicts = [], []
    for tbl, tbl_loc in sorted(by_table):
        tbl_entries = by_table[(tbl, tbl_loc)]
        tbl_src = next((e.get("source_type") for e in tbl_entries if e.get("source_type")), "")
        active = sorted(
            (e for e in tbl_entries if e.get("status") in _AQ_UNDECIDED),
            key=lambda e: 0 if (e.get("term_type") or "").strip().lower() == "table" else 1,
        )
        decided = [e for e in tbl_entries if e.get("status") not in _AQ_UNDECIDED]
        infos = {e["term_id"]: WorkflowManager.describe_conflict(e) for e in active if e.get("conflict_found")}
        conflicts += [e for e in active if e["term_id"] in infos]

        fields = _aq_entry_fields(tbl_entries)
        not_generated = {_AQ_FIELD_META[k][0] for k in _AQ_FIELD_META if k not in fields}
        _chip = "font-size:11.5px;font-weight:700;border-radius:999px;padding:3px 10px;"
        chips = f'<span style="{_chip}color:#854F0B;background:#FAEEDA;">⏳ {len(active)} pending</span>'
        if infos:
            chips += f'<span style="{_chip}color:#A32D2D;background:#FCEBEB;">⚠ {len(infos)} conflict{"s" if len(infos) != 1 else ""}</span>'
        if decided:
            chips += f'<span style="{_chip}color:#4B5563;background:#E5E7EB;">✔ {len(decided)} decided</span>'
        accent = "#E24B4A" if infos else "#C90000"
        st.markdown(
            "<div style='margin:22px 0 8px 0;padding:12px 16px;background:linear-gradient(90deg,#FFF5F5 0%,#FFFFFF 60%);"
            f"border:1px solid #F1E3E3;border-left:5px solid {accent};border-radius:10px;box-shadow:0 1px 3px rgba(0,0,0,.05);'>"
            "<div style='display:flex;align-items:center;gap:10px;flex-wrap:wrap;'>"
            f'<span class="material-symbols-outlined" style="font-size:22px;color:{accent};">table_chart</span>'
            f'<span style="font-weight:800;font-size:15px;color:#1F2937;letter-spacing:.01em;">{_html.escape(tbl)}</span>'
            + (f'<span style="font-size:12px;color:#6B7280;">📍 {_html.escape(tbl_loc)}</span>' if tbl_loc else '')
            + (f'<span style="{_chip}color:#1D4ED8;background:#EFF6FF;">{_html.escape(tbl_src)}</span>' if tbl_src else '') +
            f'<span style="flex:1;"></span><span style="display:flex;gap:6px;flex-wrap:wrap;">{chips}</span></div>'
            "<div style='display:flex;align-items:center;gap:6px;flex-wrap:wrap;margin-top:8px;'>"
            "<span style='font-size:11px;font-weight:700;color:#6B7280;text-transform:uppercase;letter-spacing:.05em;margin-right:2px;'>Generated</span>"
            + "".join(_aq_field_pill(f) for f in fields) +
            "</div></div>",
            unsafe_allow_html=True,
        )

        if active:
            df = pd.DataFrame([{
                "Select":         False,
                "Status":         "🔴 Conflict" if e["term_id"] in infos else "🟡 Pending",
                "Conflict In":    ("⚠️ " + (", ".join(infos[e["term_id"]]["fields"]) or "Identical to approved"))
                                  if e["term_id"] in infos else "—",
                "Type":           e.get("term_type") or "Column",
                "Physical Term":  e.get("physical_term") or e.get("related_column") or "",
                "Business Term":  e.get("term_name", ""),
                "Description":    e.get("definition", ""),
                "Classification": e.get("classification", ""),
                "Confidence (%)": int(e.get("confidence_score") or 0),
                "Source":         e.get("source_type") or e.get("source", ""),
                "term_id":        e["term_id"],
            } for e in active])
            # Only the information that was generated for this table
            visible = [c for c in df.columns if c != "term_id" and c not in not_generated]
            edited = st.data_editor(
                df,
                key=f"aq_ed_{_safe_mermaid_id(tbl + '_' + tbl_loc)}_v{ver}",
                hide_index=True,
                use_container_width=True,
                column_order=visible,
                disabled=[c for c in visible if c != "Select"],
                column_config={
                    "Select":         st.column_config.CheckboxColumn("Select", help="Tick to approve, merge or reject", default=False, width="small"),
                    "Confidence (%)": st.column_config.ProgressColumn("Confidence (%)", format="%d%%", min_value=0, max_value=100),
                    "Status":         st.column_config.TextColumn("Status"),
                    "Conflict In":    st.column_config.TextColumn("Conflict In", help="Fields that differ from the currently approved version — see details below the table"),
                },
            )
            selected += [e for e, sel in zip(active, edited["Select"].tolist()) if sel]

            for e in active:
                info = infos.get(e["term_id"])
                if not info:
                    continue
                name = e.get("physical_term") or e.get("term_name") or ""
                with st.expander(f"⚠️ {name}  —  {info['summary']}", expanded=len(infos) <= 3):
                    if info["existing"]:
                        st.markdown(_aq_conflict_comparison_html(info), unsafe_allow_html=True)
                    else:
                        st.caption(f"Matches existing term **{e.get('existing_term_name') or '—'}** ({info['summary']}).")
        elif not decided:
            st.caption("No terms in the current filter.")

        if decided:
            with st.expander(f"{len(decided)} decided term(s)", expanded=False):
                _dec = pd.DataFrame([{
                    "Physical Term":  e.get("physical_term") or "—",
                    "Business Term":  e.get("term_name", ""),
                    "Description":    e.get("definition", ""),
                    "Classification": e.get("classification", ""),
                    "Status":         e.get("status", ""),
                    "Decided On":     (e.get("decision_date") or "")[:10],
                    "Comment":        e.get("approver_comment", ""),
                } for e in decided])
                st.dataframe(_dec[[c for c in _dec.columns if c not in not_generated]],
                             use_container_width=True, hide_index=True)

    # ── Footer: actions on the ticked rows ──────────────────────────────────────
    sel_conflicts = [e for e in selected if e.get("conflict_found")]
    st.markdown("<div style='height:10px;'></div>", unsafe_allow_html=True)
    st.markdown(
        "<div style='border:0.5px solid #E0DED8;border-radius:10px;padding:10px 16px;background:#fff;"
        "display:flex;align-items:center;gap:14px;'>"
        f"<span style='font-size:13px;font-weight:600;color:#374151;'>{len(selected)} selected</span>"
        f"<span style='font-size:12px;color:#888780;'>{len(sel_conflicts)} with conflicts · {len(conflicts)} conflict(s) in view</span>"
        "</div>",
        unsafe_allow_html=True,
    )
    comment = st.text_input("Approver comment (optional)", key="aq_bulk_comment",
                            placeholder="Applied to every term you approve, merge or reject")
    b1, b2, b3, b4 = st.columns(4)
    action = None
    with b1:
        if st.button("✓ Approve Selected", key="aq_approve", type="primary", use_container_width=True,
                     disabled=not selected or not can_approve,
                     help="🔒 No permission" if not can_approve else None):
            action = ("approve", selected)
    with b2:
        if st.button("🔀 Merge Selected", key="aq_merge", use_container_width=True,
                     disabled=not sel_conflicts or not can_approve,
                     help="🔒 No permission" if not can_approve else "Create a new version of the approved term (conflict rows only)"):
            action = ("merge", sel_conflicts)
    with b3:
        if st.button("✕ Reject Selected", key="aq_reject", use_container_width=True,
                     disabled=not selected or not can_reject,
                     help="🔒 No permission" if not can_reject else None):
            action = ("reject", selected)
    with b4:
        if st.button("✕ Reject All Conflicts", key="aq_reject_conflicts", use_container_width=True,
                     disabled=not conflicts or not can_reject,
                     help="🔒 No permission" if not can_reject else "Reject every conflict-flagged term in view"):
            action = ("reject", conflicts)

    if action:
        st.session_state["_aq_result"] = _aq_apply(action[0], action[1], comment or f"Bulk {action[0]}")
        st.session_state["aq_editor_ver"] = ver + 1
        st.rerun()


def render_review_tab():
    render_dashboard_header("Review & Approval")
    st.markdown(
        '<div class="workbench-header"><div class="accent-line"></div>'
        '<h1 class="workbench-title">Review & Approval Workflow</h1>'
        '<p class="workbench-desc">AI Suggestion → Conflict Check → Approve / Reject → Glossary Hub</p>'
        '</div>',
        unsafe_allow_html=True,
    )

    # ── Show persistent email notification after rerun ─────────────────────────
    if "_email_notification" in st.session_state:
        email_ok, email_msg = st.session_state.pop("_email_notification")
        if email_ok and "Registered" not in str(email_msg):
            st.success(f"📧 {email_msg}")
        elif not email_ok:
            st.warning(f"📧 Email not sent: {email_msg}")

    # ── RBAC notice ─────────────────────────────────────────────────────────
    _review_perms = get_current_user_permissions()
    if not _review_perms.get("can_approve") and not _review_perms.get("can_reject"):
        st.info(f"🔒 **{st.session_state.user_name}** — You have **view-only** access to this queue. Approve/Reject actions require elevated permissions (manage in **RBAC Management**).")

    # ── Unity Catalog scope: when connected, every sub-tab is restricted to UC terms ──
    _uc_on     = st.session_state.get('integration_connectors', {}).get('Databricks Unity', {}).get('status') == 'Connected'
    _uc_source = "Databricks Unity Catalog" if _uc_on else None

    # ── Queue stats bar ────────────────────────────────────────────────────────
    _session_start = st.session_state.get('session_start_time', '')
    stats = WorkflowManager.get_queue_stats(source_filter=_uc_source, session_start=_session_start)
    s_cols = st.columns(5)
    STAT_META = [
        ("Pending",           "#F59E0B", "hourglass_empty"),
        ("Conflict Detected", "#EF4444", "warning"),
        ("Approved",          "#10B981", "check_circle"),
        ("Approved (Merged)", "#3B82F6", "call_merge"),
        ("Rejected",          "#6B7280", "cancel"),
    ]
    st.markdown('<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:opsz,wght,FILL,GRAD@24,400,0,0" />', unsafe_allow_html=True)
    for col, (label, color, icon) in zip(s_cols, STAT_META):
        with col:
            st.markdown(
                f"""<div style="background:white; border:1px solid #E5E7EB; border-top:4px solid {color};
                border-radius:10px; padding:12px 14px; text-align:center; box-shadow: 0 1px 3px rgba(0,0,0,0.04);">
                    <div style="font-size:24px; font-weight:700; color:{color}; line-height:1.2;">{stats.get(label, 0)}</div>
                    <div style="font-size:13px; font-weight:600; color:#374151; margin-top:6px; display:flex; align-items:center; justify-content:center; gap:5px;">
                        <span class="material-symbols-outlined" style="font-size:18px; color:{color}; vertical-align:middle;">{icon}</span>
                        <span>{label}</span>
                    </div>
                </div>""",
                unsafe_allow_html=True,
            )

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Pre-load source-scoped audit log (used both by queue cards and Audit Log tab) ──
    _tab1_audit = WorkflowManager.load_audit_log()
    if _uc_on:
        _tab1_audit = [e for e in _tab1_audit if e.get("source") == "Databricks Unity Catalog"]

    # ── Ensure Purview classification types are cached ──
    if st.session_state.get("is_authenticated") and not st.session_state.get("purview_classification_types"):
        try:
            _creds = st.session_state.get("connector_creds", {})
            _pc = PurviewConnector(_creds.get("purview_account_name",""), _creds.get("purview_tenant_id",""), _creds.get("purview_client_id",""), _creds.get("purview_client_secret",""))
            st.session_state.purview_classification_types = _pc.get_classification_types()
        except Exception:
            pass

    # ── Inner workflow tabs ────────────────────────────────────────────────────
    wf_tab1, wf_tab2, wf_tab3 = st.tabs(
        [":material/assignment_turned_in: Approval Queue", ":material/add_circle: User Suggestion", ":material/history: Audit Log"]
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

        _suggest_perms = get_current_user_permissions()
        if not _suggest_perms.get("can_suggest", False):
            st.info("🔒 You have **read-only** access. Suggesting terms requires elevated permissions.")

        with st.form("create_suggestion_form", clear_on_submit=True):
            f_col1, f_col2 = st.columns([2, 1])
            with f_col1:
                f_physical = st.text_input("Physical Term", placeholder="e.g. CUST_LTV")
                f_term = st.text_input("Business Term *", placeholder="e.g. Customer Lifetime Value")
                f_def  = st.text_area("Definition *", placeholder="A precise business definition…", height=100)
            with f_col2:
                _manual_sources = ["Snowflake", "Manual", "AI Suggester", "Data Steward", "Business User", "Imported"]
                if _uc_on:
                    _manual_sources = ["Databricks Unity Catalog"] + _manual_sources
                f_source = st.selectbox(
                    "Source",
                    _manual_sources,
                )
                f_score = st.slider("Confidence Score", 0, 100, 80)

                # Classification dropdown — use cached Purview types if available
                _cls_options = st.session_state.get("purview_classification_types", [])
                if not _cls_options:
                    _cls_options = ["PII (Personally Identifiable Information)", "Sensitive PII", "PHI (Protected Health Information)", "Confidential", "Restricted", "Internal", "Public"]
                f_classification = st.selectbox("Classification", [""] + _cls_options, index=0, help="Select a data classification type")

            _btn_c1, _btn_c2 = st.columns([1.2, 2])
            with _btn_c1:
                submitted = st.form_submit_button("Add to Approval Queue", type="primary", use_container_width=True, disabled=not _suggest_perms.get("can_suggest", False))
            if submitted:
                if not _suggest_perms.get("can_suggest", False):
                    st.error("🔒 You do not have permission to suggest terms.")
                elif not f_term.strip() or not f_def.strip():
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
                        # Check if a same/similar term is already approved
                        _approved_existing = glossary_db.check_approved_term_exists(f_term, physical_term=f_physical)
                        if _approved_existing:
                            for _ae in _approved_existing:
                                st.warning(
                                    f"⚠️ This term or a similar term has already been approved in the glossary.\n\n"
                                    f"**Term:** {_ae.get('business_term', '')}\n\n"
                                    f"**Status:** {_ae.get('status', '')}\n\n"
                                    f"**Version:** {_ae.get('version', 1)}"
                                )
                        WorkflowManager.create_suggested_term(
                            term_name        = f_term,
                            definition       = f_def,
                            source           = f_source,
                            confidence_score = f_score,
                            physical_term    = f_physical,
                            classification   = f_classification,
                        )
                        st.success(f"✅ Term **'{f_term}'** added to the Approval Queue.")
                        st.rerun()

    # ══════════════════════════════════════════════════════════════════════════
    # TAB 1 — Approval Queue
    # ══════════════════════════════════════════════════════════════════════════
    with wf_tab1:
        # ── Header row with Clear Decided button ─────────────────────────────────
        hdr_col, recheck_col, btn_col = st.columns([2, 1, 1])
        hdr_col.markdown("#### Approval Queue")
        with recheck_col:
            if st.button("🔄 Re-check Conflicts", use_container_width=True,
                         help="Compare every pending term against the Glossary Hub again"):
                WorkflowManager.recheck_all_conflicts()
                st.rerun()
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
                    "Search Term", placeholder="Business or physical term…", key="aq_search"
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
                    if search_term.lower() in (e.get("term_name") or "").lower()
                    or search_term.lower() in (e.get("physical_term") or "").lower()
                ]

            if not filtered:
                st.info("No items match the current filter.")
            else:
                _render_approval_queue(filtered)

    # ══════════════════════════════════════════════════════════════════════════
    # TAB 3 — Audit Log
    # ══════════════════════════════════════════════════════════════════════════
    with wf_tab3:
        st.markdown("#### Audit Log — Decision History")

        decided = WorkflowManager.load_audit_log()

        # Filter audit log to show only entries from the currently connected connector
        _connectors_state = st.session_state.get('integration_connectors', {})
        _connected_sources = []
        _connector_source_map = {
            'Databricks Unity': 'Databricks Unity Catalog',
            'Microsoft Purview': 'Snowflake',
            'Collibra': 'Collibra',
            'Atlan': 'Atlan',
            'dbt Cloud': 'dbt Cloud',
            'Alation': 'Alation',
        }
        for connector_name, source_name in _connector_source_map.items():
            if _connectors_state.get(connector_name, {}).get('status') == 'Connected':
                _connected_sources.append(source_name)

        # If any connector is connected, also include AI Suggester entries
        # (AI suggestions are generated from connected connector data)
        if _connected_sources and decided:
            _allowed_sources = set(_connected_sources + ["Snowflake", "AI Suggester", "Manual", "Data Steward", "Business User", "Imported"])
            decided = [e for e in decided if e.get("source") in _allowed_sources]

        if not decided:
            st.info("No decisions have been made yet.")
        else:
            # Show all history — sorted by decision date (newest first)
            unique = sorted(decided, key=lambda x: x.get("decision_date", ""), reverse=True)

            # ── Source filter — auto-select based on active connector ─────────
            all_sources = sorted(set(e.get("source") or "Unknown" for e in unique))
            # Default to the connected connector source if only one is connected
            if len(_connected_sources) == 1 and _connected_sources[0] in all_sources:
                _default_src = _connected_sources[0]
            elif _uc_on and "Databricks Unity Catalog" in all_sources:
                _default_src = "Databricks Unity Catalog"
            else:
                _default_src = "All Sources"
            src_filter_col, tbl_filter_col, status_filter_col = st.columns([1, 1, 1])
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

            # ── Status filter ─────────────────────────────────────────────────
            all_statuses = sorted(set(e.get("status", "") for e in unique))
            with status_filter_col:
                selected_status = st.selectbox(
                    "Filter by Status",
                    ["All"] + all_statuses,
                    key="audit_status_filter",
                )

            filtered_log = unique
            if selected_table != "All Tables":
                filtered_log = [e for e in filtered_log if (e.get("table_name") or "—") == selected_table]
            if selected_status != "All":
                filtered_log = [e for e in filtered_log if e.get("status") == selected_status]

            # ── Render table-by-table ─────────────────────────────────────────
            tables_in_view = sorted(set(e.get("table_name", "") or "—" for e in filtered_log))
            for table in tables_in_view:
                table_entries = [e for e in filtered_log if (e.get("table_name") or "—") == table]
                st.markdown(
                    f"<div style='margin:16px 0 6px 0;padding:6px 14px;"
                    f"background:#F3F4F6;border-left:4px solid #6B7280;"
                    f"border-radius:4px;font-weight:600;font-size:14px;color:#374151;display:flex;align-items:center;gap:6px;'>"
                    f"📊 <strong>{table}</strong></div>",
                    unsafe_allow_html=True,
                )
                rows = []
                for sno, e in enumerate(table_entries, start=1):
                    rows.append({
                        "S.No":            sno,
                        "Physical Term":   e.get("physical_term") or "—",
                        "Business Term":   e.get("term_name"),
                        "Status":          e.get("status"),
                        "Classification":  e.get("classification", ""),
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
        '<h1 class="workbench-title">Business Lineage</h1>'
        '<p class="workbench-desc">End-to-end lineage: '
        '<strong>Source</strong> → <strong>Asset (Table)</strong> → <strong>Attribute (Column)</strong> → <strong>Business Term</strong>, '
        'with Domain ownership and confidence score.</p>'
        '</div>',
        unsafe_allow_html=True,
    )

    _connectors = st.session_state.get("integration_connectors", {})
    purview_connected = _connectors.get("Microsoft Purview", {}).get("status") == "Connected"
    databricks_connected = _connectors.get("Databricks Unity", {}).get("status") == "Connected"

    # ── Load glossary data from ALL available sources ────────────────────────
    glossary_data = {}
    _base_dir = os.path.dirname(os.path.abspath(__file__))

    # Source 1: glossary_master.json
    try:
        glossary_path = os.path.join(_base_dir, 'backend', 'glossary_master.json')
        with open(glossary_path, encoding='utf-8') as _f:
            _gm = json.load(_f)
        if isinstance(_gm, dict) and _gm:
            glossary_data = _gm
    except Exception as e:
        st.caption(f"⚠ glossary_master.json: {e}")

    # Source 2: SQLite database
    if not glossary_data:
        try:
            _db_all = glossary_db.get_active_terms()
            if _db_all:
                for rec in _db_all:
                    guid = rec.get("table_guid", "")
                    entry = {
                        "Business Term": rec.get("business_term", ""),
                        "Physical Term": rec.get("physical_term", ""),
                        "Definition / Description": rec.get("description", ""),
                        "Type": rec.get("type", "Column"),
                        "Source": rec.get("source", "AI Suggester"),
                        "Confidence (%)": rec.get("confidence", 0),
                        "Active": 1,
                        "table_name": rec.get("table_name", ""),
                        "table_guid": guid,
                    }
                    glossary_data.setdefault(guid, []).append(entry)
        except Exception as e:
            st.caption(f"⚠ SQLite: {e}")

    # Source 3: ai_suggested_terms.json
    if not glossary_data:
        try:
            _ai_path = os.path.join(_base_dir, 'backend', 'ai_suggested_terms.json')
            with open(_ai_path, encoding='utf-8') as _af:
                _ai_terms = json.load(_af)
            if isinstance(_ai_terms, list) and _ai_terms:
                for t in _ai_terms:
                    raw_table = (t.get("table_name") or "").strip()
                    safe_table = raw_table.replace(" ", "_").replace("/", "_") if raw_table else ""
                    guid = f"workflow_{safe_table.upper()}" if safe_table else f"workflow_{t.get('term_id', 'unknown')}"
                    entry = {
                        "Business Term": t.get("term_name", ""),
                        "Physical Term": t.get("physical_term", t.get("term_name", "")),
                        "Definition / Description": t.get("definition", ""),
                        "Type": t.get("term_type", "Column"),
                        "Source": t.get("source", "AI Suggester"),
                        "Confidence (%)": t.get("confidence_score", 0),
                        "Active": 1,
                        "table_name": raw_table.upper() if raw_table else "",
                        "table_guid": guid,
                    }
                    glossary_data.setdefault(guid, []).append(entry)
        except Exception as e:
            st.caption(f"⚠ ai_suggested_terms.json: {e}")

    # Source 4: approval_queue.json (approved entries)
    if not glossary_data:
        try:
            _q_path = os.path.join(_base_dir, 'backend', 'approval_queue.json')
            with open(_q_path, encoding='utf-8') as _qf:
                _queue = json.load(_qf)
            if isinstance(_queue, list):
                for t in _queue:
                    if t.get("status") in ("Approved", "Approved (Merged)", "Pending"):
                        raw_table = (t.get("table_name") or "").strip()
                        safe_table = raw_table.replace(" ", "_").replace("/", "_") if raw_table else ""
                        guid = f"workflow_{safe_table.upper()}" if safe_table else f"workflow_{t.get('term_id', 'unknown')}"
                        entry = {
                            "Business Term": t.get("term_name", ""),
                            "Physical Term": t.get("physical_term", t.get("term_name", "")),
                            "Definition / Description": t.get("definition", ""),
                            "Type": t.get("term_type", "Column"),
                            "Source": t.get("source", "AI Suggester"),
                            "Confidence (%)": t.get("confidence_score", 0),
                            "Active": 1,
                            "table_name": raw_table.upper() if raw_table else "",
                            "table_guid": guid,
                        }
                        glossary_data.setdefault(guid, []).append(entry)
        except Exception as e:
            st.caption(f"⚠ approval_queue.json: {e}")

    # ── Flatten to unique business terms ─────────────────────────────────────
    # Only include terms with Active status (Approved/Approved (Merged)) from DB
    _active_db_terms = glossary_db.get_active_glossary_terms_for_lineage()

    all_terms: dict = {}
    for term_entries in glossary_data.values():
        for entry in term_entries:
            if entry.get("Active", 0) == 1:
                bt = entry.get("Business Term", "")
                if bt:
                    # If we have DB active terms, filter to only those
                    if _active_db_terms and bt not in _active_db_terms:
                        continue
                    all_terms.setdefault(bt, []).append(entry)

    # Apply connector filter only when Databricks-only (Purview shows all)
    if databricks_connected and not purview_connected:
        all_terms = {
            bt: [e for e in ents if e.get("Source", "") == "Databricks Unity Catalog"]
            for bt, ents in all_terms.items()
        }
        all_terms = {bt: ents for bt, ents in all_terms.items() if ents}

    if not all_terms:
        st.warning(
            "No active glossary terms available. "
            "Approve terms in **Review & Approval** to see them here, or "
            "connect **Microsoft Purview** or **Databricks Unity** in **Integrations & API**."
        )
        if st.button("Go to Integrations & API", key="lin_goto_int"):
            st.session_state.selected_tab = "Integrations & API"
            st.rerun()
        return

    # ── Term selector (Active glossary terms only) ──────────────────────────
    term_list = sorted(all_terms.keys())
    selected_term = st.selectbox(
        "Select Active Glossary Term",
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

    for entry in entries:
        raw_src = entry.get("Source", "Unknown")
        tbl     = entry.get("table_name", "unknown")
        phys    = entry.get("Physical Term", "")
        etype   = entry.get("Type", "Column")
        dom     = _infer_domain(tbl, raw_src)
        conf    = entry.get("Confidence (%)", 0)

        # Display source: show asset system source (Snowflake / Databricks Unity)
        if databricks_connected and not purview_connected:
            src = "Databricks Unity Catalog"
        else:
            src = "Snowflake"

        src_id = _safe_mermaid_id(f"SRC_{src}")
        tbl_id = _safe_mermaid_id(f"TBL_{tbl}")
        col_id = _safe_mermaid_id(f"COL_{tbl}_{phys}")
        dom_id = _safe_mermaid_id(f"DOM_{dom}")

        # Source node
        if src_id not in seen_src:
            seen_src[src_id] = src
            if "databricks" in src.lower():
                icon, cls = "🔷", "source"
            else:  # Snowflake
                icon, cls = "❄️", "source"
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

    mermaid_lineage = '\n'.join(lines)

    # ── Render: Business Lineage diagram ──────────────────────────────────────
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
                st.session_state.purview_search_results = []
                st.session_state.purview_search_attempted = True
                st.session_state.purview_search_no_results = False
                connector = PurviewConnector(
                    st.session_state.connector_creds['purview_account_name'],
                    st.session_state.connector_creds['purview_tenant_id'],
                    st.session_state.connector_creds['purview_client_id'],
                    st.session_state.connector_creds['purview_client_secret'],
                )
                try:
                    url = f"https://{st.session_state.connector_creds['purview_account_name']}.purview.azure.com/datamap/api/search/query"
                    # Purview returns at most 100 results per page, ranked across every kind of asset.
                    # "All" therefore asks for tables only, and every source type reads all pages,
                    # so no source's tables are cut off by other sources ranking higher.
                    payload = {"keywords": f"{search_query}*", "limit": 100,
                               "filter": ({"entityType": source_type_options[selected_source_type]}
                                          if selected_source_type != "All" else {"objectType": "Tables"})}
                    connector.authenticate()
                    import requests as _req
                    raw_results = []
                    for _page in range(20):   # up to 2,000 assets
                        r = _req.post(url, headers=connector._headers(), params={"api-version": "2023-09-01"},
                                      json=payload, timeout=30)
                        if r.status_code != 200:
                            break
                        raw_results += r.json().get('value', [])
                        _token = r.json().get('continuationToken')
                        if not _token:
                            break
                        payload["continuationToken"] = _token
                    if r.status_code == 200:
                        filtered_results = [res for res in raw_results if res.get('name', '').lower().startswith(search_query.lower())]
                        # Without a type filter Purview also returns glossary terms, schemas, etc. — keep tables/views
                        filtered_results = [res for res in filtered_results
                                            if any(k in (res.get('entityType') or '').lower() for k in ('table', 'view'))]
                        if not st.session_state.get('purview_collections'):
                            try:
                                st.session_state.purview_collections = connector.get_collections() or []
                            except Exception:
                                pass
                        # Apply the Collection filter (the search request only filters by source type)
                        _sel_coll = st.session_state.perm_cache.get('search_collection', 'All Collections')
                        if _sel_coll != 'All Collections':
                            _coll_ids = {c.get('name') for c in st.session_state.get('purview_collections', [])
                                         if (c.get('friendlyName') or c.get('name')) == _sel_coll}
                            filtered_results = [res for res in filtered_results if res.get('collectionId') in _coll_ids]
                        st.session_state.purview_search_results = filtered_results
                        if not filtered_results:
                            st.session_state.purview_search_no_results = True
                    else:
                        # Show Purview's reason instead of a misleading "no matching assets"
                        st.session_state.purview_search_attempted = False
                        st.error(f"Purview search failed (HTTP {r.status_code}): {r.text[:300]}")
                except Exception as e:
                    st.error(str(e))
            st.markdown('</div>', unsafe_allow_html=True)

        if st.session_state.get("purview_search_attempted", False) and not st.session_state.get("purview_search_results"):
            st.warning("No matching assets found. Try a different keyword or source type.")

        if st.session_state.purview_search_results:
            st.markdown("### Search Results")
            results_df = pd.DataFrame(st.session_state.purview_search_results)
            saved_ids = st.session_state.perm_cache.get('selected_table_ids', [])

            # Use individual checkboxes for clear single-click selection
            current_selected = []
            with st.container(key="asset_search_results"):
                result_panel, _ = st.columns([0.72, 0.28])
                with result_panel:
                    for idx, row in results_df.iterrows():
                        qname = row.get('qualifiedName', '')
                        col_cb, col_name, col_type = st.columns([0.28, 2.7, 1.4], gap="small")
                        with col_cb:
                            checked = qname in saved_ids
                            if st.button(
                                " ",
                                key=f"search_sel_{idx}",
                                icon=f":material/{'check_box' if checked else 'check_box_outline_blank'}:",
                                type="primary" if checked else "secondary",
                            ):
                                updated_ids = list(saved_ids)
                                if checked:
                                    updated_ids.remove(qname)
                                else:
                                    updated_ids.append(qname)
                                st.session_state.perm_cache['selected_table_ids'] = updated_ids
                                st.rerun()
                        with col_name:
                            st.markdown(f"**{row.get('name', '')}**")
                        with col_type:
                            st.caption(_source_type_label(row.get('entityType', '')))
                        if checked:
                            current_selected.append(qname)

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
                        "source_type": _source_type_label(table.get('entityType')),
                    }
                st.markdown(
                    '<div class="asset-fetch-success">Schemas fetched successfully.</div>',
                    unsafe_allow_html=True,
                )

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
            st.session_state.uc_search_results = []
            st.session_state.uc_search_no_results = False
            with st.spinner("Loading tables…"):
                tables, tbl_err = _db_conn.search_tables(sel_cat, sel_sch, uc_keyword)
            if tbl_err:
                st.error(f"Could not list tables: {tbl_err}")
            else:
                st.session_state.uc_search_results = tables
                if not tables:
                    st.session_state.uc_search_no_results = True

        if st.session_state.get("uc_search_no_results", False):
            st.warning("No matching assets found in the selected catalog and schema.")

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
                            "source_type": "Databricks",
                            "catalog": row["catalog_name"],
                            "schema": row["schema_name"],
                        }
                if st.session_state.tables_metadata:
                    st.success(f"Schemas fetched for {len(st.session_state.tables_metadata)} table(s).")

    # ══════════════════════════════════════════════════════════════════════════
    # DETECTED SCHEMAS  (shared by both sources)
    # ══════════════════════════════════════════════════════════════════════════
    if st.session_state.get('tables_metadata'):
        st.markdown("### Detected Schemas")
        for tid, meta in st.session_state.tables_metadata.items():
            src_badge = meta.get("source_type") or ("Databricks" if meta.get("source") == "databricks" else "Purview")
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

# "Information to Generate" option → (queue field, AI response keys that carry it)
_GEN_OPTION_FIELDS = {
    "Business Term":       ("term_name",      ("name",)),
    "Business Definition": ("definition",     ("description", "definition")),
    "Classifications":     ("classification", ("classification", "tags", "governance_tags")),
}

# Purview entity type → the "Source Type" name used in Asset Search
_SOURCE_TYPE_LABELS = {
    "azure_sql_table": "Azure SQL", "snowflake_table": "Snowflake", "oracle_table": "Oracle",
    "databricks_table": "Databricks", "fabric_lakehouse_table": "Fabric", "Table": "Generic Table",
}


def _source_type_label(entity_type):
    return _SOURCE_TYPE_LABELS.get(entity_type or "", entity_type or "")


def _asset_location(qualified_name):
    """Readable 'DATABASE.SCHEMA' part of a Purview qualified name, to tell same-named tables apart."""
    qn = str(qualified_name or "")
    m = re.search(r"/databases/([^/]+)/schemas/([^/]+)/tables/", qn)
    if m:
        return f"{m.group(1)}.{m.group(2)}"
    parts = [p for p in qn.split("://", 1)[-1].split("/") if p]
    return ".".join(parts[1:-1]) if len(parts) > 2 else ""


def _cell_str(row, *cols):
    """First non-empty, non-NaN value among the given columns of a row, as a stripped string."""
    for c in cols:
        v = row.get(c)
        if v is None or pd.isna(v):
            continue
        s = str(v).strip()
        if s:
            return s
    return ""

def render_glossary_tab():
    render_dashboard_header("Glossary AI")
    st.markdown('<div class="workbench-header"><div class="accent-line"></div><h1 class="workbench-title">Glossary AI</h1><p class="workbench-desc">AI-powered generation of formal Business terms and definitions</p></div>', unsafe_allow_html=True)
    
    _has_metadata = bool(st.session_state.get('tables_metadata'))
    _has_generated = st.session_state.get('glossary_df') is not None

    if not _has_metadata and not _has_generated:
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

    if _has_metadata:
        col_ctx, col_opt = st.columns([2, 1])
        with col_ctx:
            st.markdown('<div class="metric-card">', unsafe_allow_html=True)
            # Use a persistent key 'biz_ctx_input'
            st.text_area("Business Context / Requirements (AI Training)", key="biz_ctx", height=100)

            opt_list = ["Business Term", "Business Definition", "Classifications"]
            # Filter default to only valid options
            safe_defaults = [o for o in st.session_state.perm_cache['glossary_options'] if o in opt_list]
            st.multiselect("Information to Generate", opt_list, default=safe_defaults, key="glossary_options_box", on_change=update_cache, args=("glossary_options", "glossary_options_box"))
            st.markdown('</div>', unsafe_allow_html=True)
        with col_opt:
            st.markdown('<div class="metric-card">', unsafe_allow_html=True)
            ind_list = ["General", "Finance", "Healthcare", "Retail", "Energy"]
            ind_idx = ind_list.index(st.session_state.perm_cache['glossary_industry']) if st.session_state.perm_cache['glossary_industry'] in ind_list else 0
            st.selectbox("Domain", ind_list, index=ind_idx, key="glossary_industry_box", on_change=update_cache, args=("glossary_industry", "glossary_industry_box"))
            st.markdown('</div>', unsafe_allow_html=True)
            
            # Sync to internal vars for generation from anchor cache
            st.session_state.industry = st.session_state.perm_cache['glossary_industry']
            st.session_state.ai_options = st.session_state.perm_cache['glossary_options']
        
        selected_asset_names = [m['name'] for m in st.session_state.tables_metadata.values()]
        st.markdown("**Currently Processing Assets:**")
        for _asset_name in selected_asset_names:
            st.markdown(f"- `{_asset_name}`")

        # New AI Suggestion button in this tab
        _ai_perms = get_current_user_permissions()
        _can_suggest = _ai_perms.get("can_suggest", False)
        if st.button("AI Suggestion", type="primary", disabled=not _can_suggest, help="🔒 No permission to generate suggestions" if not _can_suggest else None):
                # Generate all recommendations via Gemini
                all_s = []
                industry = st.session_state.get('industry', 'General')
                options = st.session_state.get('ai_options', ["Business Term", "Business Definition"])
                
                # Use cached Purview classification types if available
                _purview_cls_types = st.session_state.get("purview_classification_types", [])

                for tid, meta in st.session_state.tables_metadata.items():
                    suggestions = generate_glossary_suggestions(meta['name'], meta['columns'], industry=industry, business_context=st.session_state.get('biz_ctx', ""), selected_options=options, purview_classifications=_purview_cls_types)
                    # Drop columns the AI invented — only the table's real schema can be registered back
                    _real_cols = {str(c).strip().lower(): c for c in meta['columns']}
                    suggestions = [
                        s for s in suggestions
                        if s.get('type') == 'Table' or str(s.get('related_column', '')).strip().lower() in _real_cols
                    ]
                    for s in suggestions:
                        if s.get('type') != 'Table':
                            s['related_column'] = _real_cols[str(s['related_column']).strip().lower()]
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
                        # Keep only the information the user chose to generate
                        if 'definition' in s and 'description' not in s:
                            s['description'] = s.pop('definition')
                        for _opt, (_field, _keys) in _GEN_OPTION_FIELDS.items():
                            if _opt not in options:
                                for _k in _keys:
                                    s.pop(_k, None)
                    all_s.extend(suggestions)
                
                # Apply Automated Governance Rules (Deterministic Regex/Keyword matching) — classification only
                if "Classifications" in options:
                    all_s = GovernanceEngine.process_suggestions(all_s)
                
                st.session_state.glossary_suggestions = all_s
                st.session_state.glossary_generated_fields = [
                    _field for _opt, (_field, _) in _GEN_OPTION_FIELDS.items() if _opt in options
                ]
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
                    # A selected field always gets a column, even if the AI left it out
                    for _opt, _col in (("Business Term", "Business Term"), ("Business Definition", "Description"),
                                       ("Classifications", "Classification")):
                        if _opt in options and _col not in st.session_state.glossary_df.columns:
                            st.session_state.glossary_df[_col] = ""
                    
                    # Reorder according to request: Select first, Confidence last, others in between.
                    # Explicitly exclude the internal GUID columns as requested in the image.
                    desired_cols = ['Select', 'Status', 'Type', 'Physical Term', 'Business Term', 'Description', 'Classification', 'Governance Tags', 'Confidence (%)']
                    actual_cols = [c for c in desired_cols if c in st.session_state.glossary_df.columns]
                    
                    # Internal columns to keep but hide (for processing)
                    internal_cols = ['table_guid', 'entity_guid', 'table_name', 'related_column'] 
                    
                    st.session_state.glossary_df = st.session_state.glossary_df[actual_cols + [c for c in internal_cols if c in st.session_state.glossary_df.columns]]
                    
                    st.session_state.glossary_df_version = st.session_state.get('glossary_df_version', 0) + 1
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
                f"<div style='margin:18px 0 0 0;padding:9px 14px;"
                f"background:#F3F4F6;color:#374151;"
                f"border-radius:6px 6px 0 0;font-weight:700;font-size:14px;'>📋 {label}</div>",
                unsafe_allow_html=True,
            )

            prev_state = {i: bool(full_df.at[i, 'Select']) for i in tbl_idx}
            _ver = st.session_state.get('glossary_df_version', 0)
            edited = st.data_editor(
                full_df.loc[tbl_idx],
                key=f"gloss_ed_{label}_v{_ver}",
                hide_index=True,
                use_container_width=True,
                column_config=_col_config,
                column_order=actual_visible,
            )
            # Compare only user-editable columns to avoid false positives from dtype diffs
            _cmp_cols = [c for c in actual_visible if c in edited.columns]
            _edited_cmp = edited[_cmp_cols].reset_index(drop=True)
            _orig_cmp = full_df.loc[tbl_idx, _cmp_cols].reset_index(drop=True)
            if not _edited_cmp.equals(_orig_cmp):
                for i, row in edited.iterrows():
                    if row['Select']:
                        edited.at[i, 'Status'] = 'Accepted'
                    else:
                        if edited.at[i, 'Status'] == 'Accepted':
                            edited.at[i, 'Status'] = 'Pending'
                        if prev_state.get(i, False) and not row['Select']:
                            term_name = _cell_str(row, 'Business Term', 'Original Name', 'Physical Term', 'related_column')
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
        if st.button("Send to Approval Queue", use_container_width=False, disabled=not _can_suggest, help="🔒 No permission" if not _can_suggest else "Route selected AI terms through the Review & Approval workflow before publishing to the Glossary Hub"):
            selected_df = st.session_state.glossary_df[st.session_state.glossary_df['Select'] == True]
            if selected_df.empty:
                st.warning("Please select at least one term to send to the Approval Queue.")
            else:
                # Clear previous batch of the same source before adding the new one
                _any_uc_rows = any(
                    st.session_state.get('tables_metadata', {}).get(str(row.get("table_guid", "")), {}).get("source") == "databricks"
                    for _, row in selected_df.iterrows()
                )
                _clear_src = "Databricks Unity Catalog" if _any_uc_rows else "MS Purview"
                WorkflowManager.clear_ai_pending_from_queue(source=_clear_src)
                WorkflowManager.clear_ai_suggested_terms(source=_clear_src)
                queued_count = 0
                for _, row in selected_df.iterrows():
                    physical_term = _cell_str(row, "Physical Term", "related_column")
                    biz_term      = _cell_str(row, "Business Term", "Original Name")
                    definition    = _cell_str(row, "Description", "Definition / Description")
                    _raw_score    = row.get("Confidence (%)", 80)
                    score         = int(_raw_score) if _raw_score is not None and str(_raw_score) not in ('nan', '') else 80
                    term_type     = _cell_str(row, "Type") or "Column"
                    classification = _cell_str(row, "Classification")
                    # Only the fields chosen under "Information to Generate"; the rest are stored as NULL
                    _suggested_fields = st.session_state.get("glossary_generated_fields") or [
                        f for f, c in (("term_name", "Business Term"), ("definition", "Description"),
                                       ("classification", "Classification")) if c in selected_df.columns]
                    # Business Term is absent when only e.g. Classifications were generated — fall back to the physical name
                    term_name     = biz_term or physical_term
                    if term_name:
                        # Detect whether the term came from a Databricks Unity Catalog table
                        _tbl_meta = st.session_state.get('tables_metadata', {}).get(str(row.get("table_guid", "")), {})
                        _src = "Databricks Unity Catalog" if _tbl_meta.get("source") == "databricks" else "MS Purview"
                        WorkflowManager.create_suggested_term(
                            term_name        = term_name,
                            definition       = definition,
                            source           = _src,
                            confidence_score = score,
                            table_name       = str(row.get("table_name", "") or ""),
                            term_type        = term_type,
                            physical_term    = physical_term,
                            classification   = classification,
                            suggested_fields = _suggested_fields,
                            source_type          = _tbl_meta.get("source_type", ""),
                            table_qualified_name = _tbl_meta.get("qualifiedName", ""),
                            # tables_metadata is keyed by the Purview table entity GUID
                            table_entity_guid    = str(row.get("table_guid", "") or "") if _tbl_meta.get("source") == "purview" else "",
                        )
                        queued_count += 1
                if queued_count:
                    st.success(f"✅ {queued_count} term(s) sent to Review & Approval queue.")
                    st.session_state.selected_tab = "Review & Approval"
                    st.rerun()
                else:
                    st.warning("No valid terms found in selection.")

_HUB_INFO_OPTIONS = ["Business Term", "Description", "Classification"]
_HUB_INFO_ICONS   = {"Business Term": "🏷️", "Description": "📝", "Classification": "🛡️"}


def _hub_info_selector():
    """'Information to Display & Register' picker for the Glossary Hub; returns the selected fields."""
    st.markdown(
        "<div style='font-size:12px;font-weight:700;color:#6B7280;text-transform:uppercase;"
        "letter-spacing:.05em;margin:2px 0 4px 0;'>Information to Display &amp; Register</div>",
        unsafe_allow_html=True,
    )
    picked = st.pills(
        "Information to Display & Register",
        _HUB_INFO_OPTIONS,
        selection_mode="multi",
        default=_HUB_INFO_OPTIONS,
        format_func=lambda o: f"{_HUB_INFO_ICONS[o]} {o}",
        key="hub_info_fields",
        label_visibility="collapsed",
    ) or []
    if not picked:
        st.caption("Select at least one field to display and register.")
    return [o for o in _HUB_INFO_OPTIONS if o in picked]


def _hub_register_help(count, platform_name, info_fields, can_register):
    """Tooltip for the Register button — the details stay off the button itself."""
    if not can_register:
        return "🔒 No permission"
    if not platform_name:
        return "No integration connected — go to Integrations & API"
    if not info_fields:
        return "Select the information to register"
    if not count:
        return "Select at least 1 term to register"
    return f"Register {count} term(s) to {platform_name}: " + ", ".join(info_fields)


def _hub_prepare_df(df):
    """Show the Asset Search source type in 'Source' and keep the table location for grouping."""
    df = df.rename(columns={"Source Type": "source_type"})
    if "source_type" in df.columns:
        st_vals = df["source_type"].fillna("").astype(str).str.strip()
        df["Source"] = st_vals.where(st_vals != "", df["Source"] if "Source" in df.columns else "")
    return df


def _hub_table_groups(df):
    """Group label per row: table name, plus database/schema when known (same-named tables stay apart)."""
    names = df["table_name"].fillna("—").apply(lambda x: str(x) if x else "—")
    if "table_qualified_name" not in df.columns:
        return names
    locs = df["table_qualified_name"].apply(_asset_location)
    return [f"{n}  ·  📍 {l}" if l else n for n, l in zip(names, locs)]


def _resolve_purview_target(connector, row, cache):
    """
    Purview entity GUID a Glossary Hub row registers to: the column, or the table itself
    for table-level terms. Raises with a readable reason when it can't be found, so a
    failed lookup is never reported as registered.
    """
    physical   = _cell_str(row, "Physical Term", "Original Name", "physical_term")
    table_name = _cell_str(row, "table_name") or re.sub(r"^workflow_", "", _cell_str(row, "table_guid"), flags=re.I)
    qualified  = _cell_str(row, "table_qualified_name")

    def _columns(table_guid):
        if ("cols", table_guid) not in cache:
            cache[("cols", table_guid)] = connector.get_table_columns_with_guids(table_guid) or {}
        return cache[("cols", table_guid)]

    is_table_row = _cell_str(row, "Type").lower() == "table" or physical.upper() == table_name.upper()
    resolved_key = ("resolved", table_name.upper(), qualified)
    table_guid = _cell_str(row, "table_entity_guid")
    if table_guid:
        # The row may have been discovered in another Purview account; its GUID only
        # counts if it exists in the account we are registering to now.
        if ("exists", table_guid) not in cache:
            cache[("exists", table_guid)] = bool((connector.get_entity(table_guid) or {}).get("entity"))
        if not cache[("exists", table_guid)]:
            table_guid = ""
    if not table_guid:
        if ("search", table_name.upper()) not in cache:
            cache[("search", table_name.upper())] = connector.find_tables_by_name(table_name)
        candidates = cache[("search", table_name.upper())]
        if qualified:
            candidates = [t for t in candidates if t["qualifiedName"] == qualified]
        if not candidates:
            raise Exception(f"table {table_name} was not found in Purview")
        if len(candidates) > 1:
            locs = ", ".join(_asset_location(t["qualifiedName"]) or t["qualifiedName"] for t in candidates)
            if is_table_row:
                # Use the table this batch's columns resolved to, when that is a single one
                seen = cache.get(resolved_key, set())
                candidates = [t for t in candidates if t["id"] in seen] if len(seen) == 1 else candidates
            else:
                # Same-named tables in different databases: keep the one that has this column
                with_col = [t for t in candidates
                            if any(n.strip().lower() == physical.lower() for n in _columns(t["id"]))]
                if not with_col:
                    raise Exception(f"column {physical} was not found on any of the {len(candidates)} "
                                    f"tables named {table_name} in Purview ({locs})")
                candidates = with_col
            if len(candidates) > 1:
                raise Exception(f"{len(candidates)} tables named {table_name} exist in Purview ({locs}). "
                                "Select the table in Asset Search and send it through approval again.")
        table_guid = candidates[0]["id"]
    if not is_table_row:
        cache.setdefault(resolved_key, set()).add(table_guid)

    if is_table_row:
        cache[("table_of", table_guid)] = table_guid
        return table_guid
    col_guid = next((g for n, g in _columns(table_guid).items() if n.strip().lower() == physical.lower()), None)
    if not col_guid:
        raise Exception(f"column {physical} was not found on table {table_name} in Purview")
    # Unified Catalog links terms to the table's data asset, so remember the column's table
    cache[("table_of", col_guid)] = table_guid
    return col_guid


def _purview_connector():
    """Authenticated Purview connector for the active credentials. Raises on failure."""
    creds    = st.session_state.get("connector_creds", {})
    _sec_pur = st.secrets.get("purview", {})
    # Credentials entered in Integrations win as a full set; secrets are only the default.
    # Never mix fields from the two, or one tenant's IDs would be sent with another's secret.
    _fields = ("account_name", "tenant_id", "client_id", "client_secret")
    if any(creds.get(f"purview_{f}") for f in _fields):
        account_name, tenant_id, client_id, client_secret = (creds.get(f"purview_{f}", "") for f in _fields)
    else:
        account_name, tenant_id, client_id, client_secret = (_sec_pur.get(f, "") for f in _fields)
    if not all([account_name, tenant_id, client_id, client_secret]):
        raise Exception("Failed to connect to Microsoft Purview API: Purview connection credentials missing.")
    try:
        connector = PurviewConnector(account_name, tenant_id, client_id, client_secret)
        ok, auth_msg = connector.authenticate()
        if not ok:
            raise Exception(auth_msg)
    except Exception as e:
        raise Exception(f"Failed to connect to Microsoft Purview API: {e}")
    return connector


def _purview_governance_domains():
    """Governance domains of the connected Purview account, cached per account for the session.
    → (domains, error); domains is [] when Unified Catalog isn't available."""
    try:
        connector = _purview_connector()
    except Exception as e:
        return [], str(e)
    key = f"_pv_domains_{connector.account_name.lower()}"
    if key not in st.session_state:
        try:
            st.session_state[key] = (connector.get_governance_domains(), "")
        except Exception as e:
            return [], str(e)
    return st.session_state[key]


def _purview_session():
    """Authenticated Purview connector and its first glossary → (connector, glossary_guid, glossary_name). Raises on failure."""
    connector = _purview_connector()
    account_name = connector.account_name
    try:
        glossaries = connector.get_glossaries()
    except Exception as e:
        raise Exception(f"Failed to connect to Microsoft Purview API: {e}")
    if isinstance(glossaries, list) and glossaries:
        glossary_guid, glossary_name = glossaries[0].get("guid", ""), glossaries[0].get("name", "")
    elif isinstance(glossaries, dict):
        glossary_guid, glossary_name = glossaries.get("guid", ""), glossaries.get("name", "")
    else:
        glossary_guid, glossary_name = "", ""
    if not glossary_guid:
        raise Exception(f"Connected to Purview account '{account_name}', but no active Glossary was found in Purview.")
    return connector, glossary_guid, glossary_name


def _hub_ordered_rows(rows_df):
    # Column rows first, so a table-level row can reuse the table they resolved to
    return sorted((r for _, r in rows_df.iterrows()), key=lambda r: _cell_str(r, "Type").lower() == "table")


def _register_rows_to_purview(rows_df, info_fields, selected_guid=None, mode="insert",
                              domain=None, term_status="PUBLISHED", owners=None):
    """
    Register Glossary Hub rows to Microsoft Purview, sending only `info_fields`:
      Business Term  → with `domain` ({id, name}): create/reuse the term in that governance domain
                       (Unified Catalog) and link it to the row's table data asset.
                       Without `domain`: classic Data Map glossary term assigned to the column.
      Description    → term definition when Business Term is sent, otherwise the column's description
      Classification → classification on the column
    mode="insert" adds alongside what the column already has (existing descriptions are kept);
    mode="update" replaces it: other classic terms are unassigned from the column, other
    classifications removed and descriptions overwritten. Governance-domain links are never
    removed, because they sit on the table and are shared by its columns.
    Returns (ok: bool, message_html: str).
    """
    try:
        if domain:
            connector = _purview_connector()
            glossary_guid, glossary_name = None, None
        else:
            connector, glossary_guid, glossary_name = _purview_session()
    except Exception as e:
        return False, str(e)
    replace = mode == "update"
    domain_terms = {}   # term name (lower) → Unified Catalog term dict
    uc_assets = {}      # Data Map table GUID → Unified Catalog data asset id

    send_term = "Business Term" in info_fields
    send_desc = "Description" in info_fields
    send_cls  = "Classification" in info_fields
    registered, skipped, errors = 0, [], []
    counts = {"Business Term": 0, "Description": 0, "Classification": 0}

    lookup_cache = {}
    kept_desc, removed = [], {"terms": 0, "classifications": 0}
    on_column = {"domain": 0, "classic": 0}
    classic = {"guid": glossary_guid}

    def _classic_assign(term_name, term_desc, entity_guid):
        """Create/reuse a classic glossary term and assign it to the column (or table). → term GUID"""
        if not classic["guid"]:
            gl = connector.get_glossaries()
            gl = gl[0] if isinstance(gl, list) and gl else gl if isinstance(gl, dict) else {}
            classic["guid"] = gl.get("guid")
            if not classic["guid"]:
                raise Exception("no classic glossary exists in this Purview account to put the term on the column")
        existing = connector.get_term_by_name(term_name, glossary_guid=classic["guid"])
        if existing:
            # Insert never overwrites an existing term's definition; Update does
            if replace and term_desc is not None:
                connector.update_glossary_term(existing, term_name, term_desc, classic["guid"])
            guid = existing
        else:
            result = connector.create_glossary_term(term_name, term_desc or "", classic["guid"])
            guid = result.get("guid") if isinstance(result, dict) else None
        if not guid:
            raise Exception("Purview did not return a glossary term id")
        if not connector.assign_term_to_entity(guid, entity_guid):
            raise Exception(f"putting the term on the column was rejected — {connector.last_error}")
        if replace:
            # Unassign the column's previous classic terms (the glossary terms themselves are kept)
            for old in connector.get_entity_glossary_state(entity_guid)["terms"]:
                if old["guid"] and old["guid"] != guid:
                    connector.unassign_term_from_entity(old["guid"], entity_guid)
                    removed["terms"] += 1
        return guid

    ordered = _hub_ordered_rows(rows_df)
    with st.spinner(f"Registering {len(rows_df)} term(s) to Microsoft Purview…"):
        for row in ordered:
            term_name      = _cell_str(row, "Business Term", "Glossary Term", "business_term") if send_term else ""
            definition     = _cell_str(row, "Description", "Definition / Description", "description") if send_desc else ""
            classification = _cell_str(row, "Classification") if send_cls else ""
            physical_term  = _cell_str(row, "Physical Term", "Original Name", "physical_term")
            _tbl_guid      = _cell_str(row, "table_guid") or str(selected_guid or "")
            label          = term_name or physical_term
            if not (term_name or definition or classification):
                skipped.append(physical_term or "—")
                continue

            try:
                purview_entity_guid = _resolve_purview_target(connector, row, lookup_cache)
                sent = []

                final_term_guid = None
                if term_name and domain:
                    # Governance-domain term (Unified Catalog), linked to the table's data asset
                    term_desc = definition if send_desc else None
                    key = term_name.strip().lower()
                    if key not in domain_terms:
                        domain_terms[key] = connector.find_domain_term(term_name, domain["id"])
                    term = domain_terms[key]
                    if term:
                        # Insert never overwrites an existing term's definition or owners; Update does.
                        # Insert still adds the owner to a term that has none.
                        cur_owners = (term.get("contacts") or {}).get("owner") or []
                        new_desc = term_desc if (replace and term_desc is not None
                                                 and term_desc != (term.get("description") or "")) else None
                        new_owners = owners if owners and (
                            (replace and {o["id"] for o in cur_owners} != {o["id"] for o in owners})
                            or not cur_owners) else None
                        if new_desc is not None or new_owners is not None:
                            term = domain_terms[key] = connector.update_domain_term(term, new_desc, new_owners)
                    else:
                        term = domain_terms[key] = connector.create_domain_term(
                            term_name, term_desc or "", domain["id"], status=term_status, owners=owners)
                    final_term_guid = term.get("id")
                    if not final_term_guid:
                        raise Exception("Purview did not return a term id")
                    table_guid = lookup_cache.get(("table_of", purview_entity_guid), purview_entity_guid)
                    if table_guid not in uc_assets:
                        uc_assets[table_guid] = connector.get_uc_asset_id(table_guid)
                    if not uc_assets[table_guid]:
                        raise Exception(f"table {_cell_str(row, 'table_name')} is not a data asset in the Unified Catalog yet")
                    note = "" if table_guid == purview_entity_guid else f"Column: {physical_term}"
                    if not connector.link_domain_term_to_asset(final_term_guid, uc_assets[table_guid], note):
                        raise Exception(f"linking the term to {_cell_str(row, 'table_name')} was rejected — {connector.last_error}")
                    # Put the term on the column itself (the asset's Schema tab). Tenants with asset
                    # curation keep a domain-term link on the column; others only show classic terms
                    # there, so the classic glossary carries it.
                    is_column = table_guid != purview_entity_guid
                    if is_column and connector.link_domain_term_to_column(final_term_guid, purview_entity_guid, note):
                        on_column["domain"] += 1
                    else:
                        _classic_assign(term_name, term_desc, purview_entity_guid)
                        on_column["classic"] += 1
                    sent.append("Business Term")
                elif term_name:
                    # Description=None keeps whatever description the term already has in Purview
                    final_term_guid = _classic_assign(term_name, definition if send_desc else None, purview_entity_guid)
                    sent.append("Business Term")
                if definition:
                    # The description also goes on the column itself, so it shows on the asset's
                    # Schema tab (with a business term it is the term's definition as well).
                    # A column holds one description: Insert keeps an existing one, Update replaces it.
                    current_desc = connector.get_entity_glossary_state(purview_entity_guid)["description"]
                    if current_desc == definition:
                        sent.append("Description")
                    elif replace or not current_desc:
                        connector.update_entity_description(purview_entity_guid, definition)
                        sent.append("Description")
                    else:
                        kept_desc.append(physical_term)
                        if term_name:
                            sent.append("Description")   # still sent as the term's definition

                if classification:
                    if not connector.add_classification_to_entity(purview_entity_guid, classification):
                        raise Exception(f"classification '{classification}' was rejected — {connector.last_error}")
                    if replace:
                        for old in connector.get_entity_glossary_state(purview_entity_guid)["classifications"]:
                            if old != classification:
                                if not connector.remove_classification_from_entity(purview_entity_guid, old):
                                    raise Exception(f"removing old classification '{old}' was rejected — {connector.last_error}")
                                removed["classifications"] += 1
                    sent.append("Classification")

                for f in sent:
                    counts[f] += 1
                glossary_db.mark_term_registered(_tbl_guid, physical_term, term_name or None, entity_guid=final_term_guid)
                WorkflowManager._update_audit_log_status(label, "Registered", approver_comment="Registered back to Purview")
                registered += 1
            except Exception as e:
                print(f"Purview registration error for {label}: {e}")
                errors.append(f"Term '{label}': Purview registration failed — {e}")

    WorkflowManager._rebuild_master_from_audit_log()
    if errors:
        head = f"Registered {registered} term(s); {len(errors)} failed and were not marked Registered:"
        return False, "<br>".join([head] + [_html.escape(e) for e in errors])
    if domain:
        g_info = f" in governance domain '<b>{_html.escape(domain['name'])}</b>'"
        if on_column["domain"] or on_column["classic"]:
            g_info += (f". Terms put on columns: {on_column['domain']} as domain terms, "
                       f"{on_column['classic']} through the classic glossary")
    elif glossary_name:
        g_info = f" in Purview Glossary '<b>{_html.escape(glossary_name)}</b>'"
    else:
        g_info = " in Microsoft Purview"
    sent = " · ".join(f"{counts[f]} {f.lower()}{'s' if counts[f] != 1 else ''}"
                      for f in info_fields if counts[f])
    msg = f"Successfully registered {registered} term(s){g_info}." + (f"<br>Sent: {sent}" if sent else "")
    if replace and (removed["terms"] or removed["classifications"]):
        msg += (f"<br>Replaced: {removed['terms']} old term assignment(s) and "
                f"{removed['classifications']} old classification(s) removed")
    if kept_desc:
        msg += (f"<br>Kept the existing column description (Insert doesn't overwrite; use Update) for: "
                f"{_html.escape(', '.join(kept_desc))}")
    if skipped:
        msg += f"<br>Skipped {len(skipped)} (no selected information to send): {_html.escape(', '.join(skipped))}"
    return True, msg


def _hub_finish_register(rows_df, info_fields, msg_key, selected_guid, mode, domain=None, term_status="PUBLISHED",
                         owners=None):
    st.session_state[msg_key] = _register_rows_to_purview(rows_df, info_fields, selected_guid, mode=mode,
                                                          domain=domain, term_status=term_status, owners=owners)
    ok = st.session_state[msg_key][0]
    st.toast("Registered to Microsoft Purview" if ok else "Registration finished with errors")


def _hub_start_register(rows_df, info_fields, msg_key, selected_guid=None):
    """Register button: open the Insert / Update dialog right away."""
    st.session_state["_hub_pending_register"] = {
        "rows": rows_df, "fields": info_fields, "msg_key": msg_key, "selected_guid": selected_guid,
    }
    _hub_register_dialog()


def _hub_cancel_register():
    st.session_state.pop("_hub_pending_register", None)


@st.dialog("Register to Microsoft Purview", width="large", on_dismiss=_hub_cancel_register)
def _hub_register_dialog():
    pending = st.session_state["_hub_pending_register"]
    st.markdown(f"Register **{len(pending['rows'])}** selected term(s).")

    domain, term_status = None, "PUBLISHED"
    if "Business Term" in pending["fields"]:
        target = st.radio(
            "Register business terms to",
            ["Columns (classic glossary)", "Governance domain + columns"], key="hub_reg_target",
            help="Columns: each term is created in the classic glossary and put directly on its column "
                 "(the asset's Schema tab). Governance domain: the term is also created in a domain.")
        if target.startswith("Columns"):
            st.caption("Terms go into the classic glossary and onto each column in the asset's Schema tab.")
            domains, dom_err = [], None
        else:
            domains, dom_err = _purview_governance_domains()
        if target.startswith("Columns"):
            pass
        elif domains:
            labels = [f"{d['name']}  ({d['status']})" for d in domains]
            idx = st.selectbox("Governance domain", range(len(domains)), format_func=lambda i: labels[i],
                               key="hub_reg_domain",
                               help="Terms are created in this governance domain and linked to each row's table data asset.")
            domain = domains[idx]
            term_status = st.radio("Term status", ["PUBLISHED", "DRAFT"], horizontal=True, key="hub_reg_status",
                                   format_func=str.title,
                                   help="Status for terms that don't exist in the domain yet. Existing terms keep theirs.")
            oc1, oc2 = st.columns(2)
            with oc1:
                st.text_input("Owner name", key="hub_reg_owner_name", placeholder="e.g. Jeevika Palanivelu")
            with oc2:
                st.text_input("Owner email or Entra object ID", key="hub_reg_owner_id",
                              placeholder="name@company.com or 00000000-0000-…",
                              help="Purview stores the owner's Entra object ID. An email is looked up in "
                                   "Microsoft Graph, which needs the app permission User.Read.All; "
                                   "otherwise enter the object ID (Entra admin center → Users → the user).")
            st.caption("Terms are created in this domain and linked to the table. On the column (Schema tab) the "
                       "domain term is used when the tenant has asset curation enabled; otherwise the term is "
                       "also put on the column through the classic glossary.")
        else:
            st.warning("No governance domains found in this Purview account, so terms go to the classic glossary."
                       + (f" ({dom_err})" if dom_err else ""))

    st.markdown("Choose how:")
    st.markdown(
        "- **Insert** — add the new terms and classifications alongside the existing ones. "
        "Existing descriptions are kept.\n"
        "- **Update** — replace them: term definitions and column descriptions are overwritten and old "
        "classifications removed. Classic-glossary terms are also unassigned from these columns."
    )
    c1, c2, c3 = st.columns(3)
    mode = None
    with c1:
        if st.button("Insert", use_container_width=True, key="hub_reg_insert"):
            mode = "insert"
    with c2:
        if st.button("Update", type="primary", use_container_width=True, key="hub_reg_update"):
            mode = "update"
    with c3:
        if st.button("Cancel", use_container_width=True, key="hub_reg_cancel"):
            _hub_cancel_register()
            st.rerun()
    if mode:
        owners = None
        owner_ref = st.session_state.get("hub_reg_owner_id", "").strip() if domain else ""
        if owner_ref:
            try:
                owner_id = _purview_connector().resolve_owner_id(owner_ref)
            except Exception as e:
                st.error(f"Owner: {e}")
                return
            owner_name = st.session_state.get("hub_reg_owner_name", "").strip()
            owners = [{"id": owner_id, **({"description": owner_name} if owner_name else {})}]
        st.session_state.pop("_hub_pending_register", None)
        _hub_finish_register(pending["rows"], pending["fields"], pending["msg_key"], pending["selected_guid"], mode,
                             domain=domain, term_status=term_status, owners=owners)
        st.rerun()


def _hub_register_message(state_key):
    """Show the result box of the last registration (green on success, red on failure)."""
    if state_key not in st.session_state:
        return
    ok, msg = st.session_state[state_key] if isinstance(st.session_state[state_key], tuple) else (True, st.session_state[state_key])
    border, bg, fg, icon = ("#10B981", "#ECFDF5", "#065F46", "✅") if ok else ("#EF4444", "#FEF2F2", "#991B1B", "⚠️")
    st.markdown(
        f'<div style="background-color:{bg};border:1px solid {border};border-radius:8px;padding:12px 16px;'
        f'margin-top:10px;margin-bottom:15px;display:flex;align-items:flex-start;gap:10px;">'
        f'<span style="font-size:18px;">{icon}</span>'
        f'<span style="font-weight:600;color:{fg};font-size:14px;line-height:1.6;">{msg}</span></div>',
        unsafe_allow_html=True,
    )


def render_master_glossary_tab():
    render_dashboard_header("Glossary Hub")
    st.markdown('<div class="workbench-header"><div class="accent-line"></div><h1 class="workbench-title">Glossary Hub</h1><p class="workbench-desc">Enterprise Source of Truth — All approved, versioned glossary records with full audit history.</p></div>', unsafe_allow_html=True)
    
    # Check both JSON store and SQLite database for data
    summaries = PersistenceManager.get_all_stored_summaries()
    _hub_has_new_approvals = st.session_state.get("hub_approved_this_session", False)
    _hub_session_start = st.session_state.get("session_start_time", "")
    _hub_since = _hub_session_start if _hub_has_new_approvals else None
    # Always load all tables so History toggle can show older tables too
    db_tables_all = glossary_db.get_all_table_summaries()
    
    # Merge: prefer SQLite as source of truth, fall back to JSON
    if db_tables_all:
        # Build summaries from SQLite (all tables for table filter)
        summaries = []
        for t in db_tables_all:
            summaries.append({
                "Asset GUID": t["table_guid"],
                "Asset Name": t["table_name"],
                "Active Terms": t["active_terms"],
                "Total History": t["total_history"],
                "Last Updated": t["last_updated"],
                "Version": 1,
            })
    
    if not summaries:
        st.info("No approved glossary records found. Generate suggestions in 'Glossary AI' to get started.")
        return
        
    df_sum = pd.DataFrame(summaries)
    all_asset_names = df_sum["Asset Name"].tolist()

    # ── Collect all metadata for filters (single batch read) ────────────────────
    _all_guids = df_sum["Asset GUID"].tolist()
    _all_records = PersistenceManager.get_all_versions(_all_guids) or []

    # ── Connector scope: filter records based on which connector is active ──
    _hub_uc_connected = st.session_state.get('integration_connectors', {}).get('Databricks Unity', {}).get('status') == 'Connected'
    _hub_purview_connected = st.session_state.get('integration_connectors', {}).get('Microsoft Purview', {}).get('status') == 'Connected'

    if _hub_uc_connected and _hub_purview_connected:
        # Both connected — show all records (no filtering needed)
        pass
    elif _hub_uc_connected:
        _all_records = [r for r in _all_records if r.get("Source") == "Databricks Unity Catalog"]
        _uc_guids = {r.get("table_guid") for r in _all_records if r.get("table_guid")}
        summaries = [s for s in summaries if s["Asset GUID"] in _uc_guids]
        if not summaries:
            st.info("No Unity Catalog approved records found. Generate AI suggestions from Databricks assets and approve them to see them here.")
            return
        df_sum = pd.DataFrame(summaries)
        all_asset_names = df_sum["Asset Name"].tolist()
    elif _hub_purview_connected:
        _all_records = [r for r in _all_records if r.get("Source") != "Databricks Unity Catalog"]
        _purview_guids = {r.get("table_guid") for r in _all_records if r.get("table_guid")}
        summaries = [s for s in summaries if s["Asset GUID"] in _purview_guids]
        if not summaries:
            st.info("No Purview approved records found. Generate AI suggestions from Purview assets and approve them to see them here.")
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

        # ── Active / Non-Active filter ────────────────────────────────────────
        with st.expander("Status", expanded=True):
            active_filter = st.radio(
                "Show records", ["Active", "Non-Active", "All"],
                key="hub_active_filter", label_visibility="collapsed"
            )

        # ── Search & Filters Controls ─────────────────────────────────────
        with st.expander("Search & Filters", expanded=True):
            hub_term_query = st.text_input("🔍 Search Terms", placeholder="Filter by term name...", key="hub_term_query")
            hub_desc_query = st.text_input("📝 Search Description", placeholder="Filter definition text...", key="hub_desc_query")

            _class_opts = ["All"] + sorted(list(set(all_classifications + ["PII (Personally Identifiable Information)", "Sensitive PII", "PHI (Protected Health Information)", "Confidential", "Restricted", "Internal", "Public"])))
            classification_filter = st.selectbox("🏷️ Classification", _class_opts, key="hub_class_filter")

        # ── Table / Asset filter ──────────────────────────────────────────────
        with st.expander("Table Filter", expanded=False):
            if asset_filter != "All":
                asset_to_view = asset_filter
                st.markdown(
                    f"<div class='hub-asset-badge'>📋 Viewing: <strong>{asset_to_view}</strong></div>",
                    unsafe_allow_html=True
                )
            else:
                all_options = ["All Tables"] + all_asset_names
                asset_to_view = st.selectbox("Select Table/Asset to View", all_options, key="hub_asset_select", label_visibility="collapsed")

    # ═══════════════════════════════════════════════════════════════════════════
    # RIGHT PANEL — Main Content Area (Trending UI)
    # ═══════════════════════════════════════════════════════════════════════════
    with col_main:
        # ── Light Elegant Header Banner ─────────────────────────────────────
        st.markdown(
            f'<div style="background:#F8FAFC;border:1px solid #E2E8F0;border-left:4px solid #3B82F6;border-radius:10px;padding:16px 20px;margin-bottom:18px;color:#1E293B;">'
            f'<div style="display:flex;justify-content:space-between;align-items:center;">'
            f'<div>'
            f'<div style="font-size:18px;font-weight:700;color:#1E293B;">📋 {_html.escape(asset_to_view) if asset_to_view else "Select a table"}</div>'
            f'<div style="font-size:12px;color:#64748B;margin-top:2px;">Enterprise glossary — versioned & governed</div>'
            f'</div>'
            f'<div style="background:#EFF6FF;color:#1D4ED8;border:1px solid #BFDBFE;border-radius:6px;padding:5px 12px;font-size:12px;font-weight:600;">'
            f'Active Terms</div>'
            f'</div></div>',
            unsafe_allow_html=True
        )

        # ── Which information to show and register back to Purview ────────────
        hub_info_fields = _hub_info_selector()
        if st.session_state.get("_hub_pending_register"):
            _hub_register_dialog()
        hub_hidden_info = [f for f in _HUB_INFO_OPTIONS if f not in hub_info_fields]

        # ── Sub-tabs: All Terms vs Current Session ───────────────────────────
        hub_tab_session, hub_tab_all = st.tabs(["✅ Current Session Approvals", "📋 All Terms"])

        with hub_tab_all:
            tb_left, tb_right = st.columns([3, 1])
            with tb_left:
                show_history = st.toggle("📜 Show History", key="hub_show_history", value=False)
            with tb_right:
                edit_mode = st.toggle("✏️ Edit", key="hub_edit_mode", value=False)

            # ── Data Display ──────────────────────────────────────────────────────
            if asset_to_view:
                selected_guid = None
                if asset_to_view != "All Tables":
                    selected_guid = df_sum[df_sum["Asset Name"] == asset_to_view]["Asset GUID"].iloc[0]

                # Determine source filter based on connector
                _db_source_filter = None
                if _hub_uc_connected and not _hub_purview_connected:
                    _db_source_filter = "Databricks Unity Catalog"

                # Fetch from SQLite based on History toggle
                if show_history:
                    # History ON: all approved versions (active + previously-active)
                    db_records = glossary_db.get_approved_history(table_guid=selected_guid, source_filter=_db_source_filter)
                elif active_filter == "All":
                    db_records = glossary_db.get_all_terms(table_guid=selected_guid, source_filter=_db_source_filter)
                elif active_filter == "Non-Active":
                    db_records = glossary_db.get_all_terms(table_guid=selected_guid, source_filter=_db_source_filter)
                else:
                    # Default "Active": only latest approved version per physical_term
                    db_records = glossary_db.get_latest_approved_per_term(table_guid=selected_guid, source_filter=_db_source_filter)

                # Fallback to JSON store if SQLite is empty (backward compatibility)
                if not db_records:
                    _fallback_guids = [selected_guid] if selected_guid else _all_guids
                    full_history = PersistenceManager.get_all_versions(_fallback_guids)
                    if full_history:
                        df_hist = pd.DataFrame(full_history)
                        # Filter by connector
                        if _hub_uc_connected and not _hub_purview_connected and "Source" in df_hist.columns:
                            df_hist = df_hist[df_hist["Source"] == "Databricks Unity Catalog"]
                        elif _hub_purview_connected and not _hub_uc_connected and "Source" in df_hist.columns:
                            df_hist = df_hist[df_hist["Source"] != "Databricks Unity Catalog"]
                        # Apply filter
                        if show_history:
                            if "Status" in df_hist.columns:
                                df_hist = df_hist[df_hist["Status"].isin(["Approved", "Approved (Merged)"])]
                        elif active_filter == "All":
                            pass
                        elif active_filter == "Non-Active":
                            df_hist = df_hist[df_hist["Active"] == 0]
                        else:
                            df_hist = df_hist[df_hist["Active"] == 1]
                            if "Status" in df_hist.columns:
                                df_hist = df_hist[df_hist["Status"] != "Rejected"]
                    else:
                        df_hist = pd.DataFrame()
                else:
                    # Convert SQLite records to DataFrame
                    df_hist = pd.DataFrame(db_records)
                    # Rename SQLite columns to match display format
                    df_hist = df_hist.rename(columns={
                        "business_term": "Business Term",
                        "physical_term": "Physical Term",
                        "description": "Description",
                        "classification": "Classification",
                        "type": "Type",
                        "source": "Source",
                        "confidence": "Confidence (%)",
                        "active": "Active",
                        "version": "Version",
                        "status": "Status",
                        "stored_at": "Stored At",
                        "table_name": "table_name",
                        "table_guid": "table_guid",
                        "entity_guid": "entity_guid",
                    })
                    # Apply active/non-active filter only when History is OFF
                    if not show_history:
                        if active_filter == "Active":
                            df_hist = df_hist[df_hist["Active"] == 1]
                        elif active_filter == "Non-Active":
                            df_hist = df_hist[df_hist["Active"] == 0]

                if df_hist.empty:
                    st.info("No approved records found for this asset." if not show_history else "No records found in history.")
                    st.stop()

                # Normalise column names
                df_hist = df_hist.rename(columns={
                    "Original Name":           "Physical Term",
                    "Definition / Description": "Description",
                    "Glossary Term":            "Business Term",
                })
                df_hist = _hub_prepare_df(df_hist)

                # Apply classification filter
                if classification_filter != "All" and "Classification" in df_hist.columns:
                    df_hist = df_hist[df_hist["Classification"].fillna("").astype(str).str.contains(classification_filter, case=False, regex=False)]

                # Apply Term search filter
                if hub_term_query and hub_term_query.strip():
                    _t_q = hub_term_query.strip().lower()
                    df_hist = df_hist[
                        df_hist["Business Term"].fillna("").astype(str).str.lower().str.contains(_t_q) |
                        df_hist["Physical Term"].fillna("").astype(str).str.lower().str.contains(_t_q)
                    ]

                # Apply Description search filter
                if hub_desc_query and hub_desc_query.strip():
                    _d_q = hub_desc_query.strip().lower()
                    df_hist = df_hist[
                        df_hist["Description"].fillna("").astype(str).str.lower().str.contains(_d_q)
                    ]

                # Active records first, then group by Physical Term and sort by Version
                _sort_cols = ["Active"]
                _sort_asc = [False]
                if "Physical Term" in df_hist.columns:
                    _sort_cols.append("Physical Term")
                    _sort_asc.append(True)
                if "Version" in df_hist.columns:
                    _sort_cols.append("Version")
                    _sort_asc.append(False)
                df_hist = df_hist.sort_values(_sort_cols, ascending=_sort_asc).reset_index(drop=True)

                active_count = (df_hist["Active"] == 1).sum()

                # Remove trailing empty / all-NaN rows
                df_hist = df_hist.dropna(how="all").reset_index(drop=True)

                # ── Bento Grid Metrics (Light & Suitable Colors) ────────────────
                m1, m2, m3 = st.columns(3)
                with m1:
                    st.markdown(
                        f'<div style="background:#F8FAFC;border:1px solid #E2E8F0;border-top:3px solid #10B981;border-radius:10px;padding:12px;text-align:center;">' 
                        f'<div style="font-size:24px;font-weight:800;color:#065F46;">{active_count}</div></div>',
                        unsafe_allow_html=True
                    )
                    st.markdown(":material/check_circle: **ACTIVE**")
                with m2:
                    versions_max = df_hist["Version"].max() if "Version" in df_hist.columns else 1
                    st.markdown(
                        f'<div style="background:#FEFCE8;border:1px solid #FEF08A;border-top:3px solid #F59E0B;border-radius:10px;padding:12px;text-align:center;">' 
                        f'<div style="font-size:24px;font-weight:800;color:#92400E;">{versions_max}</div></div>',
                        unsafe_allow_html=True
                    )
                    st.markdown(":material/layers: **VERSIONS**")
                with m3:
                    sources = df_hist["Source"].nunique() if "Source" in df_hist.columns else 0
                    st.markdown(
                        f'<div style="background:#EFF6FF;border:1px solid #BFDBFE;border-top:3px solid #3B82F6;border-radius:10px;padding:12px;text-align:center;">'
                        f'<div style="font-size:24px;font-weight:800;color:#1E40AF;">{sources}</div></div>',
                        unsafe_allow_html=True
                    )
                    st.markdown(":material/dns: **SOURCES**")

                st.markdown("<div style='height:18px;'></div>", unsafe_allow_html=True)

                # ── Table View (Grouped by Table Name like Audit Log) ────────────────
                if "Select" not in df_hist.columns:
                    df_hist.insert(0, "Select", True)

                HIDDEN_COLS = {
                    "version": None, "id": None, "created_at": None,
                    "is_active": None, "timestamp": None, "data": None,
                    "table_guid": None, "entity_guid": None,
                    "table_name": None, "related_column": None, "Confidence (%)": None,
                    "source_type": None, "table_qualified_name": None, "table_entity_guid": None,
                }

                priority_cols = ["Select", "Active", "Version", "Status"]
                desired_order = ["Type", "Physical Term", "Business Term", "Description", "Classification", "Source", "Stored At"]
                middle_cols = [c for c in desired_order if c in df_hist.columns and c not in priority_cols]
                extra_cols  = [c for c in df_hist.columns
                               if c not in priority_cols and c not in middle_cols and c not in HIDDEN_COLS]
                display_cols = [c for c in priority_cols if c in df_hist.columns] + middle_cols + extra_cols
                display_cols = [c for c in display_cols if c not in hub_hidden_info]

                col_config = {
                    "Select":        st.column_config.CheckboxColumn("Select", help="Check row to select for registration", default=True, width="small"),
                    "Active":        st.column_config.NumberColumn("Active",   help="1 = Current, 0 = Historical", width="small"),
                    "Version":       st.column_config.NumberColumn("Version",  width="small"),
                    "Status":        st.column_config.TextColumn("Status",     help="Approved / Rejected", width="small"),
                    "Type":          st.column_config.TextColumn("Type",       width="small"),
                    "Physical Term": st.column_config.TextColumn("Physical Term"),
                    "Business Term": st.column_config.TextColumn("Business Term"),
                    "Description":   st.column_config.TextColumn("Description"),
                    "Classification": st.column_config.TextColumn("Classification", width="small"),
                    "Source":        st.column_config.TextColumn("Source",     width="small"),
                    "Stored At":     st.column_config.TextColumn("Last Updated"),
                    **HIDDEN_COLS
                }

                disabled_cols = [c for c in display_cols if c != "Select"] if not edit_mode else []

                edited_dfs = []
                if "table_name" in df_hist.columns:
                    _hist_groups = pd.Series(_hub_table_groups(df_hist), index=df_hist.index)
                    tables_in_all = sorted(set(_hist_groups))
                    for tbl in tables_in_all:
                        sub_df = df_hist[_hist_groups == tbl]
                        st.markdown(
                            f"<div style='margin:16px 0 6px 0;padding:6px 14px;"
                            f"background:#F3F4F6;border-left:4px solid #6B7280;"
                            f"border-radius:4px;font-weight:600;font-size:14px;color:#374151;display:flex;align-items:center;gap:6px;'>"
                            f'<span class="material-symbols-outlined" style="font-size:18px;">table_chart</span> <strong>{tbl}</strong></div>',
                            unsafe_allow_html=True,
                        )
                        df_display = sub_df[display_cols] if display_cols else sub_df
                        res_df = st.data_editor(
                            df_display,
                            key=f"hub_view_{selected_guid}_{_safe_mermaid_id(tbl)}",
                            hide_index=True,
                            use_container_width=True,
                            disabled=disabled_cols,
                            num_rows="fixed",
                            column_config=col_config
                        )
                        if "table_guid" in sub_df.columns:
                            res_df["table_guid"] = sub_df["table_guid"].values
                        if "table_name" in sub_df.columns:
                            res_df["table_name"] = sub_df["table_name"].values
                        for _hc in ("table_entity_guid", "table_qualified_name", "Type"):
                            if _hc in sub_df.columns:
                                res_df[_hc] = sub_df[_hc].values
                        edited_dfs.append(res_df)
                else:
                    tbl_title = asset_to_view if asset_to_view else "GLOSSARY TERMS"
                    st.markdown(
                        f"<div style='margin:16px 0 6px 0;padding:6px 14px;"
                        f"background:#F3F4F6;border-left:4px solid #6B7280;"
                        f"border-radius:4px;font-weight:600;font-size:14px;color:#374151;display:flex;align-items:center;gap:6px;'>"
                        f'<span class="material-symbols-outlined" style="font-size:18px;">table_chart</span> <strong>{tbl_title}</strong></div>',
                        unsafe_allow_html=True,
                    )
                    df_display = df_hist[display_cols] if display_cols else df_hist
                    res_df = st.data_editor(
                        df_display,
                        key=f"hub_view_{selected_guid}",
                        hide_index=True,
                        use_container_width=True,
                        disabled=disabled_cols,
                        num_rows="fixed",
                        column_config=col_config
                    )
                    if "table_guid" in df_hist.columns:
                        res_df["table_guid"] = df_hist["table_guid"].values
                    if "table_name" in df_hist.columns:
                        res_df["table_name"] = df_hist["table_name"].values
                    for _hc in ("table_entity_guid", "table_qualified_name", "Type"):
                        if _hc in df_hist.columns:
                            res_df[_hc] = df_hist[_hc].values
                    edited_dfs.append(res_df)

                if edited_dfs:
                    combined_all_df = pd.concat(edited_dfs, ignore_index=True)
                else:
                    combined_all_df = df_hist

                target_register_df = combined_all_df[combined_all_df["Select"] == True] if "Select" in combined_all_df.columns else combined_all_df

                # ── Single Smart Register Button ─────────────────────────────────
                can_register = st.session_state.user_role == "Administrator"

                _connectors  = st.session_state.integration_connectors
                _purview_cfg = _connectors.get("Microsoft Purview", {})
                _db_cfg      = _connectors.get("Databricks Unity", {})
                creds        = st.session_state.get("connector_creds", {})
                _sec_pur     = st.secrets.get("purview", {})
                _has_purview_creds = bool((creds.get("purview_account_name") or _sec_pur.get("account_name")) and (creds.get("purview_client_id") or _sec_pur.get("client_id")))
                _purview_on  = (_purview_cfg.get("status") == "Connected") or _has_purview_creds
                _db_on       = _db_cfg.get("status") == "Connected"

                # Determine which platform is connected
                if _purview_on:
                    _platform_name = "Microsoft Purview"
                    _platform_icon = "☁️"
                elif _db_on:
                    _platform_name = "Databricks Unity Catalog"
                    _platform_icon = "🔷"
                else:
                    _platform_name = None
                    _platform_icon = "🔗"

                # Registration card
                st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)

                _btn_disabled = not can_register or not _platform_name or target_register_df.empty or not hub_info_fields
                _btn_label = "Register"
                _btn_help = _hub_register_help(len(target_register_df), _platform_name, hub_info_fields, can_register)

                if st.button(_btn_label, type="primary", use_container_width=True, disabled=_btn_disabled, help=_btn_help, key="hub_register_btn"):
                    if _purview_on or True:
                        _hub_start_register(target_register_df, hub_info_fields, "_hub_register_msg", selected_guid)

                    elif _db_on:
                        # ── Databricks Unity Catalog Logic ────────────────────
                        _db_browse   = DatabricksUnityConnector(_db_cfg.get("api_endpoint", ""), _db_cfg.get("api_token", ""))
                        _meta_entry  = st.session_state.get("tables_metadata", {}).get(selected_guid, {})
                        uc_full_name = _meta_entry.get("qualifiedName", "")

                        _whs, _wh_err = _db_browse.list_sql_warehouses()
                        _wh_id = ""
                        if not _wh_err and _whs:
                            _running = [w for w in _whs if w["state"] == "RUNNING"]
                            _wh_id = (_running or _whs)[0]["id"]

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

                # Display registration result directly under the Register button
                _hub_register_message("_hub_register_msg")

        # ═══════════════════════════════════════════════════════════════════════
        # CURRENT SESSION APPROVALS TAB
        # ═══════════════════════════════════════════════════════════════════════
        with hub_tab_session:
            _session_start = st.session_state.get("session_start_time", "")
            session_records = glossary_db.get_active_terms(source_filter=None, since=_session_start)

            if not session_records:
                st.info("No terms have been approved in this session yet. Approve terms in **Review & Approval** to see them here.")
            else:
                df_session = pd.DataFrame(session_records)
                df_session = df_session.rename(columns={
                    "business_term": "Business Term",
                    "physical_term": "Physical Term",
                    "description": "Description",
                    "classification": "Classification",
                    "type": "Type",
                    "source": "Source",
                    "confidence": "Confidence (%)",
                    "active": "Active",
                    "version": "Version",
                    "status": "Status",
                    "stored_at": "Stored At",
                    "table_name": "table_name",
                    "table_guid": "table_guid",
                    "entity_guid": "entity_guid",
                })
                df_session = _hub_prepare_df(df_session)

                if classification_filter != "All" and "Classification" in df_session.columns:
                    df_session = df_session[df_session["Classification"].fillna("").astype(str).str.contains(classification_filter, case=False, regex=False)]

                if hub_term_query and hub_term_query.strip():
                    _t_q = hub_term_query.strip().lower()
                    df_session = df_session[
                        df_session["Business Term"].fillna("").astype(str).str.lower().str.contains(_t_q) |
                        df_session["Physical Term"].fillna("").astype(str).str.lower().str.contains(_t_q)
                    ]

                if hub_desc_query and hub_desc_query.strip():
                    _d_q = hub_desc_query.strip().lower()
                    df_session = df_session[
                        df_session["Description"].fillna("").astype(str).str.lower().str.contains(_d_q)
                    ]

                st.markdown(
                    f'<div style="background:#ECFDF5;border:1px solid #A7F3D0;border-radius:8px;padding:12px 18px;margin-bottom:16px;color:#065F46;display:flex;align-items:center;gap:10px;">'
                    f'<span style="font-size:18px;">✅</span>'
                    f'<div><span style="font-size:18px;font-weight:800;color:#065F46;">{len(df_session)}</span>'
                    f'<span style="font-size:13px;margin-left:8px;color:#047857;font-weight:600;">term(s) approved in this session</span></div></div>',
                    unsafe_allow_html=True
                )

                if "Select" not in df_session.columns:
                    df_session.insert(0, "Select", True)

                _sess_display_cols = ["Select", "Type", "Physical Term", "Business Term", "Description", "Classification", "Source", "Version", "Status"]
                _sess_display_cols = [c for c in _sess_display_cols if c in df_session.columns and c not in hub_hidden_info]

                sess_edited_dfs = []
                _sess_groups = pd.Series(_hub_table_groups(df_session), index=df_session.index)
                tables_in_session = sorted(set(_sess_groups))
                for tbl in tables_in_session:
                    df_tbl = df_session[_sess_groups == tbl]
                    st.markdown(
                        f"<div style='margin:16px 0 6px 0;padding:6px 14px;"
                        f"background:#F3F4F6;border-left:4px solid #6B7280;"
                        f"border-radius:4px;font-weight:600;font-size:14px;color:#374151;display:flex;align-items:center;gap:6px;'>"
                        f'<span class="material-symbols-outlined" style="font-size:18px;">table_chart</span> <strong>{tbl}</strong></div>',
                        unsafe_allow_html=True,
                    )
                    res_sess = st.data_editor(
                        df_tbl[_sess_display_cols],
                        key=f"hub_session_view_{_safe_mermaid_id(tbl)}",
                        use_container_width=True,
                        hide_index=True,
                        disabled=[c for c in _sess_display_cols if c != "Select"],
                        column_config={
                            "Select": st.column_config.CheckboxColumn("Select", help="Check row to select for registration", default=True, width="small"),
                            "Version": st.column_config.NumberColumn("Version", width="small"),
                            "Status": st.column_config.TextColumn("Status", width="small"),
                        }
                    )
                    if "table_guid" in df_tbl.columns:
                        res_sess["table_guid"] = df_tbl["table_guid"].values
                    if "table_name" in df_tbl.columns:
                        res_sess["table_name"] = df_tbl["table_name"].values
                    for _hc in ("table_entity_guid", "table_qualified_name", "Type"):
                        if _hc in df_tbl.columns:
                            res_sess[_hc] = df_tbl[_hc].values
                    sess_edited_dfs.append(res_sess)

                if sess_edited_dfs:
                    combined_sess_df = pd.concat(sess_edited_dfs, ignore_index=True)
                else:
                    combined_sess_df = df_session

                target_session_df = combined_sess_df[combined_sess_df["Select"] == True] if "Select" in combined_sess_df.columns else combined_sess_df

                st.markdown("<div style='height:16px;'></div>", unsafe_allow_html=True)

                # ── Register Button for Session Terms ─────────────────────────
                _connectors = st.session_state.integration_connectors
                _purview_cfg = _connectors.get("Microsoft Purview", {})
                _db_cfg = _connectors.get("Databricks Unity", {})
                _creds = st.session_state.get("connector_creds", {})
                _sec_pur = st.secrets.get("purview", {})
                _has_purview_creds = bool((_creds.get("purview_account_name") or _sec_pur.get("account_name")) and (_creds.get("purview_client_id") or _sec_pur.get("client_id")))
                _purview_on = (_purview_cfg.get("status") == "Connected") or _has_purview_creds
                _db_on = _db_cfg.get("status") == "Connected"
                can_register = st.session_state.user_role == "Administrator"

                if _purview_on:
                    _platform_name = "Microsoft Purview"
                    _platform_icon = "☁️"
                elif _db_on:
                    _platform_name = "Databricks Unity Catalog"
                    _platform_icon = "🔷"
                else:
                    _platform_name = None
                    _platform_icon = "🔗"

                _btn_disabled = not can_register or not _platform_name or target_session_df.empty or not hub_info_fields
                _btn_label = "Register"
                _btn_help = _hub_register_help(len(target_session_df), _platform_name, hub_info_fields, can_register)

                if st.button(_btn_label, type="primary", use_container_width=True, disabled=_btn_disabled, help=_btn_help, key="hub_session_register_btn"):
                    if _purview_on or True:
                        _hub_start_register(target_session_df, hub_info_fields, "_hub_session_register_msg")

                # Display registration result directly under the Register button
                _hub_register_message("_hub_session_register_msg")

# ============================================
# SEMANTIC SEARCH TAB
# ============================================

def render_semantic_search_tab():
    render_dashboard_header("Semantic Search")
    st.markdown('''
        <div class="workbench-header">
            <div class="accent-line"></div>
            <h1 class="workbench-title">Semantic Search</h1>
            <p class="workbench-desc">Search your glossary using natural language. Find business terms, definitions, and data assets by meaning — not just keywords.</p>
        </div>
    ''', unsafe_allow_html=True)

    # Search input area
    col_search, col_opts = st.columns([3, 1], gap="medium")

    with col_search:
        search_query = st.text_input(
            "🔍 Search your glossary",
            placeholder="e.g. 'patient contact information', 'unique identifier for a person', 'blood type'...",
            key="semantic_search_input",
            label_visibility="collapsed"
        )

    with col_opts:
        search_mode = st.selectbox(
            "Search Mode",
            ["Semantic (AI)", "Keyword"],
            key="semantic_search_mode",
            label_visibility="collapsed"
        )

    # Advanced options
    with st.expander("⚙️ Advanced Options", expanded=False):
        adv_col1, adv_col2 = st.columns(2)
        with adv_col1:
            top_k = st.slider("Max Results", min_value=5, max_value=50, value=10, step=5, key="semantic_top_k")
        with adv_col2:
            if search_mode == "Semantic (AI)":
                threshold = st.slider("Similarity Threshold (%)", min_value=50, max_value=95, value=70, step=5, key="semantic_threshold")
            else:
                threshold = 70  # not used for keyword

    # Execute search
    if search_query and search_query.strip():
        with st.spinner("Searching glossary..." if search_mode == "Keyword" else "Performing semantic search with AI embeddings..."):
            if search_mode == "Semantic (AI)":
                results = semantic_search_glossary(
                    query=search_query,
                    top_k=top_k,
                    similarity_threshold=threshold / 100.0
                )
                score_col_name = "Similarity"
            else:
                results = keyword_search_glossary(
                    query=search_query,
                    top_k=top_k
                )
                score_col_name = "Relevance"

        if results:
            st.markdown(f"### 📋 Results ({len(results)} matches)")
            st.markdown("<br>", unsafe_allow_html=True)

            # Summary metrics
            m1, m2, m3 = st.columns(3)
            with m1:
                st.metric("Matches Found", len(results))
            with m2:
                avg_score = sum(r.get(score_col_name, 0) for r in results) / len(results)
                st.metric(f"Avg {score_col_name}", f"{avg_score:.1f}%")
            with m3:
                unique_tables = len(set(r.get("Table", "") for r in results if r.get("Table")))
                st.metric("Tables Matched", unique_tables)

            st.markdown("<br>", unsafe_allow_html=True)

            # Results as expandable cards
            for i, result in enumerate(results):
                score = result.get(score_col_name, 0)
                # Color-code by score
                if score >= 90:
                    badge_color = "#16A34A"
                    badge_bg = "#DCFCE7"
                elif score >= 80:
                    badge_color = "#2563EB"
                    badge_bg = "#DBEAFE"
                elif score >= 70:
                    badge_color = "#D97706"
                    badge_bg = "#FEF3C7"
                else:
                    badge_color = "#6B7280"
                    badge_bg = "#F3F4F6"

                with st.expander(
                    f"**{result.get('Business Term', 'N/A')}** — `{result.get('Physical Term', '')}` | {score_col_name}: {score}%",
                    expanded=(i < 3)
                ):
                    det_col1, det_col2 = st.columns([3, 1])
                    with det_col1:
                        st.markdown(f"**Definition:** {result.get('Definition', 'N/A')}")
                        st.markdown(f"**Table:** `{result.get('Table', 'N/A')}` &nbsp;|&nbsp; **Type:** {result.get('Type', 'N/A')}")
                    with det_col2:
                        st.markdown(
                            f"<div style='text-align:center; padding:8px; border-radius:8px; background:{badge_bg}; color:{badge_color}; font-weight:700; font-size:18px;'>{score}%</div>"
                            f"<div style='text-align:center; font-size:11px; color:#6B7280; margin-top:4px;'>{score_col_name}</div>",
                            unsafe_allow_html=True
                        )
                    st.caption(f"Source: {result.get('Source', 'N/A')} | Confidence: {result.get('Confidence (%)', 'N/A')}%")

            # Also show as a table
            st.markdown("<br>", unsafe_allow_html=True)
            with st.expander("📊 View as Table", expanded=False):
                df_results = pd.DataFrame(results)
                st.dataframe(df_results, use_container_width=True, hide_index=True)
        else:
            st.warning("No matching results found. Try a different query or lower the similarity threshold.")
    else:
        # Show example queries when no search is active
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown("#### 💡 Example Queries")
        example_cols = st.columns(3)
        examples = [
            ("🏥 Healthcare", "patient contact details"),
            ("🔑 Identifiers", "unique person identifier"),
            ("📍 Location", "residential address information"),
        ]
        for col, (label, example) in zip(example_cols, examples):
            with col:
                st.markdown(
                    f"""<div style='padding:16px; border-radius:10px; border:1px solid #E5E7EB; background:#FAFAFA; cursor:pointer;'>
                        <div style='font-size:13px; font-weight:600; color:#374151;'>{label}</div>
                        <div style='font-size:12px; color:#6B7280; margin-top:4px;'>"{example}"</div>
                    </div>""",
                    unsafe_allow_html=True
                )

        st.markdown("<br>", unsafe_allow_html=True)
        st.info("💡 **Semantic Search** uses AI embeddings to understand the _meaning_ of your query and match it against glossary definitions, business terms, and physical column names — even if the exact words don't appear in the records.")


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
        (mc1, "TOTAL ASSETS",       str(metrics["Total Assets"]),    metrics["Total Assets"],    100,  "#378ADD", f"{metrics['Total Assets']} tables indexed",   None),
        (mc2, "ACTIVE TERMS",       str(metrics["Active Terms"]),    metrics["Active Terms"],    200,  "#1D9E75", f"across {metrics['Total Assets']} table(s)",   True),
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
        # AI Coverage: calculated from persisted glossary data (AI-recommended/generated terms)
        _ai_count, _total_count = glossary_db.get_ai_coverage_stats()
        ai_cov_pct = min(100, int((_ai_count / _total_count) * 100)) if _total_count > 0 else 0
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
            table_name = entry.get("table_name", "") or ""
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
            ex_table = (ex_entry.get("table_name") or "") if ex_entry else ""

            # Check if same/similar term is already approved in the glossary DB
            _approved_matches = glossary_db.check_approved_term_exists(term_name, physical_term=physical)
            # Determine which warning scenarios to show
            _show_approved = (
                bool(_approved_matches)
                or "Already Approved" in match_type
                or "Already approved" in match_type
                or "Duplicate" in match_type
            )
            _show_conflict = match_type not in (
                "Already Approved — Use Merge",
                "Already approved in audit log",
                "Exact Duplicate — Use Merge",
            )

            label = f"Conflict #{i+1}: `{physical or term_name}` — {match_type}"
            with st.expander(label, expanded=(i == 0)):
                # Scenario A: regular conflict (similar term exists)
                if _show_conflict:
                    _conflict_detail = _html.escape(match_type)
                    st.markdown(
                        f'<div style="background:#FCEBEB;border:1px solid #F7C1C1;border-radius:8px;padding:10px 14px;margin-bottom:8px;">'
                        f'<span style="font-size:13px;color:#A32D2D;font-weight:600;">⚠️ Conflict Detected</span>'
                        f'<div style="font-size:12px;color:#A32D2D;margin-top:4px;">A same or similar term already exists in the glossary.</div>'
                        f'<div style="font-size:11px;color:#6B7280;margin-top:2px;">Match type: {_conflict_detail}</div>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
                    if ex_name and ex_name != "—":
                        st.markdown(
                            f'<div style="background:#F9FAFB;border:1px solid #E5E7EB;border-radius:6px;padding:8px 12px;margin-bottom:8px;font-size:12px;color:#374151;">'
                            f'Existing Term: <strong>{_html.escape(ex_name)}</strong><br/>'
                            f'Status: <strong>Conflict</strong></div>',
                            unsafe_allow_html=True,
                        )

                # Scenario B: already approved
                if _show_approved:
                    st.markdown(
                        '<div style="background:#FEF3C7;border:1px solid #FDE68A;border-radius:8px;padding:10px 14px;margin-bottom:8px;">'
                        '<span style="font-size:13px;color:#854F0B;font-weight:600;">⚠️ Already Approved</span>'
                        '<div style="font-size:12px;color:#854F0B;margin-top:4px;">The same or a similar term has already been approved in the glossary.</div>'
                        '</div>',
                        unsafe_allow_html=True,
                    )
                    if _approved_matches:
                        for _am in _approved_matches:
                            _am_term = _html.escape(str(_am.get("business_term", "")))
                            _am_status = _html.escape(str(_am.get("status", "")))
                            _am_ver = _am.get("version", 1)
                            _am_phys = _html.escape(str(_am.get("physical_term", "")))
                            st.markdown(
                                f'<div style="background:#F9FAFB;border:1px solid #E5E7EB;border-radius:6px;padding:8px 12px;margin-bottom:8px;font-size:12px;color:#374151;">'
                                f'Existing Term: <strong>{_am_term}</strong><br/>'
                                f'Physical Term: <strong>{_am_phys}</strong><br/>'
                                f'Status: <strong>{_am_status}</strong><br/>'
                                f'Version: <strong>{_am_ver}</strong></div>',
                                unsafe_allow_html=True,
                            )
                    elif ex_name and ex_name != "—":
                        st.markdown(
                            f'<div style="background:#F9FAFB;border:1px solid #E5E7EB;border-radius:6px;padding:8px 12px;margin-bottom:8px;font-size:12px;color:#374151;">'
                            f'Existing Term: <strong>{_html.escape(ex_name)}</strong><br/>'
                            f'Status: <strong>Approved</strong></div>',
                            unsafe_allow_html=True,
                        )
                # Show table name
                if table_name:
                    st.markdown(f"**Table:** `{_html.escape(table_name.upper())}`")
                col_a, col_b = st.columns(2)
                with col_a:
                    _ex_table_html = f'<p style="font-size:12px; color:#991B1B; margin:0 0 4px 0;">Table: <strong>{_html.escape(ex_table.upper())}</strong></p>' if ex_table else ""
                    st.markdown(f'''
                        <div style="background:#FEF2F2; border:1px solid #FECACA; border-radius:8px; padding:16px;">
                            <p style="font-size:11px; color:#991B1B; font-weight:700; text-transform:uppercase; margin:0 0 8px 0;">Existing Approved Term</p>
                            <p style="font-weight:600; color:#111827; margin:0 0 4px 0;">{_html.escape(ex_name)}</p>
                            {_ex_table_html}
                            <p style="font-size:13px; color:#6B7280; margin:0;">{_html.escape(str(ex_desc)[:120])}</p>
                        </div>
                    ''', unsafe_allow_html=True)
                with col_b:
                    _new_table_html = f'<p style="font-size:12px; color:#92400E; margin:0 0 4px 0;">Table: <strong>{_html.escape(table_name.upper())}</strong></p>' if table_name else ""
                    st.markdown(f'''
                        <div style="background:#FFF7ED; border:1px solid #FED7AA; border-radius:8px; padding:16px;">
                            <p style="font-size:11px; color:#92400E; font-weight:700; text-transform:uppercase; margin:0 0 8px 0;">Queued Term (New)</p>
                            <p style="font-weight:600; color:#111827; margin:0 0 4px 0;">{_html.escape(term_name)}</p>
                            {_new_table_html}
                            <p style="font-size:13px; color:#6B7280; margin:0;">{_html.escape(str(definition)[:120])}</p>
                        </div>
                    ''', unsafe_allow_html=True)



# ============================================
# RBAC HELPERS
# ============================================

def get_current_user_permissions():
    """Return permissions dict for the currently active user, respecting demo role switcher."""
    role = st.session_state.user_role
    rbac_roles = st.session_state.get('rbac_roles', {})
    # If the user switched to a specific role via the demo switcher, use that role's permissions
    if role in rbac_roles:
        return rbac_roles[role]
    # Fallback: check per-user overrides
    user = st.session_state.user_name
    rbac_users = st.session_state.get('rbac_users', {})
    if user in rbac_users:
        return rbac_users[user]
    return {"can_read": False, "can_approve": False, "can_reject": False, "can_suggest": False, "can_edit_glossary": False, "can_manage_rbac": False}


def render_rbac_tab():
    render_dashboard_header("Access Control")
    st.markdown(
        '<div class="workbench-header"><div class="accent-line"></div>'
        '<h1 class="workbench-title">Access Control</h1>'
        '<p class="workbench-desc">Manage user roles and permissions — control who can approve, reject, suggest, or edit glossary terms.</p>'
        '</div>',
        unsafe_allow_html=True,
    )

    perms = get_current_user_permissions()
    if not perms.get("can_manage_rbac") and st.session_state.user_role != "Administrator":
        st.warning("🔒 You do not have permission to manage RBAC settings. Contact an Administrator.")
        # Show read-only view of current user's permissions
        st.markdown("#### Your Permissions")
        st.markdown(f"- **Approve Terms:** {'✅ Yes' if perms.get('can_approve') else '❌ No'}")
        st.markdown(f"- **Reject Terms:** {'✅ Yes' if perms.get('can_reject') else '❌ No'}")
        st.markdown(f"- **Suggest Terms:** {'✅ Yes' if perms.get('can_suggest') else '❌ No'}")
        st.markdown(f"- **Edit Glossary:** {'✅ Yes' if perms.get('can_edit_glossary') else '❌ No'}")
        return

    rbac_tab1, rbac_tab2, rbac_tab3 = st.tabs([":material/group: Users & Permissions", ":material/admin_panel_settings: Roles", ":material/person_add: Add User"])

    # ── Tab 1: Users & Permissions ────────────────────────────────────────────
    with rbac_tab1:
        st.markdown("#### User Permissions")
        st.caption("Assign roles and fine-grained permissions to each user.")

        rbac_users = st.session_state.rbac_users
        rbac_roles = st.session_state.rbac_roles

        for user_key, user_perms in list(rbac_users.items()):
            display_name = user_perms.get("name", user_key)
            user_email = user_perms.get("email", user_key)
            is_current = user_email == st.session_state.get("logged_in_email", "")
            with st.expander(f"{'🟢' if is_current else '⚪'} {display_name} ({user_email})  —  {user_perms.get('role', 'Reader')}", expanded=is_current):
                col1, col2, col_del = st.columns([1, 2, 0.3])
                with col1:
                    available_roles = list(rbac_roles.keys())
                    current_role_idx = available_roles.index(user_perms.get("role", "Reader")) if user_perms.get("role", "Reader") in available_roles else 0
                    new_role = st.selectbox(
                        "Role",
                        available_roles,
                        index=current_role_idx,
                        key=f"rbac_role_{user_key}",
                    )
                    if new_role != user_perms.get("role"):
                        # Auto-apply role defaults
                        role_defaults = rbac_roles.get(new_role, {})
                        st.session_state.rbac_users[user_key]["role"] = new_role
                        st.session_state.rbac_users[user_key]["can_approve"] = role_defaults.get("can_approve", False)
                        st.session_state.rbac_users[user_key]["can_reject"] = role_defaults.get("can_reject", False)
                        st.session_state.rbac_users[user_key]["can_suggest"] = role_defaults.get("can_suggest", False)
                        st.session_state.rbac_users[user_key]["can_edit_glossary"] = role_defaults.get("can_edit_glossary", False)
                        save_rbac(st.session_state.rbac_users, st.session_state.rbac_roles)
                        st.rerun()
                with col2:
                    st.markdown("**Permissions Override:**")
                    p_col0, p_col1, p_col2, p_col3, p_col4 = st.columns(5)
                    with p_col0:
                        read = st.checkbox("Read", value=user_perms.get("can_read", False), key=f"rbac_read_{user_key}")
                    with p_col1:
                        approve = st.checkbox("Approve", value=user_perms.get("can_approve", False), key=f"rbac_approve_{user_key}")
                    with p_col2:
                        reject = st.checkbox("Reject", value=user_perms.get("can_reject", False), key=f"rbac_reject_{user_key}")
                    with p_col3:
                        suggest = st.checkbox("Suggest", value=user_perms.get("can_suggest", False), key=f"rbac_suggest_{user_key}")
                    with p_col4:
                        edit_gl = st.checkbox("Edit Glossary", value=user_perms.get("can_edit_glossary", False), key=f"rbac_edit_{user_key}")

                    # Persist changes
                    st.session_state.rbac_users[user_key]["can_read"] = read
                    st.session_state.rbac_users[user_key]["can_approve"] = approve
                    st.session_state.rbac_users[user_key]["can_reject"] = reject
                    st.session_state.rbac_users[user_key]["can_suggest"] = suggest
                    st.session_state.rbac_users[user_key]["can_edit_glossary"] = edit_gl
                    save_rbac(st.session_state.rbac_users, st.session_state.rbac_roles)
                with col_del:
                    st.markdown("<br>", unsafe_allow_html=True)
                    if not is_current:
                        if st.button("🗑️", key=f"rbac_del_{user_key}", help=f"Delete user {display_name}"):
                            del st.session_state.rbac_users[user_key]
                            save_rbac(st.session_state.rbac_users, st.session_state.rbac_roles)
                            st.rerun()

    # ── Tab 2: Roles ─────────────────────────────────────────────────────────
    with rbac_tab2:
        st.markdown("#### Role Definitions")
        st.caption("Each role defines default permissions applied when assigning a user to that role.")

        rbac_roles = st.session_state.rbac_roles
        role_data = []
        for role_name, role_perms in rbac_roles.items():
            role_data.append({
                "Role": role_name,
                "Read": "✅" if role_perms.get("can_read") else "❌",
                "Approve": "✅" if role_perms.get("can_approve") else "❌",
                "Reject": "✅" if role_perms.get("can_reject") else "❌",
                "Suggest": "✅" if role_perms.get("can_suggest") else "❌",
                "Edit Glossary": "✅" if role_perms.get("can_edit_glossary") else "❌",
                "Manage RBAC": "✅" if role_perms.get("can_manage_rbac") else "❌",
            })
        st.table(pd.DataFrame(role_data))

        st.markdown("---") 
        st.markdown("#### Add Custom Role")
        with st.form("add_role_form", clear_on_submit=True):
            new_role_name = st.text_input("Role Name", placeholder="e.g. Data Steward")
            rc0, rc1, rc2, rc3, rc4, rc5 = st.columns(6)
            with rc0:
                nr_read = st.checkbox("Can Read", value=True, key="nr_read")
            with rc1:
                nr_approve = st.checkbox("Can Approve", key="nr_approve")
            with rc2:
                nr_reject = st.checkbox("Can Reject", key="nr_reject")
            with rc3:
                nr_suggest = st.checkbox("Can Suggest", value=True, key="nr_suggest")
            with rc4:
                nr_edit = st.checkbox("Can Edit Glossary", key="nr_edit")
            with rc5:
                nr_manage = st.checkbox("Can Manage RBAC", key="nr_manage")
            if st.form_submit_button("Add Role", type="primary"):
                if not new_role_name.strip():
                    st.error("Role name is required.")
                elif new_role_name.strip() in rbac_roles:
                    st.warning(f"Role '{new_role_name}' already exists.")
                else:
                    st.session_state.rbac_roles[new_role_name.strip()] = {
                        "can_read": nr_read,
                        "can_approve": nr_approve,
                        "can_reject": nr_reject,
                        "can_suggest": nr_suggest,
                        "can_edit_glossary": nr_edit,
                        "can_manage_rbac": nr_manage,
                    }
                    save_rbac(st.session_state.rbac_users, st.session_state.rbac_roles)
                    st.success(f"✅ Role '{new_role_name.strip()}' created.")
                    st.rerun()

    # ── Tab 3: Add User ──────────────────────────────────────────────────────
    with rbac_tab3:
        st.markdown("#### Add New User")
        st.caption("Add a user by their email address. Default password is `user321`. The user can log in with this email and password.")
        with st.form("add_user_form", clear_on_submit=True):
            new_user_email = st.text_input("Email ID", placeholder="e.g. john@company.com")
            new_user_display_name = st.text_input("Display Name", placeholder="e.g. John D.")
            _existing_roles = list(st.session_state.rbac_roles.keys())
            _default_role_idx = _existing_roles.index("Reader") if "Reader" in _existing_roles else 0
            new_user_role = st.selectbox("Assign Role", _existing_roles, index=_default_role_idx)
            if st.form_submit_button("Add User", type="primary"):
                if not new_user_email.strip():
                    st.error("Email ID is required.")
                elif "@" not in new_user_email:
                    st.error("Please enter a valid email address.")
                elif new_user_email.strip().lower() in st.session_state.rbac_users:
                    st.warning(f"User '{new_user_email}' already exists.")
                else:
                    role_defaults = st.session_state.rbac_roles.get(new_user_role, {})
                    email_key = new_user_email.strip().lower()
                    display_name = new_user_display_name.strip() if new_user_display_name.strip() else email_key
                    st.session_state.rbac_users[email_key] = {
                        "name": display_name,
                        "email": email_key,
                        "password": "user321",
                        "role": new_user_role,
                        "can_read": role_defaults.get("can_read", True),
                        "can_approve": role_defaults.get("can_approve", False),
                        "can_reject": role_defaults.get("can_reject", False),
                        "can_suggest": role_defaults.get("can_suggest", False),
                        "can_edit_glossary": role_defaults.get("can_edit_glossary", False),
                    }
                    save_rbac(st.session_state.rbac_users, st.session_state.rbac_roles)
                    st.success(f"✅ User '{display_name}' ({email_key}) added with role '{new_user_role}'. Default password: `user321`")
                    st.rerun()


def main():
    # Gate the entire app behind login
    if not st.session_state.get('logged_in', False):
        render_login_page()
        return

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
    elif tab == "Semantic Search": render_semantic_search_tab()
    elif tab == "RBAC Management": render_rbac_tab()
    else:
        render_dashboard_header(tab)
        st.info(f"The '{tab}' module is currently under construction.")

if __name__ == "__main__":
    main()
