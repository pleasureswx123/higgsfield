"""固定白名单的素材及作品引用核验；包括逻辑删除后的历史记录。"""

from sqlalchemy import text


class RecoveryReferenceDao:
    RULES = {
        'derivative_source_missing': "SELECT d.derivative_id AS id FROM hf_media_derivative d WHERE NOT EXISTS (SELECT 1 FROM hf_stored_file f WHERE f.file_id=d.source_file_id)",
        'derivative_source_unavailable': "SELECT d.derivative_id AS id FROM hf_media_derivative d JOIN hf_stored_file f ON f.file_id=d.source_file_id WHERE f.state<>'1'",
        'derivative_file_missing': "SELECT d.derivative_id AS id FROM hf_media_derivative d WHERE d.derived_file_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM hf_stored_file f WHERE f.file_id=d.derived_file_id)",
        'derivative_file_unavailable': "SELECT d.derivative_id AS id FROM hf_media_derivative d JOIN hf_stored_file f ON f.file_id=d.derived_file_id WHERE f.state<>'1'",
        'derivative_thumbnail_metadata_invalid': "SELECT d.derivative_id AS id FROM hf_media_derivative d JOIN hf_stored_file f ON f.file_id=d.derived_file_id WHERE d.recipe='image-thumbnail-v1' AND (f.mime_type<>'image/webp' OR f.width IS NULL OR f.height IS NULL OR f.width NOT BETWEEN 1 AND 512 OR f.height NOT BETWEEN 1 AND 512 OR f.byte_size NOT BETWEEN 1 AND 2097152 OR f.seconds IS NOT NULL)",
        'asset_current_version_invalid': "SELECT a.asset_id AS id FROM hf_asset a WHERE a.current_version_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM hf_asset_version v WHERE v.version_id=a.current_version_id AND v.asset_id=a.asset_id)",
        'asset_version_owner_missing': "SELECT v.version_id AS id FROM hf_asset_version v WHERE NOT EXISTS (SELECT 1 FROM hf_asset a WHERE a.asset_id=v.asset_id)",
        'asset_version_file_missing': "SELECT v.version_id AS id FROM hf_asset_version v WHERE NOT EXISTS (SELECT 1 FROM hf_stored_file f WHERE f.file_id=v.file_id)",
        'asset_version_file_unavailable': "SELECT v.version_id AS id FROM hf_asset_version v JOIN hf_stored_file f ON f.file_id=v.file_id WHERE f.state<>'1'",
        'asset_version_source_missing': "SELECT v.version_id AS id FROM hf_asset_version v WHERE v.source_asset_version_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM hf_asset_version s WHERE s.version_id=v.source_asset_version_id)",
        'asset_version_output_missing': "SELECT v.version_id AS id FROM hf_asset_version v WHERE v.source_output_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM hf_generated_output o WHERE o.output_id=v.source_output_id)",
        'output_job_missing': "SELECT o.output_id AS id FROM hf_generated_output o WHERE NOT EXISTS (SELECT 1 FROM hf_creation_job j WHERE j.job_id=o.job_id)",
        'output_file_missing': "SELECT o.output_id AS id FROM hf_generated_output o WHERE o.file_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM hf_stored_file f WHERE f.file_id=o.file_id)",
        'output_file_unavailable': "SELECT o.output_id AS id FROM hf_generated_output o JOIN hf_stored_file f ON f.file_id=o.file_id WHERE f.state<>'1'",
        'element_current_revision_invalid': "SELECT e.element_id AS id FROM hf_element e WHERE e.current_revision_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM hf_element_revision r WHERE r.revision_id=e.current_revision_id AND r.element_id=e.element_id)",
        'element_revision_owner_missing': "SELECT r.revision_id AS id FROM hf_element_revision r WHERE NOT EXISTS (SELECT 1 FROM hf_element e WHERE e.element_id=r.element_id)",
        'element_media_revision_missing': "SELECT m.media_id AS id FROM hf_element_revision_media m WHERE NOT EXISTS (SELECT 1 FROM hf_element_revision r WHERE r.revision_id=m.element_revision_id)",
        'element_media_asset_version_missing': "SELECT m.media_id AS id FROM hf_element_revision_media m WHERE NOT EXISTS (SELECT 1 FROM hf_asset_version v WHERE v.version_id=m.asset_version_id)",
        'element_label_revision_missing': "SELECT l.label_id AS id FROM hf_element_revision_label l WHERE NOT EXISTS (SELECT 1 FROM hf_element_revision r WHERE r.revision_id=l.element_revision_id)",
        'element_media_primary_invalid': "SELECT m.element_revision_id AS id FROM hf_element_revision_media m GROUP BY m.element_revision_id HAVING count(*) FILTER (WHERE m.is_primary='Y')<>1",
        'element_media_space_mismatch': "SELECT m.media_id AS id FROM hf_element_revision_media m JOIN hf_element_revision r ON r.revision_id=m.element_revision_id JOIN hf_element e ON e.element_id=r.element_id JOIN hf_asset_version v ON v.version_id=m.asset_version_id JOIN hf_asset a ON a.asset_id=v.asset_id WHERE a.space_id<>e.space_id",
    }

    @classmethod
    async def check(cls, db, rule, limit):
        query = cls.RULES[rule]
        count = await db.scalar(text(f'SELECT count(*) FROM ({query}) AS invalid'))
        ids = []
        if count and limit:
            ids = list(await db.scalars(text(f'{query} ORDER BY id LIMIT :limit'), {'limit': limit}))
        return count, ids
