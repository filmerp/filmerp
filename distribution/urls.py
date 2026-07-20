from django.urls import path

from .views import avails, contract_waterfall_wizard, dashboard, document_center, reports, reports_export_csv, session_keepalive, settlement_workbench, statement_center, title_catalog_export, title_detail, title_list, title_setup

app_name = "distribution"

urlpatterns = [
    path("", dashboard, name="dashboard"),
    path("session/keepalive/", session_keepalive, name="session_keepalive"),
    path("titles/", title_list, name="title_list"),
    path("titles/new/", title_setup, name="title_create"),
    path("titles/<int:pk>/", title_detail, name="title_detail"),
    path("titles/<int:pk>/edit/", title_setup, name="title_edit"),
    path("contracts/setup/", contract_waterfall_wizard, name="contract_waterfall_wizard"),
    path("avails/", avails, name="avails"),
    path("documents/", document_center, name="document_center"),
    path("settlements/", settlement_workbench, name="settlement_workbench"),
    path("statements/", statement_center, name="statement_center"),
    path("reports/", reports, name="reports"),
    path("reports/export/", reports_export_csv, name="reports_export_csv"),
    path("reports/export-360/", title_catalog_export, name="title_catalog_export"),
]
