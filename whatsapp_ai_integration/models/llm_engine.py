# -*- coding: utf-8 -*-
"""
LLM Engine for WhatsApp chatbot – Odoo 16.

Detects intent, executes Odoo operations, returns human-readable replies.
"""
import json
import logging
import requests
from datetime import datetime, timedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

DEFAULT_SYSTEM_PROMPT = """You are an AI business assistant integrated with an Odoo ERP system via WhatsApp.
You help users manage their business through natural conversation.

YOUR CAPABILITIES:
1. **Create Sale Orders** – Collect: customer name, product(s), quantities.
2. **Query Customer Info** – Look up details, order history, outstanding invoices.
3. **Generate Reports** – Sales summaries, top products, revenue, outstanding payments.
4. **General Questions** – Products, stock availability, pricing.

RULES:
- Be polite, professional, concise (WhatsApp message limits).
- Confirm details BEFORE creating an order.
- Respond in the SAME LANGUAGE the user writes in.
- Never invent data — only use what is in the context.

Respond ONLY with a JSON object:
{
  "intent": "create_order" | "query_customer" | "generate_report" | "general_chat" | "confirm_order",
  "response_text": "Your reply to send via WhatsApp",
  "action": null | {
    "type": "create_so" | "search_partner" | "search_product" | "get_report",
    "params": { ... }
  },
  "needs_confirmation": true | false
}
"""


class LLMEngine(models.AbstractModel):
    _name = 'whatsapp.llm.engine'
    _description = 'LLM Processing Engine'

    # ── Config ────────────────────────────────────────────────────

    def _get_config(self):
        ICP = self.env['ir.config_parameter'].sudo()
        return {
            'provider': ICP.get_param('whatsapp_ai.llm_provider', 'anthropic'),
            'api_key': ICP.get_param('whatsapp_ai.llm_api_key', ''),
            'model': ICP.get_param('whatsapp_ai.llm_model', 'claude-sonnet-4-20250514'),
            'system_prompt': ICP.get_param('whatsapp_ai.llm_system_prompt', '') or DEFAULT_SYSTEM_PROMPT,
        }

    def _test_connection(self):
        try:
            result = self._call_llm(
                "Say 'Connection successful' in JSON format.",
                system='Reply only: {"status":"ok"}',
            )
            return {'success': True, 'message': 'LLM responded: %s' % result[:100]}
        except Exception as e:
            return {'success': False, 'message': str(e)}

    # ── LLM calls ─────────────────────────────────────────────────

    def _call_llm(self, user_message, system=None, conversation_history=None):
        cfg = self._get_config()
        if not cfg['api_key']:
            raise UserError(_("LLM API key not configured. Go to Settings > WhatsApp AI."))
        if cfg['provider'] == 'anthropic':
            return self._call_anthropic(cfg, user_message, system, conversation_history)
        elif cfg['provider'] == 'openai':
            return self._call_openai(cfg, user_message, system, conversation_history)
        raise UserError(_("Unsupported LLM provider: %s") % cfg['provider'])

    def _call_anthropic(self, cfg, user_message, system=None, history=None):
        url = "https://api.anthropic.com/v1/messages"
        headers = {
            "x-api-key": cfg['api_key'],
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        messages = list(history or [])
        messages.append({"role": "user", "content": user_message})
        payload = {
            "model": cfg['model'],
            "max_tokens": 2048,
            "system": system or cfg['system_prompt'],
            "messages": messages,
        }
        resp = requests.post(url, headers=headers, json=payload, timeout=60)
        data = resp.json()
        if resp.status_code != 200:
            error = data.get('error', {}).get('message', str(data))
            raise UserError(_("Anthropic API error: %s") % error)
        return data['content'][0]['text']

    def _call_openai(self, cfg, user_message, system=None, history=None):
        url = "https://api.openai.com/v1/chat/completions"
        headers = {
            "Authorization": "Bearer %s" % cfg['api_key'],
            "Content-Type": "application/json",
        }
        messages = [{"role": "system", "content": system or cfg['system_prompt']}]
        messages.extend(history or [])
        messages.append({"role": "user", "content": user_message})
        payload = {"model": cfg['model'], "messages": messages, "max_tokens": 2048}
        resp = requests.post(url, headers=headers, json=payload, timeout=60)
        data = resp.json()
        if resp.status_code != 200:
            error = data.get('error', {}).get('message', str(data))
            raise UserError(_("OpenAI API error: %s") % error)
        return data['choices'][0]['message']['content']

    # ── Main entry point ──────────────────────────────────────────

    def process_incoming_message(self, conversation, sender_phone, message_text):
        context_data = self._build_context(sender_phone, conversation)
        history = self._build_history(conversation)
        enriched = (
            "USER MESSAGE: %s\n\nODOO CONTEXT:\n```json\n%s\n```"
            % (message_text, json.dumps(context_data, indent=2, default=str))
        )
        raw_response = self._call_llm(enriched, conversation_history=history)
        parsed = self._parse_response(raw_response)
        if parsed.get('action'):
            action_result = self._execute_action(parsed['action'], sender_phone)
            if action_result:
                follow_up = (
                    "ACTION RESULT:\n```json\n%s\n```\n"
                    "Compose a final WhatsApp reply for the user. Reply ONLY with message text, no JSON."
                    % json.dumps(action_result, indent=2, default=str)
                )
                return self._call_llm(follow_up, conversation_history=history)
        return parsed.get('response_text', raw_response)

    # ── Context ───────────────────────────────────────────────────

    def _build_context(self, phone, conversation):
        partner = self._find_partner_by_phone(phone)
        ctx = {
            'timestamp': fields.Datetime.now().isoformat(),
            'partner': None,
            'recent_orders': [],
            'pending_invoices': [],
            'conversation_state': conversation.state if conversation else 'new',
        }
        if partner:
            ctx['partner'] = {
                'id': partner.id,
                'name': partner.name,
                'email': partner.email,
                'phone': partner.phone or partner.mobile,
                'city': partner.city,
                'country': partner.country_id.name if partner.country_id else None,
            }
            orders = self.env['sale.order'].sudo().search(
                [('partner_id', '=', partner.id)], limit=5, order='date_order desc',
            )
            ctx['recent_orders'] = [{
                'name': o.name,
                'date': str(o.date_order) if o.date_order else '',
                'amount_total': o.amount_total,
                'state': o.state,
            } for o in orders]
            invoices = self.env['account.move'].sudo().search([
                ('partner_id', '=', partner.id),
                ('move_type', '=', 'out_invoice'),
                ('payment_state', 'in', ('not_paid', 'partial')),
            ], limit=5)
            ctx['pending_invoices'] = [{
                'name': inv.name,
                'amount_total': inv.amount_total,
                'amount_residual': inv.amount_residual,
                'date_due': str(inv.invoice_date_due) if inv.invoice_date_due else '',
            } for inv in invoices]
        return ctx

    def _build_history(self, conversation, limit=10):
        if not conversation:
            return []
        msgs = self.env['whatsapp.message'].sudo().search(
            [('conversation_id', '=', conversation.id)],
            order='create_date asc', limit=limit,
        )
        history = []
        for msg in msgs:
            role = 'user' if msg.direction == 'incoming' else 'assistant'
            history.append({'role': role, 'content': msg.body or ''})
        return history

    # ── Actions ───────────────────────────────────────────────────

    def _execute_action(self, action, sender_phone):
        action_type = action.get('type')
        params = action.get('params', {})
        if action_type == 'create_so':
            return self._action_create_sale_order(sender_phone, params)
        elif action_type == 'search_partner':
            return self._action_search_partner(params)
        elif action_type == 'search_product':
            return self._action_search_product(params)
        elif action_type == 'get_report':
            return self._action_get_report(params)
        return None

    def _action_create_sale_order(self, phone, params):
        partner = self._find_partner_by_phone(phone)
        if not partner:
            partner = self.env['res.partner'].sudo().create({
                'name': params.get('customer_name', phone),
                'mobile': phone,
            })
        order_lines = []
        for line in params.get('lines', []):
            product = self._find_product(line.get('product', ''))
            if product:
                order_lines.append((0, 0, {
                    'product_id': product.id,
                    'product_uom_qty': line.get('qty', 1),
                }))
        if not order_lines:
            return {'error': 'No valid products found for the order.'}
        so = self.env['sale.order'].sudo().create({
            'partner_id': partner.id,
            'order_line': order_lines,
        })
        return {
            'success': True,
            'order_name': so.name,
            'amount_total': so.amount_total,
            'partner_name': partner.name,
            'lines': [{
                'product': l.product_id.name,
                'qty': l.product_uom_qty,
                'price': l.price_unit,
                'subtotal': l.price_subtotal,
            } for l in so.order_line],
        }

    def _action_search_partner(self, params):
        query = params.get('query', '')
        partners = self.env['res.partner'].sudo().search(
            ['|', '|',
             ('name', 'ilike', query),
             ('email', 'ilike', query),
             ('phone', 'ilike', query)],
            limit=5,
        )
        return {'results': [{
            'id': p.id, 'name': p.name, 'email': p.email,
            'phone': p.phone or p.mobile,
        } for p in partners]}

    def _action_search_product(self, params):
        query = params.get('query', '')
        products = self.env['product.product'].sudo().search(
            ['|', ('name', 'ilike', query), ('default_code', 'ilike', query)],
            limit=10,
        )
        return {'results': [{
            'id': p.id, 'name': p.name, 'ref': p.default_code,
            'price': p.list_price, 'qty_available': p.qty_available,
        } for p in products]}

    def _action_get_report(self, params):
        report_type = params.get('report_type', 'sales_summary')
        days = params.get('days', 30)
        date_from = datetime.now() - timedelta(days=days)
        if report_type == 'sales_summary':
            return self._report_sales_summary(date_from)
        elif report_type == 'top_products':
            return self._report_top_products(date_from)
        elif report_type == 'top_customers':
            return self._report_top_customers(date_from)
        elif report_type == 'outstanding_payments':
            return self._report_outstanding_payments()
        return {'error': 'Unknown report type: %s' % report_type}

    # ── Reports ───────────────────────────────────────────────────

    def _report_sales_summary(self, date_from):
        orders = self.env['sale.order'].sudo().search([
            ('date_order', '>=', date_from),
            ('state', 'in', ('sale', 'done')),
        ])
        total = sum(orders.mapped('amount_total'))
        return {
            'report': 'Sales Summary',
            'period': 'Last %d days' % (datetime.now() - date_from).days,
            'total_orders': len(orders),
            'total_revenue': total,
            'avg_order_value': total / len(orders) if orders else 0,
        }

    def _report_top_products(self, date_from, limit=10):
        # Odoo 16: product_template.name is a plain Char field
        self.env.cr.execute("""
            SELECT pt.name AS product_name,
                   SUM(sol.product_uom_qty) AS total_qty,
                   SUM(sol.price_subtotal)  AS total_revenue
            FROM sale_order_line sol
            JOIN sale_order so ON so.id = sol.order_id
            JOIN product_product pp ON pp.id = sol.product_id
            JOIN product_template pt ON pt.id = pp.product_tmpl_id
            WHERE so.date_order >= %s AND so.state IN ('sale','done')
            GROUP BY pt.name
            ORDER BY total_revenue DESC
            LIMIT %s
        """, (date_from, limit))
        return {'report': 'Top Products', 'data': self.env.cr.dictfetchall()}

    def _report_top_customers(self, date_from, limit=10):
        self.env.cr.execute("""
            SELECT rp.name AS customer,
                   COUNT(so.id) AS order_count,
                   SUM(so.amount_total) AS total_spent
            FROM sale_order so
            JOIN res_partner rp ON rp.id = so.partner_id
            WHERE so.date_order >= %s AND so.state IN ('sale','done')
            GROUP BY rp.name
            ORDER BY total_spent DESC
            LIMIT %s
        """, (date_from, limit))
        return {'report': 'Top Customers', 'data': self.env.cr.dictfetchall()}

    def _report_outstanding_payments(self):
        self.env.cr.execute("""
            SELECT rp.name AS customer,
                   COUNT(am.id) AS invoice_count,
                   SUM(am.amount_residual) AS total_outstanding
            FROM account_move am
            JOIN res_partner rp ON rp.id = am.partner_id
            WHERE am.move_type = 'out_invoice'
              AND am.payment_state IN ('not_paid','partial')
            GROUP BY rp.name
            ORDER BY total_outstanding DESC
            LIMIT 10
        """)
        return {'report': 'Outstanding Payments', 'data': self.env.cr.dictfetchall()}

    # ── Utility ───────────────────────────────────────────────────

    def _find_partner_by_phone(self, phone):
        if not phone:
            return self.env['res.partner']
        digits = ''.join(c for c in phone if c.isdigit())
        suffix = digits[-9:] if len(digits) >= 9 else digits
        return self.env['res.partner'].sudo().search([
            '|',
            ('phone', 'like', '%%%s' % suffix),
            ('mobile', 'like', '%%%s' % suffix),
        ], limit=1)

    def _find_product(self, query):
        if not query:
            return self.env['product.product']
        return self.env['product.product'].sudo().search(
            ['|', ('name', 'ilike', query), ('default_code', 'ilike', query)],
            limit=1,
        )

    def _parse_response(self, raw_text):
        try:
            text = raw_text.strip()
            if text.startswith('```'):
                text = text.split('\n', 1)[-1]
            if text.endswith('```'):
                text = text.rsplit('```', 1)[0]
            return json.loads(text.strip())
        except (json.JSONDecodeError, ValueError):
            return {'intent': 'general_chat', 'response_text': raw_text, 'action': None}
