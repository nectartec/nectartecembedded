from rest_framework import serializers
from clienteshtmls.models import Clienteshtml


class ClienteshtmlSerializer(serializers.ModelSerializer):

    class Meta:
        model = Clienteshtml
        fields = '__all__'
