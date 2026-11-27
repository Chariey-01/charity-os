from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from config.health_probe import health_body


# GET and HEAD are answered by config.health_probe.HealthProbeMiddleware before
# they reach this view; it remains for the URL name and the other methods (405).
@api_view(["GET"])
@permission_classes([AllowAny])
def health(request):
    body, status = health_body()
    return Response(body, status=status)
