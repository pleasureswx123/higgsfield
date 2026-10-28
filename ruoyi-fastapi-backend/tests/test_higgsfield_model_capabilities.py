"""能力白名单的类型、范围、条件组合与去重后媒体数量校验。"""

import unittest
from pydantic import ValidationError
from exceptions.exception import ServiceWarning
from module_higgsfield.entity.vo.model_capability_vo import ModelCapabilities, ParameterRule
from module_higgsfield.service.model_capability_service import ModelCapabilityService


def capability():
    return ModelCapabilities.model_validate(
        {
            'parametersSchema': {
                'properties': {
                    'resolution': {'type': 'string', 'enum': ['720p', '1080p']},
                    'duration': {'type': 'integer', 'minimum': 2, 'maximum': 12},
                    'audio': {'type': 'boolean'},
                    'seed': {'type': 'integer', 'minimum': 0, 'maximum': 2147483647},
                },
                'required': ['resolution', 'duration'],
                'conditions': [{'when': {'resolution': '1080p'}, 'allowed': {'duration': [4, 8]}, 'forbid': ['seed']}],
            },
            'defaultParameters': {'resolution': '720p', 'audio': False},
            'referenceRules': {
                'maxTotal': 3,
                'roles': {
                    'first_frame': {'mediaTypes': ['image'], 'minCount': 1, 'maxCount': 1},
                    'reference_image': {'mediaTypes': ['image'], 'maxCount': 2},
                },
            },
        }
    )


class CapabilityTests(unittest.TestCase):
    def test_defaults_do_not_modify_user_or_profile(self):
        cap = capability()
        ModelCapabilityService.validate_configuration(cap)
        supplied = {'duration': 6}
        result = ModelCapabilityService.parameters(cap, supplied)
        self.assertEqual(result, {'resolution': '720p', 'audio': False, 'duration': 6})
        self.assertEqual(supplied, {'duration': 6})
        self.assertNotIn('duration', cap.default_parameters)

    def test_strict_types_ranges_and_unknown_keys(self):
        for supplied in (
            {'duration': True},
            {'duration': '6'},
            {'duration': 6.0},
            {'duration': 13},
            {'duration': 6, 'gatewayAlias': 'anything'},
            {'duration': float('nan')},
            {'duration': 6, 'audio': 1},
            {'duration': 10**400},
            {},
        ):
            with self.subTest(supplied=supplied), self.assertRaises(ServiceWarning):
                ModelCapabilityService.parameters(capability(), supplied)

    def test_combinations_and_incomplete_drafts(self):
        ModelCapabilityService.parameters(capability(), {'resolution': '1080p', 'duration': 8})
        for supplied in ({'resolution': '1080p', 'duration': 6}, {'resolution': '1080p', 'duration': 4, 'seed': 0}):
            with self.assertRaises(ServiceWarning):
                ModelCapabilityService.parameters(capability(), supplied)
        self.assertEqual(
            ModelCapabilityService.parameters(capability(), {}, require_complete=False)['resolution'], '720p'
        )

    def test_media_counts_and_roles(self):
        cap = capability()
        ModelCapabilityService.references(cap, {'media': [{'mediaRole': 'first_frame', 'mediaType': 'image'}]})
        ModelCapabilityService.references(cap, {'media': []}, require_complete=False)
        for rows in (
            [],
            [{'mediaRole': 'first_frame', 'mediaType': 'video'}],
            [{'mediaRole': 'last_frame', 'mediaType': 'image'}],
            [{'mediaRole': 'first_frame', 'mediaType': 'image'}] * 2,
            [{'mediaRole': 'reference_image', 'mediaType': 'image'}] * 4,
        ):
            with self.subTest(rows=rows), self.assertRaises(ServiceWarning):
                ModelCapabilityService.references(cap, {'media': rows})

    def test_rejects_invalid_schema_and_executable_extensions(self):
        for value in (
            {'type': 'integer', 'enum': [True]},
            {'type': 'string', 'minimum': 1},
            {'type': 'number', 'minimum': float('inf')},
            {'type': 'number', 'enum': [1, 1.0]},
            {'type': 'string', 'minLength': 3, 'maxLength': 2},
            {'type': 'number', 'expression': 'run()'},
        ):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                ParameterRule.model_validate(value)
        config = capability().model_dump(by_alias=True)
        config['parametersSchema']['additionalProperties'] = True
        with self.assertRaises(ValidationError):
            ModelCapabilities.model_validate(config)

    def test_invalid_defaults_cannot_publish(self):
        cap = capability()
        cap.default_parameters['duration'] = 999
        with self.assertRaises(ServiceWarning):
            ModelCapabilityService.validate_configuration(cap)
