"""Exercise the real Recorder database and hourly statistic compilation."""

from datetime import timedelta

import pytest
from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.db_schema import Statistics, StatisticsMeta
from homeassistant.components.recorder.tasks import StatisticsTask
from homeassistant.util import dt as dt_util
from sqlalchemy import select
from test_calendar_publication import Clock
from test_calendar_publication import controlled as controlled
from test_integration import entity_id
from test_integration import system as system


@pytest.mark.parametrize("direction", ["import", "export"])
@pytest.mark.parametrize("system", ["recorder"], indirect=True)
async def test_hourly_recorder_assigns_net_increment_to_closing_hour(
    controlled, tmp_path, monkeypatch, direction
):
    hass, entry, sse = controlled
    await hass.async_start()
    recorder = get_instance(hass)
    await hass.async_block_till_done()
    await recorder.async_block_till_done()
    anchor = (dt_util.utcnow() + timedelta(hours=1)).replace(
        minute=59, second=52, microsecond=0
    )
    clock = Clock(hass, anchor.isoformat())
    key = f"net_{direction}_energy"
    eid = entity_id(hass, "sensor", key)
    sse.publish_interval = 30  # The closure must bypass normal publication gates.
    data = {
        "grid_import_power": 3600 if direction == "import" else 0,
        "grid_export_power": 3600 if direction == "export" else 0,
        "total_load_power": 3600,
    }
    with monkeypatch.context() as patch:
        patch.setattr(
            "homeassistant.helpers.entity.timer", lambda: clock.now().timestamp()
        )
        with clock.patch(patch, hass):
            # Establish a zero point in Recorder before the observed interval.
            old = hass.states.get(eid)
            hass.states.async_set(
                eid,
                "0.0",
                old.attributes,
                force_update=True,
                timestamp=clock.now().timestamp(),
            )
            sse.async_receive(data)
            clock.second = 1
            sse.async_receive(data)
            clock.second = 3
            sse._tick(clock.now())
            assert hass.states.get(eid).last_updated == clock.now()
    await hass.async_block_till_done()
    await recorder.async_block_till_done()
    start = anchor.replace(minute=55, second=0)
    recorder.queue_task(StatisticsTask(start, False))
    recorder.queue_task(StatisticsTask(start + timedelta(hours=1), False))
    await recorder.async_block_till_done()

    def rows():
        with recorder.get_session() as session:
            return session.execute(
                select(Statistics.start_ts, Statistics.sum)
                .join(StatisticsMeta, Statistics.metadata_id == StatisticsMeta.id)
                .where(StatisticsMeta.statistic_id == eid)
                .order_by(Statistics.start_ts)
            ).all()

    hourly = await hass.async_add_executor_job(rows)
    assert len(hourly) == 2
    assert hourly[0][0] == start.replace(minute=0).timestamp()
    assert hourly[0][1] == pytest.approx(0.001)
    assert hourly[1][1] - hourly[0][1] == 0
