"""/api/v1/os/procurement/* — Procurement workspace."""

from django.urls import path

from . import views as v

urlpatterns = [
    path("nav", v.NavView.as_view()),
    path("home", v.HomeView.as_view()),
    path("lookups", v.LookupsView.as_view()),
    path("policies", v.PoliciesView.as_view()),
    path("requests", v.RequestsView.as_view()),
    path("requests/<uuid:pk>", v.RequestDetailView.as_view()),
    path("requests/<uuid:pk>/<slug:action>", v.RequestDetailView.as_view()),
    path("sourcing", v.SourcingView.as_view()),
    path("sourcing/<uuid:pk>", v.SourcingDetailView.as_view()),
    path("sourcing/<uuid:pk>/<slug:action>", v.SourcingDetailView.as_view()),
    path("quotations/<uuid:pk>/<slug:action>", v.QuotationActionView.as_view()),
    path("orders", v.OrdersView.as_view()),
    path("orders/<uuid:pk>", v.OrderDetailView.as_view()),
    path("orders/<uuid:pk>/<slug:action>", v.OrderDetailView.as_view()),
    path("receipts", v.ReceiptsView.as_view()),
    path("receipts/<uuid:pk>/<slug:action>", v.ReceiptActionView.as_view()),
    path("suppliers", v.SuppliersView.as_view()),
    path("suppliers/duplicates", v.DuplicatesView.as_view()),
    path("suppliers/performance", v.SupplierPerformanceView.as_view()),
    path("suppliers/<uuid:pk>", v.SupplierDetailView.as_view()),
    path("suppliers/<uuid:pk>/<slug:action>", v.SupplierDetailView.as_view()),
    path("contracts", v.ContractsView.as_view()),
    path("contracts/<uuid:pk>/<slug:action>", v.ContractActionView.as_view()),
    path("recurring", v.RecurringView.as_view()),
    path("exceptions", v.ExceptionsView.as_view()),
    path("exceptions/<uuid:pk>/<slug:action>", v.ExceptionActionView.as_view()),
    path("conflicts", v.ConflictsView.as_view()),
    path("conflicts/<uuid:pk>", v.ConflictDetailView.as_view()),
    path("analytics", v.AnalyticsView.as_view()),
    path("settings", v.SettingsView.as_view()),
]
