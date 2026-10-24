# -*- coding: utf-8 -*-
from frappe import _


def get_data():
    """Return module tile definition for the Frappe desk home screen."""
    return [
        {
            'module_name': 'Finance AI',
            'category': 'Modules',
            'label': _('FinGuard AI'),
            'color': '#1a56db',
            'icon': 'octicon octicon-shield',
            'type': 'module',
            'description': 'AI-Powered Financial Anomaly Detection & Investigation'
        }
    ]
