import logging

from django.db import transaction
from django.utils.timezone import get_default_timezone
from rest_framework import serializers

from wallet_base.models import (
    LeadPayment,
    Wallet,
    WalletExtractionRequest,
    WalletTransaction,
)

logger = logging.getLogger("wallet")


class WalletTransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = WalletTransaction
        _datetime_fields = [
            "datetime_available",
            "datetime_expiration",
            "datetime_added",
        ]
        fields = [
            "description",
            "status",
            "currency",
            "amount",
        ] + _datetime_fields

    def __init__(self, *args, transaction_object_map=None, **kwargs):
        super().__init__(*args, **kwargs)

        for datetime_field in self.Meta._datetime_fields:
            self.fields[datetime_field].timezone = get_default_timezone()

        self.transaction_object_map = transaction_object_map

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["object_serialized"] = None
        if (
            self.transaction_object_map is not None
            and instance.object_name == "wallet_wallettransaction"
        ):
            data["object_serialized"] = WalletTransactionSerializer(
                self.transaction_object_map[instance.object_id]
            ).data
        return data


class ExtractionSerializer(serializers.ModelSerializer):
    ERROR_ALREADY_ORDERED = "1"
    ERROR_NO_CREDITS_EXTRACT = "2"

    class Meta:
        model = LeadPayment
        fields = ["payment_type", "nro"]

    def validate(self, validated_data):
        self.user = self.context["request"].user
        self.wallet = Wallet.objects.filter(user=self.user).select_related(
            "payment"
        )[0]

        if self.wallet.get_pending_credit_negative() != 0:
            raise serializers.ValidationError(
                {
                    "error_code": [self.ERROR_ALREADY_ORDERED],
                }
            )

        self.credit_amount = self.wallet.get_available_credit()

        if self.credit_amount <= 0:
            raise serializers.ValidationError(
                {
                    "error_code": [self.ERROR_NO_CREDITS_EXTRACT],
                }
            )

        return validated_data

    def create(self, validated_data):
        if self.wallet.payment is None:
            self.wallet.payment = LeadPayment(user=self.user)

        self.wallet.payment.nro = validated_data["nro"]
        self.wallet.payment.payment_type = validated_data["payment_type"]

        wallet_transaction = WalletTransaction(
            amount=self.credit_amount * -1,
            description="Pedido de extracción",
            wallet=self.wallet,
            status=WalletTransaction.STATUS_PENDING,
            currency=WalletTransaction.CURRENCY_ARS,
        )

        request = WalletExtractionRequest(
            status=WalletExtractionRequest.STATUS_PENDING,
            description=wallet_transaction.description,
            operator=self.user,
        )

        with transaction.atomic():
            self.wallet.payment.save()
            self.wallet.save()
            wallet_transaction.save()
            request.wallet_transaction = wallet_transaction
            request.save()

        return wallet_transaction

    def to_representation(self, instance):
        return {}

    def is_valid(self, *args, **kwargs):
        try:
            return super().is_valid(*args, **kwargs)
        except serializers.ValidationError as ex:
            user = self.context["request"].user
            logger.warning(
                f"got wrong request, data is {self.initial_data}, "
                f"user account is {user.username}, "
                f"error is {self.errors}"
            )
            error_data = {"error_code": ex.detail.get("error_code", [None])[0]}
            raise serializers.ValidationError(error_data)
