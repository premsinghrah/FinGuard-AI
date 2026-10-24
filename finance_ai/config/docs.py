# -*- coding: utf-8 -*-
from frappe import _


def get_data():
    """Return documentation metadata for auto-generated docs pages."""
    return {
        'title': _('FinGuard AI'),
        'description': _('AI-Powered Financial Anomaly Detection & Investigation System for ERPNext'),
        'version': '1.0.0',
        'metatags': {
            'keywords': 'anomaly detection, finance, ERPNext, machine learning, fraud prevention'
        }
    }
