"""宿主机独立启动生成、归档和恢复工作器，不启动Web服务、不执行迁移。"""

import argparse
import asyncio
import json
import os
import signal
import sys
from uuid import uuid4


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='生成与结果归档工作器（运行前须配置供应商或下载出口策略）')
    parser.add_argument(
        '--mode',
        choices=('video', 'image', 'archive', 'image-recovery', 'billing', 'credential-test', 'reconciliation', 'element-import', 'image-thumbnail'),
        default='video',
        help='生成、URL归档、图片证据恢复、本地计价、凭据测试、对账或元素模板导入',
    )
    parser.add_argument('--env', default=os.environ.get('APP_ENV', 'dev'), help='若依配置环境')
    parser.add_argument('--worker-id', default='worker-' + uuid4().hex, help='执行实例安全标识')
    parser.add_argument('--once', action='store_true', help='执行一批任务后退出，可能调用收费生成接口')
    parser.add_argument(
        '--enable-consumption', action='store_true',
        help='显式启用任务消费；恢复核验期间不要设置，此选项也适用于--once和本地写入模式',
    )
    parser.add_argument('--concurrency', type=int, default=4)
    parser.add_argument('--lease-seconds', type=int, default=60)
    parser.add_argument('--handler-timeout', type=int, default=300)
    parser.add_argument('--control-dir', help='本地管理脚本专用控制目录')
    parser.add_argument('--drain-seconds', type=int, default=1200, help='停止领取后等待在途任务的最长秒数')
    parser.add_argument('--test-stale-seconds', type=int, default=600, help='测试发送意图回收窗口，须大于处理超时加60秒')
    options = parser.parse_args()
    if not 1 <= options.concurrency <= 100 or not 1 <= options.drain_seconds <= 3600:
        parser.error('并发须为1到100，停机等待须为1到3600秒')
    if not options.enable_consumption:
        parser.error('任务消费默认关闭；完成环境与恢复核验后，使用--enable-consumption显式启用')
    return options


async def run(options: argparse.Namespace) -> int:
    # 直接调用入口也必须通过开关；在导入框架配置和建立数据库连接前拒绝。
    if not getattr(options, 'enable_consumption', False):
        raise ValueError('任务消费默认关闭，必须显式启用')
    # 延迟加载框架配置，使--help无需连接数据库或配置密钥。
    from config.database import create_async_db_engine, create_async_session_factory  # noqa: PLC0415
    from config.env import DataBaseConfig  # noqa: PLC0415
    from module_higgsfield.service.video_worker_runtime import create_video_worker  # noqa: PLC0415
    from module_higgsfield.service.archive_worker_runtime import create_archive_worker  # noqa: PLC0415
    from module_higgsfield.service.image_worker_runtime import create_image_worker, create_image_recovery_worker  # noqa: PLC0415
    from module_higgsfield.service.billing_worker_service import BillingWorker  # noqa: PLC0415
    from module_higgsfield.service.credential_test_worker_runtime import create_credential_test_worker  # noqa: PLC0415
    from module_higgsfield.service.reconciliation_worker_service import ReconciliationWorker  # noqa: PLC0415
    from module_higgsfield.service.element_import_worker_service import ElementImportWorker  # noqa: PLC0415
    from module_higgsfield.service.image_thumbnail_worker import ImageThumbnailWorker  # noqa: PLC0415

    if DataBaseConfig.default_source.db_type != 'postgresql':
        raise ValueError('工作器只支持PostgreSQL')
    engine = create_async_db_engine(echo=False)
    stop = asyncio.Event()
    previous = {}
    try:
        if options.mode == 'image-thumbnail':
            worker = ImageThumbnailWorker(create_async_session_factory(engine), options.worker_id,
                batch_size=options.concurrency, lease_seconds=options.lease_seconds)
        elif options.mode == 'element-import':
            worker = ElementImportWorker(create_async_session_factory(engine),
                concurrency=options.concurrency, handler_timeout=options.handler_timeout)
        elif options.mode == 'reconciliation':
            worker = ReconciliationWorker(create_async_session_factory(engine),
                concurrency=options.concurrency, handler_timeout=options.handler_timeout)
        elif options.mode == 'credential-test':
            worker = create_credential_test_worker(create_async_session_factory(engine),
                concurrency=options.concurrency, handler_timeout=options.handler_timeout,
                stale_after_seconds=options.test_stale_seconds)
        elif options.mode == 'billing':
            worker = BillingWorker(
                create_async_session_factory(engine), options.worker_id, batch_size=options.concurrency
            )
        elif options.mode == 'archive':
            worker = create_archive_worker(
                create_async_session_factory(engine),
                options.worker_id,
                batch_size=options.concurrency,
                lease_seconds=options.lease_seconds,
            )
        elif options.mode == 'image-recovery':
            worker = create_image_recovery_worker(
                create_async_session_factory(engine),
                options.worker_id,
                batch_size=options.concurrency,
                lease_seconds=options.lease_seconds,
            )
        else:
            create = create_image_worker if options.mode == 'image' else create_video_worker
            worker = create(
                create_async_session_factory(engine),
                options.worker_id,
                concurrency=options.concurrency,
                lease_seconds=options.lease_seconds,
                handler_timeout=options.handler_timeout,
            )
        if options.once:
            results = await worker.run_once()
            print(json.dumps(results, ensure_ascii=False))
            return (
                0
                if all(item['status'] in {'handled', 'archived', 'skipped', 'source_expired'} for item in results)
                else 2
            )
        for signum in (signal.SIGINT, signal.SIGTERM):
            previous[signum] = signal.signal(signum, lambda *_: stop.set())
        from module_higgsfield.service.worker_control_service import serve_controlled
        from module_higgsfield.service.worker_wakeup_service import worker_notifications
        async with worker_notifications(engine, stop):
            await serve_controlled(worker, engine, stop,
                control_dir=options.control_dir, mode=options.mode,
                concurrency=options.concurrency, drain_seconds=options.drain_seconds)
        return 0
    finally:
        for signum, handler in previous.items():
            signal.signal(signum, handler)
        await engine.dispose()


def main() -> int:
    options = arguments()
    os.environ['APP_ENV'] = options.env
    try:
        return asyncio.run(run(options))
    except KeyboardInterrupt:
        return 130
    except Exception as error:
        # 供应商或数据库异常正文可能携带秘密，仅输出异常类型。
        print(f'工作器停止：{type(error).__name__}，请检查运行配置与任务状态。', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
