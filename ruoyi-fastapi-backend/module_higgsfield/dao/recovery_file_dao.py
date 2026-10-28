"""恢复核验只读文件清单，按主键分页避免全表装入内存。"""

from sqlalchemy import select, literal
from module_higgsfield.entity.do.asset_do import HfStoredFile
from module_higgsfield.entity.do.provider_response_do import HfProviderResponse
from module_higgsfield.entity.do.credential_test_response_do import HfCredentialTestResponse


class RecoveryFileDao:
    SOURCES = {
        'stored_file': (HfStoredFile, HfStoredFile.file_id),
        'provider_response': (HfProviderResponse, HfProviderResponse.response_evidence_id),
        'credential_test_response': (HfCredentialTestResponse, HfCredentialTestResponse.response_evidence_id),
    }

    @staticmethod
    async def page(db, after_id, limit, source='stored_file'):
        model, identity = RecoveryFileDao.SOURCES[source]
        state = model.state if source == 'stored_file' else literal('1')
        call = literal(None) if source == 'stored_file' else model.provider_call_id
        context = (model.job_id if source == 'provider_response' else
                   model.test_id if source == 'credential_test_response' else literal(None))
        result = await db.execute(
            select(identity.label('file_id'), model.storage_key, model.sha256,
                   model.byte_size, state.label('state'), call.label('call_id'), context.label('context_id'))
            .where(identity > after_id)
            .order_by(identity).limit(limit)
        )
        return [dict(row) for row in result.mappings()]
