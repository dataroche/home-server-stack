import os
import pytest

from sqlalchemy import create_engine

from pydantic import Field
from home_server import OutputModel
from home_server.sql_io import SqlModelIO


class MyModel(OutputModel):
    __metric_name__ = "test_model"

    category: str = Field(telegraf_tag=True)
    value: float


@pytest.fixture
def engine():
    filename = "test.db"
    if os.path.exists(filename):
        os.remove(filename)

    return create_engine(f"sqlite:///{filename}")


def test_table_creation(engine):

    output = SqlModelIO(engine=engine, metric_name="test_model", schema=MyModel)
    output.metric(MyModel(category="x", value=2.0))
    print(output)
