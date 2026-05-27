from django.urls import path

from transactions.views import (
    AnalyticsSummaryView,
    BatchInsertView,
    HealthView,
    TopMerchantsView,
    UserStatsView,
    UserTransactionsView,
)

urlpatterns = [
    path('health',
         HealthView.as_view(), name='health'),
    path('analytics/summary',
         AnalyticsSummaryView.as_view(), name='analytics-summary'),
    path('analytics/top-merchants',
         TopMerchantsView.as_view(), name='analytics-top-merchants'),
    path('users/<int:user_id>/transactions',
         UserTransactionsView.as_view(), name='user-transactions'),
    path('users/<int:user_id>/stats',
         UserStatsView.as_view(), name='user-stats'),
    path('transactions/batch',
         BatchInsertView.as_view(), name='batch-insert'),
]
