import os
from unittest import mock

from django.conf import settings
from django.test.testcases import TestCase
from django.utils.timezone import now as utcnow
from django.utils.timezone import timedelta

from wallet_base.models import WalletExtractionRequest, WalletTransaction
from wallet_base.tasks import update_transactions


class WalletTaskTestCase(TestCase):
    fixture_base = os.path.join(
        settings.BASE_DIR, "wallet_base", "tests", "initial_data"
    )
    fixtures = [
        os.path.join(fixture_base, "user.json"),
        os.path.join(fixture_base, "wallet.json"),
    ]

    def test_nothing_happens(self):
        update_transactions()
        wallet_transaction = WalletTransaction.objects.get(code="555")
        self.assertEqual(
            wallet_transaction.status, WalletTransaction.STATUS_AVAILABLE
        )

    def test_expired(self):
        wallet_transaction = WalletTransaction.objects.get(code="555")
        wallet_transaction.datetime_expiration = utcnow()
        wallet_transaction.save()
        update_transactions()
        wallet_transaction = WalletTransaction.objects.get(code="555")
        self.assertEqual(
            wallet_transaction.status, WalletTransaction.STATUS_EXPIRED
        )

    def test_not_expired(self):
        wallet_transaction = WalletTransaction.objects.get(code="555")
        wallet_transaction.datetime_expiration = utcnow() + timedelta(hours=1)
        wallet_transaction.save()
        update_transactions()
        wallet_transaction = WalletTransaction.objects.get(code="555")
        self.assertEqual(
            wallet_transaction.status, WalletTransaction.STATUS_AVAILABLE
        )

    def test_available(self):
        wallet_transaction = WalletTransaction.objects.get(code="555")
        wallet_transaction.datetime_available = utcnow()
        wallet_transaction.status = WalletTransaction.STATUS_PENDING
        wallet_transaction.save()
        update_transactions()
        wallet_transaction = WalletTransaction.objects.get(code="555")
        self.assertEqual(
            wallet_transaction.status, WalletTransaction.STATUS_AVAILABLE
        )

    def test_not_available(self):
        wallet_transaction = WalletTransaction.objects.get(code="555")
        wallet_transaction.datetime_available = utcnow() + timedelta(hours=1)
        wallet_transaction.status = WalletTransaction.STATUS_PENDING
        wallet_transaction.save()
        update_transactions()
        wallet_transaction = WalletTransaction.objects.get(code="555")
        self.assertEqual(
            wallet_transaction.status, WalletTransaction.STATUS_PENDING
        )

    def test_not_processed_extraction(self):
        wallet_transaction = WalletTransaction.objects.get(code="555")
        wallet_transaction.datetime_available = utcnow() + timedelta(hours=1)
        wallet_transaction.status = WalletTransaction.STATUS_PENDING
        wallet_transaction.amount = -1
        wallet_transaction.save()
        wallet_transaction.walletextractionrequest_set.update(
            status=WalletExtractionRequest.STATUS_PENDING
        )
        extraction_count = (
            wallet_transaction.walletextractionrequest_set.count()
        )
        update_transactions()
        wallet_transaction = WalletTransaction.objects.get(code="555")
        self.assertEqual(
            wallet_transaction.status, WalletTransaction.STATUS_PENDING
        )
        self.assertEqual(
            wallet_transaction.walletextractionrequest_set.filter(
                status=WalletExtractionRequest.STATUS_PENDING
            ).count(),
            extraction_count,
        )

    def test_processed_extraction(self):
        wallet_transaction = WalletTransaction.objects.get(code="555")
        wallet_transaction.datetime_available = utcnow()
        wallet_transaction.datetime_added = utcnow()
        wallet_transaction.status = WalletTransaction.STATUS_PENDING
        wallet_transaction.amount = -1
        wallet_transaction.save()
        wallet_transaction.walletextractionrequest_set.update(
            status=WalletExtractionRequest.STATUS_PENDING
        )
        extraction_count = (
            wallet_transaction.walletextractionrequest_set.count()
        )
        update_transactions()
        wallet_transaction = WalletTransaction.objects.get(code="555")
        self.assertEqual(
            wallet_transaction.status, WalletTransaction.STATUS_PROCESSED
        )
        self.assertEqual(
            wallet_transaction.walletextractionrequest_set.filter(
                status=WalletExtractionRequest.STATUS_PROCESSED
            ).count(),
            extraction_count,
        )

    def test_processed_extraction_and_available(self):
        wallet_transaction = WalletTransaction.objects.get(code="xxxx")
        wallet_transaction.datetime_available = utcnow()
        wallet_transaction.datetime_added = utcnow()
        wallet_transaction.status = WalletTransaction.STATUS_PENDING
        wallet_transaction.save()
        wallet_transaction = WalletTransaction.objects.get(code="555")
        wallet_transaction.datetime_available = utcnow()
        wallet_transaction.datetime_added = utcnow()
        wallet_transaction.status = WalletTransaction.STATUS_PENDING
        wallet_transaction.amount = -1
        wallet_transaction.save()
        wallet_transaction.walletextractionrequest_set.update(
            status=WalletExtractionRequest.STATUS_PENDING
        )
        extraction_count = (
            wallet_transaction.walletextractionrequest_set.count()
        )
        update_transactions()
        wallet_transaction = WalletTransaction.objects.get(code="555")
        self.assertEqual(
            wallet_transaction.status, WalletTransaction.STATUS_PROCESSED
        )
        self.assertEqual(
            wallet_transaction.walletextractionrequest_set.filter(
                status=WalletExtractionRequest.STATUS_PROCESSED
            ).count(),
            extraction_count,
        )
        wallet_transaction = WalletTransaction.objects.get(code="xxxx")
        self.assertEqual(
            wallet_transaction.status, WalletTransaction.STATUS_PROCESSED
        )

    def test_processed_extraction_but_not_processed_other_pending(self):
        wallet_transaction = WalletTransaction.objects.get(code="xxxx")
        wallet_transaction.datetime_available = utcnow()
        wallet_transaction.datetime_added = utcnow()
        wallet_transaction.status = WalletTransaction.STATUS_PENDING
        wallet_transaction.save()
        wallet_transaction = WalletTransaction.objects.get(code="555")
        wallet_transaction.datetime_available = utcnow()
        wallet_transaction.datetime_added = utcnow() - timedelta(hours=1)
        wallet_transaction.status = WalletTransaction.STATUS_PENDING
        wallet_transaction.amount = -1
        wallet_transaction.save()
        wallet_transaction.walletextractionrequest_set.update(
            status=WalletExtractionRequest.STATUS_PENDING
        )
        extraction_count = (
            wallet_transaction.walletextractionrequest_set.count()
        )
        update_transactions()
        wallet_transaction = WalletTransaction.objects.get(code="555")
        self.assertEqual(
            wallet_transaction.status, WalletTransaction.STATUS_PROCESSED
        )
        self.assertEqual(
            wallet_transaction.walletextractionrequest_set.filter(
                status=WalletExtractionRequest.STATUS_PROCESSED
            ).count(),
            extraction_count,
        )
        wallet_transaction = WalletTransaction.objects.get(code="xxxx")
        self.assertEqual(
            wallet_transaction.status, WalletTransaction.STATUS_AVAILABLE
        )

    def test_processed_extraction_but_not_processed_other_available(self):
        wallet_transaction = WalletTransaction.objects.get(code="xxxx")
        wallet_transaction.datetime_available = utcnow()
        wallet_transaction.datetime_added = utcnow()
        wallet_transaction.status = WalletTransaction.STATUS_AVAILABLE
        wallet_transaction.save()
        wallet_transaction = WalletTransaction.objects.get(code="555")
        wallet_transaction.datetime_available = utcnow()
        wallet_transaction.datetime_added = utcnow() - timedelta(hours=1)
        wallet_transaction.status = WalletTransaction.STATUS_PENDING
        wallet_transaction.amount = -1
        wallet_transaction.save()
        wallet_transaction.walletextractionrequest_set.update(
            status=WalletExtractionRequest.STATUS_PENDING
        )
        extraction_count = (
            wallet_transaction.walletextractionrequest_set.count()
        )
        update_transactions()
        wallet_transaction = WalletTransaction.objects.get(code="555")
        self.assertEqual(
            wallet_transaction.status, WalletTransaction.STATUS_PROCESSED
        )
        self.assertEqual(
            wallet_transaction.walletextractionrequest_set.filter(
                status=WalletExtractionRequest.STATUS_PROCESSED
            ).count(),
            extraction_count,
        )
        wallet_transaction = WalletTransaction.objects.get(code="xxxx")
        self.assertEqual(
            wallet_transaction.status, WalletTransaction.STATUS_AVAILABLE
        )

    @mock.patch("wallet_base.tasks.tasks.logger")
    def test_logger_match(self, logger_mock):
        wallet_transaction = WalletTransaction.objects.get(code="555")
        wallet_transaction.datetime_available = utcnow()
        wallet_transaction.status = WalletTransaction.STATUS_PENDING
        wallet_transaction.amount = -1
        wallet_transaction.save()
        update_transactions()
        self.assertEqual(logger_mock.debug.call_count, 5)
        self.assertEqual(logger_mock.info.call_count, 2)

    @mock.patch("wallet_base.tasks.tasks.logger")
    def test_logger_no_match(self, logger_mock):
        update_transactions()
        self.assertEqual(logger_mock.debug.call_count, 2)
        self.assertEqual(logger_mock.info.call_count, 2)
