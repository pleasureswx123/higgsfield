"""生成任务身份与固定输入读取。"""

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from module_higgsfield.dao.job_event_dao import JobEventDao
from module_higgsfield.entity.do.job_do import HfCreationJob, HfJobReference
from module_higgsfield.entity.do.model_do import HfModelProfile, HfModelProfileVersion
from module_higgsfield.entity.do.project_do import HfProject, HfProjectMember, HfProjectRolePermission
from module_higgsfield.entity.do.provider_call_do import HfProviderCall
from module_higgsfield.entity.do.generated_output_do import HfGeneratedOutput


class GenerationReadDao:
    @staticmethod
    def category_condition(category):
        """按任务与输出事实分类，在分页前过滤；异常优先于进行中。"""
        def output_in(states):
            return select(HfGeneratedOutput.output_id).where(
                HfGeneratedOutput.job_id == HfCreationJob.job_id,
                HfGeneratedOutput.archive_state.in_(states),
            ).correlate(HfCreationJob).exists()
        attention = or_(HfCreationJob.orchestration_state.in_(('3', '6')),
                        and_(HfCreationJob.orchestration_state == '4', HfCreationJob.next_action_time.is_(None)),
                        HfCreationJob.upstream_state == '4', output_in(('3', '4')))
        active = and_(~attention, HfCreationJob.upstream_state != '5', or_(
            HfCreationJob.orchestration_state.in_(('0', '1', '2', '4')), output_in(('0', '1'))))
        return {'active': active, 'attention': attention, 'done': and_(~attention, ~active)}[category]

    @staticmethod
    async def latest_execution_call(db, job_id):
        return await db.scalar(
            select(HfProviderCall)
            .where(HfProviderCall.job_id == job_id,
                   HfProviderCall.operation.in_(['image', 'video_submit', 'video_poll']))
            .order_by(HfProviderCall.create_time.desc(), HfProviderCall.call_id.desc()).limit(1)
        )

    @staticmethod
    async def page(db, actor_id, query):
        readable_project = (
            select(HfProjectRolePermission.role_id)
            .where(
                HfProjectRolePermission.role_id == HfProjectMember.role_id,
                HfProjectRolePermission.permission_code == 'project:read',
            )
            .correlate(HfProjectMember)
            .exists()
        )
        readable_job = (
            select(HfProjectRolePermission.role_id)
            .where(
                HfProjectRolePermission.role_id == HfProjectMember.role_id,
                HfProjectRolePermission.permission_code == 'generation:read',
                or_(
                    HfProjectRolePermission.data_scope == 'project',
                    and_(
                        HfProjectRolePermission.data_scope == 'own',
                        HfCreationJob.actor_id == actor_id,
                    ),
                ),
            )
            .correlate(HfProjectMember, HfCreationJob)
            .exists()
        )
        statement = (
            select(HfCreationJob)
            .join(
                HfProject,
                HfProject.project_id == HfCreationJob.project_id,
            )
            .join(HfProjectMember, HfProjectMember.project_id == HfProject.project_id)
            .where(
                HfProject.del_flag == '0',
                HfProjectMember.user_id == actor_id,
                HfProjectMember.status == '0',
                readable_project,
                readable_job,
            )
        )
        if query.project_id:
            statement = statement.where(HfCreationJob.project_id == int(query.project_id))
        if query.folder_id:
            statement = statement.where(HfCreationJob.input_snapshot['folderId'].as_string() == query.folder_id)
        elif query.root_folder:
            statement = statement.where(HfCreationJob.input_snapshot['folderId'].as_string().is_(None))
        if query.scope == 'mine':
            statement = statement.where(HfCreationJob.actor_id == actor_id)
        if query.kind:
            statement = statement.where(HfCreationJob.kind == query.kind)
        if query.category:
            statement = statement.where(GenerationReadDao.category_condition(query.category))
        if query.state:
            statement = statement.where(
                HfCreationJob.orchestration_state == str(JobEventDao.ORCHESTRATION.index(query.state))
            )
        if query.from_time:
            statement = statement.where(HfCreationJob.create_time >= query.from_time)
        if query.to_time:
            statement = statement.where(HfCreationJob.create_time < query.to_time)
        total = await db.scalar(select(func.count()).select_from(statement.subquery()))
        rows = (
            await db.scalars(
                statement.order_by(
                    HfCreationJob.create_time.desc(),
                    HfCreationJob.job_id.desc(),
                )
                .offset((query.page_num - 1) * query.page_size)
                .limit(query.page_size)
                .with_for_update(read=True, of=HfCreationJob)
            )
        ).all()
        return rows, total

    @staticmethod
    async def job(db: AsyncSession, identity: int, lock=False) -> HfCreationJob | None:
        statement = select(HfCreationJob).where(HfCreationJob.job_id == identity)
        if lock:
            statement = statement.with_for_update(read=lock != 'write').execution_options(populate_existing=True)
        return await db.scalar(statement)

    @staticmethod
    async def model(db, version_id):
        return (
            await db.execute(
                select(HfModelProfile.model_id, HfModelProfile.display_name)
                .join(
                    HfModelProfileVersion,
                    HfModelProfileVersion.model_id == HfModelProfile.model_id,
                )
                .where(HfModelProfileVersion.model_version_id == version_id)
            )
        ).first()

    @staticmethod
    async def references(db: AsyncSession, identity: int) -> list[HfJobReference]:
        return list(
            (
                await db.scalars(
                    select(HfJobReference)
                    .where(
                        HfJobReference.job_id == identity,
                    )
                    .order_by(HfJobReference.ordinal)
                )
            ).all()
        )
