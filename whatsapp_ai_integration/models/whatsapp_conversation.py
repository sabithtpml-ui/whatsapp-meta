# -*- coding: utf-8 -*-
import logging
from odoo import api, fields, models, _

_logger = logging.getLogger(__name__)


class WhatsAppConversation(models.Model):
    _name = 'whatsapp.conversation'
    _description = 'WhatsApp Conversation'
    _order = 'last_message_date desc'
    _rec_name = 'display_name'
    _inherit = ['mail.thread']

    partner_id = fields.Many2one('res.partner', string="Contact", index=True, ondelete='set null')
    phone = fields.Char("Phone Number", required=True, index=True)
    display_name = fields.Char(compute='_compute_display_name', store=True)

    message_ids = fields.One2many('whatsapp.message', 'conversation_id', string="Messages")
    message_count = fields.Integer(compute='_compute_message_count')
    last_message_date = fields.Datetime("Last Message", compute='_compute_last_message', store=True)
    last_message_body = fields.Text("Last Message Preview", compute='_compute_last_message', store=True)

    state = fields.Selection([
        ('new', 'New'),
        ('active', 'Active'),
        ('ai_handled', 'AI Handling'),
        ('human_takeover', 'Human Takeover'),
        ('closed', 'Closed'),
    ], default='new', tracking=True)
    assigned_user_id = fields.Many2one('res.users', string="Assigned Agent")

    # Odoo 16: mail.channel instead of discuss.channel
    channel_id = fields.Many2one('mail.channel', string="Discuss Channel")

    ai_context = fields.Text("AI Context (JSON)")

    @api.depends('partner_id', 'partner_id.name', 'phone')
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = rec.partner_id.name if rec.partner_id else rec.phone

    @api.depends('message_ids')
    def _compute_message_count(self):
        for rec in self:
            rec.message_count = len(rec.message_ids)

    @api.depends('message_ids.create_date', 'message_ids.body')
    def _compute_last_message(self):
        for rec in self:
            last = self.env['whatsapp.message'].search(
                [('conversation_id', '=', rec.id)], order='create_date desc', limit=1,
            )
            rec.last_message_date = last.create_date if last else False
            rec.last_message_body = (last.body or '')[:100] if last else ''

    # ── Actions ───────────────────────────────────────────────────

    def action_open_messages(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Messages – %s' % self.display_name,
            'res_model': 'whatsapp.message',
            'view_mode': 'tree,form',
            'domain': [('conversation_id', '=', self.id)],
            'context': {'default_conversation_id': self.id},
        }

    def action_human_takeover(self):
        self.write({'state': 'human_takeover', 'assigned_user_id': self.env.uid})
        self._post_to_discuss(
            "🔄 <b>Human takeover activated.</b> AI chatbot is paused for this conversation."
        )

    def action_resume_ai(self):
        self.write({'state': 'ai_handled', 'assigned_user_id': False})

    def action_close(self):
        self.write({'state': 'closed'})

    # ── Discuss integration (Odoo 16: mail.channel) ───────────────

    def _get_or_create_channel(self):
        self.ensure_one()
        if self.channel_id:
            return self.channel_id
        channel_name = "WA: %s (%s)" % (self.display_name, self.phone)
        channel = self.env['mail.channel'].sudo().create({
            'name': channel_name,
            'channel_type': 'channel',
            'description': 'WhatsApp conversation with %s' % self.phone,
        })
        self.channel_id = channel
        return channel

    def _post_to_discuss(self, body, author_id=None):
        channel = self._get_or_create_channel()
        channel.message_post(
            body=body,
            message_type='comment',
            subtype_xmlid='mail.mt_comment',
            author_id=author_id or self.env.ref('base.partner_root').id,
        )

    def send_whatsapp_reply(self, body_text):
        """Send a WhatsApp reply from the UI or Discuss."""
        self.ensure_one()
        wa_api = self.env['whatsapp.api']
        result = wa_api.send_text_message(self.phone, body_text)
        self.env['whatsapp.message'].sudo().create({
            'conversation_id': self.id,
            'direction': 'outgoing',
            'message_type': 'text',
            'body': body_text,
            'phone': self.phone,
            'state': 'sent' if result.get('success') else 'failed',
            'wa_message_id': result.get('message_id'),
            'error_message': result.get('error'),
        })
        return result
