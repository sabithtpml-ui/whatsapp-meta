# -*- coding: utf-8 -*-
{
    'name': 'WhatsApp AI Integration',
    'version': '16.0.1.0.0',
    'category': 'Sales/CRM',
    'summary': 'WhatsApp Meta Cloud API + LLM Chatbot with Odoo Sales, Discuss & Reporting',
    'description': """
        WhatsApp AI Integration for Odoo 16
        =====================================
        * WhatsApp Meta Cloud API integration
        * Auto-send WhatsApp on Sale Order confirmation
        * Receive replies in Odoo Discuss (mail.channel)
        * LLM chatbot (Claude / GPT) for creating orders,
          querying customers, generating reports
        * Full conversation history & message logging
        * OWL-based standalone dashboard
        * REST API for external access
    """,
    'author': 'Custom',
    'depends': [
        'base',
        'sale_management',
        'mail',
        'contacts',
        'stock',
        'account',
        'product',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/ir_cron_data.xml',
        'data/mail_template_data.xml',
        'views/res_config_settings_views.xml',
        'views/whatsapp_message_views.xml',
        'views/whatsapp_conversation_views.xml',
        'views/whatsapp_compose_wizard_views.xml',
        'views/sale_order_views.xml',
        'views/res_partner_views.xml',
        'views/menu_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'whatsapp_ai_integration/static/src/css/whatsapp.css',
            'whatsapp_ai_integration/static/src/js/whatsapp_app.js',
            'whatsapp_ai_integration/static/src/xml/whatsapp_templates.xml',
        ],
    },
    'installable': True,
    'application': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
