import logging
import time
from sqlalchemy.exc import SQLAlchemyError
from app.core.config import settings
from app.db.session import SessionLocal
from app.agents.pipeline import get_provider
from app.services.analysis_service import process_one, recover_interrupted


def main():
    logging.basicConfig(level=logging.INFO)
    get_provider(settings().provider_mode)
    logging.info("singnalX single worker started: provider_mode=%s", settings().provider_mode)
    while True:
        try:
            recover_interrupted(SessionLocal)
            worked = process_one(SessionLocal)
        except SQLAlchemyError:
            # No exception text/SQL parameters: connection failures may contain credentials.
            logging.error("Worker database unavailable; saved jobs will be recovered after reconnection")
            worked = False
        if not worked:
            time.sleep(settings().worker_poll_seconds)


if __name__ == "__main__":
    main()
