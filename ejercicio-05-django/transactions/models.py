from django.db import models

class Transaction(models.Model):
    transaction_id = models.CharField(max_length=36, primary_key=True)
    timestamp      = models.DateTimeField()
    user_id        = models.IntegerField()
    merchant_id    = models.IntegerField()
    amount         = models.FloatField()
    category       = models.CharField(max_length=20)
    country_code   = models.CharField(max_length=2)
    status         = models.CharField(max_length=10)

    class Meta:
        indexes = [
            models.Index(fields=['user_id', 'timestamp'], name='idx_user_timestamp'),
            models.Index(fields=['country_code', 'user_id'], name='idx_country_user'),
        ]

    def __str__(self):
        return f"{self.transaction_id} | {self.user_id} | {self.amount}"
