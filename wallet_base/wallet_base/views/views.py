from django.http import Http404
from django.views.generic import ListView
from rest_framework import (
    authentication,
    mixins,
    permissions,
    response,
    viewsets,
)
from rest_framework.authtoken.views import ObtainAuthToken

from wallet_base.models import LeadPayment, Wallet, WalletTransaction
from wallet_base.serializers import (
    ExtractionSerializer,
    WalletTransactionSerializer,
)
from wallet_base.throttling import (
    UniversalAwsWafThrottle,
    UserRateAwsAwfThrottle,
)


class ExtractionThrottle(UniversalAwsWafThrottle):
    rate = "3/day"
    scope = "extraction_day"


class ExtractionThrottleMyAccount(UserRateAwsAwfThrottle):
    rate = "3/day"
    scope = "extraction_my_account_day"


class WalletThrottle(UniversalAwsWafThrottle):
    rate = "50/day"
    scope = "wallet_day"


class WalletThrottleMyAccount(UserRateAwsAwfThrottle):
    rate = "50/day"
    scope = "wallet_my_account_day"


class TransactionThrottle(UniversalAwsWafThrottle):
    rate = "50/day"
    scope = "transaction_day"


class TransactionThrottleMyAccount(UserRateAwsAwfThrottle):
    rate = "50/day"
    scope = "transaction_my_account_day"


class LoginView(ObtainAuthToken):
    pass


class WalletViewSet(viewsets.ViewSet):
    authentication_classes = [authentication.TokenAuthentication]
    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [WalletThrottle, WalletThrottleMyAccount]

    nro_censor_length = 5

    def retrieve(self, request, pk):
        wallet = Wallet.objects.filter(
            user=request.user,
        ).select_related(
            "payment"
        )[0]
        available = wallet.get_available_credit()
        paid_off = wallet.get_paid_credit_negative()
        not_available = wallet.get_pending_credit()
        nro = None
        payment_type = ""

        if wallet.payment is not None:
            nro = wallet.payment.nro
            payment_type = wallet.payment.payment_type

            if payment_type == LeadPayment.PAYMENT_TYPE_ALIAS:
                nro = nro[: self.nro_censor_length]  # first characters
            else:
                nro = nro[-self.nro_censor_length :]  # last characters

        return response.Response(
            {
                "available": available,
                "not_available": not_available,
                "total_balance": available + not_available,
                "paid_off": paid_off,
                "current_payment_nro": nro,
                "current_payment_type": payment_type,
            }
        )


class WalletTransactionViewSet(ListView, viewsets.ViewSet):
    authentication_classes = [authentication.TokenAuthentication]
    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [TransactionThrottle, TransactionThrottleMyAccount]
    ordering = "-datetime_added"
    paginate_by = 50

    @property
    def queryset(self):
        return WalletTransaction.objects.filter(
            wallet__user=self.request.user,
            status__in=[
                # We don't show expired or cancelled transactions, yet
                # Cancelled: we don't show it because user requesting cancelling of extraction request feature is not there yet
                WalletTransaction.STATUS_PENDING,
                WalletTransaction.STATUS_AVAILABLE,
                WalletTransaction.STATUS_PROCESSED,
                WalletTransaction.STATUS_EXPIRED,
            ],
        )

    def list(self, request):
        self.object_list = self.get_queryset()
        next_page_number = None
        previous_page_number = None

        try:
            pagination = self.get_context_data()
        except Http404:
            paginator = self.get_paginator(self.object_list, self.paginate_by)
            return response.Response(
                {
                    "object_list": [],
                    "num_pages": paginator.num_pages,
                    "count": self.object_list.count(),
                    "page_size": self.paginate_by,
                    "next_page_number": next_page_number,
                    "previous_page_number": previous_page_number,
                }
            )

        transaction_q = WalletTransaction.objects.filter(
            id__in=self.object_list.filter(
                object_name="wallet_wallettransaction", object_id__isnull=False
            ).values_list("object_id", flat=True)
        )

        transaction_object_map = {
            request.id: request for request in transaction_q
        }

        serializer = WalletTransactionSerializer(
            pagination["object_list"],
            many=True,
            transaction_object_map=transaction_object_map,
        )
        page_obj = pagination["page_obj"]

        if page_obj.has_next():
            next_page_number = page_obj.next_page_number()

        if page_obj.has_previous():
            previous_page_number = page_obj.previous_page_number()

        return response.Response(
            {
                "object_list": serializer.data,
                "num_pages": pagination["paginator"].num_pages,
                "count": self.object_list.count(),
                "page_size": self.paginate_by,
                "next_page_number": next_page_number,
                "previous_page_number": previous_page_number,
            }
        )


class WalletExtractionRequestViewSet(
    mixins.CreateModelMixin,
    viewsets.GenericViewSet,
    viewsets.ViewSet,
):
    authentication_classes = [authentication.TokenAuthentication]
    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [ExtractionThrottle, ExtractionThrottleMyAccount]
    serializer_class = ExtractionSerializer
