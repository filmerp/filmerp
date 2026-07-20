from django.urls import path

from . import security_views


app_name = "security"

urlpatterns = [
    path("", security_views.security_index, name="index"),
    path("users/", security_views.account_list, name="account_list"),
    path("users/new/", security_views.account_create, name="account_create"),
    path("users/<int:pk>/", security_views.account_detail, name="account_detail"),
    path("users/<int:pk>/edit/", security_views.account_edit, name="account_edit"),
    path("users/<int:pk>/action/", security_views.account_action, name="account_action"),
    path("roles/", security_views.role_list, name="role_list"),
    path("roles/<int:pk>/", security_views.role_detail, name="role_detail"),
    path("logins/", security_views.login_history, name="login_history"),
    path("audit/", security_views.audit_history, name="audit_history"),
]
