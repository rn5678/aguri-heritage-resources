"""No-network tests for public post-release readiness guard."""
import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch
spec=importlib.util.spec_from_file_location('deploy_health',Path(__file__).with_name('deploy_from_github.py'))
d=importlib.util.module_from_spec(spec);spec.loader.exec_module(d)
class HealthTests(unittest.TestCase):
    def response(self, path='/api/config', body=None, status=200, destination=None):
        r=MagicMock();r.__enter__.return_value=r;r.status=status
        r.geturl.return_value=destination or d.SITE.rstrip('/')+path
        r.read.return_value=json.dumps(body if body is not None else {'available':True}).encode()
        return r
    def check(self): d.Deployment.verify_live_health(object())
    def test_healthy_public_checks_without_credentials(self):
        with patch.object(d,'urlopen',side_effect=[self.response(),self.response('/api/contact/config')]) as get:
            self.check()
            self.assertEqual(get.call_count,2)
            for call in get.call_args_list:
                self.assertNotIn('Authorization',dict(call.args[0].header_items()))
                self.assertEqual(call.args[0].get_method(),'GET')
    def test_transient_failure_retries_without_deploy(self):
        with patch.object(d,'urlopen',side_effect=[d.URLError('private detail'),self.response('/api/contact/config'),self.response(),self.response('/api/contact/config')]) as get,patch.object(d.time,'sleep') as sleep:
            self.check();self.assertEqual(get.call_count,4);sleep.assert_called_once_with(5)
    def test_only_allowlisted_category_enters_failure_metadata(self):
        for category, expected in [('security', 'security'), ('secret-should-never-escape', 'unavailable'), ({'bad': 'private'}, 'unavailable')]:
            with patch.object(d, 'urlopen', return_value=self.response(body={'available': False, 'readiness': category})), patch.object(d.time, 'sleep'), self.assertRaises(d.DeployError) as raised:
                self.check()
            self.assertEqual(raised.exception.readiness['contributions'], expected)
            self.assertNotIn('secret-should', str(raised.exception))

    def test_fail_closed_false_malformed_oversized_and_redirect(self):
        cases=[self.response(body={'available':False}),self.response(body={'available':'true'}),self.response(body=[]),self.response(destination='https://other.example/api/config')]
        malformed=self.response();malformed.read.return_value=b'private invalid body';cases.append(malformed)
        huge=self.response();huge.read.return_value=b'x'*16385;cases.append(huge)
        for response in cases:
            with self.subTest(response=response),patch.object(d,'urlopen',return_value=response),patch.object(d.time,'sleep'),self.assertRaises(d.DeployError) as raised:
                self.check()
            self.assertNotIn('private',str(raised.exception));self.assertIn('repair configuration forward',str(raised.exception))
if __name__=='__main__':unittest.main()
