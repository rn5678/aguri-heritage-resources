"""Exercise the publishing HTTP boundary on an isolated loopback server.

The publisher and translator are mocks. These tests never read credentials,
write project source, contact GitHub/Cloudflare, or use the live editor port.
"""
from http.client import HTTPConnection
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock, call, patch


SPEC = importlib.util.spec_from_file_location(
    'content_editor_publishing_http_tested', Path(__file__).with_name('content_editor.py'))
editor = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = editor
SPEC.loader.exec_module(editor)

TOKEN = 'isolated-http-test-token'
POST_PATHS = ('/api/publish/prepare', '/api/publish/confirm')


class PublishingHTTP(unittest.TestCase):
    def setUp(self):
        temporary = self.enterContext(tempfile.TemporaryDirectory(prefix='aguri-editor-http-'))
        self.root = Path(temporary)
        self.lock = threading.Lock()
        self.publisher = Mock()
        self.publisher.status.return_value = {'phase': 'idle', 'message': 'Saved locally.'}
        self.publisher.start_prepare.return_value = {'phase': 'preparing'}
        self.publisher.start_publish.return_value = {'phase': 'publishing'}
        self.translator = Mock(spec=['assert_publish_ready'])
        self.publisher_factory = self.enterContext(patch.object(editor, 'publisher', return_value=self.publisher))
        self.translator_factory = self.enterContext(patch.object(editor, 'translator', return_value=self.translator))
        self.enterContext(patch.object(editor, 'ROOT', self.root))
        self.enterContext(patch.object(editor, 'TOKEN', TOKEN))
        self.enterContext(patch.object(editor, 'LOCK', self.lock))
        self.server = editor.ThreadingHTTPServer(('127.0.0.1', 0), editor.Handler)
        self.port = self.server.server_port
        self.origin = f'http://127.0.0.1:{self.port}'
        self.thread = threading.Thread(
            target=self.server.serve_forever, kwargs={'poll_interval': 0.01}, daemon=True)
        self.thread.start()
        self.addCleanup(self.close_server)

    def close_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.assertFalse(self.thread.is_alive(), 'The isolated test server did not stop.')

    def request(self, method, path, *, body='{}', headers=None):
        request_headers = {
            'Host': f'127.0.0.1:{self.port}',
            'X-Editor-Token': TOKEN,
        }
        if method == 'POST':
            request_headers.update({'Origin': self.origin, 'Content-Type': 'application/json'})
        for name, value in (headers or {}).items():
            if value is None:
                request_headers.pop(name, None)
            else:
                request_headers[name] = value
        connection = HTTPConnection('127.0.0.1', self.port, timeout=3)
        try:
            connection.request(method, path, body=body if method == 'POST' else None,
                               headers=request_headers)
            response = connection.getresponse()
            content = response.read()
            data = (json.loads(content) if response.getheader('Content-Type', '').startswith('application/json')
                    else content.decode())
            return response.status, dict(response.getheaders()), data
        finally:
            connection.close()

    def assert_no_backend_calls(self):
        self.publisher_factory.assert_not_called()
        self.translator_factory.assert_not_called()
        self.assertEqual(list(self.root.iterdir()), [])

    def test_status_requires_valid_token_and_is_read_only(self):
        for token in (None, '', 'incorrect-token'):
            with self.subTest(token=token):
                status, _, _ = self.request('GET', '/api/publish/status', headers={'X-Editor-Token': token})
                self.assertEqual(status, 403)
                self.assert_no_backend_calls()
        status, headers, data = self.request('GET', '/api/publish/status')
        self.assertEqual(status, 200)
        self.assertEqual(data['phase'], 'idle')
        self.assertEqual(headers['Cache-Control'], 'no-store')
        self.assertEqual(self.publisher.mock_calls, [call.status()])
        self.translator_factory.assert_not_called()

    def test_manual_status_refresh_requires_authentication_and_an_explicit_flag(self):
        path = '/api/publish/status?refresh=1'
        for token in (None, '', 'incorrect-token'):
            with self.subTest(token=token):
                status, _, _ = self.request('GET', path, headers={'X-Editor-Token': token})
                self.assertEqual(status, 403)
                self.assert_no_backend_calls()
        status, _, data = self.request('GET', path)
        self.assertEqual((status, data['phase']), (200, 'idle'))
        self.publisher.status.assert_called_once_with(refresh=True)
        self.publisher.reset_mock()
        for query in ('', '?refresh=0', '?refresh=true', '?refresh=1&refresh=1'):
            with self.subTest(query=query):
                status, _, _ = self.request('GET', '/api/publish/status' + query)
                self.assertEqual(status, 200)
                self.publisher.status.assert_called_once_with()
                self.publisher.reset_mock()
        self.translator_factory.assert_not_called()

    def test_post_rejects_missing_and_wrong_tokens_before_backend_access(self):
        for path in POST_PATHS:
            for token in (None, '', 'incorrect-token'):
                with self.subTest(path=path, token=token):
                    status, _, _ = self.request('POST', path, headers={'X-Editor-Token': token})
                    self.assertEqual(status, 403)
                    self.assert_no_backend_calls()

    def test_post_rejects_cross_origin_requests_with_a_valid_token(self):
        for path in POST_PATHS:
            for origin in ('https://untrusted.example', 'null', f'http://127.0.0.1:{self.port + 1}'):
                with self.subTest(path=path, origin=origin):
                    status, _, _ = self.request('POST', path, headers={'Origin': origin})
                    self.assertEqual(status, 403)
                    self.assert_no_backend_calls()

    def test_all_publishing_routes_reject_an_unexpected_host(self):
        routes = [('GET', '/api/publish/status'), *(('POST', path) for path in POST_PATHS)]
        for method, path in routes:
            for host in ('untrusted.example', f'127.0.0.1:{self.port + 1}'):
                with self.subTest(method=method, path=path, host=host):
                    status, _, _ = self.request(method, path, headers={'Host': host})
                    self.assertEqual(status, 403)
                    self.assert_no_backend_calls()

    def test_prepare_and_confirm_check_translation_under_the_edit_lock(self):
        events = []

        def ready():
            self.assertTrue(self.lock.locked())
            events.append('translation-ready')

        def prepare():
            self.assertTrue(self.lock.locked())
            events.append('prepare')
            return {'phase': 'preparing'}

        def publish(identifier):
            self.assertTrue(self.lock.locked())
            events.append(('publish', identifier))
            return {'phase': 'publishing'}

        self.translator.assert_publish_ready.side_effect = ready
        self.publisher.start_prepare.side_effect = prepare
        self.publisher.start_publish.side_effect = publish
        status, _, data = self.request('POST', '/api/publish/prepare')
        self.assertEqual((status, data['phase']), (202, 'preparing'))
        status, _, data = self.request('POST', '/api/publish/confirm', body='{"preparationId":"checked-snapshot"}')
        self.assertEqual((status, data['phase']), (202, 'publishing'))
        self.assertEqual(events, ['translation-ready', 'prepare', 'translation-ready', ('publish', 'checked-snapshot')])
        self.assertFalse(self.lock.locked())

    def test_pending_translation_blocks_both_actions_without_starting_publisher(self):
        self.translator.assert_publish_ready.side_effect = ValueError('Finish the Bengali updates before publishing.')
        for path in POST_PATHS:
            with self.subTest(path=path):
                status, _, data = self.request('POST', path)
                self.assertEqual(status, 400)
                self.assertIn('Bengali', data['error'])
                self.publisher_factory.assert_not_called()
                self.assertFalse(self.lock.locked())
        self.assertEqual(list(self.root.iterdir()), [])

    def test_invalid_payloads_do_not_reach_translation_or_publisher(self):
        for path in POST_PATHS:
            for body in ('', '{invalid', '[]', 'null', '"text"'):
                with self.subTest(path=path, body=body):
                    status, _, _ = self.request('POST', path, body=body)
                    self.assertEqual(status, 400)
                    self.assert_no_backend_calls()
            status, _, _ = self.request('POST', path, headers={'Content-Length': str(24 * 1024 * 1024 + 1)})
            self.assertEqual(status, 400)
            self.assert_no_backend_calls()

    def test_backend_failures_release_the_lock_and_do_not_expose_internal_details(self):
        self.publisher.start_prepare.side_effect = RuntimeError('synthetic-private-internal-detail')
        with patch.object(editor.sys, 'stderr', io.StringIO()):
            status, _, data = self.request('POST', '/api/publish/prepare')
        self.assertEqual(status, 500)
        self.assertNotIn('synthetic-private-internal-detail', json.dumps(data))
        self.assertFalse(self.lock.locked())
        self.assertEqual(list(self.root.iterdir()), [])

    def test_rotated_server_token_rejects_old_tab_until_it_reconnects(self):
        with patch.object(editor, 'TOKEN', 'new-isolated-session-token'):
            for path in POST_PATHS:
                status, _, _ = self.request('POST', path)
                self.assertEqual(status, 403)
                self.assert_no_backend_calls()
            status, _, data = self.request('GET', '/api/publish/status',
                                           headers={'X-Editor-Token': 'new-isolated-session-token'})
            self.assertEqual((status, data['phase']), (200, 'idle'))


if __name__ == '__main__':
    unittest.main()
