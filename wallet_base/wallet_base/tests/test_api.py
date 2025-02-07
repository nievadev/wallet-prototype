import os
from unittest import mock

from django.conf import settings
from django.contrib.auth.models import User
from django.core.cache import cache
from django.test.testcases import TestCase
from django.urls import reverse
from django.utils.timezone import now as utcnow
from django.utils.timezone import timedelta
from rest_framework import status
from rest_framework.test import APIClient

from wallet_base.models import (
    LeadPayment,
    Wallet,
    WalletExtractionRequest,
    WalletTransaction,
)


class WalletTestCase(TestCase):
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
        cls.test_datetime_utcnow = utcnow()
        cls.test_datetime = cls.test_datetime_utcnow + timedelta(days=1)
        WalletTransaction.objects.filter(code="555").update(
            datetime_added=cls.test_datetime_utcnow,
            datetime_available=cls.test_datetime,
            datetime_expiration=cls.test_datetime,
        )
        cls.user = User.objects.all()[0]
        cls.user.set_password("test")
        cls.user.save()

    def login(self):
        response = self.client.post(
            reverse("wallet-login"),
            {"username": self.user.username, "password": "test"},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Token {response.data['token']}"
        )

    def test_transaction_list(self):
        self.login()
        response = self.client.get(reverse("wallet:transaction-list"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response_data = response.json()
        self.assertEqual(len(response_data["object_list"]), 1)
        self.assertEqual(response_data["object_list"][0]["status"], "a")
        self.assertEqual(response_data["object_list"][0]["currency"], "ARS")
        self.assertEqual(response_data["object_list"][0]["amount"], 12000.0)
        self.assertTrue(
            response_data["object_list"][0]["datetime_available"].startswith(
                self.test_datetime.isoformat()[:11]
            )
        )
        self.assertTrue(
            response_data["object_list"][0]["datetime_expiration"].startswith(
                self.test_datetime.isoformat()[:11]
            )
        )
        self.assertIs(response_data["page_size"], 50)
        self.assertIs(response_data["count"], 1)
        self.assertIs(response_data["num_pages"], 1)

    def test_transaction_list_object_serialized(self):
        self.login()
        response = self.client.get(reverse("wallet:transaction-list"))
        response_data = response.json()
        self.assertEqual(
            response_data["object_list"][0]["object_serialized"], None
        )
        WalletTransaction.objects.filter(code="555").update(
            object_name="wallet_wallet",
        )
        response = self.client.get(reverse("wallet:transaction-list"))
        response_data = response.json()
        self.assertEqual(
            response_data["object_list"][0]["object_serialized"], None
        )
        transaction_base = WalletTransaction.objects.get(code="555")
        transaction_base.id = None
        transaction_base.code = "234"
        transaction_base.amount = -456789.116
        transaction_base.save()
        WalletTransaction.objects.filter(code="555").update(
            object_name="wallet_wallettransaction",
            object_id=transaction_base.id,
        )
        response = self.client.get(reverse("wallet:transaction-list"))
        response_data = response.json()
        self.assertIsInstance(
            response_data["object_list"][1]["object_serialized"], dict
        )
        self.assertEqual(
            response_data["object_list"][1]["object_serialized"][
                "datetime_added"
            ],
            transaction_base.datetime_added.isoformat().replace("+00:00", "Z"),
        )
        self.assertEqual(
            response_data["object_list"][1]["object_serialized"]["amount"],
            -456789.116,
        )

    def test_transaction_exclude_cancelled(self):
        self.login()
        WalletTransaction.objects.filter(code="555").update(
            status=WalletTransaction.STATUS_CANCELLED,
        )
        response = self.client.get(reverse("wallet:transaction-list"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response_data = response.json()["object_list"]
        self.assertIsInstance(response_data, list)
        self.assertEqual(len(response_data), 0)

    def test_wallet_sum_null_by_exclude(self):
        self.login()
        WalletTransaction.objects.filter(code="555").update(
            status=WalletTransaction.STATUS_PENDING,
        )
        response_data = self.client.get(
            reverse("wallet:wallet-detail", args=["x"])
        ).json()
        self.assertEqual(response_data["available"], 0.0)

    def test_wallet_sum_null_by_empty(self):
        self.login()
        WalletExtractionRequest.objects.all().delete()
        WalletTransaction.objects.all().delete()
        response_data = self.client.get(
            reverse("wallet:wallet-detail", args=["x"])
        ).json()
        self.assertEqual(response_data["available"], 0.0)

    def test_wallet_alias(self):
        self.login()

        wallet = Wallet.objects.select_related("payment").get(code="123")
        wallet.payment = LeadPayment()
        wallet.payment.nro = "345dfs"
        wallet.payment.payment_type = LeadPayment.PAYMENT_TYPE_ALIAS
        wallet.payment.user = self.user
        wallet.payment.save()
        wallet.save()

        self.client.post(
            reverse("wallet:request-list"),
            {
                "payment_type": "alias",
                "nro": "martin.nieva.test",
            },
        )
        response_data = self.client.get(
            reverse("wallet:wallet-detail", args=["x"])
        ).json()
        self.assertEqual(response_data["current_payment_nro"], "marti")
        self.assertEqual(response_data["current_payment_type"], "alias")

        last_transaction = WalletTransaction.objects.order_by(
            "-datetime_added"
        ).first()
        last_transaction.status = WalletTransaction.STATUS_AVAILABLE
        last_transaction.amount += 345
        last_transaction.save()

        self.client.post(
            reverse("wallet:request-list"),
            {
                "payment_type": "cbu",
                "nro": "123.567.test",
            },
        )
        response_data = self.client.get(
            reverse("wallet:wallet-detail", args=["x"])
        ).json()
        self.assertEqual(response_data["current_payment_nro"], ".test")
        self.assertEqual(response_data["current_payment_type"], "cbu")

    def test_wallet_total_balance(self):
        self.login()
        response_data = self.client.get(
            reverse("wallet:wallet-detail", args=["x"])
        ).json()
        self.assertEqual(response_data["total_balance"], 12000.0)
        self.client.post(
            reverse("wallet:request-list"),
            {
                "payment_type": "alias",
                "nro": "martin.nieva.test",
            },
        )
        response_data = self.client.get(
            reverse("wallet:wallet-detail", args=["x"])
        ).json()
        self.assertEqual(response_data["total_balance"], 0.0)
        last_transaction = WalletTransaction.objects.order_by(
            "-datetime_added"
        ).first()
        last_transaction.amount = float(last_transaction.amount) + 345.983
        last_transaction.save()
        response_data = self.client.get(
            reverse("wallet:wallet-detail", args=["x"])
        ).json()
        self.assertEqual(response_data["total_balance"], 345.9830000000002)
        last_transaction.status = WalletTransaction.STATUS_AVAILABLE
        last_transaction.save()
        response_data = self.client.get(
            reverse("wallet:wallet-detail", args=["x"])
        ).json()
        self.assertEqual(response_data["total_balance"], 345.9830000000002)

    def test_wallet_paid_off(self):
        self.login()
        self.client.post(
            reverse("wallet:request-list"),
            {
                "payment_type": "alias",
                "nro": "martin.nieva.test",
            },
        )
        response_data = self.client.get(
            reverse("wallet:wallet-detail", args=["x"])
        ).json()
        self.assertEqual(response_data["paid_off"], 0.0)
        last_transaction = WalletTransaction.objects.order_by(
            "-datetime_added"
        ).first()
        last_transaction.status = WalletTransaction.STATUS_PROCESSED
        last_transaction.save()
        response_data = self.client.get(
            reverse("wallet:wallet-detail", args=["x"])
        ).json()
        self.assertEqual(response_data["paid_off"], -12000.0)
        last_transaction.amount = float(last_transaction.amount) + 345.99
        last_transaction.save()
        response_data = self.client.get(
            reverse("wallet:wallet-detail", args=["x"])
        ).json()
        self.assertEqual(response_data["paid_off"], -11654.01)

    def test_wallet_sum(self):
        self.login()

        response_data = self.client.get(
            reverse("wallet:wallet-detail", args=["x"])
        ).json()
        self.assertEqual(response_data["available"], 12000.0)

        wallet_base = WalletTransaction.objects.get(code="555")

        wallet_base.id = None
        wallet_base.amount = 3454563
        wallet_base.code = "777"
        wallet_base.save()

        wallet_base = WalletTransaction.objects.get(code="555")
        wallet_base.id = None
        wallet_base.amount = 123123.45678
        wallet_base.code = "888"
        wallet_base.save()

        test_against_amount = 3454563 + 123123.45678 + 12000

        response_data = self.client.get(
            reverse("wallet:wallet-detail", args=["x"])
        ).json()
        self.assertEqual(response_data["available"], test_against_amount)

        self.client.post(
            reverse("wallet:request-list"),
            {
                "payment_type": "alias",
                "nro": "martin.nieva.test",
            },
        )

        response_data = self.client.get(
            reverse("wallet:wallet-detail", args=["x"])
        ).json()
        self.assertEqual(response_data["available"], test_against_amount)

        last_transaction = WalletTransaction.objects.order_by(
            "-datetime_added"
        ).first()
        last_transaction.status = WalletTransaction.STATUS_AVAILABLE
        last_transaction.save()

        response_data = self.client.get(
            reverse("wallet:wallet-detail", args=["x"])
        ).json()
        self.assertEqual(response_data["available"], 0.0)

        last_transaction = WalletTransaction.objects.order_by(
            "-datetime_added"
        ).first()
        last_transaction.id = None
        last_transaction.code = "ads234"
        last_transaction.amount = 567
        last_transaction.save()

        response_data = self.client.get(
            reverse("wallet:wallet-detail", args=["x"])
        ).json()
        self.assertEqual(response_data["available"], 567.0)

        last_transaction = WalletTransaction.objects.order_by(
            "-datetime_added"
        ).first()
        last_transaction.id = None
        last_transaction.code = "ads234x"
        last_transaction.amount = -123.434
        last_transaction.save()

        response_data = self.client.get(
            reverse("wallet:wallet-detail", args=["x"])
        ).json()
        self.assertEqual(response_data["available"], 443.56600000000003)

        last_transaction = WalletTransaction.objects.order_by(
            "-datetime_added"
        ).first()
        last_transaction.id = None
        last_transaction.code = "ads2314x"
        last_transaction.amount = 4567834
        last_transaction.save()

        response_data = self.client.get(
            reverse("wallet:wallet-detail", args=["x"])
        ).json()
        self.assertEqual(response_data["available"], 4568277.566)

    def test_wallet_unavailable_sum_null_by_empty(self):
        self.login()
        WalletExtractionRequest.objects.all().delete()
        WalletTransaction.objects.all().delete()
        response_data = self.client.get(
            reverse("wallet:wallet-detail", args=["x"])
        ).json()
        self.assertEqual(response_data["not_available"], 0.0)

    def test_wallet_unavailable_sum_null_by_exclude(self):
        self.login()
        self.client.post(
            reverse("wallet:request-list"),
            {
                "payment_type": "alias",
                "nro": "martin.nieva.test",
            },
        )
        last_transaction = WalletTransaction.objects.order_by(
            "-datetime_added"
        ).first()
        last_transaction.status = WalletTransaction.STATUS_CANCELLED
        last_transaction.save()
        self.client.post(
            reverse("wallet:request-list"),
            {
                "payment_type": "alias",
                "nro": "martin.nieva.test",
            },
        )
        last_transaction = WalletTransaction.objects.order_by(
            "-datetime_added"
        ).first()
        last_transaction.status = WalletTransaction.STATUS_EXPIRED
        last_transaction.save()
        self.client.post(
            reverse("wallet:request-list"),
            {
                "payment_type": "alias",
                "nro": "martin.nieva.test",
            },
        )
        last_transaction = WalletTransaction.objects.order_by(
            "-datetime_added"
        ).first()
        last_transaction.status = WalletTransaction.STATUS_AVAILABLE
        last_transaction.save()
        response_data = self.client.get(
            reverse("wallet:wallet-detail", args=["x"])
        ).json()
        self.assertEqual(response_data["not_available"], 0.0)

    def test_wallet_unavailable_sum_positive(self):
        self.login()

        self.client.post(
            reverse("wallet:request-list"),
            {
                "payment_type": "alias",
                "nro": "martin.nieva.test",
            },
        )

        wallet_base = WalletTransaction.objects.get(code="555")
        wallet_base.id = None
        wallet_base.amount = 12001.5
        wallet_base.code = "777"
        wallet_base.description = "gift"
        wallet_base.status = WalletTransaction.STATUS_PENDING
        wallet_base.save()

        response_data = self.client.get(
            reverse("wallet:wallet-detail", args=["x"])
        ).json()
        self.assertEqual(response_data["not_available"], 1.5)

    def test_wallet_unavailable_sum(self):
        self.login()
        test_against_amount_unavailable = 5678

        self.client.post(
            reverse("wallet:request-list"),
            {
                "payment_type": "alias",
                "nro": "martin.nieva.test",
            },
        )

        last_transaction = WalletTransaction.objects.order_by(
            "-datetime_added"
        ).first()
        last_transaction.amount = test_against_amount_unavailable
        last_transaction.save()

        self.client.post(
            reverse("wallet:request-list"),
            {
                "payment_type": "alias",
                "nro": "martin.nieva.test",
            },
        )
        response_data = self.client.get(
            reverse("wallet:wallet-detail", args=["x"])
        ).json()
        self.assertEqual(response_data["not_available"], -12000 + 5678)
        self.assertEqual(response_data["available"], 12000.0)

    def test_request_alias_update(self):
        self.login()
        wallet = Wallet.objects.select_related("payment").get(code="123")
        wallet.payment = LeadPayment()
        wallet.payment.nro = "345dfs"
        wallet.payment.payment_type = LeadPayment.PAYMENT_TYPE_ALIAS
        wallet.payment.user = self.user
        wallet.payment.save()
        wallet.save()
        self.client.post(
            reverse("wallet:request-list"),
            {
                "payment_type": "alias",
                "nro": "martin.nieva.test",
            },
        )
        wallet = Wallet.objects.select_related("payment").get(code="123")
        self.assertEqual(wallet.payment.nro, "martin.nieva.test")

    def test_request_alias_create(self):
        self.login()
        self.client.post(
            reverse("wallet:request-list"),
            {
                "payment_type": "alias",
                "nro": "martin.nieva.test",
            },
        )
        wallet = Wallet.objects.select_related("payment").get(code="123")
        self.assertEqual(wallet.payment.nro, "martin.nieva.test")

    def test_request_throttle(self):
        self.login()

        for i in range(3):
            response = self.client.post(
                reverse("wallet:request-list"),
                {
                    "payment_type": "alias",
                    "nro": "martin.nieva.test",
                },
            )
            self.assertEqual(response.status_code, status.HTTP_201_CREATED)
            last_transaction = WalletTransaction.objects.order_by(
                "-datetime_added"
            ).first()
            last_transaction.status = WalletTransaction.STATUS_AVAILABLE
            last_transaction.amount += 123
            last_transaction.save()

        response = self.client.post(
            reverse("wallet:request-list"),
            {
                "payment_type": "alias",
                "nro": "martin.nieva.test",
            },
        )
        self.assertEqual(
            response.status_code, status.HTTP_429_TOO_MANY_REQUESTS
        )

    def test_request_done(self):
        self.login()
        extraction_request_count = WalletExtractionRequest.objects.count()
        transaction_count = WalletTransaction.objects.count()
        response = self.client.post(
            reverse("wallet:request-list"),
            {
                "payment_type": "alias",
                "nro": "martin.nieva.test",
            },
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(len(response.data), 0)
        self.assertIsInstance(response.data, dict)
        self.assertEqual(
            WalletExtractionRequest.objects.count(),
            extraction_request_count + 1,
        )
        self.assertEqual(
            WalletTransaction.objects.count(), transaction_count + 1
        )
        first_transaction = WalletTransaction.objects.get(code="555")
        last_transaction = WalletTransaction.objects.order_by(
            "-datetime_added"
        ).first()
        self.assertEqual(
            float(last_transaction.amount), -first_transaction.amount
        )
        self.assertEqual(
            last_transaction.wallet_id,
            Wallet.objects.filter(user=self.user).first().id,
        )
        self.assertEqual(
            last_transaction.status, WalletTransaction.STATUS_PENDING
        )
        self.assertEqual(
            last_transaction.currency, WalletTransaction.CURRENCY_ARS
        )
        self.assertIs(last_transaction.datetime_available, None)
        extraction_req = WalletExtractionRequest.objects.order_by(
            "-datetime_request"
        ).first()
        self.assertEqual(
            extraction_req.wallet_transaction_id, last_transaction.id
        )
        self.assertEqual(
            extraction_req.status, WalletExtractionRequest.STATUS_PENDING
        )
        self.assertEqual(extraction_req.operator_id, self.user.id)

    def test_request_transaction_paging(self):
        self.login()

        transaction_base = WalletTransaction.objects.get(code="555")
        transaction_list = [
            WalletTransaction(
                code=i,
                wallet_id=transaction_base.wallet_id,
                currency=transaction_base.currency,
                status=WalletTransaction.STATUS_AVAILABLE,
                amount=1,
            )
            for i in range(60)
        ]
        WalletTransaction.objects.bulk_create(transaction_list)

        response = self.client.get(reverse("wallet:transaction-list"))
        response_data = response.json()
        already_in_fixture = 1
        self.assertEqual(len(response_data["object_list"]), 50)
        self.assertEqual(response_data["count"], 50 + 10 + already_in_fixture)
        self.assertEqual(response_data["num_pages"], 2)
        self.assertEqual(response_data["next_page_number"], 2)
        self.assertIs(response_data["previous_page_number"], None)

        response = self.client.get(
            reverse("wallet:transaction-list"),
            {"page": 1},
        )
        response_data = response.json()
        self.assertEqual(len(response_data["object_list"]), 50)
        self.assertEqual(response_data["count"], 50 + 10 + already_in_fixture)
        self.assertEqual(response_data["num_pages"], 2)
        self.assertEqual(response_data["next_page_number"], 2)
        self.assertIs(response_data["previous_page_number"], None)

        response = self.client.get(
            reverse("wallet:transaction-list"),
            {"page": 2},
        )
        response_data = response.json()
        already_in_fixture = 1
        self.assertEqual(
            len(response_data["object_list"]), 10 + already_in_fixture
        )
        self.assertEqual(response_data["count"], 50 + 10 + already_in_fixture)
        self.assertEqual(response_data["num_pages"], 2)
        self.assertIs(response_data["next_page_number"], None)
        self.assertEqual(response_data["previous_page_number"], 1)

        response = self.client.get(
            reverse("wallet:transaction-list"),
            {"page": "last"},
        )
        response_data = response.json()
        already_in_fixture = 1
        self.assertEqual(
            len(response_data["object_list"]), 10 + already_in_fixture
        )
        self.assertEqual(response_data["count"], 50 + 10 + already_in_fixture)
        self.assertEqual(response_data["num_pages"], 2)
        self.assertIs(response_data["next_page_number"], None)
        self.assertEqual(response_data["previous_page_number"], 1)

        response = self.client.get(
            reverse("wallet:transaction-list"),
            {"page": 3},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response_data = response.json()
        self.assertIsInstance(response_data["object_list"], list)
        self.assertEqual(len(response_data["object_list"]), 0)
        self.assertEqual(response_data["count"], 50 + 10 + already_in_fixture)
        self.assertEqual(response_data["num_pages"], 2)
        self.assertIs(response_data["next_page_number"], None)
        self.assertIs(response_data["previous_page_number"], None)

        WalletExtractionRequest.objects.all().delete()
        WalletTransaction.objects.all().delete()

        response = self.client.get(reverse("wallet:transaction-list"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response_data = response.json()
        self.assertIsInstance(response_data["object_list"], list)
        self.assertEqual(len(response_data["object_list"]), 0)
        self.assertEqual(response_data["count"], 0)
        self.assertEqual(response_data["num_pages"], 1)
        self.assertIs(response_data["next_page_number"], None)
        self.assertIs(response_data["previous_page_number"], None)

        response = self.client.get(
            reverse("wallet:transaction-list"),
            {"page": 1},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response_data = response.json()
        self.assertIsInstance(response_data["object_list"], list)
        self.assertEqual(len(response_data["object_list"]), 0)
        self.assertEqual(response_data["count"], 0)
        self.assertEqual(response_data["num_pages"], 1)
        self.assertIs(response_data["next_page_number"], None)
        self.assertIs(response_data["previous_page_number"], None)

        response = self.client.get(
            reverse("wallet:transaction-list"),
            {"page": 2},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response_data = response.json()
        self.assertIsInstance(response_data["object_list"], list)
        self.assertEqual(len(response_data["object_list"]), 0)
        self.assertEqual(response_data["count"], 0)
        self.assertEqual(response_data["num_pages"], 1)
        self.assertIs(response_data["next_page_number"], None)
        self.assertIs(response_data["previous_page_number"], None)

        response = self.client.get(
            reverse("wallet:transaction-list"),
            {"page": "last"},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response_data = response.json()
        self.assertIsInstance(response_data["object_list"], list)
        self.assertEqual(len(response_data["object_list"]), 0)
        self.assertEqual(response_data["count"], 0)
        self.assertEqual(response_data["num_pages"], 1)
        self.assertIs(response_data["next_page_number"], None)
        self.assertIs(response_data["previous_page_number"], None)

    @mock.patch("wallet_base.serializers.serializers.logger.warning")
    def test_request_transaction_invalid_already_requested(
        self, logger_warning
    ):
        self.login()
        self.client.post(
            reverse("wallet:request-list"),
            {
                "payment_type": "alias",
                "nro": "martin.nieva.test",
            },
        )
        response = self.client.post(
            reverse("wallet:request-list"),
            {
                "payment_type": "alias",
                "nro": "martin.nieva.test",
            },
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        response_data = response.json()
        self.assertEqual(response_data["error_code"], "1")
        logger_warning.assert_called_once()

    @mock.patch("wallet_base.serializers.serializers.logger.warning")
    def test_request_transaction_invalid_no_credits(self, logger_warning):
        self.login()
        WalletTransaction.objects.filter(code="555").update(
            status=WalletTransaction.STATUS_CANCELLED
        )
        response = self.client.post(
            reverse("wallet:request-list"),
            {
                "payment_type": "alias",
                "nro": "martin.nieva.test",
            },
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        response_data = response.json()
        self.assertEqual(response_data["error_code"], "2")
        logger_warning.assert_called_once()

    def test_request_auth(self):
        response = self.client.post(
            reverse("wallet:request-list"),
            {
                "amount": -200,
                "payment_type": "alias",
                "nro": "martin.nieva.test",
            },
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_transaction_list_auth(self):
        response = self.client.get(reverse("wallet:transaction-list"))
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_wallet_auth(self):
        response = self.client.get(reverse("wallet:wallet-detail", args=["x"]))
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
