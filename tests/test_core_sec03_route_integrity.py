"""F05: raw model schema + current Core + SEC-02 final recording route sink."""
import copy
import json
from pathlib import Path
import sys
import types
import unittest
from unittest import mock
sys.path.extend([str(Path(__file__).resolve().parents[1]/'src'), str(Path(__file__).resolve().parent)])
# Reuse the unchanged SEC-02 recording fixture, including its offline guard.
import test_core_sec02_external_data as sec02_fixture
from ai import ollama_provider
from tools import tool_registry
from tools.tool_admission import provider_turn, admitted_tools, internal_scope


class RouteIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.f = sec02_fixture.ExternalDataTests()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.f.stack.enter_context(mock.patch.object(ollama_provider, 'get_runtime_context', return_value='Synthetic runtime'))
        self.f.stack.enter_context(mock.patch.object(ollama_provider, 'finalise_route_request', side_effect=lambda **kw: kw['route_result']))
        self.text = 'Give me a driving route from home to Parramatta.'
        self.valid = {'origin': 'home', 'destination': 'Parramatta', 'mode': 'drive'}

    def call(self, raw, *, text=None, extra=False):
        calls = [types.SimpleNamespace(function=types.SimpleNamespace(name='get_route', arguments=raw))]
        if extra:
            calls.append(types.SimpleNamespace(function=types.SimpleNamespace(name='delete_memory', arguments={'query':'injected'})))
        client = types.SimpleNamespace(chat=lambda **kw: types.SimpleNamespace(message=types.SimpleNamespace(tool_calls=calls)))
        return ollama_provider.handle_route_request(client, text or self.text, [])

    def test_invalid_original_proposals_never_reach_final_transport(self):
        cases = [None, '', '{', '[]', [], 0, {}, {'destination':'Parramatta'},
                 dict(self.valid, unexpected='SYNTHETIC'), dict(self.valid, via=[{'not':'a string'}]),
                 dict(self.valid, via=[['Castle Hill']]), dict(self.valid, via='Castle Hill'),
                 dict(self.valid, mode=1), dict(self.valid, mode='fly'), dict(self.valid, origin=''),
                 dict(self.valid, via=[' ']),
                 '{"origin":"foreign","origin":"home","destination":"Parramatta","mode":"drive"}']
        for raw in cases:
            with self.subTest(raw=raw), provider_turn(self.f.prepared(self.text)), admitted_tools(internal_scope('local.specialised')):
                self.assertFalse(self.call(raw)['success'])
                self.assertEqual(self.f.calls, [])
        print('SEC03_F05_DENIED '+json.dumps({'raw_proposals':len(cases),'final_route_calls':len(self.f.calls)}))

    def test_valid_via_json_and_dictionary_exact_effects(self):
        for encode in (lambda value:value, json.dumps):
            text='Give me a driving route from Sydney to Parramatta via Castle Hill.'
            payload={'origin':'Sydney','destination':'Parramatta','mode':'drive','via':['Castle Hill']}
            with provider_turn(self.f.prepared(text)), admitted_tools(internal_scope('local.specialised')):
                self.assertTrue(self.call(encode(payload),text=text)['success'])
            body=self.f.calls[-1][1]['json']
            self.assertEqual(body['origin'],{'address':'Sydney'})
            self.assertEqual(body['destination'],{'address':'Parramatta'})
            self.assertEqual(body['intermediates'],[{'address':'Castle Hill'}])
        self.assertEqual(len(self.f.calls),2)

    def test_scope_context_and_compound_tool_output_are_not_authority(self):
        with admitted_tools(internal_scope('local.specialised')):
            self.assertFalse(self.call(self.valid)['success'])
        with provider_turn(self.f.prepared(self.text)), admitted_tools(internal_scope('local.specialised')):
            self.assertFalse(self.call(self.valid,extra=True)['success'])
            self.assertFalse(self.call(self.valid,text='Give me a route from home to Sydney.')['success'])
        self.assertEqual(self.f.calls,[])

    def test_schema_valid_private_field_still_denied_by_sec02(self):
        with provider_turn(self.f.prepared(self.text)), admitted_tools(internal_scope('local.specialised')):
            self.assertFalse(self.call(dict(self.valid,destination='PRIVATE_DESTINATION_SENTINEL'))['success'])
        self.assertEqual(self.f.calls,[])

    def test_direct_known_core_route_and_park_ride_are_preserved(self):
        text='How long will it take to drive from home to work?'
        with provider_turn(self.f.prepared(text)), admitted_tools(internal_scope('local.specialised')):
            self.assertTrue(self.call(None,text=text)['success'])
        self.assertEqual(len(self.f.calls),1)
        self.assertEqual(self.f.calls[0][1]['json']['destination'],{'address':'25 Synthetic Work Avenue'})
        self.f.calls.clear()
        text='Give me a route from home to Parramatta by public transport.'
        with provider_turn(self.f.prepared(text)), admitted_tools(internal_scope('local.specialised')):
            self.assertTrue(self.call(dict(self.valid,mode='park_and_ride'),text=text)['success'])
        self.assertEqual(len(self.f.calls),2)
        self.assertEqual([call[1]['json']['travelMode'] for call in self.f.calls],['DRIVE','TRANSIT'])

    def test_validation_does_not_mutate_original_proposal(self):
        value=dict(self.valid,via=['Castle Hill'])
        original=copy.deepcopy(value)
        with admitted_tools(internal_scope('local.specialised')):
            parsed,error=tool_registry.validate_tool_arguments('get_route',value,model_origin=True)
        self.assertIsNone(error)
        self.assertEqual(value,original)
        self.assertEqual(parsed,original)


if __name__=='__main__':
    unittest.main(verbosity=2)
