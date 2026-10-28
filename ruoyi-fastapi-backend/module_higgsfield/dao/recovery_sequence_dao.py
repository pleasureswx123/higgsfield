"""读取当前搜索路径可见业务表的主键序列，不推进或修复序列。"""

from sqlalchemy import text


class RecoverySequenceDao:
    @staticmethod
    async def inventory(db):
        rows = (await db.execute(text('''
            SELECT n.nspname AS schema_name, c.relname AS table_name, a.attname AS column_name,
                   sn.nspname AS sequence_schema, s.relname AS sequence_name,
                   q.seqincrement, q.seqmax, q.seqcycle
            FROM pg_class c
            JOIN pg_namespace n ON n.oid=c.relnamespace
            JOIN pg_index i ON i.indrelid=c.oid AND i.indisprimary AND i.indnkeyatts=1
            JOIN pg_attribute a ON a.attrelid=c.oid AND a.attnum=i.indkey[0]
            LEFT JOIN pg_class s ON s.oid=to_regclass(pg_get_serial_sequence(
                format('%I.%I', n.nspname, c.relname), a.attname))
            LEFT JOIN pg_namespace sn ON sn.oid=s.relnamespace
            LEFT JOIN pg_sequence q ON q.seqrelid=s.oid
            WHERE c.relkind IN ('r','p') AND left(c.relname,3)='hf_'
                  AND pg_table_is_visible(c.oid) AND a.atttypid='bigint'::regtype
            ORDER BY n.nspname,c.relname
        '''))).mappings().all()
        quote = db.bind.dialect.identifier_preparer.quote_identifier
        results = []
        for row in rows:
            item = dict(row)
            table = f"{quote(row['schema_name'])}.{quote(row['table_name'])}"
            column = quote(row['column_name'])
            # 标识符仅来自数据库目录，并按方言引用；不拼接用户输入。
            item['max_id'] = await db.scalar(text(f'SELECT max({column}) FROM {table}'))
            if row['sequence_name']:
                sequence = f"{quote(row['sequence_schema'])}.{quote(row['sequence_name'])}"
                state = (await db.execute(text(f'SELECT last_value,is_called FROM {sequence}'))).mappings().one()
                item.update(state)
            results.append(item)
        return results
