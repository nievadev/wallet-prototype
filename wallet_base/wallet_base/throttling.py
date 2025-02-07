from rest_framework.throttling import AnonRateThrottle, UserRateThrottle


class AwsWafThrottleMixin:
    is_waf_blocked = False

    def wait(self, *args, **kwargs):
        if self.is_waf_blocked:
            return 0

        return super().wait(*args, **kwargs)

    def allow_request(self, request, view):
        allow_request = super().allow_request(request, view)
        self.is_waf_blocked = request.META.get("is_aws_waf_block", False)

        if self.is_waf_blocked:
            return self.throttle_failure()

        return allow_request


class AnonRateAwsWafThrottle(AwsWafThrottleMixin, AnonRateThrottle):
    pass


class UserRateAwsAwfThrottle(AwsWafThrottleMixin, UserRateThrottle):
    pass


class UniversalAwsWafThrottle(AnonRateAwsWafThrottle):
    def get_cache_key(self, request, view):
        return self.cache_format % {
            "scope": self.scope,
            "ident": self.get_ident(request),
        }
