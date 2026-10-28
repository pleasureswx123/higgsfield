"""未知图片提交仅依据已保存的认证响应恢复，不重发任何供应商请求。"""

from exceptions.exception import ServiceWarning
from module_higgsfield.dao.provider_call_dao import ProviderCallDao
from module_higgsfield.dao.provider_response_dao import ProviderResponseDao
from module_higgsfield.service.generation_worker_service import JobExecutionContext
from module_higgsfield.service.image_response_service import ImageResponseService
from module_higgsfield.service.job_lease_service import JobLeaseService


class ImageReconciliationHandler:
    def __init__(self, evidence_storage, image_storage, *, max_decoded_bytes):
        self.evidence_storage, self.image_storage = evidence_storage, image_storage
        self.max_decoded_bytes = max_decoded_bytes

    async def __call__(self, context: JobExecutionContext) -> None:
        saved = None
        async with context.sessions() as db:
            job, _ = await JobLeaseService.guard(db, context.lease)
            if job.kind != 'image' or job.orchestration_state != '3':
                raise ValueError('当前任务不是未知图片提交')
            call = await ProviderCallDao.submission(db, job.job_id)
            evidence = await ProviderResponseDao.for_call(db, call.call_id) if call else None
            if (
                call
                and call.state == '3'
                and call.operation == 'image'
                and evidence
                and evidence.job_id == job.job_id
                and call.credential_version_id == job.credential_version_id
            ):
                saved = {
                    'call_id': call.call_id,
                    'job_id': job.job_id,
                    'evidence_id': evidence.response_evidence_id,
                    'http_status': evidence.http_status,
                    'files': {key: getattr(evidence, key) for key in ('storage_key', 'sha256', 'byte_size')},
                    'expected_count': job.input_snapshot.get('parameters', {}).get('n', 1),
                }
        if saved is None:
            await context.defer(60)
            return
        body = await self.evidence_storage.load(saved['files'], saved['call_id'], saved['job_id'])
        try:
            fact = ImageResponseService.parse(
                saved['http_status'],
                body,
                max_bytes=self.max_decoded_bytes,
                expected_count=saved['expected_count'],
            )
        except ValueError:
            # 证据确实存在但不能证明成功时保留未知，不将其当成重新收费生成的依据。
            await context.defer(60)
            return
        stored = {}
        for image in fact.images:
            try:
                stored[image.ordinal] = await self.image_storage.persist(
                    image,
                    declared_format=fact.declared_format,
                    declared_size=fact.declared_size,
                )
            except (ValueError, OSError, ServiceWarning):
                fact.issues.append('IMAGE_ARCHIVE_FAILED')
        await context.record_images(
            saved['call_id'],
            fact,
            stored,
            http_status=saved['http_status'],
            recovery_evidence_id=saved['evidence_id'],
        )
