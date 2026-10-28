"""价格簿锁与发布事务共享，读取同一受理时点的半开生效区间。"""

from datetime import datetime

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from module_higgsfield.entity.do.price_do import HfPriceActivation, HfPriceBook, HfPriceVersion


class GenerationPriceDao:
    @staticmethod
    async def procurement_books(db: AsyncSession, variant_id: int, account_id: int, currency: str) -> list:
        return list(await db.scalars(select(HfPriceBook).where(
            HfPriceBook.model_variant_id == variant_id, HfPriceBook.account_id == account_id,
            HfPriceBook.purpose == 'procurement', HfPriceBook.currency == currency)
            .order_by(HfPriceBook.price_book_id).with_for_update(read=True)
            .execution_options(populate_existing=True)))

    @staticmethod
    async def books(db: AsyncSession, variant_id: int, account_id: int, currencies: dict[str, str]) -> list:
        return list(
            await db.scalars(
                select(HfPriceBook)
                .where(
                    HfPriceBook.model_variant_id == variant_id,
                    or_(
                        (HfPriceBook.purpose == 'platform')
                        & HfPriceBook.account_id.is_(None)
                        & (HfPriceBook.currency == currencies['platform']),
                        (HfPriceBook.purpose == 'procurement')
                        & (HfPriceBook.account_id == account_id)
                        & (HfPriceBook.currency == currencies['procurement']),
                    ),
                )
                .order_by(HfPriceBook.price_book_id)
                .with_for_update(read=True)
                .execution_options(populate_existing=True)
            )
        )

    @staticmethod
    async def active(db: AsyncSession, book_id: int, at: datetime) -> list:
        return list(
            (
                await db.execute(
                    select(HfPriceActivation, HfPriceVersion)
                    .join(HfPriceVersion, HfPriceVersion.price_version_id == HfPriceActivation.price_version_id)
                    .where(
                        HfPriceActivation.price_book_id == book_id,
                        HfPriceVersion.price_book_id == book_id,
                        HfPriceVersion.status == '1',
                        HfPriceActivation.effective_from <= at,
                        or_(HfPriceActivation.effective_until.is_(None), HfPriceActivation.effective_until > at),
                    )
                    .order_by(HfPriceActivation.activation_id)
                )
            ).all()
        )
