import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import create_app  # noqa: E402


class CanteenTests(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.app = create_app({"DB_PATH": self.path, "TESTING": True, "SLOT_CAPACITY": 2})
        self.student = self.app.test_client()
        self.staff = self.app.test_client()
        self.staff.post("/api/login", json={"email": "staff@canteen.local", "password": "staff123"})
        self.student.post("/api/register", json={"name": "Asha", "email": "asha@sit.ac.in", "password": "secret1"})

    def tearDown(self):
        try:
            os.remove(self.path)
        except OSError:
            pass

    def order(self, client=None, item=1, qty=1, slot="12:30", date=None):
        payload = {"items": [{"item_id": item, "qty": qty}], "slot": slot}
        if date:
            payload["date"] = date
        return (client or self.student).post("/api/orders", json=payload)

    def stock(self, item=1):
        return next(i["stock"] for i in self.staff.get("/api/menu?all=1").get_json() if i["id"] == item)

    def test_health(self):
        self.assertEqual(self.app.test_client().get("/health").get_json()["status"], "ok")

    def test_auth_rules(self):
        c = self.app.test_client()
        self.assertEqual(c.get("/api/menu").status_code, 401)
        self.assertEqual(c.post("/api/login", json={"email": "x@y.z", "password": "bad"}).status_code, 401)
        dup = c.post("/api/register", json={"name": "A", "email": "asha@sit.ac.in", "password": "secret1"})
        self.assertEqual(dup.status_code, 409)
        self.assertEqual(c.post("/api/register", json={"name": "A", "email": "a@b.co", "password": "123"}).status_code, 400)
        self.assertEqual(c.post("/api/register", json={"name": "", "email": "valid@email.com", "password": "secret1"}).status_code, 400)

        # Test me and logout
        me_resp = self.student.get("/api/me")
        self.assertEqual(me_resp.status_code, 200)
        self.assertEqual(me_resp.get_json()["email"], "asha@sit.ac.in")
        self.student.post("/api/logout")
        self.assertIsNone(self.student.get("/api/me").get_json())

    def test_menu_is_seeded_and_staff_only_edits(self):
        menu = self.student.get("/api/menu").get_json()
        # Requirement: At least 35 realistic food items
        self.assertGreaterEqual(len(menu), 35)

        # Check required categories are present
        categories = {item["category"] for item in menu}
        for expected in ("Breakfast", "Lunch", "Snacks", "Fast Food", "Beverages"):
            self.assertIn(expected, categories)

        # Check item fields including image
        first = menu[0]
        for field in ("id", "name", "category", "description", "price", "stock", "available", "image"):
            self.assertIn(field, first)

        # Non-staff cannot edit menu
        self.assertEqual(self.student.post("/api/menu", json={"name": "X", "price": 1, "stock": 1}).status_code, 403)

        # Staff can add items
        r = self.staff.post("/api/menu", json={
            "name": "Lemon Soda",
            "category": "Beverages",
            "price": 20,
            "stock": 10,
            "image": "https://example.com/soda.jpg"
        })
        self.assertEqual(r.status_code, 201)
        self.assertEqual(self.staff.post("/api/menu", json={"name": "", "price": 5, "stock": 1}).status_code, 400)

    def test_menu_search_and_filter_api(self):
        # Filter by category
        breakfast_items = self.student.get("/api/menu?category=Breakfast").get_json()
        self.assertTrue(all(i["category"] == "Breakfast" for i in breakfast_items))
        self.assertGreater(len(breakfast_items), 0)

        # Search query
        dosa_items = self.student.get("/api/menu?q=dosa").get_json()
        self.assertTrue(any("dosa" in (i["name"] + i["description"]).lower() for i in dosa_items))

        # Price sorting
        asc_items = self.student.get("/api/menu?sort=price_asc").get_json()
        prices = [i["price"] for i in asc_items]
        self.assertEqual(prices, sorted(prices))

        desc_items = self.student.get("/api/menu?sort=price_desc").get_json()
        prices_desc = [i["price"] for i in desc_items]
        self.assertEqual(prices_desc, sorted(prices_desc, reverse=True))

    def test_place_order_computes_total_and_reduces_stock(self):
        before = self.stock(1)
        r = self.order(item=1, qty=2)
        self.assertEqual(r.status_code, 201)
        body = r.get_json()
        self.assertEqual(body["token"], 1)
        self.assertEqual(body["payment_method"], "counter")
        self.assertEqual(body["payment_status"], "unpaid")
        self.assertEqual(self.stock(1), before - 2)

    def test_tokens_increment(self):
        self.order()
        self.assertEqual(self.order(slot="13:00").get_json()["token"], 2)

    def test_rejects_bad_orders(self):
        self.assertEqual(self.order(qty=999).status_code, 400)
        self.assertEqual(self.order(slot="noon").status_code, 400)
        self.assertEqual(self.student.post("/api/orders", json={"items": [], "slot": "12:00"}).status_code, 400)
        self.assertEqual(self.order(item=9999).status_code, 409)
        self.assertEqual(self.order(client=self.staff).status_code, 403)

        # Reject past date
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        self.assertEqual(self.order(date=yesterday).status_code, 400)

        # Reject far future date
        far_future = (datetime.now() + timedelta(days=20)).strftime("%Y-%m-%d")
        self.assertEqual(self.order(date=far_future).status_code, 400)

    def test_insufficient_stock_rolls_back(self):
        self.staff.put("/api/menu/1", json={"stock": 1})
        self.assertEqual(self.order(qty=2).status_code, 409)
        self.assertEqual(self.stock(1), 1)
        self.assertEqual(self.student.get("/api/orders").get_json(), [])

    def test_slot_capacity(self):
        self.assertEqual(self.order(slot="14:00").status_code, 201)
        self.assertEqual(self.order(slot="14:00").status_code, 201)
        self.assertEqual(self.order(slot="14:00").status_code, 409)

    def test_status_flow_and_permissions(self):
        oid = self.order().get_json()["id"]
        url = f"/api/orders/{oid}/status"
        self.assertEqual(self.student.post(url, json={"status": "ready"}).status_code, 403)
        self.assertEqual(self.staff.post(url, json={"status": "ready"}).status_code, 409)

        # Placed -> Accepted -> Preparing -> Ready -> Completed
        self.assertEqual(self.staff.post(url, json={"status": "accepted"}).status_code, 200)
        self.assertEqual(self.staff.post(url, json={"status": "preparing"}).status_code, 200)
        self.assertEqual(self.staff.post(url, json={"status": "ready"}).status_code, 200)
        self.assertEqual(self.staff.post(url, json={"status": "completed"}).status_code, 200)
        self.assertEqual(self.staff.post(url, json={"status": "cancelled"}).status_code, 409)

    def test_cancel_restores_stock(self):
        before = self.stock(1)
        oid = self.order(qty=3).get_json()["id"]
        self.assertEqual(self.student.post(f"/api/orders/{oid}/status", json={"status": "cancelled"}).status_code, 200)
        self.assertEqual(self.stock(1), before)

    def test_students_cannot_touch_others_orders(self):
        oid = self.order().get_json()["id"]
        other = self.app.test_client()
        other.post("/api/register", json={"name": "Ravi", "email": "ravi@sit.ac.in", "password": "secret1"})
        self.assertEqual(other.post(f"/api/orders/{oid}/status", json={"status": "cancelled"}).status_code, 404)
        self.assertEqual(other.get("/api/orders").get_json(), [])

    def test_staff_queue_and_stats(self):
        self.order(qty=2)
        q = self.staff.get("/api/orders").get_json()
        self.assertEqual(q[0]["customer"], "Asha")
        s = self.staff.get("/api/stats").get_json()
        self.assertEqual((s["orders"], s["pending"]), (1, 1))

    def test_future_pickup_slot_and_next_day_ordering(self):
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        # Check slots endpoint for tomorrow
        slots_resp = self.student.get(f"/api/slots?date={tomorrow}")
        self.assertEqual(slots_resp.status_code, 200)
        slots = slots_resp.get_json()
        self.assertGreater(len(slots), 10)
        self.assertEqual(slots[0]["date"], tomorrow)

        # Place order for tomorrow
        r = self.order(item=1, qty=1, slot="09:15", date=tomorrow)
        self.assertEqual(r.status_code, 201)
        order = r.get_json()
        self.assertEqual(order["order_date"], tomorrow)
        self.assertEqual(order["slot"], "09:15")
        self.assertEqual(order["token"], 1)

    def test_payment_tracking(self):
        oid = self.order().get_json()["id"]
        # Default payment status is unpaid
        order = self.student.get("/api/orders").get_json()[0]
        self.assertEqual(order["payment_status"], "unpaid")
        self.assertEqual(order["payment_method"], "counter")

        # Student cannot update payment status
        self.assertEqual(
            self.student.post(f"/api/orders/{oid}/payment", json={"payment_status": "paid"}).status_code,
            403
        )

        # Staff marks counter payment as paid
        pay_resp = self.staff.post(f"/api/orders/{oid}/payment", json={"payment_status": "paid"})
        self.assertEqual(pay_resp.status_code, 200)
        self.assertEqual(pay_resp.get_json()["payment_status"], "paid")

        # Check updated in staff list
        updated_order = self.staff.get("/api/orders").get_json()[0]
        self.assertEqual(updated_order["payment_status"], "paid")

    def test_staff_menu_crud(self):
        # Add item with image
        add_res = self.staff.post("/api/menu", json={
            "name": "Badaam Shake",
            "category": "Beverages",
            "description": "Chilled almond milk shake",
            "price": 45,
            "stock": 25,
            "image": "https://example.com/almond.jpg"
        })
        self.assertEqual(add_res.status_code, 201)
        item_id = add_res.get_json()["id"]

        # Edit item
        edit_res = self.staff.put(f"/api/menu/{item_id}", json={
            "name": "Kesar Badaam Shake",
            "price": 50,
            "stock": 30,
            "available": 1
        })
        self.assertEqual(edit_res.status_code, 200)

        # Verify edited item
        item = next(i for i in self.staff.get("/api/menu?all=1").get_json() if i["id"] == item_id)
        self.assertEqual(item["name"], "Kesar Badaam Shake")
        self.assertEqual(item["price"], 50)
        self.assertEqual(item["stock"], 30)

        # Delete (soft delete)
        del_res = self.staff.delete(f"/api/menu/{item_id}")
        self.assertEqual(del_res.status_code, 200)
        del_item = next(i for i in self.staff.get("/api/menu?all=1").get_json() if i["id"] == item_id)
        self.assertEqual(del_item["available"], 0)

    def test_qr_code_endpoint(self):
        # SVG endpoint
        res = self.app.test_client().get("/api/canteen-qr")
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.content_type.startswith("image/svg+xml"))
        self.assertIn(b"<svg", res.data)

        # Info JSON endpoint
        info_res = self.app.test_client().get("/api/canteen-qr/info")
        self.assertEqual(info_res.status_code, 200)
        info = info_res.get_json()
        self.assertIn("url", info)
        self.assertIn("svg", info)
        self.assertIn("<svg", info["svg"])


    # ------------------------------------------------------------------ #
    # New tests added for Bug 1, Bug 2 and Bug 3                          #
    # ------------------------------------------------------------------ #

    def test_bug1_search_api_returns_filtered_results(self):
        """Bug 1: Backend search must return correct filtered results for multi-char queries.
        The root fix is in the JS (focus-safe in-place update), but the API behaviour is
        confirmed here: searching 'Dosa', 'Burger', 'Rice' must each return ≥1 item whose
        name matches, and searching a nonsense term must return an empty list."""
        # Search "Dosa" — expect at least one dosa item
        dosa_items = self.student.get("/api/menu?q=Dosa").get_json()
        self.assertTrue(len(dosa_items) >= 1,
                        "API must return Dosa items for query 'Dosa'")
        self.assertTrue(all("dosa" in i["name"].lower() or "dosa" in i["description"].lower()
                            for i in dosa_items),
                        "Every result for 'Dosa' must contain 'dosa' in name or description")

        # Search "Burger"
        burger_items = self.student.get("/api/menu?q=Burger").get_json()
        self.assertTrue(len(burger_items) >= 1,
                        "API must return Burger items for query 'Burger'")

        # Search "Rice"
        rice_items = self.student.get("/api/menu?q=Rice").get_json()
        self.assertTrue(len(rice_items) >= 1,
                        "API must return Rice items for query 'Rice'")

        # Non-matching search must return empty list
        no_items = self.student.get("/api/menu?q=XYZZY_NO_MATCH_12345").get_json()
        self.assertEqual(no_items, [],
                         "API must return empty list for nonsense search query")

    def test_bug2_orders_persist_across_simulated_restart(self):
        """Bug 2: Orders must be permanently stored in SQLite and survive a server restart.
        We simulate this by creating a second app instance pointing at the same DB file and
        verifying the order placed through the first app appears in the second app's API."""
        # Place an order through normal client
        r = self.order(item=1, qty=1, slot="11:00")
        self.assertEqual(r.status_code, 201)
        placed = r.get_json()
        order_id = placed["id"]
        order_token = placed["token"]

        # Simulate server restart: create a new app pointing at the same DB
        app2 = create_app({"DB_PATH": self.path, "TESTING": True, "SLOT_CAPACITY": 2})
        staff2 = app2.test_client()
        staff2.post("/api/login", json={"email": "staff@canteen.local", "password": "staff123"})

        # Staff on the new instance must see the order from the old instance
        orders = staff2.get("/api/orders?all=1").get_json()
        self.assertTrue(any(o["id"] == order_id for o in orders),
                        "Order must survive a server restart (persist in SQLite)")
        found = next(o for o in orders if o["id"] == order_id)
        self.assertEqual(found["token"], order_token)
        self.assertEqual(found["status"], "placed")
        # Confirm items are present
        self.assertTrue(len(found["items"]) >= 1,
                        "Order items must also persist in SQLite across restart")

    def test_bug2_staff_get_orders_uses_correct_api_path(self):
        """Bug 2: Confirm that GET /api/orders (with ?all=1) returns all orders correctly,
        since the JS bug was calling /api/api/orders instead of /api/orders."""
        self.order(item=1, qty=1, slot="10:00")
        # Must work with no date filter (all=1)
        r = self.staff.get("/api/orders?all=1")
        self.assertEqual(r.status_code, 200,
                         "GET /api/orders?all=1 must return 200, not 404")
        orders = r.get_json()
        self.assertIsInstance(orders, list)
        self.assertEqual(len(orders), 1)

        # Must work with explicit date filter
        today = datetime.now().strftime("%Y-%m-%d")
        r2 = self.staff.get(f"/api/orders?date={today}")
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(len(r2.get_json()), 1)

    def test_bug3_accept_order_updates_status_in_db(self):
        """Bug 3: POST /api/orders/<id>/status with status=accepted must:
        1) Return HTTP 200 with ok=True and status='accepted'.
        2) Persist the new status in SQLite (confirmed by re-fetching the order).
        3) The status must still be 'accepted' after a simulated restart."""
        # Student places order
        r = self.order(item=1, qty=1, slot="13:30")
        self.assertEqual(r.status_code, 201)
        order_id = r.get_json()["id"]

        # Staff clicks Accept
        accept_resp = self.staff.post(f"/api/orders/{order_id}/status",
                                      json={"status": "accepted"})
        self.assertEqual(accept_resp.status_code, 200,
                         "Accept endpoint must return 200")
        body = accept_resp.get_json()
        self.assertTrue(body.get("ok"), "Response must contain ok=True")
        self.assertEqual(body.get("status"), "accepted",
                         "Response must echo back status='accepted'")

        # Verify persisted in DB via fresh fetch
        orders = self.staff.get("/api/orders?all=1").get_json()
        found = next((o for o in orders if o["id"] == order_id), None)
        self.assertIsNotNone(found, "Order must appear in staff list after acceptance")
        self.assertEqual(found["status"], "accepted",
                         "Status in DB must be 'accepted' after Accept is clicked")

        # Simulate server restart — status must survive
        app2 = create_app({"DB_PATH": self.path, "TESTING": True, "SLOT_CAPACITY": 2})
        staff2 = app2.test_client()
        staff2.post("/api/login", json={"email": "staff@canteen.local", "password": "staff123"})
        orders2 = staff2.get("/api/orders?all=1").get_json()
        found2 = next((o for o in orders2 if o["id"] == order_id), None)
        self.assertIsNotNone(found2)
        self.assertEqual(found2["status"], "accepted",
                         "Accepted status must persist across server restart")

    def test_bug3_invalid_status_transition_rejected(self):
        """Bug 3 guard: Attempting an invalid status jump must return 409, not silently fail."""
        order_id = self.order().get_json()["id"]
        # Cannot jump from placed -> completed directly
        r = self.staff.post(f"/api/orders/{order_id}/status", json={"status": "completed"})
        self.assertEqual(r.status_code, 409,
                         "Invalid status transition must be rejected with 409")
        # Order status must remain 'placed'
        orders = self.staff.get("/api/orders?all=1").get_json()
        found = next(o for o in orders if o["id"] == order_id)
        self.assertEqual(found["status"], "placed")


if __name__ == "__main__":
    unittest.main()
