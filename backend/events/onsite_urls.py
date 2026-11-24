from django.contrib.auth import views as auth_views
from django.urls import path, reverse_lazy

from . import onsite_views as views

app_name = "onsite"

urlpatterns = [
    path(
        "login/",
        auth_views.LoginView.as_view(
            template_name="onsite/login.html", next_page=reverse_lazy("onsite:home")
        ),
        name="login",
    ),
    path("logout/", auth_views.LogoutView.as_view(next_page=reverse_lazy("onsite:login")), name="logout"),
    path("", views.home, name="home"),
    path("activities/<int:activity_id>/", views.roster, name="roster"),
    path(
        "activities/<int:activity_id>/people/<int:participant_id>/check-in/",
        views.sign_in,
        name="sign_in",
    ),
    path(
        "activities/<int:activity_id>/people/<int:participant_id>/late-note/",
        views.late_note,
        name="late_note",
    ),
    path(
        "activities/<int:activity_id>/people/<int:participant_id>/release/",
        views.release,
        name="release",
    ),
    path("activities/<int:activity_id>/arrivals/", views.arrival, name="arrival"),
    path(
        "activities/<int:activity_id>/arrivals/<int:participant_id>/leave/",
        views.leave,
        name="leave",
    ),
    path(
        "activities/<int:activity_id>/arrivals/<int:participant_id>/admit/",
        views.admit,
        name="admit",
    ),
    path("activities/<int:activity_id>/report/", views.report, name="report"),
    path("activities/<int:activity_id>/report.xlsx", views.export, name="export"),
]
