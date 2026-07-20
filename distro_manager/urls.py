from django.contrib import admin
from django.conf import settings
from django.conf.urls.static import static
from django.urls import include, path

from allauth.account.decorators import secure_admin_login
from distribution.views import DashboardLoginView


admin.site.login = secure_admin_login(admin.site.login)

urlpatterns = [
    path("admin/login/", DashboardLoginView.as_view(), name="filmerp_login"),
    path("konto/login/", DashboardLoginView.as_view(), name="account_login"),
    path("konto/", include("allauth.urls")),
    path("security/", include("distribution.security_urls")),
    path("admin/", admin.site.urls),
    path("", include("distribution.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
