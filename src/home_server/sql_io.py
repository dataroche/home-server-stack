from typing import Type

from sqlalchemy import Column, Table, MetaData, Integer
from sqlalchemy.engine import Engine
from sqlalchemy.orm import registry, sessionmaker

from sqlmodel.main import get_column_from_field

from .base import BaseModelIO, M


class SqlModelIO(BaseModelIO[M]):
    def __init__(
        self,
        engine: Engine,
        metric_name: str,
        schema: Type[M],
        timestamp_mult_to_ns: int = 1000000,
    ):
        self.engine = engine
        self.mapper_registry = registry()
        self.Session = sessionmaker(self.engine)
        super().__init__(
            metric_name=metric_name,
            schema=schema,
            timestamp_mult_to_ns=timestamp_mult_to_ns,
        )

    def _init_schema(self, schema: Type[M], prefix: str = ""):
        super()._init_schema(schema, prefix=prefix)

        columns = [Column("__id__", Integer, primary_key=True)]
        for name, model_field in schema.__fields__.items():
            column = get_column_from_field(model_field)
            column.name = name
            columns.append(column)

        metadata = MetaData(bind=self.engine)
        self.table = Table(self.metric_name, metadata, *columns)
        self.table.create()
        self.mapper_registry.map_imperatively(schema, self.table)

    def metric(self, model: M):
        with self.Session() as session:
            session.add(model)
            session.commit()
