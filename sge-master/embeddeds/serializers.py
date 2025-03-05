from rest_framework import serializers
from embeddeds.models import Embedded


class EmbeddedSerializer(serializers.ModelSerializer):

    class Meta:
        model = Embedded
        fields = '__all__'
