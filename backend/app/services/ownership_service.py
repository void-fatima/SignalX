"""404 for both absent and foreign resources; historical unassigned rows stay private."""
from sqlalchemy import select

from app.core.errors import AppError
from app.models import AnalysisRun, ImportBatch, Product


def owned(session, model, resource_id, user_id):
    row = session.scalar(select(model).where(model.id == str(resource_id), model.owner_user_id == str(user_id)))
    if row is None:
        raise AppError("not_found", "Record does not exist", 404)
    return row


def owned_run(session, run_id, user_id):
    row = session.scalar(select(AnalysisRun).join(Product).join(ImportBatch, AnalysisRun.batch_id == ImportBatch.id).where(
        AnalysisRun.id == str(run_id), Product.owner_user_id == str(user_id), ImportBatch.owner_user_id == str(user_id)))
    if row is None:
        raise AppError("not_found", "Record does not exist", 404)
    return row
