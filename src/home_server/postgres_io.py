from typing import Type

from sqlalchemy import Column, Table, MetaData
from sqlalchemy.engine import Engine

from sqlmodel.main import get_column_from_field

from .base import BaseModelIO, M


class PostgresModelIO(BaseModelIO[M]):
    def __init__(
        self,
        engine: Engine,
        metric_name: str,
        schema: Type[M],
        timestamp_mult_to_ns: int = 1000000,
    ):
        self.engine = engine
        super().__init__(
            metric_name=metric_name,
            schema=schema,
            timestamp_mult_to_ns=timestamp_mult_to_ns,
        )

    def _init_schema(self, schema: Type[M], prefix: str = ""):
        super()._init_schema(schema, prefix=prefix)

        columns = []
        for name, model_field in schema.__fields__.items():
            column = get_column_from_field(model_field)
            column.name = name
            columns.append(column)

        metadata = MetaData(bind=self.engine)
        self.table = Table(self.metric_name, metadata, *columns)
        self.table.create()
