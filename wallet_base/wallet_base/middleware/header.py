class HeaderMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # AWS WAF usage by proxy example
        request.META["is_aws_waf_block"] = (
            request.headers.get("x-amzn-waf-rule") == "block"
        )
        response = self.get_response(request)
        return response
