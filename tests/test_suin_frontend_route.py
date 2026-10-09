"""Read-only ASGI smoke checks; no account, health record, or DB startup is used."""

import unittest

import httpx

from app.main import app


class SuinFrontendRouteTests(unittest.IsolatedAsyncioTestCase):
    async def test_root_redirects_to_retro_intro_on_the_server(self):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
            follow_redirects=False,
        ) as client:
            response = await client.get("/")

        self.assertEqual(response.status_code, 307)
        self.assertEqual(
            response.headers["location"],
            "/static/intro-retro.html?v=20260917-server-entry-v1",
        )
        self.assertIn("no-store", response.headers["cache-control"])

    async def test_explicit_auth_entry_serves_the_customer_interface(self):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
            follow_redirects=False,
        ) as client:
            response = await client.get("/?auth=signup&cache=retro-entry-20260909")

        self.assertEqual(response.status_code, 200)
        self.assertIn('id="signup-form"', response.text)
        self.assertIn("no-store", response.headers["cache-control"])

    async def test_service_and_namespaced_assets(self):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
            response = await client.get("/service?returnTo=forest-challenges")
            self.assertEqual(response.status_code, 200)
            self.assertIn('id="login-form"', response.text)
            self.assertIn("/static/app.js", response.text)
            self.assertNotIn("/static/suin/app.js", response.text)
            self.assertIn("no-store", response.headers["cache-control"])
            for resource in ("app.js", "styles.css", "assets/hyeoldangi-consent.png"):
                asset = await client.get(f"/static/suin/{resource}")
                self.assertEqual(asset.status_code, 200, resource)

    async def test_unsigned_user_cannot_refresh_or_access_challenge(self):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
            for resource in ("/api/v1/auth/token/refresh", "/api/v1/challenge-v2/today"):
                response = await client.get(resource)
                self.assertEqual(response.status_code, 401, resource)


if __name__ == "__main__":
    unittest.main()
