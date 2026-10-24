/**
 * FinGuard AI — Shared Utility Library
 * "Detect anomalies. Explain risks. Protect financial integrity."
 *
 * Provides: Indian number formatting, risk badge HTML, score formatting,
 * sparkline rendering, animated counter, and DOM helpers.
 */

(function (global) {
    'use strict';

    /* ── Indian number formatting ─────────────────────────────────────── */
    function formatAmount(amount) {
        if (amount === null || amount === undefined) return '₹0';
        amount = parseFloat(amount) || 0;
        const abs = Math.abs(amount);
        const sign = amount < 0 ? '-' : '';

        if (abs >= 1e7) {                          // 1 Crore
            return sign + '₹' + (abs / 1e7).toFixed(2) + ' Cr';
        } else if (abs >= 1e5) {                   // 1 Lakh
            return sign + '₹' + (abs / 1e5).toFixed(2) + ' L';
        } else {
            // Indian comma formatting: xx,xx,xxx
            let str = Math.round(abs).toString();
            if (str.length > 3) {
                const last3 = str.slice(-3);
                const rest  = str.slice(0, -3);
                const formatted = rest.replace(/\B(?=(\d{2})+(?!\d))/g, ',');
                str = formatted + ',' + last3;
            }
            return sign + '₹' + str;
        }
    }

    /* ── Risk badge HTML ─────────────────────────────────────────────── */
    function riskBadge(level) {
        if (!level) return '<span class="finguard-badge finguard-badge-low">—</span>';
        const clean   = level.toLowerCase().replace(/\s+risk\s*/i, '').trim();
        const cls     = { high: 'finguard-badge-high', medium: 'finguard-badge-medium', low: 'finguard-badge-low' };
        const icons   = { high: '●', medium: '◆', low: '▪' };
        const badgeCls = cls[clean] || 'finguard-badge-low';
        const icon     = icons[clean] || '';
        return `<span class="finguard-badge ${badgeCls}">${icon} ${escapeHtml(level)}</span>`;
    }

    /* ── Risk colour ─────────────────────────────────────────────────── */
    function riskColor(level) {
        const clean = (level || '').toLowerCase();
        if (clean.includes('high'))   return '#e02424';
        if (clean.includes('medium')) return '#d97706';
        return '#057a55';
    }

    /* ── Score formatter ─────────────────────────────────────────────── */
    function formatScore(score) {
        const val = parseFloat(score) || 0;
        // If value is already in 0–1 range, multiply by 100
        const pct = val <= 1 ? val * 100 : val;
        return pct.toFixed(1) + '%';
    }

    /* ── Time ago ────────────────────────────────────────────────────── */
    function timeAgo(datetime) {
        if (!datetime) return '—';
        const then = new Date(datetime.replace(' ', 'T'));
        const now  = new Date();
        const diff = Math.floor((now - then) / 1000);

        if (diff < 60)   return 'just now';
        if (diff < 3600) return Math.floor(diff / 60) + ' min ago';
        if (diff < 86400)return Math.floor(diff / 3600) + ' hr ago';
        return Math.floor(diff / 86400) + ' day(s) ago';
    }

    /* ── Spinner HTML ─────────────────────────────────────────────────── */
    function renderSpinner(msg) {
        return `<div class="text-center text-muted" style="padding:40px 16px;">
            <i class="fa fa-spinner fa-spin fa-2x" style="color:#1a56db;margin-bottom:12px;display:block;"></i>
            <span style="font-size:.85rem;">${escapeHtml(msg || 'Loading…')}</span>
        </div>`;
    }

    /* ── Skeleton placeholder ─────────────────────────────────────────── */
    function renderSkeleton(rows, cols) {
        rows = rows || 5; cols = cols || 4;
        const headerCells = Array(cols).fill('<th><span class="fg-skeleton" style="width:80px;height:12px;"></span></th>').join('');
        const rowCells    = Array(cols).fill('<td><span class="fg-skeleton" style="width:90%;height:12px;"></span></td>').join('');
        const bodyRows    = Array(rows).fill(`<tr>${rowCells}</tr>`).join('');
        return `<table class="finguard-alert-table table">
            <thead><tr>${headerCells}</tr></thead>
            <tbody>${bodyRows}</tbody>
        </table>`;
    }

    /* ── Score progress bar HTML ─────────────────────────────────────── */
    function scoreBar(score, width) {
        width = width || 100;
        const val  = parseFloat(score) || 0;
        const pct  = val <= 1 ? val * 100 : val;
        const color = pct >= 75 ? '#e02424' : pct >= 45 ? '#d97706' : '#057a55';
        return `<span class="finguard-score-bar" style="width:${width}px;">
            <span class="finguard-score-fill" style="width:${Math.min(pct,100)}%;background:${color};"></span>
        </span>
        <span class="finguard-score-text">${pct.toFixed(1)}%</span>`;
    }

    /* ── Animated number counter ─────────────────────────────────────── */
    function animateCounter(element, targetValue, duration) {
        if (!element) return;
        duration = duration || 800;
        const start     = parseFloat(element.textContent) || 0;
        const end       = parseFloat(targetValue) || 0;
        const startTime = performance.now();

        function step(now) {
            const elapsed  = now - startTime;
            const progress = Math.min(elapsed / duration, 1);
            // ease-out cubic
            const eased    = 1 - Math.pow(1 - progress, 3);
            const current  = start + (end - start) * eased;

            // Preserve original formatting if the target looks like currency
            if (typeof targetValue === 'string' && targetValue.includes('₹')) {
                element.textContent = targetValue; // just set directly
            } else {
                element.textContent = Number.isInteger(end)
                    ? Math.round(current)
                    : current.toFixed(1);
            }

            if (progress < 1) requestAnimationFrame(step);
        }
        requestAnimationFrame(step);
    }

    /* ── Chart colour palette ─────────────────────────────────────────── */
    const chartColors = {
        high:    '#e02424',
        medium:  '#d97706',
        low:     '#057a55',
        primary: '#1a56db',
        neutral: '#6b7280',
        shades:  ['#1a56db', '#3b82f6', '#93c5fd', '#bfdbfe', '#dbeafe'],
    };

    /* ── HTML escape ──────────────────────────────────────────────────── */
    function escapeHtml(str) {
        if (!str) return '';
        return String(str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#039;');
    }

    /* ── Toast notification ───────────────────────────────────────────── */
    function toast(message, type) {
        // Falls back to frappe.show_alert if available
        if (typeof frappe !== 'undefined' && frappe.show_alert) {
            const indicator = { success: 'green', error: 'red', warning: 'orange', info: 'blue' }[type] || 'blue';
            frappe.show_alert({ message: message, indicator: indicator }, 5);
        } else {
            console.log('[FinGuard]', type, message);
        }
    }

    /* ── Export ───────────────────────────────────────────────────────── */
    global.FinGuard = {
        formatAmount,
        riskBadge,
        riskColor,
        formatScore,
        timeAgo,
        renderSpinner,
        renderSkeleton,
        scoreBar,
        animateCounter,
        chartColors,
        escapeHtml,
        toast,
    };

}(typeof window !== 'undefined' ? window : global));
