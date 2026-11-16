"""SEC-02 URL and local Agent boundaries; no sockets, secret files or effects."""
import io
import json
import os
from pathlib import Path
import socket
import sys
import unittest
from unittest import mock
from urllib.error import HTTPError
from urllib.request import HTTPDefaultErrorHandler, HTTPRedirectHandler, ProxyHandler

ROOT = Path(__file__).resolve().parents[1]
sys.path.extend([str(ROOT/'src'), str(ROOT/'tests')])
import s1_offline_bootstrap  # noqa: F401
from core import desktop_agent_client as agent
from core import cloud_export
from tools.public_url_policy import public_http_url
try:
    from core.local_endpoint_policy import local_http_endpoint
except ImportError:
    local_http_endpoint = None

PRIVATE_URLS = (
    'http://0x7f.0.0.1/', 'http://0x7f.1/', 'http://0xa.0.0.1/',
    'http://0X7F.0X0.0X0.0X1/', 'http://127.1/', 'http://127.0.1/',
    'http://2130706433/', 'http://0177.0.0.1/', 'http://127.00.0.1/',
    'http://0x08080808/', 'http://010.010.010.010/',
    'http://127.0.0.1/', 'http://10.0.0.1/', 'http://169.254.169.254/',
    'http://192.168.1.1/', 'http://100.64.0.1/', 'http://224.0.0.1/',
    'http://[::1]/', 'http://[fc00::1]/', 'http://[fe80::1]/',
    'http://[::ffff:127.0.0.1]/', 'http://[::ffff:8.8.8.8]/',
    'http://localhost/', 'http://LOCALHOST./', 'http://example.com./',
    'http://127%2e0%2e0%2e1/', 'http://%30x7f.1/',
    'http://127。0.0.1/', 'http://１２７.0.0.1/',
    'http://host.internal/', 'http://127.0.0.1.nip.io/',
)
ACCESS_URLS = (
    'https://example.com/object?X-Amz-Credential=SYNTHETIC',
    'https://example.com/object?X-Amz-Signature=SYNTHETIC',
    'https://example.com/object?X-Amz-Security-Token=SYNTHETIC',
    'https://example.com/object?X-Amz-Algorithm=AWS4-HMAC-SHA256',
    'https://example.com/object?x-aMz-sIgNaTuRe=SYNTHETIC',
    'https://example.com/object?%58-Amz-%53ignature=SYNTHETIC',
    'https://example.com/object?%2558-Amz-Signature=SYNTHETIC',
    'https://example.com/object?q=page&X-Amz-Signature=a&X-Amz-Signature=b',
    'https://example.com/object?X-Goog-Signature=SYNTHETIC',
    'https://example.com/object?X-Goog-Credential=SYNTHETIC',
    'https://example.com/object?GoogleAccessId=SYNTHETIC',
    'https://example.com/object?AWSAccessKeyId=SYNTHETIC',
    'https://example.com/object?sig=SYNTHETIC',
    'https://example.com/object?sv=2023-01-01&se=2099-01-01&sp=r&sr=b',
    'https://example.com/object?SV=1&Se=2',
    'https://example.com/object?x=1;sig=SYNTHETIC',
    'https://example.com/object;token=SYNTHETIC',
    'https://example.com/object;X-Amz-Signature=SYNTHETIC',
    'https://example.com/token/SYNTHETIC',
    'https://example.com/%74oken/SYNTHETIC',
    'https://example.com/%2574oken/SYNTHETIC',
    'https://example.com/object#access_token=SYNTHETIC',
    'https://example.com/object?api%5fkey=SYNTHETIC',
    'https://example.com/object?session_id=SYNTHETIC',
    'https://example.com/object?Key-Pair-Id=SYNTHETIC&Policy=SYNTHETIC',
)
MALFORMED_URLS = (
    'file:///C:/private.txt', 'ftp://example.com/a', 'http:////example.com',
    'https://user:secret@example.com/a', 'https://example.com:0/',
    'https://example.com:65536/', 'https://example.com:/',
    ' https://example.com/', 'https://example.com/has space',
    'https://example.com\\@127.0.0.1/', 'https://example.com/%0d%0aheader',
    'https://example.com/%zz', 'https://example.com\n/',
)


class URLBoundaryTests(unittest.TestCase):
    def test_private_and_numeric_aliases_denied(self):
        for url in PRIVATE_URLS:
            with self.subTest(url=url):
                self.assertIsNone(public_http_url(url))
                self.assertIsNone(public_http_url(url, strip_query=True))
        print('SEC02_URL_PRIVATE ' + json.dumps({'cases': len(PRIVATE_URLS), 'admitted': 0}))

    def test_access_urls_denied_before_cloud_query_stripping(self):
        for url in ACCESS_URLS:
            with self.subTest(url=url):
                self.assertIsNone(public_http_url(url))
                self.assertIsNone(public_http_url(url, strip_query=True))
                with self.assertRaises(cloud_export.CloudExportDenied):
                    cloud_export._project_web_read({'success': True, 'url': url, 'content': 'Synthetic access-controlled object.'})
                with self.assertRaises(cloud_export.CloudExportDenied):
                    cloud_export._project_web_search({'success': True, 'results': [{'url': url, 'content': 'Synthetic snippet.'}]})
        print('SEC02_URL_ACCESS ' + json.dumps({'cases': len(ACCESS_URLS), 'public_projections': 0}))

    def test_malformed_and_unsupported_urls_denied(self):
        for url in (*MALFORMED_URLS, None, 42, {}, 'https://example.com/'+'a'*1800):
            with self.subTest(url=url):
                self.assertIsNone(public_http_url(url))

    def test_public_urls_canonical_and_no_dns_claim(self):
        pairs = (
            ('https://example.com/article', 'https://example.com/article'),
            ('HTTPS://EXAMPLE.COM:443/a?q=weather&page=2#forecast', 'https://example.com:443/a?q=weather&page=2#forecast'),
            ('https://docs.python.org/3/library/urllib.parse.html#url-parsing', 'https://docs.python.org/3/library/urllib.parse.html#url-parsing'),
            ('http://8.8.8.8/', 'http://8.8.8.8/'),
            ('https://[2606:4700:4700:0:0:0:0:1111]/', 'https://[2606:4700:4700::1111]/'),
            ('https://bücher.de/a', 'https://xn--bcher-kva.de/a'),
            ('https://example.com/search?q=password+education', 'https://example.com/search?q=password+education'),
            ('https://example.com/a%20b?lang=en#part2', 'https://example.com/a%20b?lang=en#part2'),
        )
        with mock.patch.object(socket, 'getaddrinfo', side_effect=AssertionError('No DNS in lexical policy')) as dns:
            for source, expected in pairs:
                with self.subTest(source=source):
                    self.assertEqual(public_http_url(source), expected)
                    projected = cloud_export._project_web_read({'success': True, 'url': source, 'content': 'Public fixture.'})
                    self.assertEqual(projected['url'], public_http_url(source, strip_query=True))
            dns.assert_not_called()
        print('SEC02_URL_PUBLIC ' + json.dumps({'cases': len(pairs), 'canonical_matches': len(pairs), 'dns_calls': 0,
              'network_layer_guarantee': 'unverified; lexical policy only'}))


class RecordingResponse:
    def __init__(self, request): self.request = request
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def read(self, size=-1):
        body = json.loads(self.request.data)
        return json.dumps({'request_id': body['request_id'], 'success': True,
                           'result': {'success': True, 'status': 'recorded'}}).encode()
    def close(self): pass


class AgentTransportTests(unittest.TestCase):
    def test_invalid_endpoints_deny_before_secret_or_transport(self):
        endpoints = (
            'http://example.com:8123', 'http://10.0.0.1:8123', 'http://192.168.0.1:8123',
            'http://0x7f.1:8123', 'http://2130706433:8123', 'http://0177.0.0.1:8123',
            'http://127.1:8123', 'http://localhost.:8123', 'http://localhost.evil.com:8123',
            'http://[::ffff:127.0.0.1]:8123', 'http://[::1%25eth0]:8123',
            'ftp://127.0.0.1:8123', 'file:///C:/agent', 'http://u:p@127.0.0.1:8123',
            'http://127.0.0.1:0', 'http://127.0.0.1:65536', 'http://127.0.0.1:',
            'http://127.0.0.1:8123/proxy', 'http://127.0.0.1:8123?q=secret',
            'http://127.0.0.1:8123#fragment', 'http://127.0.0.1:8123?',
            'http://127.0.0.1:8123#', 'http://127.0.0.1:8123\\evil',
            ' http://127.0.0.1:8123', 'http://127.0.0.1:8123\n', '', {},
        )
        calls, loads = [], []
        def transport(request, **kwargs):
            calls.append(request)
            return RecordingResponse(request)
        def secret():
            loads.append('fake-load')
            return 'SYNTHETIC_AGENT_SECRET_8841'
        with mock.patch.object(agent, 'urlopen', side_effect=transport), mock.patch.object(agent, 'load_or_create_agent_secret', side_effect=secret):
            for endpoint in endpoints:
                with self.subTest(endpoint=endpoint):
                    result = agent.call_desktop_agent('ping', base_url=endpoint)
                    self.assertFalse(result['success'])
                    self.assertEqual(calls, [])
                    self.assertEqual(loads, [])
            with mock.patch.dict(os.environ, {'MAIRON_DESKTOP_AGENT_URL': 'https://example.com'}):
                self.assertFalse(agent.call_desktop_agent('ping')['success'])
                self.assertEqual(calls, [])
                self.assertEqual(loads, [])
        print('SEC02_AGENT_DENIED ' + json.dumps({'cases': len(endpoints)+1, 'secret_loads': len(loads), 'final_requests': len(calls)}))

    @unittest.skipUnless(hasattr(agent, '_NoAgentRedirect'), 'SEC-01 baseline lacks SEC-02 transport')
    def test_local_positive_final_request_and_no_proxy(self):
        calls, handlers_seen = [], []
        class Opener:
            def open(self, request, **kwargs):
                calls.append(request)
                return RecordingResponse(request)
        def factory(*handlers):
            handlers_seen.append(handlers)
            return Opener()
        endpoints = (
            ('http://localhost:8123', 'http://127.0.0.1:8123/v1/action'),
            ('http://127.0.0.1:8123/', 'http://127.0.0.1:8123/v1/action'),
            ('http://127.0.0.2:8123', 'http://127.0.0.2:8123/v1/action'),
            ('http://[::1]:8123', 'http://[::1]:8123/v1/action'),
            ('https://[0:0:0:0:0:0:0:1]:8123', 'https://[::1]:8123/v1/action'),
        )
        with mock.patch.object(agent, 'build_opener', side_effect=factory), mock.patch.object(agent, 'load_or_create_agent_secret', return_value='SYNTHETIC_AGENT_SECRET_8841') as secret:
            for endpoint, expected in endpoints:
                result = agent.call_desktop_agent('ping', base_url=endpoint)
                self.assertTrue(result['success'])
                request = calls[-1]
                self.assertEqual(request.full_url, expected)
                self.assertEqual(request.method, 'POST')
                self.assertEqual(request.get_header('X-mairon-agent-token'), 'SYNTHETIC_AGENT_SECRET_8841')
                self.assertEqual(json.loads(request.data)['action'], 'ping')
                self.assertEqual([h.proxies for h in handlers_seen[-1] if isinstance(h, ProxyHandler)], [{}])
                self.assertEqual(len([h for h in handlers_seen[-1] if isinstance(h, agent._NoAgentRedirect)]), 1)
            self.assertEqual(secret.call_count, len(endpoints))
        print('SEC02_AGENT_ALLOWED ' + json.dumps({'cases': len(endpoints), 'one_exact_local_request_each': len(calls), 'proxy_maps': 'empty'}))

    @unittest.skipUnless(hasattr(agent, '_NoAgentRedirect'), 'SEC-01 baseline lacks SEC-02 transport')
    def test_redirect_codes_never_forward_token(self):
        total_requests = 0
        for code in (301, 302, 303, 307, 308):
            for target in ('http://example.com/collect', 'http://127.0.0.1:9999/collect',
                           '//example.com/collect', 'https://[::1]:8123/elsewhere'):
                with self.subTest(code=code, target=target):
                    calls = []
                    class Opener:
                        def __init__(self, handler):
                            self.handler = handler
                            handler.add_parent(self)
                        def open(self, request, **kwargs):
                            calls.append(request)
                            if len(calls) > 1:
                                return RecordingResponse(request)
                            method = getattr(self.handler, 'http_error_' + str(code))
                            body, headers = io.BytesIO(b''), {'location': target}
                            result = method(request, body, code, 'Found', headers)
                            if result is None:
                                # The real opener falls through to this standard
                                # error handler when redirects are refused.
                                return HTTPDefaultErrorHandler().http_error_default(request, body, code, 'Found', headers)
                            return result
                    def factory(*handlers):
                        return Opener(next(h for h in handlers if isinstance(h, HTTPRedirectHandler)))
                    with mock.patch.object(agent, 'build_opener', side_effect=factory):
                        result = agent.call_desktop_agent('ping', base_url='http://127.0.0.1:8123', secret='SYNTHETIC_AGENT_SECRET_8841')
                    self.assertFalse(result['success'])
                    self.assertEqual(result['status'], 'agent_redirect_denied')
                    self.assertEqual(len(calls), 1)
                    self.assertEqual(calls[0].full_url, 'http://127.0.0.1:8123/v1/action')
                    self.assertNotIn(target, json.dumps(result))
                    self.assertNotIn('SYNTHETIC_AGENT_SECRET', json.dumps(result))
                    total_requests += len(calls)
        print('SEC02_AGENT_REDIRECTS ' + json.dumps({'cases': 20, 'initial_local_requests': total_requests, 'forwarded_requests': 0}))

    @unittest.skipUnless(local_http_endpoint, 'SEC-01 baseline lacks local endpoint policy')
    def test_shared_loopback_policy_for_research(self):
        self.assertEqual(local_http_endpoint('http://localhost:11434'), 'http://127.0.0.1:11434')
        self.assertEqual(local_http_endpoint('http://[::1]:11434/'), 'http://[::1]:11434')
        for value in ('http://remote.example:11434', 'http://10.0.0.1:11434', 'http://0x7f.1:11434',
                      'http://127.0.0.1:11434/private', 'http://localhost:11434?token=a', None):
            self.assertIsNone(local_http_endpoint(value))


if __name__ == '__main__':
    unittest.main(verbosity=2)
