from django.core.management.base import BaseCommand
from django.db import transaction

from accounts.models import Organisation, User
from breaks.models import BreakPolicy

DEMO_PASSWORD = "password123"

DEMO_ORGS = {
    "Acme Ltd": "acme",
    "Globex Corp": "globex",
}
EMPLOYEE_NAMES = [
    ("Eric", "Employee"), ("Emma", "Employee"), ("Ethan", "Employee"),
    ("Eva", "Employee"), ("Elijah", "Employee"), ("Ella", "Employee"),
]


class Command(BaseCommand):
    help = "Create two demo organisations, each with 1 manager and 2 employees."

    @transaction.atomic  # all-or-nothing: a failure halfway leaves no partial data
    def handle(self, *args, **options):
        for org_name, prefix in DEMO_ORGS.items():
            org, _ = Organisation.objects.get_or_create(name=org_name)
            BreakPolicy.objects.get_or_create(organisation=org)

            people = [(f"{prefix}_manager", User.Role.MANAGER, "Maria", "Manager")] + [
                (f"{prefix}_emp{i}", User.Role.EMPLOYEE, first, last)
                for i, (first, last) in enumerate(EMPLOYEE_NAMES, start=1)
            ]
            for username, role, first, last in people:
                user, created = User.objects.get_or_create(
                    username=username,
                    defaults={"organisation": org, "role": role,
                              "first_name": first, "last_name": last},
                )
                if created:
                    user.set_password(DEMO_PASSWORD)  # hashes the password
                    user.save(update_fields=["password"])

        self.stdout.write(self.style.SUCCESS(
            f"Demo data ready. All demo users have password '{DEMO_PASSWORD}'."
        ))
        