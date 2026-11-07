import pytest

pytestmark = pytest.mark.django_db


def test_wishlist_add_list_dedupe_remove(auth_api, store, products):
    r = auth_api.post("/api/v1/customer/wishlist", {"productId": str(products[0].id)})
    assert r.status_code == 201 and r.json()["kind"] == "product"
    assert auth_api.post("/api/v1/customer/wishlist", {"productId": str(products[0].id)}).status_code == 200
    auth_api.post("/api/v1/customer/wishlist", {"storeId": str(store.id)})
    items = auth_api.get("/api/v1/customer/wishlist").json()
    assert sorted(i["kind"] for i in items) == ["product", "store"]
    assert auth_api.delete(f"/api/v1/customer/wishlist/{r.json()['id']}").status_code == 204
    assert len(auth_api.get("/api/v1/customer/wishlist").json()) == 1


def test_wishlist_validation_and_isolation(api, customer, other_customer, store):
    api.force_authenticate(customer)
    assert api.post("/api/v1/customer/wishlist", {}).status_code == 400
    item = api.post("/api/v1/customer/wishlist", {"storeId": str(store.id)}).json()
    api.force_authenticate(other_customer)
    assert api.get("/api/v1/customer/wishlist").json() == []
    assert api.delete(f"/api/v1/customer/wishlist/{item['id']}").status_code == 404
    api.force_authenticate(None)
    assert api.get("/api/v1/customer/wishlist").status_code == 401
