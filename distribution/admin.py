from django import forms
from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from django.db.models import Sum
from django.http import HttpResponse
from django.urls import reverse
from django.utils.http import urlencode
from django.utils.html import format_html

from .marketplace import export_marketplace_csv, export_marketplace_xlsx
from .pdf import build_royalty_statement_pdf
from .cinema_imports import approve_import_rows, parse_cinema_report_import
from .forms import COST_ALLOCATION_FIELD_NAMES, CostScopeFormMixin
from .models import (
    AcquisitionAgreement,
    CinemaBooking,
    CinemaReportImport,
    CinemaReportImportRow,
    Cost,
    CostCategory,
    Counterparty,
    DocumentInboxItem,
    ExploitationField,
    LanguageVersion,
    RightsIssue,
    RightsWindow,
    RoyaltyStatement,
    SalesAgreement,
    SalesReport,
    Territory,
    Title,
    TitleMaterial,
    WaterfallPlan,
    WaterfallRun,
    WaterfallRunLine,
    WaterfallRunStatus,
    WaterfallStep,
)
from .waterfall_engine import calculate_waterfall_run, finalize_waterfall_run

admin.site.site_header = "FILMERP Panel Główny"
admin.site.site_title = "FILMERP Panel Główny"
admin.site.index_title = "FILMERP Panel Główny"


class RightsWindowInline(admin.TabularInline):
    model = RightsWindow
    extra = 0
    fields = (
        "source",
        "exploitation_field",
        "date_from",
        "date_to",
        "exclusive",
        "holdback",
        "status",
    )
    show_change_link = True


class SalesReportInline(admin.TabularInline):
    model = SalesReport
    extra = 0
    fields = (
        "counterparty",
        "exploitation_field",
        "period_start",
        "period_end",
        "currency",
        "gross_revenue",
        "deductions",
        "vat_withholding",
        "status",
    )
    show_change_link = True


class CostInline(admin.TabularInline):
    model = Cost
    extra = 0
    fields = ("category", "cost_date", "currency", "net_amount", "vat_amount", "recoupable", "paid")
    show_change_link = True


class TitleMaterialInline(admin.TabularInline):
    model = TitleMaterial
    extra = 0
    fields = (
        "asset_type",
        "exploitation_field",
        "language_version",
        "status",
        "required_for_release",
        "due_date",
        "delivered_at",
    )
    show_change_link = True


class CinemaReportImportRowInline(admin.TabularInline):
    model = CinemaReportImportRow
    extra = 0
    fields = (
        "status",
        "title",
        "cinema",
        "city",
        "date_from",
        "date_to",
        "screenings",
        "admissions",
        "box_office_gross",
        "distributor_share_percent",
        "confidence",
        "booking",
    )
    readonly_fields = ("confidence", "booking")
    show_change_link = True


class CostAdminForm(CostScopeFormMixin):
    class Meta:
        model = Cost
        exclude = ("exploitation_field", "applies_to_all_exploitation_fields", "exploitation_fields")


class WaterfallPlanAdminForm(forms.ModelForm):
    exploitation_fields = forms.MultipleChoiceField(
        label="Pola eksploatacji",
        choices=ExploitationField.choices,
        required=False,
        widget=forms.CheckboxSelectMultiple,
        help_text="Wybierz pola albo zaznacz 'wszystkie pola eksploatacji'.",
    )

    class Meta:
        model = WaterfallPlan
        fields = "__all__"


class WaterfallStepAdminForm(forms.ModelForm):
    cost_categories = forms.MultipleChoiceField(
        label="Kategorie kosztow",
        choices=CostCategory.choices,
        required=False,
        widget=forms.CheckboxSelectMultiple,
        help_text="Puste oznacza wszystkie kategorie kosztow recoupable.",
    )
    exploitation_fields = forms.MultipleChoiceField(
        label="Pola eksploatacji kroku",
        choices=ExploitationField.choices,
        required=False,
        widget=forms.CheckboxSelectMultiple,
        help_text="Puste oznacza zakres calego planu.",
    )

    class Meta:
        model = WaterfallStep
        fields = "__all__"


@admin.register(Title)
class TitleAdmin(admin.ModelAdmin):
    list_display = (
        "title_pl",
        "original_title",
        "production_year",
        "ean",
        "media_type",
        "status",
        "polish_premiere_date",
        "mg_advance",
        "acquisition_currency",
        "net_revenue_display",
        "recoupable_costs_display",
        "result_display",
    )
    list_filter = ("status", "production_year", "acquisition_currency", "media_type", "marketplace_condition")
    search_fields = ("title_pl", "original_title", "countries", "ean", "director", "cast", "genre")
    inlines = [RightsWindowInline, SalesReportInline, CostInline, TitleMaterialInline]
    actions = ["export_marketplace_csv_action", "export_marketplace_xlsx_action"]
    fieldsets = (
        ("Podstawowe", {"fields": ("title_pl", "original_title", "production_year", "countries", "runtime_minutes", "status", "polish_premiere_date", "producer", "imdb_url")}),
        ("Nabycie / MG", {"fields": ("mg_advance", "acquisition_currency")}),
        ("Marketplace / Allegro", {"fields": (
            "marketplace_category_id",
            "marketplace_category_name",
            "ean",
            "media_type",
            "marketplace_condition",
            "genre",
            "director",
            "cast",
            "screenwriter",
            "music_by",
            "release_edition",
            "package_type",
            "discs_count",
            "region_code",
            "audio_languages",
            "subtitle_languages",
            "dubbing_languages",
            "lector_languages",
            "age_rating",
            "color_mode",
            "aspect_ratio",
            "marketplace_description",
            "marketplace_tags",
        )}),
        ("Uwagi", {"fields": ("notes",)}),
    )

    @admin.action(description="Eksport marketplace CSV dla zaznaczonych tytulow")
    def export_marketplace_csv_action(self, request, queryset):
        response = HttpResponse(export_marketplace_csv(queryset), content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="filmerp_marketplace_titles.csv"'
        return response

    @admin.action(description="Eksport marketplace XLSX dla zaznaczonych tytulow")
    def export_marketplace_xlsx_action(self, request, queryset):
        response = HttpResponse(
            export_marketplace_xlsx(queryset),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        response["Content-Disposition"] = 'attachment; filename="filmerp_marketplace_titles.xlsx"'
        return response

    @admin.display(description="net revenue")
    def net_revenue_display(self, obj):
        return obj.net_revenue_total

    @admin.display(description="koszty recoupable")
    def recoupable_costs_display(self, obj):
        return obj.recoupable_costs_total

    @admin.display(description="wynik przed royalties")
    def result_display(self, obj):
        return obj.result_before_royalties


@admin.register(Counterparty)
class CounterpartyAdmin(admin.ModelAdmin):
    list_display = ("name", "counterparty_type", "country", "contact_person", "email", "payment_terms_days", "reporting_cycle")
    list_filter = ("counterparty_type", "country", "reporting_cycle")
    search_fields = ("name", "vat_id", "contact_person", "email")


@admin.register(Territory)
class TerritoryAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "parent")
    search_fields = ("name", "code")
    list_filter = ("parent",)


@admin.register(LanguageVersion)
class LanguageVersionAdmin(admin.ModelAdmin):
    list_display = ("name", "code")
    search_fields = ("name", "code")


@admin.register(AcquisitionAgreement)
class AcquisitionAgreementAdmin(admin.ModelAdmin):
    list_display = ("contract_number", "title", "licensor", "status", "signed_date", "rights_start", "rights_end", "currency", "mg_advance")
    list_filter = ("status", "currency", "pa_recoupable")
    search_fields = ("contract_number", "title__title_pl", "title__original_title", "licensor__name")
    autocomplete_fields = ("title", "licensor", "territories")
    inlines = [RightsWindowInline]


@admin.register(SalesAgreement)
class SalesAgreementAdmin(admin.ModelAdmin):
    list_display = (
        "contract_number",
        "title",
        "licensee",
        "status",
        "signed_date",
        "currency",
        "fixed_fee",
        "payment_due_date",
        "payment_overdue_badge",
        "invoice_issued",
        "invoice_paid",
    )
    list_filter = ("status", "currency", "reporting_cycle", "invoice_issued", "invoice_paid")
    search_fields = ("contract_number", "title__title_pl", "title__original_title", "licensee__name")
    autocomplete_fields = ("title", "licensee")
    inlines = [RightsWindowInline, SalesReportInline]

    @admin.display(description="overdue")
    def payment_overdue_badge(self, obj):
        if obj.is_payment_overdue:
            return format_html('<strong style="color:#b00020;">OVERDUE</strong>')
        return "—"


@admin.action(description="Sprawdź konflikty praw dla wybranych rekordów")
def audit_selected_rights(modeladmin, request, queryset):
    total_issues = 0
    for item in queryset:
        total_issues += len(item.audit_rights())
    messages.info(request, f"Audyt zakończony. Liczba nowych problemów/ostrzeżeń: {total_issues}.")


@admin.register(RightsWindow)
class RightsWindowAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "source",
        "exploitation_field",
        "territory_list",
        "language_list",
        "date_from",
        "date_to",
        "exclusive",
        "status",
        "open_issues_count",
    )
    list_filter = ("source", "exploitation_field", "exclusive", "holdback", "status", "territories", "language_versions")
    search_fields = ("title__title_pl", "title__original_title", "counterparty__name", "conflict_notes", "notes")
    autocomplete_fields = ("title", "counterparty", "acquisition_agreement", "sales_agreement", "territories", "language_versions")
    actions = [audit_selected_rights]
    readonly_fields = ("conflict_notes",)
    fieldsets = (
        ("Podstawowe", {"fields": ("title", "source", "status", "exploitation_field", "territories", "language_versions")}),
        ("Daty i warunki", {"fields": ("date_from", "date_to", "exclusive", "holdback")}),
        ("Powiązania", {"fields": ("counterparty", "acquisition_agreement", "sales_agreement")}),
        ("Audyt", {"fields": ("conflict_notes", "notes")}),
    )

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        issues = form.instance.audit_rights()
        if issues:
            conflicts = [i for i in issues if i.severity == "conflict"]
            if conflicts:
                messages.error(request, f"Wykryto konflikt praw: {len(conflicts)}. Sprawdź zakładkę Problemy praw/konflikty.")
            else:
                messages.warning(request, f"Wykryto ostrzeżenia: {len(issues)}. Sprawdź zakładkę Problemy praw/konflikty.")

    @admin.display(description="terytoria")
    def territory_list(self, obj):
        return ", ".join(t.name for t in obj.territories.all()) or "—"

    @admin.display(description="wersje")
    def language_list(self, obj):
        return ", ".join(l.name for l in obj.language_versions.all()) or "wszystkie/nieokreślone"

    @admin.display(description="issues")
    def open_issues_count(self, obj):
        count = obj.issues.filter(resolved=False).count()
        if count:
            return format_html('<strong style="color:#b00020;">{}</strong>', count)
        return 0


@admin.register(RightsIssue)
class RightsIssueAdmin(admin.ModelAdmin):
    list_display = ("severity", "issue_type", "rights_window", "conflicting_window", "resolved", "created_at")
    list_filter = ("severity", "issue_type", "resolved")
    search_fields = ("rights_window__title__title_pl", "message")
    autocomplete_fields = ("rights_window", "conflicting_window")
    readonly_fields = ("created_at", "updated_at")


@admin.register(CinemaBooking)
class CinemaBookingAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "cinema",
        "city",
        "date_from",
        "date_to",
        "screenings",
        "admissions",
        "box_office_gross",
        "distributor_share_amount_display",
        "invoice_issued",
    )
    list_filter = ("date_from", "invoice_issued")
    search_fields = ("title__title_pl", "cinema__name", "city")
    autocomplete_fields = ("title", "cinema")

    @admin.display(description="udział dystrybutora")
    def distributor_share_amount_display(self, obj):
        return obj.distributor_share_amount

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        obj.sync_sales_report()


@admin.action(description="Rozpoznaj raport kina PDF/XLSX")
def parse_selected_cinema_report_imports(modeladmin, request, queryset):
    parsed = 0
    for report_import in queryset:
        try:
            parsed += parse_cinema_report_import(report_import)
        except ValueError as exc:
            messages.warning(request, f"Pominieto {report_import}: {exc}")
    messages.success(request, f"Rozpoznano wiersze do weryfikacji: {parsed}.")


@admin.action(description="Zaakceptuj zweryfikowane wiersze i utworz bookingi")
def approve_selected_cinema_import_rows(modeladmin, request, queryset):
    imported, skipped = approve_import_rows(queryset)
    if skipped:
        messages.warning(request, f"Zaimportowano {imported}, pominieto {skipped}. Wiersze pominiete wymagaja tytulu, kina i dat.")
    else:
        messages.success(request, f"Zaimportowano bookingi: {imported}.")


@admin.action(description="Zaakceptuj wszystkie poprawne wiersze z importu i utworz bookingi")
def approve_all_valid_rows_for_selected_imports(modeladmin, request, queryset):
    rows = CinemaReportImportRow.objects.filter(report_import__in=queryset)
    imported, skipped = approve_import_rows(rows)
    if skipped:
        messages.warning(request, f"Zaimportowano {imported}, pominieto {skipped}. Pominiete wiersze wymagaja poprawy danych albo byly juz zaimportowane.")
    else:
        messages.success(request, f"Zaimportowano bookingi: {imported}.")


@admin.register(CinemaReportImport)
class CinemaReportImportAdmin(admin.ModelAdmin):
    list_display = ("original_filename", "source_file", "status", "parsed_at", "imported_at", "rows_link", "created_at")
    list_filter = ("status", "created_at", "parsed_at", "imported_at")
    search_fields = ("original_filename", "source_file", "parser_notes")
    readonly_fields = ("parsed_at", "imported_at", "parser_notes", "created_at", "updated_at")
    inlines = [CinemaReportImportRowInline]
    actions = [parse_selected_cinema_report_imports, approve_all_valid_rows_for_selected_imports]

    @admin.display(description="wiersze")
    def rows_link(self, obj):
        count = obj.rows.count()
        url = reverse("admin:distribution_cinemareportimportrow_changelist")
        query = urlencode({"report_import__id__exact": obj.pk})
        return format_html('<a href="{}?{}">{} wierszy</a>', url, query, count)

    def save_model(self, request, obj, form, change):
        if obj.source_file and not obj.original_filename:
            obj.original_filename = obj.source_file.name.split("/")[-1]
        super().save_model(request, obj, form, change)


@admin.register(CinemaReportImportRow)
class CinemaReportImportRowAdmin(admin.ModelAdmin):
    list_display = (
        "report_import",
        "status",
        "title",
        "cinema",
        "date_from",
        "date_to",
        "screenings",
        "admissions",
        "box_office_gross",
        "confidence",
        "booking",
    )
    list_filter = ("status", "date_from", "cinema", "title")
    search_fields = ("title__title_pl", "cinema__name", "city", "source_line", "notes")
    autocomplete_fields = ("report_import", "title", "cinema", "booking")
    readonly_fields = ("raw_payload", "booking", "created_at", "updated_at")
    actions = [approve_selected_cinema_import_rows]
    fieldsets = (
        ("Status", {"fields": ("report_import", "status", "confidence", "booking")}),
        ("Dane do akceptacji", {"fields": ("title", "cinema", "city", "date_from", "date_to", "screenings", "admissions", "box_office_gross", "distributor_share_percent", "currency")}),
        ("Zrodlo i uwagi", {"fields": ("source_line", "raw_payload", "notes")}),
    )

    def save_model(self, request, obj, form, change):
        if obj.status == "imported" and not obj.booking_id:
            try:
                obj.approve()
                messages.success(request, "Utworzono booking kinowy dla zaakceptowanego wiersza.")
                return
            except ValidationError as exc:
                messages.error(request, f"Nie utworzono bookingu: {exc}")
                obj.status = "needs_review"
        super().save_model(request, obj, form, change)


@admin.register(SalesReport)
class SalesReportAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "counterparty",
        "exploitation_field",
        "territory",
        "period_start",
        "period_end",
        "currency",
        "gross_revenue",
        "net_revenue_display",
        "status",
    )
    list_filter = ("exploitation_field", "territory", "currency", "status", "period_end")
    search_fields = ("title__title_pl", "title__original_title", "counterparty__name", "source_reference")
    autocomplete_fields = ("title", "counterparty", "sales_agreement", "territory")

    @admin.display(description="net revenue")
    def net_revenue_display(self, obj):
        return obj.net_revenue


@admin.register(DocumentInboxItem)
class DocumentInboxItemAdmin(admin.ModelAdmin):
    list_display = ("original_filename", "document_type", "status", "classification_confidence", "title", "counterparty", "created_at")
    list_filter = ("document_type", "status", "created_at")
    search_fields = ("original_filename", "file_hash", "title__title_pl", "counterparty__name", "notes")
    readonly_fields = (
        "file_hash", "content_type", "file_size", "classification_confidence", "extracted_data",
        "cinema_import", "cost", "uploaded_by", "reviewed_by", "processed_at", "created_at", "updated_at",
    )
    autocomplete_fields = ("title", "counterparty")


@admin.register(Cost)
class CostAdmin(admin.ModelAdmin):
    form = CostAdminForm
    list_display = ("title", "category", "supplier", "cost_date", "currency", "net_amount", "gross_amount_display", "waterfall_scope_display", "recouped_display", "outstanding_display", "recoupable", "paid")
    list_filter = ("category", "currency", "recoupable", "scope_mode", "paid", "cost_date")
    search_fields = ("title__title_pl", "title__original_title", "supplier__name", "notes")
    autocomplete_fields = ("title", "supplier")
    fieldsets = (
        ("Podstawowe", {"fields": ("title", "category", "supplier", "cost_date", "currency", "net_amount", "vat_amount", "paid")}),
        ("P&A / waterfall / recoupment", {"fields": ("recoupable", "scope_mode", "scope_fields", "allocation_percentages", *COST_ALLOCATION_FIELD_NAMES)}),
        ("Pliki i uwagi", {"fields": ("invoice_file", "notes")}),
    )

    class Media:
        js = ("distribution/cost-scope.js",)
        css = {"all": ("distribution/cost-scope.css",)}

    @admin.display(description="kwota brutto")
    def gross_amount_display(self, obj):
        return obj.gross_amount

    @admin.display(description="waterfall fields")
    def waterfall_scope_display(self, obj):
        return obj.scope_label

    @admin.display(description="odzyskano")
    def recouped_display(self, obj):
        return obj.recouped_amount

    @admin.display(description="pozostało")
    def outstanding_display(self, obj):
        return obj.outstanding_recoupment


@admin.register(TitleMaterial)
class TitleMaterialAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "asset_type",
        "exploitation_field",
        "language_version",
        "status",
        "required_for_release",
        "due_date",
        "delivered_at",
        "overdue_badge",
    )
    list_filter = ("asset_type", "status", "required_for_release", "exploitation_field", "due_date")
    search_fields = ("title__title_pl", "title__original_title", "supplier__name", "external_reference", "notes")
    autocomplete_fields = ("title", "language_version", "supplier")
    fieldsets = (
        ("Materiał", {"fields": ("title", "asset_type", "exploitation_field", "language_version", "status", "required_for_release")}),
        ("Terminy", {"fields": ("due_date", "delivered_at")}),
        ("Dostawca i pliki", {"fields": ("supplier", "file", "external_reference", "notes")}),
    )

    @admin.display(description="po terminie")
    def overdue_badge(self, obj):
        if obj.is_overdue:
            return format_html('<strong style="color:#b00020;">TAK</strong>')
        return ""


class WaterfallStepInline(admin.TabularInline):
    model = WaterfallStep
    form = WaterfallStepAdminForm
    extra = 0
    fields = (
        "phase", "sort_order", "name", "step_type", "allocation_mode", "beneficiary",
        "percentage", "fixed_amount", "target_amount", "premium_percent",
        "include_title_mg", "include_recoupable_costs", "active",
    )
    autocomplete_fields = ("beneficiary",)
    show_change_link = True


@admin.register(WaterfallPlan)
class WaterfallPlanAdmin(admin.ModelAdmin):
    form = WaterfallPlanAdminForm
    list_display = ("title", "name", "version", "status", "currency", "scope_display", "effective_from", "effective_to")
    list_filter = ("status", "currency", "applies_to_all_exploitation_fields")
    search_fields = ("title__title_pl", "title__original_title", "name", "notes")
    autocomplete_fields = ("title",)
    inlines = (WaterfallStepInline,)

    @admin.display(description="pola eksploatacji")
    def scope_display(self, obj):
        if obj.applies_to_all_exploitation_fields:
            return "wszystkie"
        labels = dict(ExploitationField.choices)
        return ", ".join(labels.get(value, value) for value in obj.exploitation_fields)


@admin.register(WaterfallStep)
class WaterfallStepAdmin(admin.ModelAdmin):
    form = WaterfallStepAdminForm
    list_display = ("plan", "phase", "sort_order", "name", "step_type", "allocation_mode", "beneficiary", "active")
    list_filter = ("step_type", "allocation_mode", "active", "plan__currency")
    search_fields = ("plan__title__title_pl", "plan__name", "name", "beneficiary__name", "notes")
    autocomplete_fields = ("plan", "beneficiary")
    fieldsets = (
        ("Kolejnosc", {"fields": ("plan", "phase", "sort_order", "name", "active")}),
        ("Sposob rozliczenia", {"fields": ("step_type", "allocation_mode", "beneficiary", "percentage", "fixed_amount", "target_amount", "premium_percent", "opening_recouped", "cap_amount")}),
        ("MG i koszty", {"fields": ("include_title_mg", "include_recoupable_costs", "cost_categories", "exploitation_fields")}),
        ("Podstawa umowna", {"fields": ("notes",)}),
    )

    def has_module_permission(self, request):
        return False


class WaterfallRunLineInline(admin.TabularInline):
    model = WaterfallRunLine
    extra = 0
    can_delete = False
    readonly_fields = (
        "sequence", "phase", "step", "beneficiary", "opening_available", "calculation_base",
        "allocated_amount", "closing_available", "opening_recoupment", "closing_recoupment",
    )

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(WaterfallRun)
class WaterfallRunAdmin(admin.ModelAdmin):
    list_display = ("plan", "period_start", "period_end", "status", "net_revenue", "allocated_amount", "closing_available", "calculated_at")
    list_filter = ("status", "plan__currency", "period_end")
    search_fields = ("plan__title__title_pl", "plan__name", "notes")
    autocomplete_fields = ("plan",)
    readonly_fields = ("gross_revenue", "net_revenue", "allocated_amount", "closing_available", "calculated_at", "finalized_at", "finalized_by", "calculation_snapshot")
    actions = ("recalculate_selected", "finalize_selected")
    inlines = (WaterfallRunLineInline,)

    @admin.action(description="Przelicz zaznaczone robocze okresy")
    def recalculate_selected(self, request, queryset):
        count = 0
        for run in queryset.filter(status=WaterfallRunStatus.DRAFT):
            calculate_waterfall_run(run)
            count += 1
        messages.success(request, f"Przeliczono okresy: {count}.")

    @admin.action(description="Zatwierdź zaznaczone rozliczenia okresów")
    def finalize_selected(self, request, queryset):
        count = 0
        for run in queryset.filter(status=WaterfallRunStatus.DRAFT):
            if not run.calculated_at:
                calculate_waterfall_run(run)
            finalize_waterfall_run(run, request.user)
            count += 1
        messages.success(request, f"Zatwierdzono rozliczenia okresów: {count}.")


@admin.register(WaterfallRunLine)
class WaterfallRunLineAdmin(admin.ModelAdmin):
    list_display = ("run", "sequence", "phase", "step", "beneficiary", "allocated_amount", "closing_recoupment")
    list_filter = ("run__status", "run__plan__currency", "phase")
    search_fields = ("run__plan__title__title_pl", "step__name", "beneficiary__name")
    readonly_fields = [field.name for field in WaterfallRunLine._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_module_permission(self, request):
        return False


@admin.register(RoyaltyStatement)
class RoyaltyStatementAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "recipient",
        "period_start",
        "period_end",
        "currency",
        "gross_revenue_display",
        "net_revenue_display",
        "recoupable_costs_display",
        "distributor_fee_display",
        "amount_due_display",
        "status",
        "pdf_link",
    )
    list_filter = ("status", "currency", "period_end", "waterfall_plan")
    search_fields = ("title__title_pl", "title__original_title", "recipient__name")
    autocomplete_fields = ("title", "recipient", "waterfall_plan", "waterfall_run")
    readonly_fields = ("calculation_snapshot", "calculated_at", "locked_at")
    actions = ["generate_pdf_for_selected"]

    @admin.action(description="Wygeneruj PDF royalty statement")
    def generate_pdf_for_selected(self, request, queryset):
        count = 0
        for statement in queryset:
            statement.freeze_calculation(lock=True)
            pdf_file = build_royalty_statement_pdf(statement)
            statement.statement_file.save(pdf_file.name, pdf_file, save=True)
            count += 1
        messages.success(request, f"Wygenerowano PDF dla statementow: {count}.")

    @admin.display(description="gross")
    def gross_revenue_display(self, obj):
        return obj.gross_revenue

    @admin.display(description="net")
    def net_revenue_display(self, obj):
        return obj.net_revenue

    @admin.display(description="koszty recoupable")
    def recoupable_costs_display(self, obj):
        return obj.recoupable_costs

    @admin.display(description="prowizja dystrybutora")
    def distributor_fee_display(self, obj):
        return obj.distributor_fee_amount

    @admin.display(description="do wypłaty")
    def amount_due_display(self, obj):
        return obj.amount_due

    @admin.display(description="PDF")
    def pdf_link(self, obj):
        if obj.statement_file:
            return format_html('<a href="{}">pobierz</a>', obj.statement_file.url)
        return "brak"
