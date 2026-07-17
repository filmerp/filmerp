from django.urls import path

from .views import avails, contract_waterfall_wizard, dashboard, document_center, reports, reports_export_csv, settlement_workbench, statement_center, title_detail, title_list

app_name = "distribution"

urlpatterns = [
    path("", dashboard, name="dashboard"),
    path("titles/", title_list, name="title_list"),
    path("titles/<int:pk>/", title_detail, name="title_detail"),
    path("contracts/setup/", contract_waterfall_wizard, name="contract_waterfall_wizard"),
    path("avails/", avails, name="avails"),
    path("documents/", document_center, name="document_center"),
    path("settlements/", settlement_workbench, name="settlement_workbench"),
    path("statements/", statement_center, name="statement_center"),
    path("reports/", reports, name="reports"),
    path("reports/export/", reports_export_csv, name="reports_export_csv"),
]
