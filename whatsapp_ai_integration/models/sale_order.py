# -*- coding: utf-8 -*-
import logging
from odoo import api, fields, models, _

_logger = logging.getLogger(__name__)


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    wa_message_sent = fields.Boolean("WhatsApp Notified", default=False, copy=False)
    wa_message_ids = fields.One2many(
        'whatsapp.message', compute='_compute_wa_messages', string="WhatsApp Messages",
    )
    wa_message_count = fields.Integer(compute='_compute_wa_messages')

    def _compute_wa_messages(self):
        for order in self:
            msgs = self.env['whatsapp.message'].search([
                ('body', 'ilike', order.name),
                ('partner_id', '=', order.partner_id.id),
            ])
            order.wa_message_ids = msgs
            order.wa_message_count = len(msgs)

    def action_confirm(self):
        result = super(SaleOrder, self).action_confirm()
        self._send_whatsapp_notification()
        return result

    def _send_whatsapp_notification(self):
        ICP = self.env['ir.config_parameter'].sudo()
        if not ICP.get_param('whatsapp_ai.auto_send_so', 'True') == 'True':
            return

        wa_api = self.env['whatsapp.api']
        template_name = ICP.get_param('whatsapp_ai.so_template_name', '')

        for order in self:
            phone = order.partner_id.mobile or order.partner_id.phone
            if not phone:
                _logger.warning(
                    "SO %s: partner %s has no phone, skipping WhatsApp.",
                    order.name, order.partner_id.name,
                )
                continue

            lines_summary = "\n".join(
                "  • %s × %s = %.2f" % (l.product_id.name, l.product_uom_qty, l.price_subtotal)
                for l in order.order_line
            )
            message_body = (
                "Hello %s 👋\n\n"
                "Your order *%s* has been confirmed! ✅\n\n"
                "📦 *Order Details:*\n%s\n\n"
                "💰 *Total:* %.2f %s\n\n"
                "Thank you for your business! Reply to this message if you have any questions."
            ) % (
                order.partner_id.name, order.name, lines_summary,
                order.amount_total, order.currency_id.name,
            )

            if template_name:
                result = wa_api.send_template_message(
                    phone, template_name,
                    body_params=[
                        order.partner_id.name,
                        order.name,
                        "%.2f %s" % (order.amount_total, order.currency_id.name),
                    ],
                )
            else:
                result = wa_api.send_text_message(phone, message_body)

            conversation = self._get_or_create_conversation(phone, order.partner_id)
            self.env['whatsapp.message'].sudo().create({
                'conversation_id': conversation.id,
                'wa_message_id': result.get('message_id'),
                'direction': 'outgoing',
                'message_type': 'template' if template_name else 'text',
                'body': message_body,
                'phone': phone,
                'state': 'sent' if result.get('success') else 'failed',
                'error_message': result.get('error'),
            })
            if result.get('success'):
                order.wa_message_sent = True

    def _get_or_create_conversation(self, phone, partner):
        Conversation = self.env['whatsapp.conversation'].sudo()
        sanitized = self.env['whatsapp.api']._sanitize_phone(phone)
        conv = Conversation.search([('phone', '=', sanitized)], limit=1)
        if not conv:
            conv = Conversation.create({
                'phone': sanitized,
                'partner_id': partner.id,
                'state': 'active',
            })
        return conv

    def action_view_whatsapp_messages(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'WhatsApp Messages',
            'res_model': 'whatsapp.message',
            'view_mode': 'tree,form',
            'domain': [('partner_id', '=', self.partner_id.id)],
        }

    def action_send_whatsapp_manual(self):
        self._send_whatsapp_notification()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('WhatsApp'),
                'message': _('Notification sent.'),
                'type': 'success',
                'sticky': False,
            },
        }
