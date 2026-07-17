from django import forms

from .models import (
    AgreementStatus,
    AcquisitionAgreement,
    CinemaReportImport,
    Cost,
    CostCategory,
    Counterparty,
    CounterpartyType,
    Currency,
    DocumentInboxItem,
    ExploitationField,
    Territory,
    Title,
)


class ContractWaterfallWizardForm(forms.Form):
    title = forms.ModelChoiceField(label="Tytuł", queryset=Title.objects.none())
    contract_number = forms.CharField(label="Numer umowy", max_length=120, required=False)
    licensor = forms.ModelChoiceField(label="Licencjodawca / producent", queryset=Counterparty.objects.none())
    distributor = forms.ModelChoiceField(label="Dystrybutor", queryset=Counterparty.objects.none())
    signed_date = forms.DateField(label="Data podpisania", required=False, widget=forms.DateInput(attrs={"type": "date"}))
    rights_start = forms.DateField(label="Początek praw", required=False, widget=forms.DateInput(attrs={"type": "date"}))
    rights_end = forms.DateField(label="Koniec praw", required=False, widget=forms.DateInput(attrs={"type": "date"}))
    territories = forms.ModelMultipleChoiceField(
        label="Terytoria", queryset=Territory.objects.none(), required=False,
        widget=forms.CheckboxSelectMultiple,
    )
    currency = forms.ChoiceField(label="Waluta", choices=Currency.choices, initial=Currency.PLN)
    mg_advance = forms.DecimalField(label="MG do odzyskania", min_value=0, max_digits=14, decimal_places=2, initial=0)
    distributor_fee_percent = forms.DecimalField(label="Fee dystrybutora %", min_value=0, max_value=100, max_digits=5, decimal_places=2, initial=10)
    pa_recoupable = forms.BooleanField(label="Odzyskuj koszty P&A", required=False, initial=True)
    pa_cost_categories = forms.MultipleChoiceField(
        label="Kategorie kosztów P&A", choices=CostCategory.choices, required=False,
        widget=forms.CheckboxSelectMultiple,
    )
    applies_to_all_exploitation_fields = forms.BooleanField(label="Wszystkie pola eksploatacji", required=False, initial=True)
    exploitation_fields = forms.MultipleChoiceField(
        label="Wybrane pola eksploatacji", choices=ExploitationField.choices, required=False,
        widget=forms.CheckboxSelectMultiple,
    )
    licensor_share_percent = forms.DecimalField(label="Udział licencjodawcy po recoupment %", min_value=0, max_value=100, max_digits=5, decimal_places=2, initial=50)
    status = forms.ChoiceField(label="Status umowy", choices=AgreementStatus.choices, initial=AgreementStatus.SIGNED)
    notes = forms.CharField(label="Uwagi / podstawa umowna", required=False, widget=forms.Textarea(attrs={"rows": 3}))

    def __init__(self, *args, title=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["title"].queryset = Title.objects.order_by("title_pl")
        self.fields["licensor"].queryset = Counterparty.objects.order_by("name")
        self.fields["distributor"].queryset = Counterparty.objects.order_by("name")
        self.fields["territories"].queryset = Territory.objects.order_by("name")
        self.fields["pa_cost_categories"].initial = [
            CostCategory.PA, CostCategory.DIGITAL_MARKETING, CostCategory.PR,
            CostCategory.KEY_ART, CostCategory.TRAILER, CostCategory.PROMO_MATERIALS,
        ]
        if title:
            self.fields["title"].initial = title
            self.fields["currency"].initial = title.acquisition_currency
            self.fields["mg_advance"].initial = title.mg_advance
            self.fields["licensor"].initial = title.producer_id

    def clean(self):
        cleaned = super().clean()
        start, end = cleaned.get("rights_start"), cleaned.get("rights_end")
        if start and end and start > end:
            self.add_error("rights_end", "Koniec praw nie może być wcześniejszy niż początek.")
        if not cleaned.get("applies_to_all_exploitation_fields") and not cleaned.get("exploitation_fields"):
            self.add_error("exploitation_fields", "Wybierz pola albo zaznacz wszystkie pola eksploatacji.")
        if cleaned.get("pa_recoupable") and not cleaned.get("pa_cost_categories"):
            self.add_error("pa_cost_categories", "Wybierz co najmniej jedną kategorię kosztów P&A.")
        return cleaned


class TitleSetupForm(forms.ModelForm):
    class Meta:
        model = Title
        fields = (
            "title_pl", "original_title", "production_year", "status", "producer",
            "countries", "runtime_minutes", "polish_premiere_date", "genre",
            "director", "cast", "screenwriter", "music_by",
            "acquisition_currency", "mg_advance", "ean", "media_type",
            "age_rating", "audio_languages", "subtitle_languages",
            "dubbing_languages", "lector_languages", "marketplace_description", "notes",
        )
        widgets = {
            "polish_premiere_date": forms.DateInput(attrs={"type": "date"}),
            "cast": forms.Textarea(attrs={"rows": 3}),
            "marketplace_description": forms.Textarea(attrs={"rows": 4}),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }


class CinemaReportUploadForm(forms.ModelForm):
    class Meta:
        model = CinemaReportImport
        fields = ("source_file",)
        widgets = {
            "source_file": forms.ClearableFileInput(attrs={"accept": ".pdf,.xlsx"}),
        }


class CostInvoiceUploadForm(forms.ModelForm):
    supplier_name = forms.CharField(label="Dostawca", max_length=255, required=False)

    class Meta:
        model = Cost
        fields = (
            "cost_date",
            "currency",
            "category",
            "net_amount",
            "vat_amount",
            "recoupable",
            "applies_to_all_exploitation_fields",
            "exploitation_field",
            "invoice_file",
        )
        widgets = {
            "cost_date": forms.DateInput(attrs={"type": "date"}),
            "invoice_file": forms.ClearableFileInput(attrs={"accept": ".pdf,.jpg,.jpeg,.png"}),
        }

    def __init__(self, *args, title=None, currency=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.title = title
        self.fields["invoice_file"].required = True
        if currency:
            self.fields["currency"].initial = currency

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.title = self.title
        supplier_name = self.cleaned_data.get("supplier_name", "").strip()
        if supplier_name:
            instance.supplier, _ = Counterparty.objects.get_or_create(
                name=supplier_name,
                defaults={"counterparty_type": CounterpartyType.SUPPLIER},
            )
        if commit:
            instance.save()
        return instance


class DocumentUploadForm(forms.ModelForm):
    class Meta:
        model = DocumentInboxItem
        fields = ("source_file",)
        widgets = {
            "source_file": forms.ClearableFileInput(
                attrs={"accept": ".pdf,.xlsx,.jpg,.jpeg,.png,.webp"}
            ),
        }

    def clean_source_file(self):
        source_file = self.cleaned_data["source_file"]
        if source_file.size > 25 * 1024 * 1024:
            raise forms.ValidationError("Maksymalny rozmiar dokumentu to 25 MB.")
        return source_file


class DocumentClassificationForm(forms.ModelForm):
    class Meta:
        model = DocumentInboxItem
        fields = ("document_type",)


class DocumentCostForm(forms.ModelForm):
    supplier_name = forms.CharField(label="Dostawca", max_length=255, required=False)

    class Meta:
        model = Cost
        fields = (
            "title",
            "cost_date",
            "currency",
            "category",
            "net_amount",
            "vat_amount",
            "recoupable",
            "applies_to_all_exploitation_fields",
            "exploitation_field",
        )
        widgets = {
            "cost_date": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, document=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.document = document
        if not document or self.is_bound:
            return
        extracted = document.extracted_data or {}
        self.fields["title"].initial = document.title_id or extracted.get("title_id")
        self.fields["supplier_name"].initial = extracted.get("supplier_name", "")
        for field_name in ("cost_date", "currency", "net_amount", "vat_amount"):
            if extracted.get(field_name) not in (None, ""):
                self.fields[field_name].initial = extracted[field_name]

    def save(self, commit=True):
        instance = super().save(commit=False)
        supplier_name = self.cleaned_data.get("supplier_name", "").strip()
        if supplier_name:
            instance.supplier, _ = Counterparty.objects.get_or_create(
                name=supplier_name,
                defaults={"counterparty_type": CounterpartyType.SUPPLIER},
            )
        if self.document:
            instance.invoice_file.name = self.document.source_file.name
            reference = f"Centrum dokumentow #{self.document.pk}"
            instance.notes = f"{reference}. {instance.notes}".strip()
        if commit:
            instance.save()
        return instance
