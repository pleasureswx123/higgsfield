"""对同一已归档成片顺序测试下载策略，只读业务数据，不调用生成或改写已有文件。"""

import argparse
import asyncio
from dataclasses import replace
import json
from pathlib import Path
import sys

BACKEND = Path(__file__).resolve().parents[1] / 'ruoyi-fastapi-backend'
sys.path.insert(0, str(BACKEND))

from sqlalchemy import text
from config.database import DataSourceRegistry
from module_higgsfield.service.archive_worker_runtime import video_download_policy
from module_higgsfield.service.output_download_service import OutputDownloadService
from module_higgsfield.service.output_source_crypto_service import OutputSourceCryptoService
from module_higgsfield.service.storage_service import StorageService


async def run(args):
    reports = []
    try:
        async with DataSourceRegistry.session(log_sql=False) as db:
            row = (await db.execute(text('SELECT o.job_id,o.ordinal,o.kind,o.source_url_ciphertext,'
                'f.sha256,f.byte_size FROM hf_generated_output o JOIN hf_stored_file f ON f.file_id=o.file_id '
                'WHERE o.output_id=:id AND o.archive_state=\'2\''), {'id': args.output_id})).mappings().one()
        source = OutputSourceCryptoService().decrypt(row['source_url_ciphertext'], row['job_id'], row['ordinal'])
        storage = StorageService()
        for connections in args.connections:
            latest = {}
            async def progress(value):
                latest.update(value)
                print(json.dumps({'connectionsRequested': connections, **value}), flush=True)
            policy = replace(video_download_policy(), range_concurrency=connections)
            facts = None
            try:
                facts = await OutputDownloadService(storage, policy).download(source, kind=row['kind'], progress=progress)
                matches = facts['sha256'] == row['sha256'] and facts['byte_size'] == row['byte_size']
                reports.append({'outputId': args.output_id, 'connectionsRequested': connections,
                    'matchesArchivedFile': matches, 'sha256': facts['sha256'], **latest})
                if not matches:
                    raise ValueError('下载文件与已归档结果不一致')
            finally:
                if facts is not None:
                    await asyncio.to_thread(storage.remove_unbound_key, facts['storage_key'])
                Path(args.report).write_text(json.dumps(reports, ensure_ascii=False, indent=2), encoding='utf-8')
    finally:
        await DataSourceRegistry.dispose_all()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-id', type=int, required=True)
    parser.add_argument('--connections', type=int, nargs='+', choices=range(1, 5), default=[1, 4])
    parser.add_argument('--report', required=True)
    asyncio.run(run(parser.parse_args()))
