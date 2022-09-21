import logging
import json
import requests
from datetime import date, datetime

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class G2PMTSConfiguration(models.Model):
    _inherit = 'mts.configuration'

    def custom_single_action(self):
        _logger.info("Custom Input action called.")
        search_domain = [
            ('is_registrant','=', True),
            ('reg_ids.id_type','=like', 'MOSIP VID'),
            '!', ('reg_ids.id_type','=like','MOSIP UIN TOKEN')
        ]
        selected_fields = [
            'id',
            'given_name',
            'family_name',
            'birthdate',
            'gender'
        ]
        record_set = self.env['res.partner'].search(search_domain, limit=100)
        if len(record_set)>0:
            record_list = record_set.read(selected_fields)
            for i, rec in enumerate(record_set):
                for reg_id in rec.reg_ids:
                    if reg_id.id_type.name == 'MOSIP VID':
                        record_list[i]['vid'] = reg_id.value
                        break
                record_list[i]['phoneNumber'] = rec.phone_number_ids[0].phone_no
            record_list = json.loads(json.dumps(record_list, default=self.record_set_json_serialize))
            _logger.info('The recordset for debug %s', json.dumps(record_list))
            dt_utc = datetime.utcnow()
            mts_request = {
                "id": "string",
                "version": "string",
                "metadata": "string",
                "requesttime": dt_utc.strftime('%Y-%m-%dT%H:%M:%S') + dt_utc.strftime('.%f')[0:4] + 'Z',
                "request": {
                    "output": self.output_type,
                    "deliverytype": self.delivery_type,
                    "mapping": json.loads(self.mapping),
                    "lang": self.lang_code,
                    "outputFormat": self.output_format,
                    "callbackProperties": {
                        "url": self.callback_url,
                        "httpMethod": self.callback_httpmethod,
                        "timeoutSeconds": self.callback_timeout,
                        "callInBulk": False,
                        "authType": self.callback_authtype,
                        "database": self.callback_database,
                        "odooAuthUrl": self.callback_auth_url,
                        "username": self.callback_username,
                        "password": self.callback_password,
                    },
                    "authdata": record_list
                }
            }
            mts_res = requests.post('%s/authtoken/%s' % (self.mts_url,'json'), json=mts_request)
            _logger.info('Output of MTS %s', mts_res.text)
        if self.is_recurring == 'onetime':
            self.job_status = 'completed'

    def record_set_json_serialize(self, obj):
        if isinstance(obj, date):
            return obj.strftime('%Y/%m/%d')
        _logger.info('Cannot serialize obj type %s. Hence returning string', type(obj))
        return str(obj)

    def delete_vids_if_token(self):
        search_domain = [
            ('is_registrant','=', True),
            ('reg_ids.id_type','=like', 'MOSIP VID'),
            ('reg_ids.id_type','=like','MOSIP UIN TOKEN')
        ]
        for rec in self.env['res.partner'].search(search_domain):
            vid_reg_id = None
            uin_token_reg_id = None
            for reg_id in rec.reg_ids:
                if reg_id.id_type.name == 'MOSIP VID':
                    vid_reg_id = reg_id
                if reg_id.id_type.name == 'MOSIP UIN TOKEN':
                    uin_token_reg_id = reg_id
                if vid_reg_id and uin_token_reg_id:
                    break
            if uin_token_reg_id.status == 'processed' and uin_token_reg_id.value:
                vid_reg_id.unlink()
