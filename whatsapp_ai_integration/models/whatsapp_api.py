# -*- coding: utf-8 -*-
import json
import logging
import requests

from odoo import api, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

WA_BASE_URL = "https://graph.facebook.com"


class WhatsAppAPI(models.AbstractModel):
    _name = 'whatsapp.api'
    _description = 'WhatsApp Cloud API Interface'

    def _get_config(self):
        ICP = self.env['ir.config_parameter'].sudo()
        return {
            'phone_number_id': ICP.get_param('whatsapp_ai.phone_number_id', ''),
            'access_token': ICP.get_param('whatsapp_ai.access_token', ''),
            'api_version': ICP.get_param('whatsapp_ai.api_version', 'v21.0'),
            'verify_token': ICP.get_param('whatsapp_ai.verify_token', ''),
        }

    def _base_url(self):
        cfg = self._get_config()
        return "{}/{}/{}".format(WA_BASE_URL, cfg['api_version'], cfg['phone_number_id'])

    def _headers(self):
        cfg = self._get_config()
        return {
            'Authorization': 'Bearer %s' % cfg['access_token'],
            'Content-Type': 'application/json',
        }

    # ── Public API ────────────────────────────────────────────────

    def _get_business_profile(self):
        try:
            url = "%s/whatsapp_business_profile" % self._base_url()
            resp = requests.get(url, headers=self._headers(), timeout=15)
            data = resp.json()
            if resp.status_code == 200:
                return {'success': True, 'data': data}
            return {'success': False, 'error': data.get('error', {}).get('message', str(data))}
        except Exception as e:
            _logger.exception("WhatsApp API connection test failed")
            return {'success': False, 'error': str(e)}

    def send_text_message(self, to_number, body_text):
        url = "%s/messages" % self._base_url()
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": self._sanitize_phone(to_number),
            "type": "text",
            "text": {"preview_url": False, "body": body_text[:4096]},
        }
        return self._post(url, payload)

    def send_template_message(self, to_number, template_name, language_code='en',
                              header_params=None, body_params=None):
        components = []
        if header_params:
            components.append({
                "type": "header",
                "parameters": [{"type": "text", "text": p} for p in header_params],
            })
        if body_params:
            components.append({
                "type": "body",
                "parameters": [{"type": "text", "text": p} for p in body_params],
            })
        url = "%s/messages" % self._base_url()
        payload = {
            "messaging_product": "whatsapp",
            "to": self._sanitize_phone(to_number),
            "type": "template",
            "template": {
                "name": template_name,
                "language": {"code": language_code},
            },
        }
        if components:
            payload['template']['components'] = components
        return self._post(url, payload)

    def send_interactive_message(self, to_number, body_text, buttons):
        url = "%s/messages" % self._base_url()
        payload = {
            "messaging_product": "whatsapp",
            "to": self._sanitize_phone(to_number),
            "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {"text": body_text},
                "action": {
                    "buttons": [
                        {"type": "reply", "reply": {"id": b['id'], "title": b['title'][:20]}}
                        for b in buttons[:3]
                    ]
                },
            },
        }
        return self._post(url, payload)

    def mark_as_read(self, message_id):
        url = "%s/messages" % self._base_url()
        payload = {
            "messaging_product": "whatsapp",
            "status": "read",
            "message_id": message_id,
        }
        return self._post(url, payload)

    # ── Internal ──────────────────────────────────────────────────

    def _post(self, url, payload):
        try:
            resp = requests.post(url, headers=self._headers(), json=payload, timeout=30)
            data = resp.json()
            if resp.status_code in (200, 201):
                msg_id = (data.get('messages') or [{}])[0].get('id')
                return {'success': True, 'message_id': msg_id}
            error_msg = data.get('error', {}).get('message', json.dumps(data))
            _logger.warning("WhatsApp API error: %s", error_msg)
            return {'success': False, 'error': error_msg}
        except Exception as e:
            _logger.exception("WhatsApp API request failed")
            return {'success': False, 'error': str(e)}

    @staticmethod
    def _sanitize_phone(phone):
        if not phone:
            return ''
        return ''.join(c for c in phone if c.isdigit())
