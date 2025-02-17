# -*- coding: utf-8 -*-
import base64
import datetime
import json
import subprocess

import mock
import pytest

from elastalert.alerts import AlertaAlerter
from elastalert.alerts import Alerter
from elastalert.alerts import BasicMatchString
from elastalert.alerts import CommandAlerter
from elastalert.alerts import EmailAlerter
from elastalert.alerts import HipChatAlerter
from elastalert.alerts import HTTPPostAlerter
from elastalert.alerts import MsTeamsAlerter
from elastalert.alerts import PagerDutyAlerter
from elastalert.alerts import SlackAlerter
from elastalert.alerts import StrideAlerter
from elastalert.loaders import FileRulesLoader
from elastalert.opsgenie import OpsGenieAlerter
from elastalert.util import ts_add
from elastalert.util import ts_now


class mock_rule:
    def get_match_str(self, event):
        return str(event)


def test_basic_match_string(ea):
    ea.rules[0]['top_count_keys'] = ['username']
    match = {'@timestamp': '1918-01-17', 'field': 'value', 'top_events_username': {'bob': 10, 'mallory': 5}}
    alert_text = str(BasicMatchString(ea.rules[0], match))
    assert 'anytest' in alert_text
    assert 'some stuff happened' in alert_text
    assert 'username' in alert_text
    assert 'bob: 10' in alert_text
    assert 'field: value' in alert_text

    # Non serializable objects don't cause errors
    match['non-serializable'] = {open: 10}
    alert_text = str(BasicMatchString(ea.rules[0], match))

    # unicode objects dont cause errors
    match['snowman'] = '☃'
    alert_text = str(BasicMatchString(ea.rules[0], match))

    # Pretty printed objects
    match.pop('non-serializable')
    match['object'] = {'this': {'that': [1, 2, "3"]}}
    alert_text = str(BasicMatchString(ea.rules[0], match))
    assert '"this": {\n        "that": [\n            1,\n            2,\n            "3"\n        ]\n    }' in alert_text

    ea.rules[0]['alert_text'] = 'custom text'
    alert_text = str(BasicMatchString(ea.rules[0], match))
    assert 'custom text' in alert_text
    assert 'anytest' not in alert_text

    ea.rules[0]['alert_text_type'] = 'alert_text_only'
    alert_text = str(BasicMatchString(ea.rules[0], match))
    assert 'custom text' in alert_text
    assert 'some stuff happened' not in alert_text
    assert 'username' not in alert_text
    assert 'field: value' not in alert_text

    ea.rules[0]['alert_text_type'] = 'exclude_fields'
    alert_text = str(BasicMatchString(ea.rules[0], match))
    assert 'custom text' in alert_text
    assert 'some stuff happened' in alert_text
    assert 'username' in alert_text
    assert 'field: value' not in alert_text


def test_email():
    rule = {'name': 'test alert', 'email': ['testing@test.test', 'test@test.test'], 'from_addr': 'testfrom@test.test',
            'type': mock_rule(), 'timestamp_field': '@timestamp', 'email_reply_to': 'test@example.com', 'owner': 'owner_value',
            'alert_subject': 'Test alert for {0}, owned by {1}', 'alert_subject_args': ['test_term', 'owner'], 'snowman': '☃'}
    with mock.patch('elastalert.alerts.SMTP') as mock_smtp:
        mock_smtp.return_value = mock.Mock()

        alert = EmailAlerter(rule)
        alert.alert([{'test_term': 'test_value'}])
        expected = [mock.call('localhost'),
                    mock.call().ehlo(),
                    mock.call().has_extn('STARTTLS'),
                    mock.call().starttls(certfile=None, keyfile=None),
                    mock.call().sendmail(mock.ANY, ['testing@test.test', 'test@test.test'], mock.ANY),
                    mock.call().quit()]
        assert mock_smtp.mock_calls == expected

        body = mock_smtp.mock_calls[4][1][2]

        assert 'Reply-To: test@example.com' in body
        assert 'To: testing@test.test' in body
        assert 'From: testfrom@test.test' in body
        assert 'Subject: Test alert for test_value, owned by owner_value' in body


def test_email_from_field():
    rule = {'name': 'test alert', 'email': ['testing@test.test'], 'email_add_domain': 'example.com',
            'type': mock_rule(), 'timestamp_field': '@timestamp', 'email_from_field': 'data.user', 'owner': 'owner_value'}
    # Found, without @
    with mock.patch('elastalert.alerts.SMTP') as mock_smtp:
        mock_smtp.return_value = mock.Mock()
        alert = EmailAlerter(rule)
        alert.alert([{'data': {'user': 'qlo'}}])
        assert mock_smtp.mock_calls[4][1][1] == ['qlo@example.com']

    # Found, with @
    rule['email_add_domain'] = '@example.com'
    with mock.patch('elastalert.alerts.SMTP') as mock_smtp:
        mock_smtp.return_value = mock.Mock()
        alert = EmailAlerter(rule)
        alert.alert([{'data': {'user': 'qlo'}}])
        assert mock_smtp.mock_calls[4][1][1] == ['qlo@example.com']

    # Found, list
    with mock.patch('elastalert.alerts.SMTP') as mock_smtp:
        mock_smtp.return_value = mock.Mock()
        alert = EmailAlerter(rule)
        alert.alert([{'data': {'user': ['qlo', 'foo']}}])
        assert mock_smtp.mock_calls[4][1][1] == ['qlo@example.com', 'foo@example.com']

    # Not found
    with mock.patch('elastalert.alerts.SMTP') as mock_smtp:
        mock_smtp.return_value = mock.Mock()
        alert = EmailAlerter(rule)
        alert.alert([{'data': {'foo': 'qlo'}}])
        assert mock_smtp.mock_calls[4][1][1] == ['testing@test.test']

    # Found, wrong type
    with mock.patch('elastalert.alerts.SMTP') as mock_smtp:
        mock_smtp.return_value = mock.Mock()
        alert = EmailAlerter(rule)
        alert.alert([{'data': {'user': 17}}])
        assert mock_smtp.mock_calls[4][1][1] == ['testing@test.test']


def test_email_with_unicode_strings():
    rule = {'name': 'test alert', 'email': 'testing@test.test', 'from_addr': 'testfrom@test.test',
            'type': mock_rule(), 'timestamp_field': '@timestamp', 'email_reply_to': 'test@example.com', 'owner': 'owner_value',
            'alert_subject': 'Test alert for {0}, owned by {1}', 'alert_subject_args': ['test_term', 'owner'], 'snowman': '☃'}
    with mock.patch('elastalert.alerts.SMTP') as mock_smtp:
        mock_smtp.return_value = mock.Mock()

        alert = EmailAlerter(rule)
        alert.alert([{'test_term': 'test_value'}])
        expected = [mock.call('localhost'),
                    mock.call().ehlo(),
                    mock.call().has_extn('STARTTLS'),
                    mock.call().starttls(certfile=None, keyfile=None),
                    mock.call().sendmail(mock.ANY, ['testing@test.test'], mock.ANY),
                    mock.call().quit()]
        assert mock_smtp.mock_calls == expected

        body = mock_smtp.mock_calls[4][1][2]

        assert 'Reply-To: test@example.com' in body
        assert 'To: testing@test.test' in body
        assert 'From: testfrom@test.test' in body
        assert 'Subject: Test alert for test_value, owned by owner_value' in body


def test_email_with_auth():
    rule = {'name': 'test alert', 'email': ['testing@test.test', 'test@test.test'], 'from_addr': 'testfrom@test.test',
            'type': mock_rule(), 'timestamp_field': '@timestamp', 'email_reply_to': 'test@example.com',
            'alert_subject': 'Test alert for {0}', 'alert_subject_args': ['test_term'], 'smtp_auth_file': 'file.txt',
            'rule_file': '/tmp/foo.yaml'}
    with mock.patch('elastalert.alerts.SMTP') as mock_smtp:
        with mock.patch('elastalert.alerts.yaml_loader') as mock_open:
            mock_open.return_value = {'user': 'someone', 'password': 'hunter2'}
            mock_smtp.return_value = mock.Mock()
            alert = EmailAlerter(rule)

        alert.alert([{'test_term': 'test_value'}])
        expected = [mock.call('localhost'),
                    mock.call().ehlo(),
                    mock.call().has_extn('STARTTLS'),
                    mock.call().starttls(certfile=None, keyfile=None),
                    mock.call().login('someone', 'hunter2'),
                    mock.call().sendmail(mock.ANY, ['testing@test.test', 'test@test.test'], mock.ANY),
                    mock.call().quit()]
        assert mock_smtp.mock_calls == expected


def test_email_with_cert_key():
    rule = {'name': 'test alert', 'email': ['testing@test.test', 'test@test.test'], 'from_addr': 'testfrom@test.test',
            'type': mock_rule(), 'timestamp_field': '@timestamp', 'email_reply_to': 'test@example.com',
            'alert_subject': 'Test alert for {0}', 'alert_subject_args': ['test_term'], 'smtp_auth_file': 'file.txt',
            'smtp_cert_file': 'dummy/cert.crt', 'smtp_key_file': 'dummy/client.key', 'rule_file': '/tmp/foo.yaml'}
    with mock.patch('elastalert.alerts.SMTP') as mock_smtp:
        with mock.patch('elastalert.alerts.yaml_loader') as mock_open:
            mock_open.return_value = {'user': 'someone', 'password': 'hunter2'}
            mock_smtp.return_value = mock.Mock()
            alert = EmailAlerter(rule)

        alert.alert([{'test_term': 'test_value'}])
        expected = [mock.call('localhost'),
                    mock.call().ehlo(),
                    mock.call().has_extn('STARTTLS'),
                    mock.call().starttls(certfile='dummy/cert.crt', keyfile='dummy/client.key'),
                    mock.call().login('someone', 'hunter2'),
                    mock.call().sendmail(mock.ANY, ['testing@test.test', 'test@test.test'], mock.ANY),
                    mock.call().quit()]
        assert mock_smtp.mock_calls == expected


def test_email_with_cc():
    rule = {'name': 'test alert', 'email': ['testing@test.test', 'test@test.test'], 'from_addr': 'testfrom@test.test',
            'type': mock_rule(), 'timestamp_field': '@timestamp', 'email_reply_to': 'test@example.com',
            'cc': 'tester@testing.testing'}
    with mock.patch('elastalert.alerts.SMTP') as mock_smtp:
        mock_smtp.return_value = mock.Mock()

        alert = EmailAlerter(rule)
        alert.alert([{'test_term': 'test_value'}])
        expected = [mock.call('localhost'),
                    mock.call().ehlo(),
                    mock.call().has_extn('STARTTLS'),
                    mock.call().starttls(certfile=None, keyfile=None),
                    mock.call().sendmail(mock.ANY, ['testing@test.test', 'test@test.test', 'tester@testing.testing'], mock.ANY),
                    mock.call().quit()]
        assert mock_smtp.mock_calls == expected

        body = mock_smtp.mock_calls[4][1][2]

        assert 'Reply-To: test@example.com' in body
        assert 'To: testing@test.test' in body
        assert 'CC: tester@testing.testing' in body
        assert 'From: testfrom@test.test' in body


def test_email_with_bcc():
    rule = {'name': 'test alert', 'email': ['testing@test.test', 'test@test.test'], 'from_addr': 'testfrom@test.test',
            'type': mock_rule(), 'timestamp_field': '@timestamp', 'email_reply_to': 'test@example.com',
            'bcc': 'tester@testing.testing'}
    with mock.patch('elastalert.alerts.SMTP') as mock_smtp:
        mock_smtp.return_value = mock.Mock()

        alert = EmailAlerter(rule)
        alert.alert([{'test_term': 'test_value'}])
        expected = [mock.call('localhost'),
                    mock.call().ehlo(),
                    mock.call().has_extn('STARTTLS'),
                    mock.call().starttls(certfile=None, keyfile=None),
                    mock.call().sendmail(mock.ANY, ['testing@test.test', 'test@test.test', 'tester@testing.testing'], mock.ANY),
                    mock.call().quit()]
        assert mock_smtp.mock_calls == expected

        body = mock_smtp.mock_calls[4][1][2]

        assert 'Reply-To: test@example.com' in body
        assert 'To: testing@test.test' in body
        assert 'CC: tester@testing.testing' not in body
        assert 'From: testfrom@test.test' in body


def test_email_with_cc_and_bcc():
    rule = {'name': 'test alert', 'email': ['testing@test.test', 'test@test.test'], 'from_addr': 'testfrom@test.test',
            'type': mock_rule(), 'timestamp_field': '@timestamp', 'email_reply_to': 'test@example.com',
            'cc': ['test1@test.com', 'test2@test.com'], 'bcc': 'tester@testing.testing'}
    with mock.patch('elastalert.alerts.SMTP') as mock_smtp:
        mock_smtp.return_value = mock.Mock()

        alert = EmailAlerter(rule)
        alert.alert([{'test_term': 'test_value'}])
        expected = [mock.call('localhost'),
                    mock.call().ehlo(),
                    mock.call().has_extn('STARTTLS'),
                    mock.call().starttls(certfile=None, keyfile=None),
                    mock.call().sendmail(
                        mock.ANY,
                        [
                            'testing@test.test',
                            'test@test.test',
                            'test1@test.com',
                            'test2@test.com',
                            'tester@testing.testing'
                        ],
                        mock.ANY
        ),
            mock.call().quit()]
        assert mock_smtp.mock_calls == expected

        body = mock_smtp.mock_calls[4][1][2]

        assert 'Reply-To: test@example.com' in body
        assert 'To: testing@test.test' in body
        assert 'CC: test1@test.com,test2@test.com' in body
        assert 'From: testfrom@test.test' in body


def test_email_with_args():
    rule = {
        'name': 'test alert',
        'email': ['testing@test.test', 'test@test.test'],
        'from_addr': 'testfrom@test.test',
        'type': mock_rule(),
        'timestamp_field': '@timestamp',
        'email_reply_to': 'test@example.com',
        'alert_subject': 'Test alert for {0} {1}',
        'alert_subject_args': ['test_term', 'test.term'],
        'alert_text': 'Test alert for {0} and {1} {2}',
        'alert_text_args': ['test_arg1', 'test_arg2', 'test.arg3'],
        'alert_missing_value': '<CUSTOM MISSING VALUE>'
    }
    with mock.patch('elastalert.alerts.SMTP') as mock_smtp:
        mock_smtp.return_value = mock.Mock()

        alert = EmailAlerter(rule)
        alert.alert([{'test_term': 'test_value', 'test_arg1': 'testing', 'test': {'term': ':)', 'arg3': '☃'}}])
        expected = [mock.call('localhost'),
                    mock.call().ehlo(),
                    mock.call().has_extn('STARTTLS'),
                    mock.call().starttls(certfile=None, keyfile=None),
                    mock.call().sendmail(mock.ANY, ['testing@test.test', 'test@test.test'], mock.ANY),
                    mock.call().quit()]
        assert mock_smtp.mock_calls == expected

        body = mock_smtp.mock_calls[4][1][2]
        # Extract the MIME encoded message body
        body_text = base64.b64decode(body.split('\n\n')[-1][:-1]).decode('utf-8')

        assert 'testing' in body_text
        assert '<CUSTOM MISSING VALUE>' in body_text
        assert '☃' in body_text

        assert 'Reply-To: test@example.com' in body
        assert 'To: testing@test.test' in body
        assert 'From: testfrom@test.test' in body
        assert 'Subject: Test alert for test_value :)' in body


def test_email_query_key_in_subject():
    rule = {'name': 'test alert', 'email': ['testing@test.test', 'test@test.test'],
            'type': mock_rule(), 'timestamp_field': '@timestamp', 'email_reply_to': 'test@example.com',
            'query_key': 'username'}
    with mock.patch('elastalert.alerts.SMTP') as mock_smtp:
        mock_smtp.return_value = mock.Mock()

        alert = EmailAlerter(rule)
        alert.alert([{'test_term': 'test_value', 'username': 'werbenjagermanjensen'}])

        body = mock_smtp.mock_calls[4][1][2]
        lines = body.split('\n')
        found_subject = False
        for line in lines:
            if line.startswith('Subject'):
                assert 'werbenjagermanjensen' in line
                found_subject = True
        assert found_subject


def test_opsgenie_basic():
    rule = {'name': 'testOGalert', 'opsgenie_key': 'ogkey',
            'opsgenie_account': 'genies', 'opsgenie_addr': 'https://api.opsgenie.com/v2/alerts',
            'opsgenie_recipients': ['lytics'], 'type': mock_rule()}
    with mock.patch('requests.post') as mock_post:

        alert = OpsGenieAlerter(rule)
        alert.alert([{'@timestamp': '2014-10-31T00:00:00'}])
        print(("mock_post: {0}".format(mock_post._mock_call_args_list)))
        mcal = mock_post._mock_call_args_list
        print(('mcal: {0}'.format(mcal[0])))
        assert mcal[0][0][0] == ('https://api.opsgenie.com/v2/alerts')

        assert mock_post.called

        assert mcal[0][1]['headers']['Authorization'] == 'GenieKey ogkey'
        assert mcal[0][1]['json']['source'] == 'ElastAlert'
        assert mcal[0][1]['json']['responders'] == [{'username': 'lytics', 'type': 'user'}]
        assert mcal[0][1]['json']['source'] == 'ElastAlert'


def test_opsgenie_frequency():
    rule = {'name': 'testOGalert', 'opsgenie_key': 'ogkey',
            'opsgenie_account': 'genies', 'opsgenie_addr': 'https://api.opsgenie.com/v2/alerts',
            'opsgenie_recipients': ['lytics'], 'type': mock_rule(),
            'filter': [{'query': {'query_string': {'query': '*hihi*'}}}],
            'alert': 'opsgenie'}
    with mock.patch('requests.post') as mock_post:

        alert = OpsGenieAlerter(rule)
        alert.alert([{'@timestamp': '2014-10-31T00:00:00'}])

        assert alert.get_info()['recipients'] == rule['opsgenie_recipients']

        print(("mock_post: {0}".format(mock_post._mock_call_args_list)))
        mcal = mock_post._mock_call_args_list
        print(('mcal: {0}'.format(mcal[0])))
        assert mcal[0][0][0] == ('https://api.opsgenie.com/v2/alerts')

        assert mock_post.called

        assert mcal[0][1]['headers']['Authorization'] == 'GenieKey ogkey'
        assert mcal[0][1]['json']['source'] == 'ElastAlert'
        assert mcal[0][1]['json']['responders'] == [{'username': 'lytics', 'type': 'user'}]
        assert mcal[0][1]['json']['source'] == 'ElastAlert'
        assert mcal[0][1]['json']['source'] == 'ElastAlert'


def test_opsgenie_alert_routing():
    rule = {'name': 'testOGalert', 'opsgenie_key': 'ogkey',
            'opsgenie_account': 'genies', 'opsgenie_addr': 'https://api.opsgenie.com/v2/alerts',
            'opsgenie_recipients': ['{RECEIPIENT_PREFIX}'], 'opsgenie_recipients_args': {'RECEIPIENT_PREFIX': 'recipient'},
            'type': mock_rule(),
            'filter': [{'query': {'query_string': {'query': '*hihi*'}}}],
            'alert': 'opsgenie',
            'opsgenie_teams': ['{TEAM_PREFIX}-Team'], 'opsgenie_teams_args': {'TEAM_PREFIX': 'team'}}
    with mock.patch('requests.post'):

        alert = OpsGenieAlerter(rule)
        alert.alert([{'@timestamp': '2014-10-31T00:00:00', 'team': "Test", 'recipient': "lytics"}])

        assert alert.get_info()['teams'] == ['Test-Team']
        assert alert.get_info()['recipients'] == ['lytics']


def test_opsgenie_default_alert_routing():
    rule = {'name': 'testOGalert', 'opsgenie_key': 'ogkey',
            'opsgenie_account': 'genies', 'opsgenie_addr': 'https://api.opsgenie.com/v2/alerts',
            'opsgenie_recipients': ['{RECEIPIENT_PREFIX}'], 'opsgenie_recipients_args': {'RECEIPIENT_PREFIX': 'recipient'},
            'type': mock_rule(),
            'filter': [{'query': {'query_string': {'query': '*hihi*'}}}],
            'alert': 'opsgenie',
            'opsgenie_teams': ['{TEAM_PREFIX}-Team'],
            'opsgenie_default_receipients': ["devops@test.com"], 'opsgenie_default_teams': ["Test"]
            }
    with mock.patch('requests.post'):

        alert = OpsGenieAlerter(rule)
        alert.alert([{'@timestamp': '2014-10-31T00:00:00', 'team': "Test"}])

        assert alert.get_info()['teams'] == ['{TEAM_PREFIX}-Team']
        assert alert.get_info()['recipients'] == ['devops@test.com']


def test_kibana(ea):
    rule = {'filter': [{'query': {'query_string': {'query': 'xy:z'}}}],
            'name': 'Test rule!',
            'es_host': 'test.testing',
            'es_port': 12345,
            'timeframe': datetime.timedelta(hours=1),
            'index': 'logstash-test',
            'include': ['@timestamp'],
            'timestamp_field': '@timestamp'}
    match = {'@timestamp': '2014-10-10T00:00:00'}
    with mock.patch("elastalert.elastalert.elasticsearch_client") as mock_es:
        mock_create = mock.Mock(return_value={'_id': 'ABCDEFGH'})
        mock_es_inst = mock.Mock()
        mock_es_inst.index = mock_create
        mock_es_inst.host = 'test.testing'
        mock_es_inst.port = 12345
        mock_es.return_value = mock_es_inst
        link = ea.generate_kibana_db(rule, match)

    assert 'http://test.testing:12345/_plugin/kibana/#/dashboard/temp/ABCDEFGH' == link

    # Name and index
    dashboard = json.loads(mock_create.call_args_list[0][1]['body']['dashboard'])
    assert dashboard['index']['default'] == 'logstash-test'
    assert 'Test rule!' in dashboard['title']

    # Filters and time range
    filters = dashboard['services']['filter']['list']
    assert 'xy:z' in filters['1']['query']
    assert filters['1']['type'] == 'querystring'
    time_range = filters['0']
    assert time_range['from'] == ts_add(match['@timestamp'], -rule['timeframe'])
    assert time_range['to'] == ts_add(match['@timestamp'], datetime.timedelta(minutes=10))

    # Included fields active in table
    assert dashboard['rows'][1]['panels'][0]['fields'] == ['@timestamp']


def test_command():
    # Test command as list with a formatted arg
    rule = {'command': ['/bin/test/', '--arg', '%(somefield)s']}
    alert = CommandAlerter(rule)
    match = {'@timestamp': '2014-01-01T00:00:00',
             'somefield': 'foobarbaz',
             'nested': {'field': 1}}
    with mock.patch("elastalert.alerts.subprocess.Popen") as mock_popen:
        alert.alert([match])
    assert mock_popen.called_with(['/bin/test', '--arg', 'foobarbaz'], stdin=subprocess.PIPE, shell=False)

    # Test command as string with formatted arg (old-style string format)
    rule = {'command': '/bin/test/ --arg %(somefield)s'}
    alert = CommandAlerter(rule)
    with mock.patch("elastalert.alerts.subprocess.Popen") as mock_popen:
        alert.alert([match])
    assert mock_popen.called_with('/bin/test --arg foobarbaz', stdin=subprocess.PIPE, shell=False)

    # Test command as string without formatted arg (old-style string format)
    rule = {'command': '/bin/test/foo.sh'}
    alert = CommandAlerter(rule)
    with mock.patch("elastalert.alerts.subprocess.Popen") as mock_popen:
        alert.alert([match])
    assert mock_popen.called_with('/bin/test/foo.sh', stdin=subprocess.PIPE, shell=True)

    # Test command as string with formatted arg (new-style string format)
    rule = {'command': '/bin/test/ --arg {match[somefield]}', 'new_style_string_format': True}
    alert = CommandAlerter(rule)
    with mock.patch("elastalert.alerts.subprocess.Popen") as mock_popen:
        alert.alert([match])
    assert mock_popen.called_with('/bin/test --arg foobarbaz', stdin=subprocess.PIPE, shell=False)

    rule = {'command': '/bin/test/ --arg {match[nested][field]}', 'new_style_string_format': True}
    alert = CommandAlerter(rule)
    with mock.patch("elastalert.alerts.subprocess.Popen") as mock_popen:
        alert.alert([match])
    assert mock_popen.called_with('/bin/test --arg 1', stdin=subprocess.PIPE, shell=False)

    # Test command as string without formatted arg (new-style string format)
    rule = {'command': '/bin/test/foo.sh', 'new_style_string_format': True}
    alert = CommandAlerter(rule)
    with mock.patch("elastalert.alerts.subprocess.Popen") as mock_popen:
        alert.alert([match])
    assert mock_popen.called_with('/bin/test/foo.sh', stdin=subprocess.PIPE, shell=True)

    rule = {'command': '/bin/test/foo.sh {{bar}}', 'new_style_string_format': True}
    alert = CommandAlerter(rule)
    with mock.patch("elastalert.alerts.subprocess.Popen") as mock_popen:
        alert.alert([match])
    assert mock_popen.called_with('/bin/test/foo.sh {bar}', stdin=subprocess.PIPE, shell=True)

    # Test command with pipe_match_json
    rule = {'command': ['/bin/test/', '--arg', '%(somefield)s'],
            'pipe_match_json': True}
    alert = CommandAlerter(rule)
    match = {'@timestamp': '2014-01-01T00:00:00',
             'somefield': 'foobarbaz'}
    with mock.patch("elastalert.alerts.subprocess.Popen") as mock_popen:
        mock_subprocess = mock.Mock()
        mock_popen.return_value = mock_subprocess
        mock_subprocess.communicate.return_value = (None, None)
        alert.alert([match])
    assert mock_popen.called_with(['/bin/test', '--arg', 'foobarbaz'], stdin=subprocess.PIPE, shell=False)
    assert mock_subprocess.communicate.called_with(input=json.dumps(match))

    # Test command with fail_on_non_zero_exit
    rule = {'command': ['/bin/test/', '--arg', '%(somefield)s'],
            'fail_on_non_zero_exit': True}
    alert = CommandAlerter(rule)
    match = {'@timestamp': '2014-01-01T00:00:00',
             'somefield': 'foobarbaz'}
    with pytest.raises(Exception) as exception:
        with mock.patch("elastalert.alerts.subprocess.Popen") as mock_popen:
            mock_subprocess = mock.Mock()
            mock_popen.return_value = mock_subprocess
            mock_subprocess.wait.return_value = 1
            alert.alert([match])
    assert mock_popen.called_with(['/bin/test', '--arg', 'foobarbaz'], stdin=subprocess.PIPE, shell=False)
    assert "Non-zero exit code while running command" in str(exception)


def test_ms_teams():
    rule = {
        'name': 'Test Rule',
        'type': 'any',
        'ms_teams_webhook_url': 'http://test.webhook.url',
        'ms_teams_alert_summary': 'Alert from ElastAlert',
        'alert_subject': 'Cool subject',
        'alert': []
    }
    rules_loader = FileRulesLoader({})
    rules_loader.load_modules(rule)
    alert = MsTeamsAlerter(rule)
    match = {
        '@timestamp': '2016-01-01T00:00:00',
        'somefield': 'foobarbaz'
    }
    with mock.patch('requests.post') as mock_post_request:
        alert.alert([match])

    expected_data = {
        '@type': 'MessageCard',
        '@context': 'http://schema.org/extensions',
        'summary': rule['ms_teams_alert_summary'],
        'title': rule['alert_subject'],
        'text': BasicMatchString(rule, match).__str__()
    }
    mock_post_request.assert_called_once_with(
        rule['ms_teams_webhook_url'],
        data=mock.ANY,
        headers={'content-type': 'application/json'},
        proxies=None
    )
    assert expected_data == json.loads(mock_post_request.call_args_list[0][1]['data'])


def test_ms_teams_uses_color_and_fixed_width_text():
    rule = {
        'name': 'Test Rule',
        'type': 'any',
        'ms_teams_webhook_url': 'http://test.webhook.url',
        'ms_teams_alert_summary': 'Alert from ElastAlert',
        'ms_teams_alert_fixed_width': True,
        'ms_teams_theme_color': '#124578',
        'alert_subject': 'Cool subject',
        'alert': []
    }
    rules_loader = FileRulesLoader({})
    rules_loader.load_modules(rule)
    alert = MsTeamsAlerter(rule)
    match = {
        '@timestamp': '2016-01-01T00:00:00',
        'somefield': 'foobarbaz'
    }
    with mock.patch('requests.post') as mock_post_request:
        alert.alert([match])
    body = BasicMatchString(rule, match).__str__()
    body = body.replace('`', "'")
    body = "```{0}```".format('```\n\n```'.join(x for x in body.split('\n'))).replace('\n``````', '')
    expected_data = {
        '@type': 'MessageCard',
        '@context': 'http://schema.org/extensions',
        'summary': rule['ms_teams_alert_summary'],
        'title': rule['alert_subject'],
        'themeColor': '#124578',
        'text': body
    }
    mock_post_request.assert_called_once_with(
        rule['ms_teams_webhook_url'],
        data=mock.ANY,
        headers={'content-type': 'application/json'},
        proxies=None
    )
    assert expected_data == json.loads(mock_post_request.call_args_list[0][1]['data'])


def test_slack_uses_custom_title():
    rule = {
        'name': 'Test Rule',
        'type': 'any',
        'slack_webhook_url': 'http://please.dontgohere.slack',
        'alert_subject': 'Cool subject',
        'alert': []
    }
    rules_loader = FileRulesLoader({})
    rules_loader.load_modules(rule)
    alert = SlackAlerter(rule)
    match = {
        '@timestamp': '2016-01-01T00:00:00',
        'somefield': 'foobarbaz'
    }
    with mock.patch('requests.post') as mock_post_request:
        alert.alert([match])

    expected_data = {
        'username': 'elastalert',
        'channel': '',
        'icon_emoji': ':ghost:',
        'attachments': [
            {
                'color': 'danger',
                'title': rule['alert_subject'],
                'text': BasicMatchString(rule, match).__str__(),
                'mrkdwn_in': ['text', 'pretext'],
                'fields': []
            }
        ],
        'text': '',
        'parse': 'none'
    }
    mock_post_request.assert_called_once_with(
        rule['slack_webhook_url'],
        data=mock.ANY,
        headers={'content-type': 'application/json'},
        proxies=None,
        verify=False,
        timeout=10
    )
    assert expected_data == json.loads(mock_post_request.call_args_list[0][1]['data'])


def test_slack_uses_custom_timeout():
    rule = {
        'name': 'Test Rule',
        'type': 'any',
        'slack_webhook_url': 'http://please.dontgohere.slack',
        'alert_subject': 'Cool subject',
        'alert': [],
        'slack_timeout': 20
    }
    rules_loader = FileRulesLoader({})
    rules_loader.load_modules(rule)
    alert = SlackAlerter(rule)
    match = {
        '@timestamp': '2016-01-01T00:00:00',
        'somefield': 'foobarbaz'
    }
    with mock.patch('requests.post') as mock_post_request:
        alert.alert([match])

    expected_data = {
        'username': 'elastalert',
        'channel': '',
        'icon_emoji': ':ghost:',
        'attachments': [
            {
                'color': 'danger',
                'title': rule['alert_subject'],
                'text': BasicMatchString(rule, match).__str__(),
                'mrkdwn_in': ['text', 'pretext'],
                'fields': []
            }
        ],
        'text': '',
        'parse': 'none'
    }
    mock_post_request.assert_called_once_with(
        rule['slack_webhook_url'],
        data=mock.ANY,
        headers={'content-type': 'application/json'},
        proxies=None,
        verify=False,
        timeout=20
    )
    assert expected_data == json.loads(mock_post_request.call_args_list[0][1]['data'])


def test_slack_uses_rule_name_when_custom_title_is_not_provided():
    rule = {
        'name': 'Test Rule',
        'type': 'any',
        'slack_webhook_url': ['http://please.dontgohere.slack'],
        'alert': []
    }
    rules_loader = FileRulesLoader({})
    rules_loader.load_modules(rule)
    alert = SlackAlerter(rule)
    match = {
        '@timestamp': '2016-01-01T00:00:00',
        'somefield': 'foobarbaz'
    }
    with mock.patch('requests.post') as mock_post_request:
        alert.alert([match])

    expected_data = {
        'username': 'elastalert',
        'channel': '',
        'icon_emoji': ':ghost:',
        'attachments': [
            {
                'color': 'danger',
                'title': rule['name'],
                'text': BasicMatchString(rule, match).__str__(),
                'mrkdwn_in': ['text', 'pretext'],
                'fields': []
            }
        ],
        'text': '',
        'parse': 'none',
    }
    mock_post_request.assert_called_once_with(
        rule['slack_webhook_url'][0],
        data=mock.ANY,
        headers={'content-type': 'application/json'},
        proxies=None,
        verify=False,
        timeout=10
    )
    assert expected_data == json.loads(mock_post_request.call_args_list[0][1]['data'])


def test_slack_uses_custom_slack_channel():
    rule = {
        'name': 'Test Rule',
        'type': 'any',
        'slack_webhook_url': ['http://please.dontgohere.slack'],
        'slack_channel_override': '#test-alert',
        'alert': []
    }
    rules_loader = FileRulesLoader({})
    rules_loader.load_modules(rule)
    alert = SlackAlerter(rule)
    match = {
        '@timestamp': '2016-01-01T00:00:00',
        'somefield': 'foobarbaz'
    }
    with mock.patch('requests.post') as mock_post_request:
        alert.alert([match])

    expected_data = {
        'username': 'elastalert',
        'channel': '#test-alert',
        'icon_emoji': ':ghost:',
        'attachments': [
            {
                'color': 'danger',
                'title': rule['name'],
                'text': BasicMatchString(rule, match).__str__(),
                'mrkdwn_in': ['text', 'pretext'],
                'fields': []
            }
        ],
        'text': '',
        'parse': 'none',
    }
    mock_post_request.assert_called_once_with(
        rule['slack_webhook_url'][0],
        data=mock.ANY,
        headers={'content-type': 'application/json'},
        proxies=None,
        verify=False,
        timeout=10
    )
    assert expected_data == json.loads(mock_post_request.call_args_list[0][1]['data'])


def test_slack_uses_list_of_custom_slack_channel():
    rule = {
        'name': 'Test Rule',
        'type': 'any',
        'slack_webhook_url': ['http://please.dontgohere.slack'],
        'slack_channel_override': ['#test-alert', '#test-alert2'],
        'alert': []
    }
    rules_loader = FileRulesLoader({})
    rules_loader.load_modules(rule)
    alert = SlackAlerter(rule)
    match = {
        '@timestamp': '2016-01-01T00:00:00',
        'somefield': 'foobarbaz'
    }
    with mock.patch('requests.post') as mock_post_request:
        alert.alert([match])

    expected_data1 = {
        'username': 'elastalert',
        'channel': '#test-alert',
        'icon_emoji': ':ghost:',
        'attachments': [
            {
                'color': 'danger',
                'title': rule['name'],
                'text': BasicMatchString(rule, match).__str__(),
                'mrkdwn_in': ['text', 'pretext'],
                'fields': []
            }
        ],
        'text': '',
        'parse': 'none'
    }
    expected_data2 = {
        'username': 'elastalert',
        'channel': '#test-alert2',
        'icon_emoji': ':ghost:',
        'attachments': [
            {
                'color': 'danger',
                'title': rule['name'],
                'text': BasicMatchString(rule, match).__str__(),
                'mrkdwn_in': ['text', 'pretext'],
                'fields': []
            }
        ],
        'text': '',
        'parse': 'none'
    }
    mock_post_request.assert_called_with(
        rule['slack_webhook_url'][0],
        data=mock.ANY,
        headers={'content-type': 'application/json'},
        proxies=None,
        verify=False,
        timeout=10
    )
    assert expected_data1 == json.loads(mock_post_request.call_args_list[0][1]['data'])
    assert expected_data2 == json.loads(mock_post_request.call_args_list[1][1]['data'])


def test_http_alerter_with_payload():
    rule = {
        'name': 'Test HTTP Post Alerter With Payload',
        'type': 'any',
        'http_post_url': 'http://test.webhook.url',
        'http_post_payload': {'posted_name': 'somefield'},
        'http_post_static_payload': {'name': 'somestaticname'},
        'alert': []
    }
    rules_loader = FileRulesLoader({})
    rules_loader.load_modules(rule)
    alert = HTTPPostAlerter(rule)
    match = {
        '@timestamp': '2017-01-01T00:00:00',
        'somefield': 'foobarbaz'
    }
    with mock.patch('requests.post') as mock_post_request:
        alert.alert([match])
    expected_data = {
        'posted_name': 'foobarbaz',
        'name': 'somestaticname'
    }
    mock_post_request.assert_called_once_with(
        rule['http_post_url'],
        data=mock.ANY,
        headers={'Content-Type': 'application/json', 'Accept': 'application/json;charset=utf-8'},
        proxies=None,
        timeout=10
    )
    assert expected_data == json.loads(mock_post_request.call_args_list[0][1]['data'])


def test_http_alerter_with_payload_all_values():
    rule = {
        'name': 'Test HTTP Post Alerter With Payload',
        'type': 'any',
        'http_post_url': 'http://test.webhook.url',
        'http_post_payload': {'posted_name': 'somefield'},
        'http_post_static_payload': {'name': 'somestaticname'},
        'http_post_all_values': True,
        'alert': []
    }
    rules_loader = FileRulesLoader({})
    rules_loader.load_modules(rule)
    alert = HTTPPostAlerter(rule)
    match = {
        '@timestamp': '2017-01-01T00:00:00',
        'somefield': 'foobarbaz'
    }
    with mock.patch('requests.post') as mock_post_request:
        alert.alert([match])
    expected_data = {
        'posted_name': 'foobarbaz',
        'name': 'somestaticname',
        '@timestamp': '2017-01-01T00:00:00',
        'somefield': 'foobarbaz'
    }
    mock_post_request.assert_called_once_with(
        rule['http_post_url'],
        data=mock.ANY,
        headers={'Content-Type': 'application/json', 'Accept': 'application/json;charset=utf-8'},
        proxies=None,
        timeout=10
    )
    assert expected_data == json.loads(mock_post_request.call_args_list[0][1]['data'])


def test_http_alerter_without_payload():
    rule = {
        'name': 'Test HTTP Post Alerter Without Payload',
        'type': 'any',
        'http_post_url': 'http://test.webhook.url',
        'http_post_static_payload': {'name': 'somestaticname'},
        'alert': []
    }
    rules_loader = FileRulesLoader({})
    rules_loader.load_modules(rule)
    alert = HTTPPostAlerter(rule)
    match = {
        '@timestamp': '2017-01-01T00:00:00',
        'somefield': 'foobarbaz'
    }
    with mock.patch('requests.post') as mock_post_request:
        alert.alert([match])
    expected_data = {
        '@timestamp': '2017-01-01T00:00:00',
        'somefield': 'foobarbaz',
        'name': 'somestaticname'
    }
    mock_post_request.assert_called_once_with(
        rule['http_post_url'],
        data=mock.ANY,
        headers={'Content-Type': 'application/json', 'Accept': 'application/json;charset=utf-8'},
        proxies=None,
        timeout=10
    )
    assert expected_data == json.loads(mock_post_request.call_args_list[0][1]['data'])


def test_pagerduty_alerter():
    rule = {
        'name': 'Test PD Rule',
        'type': 'any',
        'pagerduty_service_key': 'magicalbadgers',
        'pagerduty_client_name': 'ponies inc.',
        'alert': []
    }
    rules_loader = FileRulesLoader({})
    rules_loader.load_modules(rule)
    alert = PagerDutyAlerter(rule)
    match = {
        '@timestamp': '2017-01-01T00:00:00',
        'somefield': 'foobarbaz'
    }
    with mock.patch('requests.post') as mock_post_request:
        alert.alert([match])
    expected_data = {
        'client': 'ponies inc.',
        'description': 'Test PD Rule',
        'details': {
            'information': 'Test PD Rule\n\n@timestamp: 2017-01-01T00:00:00\nsomefield: foobarbaz\n'
        },
        'event_type': 'trigger',
        'incident_key': '',
        'service_key': 'magicalbadgers',
    }
    mock_post_request.assert_called_once_with('https://events.pagerduty.com/generic/2010-04-15/create_event.json',
                                              data=mock.ANY, headers={'content-type': 'application/json'}, proxies=None)
    assert expected_data == json.loads(mock_post_request.call_args_list[0][1]['data'])


def test_pagerduty_alerter_v2():
    rule = {
        'name': 'Test PD Rule',
        'type': 'any',
        'pagerduty_service_key': 'magicalbadgers',
        'pagerduty_client_name': 'ponies inc.',
        'pagerduty_api_version': 'v2',
        'pagerduty_v2_payload_class': 'ping failure',
        'pagerduty_v2_payload_component': 'mysql',
        'pagerduty_v2_payload_group': 'app-stack',
        'pagerduty_v2_payload_severity': 'error',
        'pagerduty_v2_payload_source': 'mysql.host.name',
        'alert': []
    }
    rules_loader = FileRulesLoader({})
    rules_loader.load_modules(rule)
    alert = PagerDutyAlerter(rule)
    match = {
        '@timestamp': '2017-01-01T00:00:00',
        'somefield': 'foobarbaz'
    }
    with mock.patch('requests.post') as mock_post_request:
        alert.alert([match])
    expected_data = {
        'client': 'ponies inc.',
        'payload': {
            'class': 'ping failure',
            'component': 'mysql',
            'group': 'app-stack',
            'severity': 'error',
            'source': 'mysql.host.name',
            'summary': 'Test PD Rule',
            'custom_details': {
                'information': 'Test PD Rule\n\n@timestamp: 2017-01-01T00:00:00\nsomefield: foobarbaz\n'
            },
            'timestamp': '2017-01-01T00:00:00'
        },
        'event_action': 'trigger',
        'dedup_key': '',
        'routing_key': 'magicalbadgers',
    }
    mock_post_request.assert_called_once_with('https://events.pagerduty.com/v2/enqueue',
                                              data=mock.ANY, headers={'content-type': 'application/json'}, proxies=None)
    assert expected_data == json.loads(mock_post_request.call_args_list[0][1]['data'])


def test_pagerduty_alerter_custom_incident_key():
    rule = {
        'name': 'Test PD Rule',
        'type': 'any',
        'pagerduty_service_key': 'magicalbadgers',
        'pagerduty_client_name': 'ponies inc.',
        'pagerduty_incident_key': 'custom key',
        'alert': []
    }
    rules_loader = FileRulesLoader({})
    rules_loader.load_modules(rule)
    alert = PagerDutyAlerter(rule)
    match = {
        '@timestamp': '2017-01-01T00:00:00',
        'somefield': 'foobarbaz'
    }
    with mock.patch('requests.post') as mock_post_request:
        alert.alert([match])
    expected_data = {
        'client': 'ponies inc.',
        'description': 'Test PD Rule',
        'details': {
            'information': 'Test PD Rule\n\n@timestamp: 2017-01-01T00:00:00\nsomefield: foobarbaz\n'
        },
        'event_type': 'trigger',
        'incident_key': 'custom key',
        'service_key': 'magicalbadgers',
    }
    mock_post_request.assert_called_once_with(alert.url, data=mock.ANY, headers={'content-type': 'application/json'}, proxies=None)
    assert expected_data == json.loads(mock_post_request.call_args_list[0][1]['data'])


def test_pagerduty_alerter_custom_incident_key_with_args():
    rule = {
        'name': 'Test PD Rule',
        'type': 'any',
        'pagerduty_service_key': 'magicalbadgers',
        'pagerduty_client_name': 'ponies inc.',
        'pagerduty_incident_key': 'custom {0}',
        'pagerduty_incident_key_args': ['somefield'],
        'alert': []
    }
    rules_loader = FileRulesLoader({})
    rules_loader.load_modules(rule)
    alert = PagerDutyAlerter(rule)
    match = {
        '@timestamp': '2017-01-01T00:00:00',
        'somefield': 'foobarbaz'
    }
    with mock.patch('requests.post') as mock_post_request:
        alert.alert([match])
    expected_data = {
        'client': 'ponies inc.',
        'description': 'Test PD Rule',
        'details': {
            'information': 'Test PD Rule\n\n@timestamp: 2017-01-01T00:00:00\nsomefield: foobarbaz\n'
        },
        'event_type': 'trigger',
        'incident_key': 'custom foobarbaz',
        'service_key': 'magicalbadgers',
    }
    mock_post_request.assert_called_once_with(alert.url, data=mock.ANY, headers={'content-type': 'application/json'}, proxies=None)
    assert expected_data == json.loads(mock_post_request.call_args_list[0][1]['data'])


def test_pagerduty_alerter_custom_alert_subject():
    rule = {
        'name': 'Test PD Rule',
        'type': 'any',
        'alert_subject': 'Hungry kittens',
        'pagerduty_service_key': 'magicalbadgers',
        'pagerduty_client_name': 'ponies inc.',
        'pagerduty_incident_key': 'custom {0}',
        'pagerduty_incident_key_args': ['somefield'],
        'alert': []
    }
    rules_loader = FileRulesLoader({})
    rules_loader.load_modules(rule)
    alert = PagerDutyAlerter(rule)
    match = {
        '@timestamp': '2017-01-01T00:00:00',
        'somefield': 'foobarbaz'
    }
    with mock.patch('requests.post') as mock_post_request:
        alert.alert([match])
    expected_data = {
        'client': 'ponies inc.',
        'description': 'Hungry kittens',
        'details': {
            'information': 'Test PD Rule\n\n@timestamp: 2017-01-01T00:00:00\nsomefield: foobarbaz\n'
        },
        'event_type': 'trigger',
        'incident_key': 'custom foobarbaz',
        'service_key': 'magicalbadgers',
    }
    mock_post_request.assert_called_once_with(alert.url, data=mock.ANY, headers={'content-type': 'application/json'}, proxies=None)
    assert expected_data == json.loads(mock_post_request.call_args_list[0][1]['data'])


def test_pagerduty_alerter_custom_alert_subject_with_args():
    rule = {
        'name': 'Test PD Rule',
        'type': 'any',
        'alert_subject': '{0} kittens',
        'alert_subject_args': ['somefield'],
        'pagerduty_service_key': 'magicalbadgers',
        'pagerduty_client_name': 'ponies inc.',
        'pagerduty_incident_key': 'custom {0}',
        'pagerduty_incident_key_args': ['someotherfield'],
        'alert': []
    }
    rules_loader = FileRulesLoader({})
    rules_loader.load_modules(rule)
    alert = PagerDutyAlerter(rule)
    match = {
        '@timestamp': '2017-01-01T00:00:00',
        'somefield': 'Stinky',
        'someotherfield': 'foobarbaz'
    }
    with mock.patch('requests.post') as mock_post_request:
        alert.alert([match])
    expected_data = {
        'client': 'ponies inc.',
        'description': 'Stinky kittens',
        'details': {
            'information': 'Test PD Rule\n\n@timestamp: 2017-01-01T00:00:00\nsomefield: Stinky\nsomeotherfield: foobarbaz\n'
        },
        'event_type': 'trigger',
        'incident_key': 'custom foobarbaz',
        'service_key': 'magicalbadgers',
    }
    mock_post_request.assert_called_once_with(alert.url, data=mock.ANY, headers={'content-type': 'application/json'}, proxies=None)
    assert expected_data == json.loads(mock_post_request.call_args_list[0][1]['data'])


def test_pagerduty_alerter_custom_alert_subject_with_args_specifying_trigger():
    rule = {
        'name': 'Test PD Rule',
        'type': 'any',
        'alert_subject': '{0} kittens',
        'alert_subject_args': ['somefield'],
        'pagerduty_service_key': 'magicalbadgers',
        'pagerduty_event_type': 'trigger',
        'pagerduty_client_name': 'ponies inc.',
        'pagerduty_incident_key': 'custom {0}',
        'pagerduty_incident_key_args': ['someotherfield'],
        'alert': []
    }
    rules_loader = FileRulesLoader({})
    rules_loader.load_modules(rule)
    alert = PagerDutyAlerter(rule)
    match = {
        '@timestamp': '2017-01-01T00:00:00',
        'somefield': 'Stinkiest',
        'someotherfield': 'foobarbaz'
    }
    with mock.patch('requests.post') as mock_post_request:
        alert.alert([match])
    expected_data = {
        'client': 'ponies inc.',
        'description': 'Stinkiest kittens',
        'details': {
            'information': 'Test PD Rule\n\n@timestamp: 2017-01-01T00:00:00\nsomefield: Stinkiest\nsomeotherfield: foobarbaz\n'
        },
        'event_type': 'trigger',
        'incident_key': 'custom foobarbaz',
        'service_key': 'magicalbadgers',
    }
    mock_post_request.assert_called_once_with(alert.url, data=mock.ANY, headers={'content-type': 'application/json'}, proxies=None)
    assert expected_data == json.loads(mock_post_request.call_args_list[0][1]['data'])


def test_alert_text_kw(ea):
    rule = ea.rules[0].copy()
    rule['alert_text'] = '{field} at {time}'
    rule['alert_text_kw'] = {
        '@timestamp': 'time',
        'field': 'field',
    }
    match = {'@timestamp': '1918-01-17', 'field': 'value'}
    alert_text = str(BasicMatchString(rule, match))
    body = '{field} at {@timestamp}'.format(**match)
    assert body in alert_text


def test_alert_text_global_substitution(ea):
    rule = ea.rules[0].copy()
    rule['owner'] = 'the owner from rule'
    rule['priority'] = 'priority from rule'
    rule['abc'] = 'abc from rule'
    rule['alert_text'] = 'Priority: {0}; Owner: {1}; Abc: {2}'
    rule['alert_text_args'] = ['priority', 'owner', 'abc']

    match = {
        '@timestamp': '2016-01-01',
        'field': 'field_value',
        'abc': 'abc from match',
    }

    alert_text = str(BasicMatchString(rule, match))
    assert 'Priority: priority from rule' in alert_text
    assert 'Owner: the owner from rule' in alert_text

    # When the key exists in both places, it will come from the match
    assert 'Abc: abc from match' in alert_text


def test_alert_text_kw_global_substitution(ea):
    rule = ea.rules[0].copy()
    rule['foo_rule'] = 'foo from rule'
    rule['owner'] = 'the owner from rule'
    rule['abc'] = 'abc from rule'
    rule['alert_text'] = 'Owner: {owner}; Foo: {foo}; Abc: {abc}'
    rule['alert_text_kw'] = {
        'owner': 'owner',
        'foo_rule': 'foo',
        'abc': 'abc',
    }

    match = {
        '@timestamp': '2016-01-01',
        'field': 'field_value',
        'abc': 'abc from match',
    }

    alert_text = str(BasicMatchString(rule, match))
    assert 'Owner: the owner from rule' in alert_text
    assert 'Foo: foo from rule' in alert_text

    # When the key exists in both places, it will come from the match
    assert 'Abc: abc from match' in alert_text


def test_resolving_rule_references(ea):
    rule = {
        'name': 'test_rule',
        'type': mock_rule(),
        'owner': 'the_owner',
        'priority': 2,
        'list_of_things': [
            '1',
            '$owner$',
            [
                '11',
                '$owner$',
            ],
        ],
        'nested_dict': {
            'nested_one': '1',
            'nested_owner': '$owner$',
        },
        'resolved_string_reference': '$owner$',
        'resolved_int_reference': '$priority$',
        'unresolved_reference': '$foo$',
    }
    alert = Alerter(rule)
    assert 'the_owner' == alert.rule['resolved_string_reference']
    assert 2 == alert.rule['resolved_int_reference']
    assert '$foo$' == alert.rule['unresolved_reference']
    assert 'the_owner' == alert.rule['list_of_things'][1]
    assert 'the_owner' == alert.rule['list_of_things'][2][1]
    assert 'the_owner' == alert.rule['nested_dict']['nested_owner']


def test_stride_plain_text():
    rule = {
        'name': 'Test Rule',
        'type': 'any',
        'stride_access_token': 'token',
        'stride_cloud_id': 'cloud_id',
        'stride_conversation_id': 'conversation_id',
        'alert_subject': 'Cool subject',
        'alert': []
    }
    rules_loader = FileRulesLoader({})
    rules_loader.load_modules(rule)
    alert = StrideAlerter(rule)
    match = {
        '@timestamp': '2016-01-01T00:00:00',
        'somefield': 'foobarbaz'
    }
    with mock.patch('requests.post') as mock_post_request:
        alert.alert([match])

    body = "{0}\n\n@timestamp: {1}\nsomefield: {2}".format(
        rule['name'], match['@timestamp'], match['somefield']
    )
    expected_data = {'body': {'version': 1, 'type': "doc", 'content': [
        {'type': "panel", 'attrs': {'panelType': "warning"}, 'content': [
            {'type': 'paragraph', 'content': [
                {'type': 'text', 'text': body}
            ]}
        ]}
    ]}}

    mock_post_request.assert_called_once_with(
        alert.url,
        data=mock.ANY,
        headers={
            'content-type': 'application/json',
            'Authorization': 'Bearer {}'.format(rule['stride_access_token'])},
        verify=True,
        proxies=None
    )
    assert expected_data == json.loads(
        mock_post_request.call_args_list[0][1]['data'])


def test_stride_underline_text():
    rule = {
        'name': 'Test Rule',
        'type': 'any',
        'stride_access_token': 'token',
        'stride_cloud_id': 'cloud_id',
        'stride_conversation_id': 'conversation_id',
        'alert_subject': 'Cool subject',
        'alert_text': '<u>Underline Text</u>',
        'alert_text_type': 'alert_text_only',
        'alert': []
    }
    rules_loader = FileRulesLoader({})
    rules_loader.load_modules(rule)
    alert = StrideAlerter(rule)
    match = {
        '@timestamp': '2016-01-01T00:00:00',
        'somefield': 'foobarbaz'
    }
    with mock.patch('requests.post') as mock_post_request:
        alert.alert([match])

    body = "Underline Text"
    expected_data = {'body': {'version': 1, 'type': "doc", 'content': [
        {'type': "panel", 'attrs': {'panelType': "warning"}, 'content': [
            {'type': 'paragraph', 'content': [
                {'type': 'text', 'text': body, 'marks': [
                    {'type': 'underline'}
                ]}
            ]}
        ]}
    ]}}

    mock_post_request.assert_called_once_with(
        alert.url,
        data=mock.ANY,
        headers={
            'content-type': 'application/json',
            'Authorization': 'Bearer {}'.format(rule['stride_access_token'])},
        verify=True,
        proxies=None
    )
    assert expected_data == json.loads(
        mock_post_request.call_args_list[0][1]['data'])


def test_stride_bold_text():
    rule = {
        'name': 'Test Rule',
        'type': 'any',
        'stride_access_token': 'token',
        'stride_cloud_id': 'cloud_id',
        'stride_conversation_id': 'conversation_id',
        'alert_subject': 'Cool subject',
        'alert_text': '<b>Bold Text</b>',
        'alert_text_type': 'alert_text_only',
        'alert': []
    }
    rules_loader = FileRulesLoader({})
    rules_loader.load_modules(rule)
    alert = StrideAlerter(rule)
    match = {
        '@timestamp': '2016-01-01T00:00:00',
        'somefield': 'foobarbaz'
    }
    with mock.patch('requests.post') as mock_post_request:
        alert.alert([match])

    body = "Bold Text"
    expected_data = {'body': {'version': 1, 'type': "doc", 'content': [
        {'type': "panel", 'attrs': {'panelType': "warning"}, 'content': [
            {'type': 'paragraph', 'content': [
                {'type': 'text', 'text': body, 'marks': [
                    {'type': 'strong'}
                ]}
            ]}
        ]}
    ]}}

    mock_post_request.assert_called_once_with(
        alert.url,
        data=mock.ANY,
        headers={
            'content-type': 'application/json',
            'Authorization': 'Bearer {}'.format(rule['stride_access_token'])},
        verify=True,
        proxies=None
    )
    assert expected_data == json.loads(
        mock_post_request.call_args_list[0][1]['data'])


def test_stride_strong_text():
    rule = {
        'name': 'Test Rule',
        'type': 'any',
        'stride_access_token': 'token',
        'stride_cloud_id': 'cloud_id',
        'stride_conversation_id': 'conversation_id',
        'alert_subject': 'Cool subject',
        'alert_text': '<strong>Bold Text</strong>',
        'alert_text_type': 'alert_text_only',
        'alert': []
    }
    rules_loader = FileRulesLoader({})
    rules_loader.load_modules(rule)
    alert = StrideAlerter(rule)
    match = {
        '@timestamp': '2016-01-01T00:00:00',
        'somefield': 'foobarbaz'
    }
    with mock.patch('requests.post') as mock_post_request:
        alert.alert([match])

    body = "Bold Text"
    expected_data = {'body': {'version': 1, 'type': "doc", 'content': [
        {'type': "panel", 'attrs': {'panelType': "warning"}, 'content': [
            {'type': 'paragraph', 'content': [
                {'type': 'text', 'text': body, 'marks': [
                    {'type': 'strong'}
                ]}
            ]}
        ]}
    ]}}

    mock_post_request.assert_called_once_with(
        alert.url,
        data=mock.ANY,
        headers={
            'content-type': 'application/json',
            'Authorization': 'Bearer {}'.format(rule['stride_access_token'])},
        verify=True,
        proxies=None
    )
    assert expected_data == json.loads(
        mock_post_request.call_args_list[0][1]['data'])


def test_stride_hyperlink():
    rule = {
        'name': 'Test Rule',
        'type': 'any',
        'stride_access_token': 'token',
        'stride_cloud_id': 'cloud_id',
        'stride_conversation_id': 'conversation_id',
        'alert_subject': 'Cool subject',
        'alert_text': '<a href="http://stride.com">Link</a>',
        'alert_text_type': 'alert_text_only',
        'alert': []
    }
    rules_loader = FileRulesLoader({})
    rules_loader.load_modules(rule)
    alert = StrideAlerter(rule)
    match = {
        '@timestamp': '2016-01-01T00:00:00',
        'somefield': 'foobarbaz'
    }
    with mock.patch('requests.post') as mock_post_request:
        alert.alert([match])

    body = "Link"
    expected_data = {'body': {'version': 1, 'type': "doc", 'content': [
        {'type': "panel", 'attrs': {'panelType': "warning"}, 'content': [
            {'type': 'paragraph', 'content': [
                {'type': 'text', 'text': body, 'marks': [
                    {'type': 'link', 'attrs': {'href': 'http://stride.com'}}
                ]}
            ]}
        ]}
    ]}}

    mock_post_request.assert_called_once_with(
        alert.url,
        data=mock.ANY,
        headers={
            'content-type': 'application/json',
            'Authorization': 'Bearer {}'.format(rule['stride_access_token'])},
        verify=True,
        proxies=None
    )
    assert expected_data == json.loads(
        mock_post_request.call_args_list[0][1]['data'])


def test_stride_html():
    rule = {
        'name': 'Test Rule',
        'type': 'any',
        'stride_access_token': 'token',
        'stride_cloud_id': 'cloud_id',
        'stride_conversation_id': 'conversation_id',
        'alert_subject': 'Cool subject',
        'alert_text': '<b>Alert</b>: we found something. <a href="http://stride.com">Link</a>',
        'alert_text_type': 'alert_text_only',
        'alert': []
    }
    rules_loader = FileRulesLoader({})
    rules_loader.load_modules(rule)
    alert = StrideAlerter(rule)
    match = {
        '@timestamp': '2016-01-01T00:00:00',
        'somefield': 'foobarbaz'
    }
    with mock.patch('requests.post') as mock_post_request:
        alert.alert([match])

    expected_data = {'body': {'version': 1, 'type': "doc", 'content': [
        {'type': "panel", 'attrs': {'panelType': "warning"}, 'content': [
            {'type': 'paragraph', 'content': [
                {'type': 'text', 'text': 'Alert', 'marks': [
                    {'type': 'strong'}
                ]},
                {'type': 'text', 'text': ': we found something. '},
                {'type': 'text', 'text': 'Link', 'marks': [
                    {'type': 'link', 'attrs': {'href': 'http://stride.com'}}
                ]}
            ]}
        ]}
    ]}}

    mock_post_request.assert_called_once_with(
        alert.url,
        data=mock.ANY,
        headers={
            'content-type': 'application/json',
            'Authorization': 'Bearer {}'.format(rule['stride_access_token'])},
        verify=True,
        proxies=None
    )
    assert expected_data == json.loads(
        mock_post_request.call_args_list[0][1]['data'])


def test_hipchat_body_size_limit_text():
    rule = {
        'name': 'Test Rule',
        'type': 'any',
        'hipchat_auth_token': 'token',
        'hipchat_room_id': 'room_id',
        'hipchat_message_format': 'text',
        'alert_subject': 'Cool subject',
        'alert_text': 'Alert: we found something.\n\n{message}',
        'alert_text_type': 'alert_text_only',
        'alert': [],
        'alert_text_kw': {
            '@timestamp': 'time',
            'message': 'message',
        },
    }
    rules_loader = FileRulesLoader({})
    rules_loader.load_modules(rule)
    alert = HipChatAlerter(rule)
    match = {
        '@timestamp': '2018-01-01T00:00:00',
        'message': 'foo bar\n' * 5000,
    }
    body = alert.create_alert_body([match])

    assert len(body) <= 10000


def test_hipchat_body_size_limit_html():
    rule = {
        'name': 'Test Rule',
        'type': 'any',
        'hipchat_auth_token': 'token',
        'hipchat_room_id': 'room_id',
        'hipchat_message_format': 'html',
        'alert_subject': 'Cool subject',
        'alert_text': 'Alert: we found something.\n\n{message}',
        'alert_text_type': 'alert_text_only',
        'alert': [],
        'alert_text_kw': {
            '@timestamp': 'time',
            'message': 'message',
        },
    }
    rules_loader = FileRulesLoader({})
    rules_loader.load_modules(rule)
    alert = HipChatAlerter(rule)
    match = {
        '@timestamp': '2018-01-01T00:00:00',
        'message': 'foo bar\n' * 5000,
    }

    body = alert.create_alert_body([match])

    assert len(body) <= 10000


def test_alerta_no_auth(ea):
    rule = {
        'name': 'Test Alerta rule!',
        'alerta_api_url': 'http://elastalerthost:8080/api/alert',
        'timeframe': datetime.timedelta(hours=1),
        'timestamp_field': '@timestamp',
        'alerta_api_skip_ssl': True,
        'alerta_attributes_keys': ["hostname", "TimestampEvent", "senderIP"],
        'alerta_attributes_values': ["%(key)s", "%(logdate)s", "%(sender_ip)s"],
        'alerta_correlate': ["ProbeUP", "ProbeDOWN"],
        'alerta_event': "ProbeUP",
        'alerta_group': "Health",
        'alerta_origin': "Elastalert",
        'alerta_severity': "debug",
        'alerta_text': "Probe %(hostname)s is UP at %(logdate)s GMT",
        'alerta_value': "UP",
        'type': 'any',
        'alerta_use_match_timestamp': True,
        'alert': 'alerta'
    }

    match = {
        '@timestamp': '2014-10-10T00:00:00',
        # 'key': ---- missing field on purpose, to verify that simply the text is left empty
        # 'logdate': ---- missing field on purpose, to verify that simply the text is left empty
        'sender_ip': '1.1.1.1',
        'hostname': 'aProbe'
    }

    rules_loader = FileRulesLoader({})
    rules_loader.load_modules(rule)
    alert = AlertaAlerter(rule)
    with mock.patch('requests.post') as mock_post_request:
        alert.alert([match])

    expected_data = {
        "origin": "Elastalert",
        "resource": "elastalert",
        "severity": "debug",
        "service": ["elastalert"],
        "tags": [],
        "text": "Probe aProbe is UP at <MISSING VALUE> GMT",
        "value": "UP",
        "createTime": "2014-10-10T00:00:00.000000Z",
        "environment": "Production",
        "rawData": "Test Alerta rule!\n\n@timestamp: 2014-10-10T00:00:00\nhostname: aProbe\nsender_ip: 1.1.1.1\n",
        "timeout": 86400,
        "correlate": ["ProbeUP", "ProbeDOWN"],
        "group": "Health",
        "attributes": {"senderIP": "1.1.1.1", "hostname": "<MISSING VALUE>", "TimestampEvent": "<MISSING VALUE>"},
        "type": "elastalert",
        "event": "ProbeUP"
    }

    mock_post_request.assert_called_once_with(
        alert.url,
        data=mock.ANY,
        headers={
            'content-type': 'application/json'},
        verify=False
    )
    assert expected_data == json.loads(
        mock_post_request.call_args_list[0][1]['data'])


def test_alerta_auth(ea):
    rule = {
        'name': 'Test Alerta rule!',
        'alerta_api_url': 'http://elastalerthost:8080/api/alert',
        'alerta_api_key': '123456789ABCDEF',
        'timeframe': datetime.timedelta(hours=1),
        'timestamp_field': '@timestamp',
        'alerta_severity': "debug",
        'type': 'any',
        'alerta_use_match_timestamp': True,
        'alert': 'alerta'
    }

    match = {
        '@timestamp': '2014-10-10T00:00:00',
        'sender_ip': '1.1.1.1',
        'hostname': 'aProbe'
    }

    rules_loader = FileRulesLoader({})
    rules_loader.load_modules(rule)
    alert = AlertaAlerter(rule)
    with mock.patch('requests.post') as mock_post_request:
        alert.alert([match])

    mock_post_request.assert_called_once_with(
        alert.url,
        data=mock.ANY,
        verify=True,
        headers={
            'content-type': 'application/json',
            'Authorization': 'Key {}'.format(rule['alerta_api_key'])})


def test_alerta_new_style(ea):
    rule = {
        'name': 'Test Alerta rule!',
        'alerta_api_url': 'http://elastalerthost:8080/api/alert',
        'timeframe': datetime.timedelta(hours=1),
        'timestamp_field': '@timestamp',
        'alerta_attributes_keys': ["hostname", "TimestampEvent", "senderIP"],
        'alerta_attributes_values': ["{hostname}", "{logdate}", "{sender_ip}"],
        'alerta_correlate': ["ProbeUP", "ProbeDOWN"],
        'alerta_event': "ProbeUP",
        'alerta_group': "Health",
        'alerta_origin': "Elastalert",
        'alerta_severity': "debug",
        'alerta_text': "Probe {hostname} is UP at {logdate} GMT",
        'alerta_value': "UP",
        'alerta_new_style_string_format': True,
        'type': 'any',
        'alerta_use_match_timestamp': True,
        'alert': 'alerta'
    }

    match = {
        '@timestamp': '2014-10-10T00:00:00',
        # 'key': ---- missing field on purpose, to verify that simply the text is left empty
        # 'logdate': ---- missing field on purpose, to verify that simply the text is left empty
        'sender_ip': '1.1.1.1',
        'hostname': 'aProbe'
    }

    rules_loader = FileRulesLoader({})
    rules_loader.load_modules(rule)
    alert = AlertaAlerter(rule)
    with mock.patch('requests.post') as mock_post_request:
        alert.alert([match])

    expected_data = {
        "origin": "Elastalert",
        "resource": "elastalert",
        "severity": "debug",
        "service": ["elastalert"],
        "tags": [],
        "text": "Probe aProbe is UP at <MISSING VALUE> GMT",
        "value": "UP",
        "createTime": "2014-10-10T00:00:00.000000Z",
        "environment": "Production",
        "rawData": "Test Alerta rule!\n\n@timestamp: 2014-10-10T00:00:00\nhostname: aProbe\nsender_ip: 1.1.1.1\n",
        "timeout": 86400,
        "correlate": ["ProbeUP", "ProbeDOWN"],
        "group": "Health",
        "attributes": {"senderIP": "1.1.1.1", "hostname": "aProbe", "TimestampEvent": "<MISSING VALUE>"},
        "type": "elastalert",
        "event": "ProbeUP"
    }

    mock_post_request.assert_called_once_with(
        alert.url,
        data=mock.ANY,
        verify=True,
        headers={
            'content-type': 'application/json'}
    )
    assert expected_data == json.loads(
        mock_post_request.call_args_list[0][1]['data'])


def test_alert_subject_size_limit_no_args(ea):
    rule = {
        'name': 'test_rule',
        'type': mock_rule(),
        'owner': 'the_owner',
        'priority': 2,
        'alert_subject': 'A very long subject',
        'alert_subject_max_len': 5
    }
    alert = Alerter(rule)
    alertSubject = alert.create_custom_title([{'test_term': 'test_value', '@timestamp': '2014-10-31T00:00:00'}])
    assert 5 == len(alertSubject)


def test_alert_subject_size_limit_with_args(ea):
    rule = {
        'name': 'test_rule',
        'type': mock_rule(),
        'owner': 'the_owner',
        'priority': 2,
        'alert_subject': 'Test alert for {0} {1}',
        'alert_subject_args': ['test_term', 'test.term'],
        'alert_subject_max_len': 6
    }
    alert = Alerter(rule)
    alertSubject = alert.create_custom_title([{'test_term': 'test_value', '@timestamp': '2014-10-31T00:00:00'}])
    assert 6 == len(alertSubject)
