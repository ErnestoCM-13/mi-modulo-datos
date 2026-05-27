from rest_framework import serializers
from transactions.models import Transaction

class TransactionSerializer(serializers.ModelSerializer):
    """Serializer de lectura — convierte objetos Transaction a JSON."""

    class Meta:
        model  = Transaction
        fields = '__all__'

class TransactionInSerializer(serializers.Serializer):
    """Serializer de escritura — valida datos de entrada para batch insert."""

    transaction_id = serializers.CharField(max_length=36)
    timestamp      = serializers.CharField()
    user_id        = serializers.IntegerField()
    merchant_id    = serializers.IntegerField()
    amount         = serializers.FloatField()
    category       = serializers.CharField(max_length=20)
    country_code   = serializers.CharField(max_length=2)
    status         = serializers.CharField(max_length=10)
