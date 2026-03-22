from odoo import _, api, fields, models, modules, tools, Command
import json

from odoo.osv import expression
from odoo.tools import html_escape
from odoo.tools.misc import DEFAULT_SERVER_DATETIME_FORMAT
import logging
from collections import defaultdict
from hashlib import sha512
from secrets import choice
from odoo.tools.misc import DEFAULT_SERVER_DATETIME_FORMAT


class Channel(models.Model):

    _inherit = 'mail.channel'


    def channel_pin(self, pinned=False):
        self.ensure_one()
        if not self.env.user.provider_id:
            return
        member = self.env['mail.channel.member'].sudo().search(
            [('partner_id', '=', self.env.user.partner_id.id), ('channel_id', '=', self.id), ('is_pinned', '!=', pinned)])
        if member:
            member.write({'is_pinned': pinned})
        if not pinned:
            print("ddddddddddddddddddd")
            self.env['bus.bus']._sendone(self.env.user.partner_id, 'mail.channel/unpin', {'id': self.id})
        else:
            self.env['bus.bus']._sendone(self.env.user.partner_id, 'mail.channel/legacy_insert', self.channel_info()[0])
        return

    def channel_info(self):
        """ Get the informations header for the current channels
            :returns a list of channels values
            :rtype : list(dict)
        """

        if not self:
            return []
        # print("ssddf",self)
        query = """
            SELECT id FROM mail_message 
            WHERE email_from = '' 
            AND "isWaMsgs" = TRUE
            ORDER BY date DESC
            LIMIT 400
        """
        self.env.cr.execute(query)
        message_ids = [r[0] for r in self.env.cr.fetchall()]
        messages = self.env['mail.message'].browse(message_ids)

        # print("messages",messages)
        # Get unique partner-channel pairs (most recent first)
        partner_channel_map = []
        for msg in messages:
            # print(msg.res_id,msg.model)
            partner_channel_map.append(msg.res_id)
        # print("part",partner_channel_map)
        # Get the channel IDs
        # channel_ids = list(partner_channel_map.values())
        # print("Channe",partner_channel_map)
        # Get the channels
        channels = self.env['mail.channel'].search([('id','in',partner_channel_map)])

        # print("Channels",channels)
        channel_infos = []
        rtc_sessions_by_channel = channels.sudo().rtc_session_ids._mail_rtc_session_format_by_channel()
        channel_last_message_ids = dict((r['id'], r['message_id']) for r in channels._channel_last_message_ids())
        current_partner = self.env['res.partner']
        current_guest = self.env['mail.guest']
        guest = self.env['mail.guest']._get_guest_from_context()
        if self.env.user._is_public and guest:
            current_guest = guest
        else:
            current_partner = self.env.user.partner_id
        all_needed_members_domain = expression.OR([
            [('channel_id.channel_type', '!=', 'channel')],
            [('rtc_inviting_session_id', '!=', False)],
            [('partner_id', '=', current_partner.id) if current_partner else expression.FALSE_LEAF],
            [('guest_id', '=', current_guest.id) if current_guest else expression.FALSE_LEAF],
        ])
        all_needed_members = self.env['mail.channel.member'].search(expression.AND([[('channel_id', 'in', channels.ids)], all_needed_members_domain]), order='id')
        all_needed_members.partner_id.sudo().mail_partner_format()  # prefetch in batch
        members_by_channel = defaultdict(lambda: self.env['mail.channel.member'])
        invited_members_by_channel = defaultdict(lambda: self.env['mail.channel.member'])
        member_of_current_user_by_channel = defaultdict(lambda: self.env['mail.channel.member'])
        for member in all_needed_members:
            members_by_channel[member.channel_id] |= member
            if member.rtc_inviting_session_id:
                invited_members_by_channel[member.channel_id] |= member
            if (current_partner and member.partner_id == current_partner) or (current_guest and member.guest_id == current_guest):
                member_of_current_user_by_channel[member.channel_id] = member
        # sorted_channels = channels.sorted(
        #     key=lambda c: channel_last_message_ids.get(c.id, {}).get('date', '2000-01-01'),
        #     reverse=True
        # )

        for channel in channels:
            channel_data = {
                'avatarCacheKey': channel._get_avatar_cache_key(),
                'channel_type': channel.channel_type,
                'id': channel.id,
                'memberCount': channel.member_count,
            }
            info = {
                'id': channel.id,
                'name': channel.name,
                'defaultDisplayMode': channel.default_display_mode,
                'description': channel.description,
                'uuid': channel.uuid,
                'state': 'open',
                'is_minimized': False,
                'group_based_subscription': bool(channel.group_ids),
                'create_uid': channel.create_uid.id,
                'authorizedGroupFullName': channel.group_public_id.full_name,
            }
            # add last message preview (only used in mobile)
            info['last_message_id'] = channel_last_message_ids.get(channel.id, False)
            # find the channel member state
            if current_partner or current_guest:
                info['message_needaction_counter'] = channel.message_needaction_counter
                member = member_of_current_user_by_channel.get(channel, self.env['mail.channel.member']).with_prefetch([m.id for m in member_of_current_user_by_channel.values()])
                if member:
                    channel_data['channelMembers'] = [('insert', list(member._mail_channel_member_format().values()))]
                    info['state'] = member.fold_state or 'open'
                    channel_data['serverMessageUnreadCounter'] = member.message_unread_counter
                    info['is_minimized'] = member.is_minimized
                    info['seen_message_id'] = member.seen_message_id.id
                    channel_data['custom_channel_name'] = member.custom_channel_name
                    info['is_pinned'] = member.is_pinned
                    info['last_interest_dt'] = member.last_interest_dt.strftime(DEFAULT_SERVER_DATETIME_FORMAT)
                    if member.rtc_inviting_session_id:
                        info['rtc_inviting_session'] = {'id': member.rtc_inviting_session_id.id}
            # add members info
            if channel.channel_type != 'channel':
                # avoid sending potentially a lot of members for big channels
                # exclude chat and other small channels from this optimization because they are
                # assumed to be smaller and it's important to know the member list for them
                channel_data['channelMembers'] = [('insert', list(members_by_channel[channel]._mail_channel_member_format().values()))]
                info['seen_partners_info'] = sorted([{
                    'id': cp.id,
                    'partner_id': cp.partner_id.id,
                    'fetched_message_id': cp.fetched_message_id.id,
                    'seen_message_id': cp.seen_message_id.id,
                } for cp in members_by_channel[channel] if cp.partner_id], key=lambda p: p['partner_id'])
            # add RTC sessions info
            info.update({
                'invitedMembers': [('insert', list(invited_members_by_channel[channel]._mail_channel_member_format(fields={'id': True, 'channel': {}, 'persona': {'partner': {'id', 'name', 'im_status'}, 'guest': {'id', 'name', 'im_status'}}}).values()))],
                'rtcSessions': [('insert', rtc_sessions_by_channel.get(channel, []))],
            })

            info['channel'] = channel_data

            channel_infos.append(info)
        channel_infos_dict = dict((c['id'], c) for c in channel_infos)
        for channel in channels:
            channel_infos_dict[channel.id]['channel']['whatsapp_channel'] = True
            is_tus_insta_messenger_installed = self.env['ir.module.module'].sudo().search(
                [('state', '=', 'installed'), ('name', '=', 'odoo_facebook_instagram_messenger')])
            if is_tus_insta_messenger_installed:
                if channel.facebook_channel or channel.instagram_channel:
                    channel_infos_dict[channel.id]['channel']['whatsapp_channel'] = False
        # print("Exiting loop")
        return list(channel_infos_dict.values())


    # def channel_info(self):
    #     """ whatsapp_channel fields sent in JS
    #     """
    #     print("channel infosss")
    #     channel_infos = super().channel_info()
    #     print("channel info",channel_infos)
    #     channel_infos_dict = dict((c['id'], c) for c in channel_infos)
    #     for channel in self:
    #         channel_infos_dict[channel.id]['channel']['whatsapp_channel'] = True
    #         is_tus_insta_messenger_installed = self.env['ir.module.module'].sudo().search(
    #             [('state', '=', 'installed'), ('name', '=', 'odoo_facebook_instagram_messenger')])
    #         if is_tus_insta_messenger_installed:
    #             if channel.facebook_channel or channel.instagram_channel:
    #                 channel_infos_dict[channel.id]['channel']['whatsapp_channel'] = False
    #     print("Exiting loop")
    #     return list(channel_infos_dict.values())

    @api.model
    def channel_get(self, partners_to, pin=True):
        """ Get the canonical private channel between some partners, create it if needed.
            To reuse an old channel (conversation), this one must be private, and contains
            only the given partners.
            :param partners_to : list of res.partner ids to add to the conversation
            :param pin : True if getting the channel should pin it for the current user
            :returns: channel_info of the created or existing channel
            :rtype: dict
        """
        partner_info = False
        if self.env.user.partner_id.id not in partners_to:
            partner_info = self.env['res.partner'].sudo().search([('id', 'in', partners_to)])
            partners_to.append(self.env.user.partner_id.id)
        # determine type according to the number of partner in the channel
        else:
            partner_info = self.env['res.partner'].sudo().search([('id', 'in', partners_to)])
        self.flush_model()
        self.env['mail.channel.member'].flush_model()
        provider_channel_id = partner_info.channel_provider_line_ids.filtered(lambda s: s.provider_id == self.env.user.provider_id)
        if provider_channel_id:
            if not all(x in provider_channel_id.channel_id.channel_partner_ids.ids for x in partners_to):
                provider_channel_id = False
        if not provider_channel_id:
            provider_channel_id = self.env.user.partner_id.channel_provider_line_ids.filtered(lambda s: s.provider_id == self.env.user.provider_id)
            if not all(x in provider_channel_id.channel_id.channel_partner_ids.ids for x in partners_to):
                provider_channel_id = False

        if provider_channel_id:
            # get the existing channel between the given partners
            channel = self.browse(provider_channel_id.channel_id.id)
            # pin up the channel for the current partner
            if pin:
                self.env['mail.channel.member'].search(
                    [('partner_id', '=', self.env.user.partner_id.id), ('channel_id', '=', channel.id)]).write(
                    {'is_pinned': True})
            channel._broadcast(self.env.user.partner_id.ids)
        else:
            self.env.cr.execute("""
                        SELECT M.channel_id
                        FROM mail_channel C, mail_channel_member M
                        WHERE M.channel_id = C.id
                            AND M.partner_id IN %s
                            AND C.channel_type LIKE 'chat'
                            AND NOT EXISTS (
                                SELECT 1
                                FROM mail_channel_member M2
                                WHERE M2.channel_id = C.id
                                    AND M2.partner_id NOT IN %s
                            )
                        GROUP BY M.channel_id
                        HAVING ARRAY_AGG(DISTINCT M.partner_id ORDER BY M.partner_id) = %s
                        LIMIT 1
                    """, (tuple(partners_to), tuple(partners_to), sorted(list(partners_to)),))
            result = self.env.cr.dictfetchall()
            if result:
                # get the existing channel between the given partners
                channel = self.browse(result[0].get('channel_id'))
                # pin up the channel for the current partner
                if pin:
                    self.env['mail.channel.member'].search(
                        [('partner_id', '=', self.env.user.partner_id.id), ('channel_id', '=', channel.id)]).write({
                        'is_pinned': True,
                        'last_interest_dt': fields.Datetime.now(),
                    })
                channel._broadcast(self.env.user.partner_id.ids)
                return channel.channel_info()[0]

            # create a new one
            channel = self.create({
                'channel_partner_ids': [(4, partner_id) for partner_id in partners_to],
                'channel_member_ids': [
                    Command.create({
                        'partner_id': partner_id,
                        # only pin for the current user, so the chat does not show up for the correspondent until a message has been sent
                        'is_pinned': partner_id == self.env.user.partner_id.id
                    }) for partner_id in partners_to
                ],
                'channel_type': 'chat',
                # 'email_send': False,
                'name': ', '.join(self.env['res.partner'].sudo().browse(partners_to).mapped('name')),
            })
            have_user = self.env['res.users'].search([('partner_id','in',partner_info.ids)])
            if not have_user:
                channel.whatsapp_channel = True
            if partner_info:
                # partner_info.channel_id = channel.id
                partner_info.write({'channel_provider_line_ids': [
                    (0, 0, {'channel_id': channel.id, 'provider_id': self.env.user.provider_id.id})]})
            mail_channel_partner = self.env['mail.channel.member'].sudo().search(
                [('channel_id', '=', channel.id), ('partner_id', '=', self.env.user.partner_id.id)])
            mail_channel_partner.write({'is_pinned': True})
            channel._broadcast(partners_to)
        return channel.channel_info()[0]

    def get_channel_agent(self, channel_id):
        if self.env.user:
            channel = self.env['mail.channel'].sudo().browse(int(channel_id))
            partner_lst = channel.channel_partner_ids.ids
            channel_users = self.env['res.users'].sudo().search_read([('partner_id.id', 'in', partner_lst)],
                                                                     ['id', 'name'])
            users = self.env['res.users'].sudo().search([('partner_id.id', 'not in', partner_lst)])
            users_lst = []
            for user in users:
                if user.has_group('tus_meta_whatsapp_base.whatsapp_group_user') and user.provider_id and user.provider_id == self.env.user.provider_id:
                    users_lst.append({'name': user.name, 'id': user.id})
            dict = {'channel_users': channel_users, 'users': users_lst}
            return dict

    def add_agent(self, user_id, channel_id):
        user = self.env['res.users'].sudo().browse(int(user_id))
        channel = self.env['mail.channel'].sudo().browse(int(channel_id))
        if channel.whatsapp_channel:
            channel.write({'channel_partner_ids': [(4, user.partner_id.id)]})
            mail_channel_partner = self.env['mail.channel.member'].sudo().search(
                [('channel_id', '=', channel_id),
                 ('partner_id', '=', user.partner_id.id)])
            mail_channel_partner.write({'is_pinned': True})
            return True

    def remove_agent(self, user_id, channel_id):
        user = self.env['res.users'].sudo().browse(int(user_id))
        channel = self.env['mail.channel'].sudo().browse(int(channel_id))
        if channel.whatsapp_channel:
            channel.write({'channel_partner_ids': [(3, user.partner_id.id)]})
            return True

    @api.constrains('channel_member_ids', 'channel_partner_ids')
    def _constraint_partners_chat(self):
        pass

    def _set_last_seen_message(self, last_message):
        """
        When Message Seen/Read in odoo, Double Blue Tick (Read Receipts) in WhatsApp
        """
        res = super(Channel, self)._set_last_seen_message(last_message)
        last_message.write({'isWaMsgsRead': True})
        if last_message.isWaMsgsRead == True:
            channel_company_line_id = self.env['channel.provider.line'].search(
                [('channel_id', '=', last_message.res_id)])
            if channel_company_line_id.provider_id:
                provider_id = channel_company_line_id.provider_id
                if provider_id:
                    answer = provider_id.graph_api_wamsg_mark_as_read(last_message.wa_message_id)
                    if answer.status_code == 200:
                        dict = json.loads(answer.text)
                        if provider_id.provider == 'graph_api':  # if condition for Graph API
                            if 'success' in dict and dict.get('success'):
                                last_message.write({'isWaMsgsRead': True})
        return res        
