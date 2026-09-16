from rest_framework.views import exception_handler as drf_handler

def exception_handler(exc, context):
    response=drf_handler(exc,context)
    if response is not None:
        detail=response.data
        response.data={'error':str(detail.get('detail','Request validation failed')) if isinstance(detail,dict) else 'Request validation failed', 'details':detail}
    return response
