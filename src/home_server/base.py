import logging
import datetime
import time
import pandas as pd
from typing import Optional, Set, Type, Generic, TypeVar
from collections.abc import MutableMapping

from pydantic import BaseModel
from telegraf.client import ClientBase as WriteClientBase
from influxdb import DataFrameClient
from influxdb.resultset import ResultSet

from .settings import Settings

logger = logging.getLogger(__name__)


class OutputModel(BaseModel):
    __metric_name__ = ""
    __timestamp_mult_to_ns__ = 0

    @classmethod
    def io(
        cls: Type["OM"],
        **kwargs,
    ) -> "ModelIO[OM]":
        settings = Settings()
        if settings.io_mode == "influx":
            return cls.influx_io(settings, **kwargs)
        else:
            raise NotImplementedError(f"Mode {settings.io_mode}")

    @classmethod
    def influx_io(
        cls: Type["OM"],
        settings: Settings,
        write_client: Optional[WriteClientBase] = None,
        read_client: Optional[DataFrameClient] = None,
        **kwargs,
    ):

        if write_client is None:
            write_client = settings.telegraf_client_factory()
            # write_client = settings.influxdb_http_write_client_factory()

        if read_client is None:
            read_client = settings.influxdb_client_factory()

        metric_name = kwargs.pop("metric_name", cls.__metric_name__)
        kwargs["timestamp_mult_to_ns"] = kwargs.pop(
            "timestamp_mult_to_ns", cls.__timestamp_mult_to_ns__
        )

        if not kwargs["timestamp_mult_to_ns"]:
            # Use default
            del kwargs["timestamp_mult_to_ns"]

        if not metric_name:
            raise ValueError("Requires metric name.")

        return ModelIO(
            client=write_client,
            metric_name=metric_name,
            schema=cls,
            influxdb_client=read_client,
            **kwargs,
        )


M = TypeVar("M", bound=BaseModel)
OM = TypeVar("OM", bound=OutputModel)


class BaseModelIO(Generic[M]):
    def __init__(
        self,
        metric_name: str,
        schema: Type[M],
        timestamp_mult_to_ns: int = 1000000,
    ):
        self.metric_name = metric_name

        self.tags: Set[str] = set()
        self.timestamp_field = ""
        self.timestamp_mult = timestamp_mult_to_ns

        self.schema = schema
        self._init_schema(schema)

    def _init_schema(self, schema: Type[M], prefix: str = ""):

        self.tags = set()
        for f_name, field in schema.__fields__.items():
            f_name = prefix + f_name
            extra = field.field_info.extra
            if extra.get("telegraf_tag"):
                self.tags.add(f_name)

            if extra.get("telegraf_timestamp"):
                self.timestamp_field = f_name


class ModelIO(BaseModelIO):
    def __init__(
        self,
        client: WriteClientBase,
        metric_name: str,
        schema: Type[M],
        timestamp_mult_to_ns: int = 1000000,
        influxdb_client: DataFrameClient = None,
    ):
        self.client = client
        self.influxdb_client = influxdb_client
        super().__init__(
            metric_name=metric_name,
            schema=schema,
            timestamp_mult_to_ns=timestamp_mult_to_ns,
        )

    def _init_schema(self, schema: Type[M], prefix: str = ""):

        self.tags = set()
        for f_name, field in schema.__fields__.items():
            f_name = prefix + f_name
            extra = field.field_info.extra
            if extra.get("telegraf_tag"):
                self.tags.add(f_name)

            if extra.get("telegraf_timestamp"):
                self.timestamp_field = f_name

    def metric(self, model: M):
        data = flatten(model.dict(exclude_unset=True, exclude_defaults=True))

        def pop_data(key):
            return data.pop(key) if key in data else getattr(model, key)

        tags = {t: pop_data(t) for t in self.tags}
        timestamp = (
            self.timestamp_mult * pop_data(self.timestamp_field)
            if self.timestamp_field
            else None
        )

        self.client.metric(
            self.metric_name, values=data, tags=tags, timestamp=timestamp
        )

    @property
    def tags_str_query(self):

        tags_str = ",".join(self.tags)
        tags_str = "," + tags_str if tags_str else ""
        return tags_str

    def get_latest_unique_rows(self, groupby: str = None, **where):
        if not self.influxdb_client:
            raise ValueError("Requires influxdb client")

        where_str = (
            " AND ".join(f"\"{key}\"='{value}'" for key, value in where.items())
            if where
            else "1=1"
        )
        query = f'SELECT *{self.tags_str_query} FROM "{self.metric_name}" WHERE {where_str} GROUP BY * ORDER BY DESC LIMIT 1'

        result = self.influxdb_client.query(query)
        df = _parse_influx_df(result)
        if groupby:
            df.sort_index(inplace=True)
            df["__index"] = df.index
            df = df.groupby(groupby).last()
            df[groupby] = df.index
            df.set_index("__index", inplace=True)

        models = [self.from_df_row(timestamp, row) for timestamp, row in df.iterrows()]
        return models

    def get_timeseries(
        self,
        limit: Optional[int] = 10000,
        last_x_seconds: Optional[int] = None,
        after_dt: Optional[datetime.datetime] = None,
        before_dt: Optional[datetime.datetime] = None,
        **where,
    ):
        if not self.influxdb_client:
            raise ValueError("Requires influxdb client")

        where_clauses = [f"\"{key}\"='{value}'" for key, value in where.items()]

        if last_x_seconds:
            after_dt = datetime.datetime.fromtimestamp(time.time() - last_x_seconds)

        if after_dt:
            where_clauses = where_clauses + [f"time >= '{after_dt}'"]

        if before_dt:
            where_clauses = where_clauses + [f"time < '{before_dt}'"]

        where_str = " AND ".join(where_clauses) if where_clauses else "1=1"

        limit_str = f"LIMIT {limit}" if limit else ""
        query = f'SELECT *{self.tags_str_query} FROM "{self.metric_name}" WHERE {where_str} ORDER BY DESC {limit_str}'
        result = self.influxdb_client.query(query, chunked=True, chunk_size=10000)
        df = _parse_influx_df(result)
        df.sort_index(inplace=True)
        df = df[~df.index.duplicated(keep="first")]
        return df

    def from_df_row(self, timestamp: pd.Timestamp, row: pd.Series):
        NS_PER_SECOND = 10**9
        orig_timestamp_precision_mult = NS_PER_SECOND / self.timestamp_mult
        data = {
            self.timestamp_field: timestamp.timestamp() * orig_timestamp_precision_mult,
            **row.to_dict(),
        }
        return self.schema.construct(**data)

    def drop_all_metric(self):
        if not self.influxdb_client:
            raise ValueError("Requires influxdb client")
        self.influxdb_client.drop_measurement(self.metric_name)


def _parse_influx_df(result: ResultSet):
    frames = []
    for measurement, df in result.items():
        frames.append(df)

    if not frames:
        return pd.DataFrame()

    return pd.concat(frames)


def flatten(d, parent_key="", sep="_"):
    items = []
    for k, v in d.items():
        new_key = parent_key + sep + k if parent_key else k
        if isinstance(v, MutableMapping):
            items.extend(flatten(v, new_key, sep=sep).items())
        else:
            items.append((new_key, v))
    return dict(items)
