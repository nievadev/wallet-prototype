import random
from uuid import uuid4

from aesfield.field import AESField
from dateutil.relativedelta import relativedelta
from django.contrib.auth.models import User
from django.db import models
from django.db.models import Sum
from django.utils.timezone import now as utcnow


def uuid_md5():
    return uuid4().hex


def generate_unique_wallet_number():
    for i in range(5):
        wallet_number = random.randint(10000000, 99999999)
        if not Wallet.objects.filter(wallet_number=wallet_number).exists():
            return str(wallet_number)
    raise Exception("No wallet number could be assigned.")


class LeadPayment(models.Model):
    PAYMENT_TYPE_ALIAS = "alias"
    PAYMENT_TYPE_CBU = "cbu"

    PAYMENT_TYPE_CHOICES = (
        (PAYMENT_TYPE_ALIAS, PAYMENT_TYPE_ALIAS),
        (PAYMENT_TYPE_CBU, PAYMENT_TYPE_CBU),
    )

    user = models.ForeignKey(User, on_delete=models.PROTECT)
    nro = AESField()
    payment_type = models.CharField(
        max_length=10, choices=PAYMENT_TYPE_CHOICES, db_index=True
    )


class WalletTransaction(models.Model):
    STATUS_PENDING = "p"
    STATUS_AVAILABLE = "a"
    STATUS_CANCELLED = "c"
    STATUS_PROCESSED = "x"
    STATUS_EXPIRED = "e"

    STATUS = (
        (STATUS_PENDING, "Pending"),
        (STATUS_AVAILABLE, "Available"),
        (STATUS_EXPIRED, "Expired"),
        (STATUS_PROCESSED, "Processed"),
        (STATUS_CANCELLED, "Cancelled"),
    )

    CURRENCY_ARS = "ARS"
    CURRENCY = ((CURRENCY_ARS, "Peso - Argentino"),)

    wallet = models.ForeignKey("Wallet", on_delete=models.PROTECT)
    code = models.CharField(
        max_length=32, unique=True, default=uuid_md5, db_index=True
    )
    description = models.CharField(
        max_length=250, null=True, blank=True, default=None
    )
    object_id = models.IntegerField(
        db_index=True, default=0, null=True, blank=True
    )
    object_name = models.CharField(
        max_length=100, null=True, blank=True, db_index=True
    )
    status = models.CharField(choices=STATUS, max_length=1, db_index=True)
    currency = models.CharField(
        choices=CURRENCY, max_length=3, db_index=True, default=CURRENCY_ARS
    )
    amount = models.FloatField(db_index=True)
    datetime_available = models.DateTimeField(
        null=True, blank=True, db_index=True
    )
    datetime_expiration = models.DateTimeField(
        null=True, blank=True, db_index=True
    )
    datetime_added = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta(object):
        app_label = "wallet_base"


class WalletExtractionRequest(models.Model):
    STATUS_PENDING = "p"
    STATUS_PROCESSED = "r"
    STATUS_CANCELLED = "e"

    STATUS = (
        (STATUS_PENDING, "Pending"),
        (STATUS_PROCESSED, "Processed"),
        (STATUS_CANCELLED, "Cancelled"),
    )

    wallet_transaction = models.ForeignKey(
        WalletTransaction, on_delete=models.PROTECT
    )
    datetime_resolution = models.DateTimeField(
        null=True, blank=True, db_index=True
    )
    datetime_request = models.DateTimeField(auto_now_add=True, db_index=True)
    status = models.CharField(choices=STATUS, max_length=1, db_index=True)
    description = models.TextField(null=True, blank=True, default="")
    operator = models.ForeignKey(User, on_delete=models.PROTECT)

    class Meta(object):
        app_label = "wallet_base"
        constraints = [
            models.UniqueConstraint(
                fields=["wallet_transaction", "status"],
                name="unique_extraction",
            ),
        ]


class Wallet(models.Model):
    user = models.ForeignKey(User, on_delete=models.PROTECT)
    datetime_created = models.DateTimeField(auto_now_add=True, db_index=True)
    code = models.CharField(
        max_length=32, unique=True, default=uuid_md5, db_index=True
    )
    wallet_number = models.CharField(
        max_length=8,
        unique=True,
        null=False,
        blank=False,
        db_index=True,
        default=generate_unique_wallet_number,
    )
    payment = models.ForeignKey(
        LeadPayment, on_delete=models.PROTECT, null=True
    )
    tax_code = models.CharField(
        max_length=100, null=True, blank=True, db_index=True
    )
    culture = models.CharField(
        max_length=5, null=True, default="es-ar", db_index=True
    )

    class Meta(object):
        app_label = "wallet_base"

    def __str__(self):
        return self.wallet_number

    def get_available_credit(
        self,
        status=[WalletTransaction.STATUS_AVAILABLE],
    ):
        wt_query = WalletTransaction.objects.filter(
            wallet=self, status__in=status
        )

        amount = wt_query.aggregate(total_amount=Sum("amount"))

        if amount["total_amount"] is not None:
            return amount["total_amount"]

        return 0.0

    def get_paid_credit_negative(self):
        wt_query = WalletTransaction.objects.filter(
            wallet=self,
            amount__lt=0,
            status=WalletTransaction.STATUS_PROCESSED,
        )

        amount = wt_query.aggregate(total_amount=Sum("amount"))

        if amount["total_amount"] is not None:
            return amount["total_amount"]

        return 0.0

    def get_pending_credit(self):
        wt_query = WalletTransaction.objects.filter(
            wallet=self,
            status=WalletTransaction.STATUS_PENDING,
        )

        amount = wt_query.aggregate(total_amount=Sum("amount"))

        if amount["total_amount"] is not None:
            return amount["total_amount"]

        return 0.0

    def get_pending_credit_negative(self):
        wt_query = WalletTransaction.objects.filter(
            wallet=self,
            status=WalletTransaction.STATUS_PENDING,
            amount__lt=0,
        )

        amount = wt_query.aggregate(total_amount=Sum("amount"))

        if amount["total_amount"] is not None:
            return amount["total_amount"]

        return 0.0

    def add_available(
        self,
        amount,
        currency=WalletTransaction.CURRENCY_ARS,
        expiration_delta_years=3,
        available_delta_days=0,
        description="created manually",
    ):
        return self.wallettransaction_set.create(
            amount=amount,
            status=WalletTransaction.STATUS_AVAILABLE,
            datetime_available=utcnow()
            + relativedelta(days=available_delta_days),
            datetime_expiration=utcnow()
            + relativedelta(years=expiration_delta_years),
            currency=currency,
            description=description,
        )

    def add_pending(
        self,
        amount,
        currency=WalletTransaction.CURRENCY_ARS,
        expiration_delta_years=3,
        available_delta_days=0,
        description="created manually",
    ):
        return self.wallettransaction_set.create(
            amount=amount,
            status=WalletTransaction.STATUS_PENDING,
            datetime_available=utcnow()
            + relativedelta(days=available_delta_days),
            datetime_expiration=utcnow()
            + relativedelta(
                years=expiration_delta_years, days=available_delta_days
            ),
            currency=currency,
            description=description,
        )
