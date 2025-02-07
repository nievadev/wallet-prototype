import logging

from celery import shared_task
from django.db import transaction
from django.db.models import Q
from django.utils.timezone import now as utcnow

from wallet_base.models import WalletExtractionRequest, WalletTransaction

logger = logging.getLogger("wallet")


def _update_transactions():
    now = utcnow()

    with transaction.atomic():
        matched_number_expired = WalletTransaction.objects.filter(
            status=WalletTransaction.STATUS_AVAILABLE,
            datetime_expiration__lt=now,
        ).update(status=WalletTransaction.STATUS_EXPIRED)

        matched_number_available = WalletTransaction.objects.filter(
            status=WalletTransaction.STATUS_PENDING,
            amount__gte=0,
            datetime_available__lt=now,
        ).update(status=WalletTransaction.STATUS_AVAILABLE)

    logger.debug(f"expired {matched_number_expired}")
    logger.debug(f"made available {matched_number_available}")

    transaction_q = WalletTransaction.objects.filter(
        status=WalletTransaction.STATUS_PENDING,
        amount__lt=0,
        datetime_available__lt=now,
    )

    for transaction_pending in transaction_q:
        logger.debug(f"processing transaction_pending={transaction_pending.id}")
        current_now = utcnow()

        with transaction.atomic():
            matched_number_transaction = WalletTransaction.objects.filter(
                Q(
                    datetime_available__lt=transaction_pending.datetime_added,
                    wallet_id=transaction_pending.wallet_id,
                    status=WalletTransaction.STATUS_AVAILABLE,
                )
                | Q(id=transaction_pending.id)
            ).update(
                status=WalletTransaction.STATUS_PROCESSED,
                object_id=transaction_pending.id,
                object_name="wallet_wallettransaction",
            )

            matched_number_request = (
                transaction_pending.walletextractionrequest_set.update(
                    status=WalletExtractionRequest.STATUS_PROCESSED,
                    datetime_resolution=current_now,
                )
            )

        logger.debug(f"processed {matched_number_transaction}")
        logger.debug(f"processed requests {matched_number_request}")


@shared_task(ignore_result=True)
def update_transactions():
    """Task to be configured to run periodically e.g. using cron or django celery beat."""

    logger.info("update transactions STARTED")

    try:
        _update_transactions()
    except Exception:
        logger.exception("update transactions ERROR")
        return

    logger.info("update transactions DONE")
