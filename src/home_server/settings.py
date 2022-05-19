from typing import Literal
from pydantic import BaseSettings

from telegraf.client import TelegrafClient, HttpClient
from influxdb import DataFrameClient as InfluxDbDataFrameClient


class Settings(BaseSettings):
    telegraf_host: str = "127.0.0.1"
    telegraf_port: int = 8092
    telegraf_protocol: Literal["udp", "http"] = "http"

    influxdb_host: str = "127.0.0.1"
    influxdb_port: int = 8086
    influxdb_username: str = ""
    influxdb_password: str = ""
    influxdb_database: str = "telegraf"

    def influxdb_http_write_client_factory(self):
        return HttpClient(host=self.influxdb_host, port=self.influxdb_port)

    def telegraf_client_factory(self):
        if self.telegraf_protocol == "http":
            return HttpClient(host=self.telegraf_host, port=self.telegraf_port)
        else:
            return TelegrafClient(host=self.telegraf_host, port=self.telegraf_port)

    def influxdb_client_factory(self):
        return InfluxDbDataFrameClient(
            host=self.influxdb_host,
            port=self.influxdb_port,
            username=self.influxdb_username,
            password=self.influxdb_password,
            database=self.influxdb_database,
        )
