from django.contrib import admin

from .models import Department, Organization, OrgUnit, Team

admin.site.register(Organization)


@admin.register(OrgUnit)
class OrgUnitAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "unit_type", "parent", "is_active")
    list_filter = ("unit_type", "organization")
    search_fields = ("name", "code")


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "org_unit", "parent")


admin.site.register(Team)
