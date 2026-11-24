from django.urls import include, path

urlpatterns = [path("onsite/", include("events.onsite_urls"))]
