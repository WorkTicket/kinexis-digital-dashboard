import json
import logging
from typing import Any, Optional

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import DataSource, Client, JobRun
from app.connectors.gsc import sync_gsc
from app.connectors.ga4 import sync_ga4
from app.connectors.cloudflare import sync_cloudflare
from app.connectors.pagespeed import sync_pagespeed, ensure_pagespeed_datasource
from app.connectors.bing import sync_bing
from app.connectors.hubspot import sync_hubspot
from app.connectors.ads_csv import sync_ads_csv
from app.connectors.google_ads import sync_google_ads
from app.connectors.meta_ads import sync_meta_ads
from app.connectors.gbp import sync_gbp
from app.connectors.backlinks import sync_backlinks
from app.connectors.clarity import sync_clarity, ensure_clarity_datasource
from app.connectors.crux import sync_crux, ensure_crux_datasource, sync_crux_for_client
from app.connectors.site_crawl import ensure_crawl_for_client
from app.connectors.serp import ensure_serp_for_flagged_queries, serp_enabled
from app.insight_service import generate_insights_for_client
from app.ai_summarizer import generate_weekly_summary
from app.impact_tracker import run_due_impact_rechecks
from app.success_report import run_monthly_reports_for_all_clients
from app.timeutil import utcnow

logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler(timezone="UTC")

# Retry these statuses on schedule (error/partial/reauth were stuck forever before).
# Do not hammer reauth_required — operator must reconnect before sync resumes.
_SYNC_RETRY_STATUSES = ("active", "pending", "error", "partial")

SYNC_MAP = {
    "gsc": sync_gsc,
    "ga4": sync_ga4,
    "cloudflare": sync_cloudflare,
    "clarity": sync_clarity,
    "pagespeed": sync_pagespeed,
    "bing": sync_bing,
    "hubspot": sync_hubspot,
    "ads_csv": sync_ads_csv,
    "google_ads": sync_google_ads,
    "meta_ads": sync_meta_ads,
    "gbp": sync_gbp,
    "backlinks": sync_backlinks,
    "crux": sync_crux,
}


def start_job_run(db: Session, job_type: str) -> JobRun:
    """Create a JobRun row at job start."""
    run = JobRun(
        job_type=job_type,
        started_at=utcnow(),
        ok=None,
        error=None,
        summary_json="{}",
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def finish_job_run(
    db: Session,
    run: JobRun,
    *,
    ok: bool,
    error: Optional[str] = None,
    summary: Optional[dict[str, Any]] = None,
) -> JobRun:
    """Mark a JobRun finished with outcome."""
    run.finished_at = utcnow()
    run.ok = bool(ok)
    run.error = (error or None)
    if error and len(run.error or "") > 2000:
        run.error = run.error[-2000:]
    run.summary_json = json.dumps(summary or {})
    db.commit()
    db.refresh(run)
    return run


def _active_clients(db: Session) -> list[Client]:
    return (
        db.query(Client)
        .filter((Client.archived == False) | (Client.archived.is_(None)))  # noqa: E712
        .all()
    )


def _archived_client_ids(db: Session) -> set[int]:
    rows = (
        db.query(Client.id)
        .filter(Client.archived == True)  # noqa: E712
        .all()
    )
    return {r[0] for r in rows}


def run_all_syncs():
    logger.info("Starting scheduled sync for all active data sources...")
    db = SessionLocal()
    run = start_job_run(db, "daily_sync")
    synced = 0
    failed = 0
    clients_touched: set[int] = set()
    try:
        archived = _archived_client_ids(db)

        # Auto-wire PageSpeed / Clarity / CrUX from Settings for every non-archived client
        for client in _active_clients(db):
            try:
                ensure_pagespeed_datasource(db, client.id)
            except Exception as e:
                logger.warning("PageSpeed auto-wire failed for client %s: %s", client.id, e)
            try:
                ensure_clarity_datasource(db, client.id)
            except Exception as e:
                logger.warning("Clarity auto-wire failed for client %s: %s", client.id, e)
            try:
                # Only auto-create CrUX when a PageSpeed key exists — otherwise
                # every client shows a red "need attention" with no fix available yet.
                from app.connectors.crux import _settings_api_key

                if _settings_api_key(db):
                    ensure_crux_datasource(db, client.id)
            except Exception as e:
                logger.warning("CrUX auto-wire failed for client %s: %s", client.id, e)
        db.commit()

        sources = (
            db.query(DataSource)
            .filter(DataSource.status.in_(list(_SYNC_RETRY_STATUSES)))
            .all()
        )
        work: list[tuple[int, str, int]] = []
        for ds in sources:
            if ds.client_id in archived:
                continue
            if ds.type not in SYNC_MAP:
                logger.warning(f"Unknown source type {ds.type} for DataSource {ds.id}")
                continue
            work.append((ds.id, ds.type, ds.client_id))

        # Bounded parallel sync — each worker uses its own Session (SQLite-safe with WAL).
        # Crawl / insights / SERP stay sequential below (heavier writers).
        from concurrent.futures import ThreadPoolExecutor, as_completed

        def _sync_one(item: tuple[int, str, int]) -> tuple[bool, int, str | None]:
            ds_id, ds_type, client_id = item
            sync_fn = SYNC_MAP[ds_type]
            worker_db = SessionLocal()
            try:
                ds = worker_db.query(DataSource).filter(DataSource.id == ds_id).first()
                if not ds:
                    return False, client_id, f"DataSource {ds_id} missing"
                try:
                    ok = bool(sync_fn(ds))
                    return ok, client_id, None
                except Exception as e:
                    from app.credentials import CredentialsDecryptError
                    from app.ds_status import mark_reauth_required

                    if isinstance(e, CredentialsDecryptError):
                        logger.error(
                            "Sync decrypt failed for DataSource %s (%s): %s",
                            ds_id,
                            ds_type,
                            e,
                        )
                        try:
                            mark_reauth_required(ds, str(e))
                            worker_db.merge(ds)
                            worker_db.commit()
                        except Exception:
                            worker_db.rollback()
                    else:
                        logger.error(
                            "Sync failed for DataSource %s (%s): %s",
                            ds_id,
                            ds_type,
                            e,
                        )
                    return False, client_id, str(e)
            finally:
                worker_db.close()

        max_workers = min(4, max(1, len(work)))
        if work:
            with ThreadPoolExecutor(max_workers=max_workers) as pool:
                futures = [pool.submit(_sync_one, item) for item in work]
                for fut in as_completed(futures):
                    try:
                        ok, client_id, _err = fut.result()
                    except Exception as e:
                        failed += 1
                        logger.error("Sync worker crashed: %s", e)
                        continue
                    if ok:
                        synced += 1
                        clients_touched.add(client_id)
                    else:
                        failed += 1

        for client_id in clients_touched:
            try:
                ensure_crawl_for_client(db, client_id, max_pages=25)
            except Exception as e:
                logger.warning("Site crawl failed for client %s: %s", client_id, e)
            try:
                sync_crux_for_client(db, client_id)
            except Exception as e:
                logger.warning("CrUX sync failed for client %s: %s", client_id, e)
            try:
                generate_insights_for_client(db, client_id)
            except Exception as e:
                logger.error(f"Insight generation failed for client {client_id}: {e}")
            try:
                if serp_enabled():
                    ensure_serp_for_flagged_queries(db, client_id)
                    from app.connectors.sov import write_sov_presence

                    write_sov_presence(db, client_id)
            except Exception as e:
                logger.warning("SERP refresh failed for client %s: %s", client_id, e)

        finish_job_run(
            db,
            run,
            ok=failed == 0 or synced > 0,
            summary={
                "synced": synced,
                "failed": failed,
                "clients": len(clients_touched),
                "workers": max_workers if work else 0,
            },
        )
    except Exception as e:
        logger.exception("Scheduled sync job crashed: %s", e)
        try:
            finish_job_run(db, run, ok=False, error=str(e)[:2000])
        except Exception:
            db.rollback()
    finally:
        db.close()
    logger.info("Scheduled sync complete.")


def run_weekly_summaries():
    logger.info("Starting weekly AI summaries for all clients...")
    db = SessionLocal()
    run = start_job_run(db, "weekly_summaries")
    ok_count = 0
    fail_count = 0
    try:
        for client in _active_clients(db):
            try:
                generate_weekly_summary(client.id)
                ok_count += 1
            except Exception as e:
                fail_count += 1
                logger.error(f"Weekly summary failed for client {client.id}: {e}")
        finish_job_run(
            db,
            run,
            ok=fail_count == 0,
            summary={"ok": ok_count, "failed": fail_count},
            error=None if fail_count == 0 else f"{fail_count} client summary failure(s)",
        )
    except Exception as e:
        logger.exception("Weekly summaries job crashed: %s", e)
        try:
            finish_job_run(db, run, ok=False, error=str(e)[:2000])
        except Exception:
            db.rollback()
    finally:
        db.close()
    logger.info("Weekly summaries complete.")


def run_impact_rechecks():
    logger.info("Starting scheduled impact rechecks...")
    db = SessionLocal()
    run = start_job_run(db, "daily_impact_recheck")
    try:
        result = run_due_impact_rechecks()
        finish_job_run(db, run, ok=True, summary=result if isinstance(result, dict) else {})
        logger.info(f"Impact rechecks complete: {result}")
    except Exception as e:
        logger.error(f"Impact recheck job failed: {e}")
        try:
            finish_job_run(db, run, ok=False, error=str(e)[:2000])
        except Exception:
            db.rollback()
    finally:
        db.close()


def run_monthly_reports():
    logger.info("Starting monthly client reports...")
    db = SessionLocal()
    run = start_job_run(db, "monthly_reports")
    try:
        result = run_monthly_reports_for_all_clients()
        finish_job_run(
            db,
            run,
            ok=True,
            summary=result if isinstance(result, dict) else {"result": str(result)},
        )
        logger.info(f"Monthly reports complete: {result}")
    except Exception as e:
        logger.error(f"Monthly report job failed: {e}")
        try:
            finish_job_run(db, run, ok=False, error=str(e)[:2000])
        except Exception:
            db.rollback()
    finally:
        db.close()


def start_scheduler():
    scheduler.add_job(
        run_all_syncs,
        "cron",
        hour=3,
        minute=0,
        timezone="UTC",
        id="daily_sync",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        run_weekly_summaries,
        "cron",
        day_of_week="mon",
        hour=5,
        minute=0,
        timezone="UTC",
        id="weekly_summaries",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        run_impact_rechecks,
        "cron",
        hour=6,
        minute=0,
        timezone="UTC",
        id="daily_impact_recheck",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        run_monthly_reports,
        "cron",
        day=1,
        hour=7,
        minute=0,
        timezone="UTC",
        id="monthly_reports",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        run_seasonality_build,
        "cron",
        day_of_week="sun",
        hour=4,
        minute=0,
        timezone="UTC",
        id="weekly_seasonality",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        run_proof_nag,
        "cron",
        hour=8,
        minute=0,
        timezone="UTC",
        id="daily_proof_nag",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()
    logger.info(
        "Scheduler started (daily sync 03:00, weekly summaries Mon 05:00, "
        "impact recheck 06:00, monthly reports 1st 07:00, "
        "seasonality Sun 04:00, proof nag 08:00 UTC)"
    )


def run_seasonality_build():
    """Weekly job: rebuild 52-week seasonal baselines for every client with >= 6 months of data."""
    from app.seasonality_engine import compute_seasonality_baseline
    from app.dimensions import SITE_TOTAL_DIMENSION

    db = SessionLocal()
    run = start_job_run(db, "seasonality_build")
    try:
        clients = _active_clients(db)
        stored = 0
        for client in clients:
            for metric in ("clicks", "impressions", "sessions"):
                try:
                    n = compute_seasonality_baseline(
                        db, client.id, "gsc" if metric != "sessions" else "ga4",
                        metric, years_back=2,
                        dimension_type=SITE_TOTAL_DIMENSION.get("gsc" if metric != "sessions" else "ga4"),
                    )
                    stored += n
                except Exception:
                    logger.warning("Seasonality build failed for client %s metric %s", client.id, metric, exc_info=True)
        finish_job_run(db, run, ok=True, summary={"clients": len(clients), "weeks_stored": stored})
        if stored:
            logger.info("Seasonality baseline built: %d weeks across %d clients", stored, len(clients))
    except Exception as e:
        finish_job_run(db, run, ok=False, error=str(e))
        logger.error("Seasonality build failed: %s", e)
    finally:
        db.close()


def run_proof_nag():
    """Daily job: find tasks awaiting recheck and stuck growth levers."""
    from app.proof_nag import run_pending_proof_check

    db = SessionLocal()
    run = start_job_run(db, "proof_nag")
    try:
        result = run_pending_proof_check(db)
        finish_job_run(db, run, ok=True, summary=result)
        if result.get("total", 0):
            logger.info(
                "Proof nag: %d tasks awaiting recheck, %d stuck levers",
                result.get("pending_recheck_count", 0),
                result.get("stuck_levers_count", 0),
            )
    except Exception as e:
        finish_job_run(db, run, ok=False, error=str(e))
        logger.error("Proof nag failed: %s", e)
    finally:
        db.close()
