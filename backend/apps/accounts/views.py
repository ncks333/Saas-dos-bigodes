from urllib.parse import urlencode

from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from django.utils.encoding import force_bytes
from django.utils.decorators import method_decorator
from django_ratelimit.decorators import ratelimit
from rest_framework import serializers, status, viewsets
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.settings import api_settings
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from rest_framework_simplejwt.token_blacklist.models import OutstandingToken, BlacklistedToken

from apps.audit.services import record_event
from apps.billing.access import user_has_subscription_access
from core.permissions.roles import IsAdminRole
from .models import User
from .serializers import ChangePasswordSerializer, LoginSerializer, UserSerializer
from .throttles import LoginRateThrottle, PasswordResetRateThrottle


@method_decorator(ratelimit(key="ip", rate="5/15m", method="POST", block=True), name="dispatch")
class LoginView(TokenObtainPairView):
    permission_classes = [AllowAny]
    serializer_class = LoginSerializer
    throttle_classes = [LoginRateThrottle]

    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        if response.status_code == 200:
            user = User.objects.filter(username=request.data.get("username")).first()
            if user:
                record_event(user, "LOGIN", request=request)
        return response


class SubscriptionTokenRefreshView(TokenRefreshView):
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        try:
            refresh = RefreshToken(request.data.get("refresh", ""))
        except TokenError:
            return super().post(request, *args, **kwargs)
        user = User.objects.filter(pk=refresh.get(api_settings.USER_ID_CLAIM)).first()
        if user is None or not user_has_subscription_access(user):
            raise PermissionDenied(
                {
                    "code": "subscription_required",
                    "detail": "Assinatura precisa ser regularizada.",
                }
            )
        return super().post(request, *args, **kwargs)


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        refresh = request.data.get("refresh")
        if not refresh:
            raise serializers.ValidationError({"refresh": "Campo obrigatório."})
        RefreshToken(refresh).blacklist()
        record_event(request.user, "LOGOUT", request=request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class LogoutAllView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        tokens = OutstandingToken.objects.filter(user=request.user)
        for token in tokens:
            BlacklistedToken.objects.get_or_create(token=token)
        record_event(request.user, "LOGOUT_ALL", request=request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class ChangePasswordView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        record_event(request.user, "PASSWORD_CHANGED", request=request)
        return Response({"message": "Senha alterada."})


class PasswordResetRequestView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [PasswordResetRateThrottle]

    def post(self, request):
        user = User.objects.filter(email__iexact=request.data.get("email", ""), is_active=True).first()
        if user:
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            token = default_token_generator.make_token(user)
            query = urlencode({"uid": uid, "token": token})
            reset_url = f"{settings.FRONTEND_URL.rstrip('/')}/redefinir-senha?{query}"
            send_mail(
                "Recuperação de senha",
                f"Use o link abaixo para redefinir sua senha. Ele expira em 1 hora.\n\n{reset_url}\n\nSe você não fez este pedido, ignore esta mensagem.",
                None,
                [user.email],
            )
        return Response({"message": "Se o e-mail existir, as instruções serão enviadas."})


class PasswordResetConfirmView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [PasswordResetRateThrottle]

    def post(self, request):
        try:
            user = User.objects.get(pk=urlsafe_base64_decode(request.data.get("uid", "")).decode())
        except (User.DoesNotExist, ValueError, TypeError, UnicodeDecodeError):
            raise serializers.ValidationError("Código inválido.")
        if not default_token_generator.check_token(user, request.data.get("token", "")):
            raise serializers.ValidationError("Token inválido ou expirado.")
        password = request.data.get("password", "")
        from django.contrib.auth.password_validation import validate_password
        validate_password(password, user)
        user.set_password(password)
        user.save(update_fields=["password"])
        return Response({"message": "Senha redefinida."})


class UserViewSet(viewsets.ModelViewSet):
    serializer_class = UserSerializer
    permission_classes = [IsAdminRole]

    def get_queryset(self):
        return User.objects.filter(barbershop_id=self.request.user.barbershop_id)

    def perform_create(self, serializer):
        user = serializer.save(barbershop_id=self.request.user.barbershop_id)
        record_event(self.request.user, "USER_CREATED", target=user, request=self.request)
