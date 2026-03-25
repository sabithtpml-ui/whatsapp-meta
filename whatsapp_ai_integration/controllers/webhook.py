# -*- coding: utf-8 -*-
"""
Webhook controller for WhatsApp Meta Cloud API — Odoo 16.

GET  /whatsapp/webhook  → Verification handshake
POST /whatsapp/webhook  → Incoming messages & status updates
"""
import json
import logging

from odoo import http, SUPERUSER_ID
from odoo.http import request, Response

_logger = logging.getLogger(__name__)


class WhatsAppWebhookController(http.Controller):

    # ── Verification (GET) ────────────────────────────────────────

    @http.route('/whatsapp/webhook', type='http', auth='none', methods=['GET'], csrf=False)
    def verify_webhook(self, **kwargs):
        mode = kwargs.get('hub.mode')
        token = kwargs.get('hub.verify_token')
        challenge = kwargs.get('hub.challenge')

        ICP = request.env['ir.config_parameter'].sudo()
        verify_token = ICP.get_param('whatsapp_ai.verify_token', '')

        if mode == 'subscribe' and token == verify_token:
            _logger.info("WhatsApp webhook verified successfully.")
            return Response(challenge, status=200, headers=[('Content-Type', 'text/plain')])

        _logger.warning("WhatsApp webhook verification failed.")
        return Response('Forbidden', status=403)

    # ── Incoming events (POST) — type='http' because Meta doesn't
    #    send JSON-RPC format that Odoo's type='json' expects ──────

    @http.route('/whatsapp/webhook', type='http', auth='none', methods=['POST'], csrf=False)
    def receive_webhook(self, **kwargs):
        try:
            raw_data = request.httprequest.data
            body = json.loads(raw_data.decode('utf-8'))
        except (json.JSONDecodeError, UnicodeDecodeError):
            _logger.error("Invalid JSON in webhook payload")
            return Response('Bad Request', status=400)

        _logger.debug("WhatsApp webhook payload: %s", json.dumps(body, indent=2))

        for entry in body.get('entry', []):
            for change in entry.get('changes', []):
                value = change.get('value', {})

                for status in value.get('statuses', []):
                    self._process_status_update(status)

                for message in value.get('messages', []):
                    contacts = value.get('contacts', [])
                    contact_name = contacts[0].get('profile', {}).get('name', '') if contacts else ''
                    self._process_incoming_message(message, contact_name)

        return Response(json.dumps({'status': 'ok'}), status=200,
                        headers=[('Content-Type', 'application/json')])

    # ── Message processing ────────────────────────────────────────

    def _process_incoming_message(self, message, contact_name):
        env = request.env(user=SUPERUSER_ID)

        msg_id = message.get('id')
        sender_phone = message.get('from', '')
        msg_type = message.get('type', 'text')

        body = ''
        if msg_type == 'text':
            body = message.get('text', {}).get('body', '')
        elif msg_type == 'interactive':
            interactive = message.get('interactive', {})
            if interactive.get('type') == 'button_reply':
                body = interactive.get('button_reply', {}).get('title', '')
            elif interactive.get('type') == 'list_reply':
                body = interactive.get('list_reply', {}).get('title', '')
        elif msg_type == 'image':
            body = message.get('image', {}).get('caption', '[Image received]')
        elif msg_type == 'document':
            body = message.get('document', {}).get('caption', '[Document received]')
        else:
            body = '[%s message received]' % msg_type

        if not body:
            return

        _logger.info("WhatsApp from %s: %s", sender_phone, body[:50])

        wa_api = env['whatsapp.api']
        wa_api.mark_as_read(msg_id)

        conversation = self._get_or_create_conversation(env, sender_phone, contact_name)

        env['whatsapp.message'].create({
            'conversation_id': conversation.id,
            'wa_message_id': msg_id,
            'direction': 'incoming',
            'message_type': msg_type if msg_type in ('text', 'interactive', 'image', 'document') else 'text',
            'body': body,
            'phone': sender_phone,
            'state': 'received',
        })

        partner = conversation.partner_id
        conversation._post_to_discuss(
            '<b>📱 %s</b>: %s' % (contact_name or sender_phone, body),
            author_id=partner.id if partner else None,
        )

        ICP = env['ir.config_parameter']
        chatbot_enabled = ICP.get_param('whatsapp_ai.chatbot_enabled', 'True') == 'True'

        if chatbot_enabled and conversation.state not in ('human_takeover', 'closed'):
            self._handle_chatbot_reply(env, conversation, sender_phone, body)

    def _handle_chatbot_reply(self, env, conversation, phone, body):
        try:
            conversation.write({'state': 'ai_handled'})
            engine = env['whatsapp.llm.engine']
            reply_text = engine.process_incoming_message(conversation, phone, body)

            if reply_text:
                wa_api = env['whatsapp.api']
                result = wa_api.send_text_message(phone, reply_text)

                env['whatsapp.message'].create({
                    'conversation_id': conversation.id,
                    'wa_message_id': result.get('message_id'),
                    'direction': 'outgoing',
                    'message_type': 'text',
                    'body': reply_text,
                    'phone': phone,
                    'state': 'sent' if result.get('success') else 'failed',
                    'is_chatbot': True,
                    'error_message': result.get('error'),
                })

                conversation._post_to_discuss('🤖 <b>AI Bot</b>: %s' % reply_text)

        except Exception as e:
            _logger.exception("Chatbot error for conversation %s", conversation.id)
            wa_api = env['whatsapp.api']
            wa_api.send_text_message(
                phone,
                "I'm sorry, I encountered an issue. A human agent will be with you shortly.",
            )
            conversation.write({'state': 'human_takeover'})

    def _process_status_update(self, status):
        env = request.env(user=SUPERUSER_ID)
        wa_msg_id = status.get('id')
        new_status = status.get('status')

        status_map = {'sent': 'sent', 'delivered': 'delivered', 'read': 'read', 'failed': 'failed'}
        odoo_status = status_map.get(new_status)
        if not wa_msg_id or not odoo_status:
            return

        msg = env['whatsapp.message'].search([('wa_message_id', '=', wa_msg_id)], limit=1)
        if msg:
            vals = {'state': odoo_status}
            if new_status == 'failed':
                errors = status.get('errors', [])
                vals['error_message'] = errors[0].get('title', 'Unknown') if errors else 'Delivery failed'
            msg.write(vals)

    def _get_or_create_conversation(self, env, phone, contact_name):
        Conversation = env['whatsapp.conversation']
        sanitized = env['whatsapp.api']._sanitize_phone(phone)
        conv = Conversation.search([('phone', '=', sanitized)], limit=1)
        if conv:
            return conv
        partner = env['whatsapp.llm.engine']._find_partner_by_phone(phone)
        if not partner and contact_name:
            partner = env['res.partner'].create({'name': contact_name, 'mobile': phone})
        return Conversation.create({
            'phone': sanitized,
            'partner_id': partner.id if partner else False,
            'state': 'new',
        })
