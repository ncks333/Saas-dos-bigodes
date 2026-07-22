from rest_framework.views import exception_handler


def api_exception_handler(exc, context):
    response = exception_handler(exc, context)
    if response is not None:
        details = response.data
        response.data = {"error": {"status": response.status_code, "details": details}}
        if isinstance(details, dict) and details.get("code") == "subscription_required":
            response.data["code"] = details["code"]
    return response
