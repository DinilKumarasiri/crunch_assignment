from django.contrib.auth.models import AbstractUser
from django.db import models


class Organisation(models.Model):
    """A tenant. Every user and break request belongs to exactly one."""

    name = models.CharField(max_length=200, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]  # fine here: only ~50 rows

    def __str__(self):
        return self.name


class User(AbstractUser):
    """Custom user: Django's built-in user + organisation + role."""

    class Role(models.TextChoices):
        MANAGER = "MANAGER", "Manager"
        EMPLOYEE = "EMPLOYEE", "Employee"

    # null=True only so that superusers (site admins) can exist without a tenant.
    # Step 5 adds a DB rule: normal users MUST have an organisation.
    organisation = models.ForeignKey(
        Organisation,
        on_delete=models.PROTECT,
        related_name="users",
        null=True,
        blank=True,
    )
    role = models.CharField(
        max_length=10,
        choices=Role.choices,
        default=Role.EMPLOYEE,
    )

    @property
    def is_manager(self):
        return self.role == self.Role.MANAGER

    @property
    def is_employee(self):
        return self.role == self.Role.EMPLOYEE