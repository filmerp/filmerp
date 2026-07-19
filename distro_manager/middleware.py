from django.utils.http import url_has_allowed_host_and_scheme


class AdminReturnMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if getattr(response, "_filmerp_admin_return", False):
            return response
        return_url = request.POST.get("return_to")
        skip_return = any(key in request.POST for key in ("_continue", "_addanother", "_saveasnew", "_popup"))

        if (
            request.method == "POST"
            and request.path.startswith("/admin/")
            and return_url
            and not skip_return
            and response.status_code in {301, 302, 303}
            and url_has_allowed_host_and_scheme(
                return_url,
                allowed_hosts={request.get_host()},
                require_https=request.is_secure(),
            )
        ):
            response["Location"] = return_url
        return response
