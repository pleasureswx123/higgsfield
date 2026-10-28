"""复制草稿的来源关联、权限边界和提交一致性。"""

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from exceptions.exception import ServiceWarning
from module_higgsfield.entity.vo.draft_vo import DraftCreate
from module_higgsfield.entity.vo.generation_input_vo import GenerationInput
from module_higgsfield.service.draft_service import DraftService
from module_higgsfield.service.generation_input_service import GenerationInputService


class DraftSourceTests(unittest.IsolatedAsyncioTestCase):
    async def test_source_must_exist_in_same_project(self):
        payload = DraftCreate(projectId='7', kind='image', body={
            'prompt': {'content': []}, 'sourceJobId': '9007199254740993',
        })
        for source in (None, SimpleNamespace(project_id=8, actor_id=3)):
            with self.subTest(source=source), patch(
                'module_higgsfield.service.draft_service.GenerationReadDao.job', AsyncMock(return_value=source)
            ), patch('module_higgsfield.service.draft_service.WorkspaceService.authorize', AsyncMock()) as authorize:
                with self.assertRaises(ServiceWarning):
                    await DraftService.validate(None, None, 7, payload, 'image')
                authorize.assert_not_awaited()

    async def test_source_read_permission_is_checked_before_other_inputs(self):
        payload = DraftCreate(projectId='7', kind='image', body={
            'prompt': {'content': []}, 'sourceJobId': '9007199254740993',
        })
        with patch('module_higgsfield.service.draft_service.GenerationReadDao.job', AsyncMock(
            return_value=SimpleNamespace(project_id=7, actor_id=3)
        )) as job, patch('module_higgsfield.service.draft_service.WorkspaceService.authorize', AsyncMock(
            side_effect=ServiceWarning(message='测试拒绝读取')
        )) as authorize:
            with self.assertRaises(ServiceWarning):
                await DraftService.validate('db', 'user', 7, payload, 'image')
            job.assert_awaited_once_with('db', 9007199254740993)
            authorize.assert_awaited_once_with('db', 'user', 7, 'generation:read', owner_id=3)

    async def test_submission_cannot_detach_saved_source(self):
        payload = GenerationInput(projectId='7', kind='image', modelVersionId='9',
                                  prompt={'content': []}, parameters={}, references=[], draftId='11', draftRevision='1')
        body = payload.model_dump(by_alias=True, include={'prompt', 'parameters', 'model_version_id', 'folder_id'})
        body['sourceJobId'] = '9007199254740993'
        draft = SimpleNamespace(owner_id=2, project_id=7, draft_id=11, revision=1, kind='image', body=body)
        with patch('module_higgsfield.service.generation_input_service.WorkspaceService.authorize', AsyncMock()), patch(
            'module_higgsfield.service.generation_input_service.DraftDao.get', AsyncMock(return_value=draft)
        ), patch('module_higgsfield.service.generation_input_service.DraftDao.references', AsyncMock(return_value=[])):
            with self.assertRaises(ServiceWarning) as result:
                await GenerationInputService.prepare(None, SimpleNamespace(user=SimpleNamespace(user_id=2)), payload)
            self.assertIn('草稿修订不一致', result.exception.message)


    async def test_unbound_draft_keeps_parameters_without_skipping_reference_checks(self):
        payload = DraftCreate(projectId='7', kind='video', body={
            'prompt': {'content': []}, 'parameters': {'duration': 30, 'generate_audio': False},
        })
        with patch('module_higgsfield.service.draft_service.FolderDao.space', AsyncMock(return_value=SimpleNamespace(space_id=1))), patch(
            'module_higgsfield.service.draft_service.FolderService.check_target', AsyncMock()
        ) as folder, patch('module_higgsfield.service.draft_service.ReferenceCompileService.resolve', AsyncMock()) as references, patch(
            'module_higgsfield.service.draft_service.ModelCatalogService.selected', AsyncMock()
        ) as selected:
            await DraftService.validate(None, None, 7, payload, 'video')
            selected.assert_not_awaited()
            folder.assert_awaited_once()
            references.assert_awaited_once()
            self.assertEqual(payload.body.parameters, {'duration': 30, 'generate_audio': False})
