import logging
import json
import requests
from datetime import datetime

from odoo import api, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class MTSConfiguration(models.Model):
    _name = 'mts.configuration'
    _description = 'Mosip Token Seeder Importers Configuration'

    conf_name = fields.Char(string='Name', required=True)
    # only odk input, json output, and callback deliverytype supported as of now
    mts_url = fields.Char(string='URL to reach MTS', required=True, default='http://mosip-token-seeder.mosip-token-seeder')
    input_type = fields.Selection([('odk', 'ODK'), ('custom', 'Custom')], string='MTS Input Type', required=True)
    mapping = fields.Text(string='Mapping', required=True, default='{"vid": "vid","name": ["name"],"gender": "gender","dob": "dob","phoneNumber": "phoneNumber","emailId": "emailId","fullAddress": ["fullAddress"]}')
    output_type = fields.Selection([('json', 'JSON')], string='MTS Output Type', required=True)
    output_format = fields.Text(string='MTS Output Format', required=False)
    delivery_type = fields.Selection([('callback', 'Callback')],string='MTS Delivery Type', required=True)
    lang_code = fields.Char(string='Mosip Language', required=True, default='eng')
    job_status = fields.Selection([('draft','Draft'),('started','Started'),('running', 'Running'), ('completed', 'Completed')], string='Status', required=True, default='draft')

    # Job Configurations
    is_recurring = fields.Selection([('recurring', 'Recurring'),('onetime', 'One time')], string='Job Type', required=True)
    cron_id = fields.Many2one('ir.cron', string='Cron Job', help='linked to this MTS configuration', required=False)
    start_datetime = fields.Datetime(string='Start Time', required=False)
    end_datetime = fields.Datetime(string='End Time', required=False)
    interval_minutes = fields.Integer(string='Interval in minutes', required=False)

    # odk configurations
    odk_base_url = fields.Char(string='ODK Base Url', required=False)
    odk_version = fields.Char(string='ODK Url Version', required=False, default='v1')
    odk_project_id = fields.Char(string='ODK Project Id', required=False)
    odk_form_id = fields.Char(string='ODK form id', required=False)
    odk_email = fields.Char(string='ODK User email', required=False)
    odk_password = fields.Char(string='ODK User password', required=False)

    # callback configurations
    callback_url = fields.Char(string='Callback URL', required=False)
    callback_httpmethod = fields.Selection([('POST', 'POST'), ('PUT','PUT'), ('GET', 'GET')],string='Callback HTTP Method', required=False)
    callback_timeout = fields.Integer(string='Callback Timeout', required=False)
    callback_authtype = fields.Selection([('odoo','Odoo')],string='Callback Auth Type', required=False)
    callback_auth_url = fields.Char(string='Callback Auth Url', required=False)
    callback_database = fields.Char(string='Callback Auth Database', required=False)
    callback_username = fields.Char(string='Callback Auth Username', required=False)
    callback_password = fields.Char(string='Callback Auth Password', required=False)

    @api.constrains('start_datetime')
    def constraint_start_date(self):
        for rec in self:
            if rec.start_datetime:
                if rec.start_datetime > datetime.now():
                    raise ValidationError('Start Time cannot be after the current time.')

    @api.constrains('end_datetime')
    def constraint_end_date(self):
        for rec in self:
            if rec.end_datetime:
                if rec.end_datetime > datetime.now():
                    raise ValidationError('End Time cannot be after the current time.')
                if rec.end_datetime < rec.start_datetime:
                    raise ValidationError('End Time cannot be after Start Time.')

    @api.constrains('mapping', 'output_format')
    def constraint_json_fields(self):
        for rec in self:
            if rec.mapping:
                try:
                    json.loads(rec.mapping)
                except:
                    raise ValidationError('Mapping is not valid json.')
            if rec.output_format:
                try:
                    json.loads(rec.output_format)
                except:
                    raise ValidationError('Output Format is not valid json.')

    def mts_action_trigger(self):
        for rec in self:
            if rec.job_status == 'draft' or rec.job_status == 'completed':
                _logger.info('Job Started')
                rec.job_status = 'started'
                if rec.is_recurring == 'recurring':
                    ir_cron = self.env['ir.cron'].sudo()
                    rec.cron_id = ir_cron.create({
                        'name': 'MTS Cron ' + rec.conf_name + ' #' + str(rec.id),
                        'active': True,
                        'interval_number': rec.interval_minutes,
                        'interval_type': 'minutes',
                        'model_id': self.env['ir.model'].search([('model','=','mts.configuration')]).id,
                        'state': 'code',
                        'code': 'model.mts_onetime_action(' + str(rec.id)+ ')',
                        'doall': False,
                        'numbercall':-1
                    })
                    rec.job_status = 'running'
                elif rec.is_recurring == 'onetime':
                    self.with_delay().mts_onetime_action(rec.id)
                    _logger.info('Initialized one time ' + str(rec.id))
            elif rec.job_status == 'started' or rec.job_status == 'running':
                _logger.info('Job Stopped')
                rec.job_status = 'completed'
                if rec.is_recurring == 'recurring':
                    rec.sudo().cron_id.unlink()
                    rec.cron_id = None

    def mts_onetime_action(self, id : int):
        _logger.info('Being called everytime. Id: ' + str(id))
        current_conf = self.env['mts.configuration'].browse(id)
        # execute here
        if current_conf.input_type=='custom':
            current_conf.custom_single_action()
            return
        dt_utc = datetime.utcnow()
        mts_request = {
            "id": "string",
            "version": "string",
            "metadata": "string",
            "requesttime": dt_utc.strftime('%Y-%m-%dT%H:%M:%S') + dt_utc.strftime('.%f')[0:4] + 'Z',
            "request": {
                "output": current_conf.output_type,
                "deliverytype": current_conf.delivery_type,
                "mapping": json.loads(current_conf.mapping),
                "lang": current_conf.lang_code,
                "outputFormat": current_conf.output_format,
                "callbackProperties": {
                    "url": current_conf.callback_url,
                    "httpMethod": current_conf.callback_httpmethod,
                    "timeoutSeconds": current_conf.callback_timeout,
                    "callInBulk": False,
                    "authType": current_conf.callback_authtype,
                    "database": current_conf.callback_database,
                    "odooAuthUrl": current_conf.callback_auth_url,
                    "username": current_conf.callback_username,
                    "password": current_conf.callback_password,
                }
            }
        }
        mts_res = requests.post('%s/authtoken/%s' % (current_conf.mts_url,current_conf.input_type), json=mts_request)
        _logger.info('Output of MTS %s', mts_res.text)
        if current_conf.is_recurring == 'onetime':
            current_conf.job_status = 'completed'

    def custom_single_action(self):
        # to be overloaded by other modules.
        _logger.info("Custom Single Action Called")