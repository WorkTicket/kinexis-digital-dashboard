"""MetricDaily replace_metrics_window is idempotent for the same date window."""

from datetime import date, timedelta

from sqlalchemy import create_engine, func
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.connectors.base import replace_metrics_window
from app.database import Base
from app.models import Client, MetricDaily


def _session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    return TestingSession()


def test_metric_daily_idempotent_sync():
    db = _session()
    client = Client(name="Idempotency Co")
    db.add(client)
    db.commit()
    db.refresh(client)

    start = date.today() - timedelta(days=6)
    end = date.today()
    rows = []
    for i in range(7):
        d = start + timedelta(days=i)
        rows.append(
            {
                "date": d,
                "metric_name": "clicks",
                "value": 10.0 + i,
                "dimension_type": "query",
                "dimension_value": "",
            }
        )
        rows.append(
            {
                "date": d,
                "metric_name": "impressions",
                "value": 100.0 + i,
                "dimension_type": "query",
                "dimension_value": "",
            }
        )

    n1 = replace_metrics_window(
        db,
        client_id=client.id,
        source="gsc",
        start=start,
        end=end,
        rows=rows,
    )
    db.commit()
    count1 = db.query(func.count(MetricDaily.id)).filter(MetricDaily.client_id == client.id).scalar()
    total1 = (
        db.query(func.sum(MetricDaily.value))
        .filter(MetricDaily.client_id == client.id, MetricDaily.metric_name == "clicks")
        .scalar()
    )

    n2 = replace_metrics_window(
        db,
        client_id=client.id,
        source="gsc",
        start=start,
        end=end,
        rows=rows,
    )
    db.commit()
    count2 = db.query(func.count(MetricDaily.id)).filter(MetricDaily.client_id == client.id).scalar()
    total2 = (
        db.query(func.sum(MetricDaily.value))
        .filter(MetricDaily.client_id == client.id, MetricDaily.metric_name == "clicks")
        .scalar()
    )

    assert n1 == n2 == len(rows)
    assert count1 == count2 == len(rows)
    assert total1 == total2
    db.close()
