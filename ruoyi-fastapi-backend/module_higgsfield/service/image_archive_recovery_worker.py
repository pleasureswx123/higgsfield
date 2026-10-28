"""从已认证的响应证据恢复失败图片，不请求供应商、不修改原始用量。"""

import asyncio

from module_higgsfield.dao.generated_output_dao import GeneratedOutputDao
from module_higgsfield.dao.job_lease_dao import JobLeaseDao
from module_higgsfield.dao.provider_response_dao import ProviderResponseDao
from module_higgsfield.service.image_response_service import ImageResponseService
from module_higgsfield.service.output_archive_service import OutputArchiveService
from module_higgsfield.service.output_archive_worker import OutputArchiveWorker


class ImageArchiveRecoveryWorker(OutputArchiveWorker):
    def __init__(
        self, sessions, worker, evidence_storage, image_storage, *, max_decoded_bytes, batch_size=4, lease_seconds=60
    ):
        super().__init__(sessions, worker, None, None, batch_size=batch_size, lease_seconds=lease_seconds)
        if type(max_decoded_bytes) is not int or max_decoded_bytes <= 0:
            raise ValueError('图片恢复解码上限必须为正整数')
        self.evidence_storage, self.image_storage = evidence_storage, image_storage
        self.max_decoded_bytes = max_decoded_bytes

    async def download_and_register(self, identity, revision):
        async with self.sessions() as db:
            output = await GeneratedOutputDao.get(db, identity)
            if output is None or output.revision != revision or output.archive_state != '1' or output.kind != 'image':
                raise ValueError('图片归档占用已变化')
            evidence = await ProviderResponseDao.for_completed_image(db, output.job_id)
            if evidence is None:
                raise ValueError('图片缺少已认证的响应证据')
            output_count = len(await GeneratedOutputDao.for_job(db, output.job_id))
            file_facts = {key: getattr(evidence, key) for key in ('storage_key', 'sha256', 'byte_size')}
            call_id, job_id, ordinal, status = (
                evidence.provider_call_id,
                output.job_id,
                output.ordinal,
                evidence.http_status,
            )
        body = await self.evidence_storage.load(file_facts, call_id, job_id)
        # 以原批次登记数量核对响应；请求级用量仍保留在原调用事实中。
        fact = ImageResponseService.parse(status, body, max_bytes=self.max_decoded_bytes, expected_count=output_count)
        image = next((item for item in fact.images if item.ordinal == ordinal), None)
        if image is None:
            raise ValueError('证据中没有可解码的目标图片')
        stored = await self.image_storage.persist(
            image, declared_format=fact.declared_format, declared_size=fact.declared_size
        )
        async with self.sessions() as db:
            return await OutputArchiveService.register_download(
                db,
                identity,
                revision=revision,
                worker=self.worker,
                facts=stored,
            )

    async def run_once(self):
        async with self.sessions() as db:
            candidates = await ProviderResponseDao.recovery_candidates(db, await JobLeaseDao.now(db), self.batch_size)
        return await asyncio.gather(*(self.process(identity, revision) for identity, revision in candidates))
