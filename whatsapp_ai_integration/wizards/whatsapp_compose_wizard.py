# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class WhatsAppComposeWizard(models.TransientModel):
    _name = 'whatsapp.compose.wizard'
    _description = 'Compose WhatsApp Message'

    partner_id = fields.Many2one('res.partner', string="Contact")
    phone = fields.Char("Phone Number", required=True)
    message_body = fields.Text("Message", required=True)
    use_template = fields.Boolean("Use Template")
    template_name = fields.Char("Template Name")

    @api.onchange('partner_id')
    def _onchange_partner_id(self):
        if self.partner_id:
            self.phone = self.partner_id.mobile or self.partner_id.phone

    def action_send(self):
        self.ensure_one()
        if not self.phone:
            raise UserError(_("Please provide a phone number."))
        wa_api = self.env['whatsapp.api']
        if self.use_template and self.template_name:
            result = wa_api.send_template_message(self.phone, self.template_name)
        else:
            result = wa_api.send_text_message(self.phone, self.message_body)
        if not result.get('success'):
            raise UserError(_("Failed to send: %s") % result.get('error', 'Unknown'))

        Conversation = self.env['whatsapp.conversation']
        sanitized = wa_api._sanitize_phone(self.phone)
        conv = Conversation.search([('phone', '=', sanitized)], limit=1)
        if not conv:
            conv = Conversation.create({
                'phone': sanitized,
                'partner_id': self.partner_id.id if self.partner_id else False,
                'state': 'active',
            })
        self.env['whatsapp.message'].create({
            'conversation_id': conv.id,
            'wa_message_id': result.get('message_id'),
            'direction': 'outgoing',
            'message_type': 'template' if self.use_template else 'text',
            'body': self.message_body,
            'phone': self.phone,
            'state': 'sent',
        })
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('WhatsApp'),
                'message': _('Message sent successfully!'),
                'type': 'success',
                'sticky': False,
            },
        }
