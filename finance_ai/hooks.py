# -*- coding: utf-8 -*-
"""
FinGuard AI – Frappe Hooks
Defines all integration points with the Frappe/ERPNext framework.
"""

app_name = 'finance_ai'
app_title = 'FinGuard AI'
app_publisher = 'FinGuard AI'
app_description = 'AI-Powered Financial Anomaly Detection & Investigation System for ERPNext'
app_icon = 'octicon octicon-shield'
app_color = '#1a56db'
app_email = 'admin@finguard.ai'
app_license = 'MIT'
app_version = '1.0.0'

# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------
required_apps = ['erpnext']

# ---------------------------------------------------------------------------
# Install / uninstall hooks
# ---------------------------------------------------------------------------
after_install = 'finance_ai.install.after_install'

# ---------------------------------------------------------------------------
# Document Events
# Triggered synchronously when a user submits a Journal Entry or Payment Entry
# so that anomalies are flagged in near-real-time.
# ---------------------------------------------------------------------------
doc_events = {
    'Journal Entry': {
        'on_submit': 'finance_ai.anomaly_engine.scanner.quick_scan',
    },
    'Payment Entry': {
        'on_submit': 'finance_ai.anomaly_engine.scanner.quick_scan',
    },
}

# ---------------------------------------------------------------------------
# Scheduled Tasks
# ---------------------------------------------------------------------------
scheduler_events = {
    'daily': [
        'finance_ai.scheduled_tasks.run_anomaly_scan.run_full_scan',
    ],
    'hourly': [
        'finance_ai.scheduled_tasks.run_anomaly_scan.run_delta_scan',
    ],
}

# ---------------------------------------------------------------------------
# Fixtures – DocTypes whose records are bundled with the app
# ---------------------------------------------------------------------------
fixtures = [
    'Financial Anomaly Alert',
    'Anomaly Investigation',
    'Anomaly Model Log',
    'FinGuard Settings',
]

# ---------------------------------------------------------------------------
# Website
# ---------------------------------------------------------------------------
website_route_rules = []

# ---------------------------------------------------------------------------
# UI / Portal
# ---------------------------------------------------------------------------
# Pages exposed on the portal (none for now)
website_generators = []

# Role Home Page mapping
role_home_page = {}

# ---------------------------------------------------------------------------
# Permissions
# ---------------------------------------------------------------------------
# Additional permission overrides (module-level)
permission_query_conditions = {}
has_permission = {}

# ---------------------------------------------------------------------------
# DocType class overrides
# ---------------------------------------------------------------------------
override_doctype_class = {}

# ---------------------------------------------------------------------------
# Form overrides (JS)
# ---------------------------------------------------------------------------
doctype_js = {}
doctype_list_js = {}
doctype_tree_js = {}
doctype_calendar_js = {}

# ---------------------------------------------------------------------------
# Report overrides
# ---------------------------------------------------------------------------
override_doctype_dashboards = {}

# ---------------------------------------------------------------------------
# Jinja customisations
# ---------------------------------------------------------------------------
jinja = {
    'methods': [],
    'filters': [],
}

# ---------------------------------------------------------------------------
# On-update hooks (run after every migrate)
# ---------------------------------------------------------------------------
after_migrate = []

# ---------------------------------------------------------------------------
# Boot session
# ---------------------------------------------------------------------------
boot_session = 'finance_ai.startup.boot_session'

# ---------------------------------------------------------------------------
# Notification / email hooks
# ---------------------------------------------------------------------------
sounds = []
