# from google.cloud import documentai_v1beta3 as documentai
# from pdf2image import convert_from_bytes
from odoo import fields, models, api, _
from odoo.tools.config import config
from odoo.exceptions import ValidationError, UserError
import io
import os
import base64
import logging
import re
from datetime import datetime
from datetime import date
import imghdr

logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger(__name__)



os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = config.get(
    'google_credentials_path') or r"/etc/odooocr-433910-7f80eb5eb705.json"


def extract_data_from_document_using_document_ai(client, processor_name, document_data,
                                                 mime_type):
    supported_mime_types = ['application/pdf', 'image/jpeg', 'image/png']

    if mime_type not in supported_mime_types:
        raise ValidationError(f"Unsupported file format: {mime_type}. Supported formats are: {', '.join(supported_mime_types)}")

    raw_document = {"content": document_data, "mime_type": mime_type}
    request = {"name": processor_name, "raw_document": raw_document}
    response = {}
    try:
        print("Processing")
        result = client.process_document(request=request)
        for entity in result.document.entities:
            if entity.type_ in response:
                response[entity.type_] += "\n" + entity.mention_text
            else:
                response[entity.type_] = entity.mention_text
        return response
    except Exception as e:
        logger.error(f"Error during Document AI data extraction: {e}")
        raise ValidationError(f"Error: {e}")

class WhBankTransHistry(models.Model):
    _description = 'bank transfer history'
    _name = 'wh.bank.transfer.history'

    READONLY_STATES = {
        'draft': [('readonly', False)],
        'confirm': [('readonly', True)],
        'posted': [('readonly', True)],
    }


    name=fields.Char('Name')
    customer_code=fields.Char('Customer Code')
    document=fields.Many2one('ir.attachment')
    image=fields.Binary('Image',states=READONLY_STATES)
    partner_id=fields.Many2one('res.partner',string='customer',states=READONLY_STATES)
    payment_id=fields.Many2one('account.payment',string='Payment',states=READONLY_STATES)
    amount=fields.Char('Amount')
    transaction_no=fields.Char('Transaction Number')
    date=fields.Char('Date')
    parsed_date=fields.Date('Parsed Date',states=READONLY_STATES)
    parsed_amount=fields.Float('Parsed Amount',states=READONLY_STATES)
    message_id=fields.Char('Message ID')
    currency_id = fields.Many2one('res.currency', 'Currency', required=True,
                                  default=lambda self: self.env.user.company_id.currency_id)
    state=fields.Selection([('draft','Draft'), ('confirm','Confirmed'), ('posted','Posted'), ('cancel','Cancelled')],default='draft',string='Status')


    @api.onchange('parsed_amount','parsed_date','partner_id')
    def state_vali(self):
        if (self.partner_id and self.parsed_date and self.parsed_amount):
            if self.state=='draft':
                self.write({'state':'confirm'})

    def _parse_date_string(self, date_str):

        date_formats = [
            '%d-%b-%y',
            '%d-%b-%Y',
            '%d %b %Y',
            '%d/%m/%Y'
        ]
        for date_format in date_formats:
            try:
                return datetime.strptime(date_str, date_format).date()
            except ValueError:
                continue
        return None

    def _extract_numeric_value(self, input_str):
        match = re.search(r'[-+]?\d*\.\d+|\d+', input_str)
        if match:
            return float(match.group(0))
        return None

    def extract_data(self):
        if (self.date and self.amount and self.partner_id):
            self.write({'state':'confirm'})
        else:
            project_id = "odooocr-433910"
            image_data = base64.b64decode(self.image)
            img_mime_type = imghdr.what(None, h=image_data)
            if img_mime_type in ['jpeg','image/jpeg']:
                mime_type='image/jpeg'
            elif img_mime_type in ['application/pdf','pdf']:
                mime_type='application/pdf'
            elif img_mime_type in ['image/png','png']:
                mime_type='image/png'
            else:
                mime_type = 'application/pdf'
            client = documentai.DocumentProcessorServiceClient()
            processor_name=f'projects/{project_id}/locations/us/processors/1d8ed230e527672e'
            document_data = base64.b64decode(self.image)
            response = extract_data_from_document_using_document_ai(client, processor_name, document_data,mime_type)
            amount = response.get('Amount', '')
            date = response.get('Date', '')
            tans_id = response.get('tans_id', '')
            self.transaction_no= tans_id
            self.date= date
            self.amount= amount
            if self.date:
                parsed_date = self._parse_date_string(self.date)
                if parsed_date:
                    self.parsed_date = parsed_date
            if self.amount:

                parsed_value = self._extract_numeric_value(self.amount)
                if parsed_value is not None:
                    print(parsed_value)
                    self.parsed_amount = parsed_value
            if (self.date and self.amount and self.partner_id):
                self.write({'state':'confirm'})


    def create_payment(self):
        data = {
            'partner_id': self.partner_id.id,
            'payment_type': 'inbound',
            'partner_type': 'customer',
            'amount': abs(self.parsed_amount),
            'ref': self.name,
            'date': self.parsed_date,
            'payment_reference': self.transaction_no,
            'card_reference': self.transaction_no,
            'currency_id': self.currency_id.id,
        }

        payment = self.env['account.payment'].create(data)
        payment.action_post()
        self.payment_id=payment.id
        self.write({'state':'posted'})

    def unlink_payment(self):
        if self.payment_id:
            self.payment_id.action_draft()
            self.payment_id.sudo().unlink()
            self.write({'state':'cancel'})
        else:
            self.write({'state': 'cancel'})
    def reset_payment(self):
        if self.payment_id:
            self.payment_id.action_draft()
            self.payment_id.sudo().unlink()
            self.write({'state':'confirm'})
        else:
            self.write({'state': 'confirm'})


    def reset_to_draft(self):
        if self.state=='confirm':
            self.write({'state':'draft'})


