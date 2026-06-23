import os
import sqlite3
import time
import httpx

BASE_URL = "http://localhost:8000"

def create_test_db(filename="customers.csv"):
    """Create a temporary CSV file with mock rows."""
    if os.path.exists(filename):
        os.remove(filename)
    
    import csv
    with open(filename, mode='w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(["id", "name", "city", "sales_limit"])
        writer.writerows([
            [1, "Alice", "New York", 50000.0],
            [2, "Bob", "Boston", 75000.0],
            [3, "Charlie", "New York", 120000.0],
            [4, "David", "San Francisco", 90000.0]
        ])
    print(f"Created local test CSV file: {filename}")

def run_tests():
    # 1. Create CSV DB
    db_filename = "customers.csv"
    create_test_db(db_filename)
    
    client = httpx.Client(base_url=BASE_URL, timeout=60.0)
    
    # Use unique emails to prevent conflicts on repeated runs
    timestamp = int(time.time())
    analyst_email = f"analyst_{timestamp}@example.com"
    admin_email = f"admin_{timestamp}@example.com"
    password = "SecurePassword123"

    print("\n--- E2E INTEGRATION TEST START ---")
    
    try:
        # Step 1: Register Analyst
        print("\n[Step 1] Registering Analyst...")
        reg_res = client.post("/auth/register", json={
            "email": analyst_email,
            "password": password,
            "role": "analyst"
        })
        assert reg_res.status_code == 201, f"Reg failed: {reg_res.text}"
        print(f"Successfully registered analyst: {analyst_email}")

        # Step 2: Register Admin
        print("\n[Step 2] Registering Admin...")
        reg_admin_res = client.post("/auth/register", json={
            "email": admin_email,
            "password": password,
            "role": "admin"
        })
        assert reg_admin_res.status_code == 201, f"Admin reg failed: {reg_admin_res.text}"
        print(f"Successfully registered admin: {admin_email}")

        # Step 3: Login Analyst
        print("\n[Step 3] Logging in Analyst...")
        login_res = client.post("/auth/login", json={
            "email": analyst_email,
            "password": password
        })
        assert login_res.status_code == 200, f"Login failed: {login_res.text}"
        tokens = login_res.json()
        access_token = tokens["access_token"]
        refresh_token = tokens["refresh_token"]
        print("Logged in. Received Access Token & Refresh Token.")

        # Header for authenticated analyst requests
        analyst_headers = {"Authorization": f"Bearer {access_token}"}

        # Step 4: Validate Refresh Token Rotation
        print("\n[Step 4] Testing Refresh Token Rotation...")
        refresh_res = client.post("/auth/refresh", json={
            "refresh_token": refresh_token
        })
        assert refresh_res.status_code == 200, f"Refresh failed: {refresh_res.text}"
        new_tokens = refresh_res.json()
        new_access_token = new_tokens["access_token"]
        new_refresh_token = new_tokens["refresh_token"]
        assert new_access_token != access_token, "Access token was not rotated"
        assert new_refresh_token != refresh_token, "Refresh token was not rotated"
        print("Successfully rotated access and refresh tokens.")

        # Update analyst headers
        analyst_headers = {"Authorization": f"Bearer {new_access_token}"}

        # Step 5: Upload CSV Database & Index Schema
        print("\n[Step 5] Uploading CSV Database file...")
        with open(db_filename, "rb") as f:
            upload_res = client.post(
                "/database/upload",
                files={"file": (db_filename, f, "text/csv")},
                headers={"Authorization": f"Bearer {new_access_token}"}
            )
        assert upload_res.status_code == 201, f"Upload failed: {upload_res.text}"
        upload_data = upload_res.json()
        db_id = upload_data["id"]
        assert "customers" in upload_data["tables"], "Schema extraction missing 'customers' table"
        print(f"Uploaded DB. ID: {db_id}. Tables: {upload_data['tables']}")

        # Pause to let Kafka process schema-events
        time.sleep(2)

        # Step 6: Execute Natural Language Query (Fresh Cache Miss)
        print("\n[Step 6] Running Natural Language Query (Cache Miss)...")
        query_payload = {
            "db_id": db_id,
            "question": "Show me the names of all customers who live in New York"
        }
        query_res = client.post("/query", json=query_payload, headers=analyst_headers)
        assert query_res.status_code == 200, f"Query failed: {query_res.text}"
        query_data = query_res.json()
        print(f"Generated SQL: {query_data['sql']}")
        print(f"Explanation: {query_data['explanation']}")
        print(f"Confidence: {query_data['confidence']}")
        print(f"Latency: {query_data['execution_time']}s")
        print(f"Cached: {query_data['cached']}")
        assert query_data["cached"] is False, "Expected cache miss"
        
        # Verify result contains New York customers (Alice and Charlie)
        results = query_data["results"]
        assert results is not None, "Results should not be null"
        names = [r["name"] for r in results]
        assert "Alice" in names and "Charlie" in names, f"Unexpected results: {results}"
        print(f"Results match expectation: {results}")

        # Step 7: Re-run Natural Language Query (Cache Hit)
        print("\n[Step 7] Re-running query to check Redis caching...")
        query_res_cached = client.post("/query", json=query_payload, headers=analyst_headers)
        assert query_res_cached.status_code == 200, f"Query failed: {query_res_cached.text}"
        query_data_cached = query_res_cached.json()
        print(f"Cached query status -> Cached: {query_data_cached['cached']}")
        assert query_data_cached["cached"] is True, "Expected cache hit in Redis"

        # Step 8: Log in Admin and Fetch Users List
        print("\n[Step 8] Logging in Admin & Verifying Access Control...")
        admin_login_res = client.post("/auth/login", json={
            "email": admin_email,
            "password": password
        })
        assert admin_login_res.status_code == 200
        admin_access_token = admin_login_res.json()["access_token"]
        admin_headers = {"Authorization": f"Bearer {admin_access_token}"}

        users_res = client.get("/admin/users", headers=admin_headers)
        assert users_res.status_code == 200
        users_list = [u["email"] for u in users_res.json()]
        assert analyst_email in users_list, "Analyst user missing in admin list"
        assert admin_email in users_list, "Admin user missing in admin list"
        print("Admin user verified successfully. Users list retrieved.")

        # Step 9: Get Admin Performance Stats
        print("\n[Step 9] Retrieving admin metrics & stats...")
        stats_res = client.get("/admin/stats", headers=admin_headers)
        assert stats_res.status_code == 200, f"Stats retrieval failed: {stats_res.text}"
        stats_data = stats_res.json()
        print(f"Total system queries: {stats_data['total_queries']}")
        print(f"Cache Hit Rate: {stats_data['cache_hit_rate'] * 100}%")
        print(f"Average Latency: {stats_data['avg_latency_seconds']}s")
        assert stats_data["total_queries"] >= 2, "Expected at least 2 logged queries"
        
        # Step 10: Verify Rate Limiter
        print("\n[Step 10] Testing Rate Limiter (Sending burst queries)...")
        # Send rapid queries to hit the 10 queries per minute threshold
        rate_limited_hit = False
        for i in range(12):
            res = client.post("/query", json=query_payload, headers=analyst_headers)
            if res.status_code == 429:
                rate_limited_hit = True
                retry_after = res.headers.get("Retry-After")
                print(f"Successfully triggered rate limiter! Status 429 received. Retry-After: {retry_after}s")
                break
        
        # We might not hit if caching is extremely fast and doesn't trigger limits? 
        # Actually rate limits apply to /query routes, including cache hits. So we should hit 429!
        assert rate_limited_hit, "Rate limiter did not trigger 429 on burst request"

        # Step 11: Log Out Analyst
        print("\n[Step 11] Logging out analyst...")
        logout_res = client.post("/auth/logout", headers=analyst_headers)
        assert logout_res.status_code == 200, f"Logout failed: {logout_res.text}"
        print("Analyst session logged out successfully.")

        # Step 12: Validate Refresh Token Revocation
        print("\n[Step 12] Validating rotated refresh token revocation...")
        bad_refresh_res = client.post("/auth/refresh", json={
            "refresh_token": new_refresh_token
        })
        assert bad_refresh_res.status_code == 401, "Expected 401 on logged-out refresh token"
        print("Refresh token was successfully revoked and blacklisted in Redis.")

        # Step 13: Clean up Database connections via DELETE
        print("\n[Step 13] Cleaning up resources (DELETE /database/{id})...")
        delete_res = client.delete(f"/database/{db_id}", headers=admin_headers)
        assert delete_res.status_code == 200
        print("Database connection and vector storage indexes purged.")

        print("\n====================================")
        print("ALL TESTS PASSED SUCCESSFULLY! (100% OK)")
        print("====================================")

    except AssertionError as ae:
        print(f"\nAssertion Failed: {ae}")
        raise ae
    except Exception as e:
        print(f"\nError encountered during test run: {e}")
        raise e
    finally:
        # Clean up database file
        if os.path.exists(db_filename):
            os.remove(db_filename)

if __name__ == "__main__":
    run_tests()
