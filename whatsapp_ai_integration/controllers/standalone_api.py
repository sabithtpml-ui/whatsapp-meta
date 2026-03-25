# -*- coding: utf-8 -*-
import json
import logging
from datetime import datetime, timedelta

from odoo import http, SUPERUSER_ID
from odoo.http import request, Response

_logger = logging.getLogger(__name__)


class WhatsAppStandaloneAPI(http.Controller):

    def _json_response(self, data, status=200):
        return Response(
            json.dumps(data, default=str), status=status,
            headers=[('Content-Type', 'application/json')],
        )

    def _get_env(self):
        """Use SUPERUSER for API endpoints — add your own auth layer if needed."""
        return request.env(user=SUPERUSER_ID)

    # ── Send message ──────────────────────────────────────────────

    @http.route('/api/whatsapp/send', type='http', auth='none', methods=['POST'], csrf=False)
    def api_send_message(self, **kw):
        env = self._get_env()
        try:
            body = json.loads(request.httprequest.data.decode('utf-8'))
        except Exception:
            return self._json_response({'error': 'Invalid JSON'}, 400)

        phone = body.get('phone')
        message = body.get('message')
        template = body.get('template')
        if not phone or (not message and not template):
            return self._json_response({'error': 'phone + message or template required'}, 400)

        wa_api = env['whatsapp.api']
        if template:
            result = wa_api.send_template_message(phone, template, body_params=body.get('template_params', []))
        else:
            result = wa_api.send_text_message(phone, message)

        sanitized = wa_api._sanitize_phone(phone)
        conv = env['whatsapp.conversation'].search([('phone', '=', sanitized)], limit=1)
        if not conv:
            partner = env['whatsapp.llm.engine']._find_partner_by_phone(phone)
            conv = env['whatsapp.conversation'].create({
                'phone': sanitized,
                'partner_id': partner.id if partner else False,
                'state': 'active',
            })
        env['whatsapp.message'].create({
            'conversation_id': conv.id,
            'wa_message_id': result.get('message_id'),
            'direction': 'outgoing',
            'message_type': 'template' if template else 'text',
            'body': message or '[Template: %s]' % template,
            'phone': sanitized,
            'state': 'sent' if result.get('success') else 'failed',
            'error_message': result.get('error'),
        })
        return self._json_response(result)

    # ── Conversations ─────────────────────────────────────────────

    @http.route('/api/whatsapp/conversations', type='http', auth='none', methods=['GET'], csrf=False)
    def api_list_conversations(self, **kw):
        env = self._get_env()
        domain = []
        if kw.get('state'):
            domain.append(('state', '=', kw['state']))
        limit = int(kw.get('limit', 20))
        offset = int(kw.get('offset', 0))
        convs = env['whatsapp.conversation'].search(domain, limit=limit, offset=offset, order='last_message_date desc')
        total = env['whatsapp.conversation'].search_count(domain)
        return self._json_response({
            'total': total, 'limit': limit, 'offset': offset,
            'results': [{
                'id': c.id, 'phone': c.phone,
                'partner_name': c.partner_id.name if c.partner_id else None,
                'state': c.state, 'message_count': c.message_count,
                'last_message': c.last_message_body,
                'last_message_date': c.last_message_date,
            } for c in convs],
        })

    @http.route('/api/whatsapp/conversations/<int:conv_id>/messages', type='http', auth='none', methods=['GET'], csrf=False)
    def api_conversation_messages(self, conv_id, **kw):
        env = self._get_env()
        limit = int(kw.get('limit', 50))
        msgs = env['whatsapp.message'].search(
            [('conversation_id', '=', conv_id)], order='create_date asc', limit=limit,
        )
        return self._json_response({'messages': [{
            'id': m.id, 'direction': m.direction, 'body': m.body,
            'state': m.state, 'is_chatbot': m.is_chatbot, 'timestamp': m.create_date,
        } for m in msgs]})

    # ── Chatbot ───────────────────────────────────────────────────

    @http.route('/api/whatsapp/chatbot/ask', type='http', auth='none', methods=['POST'], csrf=False)
    def api_chatbot_ask(self, **kw):
        env = self._get_env()
        try:
            body = json.loads(request.httprequest.data.decode('utf-8'))
        except Exception:
            return self._json_response({'error': 'Invalid JSON'}, 400)
        phone = body.get('phone', '')
        question = body.get('question', '')
        if not question:
            return self._json_response({'error': 'question required'}, 400)

        sanitized = env['whatsapp.api']._sanitize_phone(phone) if phone else 'api_user'
        conv = env['whatsapp.conversation'].search([('phone', '=', sanitized)], limit=1)
        if not conv:
            partner = env['whatsapp.llm.engine']._find_partner_by_phone(phone) if phone else False
            conv = env['whatsapp.conversation'].create({
                'phone': sanitized,
                'partner_id': partner.id if partner else False,
                'state': 'ai_handled',
            })
        reply = env['whatsapp.llm.engine'].process_incoming_message(conv, phone, question)
        return self._json_response({'reply': reply, 'conversation_id': conv.id})

    # ── Reports ───────────────────────────────────────────────────

    @http.route('/api/whatsapp/reports/sales_summary', type='http', auth='none', methods=['GET'], csrf=False)
    def api_report_sales(self, **kw):
        env = self._get_env()
        days = int(kw.get('days', 30))
        data = env['whatsapp.llm.engine']._report_sales_summary(datetime.now() - timedelta(days=days))
        return self._json_response(data)

    @http.route('/api/whatsapp/reports/top_products', type='http', auth='none', methods=['GET'], csrf=False)
    def api_report_products(self, **kw):
        env = self._get_env()
        days = int(kw.get('days', 30))
        data = env['whatsapp.llm.engine']._report_top_products(datetime.now() - timedelta(days=days))
        return self._json_response(data)

    @http.route('/api/whatsapp/reports/top_customers', type='http', auth='none', methods=['GET'], csrf=False)
    def api_report_customers(self, **kw):
        env = self._get_env()
        days = int(kw.get('days', 30))
        data = env['whatsapp.llm.engine']._report_top_customers(datetime.now() - timedelta(days=days))
        return self._json_response(data)

    @http.route('/api/whatsapp/reports/outstanding', type='http', auth='none', methods=['GET'], csrf=False)
    def api_report_outstanding(self, **kw):
        env = self._get_env()
        data = env['whatsapp.llm.engine']._report_outstanding_payments()
        return self._json_response(data)

    # ── Health ────────────────────────────────────────────────────

    @http.route('/api/whatsapp/health', type='http', auth='none', methods=['GET'], csrf=False)
    def api_health(self, **kw):
        return self._json_response({'status': 'ok', 'module': 'whatsapp_ai_integration', 'version': '16.0.1.0.0'})
