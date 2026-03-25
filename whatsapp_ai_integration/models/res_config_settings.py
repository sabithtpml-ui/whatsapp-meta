# -*- coding: utf-8 -*-
import logging
from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    # ── WhatsApp Meta Cloud API ──────────────────────────────────
    wa_phone_number_id = fields.Char(
        string="WhatsApp Phone Number ID",
        config_parameter='whatsapp_ai.phone_number_id',
    )
    wa_business_account_id = fields.Char(
        string="WhatsApp Business Account ID",
        config_parameter='whatsapp_ai.business_account_id',
    )
    wa_access_token = fields.Char(
        string="WhatsApp Access Token",
        config_parameter='whatsapp_ai.access_token',
    )
    wa_verify_token = fields.Char(
        string="Webhook Verify Token",
        config_parameter='whatsapp_ai.verify_token',
        default='odoo_whatsapp_verify_token',
    )
    wa_api_version = fields.Char(
        string="API Version",
        config_parameter='whatsapp_ai.api_version',
        default='v21.0',
    )

    # ── LLM Configuration ────────────────────────────────────────
    llm_provider = fields.Selection(
        [('anthropic', 'Anthropic (Claude)'), ('openai', 'OpenAI (GPT)')],
        string="LLM Provider",
        config_parameter='whatsapp_ai.llm_provider',
        default='anthropic',
    )
    llm_api_key = fields.Char(
        string="LLM API Key",
        config_parameter='whatsapp_ai.llm_api_key',
    )
    llm_model = fields.Char(
        string="LLM Model",
        config_parameter='whatsapp_ai.llm_model',
        default='claude-sonnet-4-20250514',
    )
    llm_system_prompt = fields.Text(
        string="System Prompt Override",
        config_parameter='whatsapp_ai.llm_system_prompt',
    )

    # ── Feature Toggles ──────────────────────────────────────────
    wa_auto_send_so = fields.Boolean(
        string="Auto-send on SO Confirmation",
        config_parameter='whatsapp_ai.auto_send_so',
        default=True,
    )
    wa_chatbot_enabled = fields.Boolean(
        string="Enable AI Chatbot",
        config_parameter='whatsapp_ai.chatbot_enabled',
        default=True,
    )
    wa_so_template_name = fields.Char(
        string="SO Notification Template Name",
        config_parameter='whatsapp_ai.so_template_name',
    )

    def action_test_whatsapp_connection(self):
        self.ensure_one()
        result = self.env['whatsapp.api']._get_business_profile()
        notif = 'success' if result.get('success') else 'danger'
        msg = 'WhatsApp API connected!' if result.get('success') else result.get('error', 'Unknown')
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'WhatsApp Connection',
                'message': msg,
                'type': notif,
                'sticky': notif == 'danger',
            },
        }

    def action_test_llm_connection(self):
        self.ensure_one()
        result = self.env['whatsapp.llm.engine']._test_connection()
        notif = 'success' if result.get('success') else 'danger'
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'LLM Test',
                'message': result.get('message', ''),
                'type': notif,
                'sticky': notif == 'danger',
            },
        }
