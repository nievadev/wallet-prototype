import os

from django.conf import settings
from django.contrib.auth.models import User
from django.core.cache import cache
from django.test.testcases import TestCase
from django.urls import reverse
from django.utils.timezone import now as utcnow
from rest_framework import status
from rest_framework.test import APIClient

from wallet_base.models import (
    Wallet,
    WalletExtractionRequest,
    WalletTransaction,
)
from wallet_base.tasks import update_transactions


class WalletTaskTestCase(TestCase):
    fixture_base = os.path.join(
        settings.BASE_DIR, "wallet_base", "tests", "initial_data"
    )
    fixtures = [
        os.path.join(fixture_base, "user.json"),
        os.path.join(fixture_base, "wallet.json"),
    ]

    def setUp(self):
        cache.clear()
        self.client = APIClient()

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = User.objects.all()[0]
        cls.user.set_password("1234")
        cls.user.save()

    def login(self):
        response = self.client.post(
            reverse("wallet-login"),
            dict(username=self.user.username, password="1234"),
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Token {response.data['token']}"
        )

    def test_nothing_happens(self):
        wallet = Wallet.objects.get(code="123")
        transaction = wallet.add_available(999)
        self.assertEqual(transaction.status, WalletTransaction.STATUS_AVAILABLE)
        update_transactions()
        transaction.refresh_from_db()
        self.assertEqual(transaction.status, WalletTransaction.STATUS_AVAILABLE)

    def test_expired(self):
        wallet = Wallet.objects.get(code="123")
        transaction = wallet.add_available(999, expiration_delta_years=0)
        self.assertEqual(transaction.status, WalletTransaction.STATUS_AVAILABLE)
        update_transactions()
        transaction.refresh_from_db()
        self.assertEqual(transaction.status, WalletTransaction.STATUS_EXPIRED)

    def test_not_expired(self):
        wallet = Wallet.objects.get(code="123")
        transaction = wallet.add_available(999, expiration_delta_years=1)
        self.assertEqual(transaction.status, WalletTransaction.STATUS_AVAILABLE)
        update_transactions()
        transaction.refresh_from_db()
        self.assertEqual(transaction.status, WalletTransaction.STATUS_AVAILABLE)

    def test_available(self):
        wallet = Wallet.objects.get(code="123")
        transaction = wallet.add_pending(999)
        self.assertEqual(transaction.status, WalletTransaction.STATUS_PENDING)
        update_transactions()
        transaction.refresh_from_db()
        self.assertEqual(transaction.status, WalletTransaction.STATUS_AVAILABLE)

    def test_not_available(self):
        wallet = Wallet.objects.get(code="123")
        transaction = wallet.add_pending(999, available_delta_days=1)
        self.assertEqual(transaction.status, WalletTransaction.STATUS_PENDING)
        update_transactions()
        transaction.refresh_from_db()
        self.assertEqual(transaction.status, WalletTransaction.STATUS_PENDING)

    def test_not_processed_extraction(self):
        self.login()
        self.client.post(
            reverse("wallet:request-list"),
            {
                "payment_type": "alias",
                "nro": "martin.nieva.test",
            },
        )
        wallet_transaction = WalletTransaction.objects.last()
        extraction_count = (
            wallet_transaction.walletextractionrequest_set.count()
        )
        update_transactions()
        wallet_transaction.refresh_from_db()
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
        self.login()
        self.client.post(
            reverse("wallet:request-list"),
            {
                "payment_type": "alias",
                "nro": "martin.nieva.test",
            },
        )
        wallet_transaction = WalletTransaction.objects.last()
        wallet_transaction.datetime_available = utcnow()
        wallet_transaction.save()
        extraction_count = (
            wallet_transaction.walletextractionrequest_set.count()
        )
        update_transactions()
        wallet_transaction.refresh_from_db()
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
        wallet = Wallet.objects.get(code="123")
        transaction = wallet.add_pending(999)
        self.login()
        self.client.post(
            reverse("wallet:request-list"),
            {
                "payment_type": "alias",
                "nro": "martin.nieva.test",
            },
        )
        wallet_transaction = WalletTransaction.objects.last()
        wallet_transaction.datetime_available = utcnow()
        wallet_transaction.save()
        extraction_count = (
            wallet_transaction.walletextractionrequest_set.count()
        )
        update_transactions()
        wallet_transaction.refresh_from_db()
        transaction.refresh_from_db()
        self.assertEqual(
            wallet_transaction.status, WalletTransaction.STATUS_PROCESSED
        )
        self.assertEqual(
            wallet_transaction.walletextractionrequest_set.filter(
                status=WalletExtractionRequest.STATUS_PROCESSED
            ).count(),
            extraction_count,
        )
        self.assertEqual(transaction.status, WalletTransaction.STATUS_PROCESSED)

    def test_processed_extraction_but_not_processed_other_pending(self):
        self.login()
        self.client.post(
            reverse("wallet:request-list"),
            {
                "payment_type": "alias",
                "nro": "martin.nieva.test",
            },
        )
        wallet_transaction = WalletTransaction.objects.last()
        wallet_transaction.datetime_available = utcnow()
        wallet_transaction.save()
        wallet = Wallet.objects.get(code="123")
        transaction = wallet.add_pending(999)
        extraction_count = (
            wallet_transaction.walletextractionrequest_set.count()
        )
        update_transactions()
        wallet_transaction.refresh_from_db()
        transaction.refresh_from_db()
        self.assertEqual(
            wallet_transaction.status, WalletTransaction.STATUS_PROCESSED
        )
        self.assertEqual(
            wallet_transaction.walletextractionrequest_set.filter(
                status=WalletExtractionRequest.STATUS_PROCESSED
            ).count(),
            extraction_count,
        )
        self.assertEqual(transaction.status, WalletTransaction.STATUS_AVAILABLE)

    def test_processed_extraction_but_not_processed_other_available(self):
        self.login()
        self.client.post(
            reverse("wallet:request-list"),
            {
                "payment_type": "alias",
                "nro": "martin.nieva.test",
            },
        )
        wallet_transaction = WalletTransaction.objects.last()
        wallet_transaction.datetime_available = utcnow()
        wallet_transaction.save()
        wallet = Wallet.objects.get(code="123")
        transaction = wallet.add_available(999)
        extraction_count = (
            wallet_transaction.walletextractionrequest_set.count()
        )
        update_transactions()
        wallet_transaction.refresh_from_db()
        transaction.refresh_from_db()
        self.assertEqual(
            wallet_transaction.status, WalletTransaction.STATUS_PROCESSED
        )
        self.assertEqual(
            wallet_transaction.walletextractionrequest_set.filter(
                status=WalletExtractionRequest.STATUS_PROCESSED
            ).count(),
            extraction_count,
        )
        self.assertEqual(transaction.status, WalletTransaction.STATUS_AVAILABLE)
