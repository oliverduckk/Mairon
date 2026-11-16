"""SEC-02 actual service-adapter requests, recorded offline with synthetic data."""
import copy
import atexit
import json
import os
from contextlib import ExitStack
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest import mock

_fixture = tempfile.TemporaryDirectory(prefix='mairon-sec02-')
_fixture_path = Path(_fixture.name).resolve()
atexit.register(_fixture.cleanup)
tempfile.tempdir = str(_fixture_path)
sys.dont_write_bytecode = True
# Standalone Windows runs must also use synthetic configuration and stores.
os.environ.clear()
os.environ.update({'SYSTEMROOT': r'C:\Windows', 'WINDIR': r'C:\Windows',
    'TEMP': str(_fixture_path), 'TMP': str(_fixture_path),
    'MAIRON_PROJECT_ROOT': str(_fixture_path), 'MAIRON_BACKGROUND_RESEARCH_ENABLED': '0'})


def _offline_guard(event, values):
    if event.startswith(('socket.', 'winreg.')) or event in {'subprocess.Popen', 'os.system', 'os.startfile', 'os.startfile/2', 'os.kill'}:
        raise AssertionError('Unexpected real effect in SEC-02 recording test: ' + event)
    if event in {'open', 'sqlite3.connect'} and values and isinstance(values[0], (str, bytes, os.PathLike)):
        path = Path(os.fsdecode(values[0])).resolve()
        if path.is_relative_to(_fixture_path):
            return
        sensitive = path.name.lower() in {'.env', 'credentials.json', 'token.json', 'gmail_token.json', 'desktop_agent_secret.txt'}
        if event == 'sqlite3.connect' or sensitive or ('data' in path.parts and 'private' in path.parts):
            raise AssertionError('Nonfixture private access in SEC-02 recording test')


sys.addaudithook(_offline_guard)

ROOT = Path(__file__).resolve().parents[1]
sys.path.extend([str(ROOT/'src'), str(ROOT/'tests')])
import s1_offline_bootstrap  # noqa: F401
dotenv = types.ModuleType('dotenv')
dotenv.load_dotenv = lambda *args, **kwargs: False
sys.modules['dotenv'] = dotenv
from core.orchestrator import MaironCore
from core.authority_handoff import seal_prepared_turn
from tools.tool_admission import provider_turn, admitted_tools, internal_scope, provider_tool_scope
from tools import web_tools, weather_tools, route_tools, tool_registry
from research import public_factual_research, deep_research, final_synthesis, research_jobs, research_worker
from core import external_data_admission as admission
from core import cloud_export
from ai import ollama_provider
from ai import openai_provider

QUERY = 'penguin habitats'
PRIVATE = ('PRIVATE_HISTORY_SENTINEL_8841', 'EMAIL_BODY_SENTINEL_8842', 'LOCAL_FILE_SENTINEL_8843',
           'tool error includes my invoice number 582371', 'nested evidence: my medical appointment is Tuesday',
           'penguin habitats and the oncology appointment that we discussed earlier')


class Reply:
    status_code = 200
    def __init__(self, value): self.value = value
    def raise_for_status(self): pass
    def json(self): return copy.deepcopy(self.value)


class ExternalDataTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.calls = []
        self.search_rows = [{'title': 'Penguin habitat facts', 'url': 'https://example.com/penguins',
                             'content': 'Penguins live in Southern Hemisphere habitats.', 'score': 0.9}]
        self.geocode = {'results': [{'name': 'Sydney', 'country': 'Australia', 'admin1': 'NSW',
                                    'latitude': -33.8, 'longitude': 151.2}]}
        self.forecast = {'current': {'temperature_2m': 22, 'apparent_temperature': 21, 'precipitation': 0,
                                    'weather_code': 0, 'wind_speed_10m': 5},
                         'daily': {'time': ['2026-11-16'], 'weather_code': [0], 'temperature_2m_max': [25],
                                   'temperature_2m_min': [16], 'precipitation_probability_max': [10]}}
        self.stack.enter_context(mock.patch.object(web_tools, 'create_client', return_value=self))
        self.stack.enter_context(mock.patch.object(weather_tools.requests, 'get', side_effect=self.http_get))
        self.stack.enter_context(mock.patch.object(route_tools.requests, 'post', side_effect=self.http_post))
        self.stack.enter_context(mock.patch.object(route_tools, 'GOOGLE_MAPS_API_KEY', 'SYNTHETIC_SERVICE_KEY'))
        self.stack.enter_context(mock.patch.object(route_tools, 'LOCATION_ALIASES',
            {'home': '14 Synthetic Home Street', 'work': '25 Synthetic Work Avenue', 'train_station': 'Synthetic Station'}))
        self.stack.enter_context(mock.patch.object(route_tools, 'WORK_ROUTE_VIA_VALUES', []))

    def search(self, **payload):
        self.calls.append(('tavily.search', copy.deepcopy(payload)))
        return {'results': copy.deepcopy(self.search_rows)}

    def extract(self, **payload):
        self.calls.append(('tavily.extract', copy.deepcopy(payload)))
        return {'results': [{'url': payload['urls'], 'raw_content': 'Penguins live in diverse Southern Hemisphere habitats.'}]}

    def http_get(self, url, **kwargs):
        self.calls.append((url, copy.deepcopy(kwargs)))
        return Reply(self.geocode if url == weather_tools.GEOCODING_URL else self.forecast)

    def http_post(self, url, **kwargs):
        self.calls.append((url, copy.deepcopy(kwargs)))
        return Reply({'routes': [{'duration': '120s', 'staticDuration': '100s', 'distanceMeters': 1500}]})

    def prepared(self, text):
        return seal_prepared_turn(MaironCore().prepare_turn(text))

    def cloud_fixture(self, text):
        # Existing S1 currently declines public-source-verified Core turns on
        # cloud. Exercise the supported typed contract using the incumbent S3
        # fixture, with real current text; do not relax production S1 routing.
        from test_core_s3_cloud_export_admission import authority
        result = authority()
        result.turn.raw_text = text
        return result

    def test_01_private_fields_denied_in_every_caller_scope(self):
        count = 0
        auth = self.prepared('Search the public web for penguin habitats.')
        with provider_turn(auth):
            scopes = [internal_scope('research.public'), internal_scope('research.media'),
                      internal_scope('local.specialised'),
                      provider_tool_scope('local', auth, ['web_search', 'web_read', 'get_weather', 'get_route'])]
            for scope in scopes:
                with admitted_tools(scope):
                    for private in PRIVATE:
                        for tool, payload in (
                            ('web_search', {'query': private}),
                            ('web_read', {'url': 'https://example.com/penguins', 'focus': private}),
                            ('web_read', {'url': 'https://example.com/' + private.replace(' ', '-')}),
                            ('get_weather', {'location': private}),
                            ('get_route', {'origin': private, 'destination': 'Sydney', 'mode': 'drive'}),
                        ):
                            with self.subTest(caller=scope.caller, tool=tool, value=private):
                                result = tool_registry.execute_tool(tool, payload)
                                self.assertFalse(result['success'])
                                self.assertEqual(self.calls, [])
                                count += 1
        print('SEC02_PRIVATE_FIELDS ' + json.dumps({'cases': count, 'final_calls': len(self.calls)}))

    def test_02_search_read_exact_positive_and_injected_focus_denial(self):
        with provider_turn(self.prepared('Search the public web for penguin habitats.')):
            result = web_tools.web_search(QUERY)
            self.assertTrue(result['success'])
            self.assertTrue(admission.eligible_public_service_result('web_search', result))
            self.assertEqual(self.calls[0][1]['query'], QUERY)
            before = len(self.calls)
            for value in PRIVATE:
                self.assertFalse(web_tools.web_read('https://example.com/penguins', value)['success'])
                self.assertEqual(len(self.calls), before)
            read = web_tools.web_read('https://example.com/penguins', QUERY)
            self.assertTrue(read['success'])
            self.assertTrue(admission.eligible_public_service_result('web_read', read))
            self.assertEqual(self.calls[-1], ('tavily.extract', {'urls': 'https://example.com/penguins',
                'extract_depth': 'basic', 'format': 'markdown', 'include_images': False, 'query': QUERY, 'chunks_per_source': 3}))
            result['results'][0]['content'] = PRIVATE[0]
            self.assertFalse(admission.eligible_public_service_result('web_search', result))
        self.assertFalse(admission.eligible_public_service_result('web_read', read))
        print('SEC02_PUBLIC_SEARCH_READ {"exact_allowed_calls": 2, "injected_focus_additional_calls": 0}')

    def test_03_raw_unprepared_internal_scopes_cannot_export(self):
        with admitted_tools(internal_scope('research.public')):
            self.assertFalse(web_tools.web_search(QUERY)['success'])
            self.assertFalse(web_tools.web_read('https://example.com/')['success'])
        self.assertFalse(weather_tools.get_weather('Sydney')['success'])
        self.assertFalse(route_tools.request_route('Sydney', 'Melbourne', 'DRIVE')['success'])
        self.assertEqual(self.calls, [])

    def test_04_weather_exact_location_and_numeric_derivation(self):
        with provider_turn(self.prepared('What is the weather in Sydney today?')):
            self.assertFalse(weather_tools.get_weather(PRIVATE[4])['success'])
            self.assertEqual(self.calls, [])
            result = weather_tools.get_weather('Sydney')
            self.assertTrue(result['success'])
            self.assertEqual(len(self.calls), 2)
            self.assertEqual(self.calls[0][1]['params']['name'], 'Sydney')
            self.assertEqual(self.calls[1][1]['params']['latitude'], -33.8)
            self.assertEqual(self.calls[1][1]['params']['longitude'], 151.2)
            self.assertFalse(self.calls[0][1]['allow_redirects'])
            self.assertTrue(admission.eligible_public_service_result('get_weather', result))
        self.calls.clear()
        with provider_turn(self.prepared('What is the weather in Sydney?')):
            self.geocode['results'][0]['latitude'] = PRIVATE[0]
            self.assertFalse(weather_tools.get_weather('Sydney')['success'])
            self.assertEqual(len(self.calls), 1)  # The permitted geocode; no forecast export.

    def test_05_routes_scope_aliases_exact_roles_and_via(self):
        with provider_turn(self.prepared('Give me a driving route from home to work.')):
            for origin, destination, via in ((PRIVATE[0], '25 Synthetic Work Avenue', None),
                    ('14 Synthetic Home Street', PRIVATE[1], None),
                    ('14 Synthetic Home Street', '25 Synthetic Work Avenue', [{'address': PRIVATE[2]}])):
                result = route_tools.request_route(origin, destination, 'DRIVE', intermediates=via)
                self.assertFalse(result['success'])
                self.assertEqual(self.calls, [])
            result = route_tools.get_route('home', 'work')
            self.assertTrue(result['success'])
            body = self.calls[0][1]['json']
            self.assertEqual(body['origin'], {'address': '14 Synthetic Home Street'})
            self.assertEqual(body['destination'], {'address': '25 Synthetic Work Avenue'})
            self.assertNotIn('intermediates', body)
        self.calls.clear()
        with provider_turn(self.prepared('Give me a driving route from Sydney to Parramatta via Castle Hill.')):
            result = route_tools.get_route('Sydney', 'Parramatta', via=['Castle Hill'])
            self.assertTrue(result['success'])
            self.assertEqual(self.calls[0][1]['json']['intermediates'], [{'address': 'Castle Hill'}])
        print('SEC02_ROUTES {"denied_calls": 0, "exact_alias_route": true, "exact_via_route": true}')

    def test_06_capability_identity_expiry_replay_and_changed_turn(self):
        auth = self.prepared('Search the public web for penguin habitats.')
        payload = {'query': QUERY, 'search_depth': 'basic', 'topic': 'general', 'max_results': 5,
                   'include_answer': False, 'include_raw_content': False}
        with provider_turn(auth):
            permit = admission.admit_external('tavily.search', payload)
            with self.assertRaises(admission.ExternalDataDenied):
                admission.dispatch_external(copy.copy(permit), payload, self.search)
            with self.assertRaises(admission.ExternalDataDenied):
                admission.dispatch_external(permit, dict(payload, query=PRIVATE[0]), self.search)
            with mock.patch.object(admission.time, 'monotonic', return_value=permit.task.created + 601):
                with self.assertRaises(admission.ExternalDataDenied):
                    admission.dispatch_external(permit, payload, self.search)
            with provider_turn(auth):
                with self.assertRaises(admission.ExternalDataDenied):
                    admission.dispatch_external(permit, payload, self.search)
            self.assertEqual(self.calls, [])
            admission.dispatch_external(permit, payload, self.search)
            with self.assertRaises(admission.ExternalDataDenied):
                admission.dispatch_external(permit, payload, self.search)
        with self.assertRaises(admission.ExternalDataDenied):
            admission.dispatch_external(permit, payload, self.search)
        self.assertEqual(len(self.calls), 1)
        self.calls.clear()
        with provider_turn(auth):
            permit = admission.admit_external('tavily.search', payload)
            auth.turn.raw_text = 'An unrelated private question'
            with self.assertRaises(admission.ExternalDataDenied):
                admission.dispatch_external(permit, payload, self.search)
            self.assertEqual(self.calls, [])

    def test_07_research_uses_final_adapters_and_no_private_followup(self):
        with provider_turn(self.prepared('Search the public web for penguin habitats.')):
            result = public_factual_research.gather_public_factual_research(QUERY, max_reads=1)
            self.assertTrue(result['success'])
            self.assertEqual([name for name, _ in self.calls], ['tavily.search', 'tavily.extract'])
            before = len(self.calls)
            for private in PRIVATE:
                denied = public_factual_research.gather_public_factual_research(private, max_reads=1)
                self.assertFalse(denied['success'])
                self.assertEqual(len(self.calls), before)

    def test_08_json_encoded_secrets_and_benign_password_question(self):
        import base64
        secrets = ('{"api_key":"SYNTHETIC_SECRET_8841"}', '{"password":"SYNTHETIC_SECRET_8841"}',
                   r'{\"api_key\":\"SYNTHETIC_SECRET_8841\"}',
                   '%7B%22api_key%22%3A%22SYNTHETIC_SECRET_8841%22%7D',
                   r'{"api\u005fkey":"SYNTHETIC_SECRET_8841"}')
        for value in secrets + (base64.b64encode(secrets[0].encode()).decode(),):
            self.assertTrue(admission.contains_secret(value), value)
            with provider_turn(self.prepared('Search for ' + value)):
                self.assertFalse(web_tools.web_search(value)['success'])
        self.assertEqual(self.calls, [])
        with provider_turn(self.prepared('Search for how password hashing works.')):
            self.assertTrue(web_tools.web_search('how password hashing works')['success'])
        self.assertEqual(len(self.calls), 1)

    def test_09_research_local_endpoint_factories(self):
        constructors = []
        def client(**kwargs): constructors.append(kwargs); return object()
        for module, factory in ((deep_research, deep_research.create_research_planner_client),
                                (final_synthesis, final_synthesis.create_final_synthesis_client)):
            with mock.patch.object(module, 'Client', side_effect=client):
                for host in ('https://example.com', 'http://10.0.0.1:11434', 'http://localhost.evil:11434', 'http://0x7f.1:11434'):
                    with mock.patch.dict(os.environ, {'MAIRON_OLLAMA_HOST': host}):
                        with self.assertRaises(ValueError): factory()
                self.assertEqual(constructors, [])
                for host in ('http://localhost:11434', 'http://127.0.0.1:11434', 'http://[::1]:11434'):
                    with mock.patch.dict(os.environ, {'MAIRON_OLLAMA_HOST': host}): factory()
                    self.assertFalse(constructors[-1]['follow_redirects'])
                    self.assertFalse(constructors[-1]['trust_env'])
                constructors.clear()

    def test_10_url_rejections_at_sink_with_current_public_authority(self):
        from test_core_sec02_url_transport import PRIVATE_URLS, ACCESS_URLS
        with provider_turn(self.prepared('Read https://example.com/penguins?q=birds#habitat')):
            for url in PRIVATE_URLS + ACCESS_URLS:
                with self.subTest(url=url):
                    self.assertFalse(web_tools.web_read(url)['success'])
                    self.assertEqual(self.calls, [])
            self.assertTrue(web_tools.web_read('https://example.com/penguins?q=birds#habitat')['success'])
            self.assertEqual(self.calls[0][1]['urls'], 'https://example.com/penguins?q=birds#habitat')
        self.calls.clear()
        for url in ACCESS_URLS:
            with provider_turn(self.prepared('Search for information about ' + url)):
                self.assertFalse(web_tools.web_search('information about ' + url)['success'])
        self.assertEqual(self.calls, [])
        print('SEC02_URL_SINK ' + json.dumps({'denied_extracts': len(PRIVATE_URLS + ACCESS_URLS),
              'denied_embedded_queries': len(ACCESS_URLS), 'unauthorised_calls': 0, 'public_extracts': 1}))

    def test_11_weather_default_negation_and_canonical_payload(self):
        for text in ('Do not check the weather.', 'Explain the word weather.', 'My friend said "weather Sydney".'):
            with provider_turn(self.prepared(text)):
                admission.allow_weather_default('Sydney')
                self.assertFalse(weather_tools.get_weather('Sydney')['success'])
        self.assertEqual(self.calls, [])
        with provider_turn(self.prepared('What is the weather?')):
            admission.allow_weather_default('Sydney')
            self.assertTrue(weather_tools.get_weather('SYDNEY')['success'])
            self.assertEqual(self.calls[0][1]['params']['name'], 'Sydney')
        self.calls.clear()
        with provider_turn(self.prepared('Search for penguin habitats.')):
            self.assertTrue(web_tools.web_search('PENGUIN   HABITATS')['success'])
            self.assertEqual(self.calls[0][1]['query'], QUERY)

    def test_12_provider_specialised_and_direct_ingress(self):
        class Model:
            def __init__(self, name, fields): self.name, self.fields = name, fields
            def chat(self, **kwargs):
                function = types.SimpleNamespace(name=self.name, arguments=self.fields)
                return types.SimpleNamespace(message=types.SimpleNamespace(tool_calls=[types.SimpleNamespace(function=function)], content=''))
        self.stack.enter_context(mock.patch.object(ollama_provider, 'get_runtime_context', return_value='Synthetic runtime'))
        self.stack.enter_context(mock.patch.object(ollama_provider, 'ensure_background_research_worker_started'))
        self.stack.enter_context(mock.patch.object(ollama_provider, 'begin_interactive_turn'))
        self.stack.enter_context(mock.patch.object(ollama_provider, 'end_interactive_turn'))
        self.stack.enter_context(mock.patch.object(ollama_provider, 'finalise_weather_request', side_effect=lambda **kw: kw['weather_result']))
        self.stack.enter_context(mock.patch.object(ollama_provider, 'finalise_route_request', side_effect=lambda **kw: kw['route_result']))
        for text, name, good, bad, handler, expected in (
            ('What is the weather in Sydney?', 'get_weather', {'location': 'Sydney'}, {'location': PRIVATE[4]}, ollama_provider.handle_weather_request, 2),
            ('Give me a driving route from Sydney to Parramatta.', 'get_route', {'origin': 'Sydney', 'destination': 'Parramatta', 'mode': 'drive'},
             {'origin': 'Sydney', 'destination': PRIVATE[1], 'mode': 'drive'}, ollama_provider.handle_route_request, 1)):
            with provider_turn(self.prepared(text)), admitted_tools(internal_scope('local.specialised')):
                self.assertFalse(handler(Model(name, bad), text, [])['success'])
                self.assertEqual(self.calls, [])
                self.assertTrue(handler(Model(name, good), text, [])['success'])
                self.assertEqual(len(self.calls), expected)
            self.calls.clear()
            with admitted_tools(internal_scope('local.specialised')):
                self.assertFalse(handler(Model(name, good), text, [])['success'])
            self.assertEqual(self.calls, [])
        # Real raw provider entry, supplied typed runtime still cannot create a turn.
        text = 'What is the weather in Sydney?'
        runtime = self.prepared(text).runtime
        with mock.patch.object(ollama_provider, 'finalise_weather_request', side_effect=lambda **kw: ('Lookup declined.', [], None, None)):
            ollama_provider.get_response(Model('get_weather', {'location': 'Sydney'}), text, '', [], core_answer_contract=runtime)
        self.assertEqual(self.calls, [])
        print('SEC02_SPECIALISED {"allowed_weather_calls": 2, "allowed_route_calls": 1, "private_or_unprepared_calls": 0}')

    def test_13_route_variants_and_preferred_fallback(self):
        cases = (
            ('Give me directions to Parramatta.', 'home', 'Parramatta', 'drive', 1),
            ('Give me a route from Sydney to Parramatta by train.', 'Sydney', 'Parramatta', 'transit', 1),
            ('Give me a route from home to Parramatta by public transport.', 'home', 'Parramatta', 'park_and_ride', 2),
        )
        for text, origin, dest, mode, count in cases:
            with self.subTest(text=text), provider_turn(self.prepared(text)):
                result = route_tools.get_route(origin, dest, mode)
                self.assertTrue(result['success'], result)
                self.assertEqual(len(self.calls), count)
                if count == 2:
                    self.assertEqual(self.calls[0][1]['json']['destination'], {'address': 'Synthetic Station'})
                    self.assertEqual(self.calls[1][1]['json']['origin'], {'address': 'Synthetic Station'})
                    departure = self.calls[1][1]['json']['departureTime']
                    self.assertLess(abs((datetime.fromisoformat(departure.replace('Z', '+00:00')) - datetime.now(timezone.utc)).total_seconds()), 600)
            self.calls.clear()
        original_post = self.http_post
        def fallback_post(url, **kwargs):
            response = original_post(url, **kwargs)
            return Reply({'routes': []}) if len(self.calls) < 3 else response
        with mock.patch.object(route_tools, 'WORK_ROUTE_VIA_VALUES', ['Synthetic Waypoint']), mock.patch.object(route_tools.requests, 'post', side_effect=fallback_post):
            with provider_turn(self.prepared('Give me a driving route from home to work.')):
                self.assertTrue(route_tools.get_route('home', 'work')['success'])
                self.assertEqual(len(self.calls), 3)
                self.assertEqual(self.calls[0][1]['json']['intermediates'], [{'address': 'Synthetic Waypoint', 'via': True}])
                self.assertEqual(self.calls[1][1]['json']['intermediates'], [{'address': 'Synthetic Waypoint'}])
                self.assertNotIn('intermediates', self.calls[2][1]['json'])

    def test_14_durable_research_worker_and_revocation(self):
        request = 'Research penguin habitats in the background.'
        with tempfile.TemporaryDirectory() as directory, mock.patch.object(research_jobs, 'research_job_database_path', return_value=Path(directory)/'jobs.db'):
            research_jobs.initialise_research_job_store()
            with provider_turn(self.prepared(request)):
                job = research_jobs.create_research_job(topic=QUERY, goal=request, original_request=request,
                    metadata={'private_context': PRIVATE[4], 'sec02_public_export': {'request': PRIVATE[0]}})
            self.assertIn('sec02_public_export', job['metadata'])
            self.assertEqual(job['metadata']['sec02_public_export']['request'], request)
            job = research_jobs.claim_next_research_job(worker_id='synthetic-worker')
            result, packet = research_worker._run_public_research_pass(query=QUERY, job=job,
                research_fn=public_factual_research.gather_public_factual_research, packet_builder=lambda result: 'Synthetic public packet')
            self.assertTrue(result['success'])
            self.assertEqual([name for name, _ in self.calls], ['tavily.search', 'tavily.extract'])
            self.calls.clear()
            with admission.research_external_job(job):
                choices = admission.research_query_choices()
                self.assertTrue(choices)
                self.assertFalse(any(value in json.dumps(choices) for value in PRIVATE))
                alternate = next(value for value in choices if value != QUERY and 'official' in value)
                self.assertTrue(web_tools.web_search(alternate)['success'])
                for private in PRIVATE:
                    self.assertFalse(web_tools.web_search(private)['success'])
                self.assertEqual(len(self.calls), 1)
            self.calls.clear()
            with admission.research_external_job(job):
                payload = {'query': QUERY, 'search_depth': 'basic', 'topic': 'general', 'max_results': 5,
                           'include_answer': False, 'include_raw_content': False}
                permit = admission.admit_external('tavily.search', payload)
                research_jobs.update_research_job(job['id'], status='cancelled')
                with self.assertRaises(admission.ExternalDataDenied):
                    admission.dispatch_external(permit, payload, self.search)
            with admission.research_external_job(job):
                self.assertFalse(web_tools.web_search(QUERY)['success'])
            legacy = research_jobs.create_research_job(topic='polar habitats', goal='Research polar habitats', original_request='yes',
                metadata={'sec02_public_export': job['metadata']['sec02_public_export']})
            self.assertNotIn('sec02_public_export', legacy['metadata'])
            legacy = research_jobs.claim_next_research_job(worker_id='synthetic-worker')
            with admission.research_external_job(legacy):
                self.assertFalse(web_tools.web_search('polar habitats')['success'])
            self.assertEqual(self.calls, [])
        print('SEC02_DURABLE_JOB {"authorised_worker_calls": 2, "authorised_task_derivation_calls": 1, "private_revoked_legacy_calls": 0}')

    def test_15_cloud_receipts_and_final_sdk_context(self):
        prompt = 'Search for penguin habitats.'
        auth = self.cloud_fixture('/cloud ' + prompt)
        grant = cloud_export.issue_cloud_export_grant(auth, prompt, purpose='explicit_cloud_request')
        initial = cloud_export.admit_cloud_initial(grant, prompt)
        with self.assertRaises(cloud_export.CloudExportDenied):
            cloud_export.admit_cloud_sdk_request(grant, prompt, initial, model=openai_provider.MODEL, registry_tools=tool_registry.CLOUD_TOOLS)
        with provider_turn(auth):
            result = web_tools.web_search(QUERY)
            self.assertTrue(result['success'])
            args = dict(tool_name='web_search', call_id='call_synthetic', response_id='resp_synthetic')
            followup = cloud_export.admit_cloud_tool_followup(grant, prompt, tool_result=result, **args)
            cloud_export.admit_cloud_sdk_request(grant, prompt, followup, model=openai_provider.MODEL, registry_tools=tool_registry.CLOUD_TOOLS)
            for forged in (dict(result), copy.deepcopy(result), dict(result, results=[{'url': 'https://example.com/', 'content': PRIVATE[0]}])):
                with self.assertRaises(cloud_export.CloudExportDenied):
                    cloud_export.admit_cloud_tool_followup(grant, prompt, tool_result=forged, **args)
            with mock.patch.object(admission.time, 'monotonic', return_value=admission.current_external_task().created + 601):
                with self.assertRaises(cloud_export.CloudExportDenied):
                    cloud_export.admit_cloud_tool_followup(grant, prompt, tool_result=result, **args)
        with self.assertRaises(cloud_export.CloudExportDenied):
            cloud_export.admit_cloud_tool_followup(grant, prompt, tool_result=result, **args)
        with self.assertRaises(cloud_export.CloudExportDenied):
            cloud_export.admit_cloud_sdk_request(grant, prompt, followup, model=openai_provider.MODEL, registry_tools=tool_registry.CLOUD_TOOLS)
        with provider_turn(auth), self.assertRaises(cloud_export.CloudExportDenied):
            cloud_export.admit_cloud_sdk_request(grant, prompt, followup, model=openai_provider.MODEL, registry_tools=tool_registry.CLOUD_TOOLS)

    def test_16_cloud_provider_real_registry_recorded_sdk(self):
        prompt = 'Search for penguin habitats.'
        for query, expected in ((QUERY, 1), (PRIVATE[4], 0)):
            cloud_calls = []
            def create(**payload):
                cloud_calls.append(copy.deepcopy(payload))
                call = types.SimpleNamespace(type='function_call', name='web_search',
                    arguments=json.dumps({'query': query, 'topic': 'general', 'time_range': 'none'}), call_id='call_synthetic')
                return types.SimpleNamespace(output=[call] if len(cloud_calls) == 1 else [], id='resp_synthetic', output_text='Synthetic answer')
            client = types.SimpleNamespace(responses=types.SimpleNamespace(create=create))
            auth = self.cloud_fixture('/cloud ' + prompt)
            grant = cloud_export.issue_cloud_export_grant(auth, prompt, purpose='explicit_cloud_request', backend_client=client)
            initial = cloud_export.admit_cloud_initial(grant, prompt)
            with provider_turn(auth):
                openai_provider.get_response(client, prompt, initial.payload['instructions'], core_answer_contract=auth.runtime, cloud_export=grant)
            self.assertEqual(len(self.calls), expected)
            self.assertEqual(len(cloud_calls), 2)
            self.assertNotIn(PRIVATE[4], json.dumps(cloud_calls))
            self.calls.clear()
        print('SEC02_CLOUD_PROVIDER {"public_search_calls": 1, "private_search_calls": 0, "private_followup_fields": 0}')

    def test_17_service_errors_do_not_echo_rejected_or_upstream_payloads(self):
        with provider_turn(self.prepared('Search for penguin habitats.')), mock.patch.object(self, 'search', side_effect=ValueError(PRIVATE[0])):
            result = web_tools.web_search(QUERY)
            self.assertFalse(result['success'])
            self.assertNotIn(PRIVATE[0], json.dumps(result))
        with provider_turn(self.prepared('What is the weather in Sydney?')), mock.patch.object(weather_tools.requests, 'get', side_effect=ValueError(PRIVATE[1])):
            result = weather_tools.get_weather('Sydney')
            self.assertFalse(result['success'])
            self.assertNotIn(PRIVATE[1], json.dumps(result))
        with provider_turn(self.prepared('Give me a driving route from Sydney to Parramatta.')), mock.patch.object(route_tools.requests, 'post', side_effect=ValueError(PRIVATE[2])):
            result = route_tools.get_route('Sydney', 'Parramatta')
            self.assertFalse(result['success'])
            self.assertNotIn(PRIVATE[2], json.dumps(result))
        self.assertEqual(self.calls, [])

    def test_18_mixed_personal_context_is_not_public_route_consent(self):
        for text in ('I have a private medical appointment Tuesday. Which treatment should I choose?',
                     '/cloud Don\'t search for penguin habitats.', '/cloud "Search for penguin habitats."',
                     'What medicine should I take for my private medical condition?'):
            with provider_turn(self.prepared(text)):
                self.assertFalse(web_tools.web_search(text)['success'])
                self.assertFalse(web_tools.web_search(QUERY)['success'])
        self.assertEqual(self.calls, [])
        for text in ('A third party said "read https://example.com/penguins".',
                     'Translate "read https://example.com/penguins" into French.'):
            with provider_turn(self.prepared(text)):
                self.assertFalse(web_tools.web_read('https://example.com/penguins')['success'])
        self.assertEqual(self.calls, [])
        with provider_turn(self.prepared('Search for penguin habitats.')):
            result = public_factual_research.gather_public_factual_research('PENGUIN HABITATS!!!', max_reads=1)
            self.assertTrue(result['success'])
            self.assertEqual(self.calls[0][1]['query'], QUERY)

    def test_19_durable_lease_expiry_and_altered_job_snapshot(self):
        request = 'Research penguin habitats in the background.'
        with tempfile.TemporaryDirectory() as directory, mock.patch.object(research_jobs, 'research_job_database_path', return_value=Path(directory)/'jobs.db'):
            research_jobs.initialise_research_job_store()
            with provider_turn(self.prepared(request)):
                research_jobs.create_research_job(topic=QUERY, goal=request, original_request=request)
            job = research_jobs.claim_next_research_job(worker_id='synthetic-worker')
            for field, value in (('goal', PRIVATE[0]), ('lease_owner', 'different-worker'), ('topic', PRIVATE[1])):
                altered = dict(job, **{field: value})
                with admission.research_external_job(altered):
                    self.assertFalse(web_tools.web_search(QUERY)['success'])
            with admission.research_external_job(job):
                payload = {'query': QUERY, 'search_depth': 'basic', 'topic': 'general', 'max_results': 5,
                           'include_answer': False, 'include_raw_content': False}
                permit = admission.admit_external('tavily.search', payload)
                with research_jobs._connect() as connection:
                    connection.execute('UPDATE research_jobs SET lease_expires_at = ? WHERE id = ?',
                        ((datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(), job['id']))
                with self.assertRaises(admission.ExternalDataDenied):
                    admission.dispatch_external(permit, payload, self.search)
            self.assertEqual(self.calls, [])

    def test_20_ordinary_public_question_and_redirect_refusal(self):
        text = 'Who is the president of France?'
        with provider_turn(self.prepared(text)):
            self.assertTrue(public_factual_research.gather_public_factual_research(text, max_reads=1)['success'])
            self.assertEqual([name for name, _ in self.calls], ['tavily.search', 'tavily.extract'])
        self.calls.clear()
        def redirect(url, **kwargs):
            self.calls.append((url, kwargs))
            response = Reply({'private': PRIVATE[0]})
            response.status_code = 307
            return response
        with provider_turn(self.prepared('What is the weather in Sydney?')), mock.patch.object(weather_tools.requests, 'get', side_effect=redirect):
            self.assertFalse(weather_tools.get_weather('Sydney')['success'])
            self.assertEqual(len(self.calls), 1)
            self.assertFalse(self.calls[0][1]['allow_redirects'])
        self.calls.clear()
        with provider_turn(self.prepared('Give me a route from Sydney to Parramatta.')), mock.patch.object(route_tools.requests, 'post', side_effect=redirect):
            self.assertFalse(route_tools.get_route('Sydney', 'Parramatta')['success'])
            self.assertEqual(len(self.calls), 1)
            self.assertFalse(self.calls[0][1]['allow_redirects'])

    def test_21_explicit_background_forms_minimise_timing_context(self):
        for text in ('While I am asleep, research penguin habitats.',
                     'Could you please do some research on penguin habitats overnight?',
                     'Look into penguin habitats in the background.'):
            with provider_turn(self.prepared(text)):
                record = admission.research_job_export_record(QUERY, text)
                self.assertIsNotNone(record)
                self.assertTrue(web_tools.web_search(text)['success'])
                self.assertEqual(self.calls[-1][1]['query'], QUERY)
        self.assertEqual(len(self.calls), 3)


if __name__ == '__main__':
    unittest.main(verbosity=2)
