# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    wa_conversation_ids = fields.One2many(
        'whatsapp.conversation', 'partner_id', string="WhatsApp Conversations",
    )
    wa_conversation_count = fields.Integer(compute='_compute_wa_conversation_count')
    wa_opted_in = fields.Boolean("WhatsApp Opted-In", default=True)

    def _compute_wa_conversation_count(self):
        for partner in self:
            partner.wa_conversation_count = len(partner.wa_conversation_ids)

    def action_open_whatsapp_conversations(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'WhatsApp – %s' % self.name,
            'res_model': 'whatsapp.conversation',
            'view_mode': 'tree,form',
            'domain': [('partner_id', '=', self.id)],
        }

    def action_send_whatsapp(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Send WhatsApp Message',
            'res_model': 'whatsapp.compose.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_partner_id': self.id,
                'default_phone': self.mobile or self.phone,
            },
        }
