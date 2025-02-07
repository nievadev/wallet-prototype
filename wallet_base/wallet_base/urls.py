from django.urls import include, re_path
from rest_framework import routers

from wallet_base.views import (
    LoginView,
    WalletExtractionRequestViewSet,
    WalletTransactionViewSet,
    WalletViewSet,
)

router = routers.DefaultRouter()
router.include_root_view = False
router.register(r"wallet", WalletViewSet, basename="wallet")
router.register(
    r"transaction", WalletTransactionViewSet, basename="transaction"
)
router.register(r"request", WalletExtractionRequestViewSet, basename="request")

urlpatterns = [
    re_path(r"api/v1/", include((router.urls, "wallet"), namespace="wallet")),
    re_path(r"login/", LoginView.as_view(), name="wallet-login"),
]
