import uuid

from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

class BaseTestCase(TestCase):
    """Setup compartido: crea un usuario con token para los tests autenticados."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user  = User.objects.create_user(username='testuser', password='testpass')
        cls.token = Token.objects.create(user=cls.user)

        cls.public_client = APIClient()

        cls.auth_client = APIClient()
        cls.auth_client.credentials(HTTP_AUTHORIZATION=f'Token {cls.token.key}')

# --- 1. Health ───

class HealthTests(BaseTestCase):
    def test_health_returns_200(self):
        resp = self.public_client.get('/health')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['status'], 'ok')
        self.assertIn('uptime_s', resp.data)
        self.assertIn('cache_hit_rate', resp.data)

# --- 2-3. Analytics (public) ───

class AnalyticsTests(BaseTestCase):
    def test_summary_structure(self):
        resp = self.public_client.get('/analytics/summary')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('total_count', resp.data)
        self.assertIn('total_amount', resp.data)
        self.assertIn('by_country', resp.data)
        self.assertIn('by_category', resp.data)

    def test_top_merchants_default(self):
        resp = self.public_client.get('/analytics/top-merchants')
        self.assertEqual(resp.status_code, 200)
        self.assertIsInstance(resp.data, list)
        self.assertLessEqual(len(resp.data), 10)

# --- 4-7. User endpoints (requires token) ───

class UserEndpointTests(BaseTestCase):
    def test_transactions_requires_auth(self):
        resp = self.public_client.get('/users/1/transactions')
        self.assertEqual(resp.status_code, 401)

    def test_transactions_with_token(self):
        resp = self.auth_client.get('/users/1/transactions')
        self.assertIn(resp.status_code, [200, 404])

    def test_stats_with_token(self):
        resp = self.auth_client.get('/users/1/stats')
        self.assertIn(resp.status_code, [200, 404])

    def test_user_not_found_404(self):
        resp = self.auth_client.get('/users/99999999/transactions')
        self.assertEqual(resp.status_code, 404)

# --- 8-9. Batch (requires token) ───

class BatchTests(BaseTestCase):
    def test_batch_requires_auth(self):
        resp = self.public_client.post('/transactions/batch', [], format='json')
        self.assertEqual(resp.status_code, 401)

    def test_batch_valid(self):
        txns = [
            {
                'transaction_id': str(uuid.uuid4()),
                'timestamp':      '2026-05-01 12:00:00',
                'user_id':        1,
                'merchant_id':    1,
                'amount':         100.50,
                'category':       'Food',
                'country_code':   'MX',
                'status':         'completed',
            }
        ]
        resp = self.auth_client.post('/transactions/batch', txns, format='json')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['received'], 1)
        self.assertEqual(resp.data['inserted'], 1)

    def test_batch_invalid_schema_422(self):
        bad = [{'transaction_id': 'x', 'amount': 'not_a_number'}]
        resp = self.auth_client.post('/transactions/batch', bad, format='json')
        self.assertEqual(resp.status_code, 422)
