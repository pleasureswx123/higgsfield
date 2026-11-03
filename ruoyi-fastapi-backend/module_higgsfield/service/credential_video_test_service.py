"""视频测试持久化任务编号后轮询，进程恢复也不重复提交付费生成。"""

from datetime import datetime, timedelta

from module_higgsfield.dao.credential_test_dao import CredentialTestDao
from module_higgsfield.dao.provider_call_dao import ProviderCallDao
from module_higgsfield.dao.job_lease_dao import JobLeaseDao
from module_higgsfield.dao.credential_test_response_dao import CredentialTestResponseDao
from module_higgsfield.service.credential_test_binding_service import CredentialTestBindingService
from module_higgsfield.service.credential_test_completion_service import CredentialTestCompletionService
from module_higgsfield.service.credential_test_response_service import CredentialTestResponseService
from module_higgsfield.service.provider_http_service import ProviderHttpService
from module_higgsfield.service.videoplus_response_service import VideoPlusResponseService
from module_higgsfield.service.archive_worker_runtime import video_download_policy
from module_higgsfield.service.output_download_service import OutputDownloadService
from module_higgsfield.service.credential_test_usage_service import CredentialTestUsageService
from module_higgsfield.service.credential_test_billing_service import CredentialTestBillingService


class CredentialVideoTestService:
    @staticmethod
    async def submitted(executor, test_id, intent, response):
        fact = VideoPlusResponseService.submission(response.http_status or 0, response.body)
        if fact.acceptance == 'accepted':
            submission_evidence = await executor.evidence_storage.save(response.body, intent.call_id, test_id)
            async with executor.sessions() as db:
                test = await CredentialTestDao.locked(db, test_id)
                call = await ProviderCallDao.locked(db, intent.call_id)
                if test.state != '0' or test.provider_call_id != call.call_id:
                    return False
                call.request_metadata = {**call.request_metadata, 'videoTaskId': fact.upstream_task_id,
                                         'videoSubmissionHttpStatus': response.http_status,
                                         'videoSubmissionEvidence': submission_evidence}
                await db.commit()
            return True
        if response.transport == 'response' and response.body is not None:
            evidence = await executor.evidence_storage.save(response.body, intent.call_id, test_id)
            async with executor.sessions() as db:
                await CredentialTestResponseService.register(db, test_id, intent.call_id, evidence, http_status=response.http_status)
        diagnostic = {'transport': response.transport, 'httpStatus': response.http_status,
            'authentication': 'unknown', 'acceptance': 'unknown',
            'issue': 'RESPONSE_INVALID' if response.transport == 'response' else 'TRANSPORT_UNKNOWN'}
        if response.http_status in {401, 403}:
            diagnostic.update(authentication='failed', acceptance='rejected', issue='AUTH_REJECTED')
        async with executor.sessions() as db:
            return await CredentialTestCompletionService.finish(db, test_id, intent.call_id, diagnostic)

    @staticmethod
    async def poll(executor, test_id):
        if await CredentialVideoTestService.finish_saved(executor, test_id):
            return True
        async with executor.sessions() as db:
            test = await CredentialTestDao.locked(db, test_id)
            if test is None or test.state != '0' or test.provider_call_id is None:
                return False
            call = await ProviderCallDao.locked(db, test.provider_call_id)
            task_id = call.request_metadata.get('videoTaskId') if call else None
            if not task_id:
                return False
            now = await JobLeaseDao.now(db)
            next_poll = call.request_metadata.get('videoNextPoll')
            if next_poll and datetime.fromisoformat(next_poll) > now:
                return True
            # 使用原密钥和配置；不因模型后来发布而重新创建付费测试。
            binding = await CredentialTestBindingService.require(db, test.credential_version_id,
                test.cost_center_id, test.model_version_id)
            transport = executor.transport_factory(binding) if executor.transport_factory else ProviderHttpService.from_versions(
                binding.config, binding.version, crypto=executor.credentials)
            call_id = call.call_id
            call.request_metadata = {**call.request_metadata, 'videoNextPoll': (now + timedelta(seconds=300)).isoformat()}
            stored_video = call.response_metadata.get('testVideoFile') if call.response_metadata else None
            await db.commit()
        import time
        started = time.monotonic()
        response = await transport.poll(task_id)
        from module_higgsfield.service.credential_test_detail_service import CredentialTestDetailService
        # 只保留最近一次有界脱敏查询快照，不累积大型轮询历史。
        latest = {'httpStatus': response.http_status, 'transport': response.transport,
                  'elapsedSeconds': round(time.monotonic() - started, 3),
                  'response': CredentialTestDetailService.redact(response.body)}
        async with executor.sessions() as db:
            call = await ProviderCallDao.locked(db, call_id)
            latest['receivedAt'] = (await JobLeaseDao.now(db)).isoformat()
            call.request_metadata = {**call.request_metadata, 'videoLatestPoll': latest}
            await db.commit()
        fact = VideoPlusResponseService.polling(response.http_status or 0, response.body, expected_task_id=task_id, input_image_count=0)
        if fact.upstream_state not in {'succeeded', 'failed'}:
            async with executor.sessions() as db:
                call = await ProviderCallDao.locked(db, call_id)
                call.request_metadata = {**call.request_metadata, 'videoNextPoll': (now + timedelta(seconds=60)).isoformat()}
                await db.commit()
            return True
        evidence = await executor.evidence_storage.save(response.body, call_id, test_id)
        async with executor.sessions() as db:
            await CredentialTestResponseService.register(db, test_id, call_id, evidence, http_status=response.http_status)
        return await CredentialVideoTestService.finish_saved(executor, test_id)

    @staticmethod
    async def finish_saved(executor, test_id):
        """最终响应已保存但完成事务中断时，只重放证据，不再次查询或覆盖证据。"""
        async with executor.sessions() as db:
            test = await CredentialTestDao.get(db, test_id)
            if test is None or test.state != '0' or test.provider_call_id is None:
                return False
            call = await ProviderCallDao.get(db, test.provider_call_id)
            evidence = await CredentialTestResponseDao.get(db, test_id)
            if not call or not call.request_metadata.get('videoTaskId') or evidence is None:
                return False
            task_id, call_id, status = call.request_metadata['videoTaskId'], call.call_id, evidence.http_status
            saved = bool((call.response_metadata or {}).get('testVideoFile'))
            facts = {key: getattr(evidence, key) for key in ('storage_key', 'sha256', 'byte_size')}
        body = await executor.evidence_storage.load(facts, call_id, test_id)
        fact = VideoPlusResponseService.polling(status, body, expected_task_id=task_id, input_image_count=0)
        # 费用随真实结果入账；归档失败不能丢掉已发生的消费。
        async with executor.sessions() as db:
            test = await CredentialTestDao.locked(db, test_id)
            call = await ProviderCallDao.locked(db, call_id)
            if test.state != '0':
                return True
            now = await JobLeaseDao.now(db)
            await CredentialTestUsageService.append(db, test, call, fact.usage_fact, now=now)
            await CredentialTestBillingService.calculate(db, test, call, now=now)
            await db.commit()
        if fact.upstream_state == 'succeeded' and fact.outputs and not saved:
            downloader = OutputDownloadService(executor.storage, video_download_policy())
            try:
                stored_video = await downloader.download(fact.outputs[0].source_url.get_secret_value(), kind='video')
            except Exception as exc:
                # 只记录安全错误类别；保留生成事实，不能把归档失败误报为仍在生成。
                async with executor.sessions() as db:
                    call = await ProviderCallDao.locked(db, call_id)
                    call.request_metadata = {**call.request_metadata, 'videoArchiveIssue':
                        'DOWNLOAD_TIMEOUT' if isinstance(exc, TimeoutError) else 'ARCHIVE_RETRY_REQUIRED'}
                    await db.commit()
                raise
            # ffprobe 校验返回 Decimal 秒数；JSONB 中保留十进制字符串，避免浮点误差。
            if stored_video.get('seconds') is not None:
                stored_video = {**stored_video, 'seconds': str(stored_video['seconds'])}
            async with executor.sessions() as db:
                call = await ProviderCallDao.locked(db, call_id)
                call.response_metadata = {**(call.response_metadata or {}), 'testVideoFile': stored_video}
                await db.commit()
            saved = True
        passed = fact.upstream_state == 'succeeded' and bool(fact.outputs) and saved
        async with executor.sessions() as db:
            await CredentialTestCompletionService.finish(db, test_id, call_id, {
                'transport': 'response', 'httpStatus': status, 'authentication': 'passed', 'acceptance': 'accepted',
                'modelVerified': passed, 'outputCount': len(fact.outputs), 'issue': 'NONE' if passed else 'PROVIDER_REJECTED'},
                usage_fact=fact.usage_fact)
        return True
