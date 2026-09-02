#!/usr/bin/env python3
"""NovaMind AI Data Analyst Agent — professional dark-theme analytics UI.

Spotter-inspired conversational interface for natural-language data queries.
Powered by AWS Bedrock + Athena.

Local mode (default): uses AWS credentials and env vars directly.
Remote mode: set API_URL to your ECS load balancer.

Example:
  export GLUE_DB_NAME=project_library_db
  export PROJECT_FILES_BUCKET=langchain-<account-id>-us-east-1
  export ATHENA_WORKGROUP=project-text-to-sql
  streamlit run scripts/streamlit_app_new.py
"""
from __future__ import annotations

import base64
import os
import sys
from pathlib import Path
from typing import Optional

import requests
import streamlit as st

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_PATH = os.path.join(PROJECT_ROOT, 'src')
if SRC_PATH not in sys.path:
    sys.path.insert(0, SRC_PATH)

from llm_sql.config import SettingsError, get_settings, require_runtime_settings
from llm_sql.runner import build_athena_service
from llm_sql.connectors.registry import (
    get_connector,
    list_connections,
    load_connections,
)

# ── Branding ─────────────────────────────────────────────────────────────────
APP_NAME = 'NovaMind AI Data Analyst Agent'
LOGO_PATH = Path(PROJECT_ROOT) / 'assets' / 'novamind_logo.svg'
LINKEDIN_URL = 'https://www.linkedin.com/in/aamir-imran'
GITHUB_URL = 'https://github.com/aamir490'

CONNECTOR_OPTIONS = {
    'Athena (AWS)': 'athena',
    'Redshift (AWS)': 'redshift',
    'RDS PostgreSQL': 'rds_postgres',
    'RDS MySQL': 'rds_mysql',
    'Snowflake': 'snowflake',
    'Databricks': 'databricks',
}

SUGGESTIONS = [
    'How many books are in the library?',
    'What is the average price of cars?',
    'Top 5 most expensive cars',
    'List all genres in the library',
    'Cars with horsepower above 200',
    'Books published after 1950',
]


def _get_logo_b64() -> str:
    """Read the NovaMind SVG logo and return a base64 data URI."""
    if LOGO_PATH.exists():
        svg_content = LOGO_PATH.read_text(encoding='utf-8')
        b64 = base64.b64encode(svg_content.encode()).decode()
        return f'data:image/svg+xml;base64,{b64}'
    return ''


def _inject_custom_css():
    """Inject NovaMind dark-theme CSS with subtle data-grid background."""
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

    :root {
        --nm-bg: #070b14;
        --nm-surface: #0f1623;
        --nm-card: #141c2b;
        --nm-border: #1e2a3d;
        --nm-text: #e8edf5;
        --nm-muted: #8b9cb3;
        --nm-accent: #5b8def;
        --nm-accent-soft: rgba(91, 141, 239, 0.15);
        --nm-success: #34d399;
        --nm-glow: rgba(91, 141, 239, 0.08);
    }

    .stApp {
        background-color: var(--nm-bg);
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
        color: var(--nm-text);
    }

    [data-testid="stHeader"] {
        background: transparent;
        border-bottom: none;
    }

    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #0c1220 0%, #0a0f1a 100%);
        border-right: 1px solid var(--nm-border);
    }

    [data-testid="stSidebar"] * {
        color: var(--nm-text);
    }

    [data-testid="stMainBlockContainer"] {
        position: relative;
        z-index: 1;
        max-width: 960px;
        padding-top: 1rem;
    }

    /* ── Data grid background ── */
    .nm-bg-layer {
        position: fixed;
        inset: 0;
        pointer-events: none;
        z-index: 0;
        overflow: hidden;
    }
    .nm-grid {
        position: absolute;
        inset: 0;
        background-image:
            linear-gradient(rgba(91, 141, 239, 0.04) 1px, transparent 1px),
            linear-gradient(90deg, rgba(91, 141, 239, 0.04) 1px, transparent 1px);
        background-size: 48px 48px;
        mask-image: radial-gradient(ellipse 80% 60% at 50% 0%, black 20%, transparent 75%);
    }
    .nm-glow {
        position: absolute;
        border-radius: 50%;
        filter: blur(80px);
        opacity: 0.35;
        animation: nm-float 12s ease-in-out infinite alternate;
    }
    .nm-glow-1 {
        width: 420px; height: 420px;
        background: radial-gradient(circle, #3b5bdb 0%, transparent 70%);
        top: -120px; left: 10%;
    }
    .nm-glow-2 {
        width: 360px; height: 360px;
        background: radial-gradient(circle, #0891b2 0%, transparent 70%);
        top: 40%; right: -80px;
        animation-delay: -4s;
    }
    @keyframes nm-float {
        from { transform: translateY(0) scale(1); }
        to   { transform: translateY(20px) scale(1.05); }
    }

    /* ── Typography & cards ── */
    .nm-title {
        font-size: 1.85rem;
        font-weight: 700;
        color: var(--nm-text);
        letter-spacing: -0.02em;
        margin: 0 0 0.35rem;
    }
    .nm-subtitle {
        font-size: 1rem;
        color: var(--nm-accent);
        font-weight: 500;
        margin-bottom: 0.5rem;
    }
    .nm-desc {
        font-size: 0.92rem;
        color: var(--nm-muted);
        line-height: 1.6;
        max-width: 560px;
        margin: 0 auto;
    }
    .nm-card {
        background: var(--nm-card);
        border: 1px solid var(--nm-border);
        border-radius: 14px;
        padding: 1.25rem 1.5rem;
        margin-bottom: 1rem;
    }
    .nm-card h3 {
        font-size: 0.95rem;
        font-weight: 600;
        color: var(--nm-text);
        margin: 0 0 0.6rem;
    }
    .nm-card p, .nm-card li {
        font-size: 0.85rem;
        color: var(--nm-muted);
        line-height: 1.55;
        margin: 0 0 0.5rem;
    }
    .nm-divider {
        border: none;
        border-top: 1px solid var(--nm-border);
        margin: 2rem 0;
    }
    .nm-section-label {
        font-size: 0.72rem;
        font-weight: 600;
        color: var(--nm-muted);
        text-transform: uppercase;
        letter-spacing: 0.08em;
        margin-bottom: 0.75rem;
    }
    .nm-flow {
        display: flex;
        flex-direction: column;
        align-items: center;
        gap: 0;
        padding: 0.5rem 0;
    }
    .nm-flow-step {
        background: var(--nm-surface);
        border: 1px solid var(--nm-border);
        border-radius: 10px;
        padding: 0.55rem 1.25rem;
        font-size: 0.82rem;
        font-weight: 500;
        color: var(--nm-text);
        min-width: 180px;
        text-align: center;
    }
    .nm-flow-arrow {
        color: var(--nm-accent);
        font-size: 1rem;
        line-height: 1;
        padding: 0.2rem 0;
    }
    .nm-footer {
        text-align: center;
        font-size: 0.78rem;
        color: var(--nm-muted);
        padding: 1.5rem 0 0.5rem;
    }
    .nm-footer a {
        color: var(--nm-accent);
        text-decoration: none;
        font-weight: 500;
    }
    .nm-footer a:hover {
        text-decoration: underline;
    }
    .nm-logo {
        display: block;
        margin: 0 auto 1rem;
    }
    .nm-logo-sm { width: 120px; }
    .nm-logo-md { width: 160px; }
    .nm-logo-lg { width: 200px; }

    /* ── Hero & dashboard ── */
    .nm-hero {
        text-align: center;
        padding: 1.5rem 0 1rem;
    }
    .nm-tagline {
        font-size: 0.95rem;
        color: var(--nm-muted);
        margin-top: 0.25rem;
    }
    .nm-features {
        display: grid;
        grid-template-columns: repeat(3, 1fr);
        gap: 1rem;
        margin: 1.75rem 0 1rem;
    }
    @media (max-width: 768px) {
        .nm-features { grid-template-columns: 1fr; }
    }
    .nm-feature {
        background: var(--nm-card);
        border: 1px solid var(--nm-border);
        border-radius: 12px;
        padding: 1rem 1.1rem;
        text-align: left;
    }
    .nm-feature-title {
        font-size: 0.85rem;
        font-weight: 600;
        color: var(--nm-text);
        margin-bottom: 0.25rem;
    }
    .nm-feature-desc {
        font-size: 0.78rem;
        color: var(--nm-muted);
        line-height: 1.45;
    }

    /* ── Sidebar ── */
    .sidebar-logo {
        text-align: center;
        padding: 1rem 0 0.75rem;
        border-bottom: 1px solid var(--nm-border);
        margin-bottom: 1rem;
    }
    .sidebar-section-title {
        font-size: 0.68rem;
        font-weight: 600;
        color: var(--nm-muted);
        text-transform: uppercase;
        letter-spacing: 0.08em;
        margin: 0.85rem 0 0.45rem;
    }
    .connection-badge {
        display: inline-flex;
        align-items: center;
        gap: 0.45rem;
        padding: 0.35rem 0.8rem;
        border-radius: 20px;
        font-size: 0.75rem;
        font-weight: 500;
        background: rgba(52, 211, 153, 0.12);
        color: var(--nm-success);
        border: 1px solid rgba(52, 211, 153, 0.25);
        margin-bottom: 0.6rem;
    }
    .connection-badge::before {
        content: '';
        width: 7px;
        height: 7px;
        border-radius: 50%;
        background: var(--nm-success);
        box-shadow: 0 0 6px var(--nm-success);
    }
    .info-table {
        font-size: 0.78rem;
        color: var(--nm-muted);
        line-height: 1.7;
    }
    .info-table strong { color: var(--nm-text); }

    /* ── Query area label ── */
    .nm-query-label {
        font-size: 1.05rem;
        font-weight: 600;
        color: var(--nm-text);
        margin: 1.5rem 0 0.25rem;
    }
    .nm-query-rule {
        border: none;
        border-top: 1px solid var(--nm-border);
        margin: 0.35rem 0 1rem;
    }

    /* ── Suggestion chips ── */
    .suggestions-header {
        text-align: center;
        font-size: 0.72rem;
        color: var(--nm-muted);
        margin: 1.25rem 0 0.65rem;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        font-weight: 600;
    }
    div[data-testid="stHorizontalBlock"] button[kind="secondary"] {
        border-radius: 10px;
        border: 1px solid var(--nm-border);
        background: var(--nm-surface);
        color: var(--nm-text);
        font-size: 0.8rem;
        transition: border-color 0.2s, background 0.2s;
    }
    div[data-testid="stHorizontalBlock"] button[kind="secondary"]:hover {
        border-color: var(--nm-accent);
        background: var(--nm-accent-soft);
        color: var(--nm-text);
    }

    /* ── Login form ── */
    [data-testid="stForm"] {
        max-width: 400px;
        margin: 0 auto;
        padding: 1.75rem;
        border: 1px solid var(--nm-border);
        border-radius: 16px;
        background: var(--nm-card);
        box-shadow: 0 8px 32px rgba(0, 0, 0, 0.35);
    }

    /* ── Chat ── */
    [data-testid="stChatMessage"] {
        border-radius: 12px;
        border: 1px solid var(--nm-border);
        background: var(--nm-card);
    }
    .chat-header {
        text-align: center;
        padding: 0.5rem 0 1rem;
        border-bottom: 1px solid var(--nm-border);
        margin-bottom: 1rem;
    }

    /* ── Streamlit widget overrides ── */
    .stTextInput input, .stTextArea textarea {
        background: var(--nm-surface) !important;
        border: 1px solid var(--nm-border) !important;
        color: var(--nm-text) !important;
        border-radius: 10px !important;
    }
    .stTextInput input:focus, .stTextArea textarea:focus {
        border-color: var(--nm-accent) !important;
        box-shadow: 0 0 0 1px var(--nm-accent) !important;
    }
    .stButton > button[kind="primary"] {
        background: linear-gradient(135deg, #4c7fe0 0%, #3b5bdb 100%);
        border: none;
        border-radius: 10px;
        font-weight: 600;
        color: white;
    }
    .stButton > button[kind="primary"]:hover {
        background: linear-gradient(135deg, #5b8def 0%, #4c6ef5 100%);
        border: none;
        color: white;
    }
    .stSelectbox > div > div {
        background: var(--nm-surface);
        border-color: var(--nm-border);
        color: var(--nm-text);
    }
    label, .stMarkdown p, .stCaption, [data-testid="stMarkdownContainer"] {
        color: var(--nm-text);
    }
    .stExpander {
        background: var(--nm-surface);
        border: 1px solid var(--nm-border);
        border-radius: 10px;
    }
    hr { border-color: var(--nm-border); }

    #MainMenu { visibility: hidden; }
    footer { visibility: hidden; }
    [data-testid="stDecoration"] { display: none; }
    [data-testid="stToolbar"] { display: none; }
    .stDeployButton { display: none; }
    </style>
    """, unsafe_allow_html=True)

    st.markdown("""
    <div class="nm-bg-layer">
        <div class="nm-grid"></div>
        <div class="nm-glow nm-glow-1"></div>
        <div class="nm-glow nm-glow-2"></div>
    </div>
    """, unsafe_allow_html=True)


def _render_footer():
    st.markdown(
        f'<div class="nm-footer">'
        f'Made by Aamir &nbsp;·&nbsp; '
        f'<a href="{LINKEDIN_URL}" target="_blank" rel="noopener">LinkedIn</a>'
        f' &nbsp;|&nbsp; '
        f'<a href="{GITHUB_URL}" target="_blank" rel="noopener">GitHub</a>'
        f'</div>',
        unsafe_allow_html=True,
    )


def _render_flow_diagram():
    steps = [
        'User Question',
        'AI Understanding',
        'SQL Generation',
        'Data Query',
        'Results',
        'AI Answer / Insight',
    ]
    parts = ['<div class="nm-flow">']
    for i, step in enumerate(steps):
        parts.append(f'<div class="nm-flow-step">{step}</div>')
        if i < len(steps) - 1:
            parts.append('<div class="nm-flow-arrow">↓</div>')
    parts.append('</div>')
    st.markdown(''.join(parts), unsafe_allow_html=True)


def _render_project_about(*, compact: bool = False):
    st.markdown(
        '<div class="nm-card">'
        '<h3>What does this project do?</h3>'
        '<p><strong>NovaMind AI Data Analyst Agent</strong> lets you ask questions about '
        'structured data in plain English. The application uses Amazon Bedrock to interpret '
        'your question, generates read-only SQL against schemas discovered via AWS Glue, '
        'executes queries through Amazon Athena (with results staged in Amazon S3 when '
        'configured), and returns a natural-language answer.</p>'
        '<p>In deployed mode, this Streamlit UI can connect to a remote API behind an '
        'Application Load Balancer running on Amazon ECS/Fargate, which exposes a '
        '<code>POST /query</code> endpoint.</p>'
        '</div>',
        unsafe_allow_html=True,
    )

    st.markdown('<div class="nm-card"><h3>How does it work?</h3>', unsafe_allow_html=True)
    _render_flow_diagram()
    st.markdown(
        '<p style="font-size:0.82rem;color:#8b9cb3;margin-top:0.75rem;line-height:1.55;">'
        'Bedrock reads your question and the Glue catalog schema, produces validated '
        'read-only SQL, Athena runs the query, and Bedrock summarizes the result into '
        'a clear answer. Only SELECT/WITH statements on allowlisted tables are executed.'
        '</p></div>',
        unsafe_allow_html=True,
    )

    if not compact:
        st.markdown(
            '<div class="nm-card">'
            '<h3>Why use it?</h3>'
            '<p>Explore warehouse data without writing SQL manually. Ask business questions '
            'directly, review generated SQL when supported, and get auditable read-only '
            'query execution backed by AWS Glue schema discovery and Bedrock reasoning.</p>'
            '</div>',
            unsafe_allow_html=True,
        )


# ── Service Layer (unchanged logic) ──────────────────────────────────────────

def _parse_glue_db_names(raw: str | None, fallback: str | None) -> list[str]:
    if raw:
        names = [part.strip() for part in raw.split(',') if part.strip()]
        if names:
            return names
    if fallback:
        return [fallback]
    return []


@st.cache_resource(show_spinner=False)
def _get_local_service(_db, _bucket, _region, _workgroup):
    from llm_sql.config import get_settings as _gs
    _gs.cache_clear()
    settings = get_settings()
    runtime = require_runtime_settings(settings)
    glue_db_names = _parse_glue_db_names(
        os.environ.get('GLUE_DB_NAMES'),
        runtime.glue_db_name,
    )
    if not glue_db_names:
        raise SettingsError('Set GLUE_DB_NAME or GLUE_DB_NAMES.')
    return build_athena_service(
        glue_db_names,
        runtime.project_files_bucket,
        region=runtime.region,
        athena_workgroup=runtime.athena_workgroup,
    )


def _api_base_url() -> Optional[str]:
    url = (os.environ.get('API_URL') or st.session_state.get('api_url') or '').strip()
    if not url:
        return None
    return url.rstrip('/')


def _ask_remote(question: str) -> str:
    base = _api_base_url()
    if not base:
        raise RuntimeError('API_URL is not set.')
    headers = {'Content-Type': 'application/json'}
    api_key = os.environ.get('API_KEY') or st.session_state.get('api_key')
    if api_key:
        headers['X-Api-Key'] = api_key
    response = requests.post(
        f'{base}/query',
        json={'question': question},
        headers=headers,
        timeout=300,
    )
    if response.status_code != 200:
        detail = response.text
        try:
            detail = response.json().get('detail', detail)
        except Exception:
            pass
        raise RuntimeError(f'API error ({response.status_code}): {detail}')
    return response.json()['answer']


def _ask_local(question: str) -> str:
    db = os.environ.get('GLUE_DB_NAME', '')
    bucket = os.environ.get('PROJECT_FILES_BUCKET', '')
    region = os.environ.get('AWS_REGION', 'us-east-1')
    workgroup = os.environ.get('ATHENA_WORKGROUP', 'primary')
    service = _get_local_service(db, bucket, region, workgroup)
    return service.run_query(question)


def _ask(question: str) -> str:
    if _api_base_url():
        return _ask_remote(question)

    active_source = st.session_state.get('active_source', 'Athena (AWS)')
    selected_type = CONNECTOR_OPTIONS.get(active_source, '')

    if selected_type == 'athena':
        return _ask_local(question)

    connections = load_connections()
    matching_conn = None
    for name, config in connections.items():
        if config.get('type') == selected_type:
            matching_conn = name
            break

    if matching_conn:
        try:
            connector = get_connector(matching_conn)
            if hasattr(connector, 'run_query'):
                return connector.run_query(question)
            catalog, tables = connector.get_schema()
            return (
                f"Connected to **{matching_conn}** ({selected_type}). "
                f"Found {len(tables)} tables. "
                f"Full LLM-powered query support coming soon."
            )
        except NotImplementedError as e:
            return f"⚠️ {e}"
        except Exception as e:
            return f"⚠️ Connector error: {e}"

    return (
        f"⚠️ **{active_source}** is not configured yet.\n\n"
        f"To set it up:\n"
        f"1. Copy `config/connections/{selected_type}.yaml.template` → "
        f"`config/connections/{selected_type}.yaml`\n"
        f"2. Fill in your connection details\n"
        f"3. Restart the app"
    )


# ── UI Components ────────────────────────────────────────────────────────────

def _render_hero():
    logo_uri = _get_logo_b64()
    logo_html = (
        f'<img src="{logo_uri}" class="nm-logo nm-logo-lg" alt="NovaMind"/>'
        if logo_uri else ''
    )

    st.markdown(f"""
    <div class="nm-hero">
        {logo_html}
        <div class="nm-title">{APP_NAME}</div>
        <div class="nm-subtitle">Ask questions. Get insights. Let AI handle the SQL.</div>
        <div class="nm-desc">
            Ask questions in plain English. NovaMind generates SQL, executes it
            against your data warehouse, and delivers trusted answers in seconds.
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("""
    <div class="nm-features">
        <div class="nm-feature">
            <div class="nm-feature-title">Multi-step reasoning</div>
            <div class="nm-feature-desc">Bedrock interprets complex questions against your schema.</div>
        </div>
        <div class="nm-feature">
            <div class="nm-feature-title">Instant insights</div>
            <div class="nm-feature-desc">Read-only SQL generated and executed in seconds.</div>
        </div>
        <div class="nm-feature">
            <div class="nm-feature-title">Enterprise-grade trust</div>
            <div class="nm-feature-desc">Validated SELECT-only queries with table allowlists.</div>
        </div>
    </div>
    """, unsafe_allow_html=True)


def _render_suggestions():
    st.markdown(
        '<div class="suggestions-header">Try asking</div>',
        unsafe_allow_html=True,
    )

    cols = st.columns(3)
    for i, text in enumerate(SUGGESTIONS):
        with cols[i % 3]:
            if st.button(text, key=f'sug_{i}', use_container_width=True):
                st.session_state['pending_question'] = text
                st.rerun()


def _render_query_input() -> Optional[str]:
    st.markdown(
        '<div class="nm-query-label">Ask Your Data</div>'
        '<hr class="nm-query-rule"/>',
        unsafe_allow_html=True,
    )

    with st.form('query_form', clear_on_submit=True):
        question = st.text_input(
            'Question',
            placeholder='Ask a question about your data...',
            label_visibility='collapsed',
        )
        submitted = st.form_submit_button('Ask AI', use_container_width=False, type='primary')

    if submitted and question and question.strip():
        return question.strip()
    return None


def _render_sidebar():
    logo_uri = _get_logo_b64()

    with st.sidebar:
        if logo_uri:
            st.markdown(
                f'<div class="sidebar-logo">'
                f'<img src="{logo_uri}" class="nm-logo nm-logo-sm" alt="NovaMind"/>'
                f'</div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                '<div class="sidebar-logo">'
                '<span style="font-size:1.2rem;font-weight:700;color:#5b8def;">NovaMind</span>'
                '</div>',
                unsafe_allow_html=True,
            )

        settings = get_settings()

        st.markdown(
            '<div class="sidebar-section-title">Load Balancer URL</div>',
            unsafe_allow_html=True,
        )
        remote_url = st.text_input(
            'ALB URL',
            value=st.session_state.get('api_url', ''),
            placeholder='http://data-arch-ai-alb-xxx.elb.amazonaws.com',
            key='api_url_input',
            label_visibility='collapsed',
        )
        if remote_url:
            st.session_state['api_url'] = remote_url.strip().rstrip('/')

        st.markdown(
            '<div class="sidebar-section-title">Connection</div>',
            unsafe_allow_html=True,
        )

        if _api_base_url():
            st.markdown(
                '<div class="connection-badge">Remote API Connected</div>',
                unsafe_allow_html=True,
            )
            if not os.environ.get('API_KEY'):
                st.session_state.setdefault('api_key', '')
                st.session_state['api_key'] = st.text_input(
                    'API Key (optional)',
                    type='password',
                    key='api_key_input',
                    placeholder='X-Api-Key header',
                )
        else:
            try:
                runtime = require_runtime_settings(settings)
                st.markdown(
                    '<div class="connection-badge">Local AWS Connected</div>',
                    unsafe_allow_html=True,
                )
                st.markdown(
                    f'<div class="info-table">'
                    f'<strong>Database:</strong> {runtime.glue_db_name}<br>'
                    f'<strong>Region:</strong> {runtime.region}<br>'
                    f'<strong>Workgroup:</strong> {runtime.athena_workgroup}'
                    f'</div>',
                    unsafe_allow_html=True,
                )
            except SettingsError:
                st.markdown(
                    '<div style="padding:0.5rem 0.75rem;background:rgba(91,141,239,0.08);'
                    'border:1px solid var(--nm-border);border-radius:8px;'
                    'font-size:0.78rem;color:#8b9cb3;">'
                    '<strong>Setup needed</strong><br>'
                    'Enter a Load Balancer URL above, or fill in AWS details below.'
                    '</div>',
                    unsafe_allow_html=True,
                )

        with st.expander('AWS Configuration', expanded=not bool(_api_base_url())):
            new_db = st.text_input(
                'Glue Database',
                value=os.environ.get('GLUE_DB_NAME', st.session_state.get('cfg_glue_db', '')),
                placeholder='e.g. project_library_db',
                key='cfg_glue_db_input',
            )
            new_bucket = st.text_input(
                'S3 Bucket',
                value=os.environ.get('PROJECT_FILES_BUCKET', st.session_state.get('cfg_bucket', '')),
                placeholder='e.g. langchain-637423369471-us-east-1',
                key='cfg_bucket_input',
            )
            new_workgroup = st.text_input(
                'Athena Workgroup',
                value=os.environ.get('ATHENA_WORKGROUP', st.session_state.get('cfg_workgroup', 'project-text-to-sql')),
                placeholder='e.g. project-text-to-sql',
                key='cfg_workgroup_input',
            )
            new_region = st.text_input(
                'AWS Region',
                value=os.environ.get('AWS_REGION', st.session_state.get('cfg_region', 'us-east-1')),
                placeholder='e.g. us-east-1',
                key='cfg_region_input',
            )

            if new_db:
                st.session_state['cfg_glue_db'] = new_db
                os.environ['GLUE_DB_NAME'] = new_db
            if new_bucket:
                st.session_state['cfg_bucket'] = new_bucket
                os.environ['PROJECT_FILES_BUCKET'] = new_bucket
            if new_workgroup:
                st.session_state['cfg_workgroup'] = new_workgroup
                os.environ['ATHENA_WORKGROUP'] = new_workgroup
            if new_region:
                st.session_state['cfg_region'] = new_region
                os.environ['AWS_REGION'] = new_region

        st.divider()

        st.markdown(
            '<div class="sidebar-section-title">Data Source</div>',
            unsafe_allow_html=True,
        )

        connections = load_connections()
        configured_names = list(connections.keys())

        all_options = list(CONNECTOR_OPTIONS.keys())
        for name in configured_names:
            if name not in all_options:
                conn_type = connections[name].get('type', 'unknown')
                all_options.append(f'{name} ({conn_type})')

        current = st.session_state.get('active_source', all_options[0])
        if current not in all_options:
            current = all_options[0]

        selected = st.selectbox(
            'Active data source',
            options=all_options,
            index=all_options.index(current),
            key='source_selector',
            label_visibility='collapsed',
        )
        st.session_state['active_source'] = selected

        selected_type = CONNECTOR_OPTIONS.get(selected, '')
        if selected_type:
            has_config = any(
                c.get('type') == selected_type for c in connections.values()
            )
            if has_config or selected_type == 'athena':
                st.caption(f"Type: `{selected_type}` — configured")
            else:
                st.caption(f"No `.yaml` config found for `{selected_type}`")

        st.divider()

        col1, col2, col3 = st.columns(3)
        with col1:
            if st.button('Clear', use_container_width=True):
                st.session_state['messages'] = []
                st.rerun()
        with col2:
            if st.button('Reconnect', use_container_width=True):
                st.cache_resource.clear()
                st.rerun()
        with col3:
            if st.button('Logout', use_container_width=True):
                st.session_state['authenticated'] = False
                st.session_state['messages'] = []
                st.rerun()

        _render_footer()


def _check_login() -> bool:
    if st.session_state.get('authenticated'):
        return True

    valid_username = os.environ.get('APP_USERNAME', 'admin')
    valid_password = os.environ.get('APP_PASSWORD', 'cloudage')

    logo_uri = _get_logo_b64()
    logo_html = (
        f'<img src="{logo_uri}" class="nm-logo nm-logo-md" alt="NovaMind"/>'
        if logo_uri else ''
    )

    col_l, col_c, col_r = st.columns([1, 2, 1])
    with col_c:
        st.markdown(
            f'<div style="text-align:center;padding:2rem 0 0.5rem;">{logo_html}</div>'
            f'<div class="nm-title" style="text-align:center;font-size:1.5rem;">{APP_NAME}</div>'
            f'<div class="nm-subtitle" style="text-align:center;">AI-powered data analysis</div>'
            f'<p class="nm-desc" style="text-align:center;margin:1rem auto 1.5rem;">'
            f'Ask questions about your data using natural language instead of '
            f'manually writing SQL queries.</p>',
            unsafe_allow_html=True,
        )

        with st.form('login_form'):
            username = st.text_input('Username', placeholder='Enter username')
            password = st.text_input('Password', type='password', placeholder='Enter password')
            submitted = st.form_submit_button('Sign In', use_container_width=True)

            if submitted:
                if username == valid_username and password == valid_password:
                    st.session_state['authenticated'] = True
                    st.session_state['user'] = username
                    st.rerun()
                else:
                    st.error('Invalid username or password')

        st.markdown('<hr class="nm-divider"/>', unsafe_allow_html=True)
        _render_project_about(compact=True)
        _render_footer()

    return False


def _process_question(question: str) -> None:
    st.session_state['messages'].append({'role': 'user', 'content': question})
    with st.chat_message('user'):
        st.markdown(question)

    with st.chat_message('assistant'):
        thinking = st.empty()
        thinking.markdown(
            '<span style="color:#8b9cb3;font-size:0.85rem;">'
            'Analyzing your question and generating SQL…</span>',
            unsafe_allow_html=True,
        )
        try:
            answer = _ask(question)
            thinking.empty()
            st.markdown(answer)
            st.session_state['messages'].append({'role': 'assistant', 'content': answer})
        except Exception as exc:
            thinking.empty()
            err_msg = f"**Error:** {exc}"
            st.markdown(err_msg)
            st.session_state['messages'].append({'role': 'assistant', 'content': err_msg})


def main() -> None:
    st.set_page_config(
        page_title='NovaMind — Data Intelligence',
        page_icon='🧠',
        layout='wide',
        initial_sidebar_state='expanded',
    )

    _inject_custom_css()

    if not _check_login():
        return

    _render_sidebar()

    if 'messages' not in st.session_state:
        st.session_state['messages'] = []

    if not st.session_state['messages']:
        _render_hero()
        _render_suggestions()
        with st.expander('About This Project', expanded=False):
            _render_project_about()
    else:
        logo_uri = _get_logo_b64()
        if logo_uri:
            st.markdown(
                f'<div class="chat-header">'
                f'<img src="{logo_uri}" class="nm-logo nm-logo-sm" alt="NovaMind"/>'
                f'</div>',
                unsafe_allow_html=True,
            )

        for msg in st.session_state['messages']:
            with st.chat_message(msg['role']):
                st.markdown(msg['content'])

    pending = st.session_state.pop('pending_question', None)
    form_question = _render_query_input()
    question = pending or form_question

    if not question:
        return

    _process_question(question)
    st.rerun()


if __name__ == '__main__':
    main()
