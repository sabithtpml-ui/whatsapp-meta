# -*- coding: utf-8 -*-
import logging
from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class WhatsAppMessage(models.Model):
    _name = 'whatsapp.message'
    _description = 'WhatsApp Message'
    _order = 'create_date desc'
    _rec_name = 'wa_message_id'

    wa_message_id = fields.Char("WhatsApp Message ID", index=True)
    conversation_id = fields.Many2one(
        'whatsapp.conversation', string="Conversation", ondelete='cascade',
    )
    partner_id = fields.Many2one(
        'res.partner', string="Contact",
        related='conversation_id.partner_id', store=True, readonly=True,
    )

    direction = fields.Selection([
        ('incoming', 'Incoming'),
        ('outgoing', 'Outgoing'),
    ], required=True, default='outgoing')
    message_type = fields.Selection([
        ('text', 'Text'),
        ('template', 'Template'),
        ('interactive', 'Interactive'),
        ('image', 'Image'),
        ('document', 'Document'),
        ('reaction', 'Reaction'),
    ], default='text')
    body = fields.Text("Message Body")
    phone = fields.Char("Phone Number")

    state = fields.Selection([
        ('draft', 'Draft'),
        ('sent', 'Sent'),
        ('delivered', 'Delivered'),
        ('read', 'Read'),
        ('failed', 'Failed'),
        ('received', 'Received'),
    ], default='draft', tracking=True)
    error_message = fields.Text("Error Details")

    is_chatbot = fields.Boolean("Processed by AI", default=False)
    intent_detected = fields.Char("Detected Intent")
    mail_message_id = fields.Many2one('mail.message', string="Discuss Message")

    def action_resend(self):
        for rec in self.filtered(lambda m: m.state == 'failed' and m.direction == 'outgoing'):
            wa_api = self.env['whatsapp.api']
            result = wa_api.send_text_message(rec.phone, rec.body)
            if result.get('success'):
                rec.write({
                    'state': 'sent',
                    'wa_message_id': result.get('message_id'),
                    'error_message': False,
                })
            else:
                rec.error_message = result.get('error', 'Unknown error')
