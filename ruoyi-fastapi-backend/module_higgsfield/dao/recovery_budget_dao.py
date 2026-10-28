"""预算缓存与只追加账本按原精度比对，不使用浮点或跨币种合并。"""

from sqlalchemy import text


class RecoveryBudgetDao:
    @staticmethod
    async def conversions(db, after_id, limit):
        rows = await db.execute(text('''
            SELECT l.entry_id,l.entry_type,l.exchange_rate_version_id,l.conversion_snapshot,
                   l.reserved_delta,l.consumed_delta,b.currency AS budget_currency,
                   x.exchange_rate_id,x.base_currency,x.quote_currency,x.rate,
                   x.valid_from,x.valid_until,x.status
            FROM hf_budget_ledger_entry l
            LEFT JOIN hf_budget_period p ON p.period_id=l.period_id
            LEFT JOIN hf_budget b ON b.budget_id=p.budget_id
            LEFT JOIN hf_exchange_rate_version x ON x.exchange_rate_id=l.exchange_rate_version_id
            WHERE l.entry_id>:after_id
              AND (l.exchange_rate_version_id IS NOT NULL OR l.conversion_snapshot<>'{}'::jsonb)
            ORDER BY l.entry_id LIMIT :limit
        '''), {'after_id': after_id, 'limit': limit})
        return [dict(row) for row in rows.mappings()]

    REFERENCE_RULES = {
        'period_budget_missing': 'SELECT p.period_id AS id FROM hf_budget_period p WHERE NOT EXISTS (SELECT 1 FROM hf_budget b WHERE b.budget_id=p.budget_id)',
        'reservation_period_missing': 'SELECT r.reservation_id AS id FROM hf_budget_reservation r WHERE NOT EXISTS (SELECT 1 FROM hf_budget_period p WHERE p.period_id=r.period_id)',
        'reservation_job_missing': 'SELECT r.reservation_id AS id FROM hf_budget_reservation r WHERE NOT EXISTS (SELECT 1 FROM hf_creation_job j WHERE j.job_id=r.job_id)',
        'ledger_period_missing': 'SELECT l.entry_id AS id FROM hf_budget_ledger_entry l WHERE NOT EXISTS (SELECT 1 FROM hf_budget_period p WHERE p.period_id=l.period_id)',
        'ledger_reservation_missing': 'SELECT l.entry_id AS id FROM hf_budget_ledger_entry l WHERE l.reservation_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM hf_budget_reservation r WHERE r.reservation_id=l.reservation_id)',
        'ledger_reservation_period_mismatch': 'SELECT l.entry_id AS id FROM hf_budget_ledger_entry l JOIN hf_budget_reservation r ON r.reservation_id=l.reservation_id WHERE l.period_id<>r.period_id',
        'reservation_ledger_mismatch': 'SELECT r.reservation_id AS id FROM hf_budget_reservation r WHERE r.remaining_amount<>coalesce((SELECT sum(l.reserved_delta) FROM hf_budget_ledger_entry l WHERE l.reservation_id=r.reservation_id AND l.period_id=r.period_id),0)',
        'ledger_billing_event_missing': 'SELECT l.entry_id AS id FROM hf_budget_ledger_entry l WHERE l.billing_event_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM hf_billing_event e WHERE e.event_id=l.billing_event_id)',
        'ledger_adjustment_missing': 'SELECT l.entry_id AS id FROM hf_budget_ledger_entry l WHERE l.adjustment_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM hf_billing_adjustment a WHERE a.adjustment_id=l.adjustment_id)',
        'ledger_adjustment_event_mismatch': 'SELECT l.entry_id AS id FROM hf_budget_ledger_entry l JOIN hf_billing_adjustment a ON a.adjustment_id=l.adjustment_id WHERE l.billing_event_id IS DISTINCT FROM a.event_id',
        'ledger_exchange_rate_missing': 'SELECT l.entry_id AS id FROM hf_budget_ledger_entry l WHERE l.exchange_rate_version_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM hf_exchange_rate_version x WHERE x.exchange_rate_id=l.exchange_rate_version_id)',
        'ledger_billing_purpose_mismatch': 'SELECT l.entry_id AS id FROM hf_budget_ledger_entry l JOIN hf_billing_event e ON e.event_id=l.billing_event_id JOIN hf_budget_period p ON p.period_id=l.period_id JOIN hf_budget b ON b.budget_id=p.budget_id WHERE e.purpose<>b.purpose',
    }

    @classmethod
    async def references(cls, db, rule, limit):
        query = cls.REFERENCE_RULES[rule]
        count = await db.scalar(text(f'SELECT count(*) FROM ({query}) AS invalid'))
        ids = list(await db.scalars(text(f'{query} ORDER BY id LIMIT :limit'), {'limit': limit})) if count and limit else []
        return count, ids

    @staticmethod
    async def page(db, after_id, limit):
        rows = await db.execute(text('''
            SELECT p.period_id,
                   p.limit_amount <> coalesce(l.limits,0) AS limit_ledger_mismatch,
                   p.reserved_amount <> coalesce(l.reserved,0) AS reserved_ledger_mismatch,
                   p.consumed_amount <> coalesce(l.consumed,0) AS consumed_ledger_mismatch,
                   p.reserved_amount <> coalesce(r.remaining,0) AS reservation_balance_mismatch
            FROM (SELECT * FROM hf_budget_period WHERE period_id>:after_id ORDER BY period_id LIMIT :limit) p
            LEFT JOIN LATERAL (
                SELECT sum(limit_delta) AS limits, sum(reserved_delta) AS reserved,
                       sum(consumed_delta) AS consumed
                FROM hf_budget_ledger_entry WHERE period_id=p.period_id
            ) l ON true
            LEFT JOIN LATERAL (
                SELECT sum(remaining_amount) AS remaining
                FROM hf_budget_reservation WHERE period_id=p.period_id
            ) r ON true
            ORDER BY p.period_id
        '''), {'after_id': after_id, 'limit': limit})
        return [dict(row) for row in rows.mappings()]
