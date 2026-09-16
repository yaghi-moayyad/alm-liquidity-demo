class ResponsePolicyMiddleware:
    def __init__(self,get_response): self.get_response=get_response
    def __call__(self,request):
        response=self.get_response(request)
        if not request.path.startswith('/static/'):
            response['Cache-Control']='no-store'
        # Django admin and DRF's browsable API manage their own bundled scripts.
        if request.path in ('/','/accounts/login/','/api-docs'):
            response['Content-Security-Policy']="default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; form-action 'self'"
        return response
