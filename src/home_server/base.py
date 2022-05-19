import logging
import pandas as pd
from typing import List, Set, Type, Generic, TypeVar
import collections

from pydantic import BaseModel, Field, validator
from telegraf.client import TelegrafClient
from influxdb import DataFrameClient
from influxdb.resultset import ResultSet

logger = logging.getLogger(__name__)

class OutputModel(BaseModel):
    __metric_name__ = ''
    __timestamp_mult_to_ns__ = 0

    @classmethod
    def telegraf_output_factory(cls, client: TelegrafClient, **kwargs):
        metric_name = kwargs.pop('metric_name', cls.__metric_name__)
        kwargs['timestamp_mult_to_ns'] = kwargs.pop('timestamp_mult_to_ns', cls.__timestamp_mult_to_ns__)

        if not kwargs['timestamp_mult_to_ns']:
            # Use default
            del kwargs['timestamp_mult_to_ns']

        if not metric_name:
            raise ValueError('Requires metric name.')

        return TelegrafOutput(
            client=client,
            metric_name=metric_name,
            schema=cls,
            **kwargs
        )

M = TypeVar('M', bound=BaseModel)
OM = TypeVar('OM', bound=OutputModel)

class TelegrafOutputFactory():
    def __init__(self, client: TelegrafClient, influxdb_client: DataFrameClient = None):
        self.client = client
        self.influxdb_client = influxdb_client

    def __call__(self, schema: Type[OM]):
        return schema.telegraf_output_factory(self.client, influxdb_client=self.influxdb_client)


class TelegrafOutput(Generic[M]):
    def __init__(self, client: TelegrafClient, metric_name: str, schema: Type[M], timestamp_mult_to_ns: int = 1000000, influxdb_client: DataFrameClient = None):
        self.client = client
        self.influxdb_client = influxdb_client
        self.metric_name = metric_name

        self.tags: Set[str] = set()
        self.timestamp_field = ''
        self.timestamp_mult = timestamp_mult_to_ns

        self.schema = schema
        self._init_schema(schema)

    def _init_schema(self, schema: Type[M], prefix: str = ''):

        self.tags = set()
        for f_name, field in schema.__fields__.items():
            f_name = prefix + f_name
            extra = field.field_info.extra
            if extra.get('telegraf_tag'):
                self.tags.add(f_name)
            
            if extra.get('telegraf_timestamp'):
                self.timestamp_field = f_name
    
    def metric(self, model: M):
        data = flatten(model.dict(exclude_unset=True, exclude_defaults=True))

        pop_data = lambda key: (data.pop(key) if key in data else getattr(model, key))

        tags = {
            t: pop_data(t)
            for t in self.tags
        }
        timestamp = self.timestamp_mult * pop_data(self.timestamp_field) if self.timestamp_field else None
        
        self.client.metric(self.metric_name, values=data, tags=tags, timestamp=timestamp)

    @property
    def tags_str_query(self):
        
        tags_str = ','.join(self.tags)
        tags_str = ',' + tags_str if tags_str else ''
        return tags_str

    def get_latest_unique_rows(self, groupby: str = None, **where):
        if not self.influxdb_client:
            raise ValueError('Requires influxdb client')

        where_str = ' AND '.join(f'"{key}"=\'{value}\'' for key, value in where.items()) if where else '1=1'
        query = f'SELECT *{self.tags_str_query} FROM "{self.metric_name}" WHERE {where_str} GROUP BY * ORDER BY DESC LIMIT 1'

        result = self.influxdb_client.query(query)
        df = _parse_influx_df(result)
        if groupby:
            df.sort_index(inplace=True)
            df['__index'] = df.index
            df = df.groupby(groupby).last()
            df[groupby] = df.index
            df.set_index('__index', inplace=True)

        models = [self.from_df_row(timestamp, row) for timestamp, row in df.iterrows()]
        return models


    def get_timeseries(self, limit: int = 10000, **where):
        if not self.influxdb_client:
            raise ValueError('Requires influxdb client')

        where_str = ' AND '.join(f'"{key}"=\'{value}\'' for key, value in where.items()) if where else '1=1'
        query = f'SELECT *{self.tags_str_query} FROM "{self.metric_name}" WHERE {where_str} ORDER BY DESC LIMIT {limit}'
        result = self.influxdb_client.query(query)
        df = _parse_influx_df(result)
        df.sort_index(inplace=True)
        df = df[~df.index.duplicated(keep='first')]
        return df

    def from_df_row(self, timestamp: pd.Timestamp, row: pd.Series):
        NS_PER_SECOND = 10**9
        orig_timestamp_precision_mult = NS_PER_SECOND / self.timestamp_mult
        data = {
            self.timestamp_field: timestamp.timestamp() * orig_timestamp_precision_mult,
            **row.to_dict()
        }
        return self.schema.construct(**data)
        

def _parse_influx_df(result: ResultSet):
    frames = []
    for measurement, df in result.items():
        frames.append(df)

    if not frames:
        return pd.DataFrame()
    
    return pd.concat(frames)

def flatten(d, parent_key='', sep='_'):
    items = []
    for k, v in d.items():
        new_key = parent_key + sep + k if parent_key else k
        if isinstance(v, collections.MutableMapping):
            items.extend(flatten(v, new_key, sep=sep).items())
        else:
            items.append((new_key, v))
    return dict(items)
    

def trading_pair_validator(t_pair: str):
    return t_pair.replace('-', '/')
    
class AssetTags(BaseModel):
    base_asset: str = Field(telegraf_tag=True)
    exchange: str = Field(telegraf_tag=True)
    quote_asset: str = Field(telegraf_tag=True)
    trading_pair: str = Field(telegraf_tag=True)

    @validator('trading_pair')
    def validate_trading_pair(cls, value: str):
        return trading_pair_validator(value)