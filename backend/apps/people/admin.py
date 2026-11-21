from django.contrib import admin

from .models import Designation, Employee

admin.site.register(Designation)


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ("full_name", "employee_id", "designation", "department", "org_unit", "status")
    list_filter = ("status", "department")
    search_fields = ("full_name", "employee_id", "work_email")
    raw_id_fields = ("user", "manager")
