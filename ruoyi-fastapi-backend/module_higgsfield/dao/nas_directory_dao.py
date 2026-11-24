"""一次查询取得同一 PostgreSQL 快照中的项目、目录、素材及独立生成结果。"""

from sqlalchemy import text


class NasDirectoryDao:
    @staticmethod
    async def database_identity(db):
        row = (await db.execute(text("SELECT current_database(), current_schema()"))).one()
        return list(row)

    @staticmethod
    async def entries(db):
        query = text("""
            WITH projects AS (
                SELECT p.project_id, p.project_name, p.create_user_id, s.space_id
                FROM hf_project p JOIN hf_asset_space s USING (project_id)
                WHERE p.del_flag='0' AND s.kind='project'
            ), entries AS (
                SELECT 'project' AS kind, p.project_id AS id, p.project_id,
                       p.create_user_id AS parent, p.project_name AS name,
                       NULL::text AS storage_key, NULL::text AS mime_type
                FROM projects p
                UNION ALL
                SELECT DISTINCT 'creator', p.create_user_id, NULL::bigint, NULL::bigint,
                       COALESCE(NULLIF(btrim(u.nick_name), ''), '用户-' || p.create_user_id), NULL, NULL
                FROM projects p LEFT JOIN sys_user u ON u.user_id=p.create_user_id
                UNION ALL
                SELECT 'folder', f.folder_id, p.project_id, f.parent_id, f.folder_name, NULL, NULL
                FROM projects p JOIN hf_folder f USING (space_id) WHERE f.del_flag='0'
                UNION ALL
                SELECT 'asset', a.asset_id, p.project_id, e.folder_id, a.asset_name, sf.storage_key, sf.mime_type
                FROM projects p JOIN hf_asset a USING (space_id)
                JOIN hf_asset_version v ON v.version_id=a.current_version_id AND v.asset_id=a.asset_id
                JOIN hf_stored_file sf ON sf.file_id=v.file_id AND sf.state='1'
                LEFT JOIN hf_folder_entry e ON e.space_id=p.space_id AND e.asset_id=a.asset_id
                WHERE a.del_flag='0'
                UNION ALL
                SELECT 'output', o.output_id, p.project_id, e.folder_id,
                       (CASE o.kind WHEN 'image' THEN '生成图片' ELSE '生成视频' END)
                           || '-' || j.job_id || '-' || (o.ordinal+1),
                       sf.storage_key, sf.mime_type
                FROM projects p JOIN hf_creation_job j USING (project_id)
                JOIN hf_generated_output o USING (job_id)
                JOIN hf_stored_file sf ON sf.file_id=o.file_id AND sf.state='1'
                LEFT JOIN hf_folder_entry e ON e.output_id=o.output_id AND e.space_id=p.space_id
                WHERE o.del_flag='0' AND o.archive_state='2'
                  AND NOT (o.actual_metadata ? 'assetId' AND e.entry_id IS NULL)
            )
            SELECT * FROM entries ORDER BY project_id, id, kind
        """)
        return (await db.execute(query)).mappings().all()
