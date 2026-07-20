from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group

from .models import SecurityProfile


User = get_user_model()
SYSTEM_ROLE_NAMES = ["administrator", "legal", "sales", "finance", "readonly"]


class UserAccountForm(forms.ModelForm):
    roles = forms.ModelMultipleChoiceField(
        label="Role",
        queryset=Group.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )
    mfa_required = forms.BooleanField(label="Wymagaj MFA", required=False)
    force_password_change = forms.BooleanField(label="Wymagaj zmiany hasła przy następnym użyciu konta", required=False)

    class Meta:
        model = User
        fields = ["username", "first_name", "last_name", "email", "is_active"]
        labels = {
            "username": "Nazwa uzytkownika",
            "first_name": "Imie",
            "last_name": "Nazwisko",
            "email": "E-mail",
            "is_active": "Konto aktywne",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["roles"].queryset = Group.objects.filter(name__in=SYSTEM_ROLE_NAMES).order_by("name")
        self.fields["email"].required = True
        if self.instance and self.instance.pk:
            self.fields["roles"].initial = self.instance.groups.filter(name__in=SYSTEM_ROLE_NAMES)
            profile, _ = SecurityProfile.objects.get_or_create(user=self.instance)
            self.fields["mfa_required"].initial = profile.mfa_required
            self.fields["force_password_change"].initial = profile.force_password_change

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        conflict = User.objects.filter(email__iexact=email)
        if self.instance and self.instance.pk:
            conflict = conflict.exclude(pk=self.instance.pk)
        if conflict.exists():
            raise forms.ValidationError("Ten adres e-mail jest juz przypisany do innego konta.")
        return email

    def clean_roles(self):
        roles = self.cleaned_data["roles"]
        if not roles:
            raise forms.ValidationError("Wybierz co najmniej jedna role.")
        return roles

    def save(self, commit=True):
        user = super().save(commit=False)
        selected_roles = list(self.cleaned_data["roles"])
        user.is_staff = user.is_superuser or any(group.name == "administrator" for group in selected_roles)
        if commit:
            user.save()
            user.groups.set(selected_roles)
            profile, _ = SecurityProfile.objects.get_or_create(user=user)
            profile.mfa_required = self.cleaned_data["mfa_required"] or any(group.name == "administrator" for group in selected_roles)
            profile.force_password_change = self.cleaned_data["force_password_change"]
            profile.save(update_fields=["mfa_required", "force_password_change", "updated_at"])
        return user


class UserCreateForm(UserAccountForm):
    send_invitation = forms.BooleanField(label="Wyslij zaproszenie e-mail", required=False, initial=True)

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_unusable_password()
        if commit:
            user.save()
            selected_roles = list(self.cleaned_data["roles"])
            user.groups.set(selected_roles)
            user.is_staff = user.is_superuser or any(group.name == "administrator" for group in selected_roles)
            user.save(update_fields=["is_staff"])
            profile, _ = SecurityProfile.objects.get_or_create(user=user)
            profile.mfa_required = self.cleaned_data["mfa_required"] or any(group.name == "administrator" for group in selected_roles)
            profile.force_password_change = self.cleaned_data["force_password_change"]
            profile.save(update_fields=["mfa_required", "force_password_change", "updated_at"])
        return user


class DeactivateUserForm(forms.Form):
    reason = forms.CharField(
        label="Powod dezaktywacji",
        max_length=255,
        widget=forms.Textarea(attrs={"rows": 3}),
    )
