import time
from pydantic import Field
from home_server import OutputModel


class MyModel(OutputModel):
    __metric_name__ = "test_model"

    category: str = Field(telegraf_tag=True)
    value: float


def test_send_models():
    output = MyModel.io()

    for x in range(10):
        output.metric(MyModel(category="x", value=float(x)))

    for y in range(2):
        output.metric(MyModel(category="y", value=float(y)))

    time.sleep(1)


def test_get_latest_rows():
    output = MyModel.io()

    data = output.get_timeseries()
    try:
        assert len(data) == 12
    finally:
        output.drop_all_metric()
