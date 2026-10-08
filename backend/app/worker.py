import logging
import time
from sqlalchemy.exc import SQLAlchemyError
from app.core.config import settings
from app.db.session import SessionLocal
from app.agents.orchestrator import analyze_agent
from app.agents.pipeline import get_provider
from app.auth.service import cleanup_stale_sessions
from app.models import utcnow
from app.services.analysis_service import process_one, recover_interrupted


SESSION_CLEANUP_INTERVAL_SECONDS = 3600


def main():
    logging.basicConfig(level=logging.INFO)
    get_provider(settings().provider_mode)
    last_session_cleanup = 0.0
    logging.info("singnalX single worker started: provider_mode=%s", settings().provider_mode)
    while True:
        try:
            now = time.monotonic()
            if now - last_session_cleanup >= SESSION_CLEANUP_INTERVAL_SECONDS:
                with SessionLocal() as session:
                    removed = cleanup_stale_sessions(session, utcnow())
                    session.commit()
                if removed:
                    logging.info("Removed %s expired or revoked sessions", removed)
                last_session_cleanup = now
            worked = process_one(SessionLocal, agent_orchestrator=analyze_agent)
            if not worked:
                recover_interrupted(SessionLocal)
        except SQLAlchemyError:
            # Driver exceptions can include DSNs, query parameters, or user data.
            logging.error("Worker database unavailable; saved jobs will be recovered after reconnection")
            worked = False
        if not worked:
            time.sleep(settings().worker_poll_seconds)


if __name__ == "__main__":
    main()
