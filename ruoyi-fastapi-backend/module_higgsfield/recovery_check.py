"""只读恢复核验入口；不启动Web、工作器、迁移或供应商调用。"""

import argparse
import asyncio
import json
import os
import sys


async def run(options):
    if not options.confirm_quiesced:
        raise ValueError('须先停止写入与任务消费')
    from config.database import create_async_db_engine, create_async_session_factory
    from config.env import DataBaseConfig
    from module_higgsfield.service.recovery_file_service import RecoveryFileService
    from module_higgsfield.service.recovery_sequence_service import RecoverySequenceService
    from module_higgsfield.service.recovery_reference_service import RecoveryReferenceService
    from module_higgsfield.service.recovery_credential_service import RecoveryCredentialService
    from module_higgsfield.service.recovery_evidence_service import RecoveryEvidenceService
    from module_higgsfield.service.recovery_budget_service import RecoveryBudgetService
    from module_higgsfield.service.credential_crypto_service import CredentialCryptoService
    from module_higgsfield.service.storage_service import StorageService

    if DataBaseConfig.default_source.db_type != 'postgresql':
        raise ValueError('恢复核验只支持PostgreSQL')
    engine = create_async_db_engine(echo=False)
    try:
        crypto = CredentialCryptoService()
        storage = StorageService()
        files = await RecoveryFileService.audit(
            create_async_session_factory(engine), storage,
            page_size=options.page_size, sample_limit=options.sample_limit,
        )
        sequences = await RecoverySequenceService.audit(
            create_async_session_factory(engine), sample_limit=options.sample_limit,
        )
        references = await RecoveryReferenceService.audit(
            create_async_session_factory(engine), sample_limit=options.sample_limit,
        )
        credentials = await RecoveryCredentialService.audit(
            create_async_session_factory(engine), crypto,
            page_size=options.page_size, sample_limit=options.sample_limit,
        )
        evidence = await RecoveryEvidenceService.audit(
            create_async_session_factory(engine), storage, crypto.keyring,
            page_size=options.page_size, sample_limit=options.sample_limit,
        )
        budgets = await RecoveryBudgetService.audit(
            create_async_session_factory(engine), page_size=options.page_size, sample_limit=options.sample_limit,
        )
        report = {'scope': 'recovery_integrity', 'complete': True,
                  'files': files, 'sequences': sequences, 'references': references, 'credentials': credentials,
                  'evidence': evidence, 'budgets': budgets,
                  'failed': sum(item['failed'] for item in (files, sequences, references, credentials, evidence, budgets)),
                  'fullRecoveryVerified': False}
    finally:
        await engine.dispose()
    # 所有检查与连接清理均完成后才发布报告，清理失败不能留下完成标记。
    print(json.dumps(report, ensure_ascii=False))
    return 2 if report['failed'] else 0


def main():
    parser = argparse.ArgumentParser(description='隔离恢复环境只读文件、序列、引用、凭据及预算核验，不代表完整恢复验收')
    parser.add_argument('--env', default=os.environ.get('APP_ENV', 'dev'))
    parser.add_argument('--confirm-quiesced', action='store_true', help='确认已停止写入与任务消费')
    parser.add_argument('--page-size', type=int, default=200)
    parser.add_argument('--sample-limit', type=int, default=100)
    options = parser.parse_args()
    if not 1 <= options.page_size <= 500 or not 0 <= options.sample_limit <= 1000:
        parser.error('page-size须为1至500，sample-limit须为0至1000')
    if not options.confirm_quiesced:
        parser.error('请先停止写入与任务消费，再传入--confirm-quiesced')
    os.environ['APP_ENV'] = options.env
    try:
        return asyncio.run(run(options))
    except Exception as error:
        # 不输出内部存储路径、连接串或异常正文，也不打印部分成功报告。
        print(f'恢复核验未完成：{type(error).__name__}', file=sys.stderr)
        return 3


if __name__ == '__main__':
    raise SystemExit(main())
