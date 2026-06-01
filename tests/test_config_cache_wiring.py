import unittest
from unittest.mock import AsyncMock, patch


class TestMasterConfigCacheWiring(unittest.IsolatedAsyncioTestCase):
    async def test_get_delegates_to_versioned_cache(self):
        import app.services.master_config as mc
        sentinel = object()
        fake_cache = AsyncMock()
        fake_cache.get.return_value = sentinel
        with patch.object(mc, "_cache", fake_cache):
            result = await mc.get_master_config(db=AsyncMock())
        self.assertIs(result, sentinel)
        self.assertEqual(fake_cache.get.await_count, 1)

    async def test_update_bumps_cache_with_new_config(self):
        import app.services.master_config as mc
        db = AsyncMock()
        updated = object()
        db.get.return_value = object()  # existing row
        db.refresh = AsyncMock()
        fake_cache = AsyncMock()
        with patch.object(mc, "_cache", fake_cache), \
             patch.object(mc, "_apply_and_refresh", AsyncMock(return_value=updated)):
            await mc.update_master_config(db, {"temperature": 0.5})
        fake_cache.bump.assert_awaited_once_with(updated)

    async def test_invalidate_is_async_and_bumps(self):
        import app.services.master_config as mc
        fake_cache = AsyncMock()
        with patch.object(mc, "_cache", fake_cache):
            await mc.invalidate_cache()
        fake_cache.bump.assert_awaited_once_with()


class TestSecuritySettingsCacheWiring(unittest.IsolatedAsyncioTestCase):
    async def test_get_delegates_to_versioned_cache(self):
        import app.services.security_settings as ss
        sentinel = object()
        fake_cache = AsyncMock()
        fake_cache.get.return_value = sentinel
        with patch.object(ss, "_cache", fake_cache):
            result = await ss.get_security_settings(db=AsyncMock())
        self.assertIs(result, sentinel)
        self.assertEqual(fake_cache.get.await_count, 1)

    async def test_update_bumps_cache_with_new_settings(self):
        import app.services.security_settings as ss
        db = AsyncMock()
        updated = object()
        with patch.object(ss, "_cache", AsyncMock()) as fake_cache, \
             patch.object(ss, "_apply_and_refresh", AsyncMock(return_value=updated)):
            await ss.update_security_settings(db, {"max_login_attempts": 3})
        fake_cache.bump.assert_awaited_once_with(updated)

    async def test_invalidate_is_async_and_bumps(self):
        import app.services.security_settings as ss
        fake_cache = AsyncMock()
        with patch.object(ss, "_cache", fake_cache):
            await ss.invalidate_cache()
        fake_cache.bump.assert_awaited_once_with()


if __name__ == "__main__":
    unittest.main()
