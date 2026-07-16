import logging
from datetime import datetime, timedelta, date
from typing import Optional

from google.analytics.data_v1beta import BetaAnalyticsDataClient
from google.analytics.data_v1beta.types import (
    RunReportRequest,
    DateRange,
    Dimension,
    Metric,
)

from app.connectors.base import replace_metrics_window
from app.credentials import CredentialsDecryptError, decrypt_credentials
from app.ds_status import mark_active, mark_error, mark_reauth_required
from app.google_oauth import ensure_fresh_credentials, persist_datasource_token_update
from app.models import DataSource
from app.database import SessionLocal

logger = logging.getLogger(__name__)

GA4_SCOPES = ["https://www.googleapis.com/auth/analytics.readonly"]


def _get_client(ds: DataSource, *, force_refresh: bool = True) -> Optional[BetaAnalyticsDataClient]:
    if not ds.credentials_encrypted:
        return None
    creds_data = decrypt_credentials(ds.credentials_encrypted)
    token = creds_data.get("access_token")
    refresh_token = creds_data.get("refresh_token")
    if not token and not refresh_token:
        return None
    # GA4 gRPC rejects stale bearer tokens that google-auth still treats as valid
    credentials, updated, did_refresh = ensure_fresh_credentials(
        creds_data, scopes=GA4_SCOPES, force=force_refresh
    )
    if did_refresh:
        persist_datasource_token_update(ds, updated)
        db = SessionLocal()
        try:
            db.merge(ds)
            db.commit()
        finally:
            db.close()
    return BetaAnalyticsDataClient(credentials=credentials)


def sync_ga4(ds: DataSource) -> bool:
    property_id = None
    try:
        if ds.credentials_encrypted:
            creds_data = decrypt_credentials(ds.credentials_encrypted)
            property_id = creds_data.get("property_id")
    except CredentialsDecryptError as e:
        logger.error("DataSource %s: GA4 decrypt failed: %s", ds.id, e)
        mark_reauth_required(ds, str(e))
        db = SessionLocal()
        try:
            db.merge(ds)
            db.commit()
        finally:
            db.close()
        return False

    if not property_id:
        logger.error(f"DataSource {ds.id}: No property_id in credentials for GA4 sync")
        mark_error(ds, "Missing GA4 property_id")
        db = SessionLocal()
        try:
            db.merge(ds)
            db.commit()
        finally:
            db.close()
        return False

    try:
        client = _get_client(ds, force_refresh=True)
    except CredentialsDecryptError as e:
        logger.error("DataSource %s: GA4 decrypt failed: %s", ds.id, e)
        mark_reauth_required(ds, str(e))
        db = SessionLocal()
        try:
            db.merge(ds)
            db.commit()
        finally:
            db.close()
        return False
    except Exception as e:
        logger.error(f"DataSource {ds.id}: GA4 credential refresh failed: {e}")
        mark_error(ds, str(e))
        db = SessionLocal()
        try:
            db.merge(ds)
            db.commit()
        finally:
            db.close()
        return False

    if client is None:
        logger.error(f"DataSource {ds.id}: No valid credentials for GA4 sync")
        mark_error(ds, "No valid Google credentials")
        db = SessionLocal()
        try:
            db.merge(ds)
            db.commit()
        finally:
            db.close()
        return False

    try:
        end_date = date.today()
        start_date = end_date - timedelta(days=90)

        request = RunReportRequest(
            property=f"properties/{property_id}",
            dimensions=[Dimension(name="date"), Dimension(name="landingPage")],
            metrics=[
                Metric(name="sessions"),
                Metric(name="keyEvents"),
                Metric(name="screenPageViews"),
            ],
            date_ranges=[
                DateRange(start_date=start_date.isoformat(), end_date=end_date.isoformat())
            ],
        )

        try:
            response = client.run_report(request)
        except Exception as api_err:
            if "401" in str(api_err) or "unauthenticated" in str(api_err).lower():
                logger.warning(
                    "GA4 401 for DataSource %s — refreshing token and retrying", ds.id
                )
                client = _get_client(ds, force_refresh=True)
                if client is None:
                    raise
                response = client.run_report(request)
            else:
                raise

        # Organic Search channel sessions for funnel click→session alignment
        organic_sessions_rows: list = []
        try:
            organic_request = RunReportRequest(
                property=f"properties/{property_id}",
                dimensions=[Dimension(name="date"), Dimension(name="sessionDefaultChannelGrouping")],
                metrics=[Metric(name="sessions")],
                date_ranges=[
                    DateRange(start_date=start_date.isoformat(), end_date=end_date.isoformat())
                ],
                dimension_filter={
                    "filter": {
                        "field_name": "sessionDefaultChannelGrouping",
                        "string_filter": {
                            "match_type": "EXACT",
                            "value": "Organic Search",
                        },
                    }
                },
            )
            organic_response = client.run_report(organic_request)
            organic_sessions_rows = list(organic_response.rows)
        except Exception as e:
            logger.warning(
                "GA4 Organic Search channel query failed for client %s: %s — "
                "funnel will fall back to all-channel sessions",
                ds.client_id,
                e,
            )

        row_count = len(response.rows) if response.rows else 0
        metric_payloads: list[dict] = []

        if response.rows:
            for row in response.rows:
                date_str = row.dimension_values[0].value
                landing_page = row.dimension_values[1].value
                row_date = datetime.strptime(date_str, "%Y%m%d").date()

                metric_values = {
                    "sessions": row.metric_values[0].value,
                    "key_events": row.metric_values[1].value,
                    "screen_page_views": row.metric_values[2].value,
                }

                for metric_name, value in metric_values.items():
                    metric_payloads.append(
                        {
                            "date": row_date,
                            "metric_name": metric_name,
                            "value": float(value),
                            "dimension_type": "landing_page",
                            "dimension_value": landing_page,
                        }
                    )

        for row in organic_sessions_rows:
            date_str = row.dimension_values[0].value
            channel = row.dimension_values[1].value
            row_date = datetime.strptime(date_str, "%Y%m%d").date()
            metric_payloads.append(
                {
                    "date": row_date,
                    "metric_name": "sessions",
                    "value": float(row.metric_values[0].value),
                    "dimension_type": "organic_channel",
                    "dimension_value": channel,
                }
            )

        db = SessionLocal()
        try:
            replace_metrics_window(
                db,
                client_id=ds.client_id,
                source="ga4",
                start=start_date,
                end=end_date,
                rows=metric_payloads,
            )

            mark_active(ds)
            db.merge(ds)
            db.commit()
            if row_count == 0:
                logger.warning(
                    f"GA4 sync returned 0 rows for client {ds.client_id} "
                    f"(linked OK — no Analytics data in range yet)"
                )
            else:
                logger.info(f"GA4 sync complete for client {ds.client_id}: {row_count} rows")
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

        return True

    except Exception as e:
        logger.error(f"GA4 sync failed for DataSource {ds.id}: {e}")
        mark_error(ds, str(e))
        db = SessionLocal()
        try:
            db.merge(ds)
            db.commit()
        finally:
            db.close()
        return False
