from django import forms

from .models import (
    CinemaReportImport,
    Cost,
    Counterparty,
    CounterpartyType,
    DocumentInboxItem,
)


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
