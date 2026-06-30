from django.contrib import admin
from django.urls import include, path
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView

from apps.accounts.views import ChangePasswordView, LoginView, LogoutAllView, LogoutView, PasswordResetConfirmView, PasswordResetRequestView, UserViewSet
from apps.appointments.views import AppointmentViewSet, AvailabilityView, PublicBookingView, PublicCancellationView, ScheduleBlockViewSet
from apps.appointments.agent_views import AgentToolViewSet
from apps.barbershops.views import CurrentBarbershopView, OperatingHourViewSet, PublicBarbershopView
from apps.customers.views import CustomerViewSet
from apps.reports.views import DashboardView
from apps.services.views import PublicServiceListView, ServiceViewSet

router = DefaultRouter()
router.register("customers", CustomerViewSet, basename="customer")
router.register("services", ServiceViewSet, basename="service")
router.register("appointments", AppointmentViewSet, basename="appointment")
router.register("schedule-blocks", ScheduleBlockViewSet, basename="schedule-block")
router.register("operating-hours", OperatingHourViewSet, basename="operating-hour")
router.register("users", UserViewSet, basename="user")
router.register("agent-tools", AgentToolViewSet, basename="agent-tool")

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/", include(router.urls)),
    path("api/v1/auth/login/", LoginView.as_view()),
    path("api/v1/auth/refresh/", TokenRefreshView.as_view()),
    path("api/v1/auth/logout/", LogoutView.as_view()),
    path("api/v1/auth/logout-all/", LogoutAllView.as_view()),
    path("api/v1/auth/change-password/", ChangePasswordView.as_view()),
    path("api/v1/auth/password-reset/", PasswordResetRequestView.as_view()),
    path("api/v1/auth/password-reset/confirm/", PasswordResetConfirmView.as_view()),
    path("api/v1/barbershop/", CurrentBarbershopView.as_view()),
    path("api/v1/dashboard/", DashboardView.as_view()),
    path("api/v1/public/cancel/", PublicCancellationView.as_view()),
    path("api/v1/public/<slug:slug>/", PublicBarbershopView.as_view()),
    path("api/v1/public/<slug:slug>/services/", PublicServiceListView.as_view()),
    path("api/v1/public/<slug:slug>/availability/", AvailabilityView.as_view()),
    path("api/v1/public/<slug:slug>/book/", PublicBookingView.as_view()),
]
