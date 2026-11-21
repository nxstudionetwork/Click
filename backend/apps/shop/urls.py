from django.urls import path

from . import views

# Public Shopping discovery, mounted at /api/v1/shop/.
public_urls = [
    path("home", views.ShopHomeView.as_view(), name="shop-home"),
    path("feed", views.ShopFeedView.as_view(), name="shop-feed"),
    path("search", views.ShopSearchView.as_view(), name="shop-search"),
    path("suggest", views.ShopSuggestView.as_view(), name="shop-suggest"),
    path("categories", views.ShopCategoriesView.as_view(), name="shop-categories"),
    path("categories/<slug:slug>", views.ShopCategoryView.as_view(), name="shop-category"),
    path("brands", views.ShopBrandsView.as_view(), name="shop-brands"),
    path("products/<uuid:pk>", views.ShopProductView.as_view(), name="shop-product"),
    path("products/<uuid:pk>/reviews", views.ShopProductReviewsView.as_view(), name="shop-product-reviews"),
    path("compare", views.ShopCompareView.as_view(), name="shop-compare"),
    path("visual-search", views.VisualSearchView.as_view(), name="shop-visual-search"),
]

# Customer-owned Shopping actions, mounted under /api/v1/customer/.
customer_urls = [
    path("shop/products/<uuid:pk>/review", views.MyProductReviewView.as_view(), name="shop-my-review"),
]
