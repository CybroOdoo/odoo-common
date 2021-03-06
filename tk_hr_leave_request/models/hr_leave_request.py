# -*- encoding: utf-8 -*-
##############################################################################
#
#   Author: Taktik S.A.
#   Copyright (c) 2015 Taktik S.A. (http://www.taktik.be)
#   All Rights Reserved
#
#   WARNING: This program as such is intended to be used by professional
#   programmers who take the whole responsibility of assessing all potential
#   consequences resulting from its eventual inadequacies and bugs.
#   End users who are looking for a ready-to-use solution with commercial
#   guarantees and support are strongly advised to contact a Free Software
#   Service Company.
#
#   This program is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of the
#   License, or (at your option) any later version.
#
#   This program is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#   GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
#############################################################################


import re
from openerp.tools.misc import DEFAULT_SERVER_DATETIME_FORMAT, DEFAULT_SERVER_DATE_FORMAT
from datetime import datetime, timedelta
import random
from openerp import models, api, fields, _


def random_token():
    """
    Compute a random token
    :return: string
    """
    # the token has an entropy of about 120 bits (6 bits/char * 20 chars)
    chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789'
    return ''.join(random.SystemRandom().choice(chars) for i in xrange(20))


class HrHoliday(models.Model):
    _inherit = 'hr.holidays'

    state = fields.Selection(
        [('draft', _('To Submit')),
         ('cancel', _('Cancelled')),
         ('confirm', _('To Approve')),
         ('refuse', _('Refused')),
         ('validate1', _('Second Approval')),
         ('validate', _('Approved'))],
        'Status',
        readonly=True,
        track_visibility='onchange',
        copy=False,
        help='The status is set to \'To Submit\', when a holiday request is created.\
                \nThe status is \'To Approve\', when holiday request is confirmed by user.\
                \nThe status is \'Refused\', when holiday request is refused by manager.\
                \nThe status is \'Approved\', when holiday request is approved by manager.',
        default='draft')

    @api.multi
    def replace_links_body(self, mail_values):
        """
        Replace the value of links in the email template with the updated
        values (token, id , ...)
        """
        action_id = self.env.ref('hr_holidays.open_ask_holidays').id

        hr_holidays_id = self.id

        menu_id = self.env.ref('hr_holidays.menu_open_ask_holidays_new').id

        leave_request = 'web#id=%s&view_type=form&model=hr.holidays&menu_id=%s&action=%s' % (
            str(hr_holidays_id),
            str(menu_id),
            str(action_id)
        )

        mail_body = mail_values.get('body', '')
        mail_body_html = mail_values.get('body_html', '')

        rdict = {
            '_URL_LEAVE_REQUEST_': leave_request,
        }

        robj = re.compile('|'.join(rdict.keys()))
        result_body = robj.sub(
            lambda m: rdict[m.group(0)],
            mail_body
        )
        result_body_html = robj.sub(
            lambda m: rdict[m.group(0)],
            mail_body_html
        )

        mail_values.update({
            'body': result_body,
            'body_html': result_body_html
        })

        return mail_values

    @api.multi
    def write(self, values):
        res = super(HrHoliday, self).write(values)
        if ('state' in values and
                (values.get('state', False) == 'confirm')):
            self.send_request_by_mail()
        if ('state' in values and
                (values.get('state', False) == 'validate' or
                 values.get('state', False) == 'refuse')):
            self.send_response_by_mail()
        return res

    def send_request_by_mail(self):
        mail_obj = self.env['mail.mail']
        template_id = self.env.ref(
            'tk_hr_leave_request.tk_hr_leave_request_email_template'
        )
        # if the employee has a manager it sends a email
        # otherwise we assume the employee has the access right to approve
        # his leave request
        if (self.employee_id.parent_id.user_id and
                self.date_from and self.date_to) or \
                (self.employee_id.parent_id.user_id and self.number_of_days_temp):
            recipient = self.employee_id.parent_id.user_id.partner_id
            self.token = random_token()
            ctx = self.env.context.copy()
            ctx.update({'lang': recipient.lang})
            mail_values = template_id.with_context(ctx).generate_email(
                template_id.id, self.id
            )
            mail_values['recipient_ids'] = [(4, recipient.id)]
            mail_values = self.replace_links_body(mail_values)
            msg_id = mail_obj.create(mail_values)

    def send_response_by_mail(self):
        mail_obj = self.env['mail.mail']
        template_id = self.env.ref(
            'tk_hr_leave_request.tk_hr_response_email_template'
        )
        for holiday in self:
            if holiday.state == 'validate' or holiday.state == 'refuse':
                recipient = holiday.employee_id.user_id.partner_id
                ctx = self.env.context.copy()
                ctx.update({'lang': recipient.lang})
                mail_values = template_id.with_context(ctx).generate_email(template_id.id, holiday.id)
                mail_values['recipient_ids'] = [(4, recipient.id)]
                msg_id = mail_obj.create(mail_values)

    def get_state_lang(self):
        res = ""
        state = self.state
        if state == 'validate':
            if self.employee_id.user_id.lang == 'fr_BE':
                res = u'Approuvé'
            else:
                res = u'Validate'
        elif state == 'refuse':
            if self.employee_id.user_id.lang == 'fr_BE':
                res = u'Refusé'
            else:
                res = u'Refused'
        else:
            res = u'Other'
        return res

    token = fields.Char(
        string="Token",
        required=False
    )
