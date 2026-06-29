import re
from django.core.exceptions import ValidationError


class StrongPasswordValidator:
    def validate(self, password, user=None):
        if not (re.search(r"[A-Z]", password) and re.search(r"[a-z]", password) and re.search(r"\d", password)):
            raise ValidationError("A senha deve conter letra maiúscula, minúscula e número.")

    def get_help_text(self):
        return "Use ao menos uma letra maiúscula, uma minúscula e um número."
