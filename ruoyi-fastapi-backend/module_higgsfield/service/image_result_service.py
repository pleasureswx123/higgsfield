"""同步图片结果登记：文件、输出、用量证据和完成事件一次提交。"""

from dataclasses import replace

from module_higgsfield.dao.asset_dao import AssetDao
from module_higgsfield.dao.generated_output_dao import GeneratedOutputDao
from module_higgsfield.dao.job_event_dao import JobEventDao
from module_higgsfield.dao.provider_call_dao import ProviderCallDao
from module_higgsfield.dao.provider_response_dao import ProviderResponseDao
from module_higgsfield.entity.do.asset_do import HfStoredFile
from module_higgsfield.entity.vo.archive_file_vo import ArchiveFileFacts
from module_higgsfield.entity.vo.image_provider_fact_vo import ImageProviderFact
from module_higgsfield.service.job_lease_service import JobLeaseService
from module_higgsfield.service.project_workspace_service import WorkspaceService
from module_higgsfield.service.usage_record_service import UsageRecordService
from module_higgsfield.service.usage_normalization_service import UsageNormalizationService


class ImageResultService:
    @staticmethod
    async def record(
        db,
        lease,
        call_id,
        fact: ImageProviderFact,
        stored: dict[int, dict],
        *,
        http_status=200,
        recovery_evidence_id=None,
    ):
        """stored只接受已经真实校验并落盘的事实；失败图片保留原序号，不重新生成。"""
        images = {image.ordinal: image for image in fact.images}
        ordinals = set(images) | set(fact.rejected_ordinals)
        if (
            not ordinals
            or len(ordinals) > 10
            or len(images) != len(fact.images)
            or len(set(fact.rejected_ordinals)) != len(fact.rejected_ordinals)
            or ordinals != set(range(len(ordinals)))
            or set(images) & set(fact.rejected_ordinals)
            or not set(stored) <= set(images)
            or any(type(index) is not int or index < 0 for index in ordinals)
            or not 200 <= http_status < 300
        ):
            raise ValueError('图片结果序号、文件集合或响应状态无效')
        files = {index: ArchiveFileFacts.model_validate(values) for index, values in stored.items()}
        if any(not file.mime_type.startswith('image/') for file in files.values()):
            raise ValueError('图片结果不能绑定其他媒体类型')
        try:
            job, now = await JobLeaseService.guard(db, lease)
            call = await ProviderCallDao.locked(db, call_id)
            if (
                job.kind != 'image'
                or call is None
                or call.job_id != job.job_id
                or call.credential_version_id != job.credential_version_id
                or call.operation != 'image'
            ):
                WorkspaceService.conflict('PROVIDER_RESPONSE_STALE', '图片响应不属于当前发送意图')
            if recovery_evidence_id is None:
                if (
                    job.orchestration_state != '2'
                    or call.state != '1'
                    or call.request_metadata.get('fencingToken') != str(lease.fencing_token)
                ):
                    WorkspaceService.conflict('PROVIDER_RESPONSE_STALE', '图片响应发送版本已失效')
            else:
                evidence = await ProviderResponseDao.for_call(db, call_id)
                if (
                    type(recovery_evidence_id) is not int
                    or evidence is None
                    or evidence.response_evidence_id != recovery_evidence_id
                    or evidence.job_id != job.job_id
                    or evidence.http_status != http_status
                    or job.orchestration_state != '3'
                    or call.state != '3'
                ):
                    WorkspaceService.conflict('RESPONSE_EVIDENCE_INVALID', '无法使用该响应证据恢复当前未知任务')
            job, now = await JobLeaseService.guard(db, lease)
            if await GeneratedOutputDao.for_job(db, job.job_id):
                WorkspaceService.conflict('OUTPUT_IDENTITY_CONFLICT', '当前图片任务已登记输出，不能覆盖')
            audit = dict(create_by=lease.worker, update_by=lease.worker, create_time=now, update_time=now)
            for ordinal in sorted(ordinals):
                file = None
                metadata = {}
                if ordinal in files:
                    values = files[ordinal].model_dump()
                    file = await AssetDao.add(db, HfStoredFile, **values, state='1', **audit)
                    metadata.update(
                        width=values['width'], height=values['height'], format=values['mime_type'].split('/')[1]
                    )
                image = images.get(ordinal)
                if image is not None and image.revised_prompt is not None:
                    metadata['revisedPrompt'] = image.revised_prompt
                output = await GeneratedOutputDao.add(
                    db,
                    dict(
                        job_id=job.job_id,
                        ordinal=ordinal,
                        kind='image',
                        archive_state='2' if file else '3',
                        file_id=file.file_id if file else None,
                        actual_metadata=metadata,
                        **audit,
                    ),
                )
                job.event_sequence += 1
                await JobEventDao.output(db, job, output, now, lease.worker)
            call.state, call.acceptance = '2', 'accepted'
            call.http_status, call.response_id = http_status, fact.response_id
            call.response_metadata = {
                'mode': 'synchronous_image',
                'outputCount': len(ordinals),
                'usage': dict(fact.usage),
                'issues': list(fact.issues),
                'unarchivedOrdinals': sorted(ordinals - set(files)),
                'declaredFormat': fact.declared_format,
                'declaredSize': fact.declared_size,
            }
            call.finished_time, call.update_time, call.update_by = now, now, lease.worker
            if fact.usage_fact is not None:
                call.response_metadata = call.response_metadata | {'usageEvidence': fact.usage_fact.model_dump()}
            if recovery_evidence_id is not None:
                call.response_metadata = call.response_metadata | {'recoveredEvidenceId': str(recovery_evidence_id)}
            # 与任务完成同事务追加用量；缺少规范化证据时保留未知，不采用外层零值。
            await UsageRecordService.append(
                db,
                job,
                call,
                fact.usage_fact or UsageNormalizationService.image(None),
                now=now,
                worker=lease.worker,
            )
            job.upstream_response_id = fact.response_id
            job.orchestration_state, job.upstream_state = '5', '3'
            job.finished_time, job.next_action_time = now, None
            job.lease_owner, job.lease_until = None, None
            job.revision += 1
            job.event_sequence += 1
            job.update_time, job.update_by = now, lease.worker
            await JobEventDao.state(db, job, now, lease.worker)
            result = replace(lease, revision=job.revision)
            await db.commit()
            return result
        except Exception:
            await db.rollback()
            raise
