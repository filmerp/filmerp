from django import forms

from .models import CinemaReportImport, Cost, Counterparty, CounterpartyType


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
