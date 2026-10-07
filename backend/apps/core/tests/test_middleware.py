from django.http import HttpResponse
from django.test import RequestFactory

from apps.core.middleware import DevCorsMiddleware


def test_dev_cors_only_when_debug_and_listed(settings):


    settings.DEBUG, settings.DEV_CORS_ORIGINS = False, ["http://localhost:8081"]
    req = RequestFactory().get("/api/v1/config", HTTP_ORIGIN="http://localhost:8081")
    assert "Access-Control-Allow-Origin" not in DevCorsMiddleware(lambda r: HttpResponse())(req)
    settings.DEBUG = True
    assert DevCorsMiddleware(lambda r: HttpResponse())(req)["Access-Control-Allow-Origin"] == "http://localhost:8081"
    other = RequestFactory().get("/", HTTP_ORIGIN="http://evil.example")
    assert "Access-Control-Allow-Origin" not in DevCorsMiddleware(lambda r: HttpResponse())(other)
