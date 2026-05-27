from django.contrib import admin
from transactions.models import Transaction

@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display  = [
        'transaction_id', 'user_id', 'merchant_id',
        'amount', 'category', 'country_code', 'status', 'timestamp',
    ]
    list_filter   = ['status', 'country_code']
    search_fields = ['transaction_id', '=user_id']
    list_per_page = 50
    ordering      = ['-timestamp']
