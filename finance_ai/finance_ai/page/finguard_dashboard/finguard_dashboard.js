// Copyright (c) 2024, FinGuard AI and contributors
// FinGuard AI — Risk Dashboard Page

frappe.pages['finguard-dashboard'].on_page_load = function (wrapper) {
    var page = frappe.ui.make_app_page({
        parent: wrapper,
        title: 'FinGuard AI \u2014 Risk Dashboard',
        single_column: true,
    });
    new FinGuardDashboard(page);
};

// ─────────────────────────────────────────────────────────────────────────────
// FinGuardDashboard Class
// ─────────────────────────────────────────────────────────────────────────────
class FinGuardDashboard {
    constructor(page) {
        this.page       = page;
        this.company    = frappe.defaults.get_default('company') || null;
        this.from_date  = frappe.datetime.add_days(frappe.datetime.get_today(), -30);
        this.to_date    = frappe.datetime.get_today();
        this.charts     = {};

        // Load shared CSS (bundled via hooks.py app_include_css)
        this._injectCSS();
        this.add_filters();
        this.make();
        this.refresh();
    }

    // ── inject CSS if not already present ────────────────────────────────────
    _injectCSS() {
        if (!document.getElementById('finguard-css')) {
            const link = document.createElement('link');
            link.id   = 'finguard-css';
            link.rel  = 'stylesheet';
            link.href = '/assets/finance_ai/css/finguard.css';
            document.head.appendChild(link);
        }
        if (!document.getElementById('finguard-util-js')) {
            const script = document.createElement('script');
            script.id  = 'finguard-util-js';
            script.src = '/assets/finance_ai/js/finguard.js';
            document.head.appendChild(script);
        }
    }

    // ── page-level filter fields ──────────────────────────────────────────────
    add_filters() {
        const me = this;

        // Company filter
        me.company_field = me.page.add_field({
            fieldname:  'company',
            label:      __('Company'),
            fieldtype:  'Link',
            options:    'Company',
            default:    frappe.defaults.get_default('company'),
            change() {
                me.company = this.get_value();
                me.refresh();
            },
        });

        // From Date
        me.from_date_field = me.page.add_field({
            fieldname:  'from_date',
            label:      __('From Date'),
            fieldtype:  'Date',
            default:    me.from_date,
            change() {
                me.from_date = this.get_value();
                me.refresh();
            },
        });

        // To Date
        me.to_date_field = me.page.add_field({
            fieldname:  'to_date',
            label:      __('To Date'),
            fieldtype:  'Date',
            default:    me.to_date,
            change() {
                me.to_date = this.get_value();
                me.refresh();
            },
        });

        // Refresh button
        me.page.add_inner_button(__('Refresh'), () => me.refresh())
            .addClass('btn-default');

        // Manual scan button
        me.page.set_primary_action(__('Run Manual Scan'), () => me.run_manual_scan(), 'octicon octicon-pulse');
    }

    // ── build skeleton HTML ───────────────────────────────────────────────────
    make() {
        const me = this;
        me.page.main.html(`
            <div class="finguard-dashboard-container">

                <!-- ── Premium Header ── -->
                <div class="finguard-dashboard-header">
                    <div class="finguard-header-inner">
                        <div class="finguard-header-brand">
                            <span class="finguard-logo-icon"><i class="fa fa-shield"></i></span>
                            <div>
                                <h2 class="finguard-brand-title">
                                    FinGuard AI
                                    <span class="finguard-brand-badge">Live</span>
                                </h2>
                                <p class="finguard-brand-sub">Intelligent Financial Anomaly Detection &amp; Risk Intelligence Platform</p>
                            </div>
                        </div>
                        <div class="finguard-header-right">
                            <div class="finguard-header-stats">
                                <div class="finguard-hstat">
                                    <div class="finguard-hstat-value" id="hstat-total">—</div>
                                    <div class="finguard-hstat-label">Total Alerts</div>
                                </div>
                                <div class="finguard-hstat">
                                    <div class="finguard-hstat-value risk-high" id="hstat-high">—</div>
                                    <div class="finguard-hstat-label">High Risk</div>
                                </div>
                            </div>
                            <div class="finguard-header-meta" id="finguard-last-updated">
                                <i class="fa fa-clock-o"></i> Last updated: —
                            </div>
                        </div>
                    </div>
                </div>

                <!-- ── KPI Cards ── -->
                <div class="finguard-section-label">Key Performance Indicators</div>
                <div class="finguard-kpi-grid" id="finguard-kpi-grid">
                    ${me._kpi_skeleton()}
                </div>

                <!-- ── Charts ── -->
                <div class="finguard-section-label">Risk Analytics</div>
                <div class="finguard-charts-row">
                    <div class="finguard-chart-container" id="finguard-trend-container">
                        <div class="finguard-chart-header">
                            <div>
                                <h4 class="finguard-chart-title"><i class="fa fa-line-chart"></i> Risk Alert Trend</h4>
                                <span class="finguard-chart-sub">Daily alert counts by severity level — last 30 days</span>
                            </div>
                        </div>
                        <div id="finguard-trend-chart" class="finguard-chart-body">
                            ${FinGuard ? FinGuard.renderSpinner() : '<div class="text-center text-muted"><i class="fa fa-spinner fa-spin"></i></div>'}
                        </div>
                    </div>

                    <div class="finguard-chart-container" id="finguard-rule-container">
                        <div class="finguard-chart-header">
                            <div>
                                <h4 class="finguard-chart-title"><i class="fa fa-bar-chart"></i> Rule Triggers</h4>
                                <span class="finguard-chart-sub">Most frequently triggered detection rules</span>
                            </div>
                        </div>
                        <div id="finguard-rule-chart" class="finguard-chart-body">
                            ${FinGuard ? FinGuard.renderSpinner() : '<div class="text-center text-muted"><i class="fa fa-spinner fa-spin"></i></div>'}
                        </div>
                    </div>
                </div>

                <!-- ── Top Alerts Table ── -->
                <div class="finguard-section-label">Alerts &amp; Investigations</div>
                <div class="finguard-section">
                    <div class="finguard-section-header">
                        <h4 class="finguard-section-title">
                            <i class="fa fa-exclamation-triangle"></i>
                            Top Open Alerts
                        </h4>
                        <div class="finguard-section-actions">
                            <a href="/app/financial-anomaly-alert" class="finguard-view-all">
                                View All <i class="fa fa-arrow-right" style="font-size:.65rem;"></i>
                            </a>
                        </div>
                    </div>
                    <div id="finguard-alerts-table">
                        <div class="text-center text-muted" style="padding:40px;">
                            <i class="fa fa-spinner fa-spin"></i> Loading alerts…
                        </div>
                    </div>
                </div>

                <!-- ── Party Risk Map ── -->
                <div class="finguard-section-label">Counterparty Intelligence</div>
                <div class="finguard-section">
                    <div class="finguard-section-header">
                        <h4 class="finguard-section-title">
                            <i class="fa fa-users"></i>
                            Top Parties by Alert Count
                        </h4>
                    </div>
                    <div id="finguard-party-table">
                        <div class="text-center text-muted" style="padding:40px;">
                            <i class="fa fa-spinner fa-spin"></i> Loading parties…
                        </div>
                    </div>
                </div>

            </div>
        `);
    }

    _kpi_skeleton() {
        return `
            <div class="finguard-kpi-card finguard-kpi-total">
                <div class="finguard-kpi-card-accent"></div>
                <div class="finguard-kpi-inner">
                    <div class="finguard-kpi-icon"><i class="fa fa-bell"></i></div>
                    <div class="finguard-kpi-body">
                        <div class="finguard-kpi-value" id="kpi-total">—</div>
                        <div class="finguard-kpi-label">Total Alerts</div>
                    </div>
                </div>
                <div class="finguard-kpi-footer">
                    <span class="finguard-kpi-trend fg-trend-flat"><i class="fa fa-minus"></i> —</span>
                    <span class="finguard-kpi-trend-label">vs last period</span>
                </div>
            </div>
            <div class="finguard-kpi-card finguard-kpi-high">
                <div class="finguard-kpi-card-accent"></div>
                <div class="finguard-kpi-inner">
                    <div class="finguard-kpi-icon"><i class="fa fa-exclamation-circle"></i></div>
                    <div class="finguard-kpi-body">
                        <div class="finguard-kpi-value risk-high" id="kpi-high">—</div>
                        <div class="finguard-kpi-label">High Risk Alerts</div>
                    </div>
                </div>
                <div class="finguard-kpi-footer">
                    <span class="finguard-kpi-trend fg-trend-flat"><i class="fa fa-minus"></i> —</span>
                    <span class="finguard-kpi-trend-label">needs immediate review</span>
                </div>
            </div>
            <div class="finguard-kpi-card finguard-kpi-open">
                <div class="finguard-kpi-card-accent"></div>
                <div class="finguard-kpi-inner">
                    <div class="finguard-kpi-icon"><i class="fa fa-folder-open"></i></div>
                    <div class="finguard-kpi-body">
                        <div class="finguard-kpi-value" id="kpi-open">—</div>
                        <div class="finguard-kpi-label">Open Alerts</div>
                    </div>
                </div>
                <div class="finguard-kpi-footer">
                    <span class="finguard-kpi-trend fg-trend-flat"><i class="fa fa-minus"></i> —</span>
                    <span class="finguard-kpi-trend-label">pending action</span>
                </div>
            </div>
            <div class="finguard-kpi-card finguard-kpi-amount">
                <div class="finguard-kpi-card-accent"></div>
                <div class="finguard-kpi-inner">
                    <div class="finguard-kpi-icon"><i class="fa fa-inr"></i></div>
                    <div class="finguard-kpi-body">
                        <div class="finguard-kpi-value" id="kpi-amount">—</div>
                        <div class="finguard-kpi-label">Amount at Risk</div>
                    </div>
                </div>
                <div class="finguard-kpi-footer">
                    <span class="finguard-kpi-trend fg-trend-flat"><i class="fa fa-minus"></i> —</span>
                    <span class="finguard-kpi-trend-label">total exposure</span>
                </div>
            </div>
        `;
    }

    // ── main refresh orchestrator ─────────────────────────────────────────────
    refresh() {
        const me = this;
        me._load_summary();
        me._load_trend();
        me._load_top_alerts();
        me._load_rule_breakdown();
        me._load_party_map();

        // Update timestamp
        const el = document.getElementById('finguard-last-updated');
        if (el) el.innerHTML = `<i class="fa fa-clock-o"></i> Last updated: ${frappe.datetime.now_datetime()}`;
    }

    // ── KPI summary ───────────────────────────────────────────────────────────
    _load_summary() {
        const me = this;
        frappe.call({
            method: 'finance_ai.api.dashboard.get_dashboard_summary',
            args: {
                company:   me.company,
                from_date: me.from_date,
                to_date:   me.to_date,
            },
            callback(r) {
                if (r.message) me.render_kpi_cards(r.message);
            },
        });
    }

    render_kpi_cards(summary) {
        const fmt = (v) => (window.FinGuard ? FinGuard.formatAmount(v) : '₹' + (v || 0).toLocaleString('en-IN'));

        const set = (id, val) => {
            const el = document.getElementById(id);
            if (el) el.textContent = val;
        };

        const total  = summary.total_alerts       || 0;
        const high   = summary.high_risk_count     || 0;
        const open   = summary.open_alerts         || 0;
        const amount = fmt(summary.total_amount_at_risk || 0);

        set('kpi-total',  total);
        set('kpi-high',   high);
        set('kpi-open',   open);
        set('kpi-amount', amount);

        // Mirror in header mini-stats
        set('hstat-total', total);
        set('hstat-high',  high);

        // Animate counters if FinGuard util available
        if (window.FinGuard && FinGuard.animateCounter) {
            FinGuard.animateCounter(document.getElementById('kpi-total'), total, 700);
            FinGuard.animateCounter(document.getElementById('kpi-high'),  high,  700);
            FinGuard.animateCounter(document.getElementById('kpi-open'),  open,  700);
        }

        // Update KPI footer hints based on values
        const highCard = document.querySelector('.finguard-kpi-high .finguard-kpi-trend');
        if (highCard) {
            if (high > 0) {
                highCard.className = 'finguard-kpi-trend fg-trend-up';
                highCard.innerHTML = `<i class="fa fa-arrow-up"></i> ${high} critical`;
            } else {
                highCard.className = 'finguard-kpi-trend fg-trend-down';
                highCard.innerHTML = `<i class="fa fa-check"></i> All clear`;
            }
        }
    }

    // ── Risk trend chart ─────────────────────────────────────────────────────
    _load_trend() {
        const me = this;
        frappe.call({
            method: 'finance_ai.api.dashboard.get_risk_trend',
            args: { company: me.company, days: 30 },
            callback(r) {
                if (r.message) me.render_risk_trend_chart(r.message);
            },
        });
    }

    render_risk_trend_chart(data) {
        const container = document.getElementById('finguard-trend-chart');
        if (!container || !data || data.length === 0) {
            if (container) container.innerHTML = '<p class="text-muted text-center" style="padding:40px">No data available.</p>';
            return;
        }

        const labels = data.map(d => d.date);
        const high   = data.map(d => d.high   || 0);
        const medium = data.map(d => d.medium  || 0);
        const low    = data.map(d => d.low    || 0);

        container.innerHTML = '';

        try {
            if (this.charts.trend) {
                this.charts.trend.update({ labels, datasets: [
                    { name: 'High',   values: high   },
                    { name: 'Medium', values: medium },
                    { name: 'Low',    values: low    },
                ]});
            } else {
                this.charts.trend = new frappe.Chart(container, {
                    type:    'line',
                    height:  260,
                    colors:  ['#e02424', '#d97706', '#057a55'],
                    data: {
                        labels,
                        datasets: [
                            { name: 'High',   values: high   },
                            { name: 'Medium', values: medium },
                            { name: 'Low',    values: low    },
                        ],
                    },
                    lineOptions: { regionFill: 0, hideDots: 0 },
                    tooltipOptions: { formatTooltipX: d => d, formatTooltipY: d => d + ' alert(s)' },
                });
            }
        } catch (e) {
            container.innerHTML = '<p class="text-muted text-center">Chart unavailable.</p>';
        }
    }

    // ── Rule breakdown chart ─────────────────────────────────────────────────
    _load_rule_breakdown() {
        const me = this;
        frappe.call({
            method: 'finance_ai.api.dashboard.get_rule_breakdown',
            callback(r) {
                if (r.message) me.render_rule_breakdown_chart(r.message);
            },
        });
    }

    render_rule_breakdown_chart(data) {
        const container = document.getElementById('finguard-rule-chart');
        if (!container || !data || data.length === 0) {
            if (container) container.innerHTML = '<p class="text-muted text-center" style="padding:40px">No rule data available.</p>';
            return;
        }

        const labels = data.map(d => d.rule);
        const values = data.map(d => d.count);

        container.innerHTML = '';

        try {
            this.charts.rule = new frappe.Chart(container, {
                type:    'bar',
                height:  260,
                colors:  ['#1a56db'],
                data: {
                    labels,
                    datasets: [{ name: 'Triggers', values }],
                },
                barOptions: { spaceRatio: 0.3 },
            });
        } catch (e) {
            container.innerHTML = '<p class="text-muted text-center">Chart unavailable.</p>';
        }
    }

    // ── Top alerts table ─────────────────────────────────────────────────────
    _load_top_alerts() {
        const me = this;
        frappe.call({
            method: 'finance_ai.api.dashboard.get_top_alerts',
            args: { company: me.company, limit: 10 },
            callback(r) {
                if (r.message) me.render_top_alerts_table(r.message);
            },
        });
    }

    render_top_alerts_table(alerts) {
        const container = document.getElementById('finguard-alerts-table');
        if (!container) return;

        if (!alerts || alerts.length === 0) {
            container.innerHTML = `
                <div class="finguard-empty-state">
                    <div class="fg-empty-icon"><i class="fa fa-check"></i></div>
                    <p>No open alerts found</p>
                    <small>All transactions are within expected parameters</small>
                </div>`;
            return;
        }

        const badge = (level) => window.FinGuard ? FinGuard.riskBadge(level) : `<span>${level}</span>`;
        const fmt   = (v)     => window.FinGuard ? FinGuard.formatAmount(v) : '₹' + (v || 0).toLocaleString('en-IN');

        const rows = alerts.map((a, idx) => `
            <tr>
                <td class="fg-row-num">${String(idx + 1).padStart(2, '0')}</td>
                <td>
                    <a href="/app/financial-anomaly-alert/${a.name}" class="finguard-alert-link">
                        ${frappe.utils.escape_html(a.alert_title || a.name)}
                    </a>
                </td>
                <td>${badge(a.risk_level)}</td>
                <td>
                    <div class="fg-score-cell">
                        <div class="finguard-score-bar">
                            <div class="finguard-score-fill" style="width:${Math.round(a.risk_score || 0)}%; background:${_scoreColor(a.risk_score)};"></div>
                        </div>
                        <span class="finguard-score-text">${Math.round(a.risk_score || 0)}%</span>
                    </div>
                </td>
                <td class="fg-party-name">${frappe.utils.escape_html(a.party || '—')}</td>
                <td class="fg-amount text-right">${fmt(a.transaction_amount)}</td>
                <td class="fg-date">${frappe.datetime.str_to_user(a.posting_date) || '—'}</td>
                <td><span class="finguard-status-pill finguard-status-${frappe.scrub(a.status || 'open')}">${frappe.utils.escape_html(a.status || 'Open')}</span></td>
                <td>
                    <a href="/app/financial-anomaly-alert/${a.name}" class="fg-btn-investigate">
                        <i class="fa fa-search"></i> Investigate
                    </a>
                </td>
            </tr>
        `).join('');

        container.innerHTML = `
            <div class="finguard-table-wrap">
                <table class="finguard-alert-table">
                    <thead>
                        <tr>
                            <th style="width:36px">#</th>
                            <th>Alert</th>
                            <th>Risk Level</th>
                            <th style="width:150px">Score</th>
                            <th>Party</th>
                            <th class="text-right">Amount</th>
                            <th>Date</th>
                            <th>Status</th>
                            <th></th>
                        </tr>
                    </thead>
                    <tbody>${rows}</tbody>
                </table>
            </div>
            <div class="finguard-table-footer">
                <span class="finguard-table-footer-text">Showing top ${alerts.length} open alert${alerts.length !== 1 ? 's' : ''} · Sorted by risk score</span>
                <a href="/app/financial-anomaly-alert" class="finguard-view-all">View all alerts</a>
            </div>`;
    }

    // ── Party risk map table ─────────────────────────────────────────────────
    _load_party_map() {
        const me = this;
        frappe.call({
            method: 'finance_ai.api.dashboard.get_party_risk_map',
            args: { company: me.company, limit: 15 },
            callback(r) {
                if (r.message) me._render_party_table(r.message);
            },
        });
    }

    _render_party_table(data) {
        const container = document.getElementById('finguard-party-table');
        if (!container) return;

        if (!data || data.length === 0) {
            container.innerHTML = `
                <div class="finguard-empty-state">
                    <div class="fg-empty-icon"><i class="fa fa-users"></i></div>
                    <p>No party data available</p>
                    <small>Run a scan to populate counterparty intelligence</small>
                </div>`;
            return;
        }

        const maxCount = Math.max(...data.map(d => d.alert_count || 1));
        const fmt = (v) => window.FinGuard ? FinGuard.formatAmount(v) : '₹' + (v || 0).toLocaleString('en-IN');

        const scoreColor = (s) => {
            s = parseFloat(s) || 0;
            if (s >= 75) return 'risk-high';
            if (s >= 50) return 'risk-medium';
            return 'risk-low';
        };

        const rows = data.map((d, idx) => {
            const pct = Math.round(((d.alert_count || 0) / maxCount) * 100);
            return `
                <tr>
                    <td class="fg-row-num">${String(idx + 1).padStart(2, '0')}</td>
                    <td>
                        <span class="fg-party-name">${frappe.utils.escape_html(d.party || 'Unknown')}</span>
                        <span class="fg-party-type">${frappe.utils.escape_html(d.party_type || '')}</span>
                    </td>
                    <td>
                        <div class="finguard-bar-wrap">
                            <div class="finguard-bar-track">
                                <div class="finguard-bar-fill" style="width:${pct}%;"></div>
                            </div>
                            <span class="finguard-bar-count">${d.alert_count}</span>
                        </div>
                    </td>
                    <td>
                        <span class="${scoreColor(d.avg_risk_score)}" style="font-weight:700;font-size:.82rem;">${d.avg_risk_score}%</span>
                    </td>
                    <td class="fg-amount text-right">${fmt(d.total_amount)}</td>
                </tr>`;
        }).join('');

        container.innerHTML = `
            <div class="finguard-table-wrap">
                <table class="finguard-alert-table">
                    <thead>
                        <tr>
                            <th style="width:36px">#</th>
                            <th>Party</th>
                            <th>Alert Distribution</th>
                            <th>Avg Risk Score</th>
                            <th class="text-right">Total Exposure</th>
                        </tr>
                    </thead>
                    <tbody>${rows}</tbody>
                </table>
            </div>
            <div class="finguard-table-footer">
                <span class="finguard-table-footer-text">Top ${data.length} counterparties by alert frequency</span>
            </div>`;
    }

    // ── Manual scan ──────────────────────────────────────────────────────────
    run_manual_scan() {
        const me = this;

        frappe.confirm(
            __('Run a full anomaly scan for the selected date range? This may take a few minutes.'),
            () => {
                me.page.set_primary_action(__('Scanning…'), null, 'octicon octicon-sync');
                frappe.show_alert({ message: __('Anomaly scan started…'), indicator: 'blue' });

                frappe.call({
                    method: 'finance_ai.api.dashboard.run_manual_scan',
                    args: {
                        company:   me.company,
                        from_date: me.from_date,
                        to_date:   me.to_date,
                    },
                    callback(r) {
                        me.page.set_primary_action(__('Run Manual Scan'), () => me.run_manual_scan(), 'octicon octicon-pulse');
                        if (r.message) {
                            frappe.show_alert({
                                message: __('Scan complete. {0} alert(s) generated.', [r.message.alerts_created || 0]),
                                indicator: 'green',
                            });
                            me.refresh();
                        }
                    },
                    error() {
                        me.page.set_primary_action(__('Run Manual Scan'), () => me.run_manual_scan(), 'octicon octicon-pulse');
                    },
                });
            }
        );
    }
}

// ── internal helper (outside class) ──────────────────────────────────────────
function _scoreColor(score) {
    score = parseFloat(score) || 0;
    if (score >= 75) return '#e02424';
    if (score >= 50) return '#d97706';
    return '#057a55';
}
