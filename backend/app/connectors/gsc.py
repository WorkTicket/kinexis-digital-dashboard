import logging
from datetime import datetime, timedelta, date
from typing import Optional

from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials

from app.connectors.base import normalize_dimension, replace_metrics_window
from app.credentials import CredentialsDecryptError, decrypt_credentials
from app.ds_status import mark_active, mark_error, mark_partial, mark_reauth_required
from app.google_oauth import ensure_fresh_credentials, persist_datasource_token_update
from app.models import DataSource
from app.database import SessionLocal

logger = logging.getLogger(__name__)

GSC_SCOPES = ["https://www.googleapis.com/auth/webmasters.readonly"]
GSC_PAGE_SIZE = 1000
# Safety cap: 25 pages × 1000 = 25k rows per dimension query
GSC_MAX_PAGES = 25

# Light dimensions produce few rows (1 date, ~3 devices, ~10-50 countries)
# and can safely cover 400 days for YoY comparisons without hitting the 25k cap.
GSC_DEEP_DAYS = 400
# Heavy dimensions (query, page) can hit pagination limits quickly over long ranges.
GSC_SHALLOW_DAYS = 90

LIGHT_DIMENSIONS = {"site", "device", "country"}

DIMENSION_QUERIES = [
    {
        "dimensions": ["date"],
        "dimension_type": None,  # site-level total — most reliable
        "label": "site",
    },
    {
        "dimensions": ["query", "date"],
        "dimension_type": "query",
        "label": "query",
    },
    {
        "dimensions": ["page", "date"],
        "dimension_type": "page",
        "label": "page",
    },
    {
        "dimensions": ["query", "page", "date"],
        "dimension_type": "query_page",
        "label": "query_page",
        "compound": True,
    },
    {
        "dimensions": ["device", "date"],
        "dimension_type": "device",
        "label": "device",
    },
    {
        "dimensions": ["country", "date"],
        "dimension_type": "country",
        "label": "country",
    },
]


def _get_credentials(ds: DataSource) -> Optional[Credentials]:
    if not ds.credentials_encrypted:
        return None
    creds_data = decrypt_credentials(ds.credentials_encrypted)
    token = creds_data.get("access_token")
    refresh_token = creds_data.get("refresh_token")
    if not token and not refresh_token:
        return None
    credentials, updated, did_refresh = ensure_fresh_credentials(creds_data, scopes=GSC_SCOPES)
    if did_refresh:
        persist_datasource_token_update(ds, updated)
        db = SessionLocal()
        try:
            db.merge(ds)
            db.commit()
        finally:
            db.close()
    return credentials


def _fetch_dimension_rows(service, site_url: str, start_date: date, end_date: date, dim_config: dict):
    """Paginate GSC searchanalytics until short page or safety cap. Returns (rows, truncated)."""
    all_rows: list = []
    truncated = False
    start_row = 0
    for _ in range(GSC_MAX_PAGES):
        response = (
            service.searchanalytics()
            .query(
                siteUrl=site_url,
                body={
                    "startDate": start_date.isoformat(),
                    "endDate": end_date.isoformat(),
                    "dimensions": dim_config["dimensions"],
                    "rowLimit": GSC_PAGE_SIZE,
                    "startRow": start_row,
                },
            )
            .execute()
        )
        batch = response.get("rows", []) or []
        all_rows.extend(batch)
        if len(batch) < GSC_PAGE_SIZE:
            break
        start_row += GSC_PAGE_SIZE
    else:
        # Hit max pages with a full last page → likely more data exists
        truncated = True
    return all_rows, truncated


def sync_gsc(ds: DataSource) -> bool:
    site_url = None
    try:
        if ds.credentials_encrypted:
            creds_data = decrypt_credentials(ds.credentials_encrypted)
            site_url = creds_data.get("site_url")
    except CredentialsDecryptError as e:
        logger.error("DataSource %s: GSC decrypt failed: %s", ds.id, e)
        mark_reauth_required(ds, str(e))
        db = SessionLocal()
        try:
            db.merge(ds)
            db.commit()
        finally:
            db.close()
        return False

    if not site_url:
        logger.error(f"DataSource {ds.id}: No site_url in credentials for GSC sync")
        mark_error(ds, "No site_url in credentials")
        db = SessionLocal()
        try:
            db.merge(ds)
            db.commit()
        finally:
            db.close()
        return False

    try:
        credentials = _get_credentials(ds)
    except CredentialsDecryptError as e:
        mark_reauth_required(ds, str(e))
        db = SessionLocal()
        try:
            db.merge(ds)
            db.commit()
        finally:
            db.close()
        return False
    except Exception as e:
        logger.error(f"DataSource {ds.id}: GSC credential refresh failed: {e}")
        mark_error(ds, str(e))
        db = SessionLocal()
        try:
            db.merge(ds)
            db.commit()
        finally:
            db.close()
        return False

    if not credentials:
        logger.error(f"DataSource {ds.id}: No valid credentials for GSC sync")
        mark_error(ds, "No valid Google credentials")
        db = SessionLocal()
        try:
            db.merge(ds)
            db.commit()
        finally:
            db.close()
        return False

    try:
        service = build("searchconsole", "v1", credentials=credentials)
        end_date = date.today()
        deep_start = end_date - timedelta(days=GSC_DEEP_DAYS)
        shallow_start = end_date - timedelta(days=GSC_SHALLOW_DAYS)

        total_rows = 0
        any_truncated = False
        truncated_dims: list[str] = []
        metric_payloads: list[dict] = []
        db = SessionLocal()

        try:
            for dim_config in DIMENSION_QUERIES:
                is_light = dim_config["label"] in LIGHT_DIMENSIONS
                dim_start = deep_start if is_light else shallow_start
                try:
                    rows, truncated = _fetch_dimension_rows(
                        service, site_url, dim_start, end_date, dim_config
                    )
                    if truncated:
                        any_truncated = True
                        truncated_dims.append(dim_config["label"])

                    dim_type = normalize_dimension(dim_config["dimension_type"])
                    compound = dim_config.get("compound", False)

                    for row in rows:
                        keys = row.get("keys", [])
                        if compound:
                            query_val = keys[0] if len(keys) > 0 else ""
                            page_val = keys[1] if len(keys) > 1 else ""
                            row_date_str = keys[2] if len(keys) > 2 else ""
                            dim_value = f"{query_val}|||{page_val}"
                        else:
                            # The last key is always the date; preceding keys are dimension values.
                            # Handles both multi-dim (["device","date"]) and single-dim (["date"]).
                            row_date_str = keys[-1] if keys else ""
                            dim_value = "" if dim_type == "site" and len(keys) <= 1 else (keys[0] if len(keys) > 1 else "")
                        row_date = datetime.strptime(row_date_str, "%Y-%m-%d").date()

                        metrics = {
                            "clicks": row.get("clicks", 0),
                            "impressions": row.get("impressions", 0),
                            "ctr": row.get("ctr", 0),
                            "position": row.get("position", 0),
                        }

                        for metric_name, value in metrics.items():
                            metric_payloads.append(
                                {
                                    "date": row_date,
                                    "metric_name": metric_name,
                                    "value": float(value),
                                    "dimension_type": dim_type,
                                    "dimension_value": normalize_dimension(dim_value),
                                }
                            )

                    total_rows += len(rows)
                    logger.debug(
                        f"GSC {dim_config['label']} dimension: {len(rows)} rows for client {ds.client_id}"
                    )

                except Exception as e:
                    logger.warning(
                        f"GSC {dim_config['label']} dimension fetch failed for DS {ds.id}: {e}"
                    )

            replace_metrics_window(
                db,
                client_id=ds.client_id,
                source="gsc",
                start=deep_start,
                end=end_date,
                rows=metric_payloads,
            )

            if any_truncated:
                msg = (
                    "GSC sync truncated at pagination cap for: "
                    + ", ".join(truncated_dims)
                    + ". Totals may be incomplete."
                )
                mark_partial(ds, msg)
                logger.warning("DataSource %s: %s", ds.id, msg)
            else:
                mark_active(ds)

            db.merge(ds)
            db.commit()
            if total_rows == 0:
                logger.warning(
                    f"GSC sync returned 0 rows for client {ds.client_id} "
                    f"(linked OK — no Search Console data in range yet)"
                )
            else:
                logger.info(
                    f"GSC sync complete for client {ds.client_id}: "
                    f"{total_rows} total rows (5 dimensions)"
                    + (" [PARTIAL]" if any_truncated else "")
                )

        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

        return True

    except Exception as e:
        logger.error(f"GSC sync failed for DataSource {ds.id}: {e}")
        mark_error(ds, str(e))
        db = SessionLocal()
        try:
            db.merge(ds)
            db.commit()
        finally:
            db.close()
        return False
