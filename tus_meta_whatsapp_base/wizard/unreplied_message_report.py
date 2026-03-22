from datetime import timedelta, datetime

from odoo import models, fields, api, _


class UnrepliedMsgReport(models.TransientModel):
    _name = "unrepelied.message.report"

    date_from=fields.Date(string="Date From")
    date_to=fields.Date(string="Date To")


    def get_report(self):
        return self.env.ref('tus_meta_whatsapp_base.report_un_replied_pdf_print').report_action(self)

    def get_data(self):
        data=[]
        domain=[('model','=',False)]
        if self.date_from:
            date_from=datetime.combine(self.date_from, datetime.min.time()) - timedelta(hours=4)
            domain.append(('date','>=',date_from))
        if self.date_to:
            date_to=datetime.combine(self.date_to, datetime.max.time()) - timedelta(hours=4)
            domain.append(('date', '<=', date_to))

        messages = self.env['whatsapp.history'].read_group(domain=domain,groupby=['partner_id'], fields=['partner_id'],)
        unique_partner_ids = [message['partner_id'][0] for message in messages]

        for k in unique_partner_ids:
            domain = [('model','=',False)]
            if self.date_from:
                date_from = datetime.combine(self.date_from, datetime.min.time()) - timedelta(hours=4)
                domain.append(('date', '>=', date_from))
            if self.date_to:
                date_to = datetime.combine(self.date_to, datetime.max.time()) - timedelta(hours=4)
                domain.append(('date', '<=', date_to))
            domain.append(('partner_id','=',k))

            send = self.env['whatsapp.history'].search(domain,limit=1,order='id desc')
            reply_date=''
            reply_by=''
            if send:
                reply = self.env['whatsapp.history'].search([('model','=','mail.channel'),('partner_id','=',k),('date','>=',send.date)],limit=1,order='id desc')
                if not reply:
                    new_reply = self.env['whatsapp.history'].search([('model','=','mail.channel'),('partner_id', '=', k), ('date', '<=', send.date)],
                                                                limit=1, order='id desc')
                    if new_reply:

                        reply_date=(new_reply.date + timedelta(hours=4)).strftime("%d-%m-%Y %H:%M:%S")
                        reply_by=new_reply.author_id.name

                    send_time=(send.date + timedelta(hours=4)).strftime("%d-%m-%Y %H:%M:%S")
                    data.append({
                        'customer_name':send.partner_id.name,
                        'customer_code':send.partner_id.partner_code,
                        'phone_number':send.phone,
                        'message':send.message,
                        'messaged_on':send_time,
                        'last_replied_on':reply_date,
                        'last_reply_by':reply_by,
                    })
        print("Data",data)
        return data

