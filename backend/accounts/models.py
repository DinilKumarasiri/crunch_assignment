from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models import Q

# from django.contrib.postgres.indexes import GinIndex, OpClass
# from django.db.models.functions import Upper


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

    organisation = models.ForeignKey(
        Organisation,
        on_delete=models.PROTECT,
        related_name="users",
        null=True,
        blank=True,
        db_index=False,  # covered by the (organisation, role) index below
    )
    role = models.CharField(
        max_length=10,
        choices=Role.choices,
        default=Role.EMPLOYEE,
    )

    class Meta(AbstractUser.Meta):
        indexes = [
            models.Index(fields=["organisation", "role"], name="user_org_role_idx"),
            # Trigram indexes: fast case-insensitive "contains" search on names
            # GinIndex(OpClass(Upper("first_name"), name="gin_trgm_ops"), name="user_first_name_trgm"),
            # GinIndex(OpClass(Upper("last_name"), name="gin_trgm_ops"), name="user_last_name_trgm"),
            # GinIndex(OpClass(Upper("username"), name="gin_trgm_ops"), name="user_username_trgm"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(is_superuser=True) | Q(organisation__isnull=False),
                name="user_requires_organisation",
                violation_error_message="Non-admin users must belong to an organisation.",
            ),
        ]

    @property
    def is_manager(self):
        return self.role == self.Role.MANAGER

    @property
    def is_employee(self):
        return self.role == self.Role.EMPLOYEE