import logging
import time
from app.core.config import settings
from app.db.session import SessionLocal
from app.agents.pipeline import get_provider
from app.services.analysis_service import process_one, recover_interrupted


def main():
    logging.basicConfig(level=logging.INFO)
    get_provider(settings().provider_mode)
    recover_interrupted(SessionLocal)
    logging.info("singnalX single worker started: provider_mode=%s", settings().provider_mode)
    while True:
        if not process_one(SessionLocal):
            recover_interrupted(SessionLocal)
            time.sleep(settings().worker_poll_seconds)


if __name__ == "__main__":
    main()
